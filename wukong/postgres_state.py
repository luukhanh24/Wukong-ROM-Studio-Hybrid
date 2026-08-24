from __future__ import annotations

import json
import hashlib
import threading
import uuid
from collections.abc import Callable
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from .models import BuildRecipe, Identity, JobManifest, JobStatus, utc_now
from .orchestrator import JobEvent, JobStore, OrchestrationError, TERMINAL_STATUSES
from .telegram import BuildQuotaError, require_sensitive_admin_reason


class _Cursor(Protocol):
    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list[Any]: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[], _Connection]


class _DatabaseStore:
    """Shared connection and SQL-dialect handling for control-plane stores."""

    def __init__(
        self,
        database_url: str | None,
        *,
        connect: ConnectionFactory | None,
        dialect: str,
    ) -> None:
        if dialect not in {"postgresql", "sqlite"}:
            raise ValueError("Database dialect must be postgresql or sqlite")
        if connect is None:
            normalized_url = str(database_url or "").strip()
            if not normalized_url:
                raise ValueError("DATABASE_URL is required for PostgreSQL state")
            try:
                import psycopg
            except ImportError as exc:  # pragma: no cover - packaging contract
                raise RuntimeError("psycopg is required for PostgreSQL state") from exc
            connect = lambda: psycopg.connect(normalized_url)
        self._connect = connect
        self._dialect = dialect

    def _sql(self, statement: str) -> str:
        return statement if self._dialect == "sqlite" else statement.replace("?", "%s")

    @contextmanager
    def _connection(self) -> Iterator[_Connection]:
        connection = self._connect()
        try:
            if self._dialect == "sqlite":
                connection.cursor().execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class PostgresTelegramUIStateStore(_DatabaseStore):
    """Durable Telegram UI preferences without persisting signed source URLs."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: ConnectionFactory | None = None,
        dialect: str = "postgresql",
    ) -> None:
        super().__init__(database_url, connect=connect, dialect=dialect)
        self._lock = threading.RLock()
        with self._connection() as connection:
            connection.cursor().execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_ui_state (
                    subject TEXT PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'vi',
                    session_json TEXT NOT NULL DEFAULT '{}',
                    job_refs_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    @staticmethod
    def _json_object(value: object) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @classmethod
    def _safe_session(cls, session: Mapping[str, Any]) -> dict[str, Any]:
        persisted = cls._json_object(json.loads(json.dumps(dict(session))))
        source = persisted.get("source")
        uri = str(source.get("uri") or "") if isinstance(source, Mapping) else ""
        if (
            isinstance(source, Mapping)
            and source.get("kind") in {"http", "https"}
            and "?" in uri
        ):
            persisted.pop("source", None)
            persisted.update({"step": "source_input", "awaiting": "url"})
        return persisted

    def _row(self, subject: str) -> Any:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT language, session_json, job_refs_json "
                    "FROM wukong_telegram_ui_state WHERE subject = ?"
                ),
                (subject,),
            )
            return cursor.fetchone()

    def language(self, user_id: int | str) -> str:
        row = self._row(str(user_id))
        value = str(row[0]) if row is not None else "vi"
        return value if value in {"vi", "en"} else "vi"

    def set_language(self, user_id: int | str, language: str) -> None:
        if language not in {"vi", "en"}:
            raise ValueError("Unsupported language")
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql(
                    "INSERT INTO wukong_telegram_ui_state (subject, language) VALUES (?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET language = excluded.language"
                ),
                (str(user_id), language),
            )

    def session(self, user_id: int | str) -> dict[str, Any]:
        row = self._row(str(user_id))
        return self._json_object(json.loads(str(row[1]))) if row is not None else {}

    def set_session(self, user_id: int | str, session: Mapping[str, Any]) -> None:
        safe_session = self._safe_session(session)
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql(
                    "INSERT INTO wukong_telegram_ui_state (subject, session_json) VALUES (?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET session_json = excluded.session_json"
                ),
                (
                    str(user_id),
                    json.dumps(safe_session, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def clear_session(self, user_id: int | str) -> None:
        self.set_session(user_id, {})

    def remember_job(self, user_id: int | str, job_id: str) -> str:
        subject = str(user_id)
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT job_refs_json FROM wukong_telegram_ui_state WHERE subject = ?"
                ),
                (subject,),
            )
            row = cursor.fetchone()
            references = self._json_object(json.loads(str(row[0]))) if row is not None else {}
            digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()
            length = 12
            reference = digest[:length]
            while reference in references and references[reference] != job_id:
                length += 4
                reference = digest[:length]
            references[reference] = job_id
            encoded = json.dumps(references, ensure_ascii=False, separators=(",", ":"))
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_ui_state (subject, job_refs_json) VALUES (?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET job_refs_json = excluded.job_refs_json"
                ),
                (subject, encoded),
            )
        return reference

    def resolve_job(self, user_id: int | str, reference: str) -> str | None:
        row = self._row(str(user_id))
        if row is None:
            return None
        references = self._json_object(json.loads(str(row[2])))
        value = references.get(reference)
        return str(value) if value else None

    def import_state(
        self,
        subject: str,
        *,
        language: str,
        session: Mapping[str, Any],
        job_refs: Mapping[str, Any],
    ) -> bool:
        normalized_language = language if language in {"vi", "en"} else "vi"
        safe_session = self._safe_session(session)
        safe_refs = self._json_object(json.loads(json.dumps(dict(job_refs))))
        existing = self._row(subject)
        if existing is not None:
            return False
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql(
                    "INSERT INTO wukong_telegram_ui_state "
                    "(subject, language, session_json, job_refs_json) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET "
                    "language = excluded.language, "
                    "session_json = excluded.session_json, "
                    "job_refs_json = excluded.job_refs_json"
                ),
                (
                    subject,
                    normalized_language,
                    json.dumps(safe_session, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(safe_refs, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        return True


class PostgresTelegramAccessStore(_DatabaseStore):
    """Durable Telegram profiles, access audit and build-credit ledger."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        admin_ids: list[int | str] | tuple[int | str, ...] = (),
        connect: ConnectionFactory | None = None,
        dialect: str = "postgresql",
    ) -> None:
        super().__init__(database_url, connect=connect, dialect=dialect)
        self._configured_admins = {
            str(value).strip() for value in admin_ids if str(value).strip()
        }
        self._lock = threading.RLock()
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_access (
                    subject TEXT PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user'))
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_users (
                    subject TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    access_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (access_status IN ('pending', 'approved', 'revoked')),
                    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    mini_app_open_count INTEGER NOT NULL DEFAULT 0,
                    job_count INTEGER NOT NULL DEFAULT 0,
                    build_credits INTEGER NOT NULL DEFAULT 0 CHECK (build_credits >= 0),
                    unlimited INTEGER NOT NULL DEFAULT 0,
                    lifetime_granted INTEGER NOT NULL DEFAULT 0,
                    lifetime_used INTEGER NOT NULL DEFAULT 0,
                    last_job_id TEXT NOT NULL DEFAULT '',
                    last_job_status TEXT NOT NULL DEFAULT '',
                    approved_at TEXT NOT NULL DEFAULT '',
                    revoked_at TEXT NOT NULL DEFAULT '',
                    access_actor TEXT NOT NULL DEFAULT '',
                    access_reason TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT '',
                    app_version TEXT NOT NULL DEFAULT '',
                    configured_admin INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_user_events (
                    event_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_subject TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_sessions (
                    subject TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    PRIMARY KEY (subject, session_id),
                    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_quota_ledger (
                    ledger_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    delta INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    job_id TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT UNIQUE,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    actor_subject TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS wukong_telegram_users_seen_idx "
                "ON wukong_telegram_users(last_seen_at DESC)"
            )
            now = utc_now()
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_users "
                    "(subject, access_status, role, first_seen_at, last_seen_at, build_credits, "
                    "unlimited, lifetime_granted) "
                    "SELECT subject, 'approved', role, ?, ?, CASE WHEN role = 'user' THEN 1 ELSE 0 END, "
                    "CASE WHEN role = 'admin' THEN 1 ELSE 0 END, CASE WHEN role = 'user' THEN 1 ELSE 0 END "
                    "FROM wukong_telegram_access WHERE 1 = 1 ON CONFLICT (subject) DO NOTHING"
                ),
                (now, now),
            )
            for subject in self._configured_admins:
                cursor.execute(
                    self._sql(
                        "INSERT INTO wukong_telegram_users "
                        "(subject, access_status, role, first_seen_at, last_seen_at, unlimited, configured_admin) "
                        "VALUES (?, 'approved', 'admin', ?, ?, 1, 1) "
                        "ON CONFLICT (subject) DO UPDATE SET access_status = 'approved', role = 'admin', "
                        "unlimited = 1, build_credits = 0, configured_admin = 1"
                    ),
                    (subject, now, now),
                )

    @staticmethod
    def _require_admin(actor: Identity) -> None:
        if actor.channel != "telegram" or actor.role != "admin":
            raise PermissionError("Admin access is required")

    def identity(self, user_id: int | str) -> Identity | None:
        subject = str(user_id).strip()
        if subject in self._configured_admins:
            return Identity("telegram", subject, "admin")
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT role FROM wukong_telegram_users "
                    "WHERE subject = ? AND access_status = 'approved'"
                ),
                (subject,),
            )
            row = cursor.fetchone()
        return Identity("telegram", subject, str(row[0])) if row is not None else None

    @staticmethod
    def _profile_payload(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        keys = (
            "telegramId", "username", "displayName", "accessStatus", "role",
            "firstSeenAt", "lastSeenAt", "miniAppOpenCount", "jobCount",
            "buildCredits", "unlimited", "lifetimeGranted", "lifetimeUsed",
            "lastJobId", "lastJobStatus", "approvedAt", "revokedAt",
            "accessActor", "accessReason", "language", "platform", "appVersion",
            "configuredAdmin",
        )
        payload = dict(zip(keys, row))
        for key in (
            "miniAppOpenCount", "jobCount", "buildCredits", "lifetimeGranted", "lifetimeUsed"
        ):
            payload[key] = int(payload[key] or 0)
        payload["unlimited"] = bool(payload["unlimited"])
        payload["configuredAdmin"] = bool(payload["configuredAdmin"])
        return payload

    @staticmethod
    def _profile_columns() -> str:
        return (
            "subject, username, display_name, access_status, role, first_seen_at, last_seen_at, "
            "mini_app_open_count, job_count, build_credits, unlimited, lifetime_granted, "
            "lifetime_used, last_job_id, last_job_status, approved_at, revoked_at, access_actor, "
            "access_reason, language, platform, app_version, configured_admin"
        )

    @staticmethod
    def _subject(user_id: int | str) -> str:
        subject = str(user_id).strip()
        if not subject or not subject.isascii() or not subject.isdigit() or int(subject) <= 0:
            raise ValueError("Telegram user ID is required")
        return subject

    @staticmethod
    def _display_name(user: Mapping[str, object]) -> str:
        return " ".join(
            value for value in (str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()) if value
        )[:256]

    def _insert_pending(self, cursor: _Cursor, subject: str, now: str) -> None:
        cursor.execute(
            self._sql(
                "INSERT INTO wukong_telegram_users (subject, first_seen_at, last_seen_at) "
                "VALUES (?, ?, ?) ON CONFLICT (subject) DO NOTHING"
            ),
            (subject, now, now),
        )

    def _append_event(
        self,
        cursor: _Cursor,
        subject: str,
        event_type: str,
        *,
        actor: str = "",
        reason: str = "",
        details: Mapping[str, object] | None = None,
    ) -> None:
        cursor.execute(
            self._sql(
                "INSERT INTO wukong_telegram_user_events "
                "(event_id, subject, event_type, actor_subject, reason, details_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                uuid.uuid4().hex,
                subject,
                event_type,
                actor,
                str(reason or "")[:1024],
                json.dumps(dict(details or {}), ensure_ascii=False, separators=(",", ":")),
                utc_now(),
            ),
        )

    def observe_user(
        self,
        user_id: int | str,
        *,
        username: str = "",
        display_name: str = "",
        language: str = "",
        platform: str = "",
        app_version: str = "",
    ) -> dict[str, Any]:
        subject = self._subject(user_id)
        now = utc_now()
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT 1 FROM wukong_telegram_users WHERE subject = ?"),
                (subject,),
            )
            created = cursor.fetchone() is None
            self._insert_pending(cursor, subject, now)
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET last_seen_at = ?, "
                    "username = CASE WHEN ? <> '' THEN ? ELSE username END, "
                    "display_name = CASE WHEN ? <> '' THEN ? ELSE display_name END, "
                    "language = CASE WHEN ? <> '' THEN ? ELSE language END, "
                    "platform = CASE WHEN ? <> '' THEN ? ELSE platform END, "
                    "app_version = CASE WHEN ? <> '' THEN ? ELSE app_version END "
                    "WHERE subject = ?"
                ),
                (
                    now,
                    str(username or "")[:256], str(username or "")[:256],
                    str(display_name or "")[:256], str(display_name or "")[:256],
                    str(language or "")[:16], str(language or "")[:16],
                    str(platform or "")[:64], str(platform or "")[:64],
                    str(app_version or "")[:64], str(app_version or "")[:64],
                    subject,
                ),
            )
            if created:
                self._append_event(cursor, subject, "first_seen")
        return self.profile(subject) or {}

    def open_session(self, user_id: int | str, session_id: str) -> dict[str, Any]:
        subject = self._subject(user_id)
        normalized = str(session_id or "").strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("Mini App session ID is required")
        now = utc_now()
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            self._insert_pending(cursor, subject, now)
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_sessions (subject, session_id, opened_at) "
                    "VALUES (?, ?, ?) ON CONFLICT (subject, session_id) DO NOTHING"
                ),
                (subject, normalized, now),
            )
            inserted = cursor.rowcount > 0
            if inserted:
                cursor.execute(
                    self._sql(
                        "UPDATE wukong_telegram_users SET mini_app_open_count = mini_app_open_count + 1, "
                        "last_seen_at = ? WHERE subject = ?"
                    ),
                    (now, subject),
                )
                self._append_event(cursor, subject, "mini_app_open", details={"sessionId": normalized})
        return self.profile(subject) or {}

    def profile(self, user_id: int | str) -> dict[str, Any] | None:
        try:
            subject = self._subject(user_id)
        except ValueError:
            return None
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    f"SELECT {self._profile_columns()} FROM wukong_telegram_users WHERE subject = ?"
                ),
                (subject,),
            )
            return self._profile_payload(cursor.fetchone())

    def approve(
        self,
        user_id: int | str,
        *,
        actor: Identity,
        reason: str = "",
    ) -> None:
        self._require_admin(actor)
        subject = self._subject(user_id)
        if subject in self._configured_admins:
            return
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            now = utc_now()
            self._insert_pending(cursor, subject, now)
            cursor.execute(
                self._sql("SELECT access_status FROM wukong_telegram_users WHERE subject = ?"),
                (subject,),
            )
            row = cursor.fetchone()
            if row is not None and str(row[0]) == "approved":
                return
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user') "
                    "ON CONFLICT (subject) DO UPDATE SET role = 'user'"
                ),
                (subject,),
            )
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET access_status = 'approved', role = 'user', "
                    "build_credits = 1, unlimited = 0, lifetime_granted = lifetime_granted + 1, "
                    "approved_at = ?, revoked_at = '', access_actor = ?, access_reason = ? "
                    "WHERE subject = ?"
                ),
                (now, actor.subject, str(reason or "")[:1024], subject),
            )
            self._append_event(cursor, subject, "approved", actor=actor.subject, reason=reason, details={"credits": 1})

    def revoke(
        self,
        user_id: int | str,
        *,
        actor: Identity,
        reason: str = "",
    ) -> None:
        self._require_admin(actor)
        reason = require_sensitive_admin_reason(reason, action="revoke")
        subject = self._subject(user_id)
        if subject in self._configured_admins:
            raise PermissionError("Configured Telegram admins cannot be revoked from the allowlist")
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            now = utc_now()
            self._insert_pending(cursor, subject, now)
            cursor.execute(
                self._sql("DELETE FROM wukong_telegram_access WHERE subject = ?"),
                (subject,),
            )
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET access_status = 'revoked', build_credits = 0, "
                    "unlimited = 0, revoked_at = ?, access_actor = ?, access_reason = ? WHERE subject = ?"
                ),
                (now, actor.subject, reason[:1024], subject),
            )
            self._append_event(cursor, subject, "revoked", actor=actor.subject, reason=reason)

    def list_access(self, *, actor: Identity) -> dict[str, list[str]]:
        self._require_admin(actor)
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT subject, role FROM wukong_telegram_users "
                "WHERE access_status = 'approved' ORDER BY subject"
            )
            rows = cursor.fetchall()
        admins = set(self._configured_admins)
        admins.update(str(row[0]) for row in rows if str(row[1]) == "admin")
        users = sorted(str(row[0]) for row in rows if str(row[1]) == "user")
        return {"admins": sorted(admins), "users": users}

    def subjects(self) -> tuple[str, ...]:
        """Return every approved Telegram subject for service-side maintenance."""

        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT subject FROM wukong_telegram_access ORDER BY subject")
            rows = cursor.fetchall()
        return tuple(sorted(
            self._configured_admins | {str(row[0]) for row in rows}
        ))

    def import_identity(self, subject: str, role: str) -> bool:
        """Import one legacy allowlist row, returning False when unchanged."""

        normalized_subject = str(subject).strip()
        normalized_role = str(role).strip().casefold()
        if not normalized_subject or normalized_role not in {"admin", "user"}:
            raise ValueError("Legacy Telegram access identity is invalid")
        if normalized_subject in self._configured_admins:
            return False
        existing = self.identity(normalized_subject)
        if existing and existing.role == normalized_role:
            return False
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            now = utc_now()
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_access (subject, role) VALUES (?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET role = excluded.role"
                ),
                (normalized_subject, normalized_role),
            )
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_users "
                    "(subject, access_status, role, first_seen_at, last_seen_at, build_credits, unlimited, lifetime_granted) "
                    "VALUES (?, 'approved', ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET access_status = 'approved', role = excluded.role, "
                    "build_credits = CASE WHEN wukong_telegram_users.access_status = 'approved' "
                    "THEN wukong_telegram_users.build_credits ELSE excluded.build_credits END, "
                    "unlimited = excluded.unlimited"
                ),
                (
                    normalized_subject,
                    normalized_role,
                    now,
                    now,
                    0 if normalized_role == "admin" else 1,
                    1 if normalized_role == "admin" else 0,
                    0 if normalized_role == "admin" else 1,
                ),
            )
        return True

    def is_configured_admin(self, subject: int | str) -> bool:
        """Return whether an identity is supplied by immutable configuration."""

        return str(subject).strip() in self._configured_admins

    def update_allowance(
        self,
        user_id: int | str,
        *,
        actor: Identity,
        operation: str,
        value: int | None = None,
        unlimited: bool | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        self._require_admin(actor)
        subject = self._subject(user_id)
        if subject in self._configured_admins:
            raise PermissionError("Configured Telegram admins are always unlimited")
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            lock = "" if self._dialect == "sqlite" else " FOR UPDATE"
            cursor.execute(
                self._sql(
                    "SELECT access_status, build_credits, unlimited, lifetime_granted "
                    f"FROM wukong_telegram_users WHERE subject = ?{lock}"
                ),
                (subject,),
            )
            row = cursor.fetchone()
            if row is None or str(row[0]) != "approved":
                raise PermissionError("Telegram account is not approved")
            before = int(row[1])
            unlimited_before = bool(row[2])
            current_unlimited = unlimited_before
            if operation == "add":
                after = before + int(value or 0)
            elif operation == "set":
                after = int(value if value is not None else -1)
            elif operation == "unlimited":
                if unlimited is None:
                    raise ValueError("Unlimited value is required")
                after = before
                current_unlimited = bool(unlimited)
            else:
                raise ValueError("Unsupported allowance operation")
            if after < 0:
                raise ValueError("Build credits cannot be negative")
            delta = after - before
            reason = require_sensitive_admin_reason(
                reason,
                credits_before=before,
                credits_after=after,
                unlimited_before=unlimited_before,
                unlimited_after=current_unlimited,
                action="reduce access",
            )
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET build_credits = ?, unlimited = ?, "
                    "lifetime_granted = lifetime_granted + ? WHERE subject = ?"
                ),
                (after, int(current_unlimited), max(0, delta), subject),
            )
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_quota_ledger "
                    "(ledger_id, subject, entry_type, delta, balance_after, actor_subject, reason, created_at) "
                    "VALUES (?, ?, 'admin_adjustment', ?, ?, ?, ?, ?)"
                ),
                (uuid.uuid4().hex, subject, delta, after, actor.subject, str(reason or "")[:1024], utc_now()),
            )
            self._append_event(
                cursor,
                subject,
                "allowance_changed",
                actor=actor.subject,
                reason=reason,
                details={"operation": operation, "delta": delta, "balance": after, "unlimited": current_unlimited},
            )
        return self.profile(subject) or {}

    def reserve_build(
        self,
        user_id: int | str,
        *,
        job_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        subject = self._subject(user_id)
        raw_request_key = str(idempotency_key or "").strip()
        if not raw_request_key or len(raw_request_key) > 128:
            raise ValueError("Build idempotency key is invalid")
        request_key = f"{subject}:{raw_request_key}"
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT job_id, consumed FROM wukong_telegram_quota_ledger "
                    "WHERE subject = ? AND idempotency_key IN (?, ?) "
                    "ORDER BY CASE WHEN idempotency_key = ? THEN 0 ELSE 1 END"
                ),
                (subject, request_key, raw_request_key, request_key),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return {"jobId": str(existing[0]), "existing": True, "consumed": bool(existing[1])}
            lock = "" if self._dialect == "sqlite" else " FOR UPDATE"
            cursor.execute(
                self._sql(
                    "SELECT access_status, build_credits, unlimited "
                    f"FROM wukong_telegram_users WHERE subject = ?{lock}"
                ),
                (subject,),
            )
            row = cursor.fetchone()
            if row is None or str(row[0]) != "approved":
                raise PermissionError("Telegram account is not approved")
            credits = int(row[1])
            consumed = not bool(row[2])
            if consumed and credits <= 0:
                raise BuildQuotaError("No build credits remain")
            balance = credits - 1 if consumed else credits
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET build_credits = ?, "
                    "lifetime_used = lifetime_used + ?, job_count = job_count + 1, "
                    "last_job_id = ?, last_job_status = 'queued' WHERE subject = ?"
                ),
                (balance, 1 if consumed else 0, job_id, subject),
            )
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_quota_ledger "
                    "(ledger_id, subject, entry_type, delta, balance_after, job_id, idempotency_key, consumed, created_at) "
                    "VALUES (?, ?, 'consume', ?, ?, ?, ?, ?, ?)"
                ),
                (
                    uuid.uuid4().hex, subject, -1 if consumed else 0, balance,
                    job_id, request_key, int(consumed), utc_now(),
                ),
            )
            self._append_event(
                cursor,
                subject,
                "build_reserved",
                details={"jobId": job_id, "consumed": consumed, "balance": balance},
            )
        return {"jobId": job_id, "existing": False, "consumed": consumed}

    def reserve_and_create_job(
        self,
        store: "PostgresJobStore",
        manifest: JobManifest,
        recipe: BuildRecipe,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Atomically consume one credit and persist the submitted PostgreSQL job."""

        if not isinstance(store, PostgresJobStore) or store._dialect != self._dialect:
            raise TypeError("Atomic job creation requires the PostgreSQL job store")
        subject = self._subject(manifest.owner.subject)
        raw_request_key = str(idempotency_key or "").strip()
        if not raw_request_key or len(raw_request_key) > 128:
            raise ValueError("Build idempotency key is invalid")
        request_key = f"{subject}:{raw_request_key}"
        with self._lock, store._lock, self._connection() as connection:
            cursor = connection.cursor()

            def existing_submission() -> dict[str, Any] | None:
                cursor.execute(
                    self._sql(
                        "SELECT job_id, consumed FROM wukong_telegram_quota_ledger "
                        "WHERE subject = ? AND idempotency_key IN (?, ?) "
                        "ORDER BY CASE WHEN idempotency_key = ? THEN 0 ELSE 1 END"
                    ),
                    (subject, request_key, raw_request_key, request_key),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                existing_job_id = str(row[0])
                cursor.execute(
                    self._sql("SELECT manifest_json FROM wukong_jobs WHERE job_id = ?"),
                    (existing_job_id,),
                )
                existing_manifest = PostgresJobStore._manifest_from_row(cursor.fetchone())
                if existing_manifest is None:
                    raise OrchestrationError("Reserved job is not available")
                return {
                    "jobId": existing_job_id,
                    "existing": True,
                    "consumed": bool(row[1]),
                    "manifest": existing_manifest,
                }

            existing = existing_submission()
            if existing is not None:
                return existing
            lock = "" if self._dialect == "sqlite" else " FOR UPDATE"
            cursor.execute(
                self._sql(
                    "SELECT access_status, build_credits, unlimited "
                    f"FROM wukong_telegram_users WHERE subject = ?{lock}"
                ),
                (subject,),
            )
            profile = cursor.fetchone()
            if profile is None or str(profile[0]) != "approved":
                raise PermissionError("Telegram account is not approved")
            # A concurrent retry may have committed while this request waited
            # for the per-user row lock. Recheck before consuming another credit.
            existing = existing_submission()
            if existing is not None:
                return existing
            credits = int(profile[1])
            consumed = not bool(profile[2])
            if consumed and credits <= 0:
                raise BuildQuotaError("No build credits remain")
            balance = credits - 1 if consumed else credits
            cursor.execute(
                self._sql("SELECT 1 FROM wukong_jobs WHERE job_id = ?"),
                (manifest.job_id,),
            )
            if cursor.fetchone() is not None:
                raise OrchestrationError(f"Job already exists: {manifest.job_id}")
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_jobs "
                    "(job_id, manifest_json, recipe_json, created_at, next_event_sequence) "
                    "VALUES (?, ?, ?, ?, 2)"
                ),
                (
                    manifest.job_id,
                    PostgresJobStore._manifest_json(manifest),
                    recipe.canonical_json,
                    manifest.created_at,
                ),
            )
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_job_events "
                    "(job_id, sequence, timestamp, event_type, payload_json) "
                    "VALUES (?, 1, ?, 'submitted', ?)"
                ),
                (
                    manifest.job_id,
                    utc_now(),
                    json.dumps(
                        {"runner": manifest.runner, "channel": manifest.owner.channel},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET build_credits = ?, "
                    "lifetime_used = lifetime_used + ?, job_count = job_count + 1, "
                    "last_job_id = ?, last_job_status = 'queued' WHERE subject = ?"
                ),
                (balance, 1 if consumed else 0, manifest.job_id, subject),
            )
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_quota_ledger "
                    "(ledger_id, subject, entry_type, delta, balance_after, job_id, "
                    "idempotency_key, consumed, created_at) "
                    "VALUES (?, ?, 'consume', ?, ?, ?, ?, ?, ?)"
                ),
                (
                    uuid.uuid4().hex,
                    subject,
                    -1 if consumed else 0,
                    balance,
                    manifest.job_id,
                    request_key,
                    int(consumed),
                    utc_now(),
                ),
            )
            self._append_event(
                cursor,
                subject,
                "build_reserved",
                details={"jobId": manifest.job_id, "consumed": consumed, "balance": balance},
            )
        return {
            "jobId": manifest.job_id,
            "existing": False,
            "consumed": consumed,
            "manifest": JobManifest.from_dict(manifest.to_dict()),
        }

    def compensate_build(
        self,
        user_id: int | str,
        job_id: str,
        *,
        reason: str,
        retain_job: bool = False,
    ) -> bool:
        subject = self._subject(user_id)
        compensation_key = f"compensate:{job_id}"
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT 1 FROM wukong_telegram_quota_ledger WHERE idempotency_key = ?"),
                (compensation_key,),
            )
            if cursor.fetchone() is not None:
                return False
            cursor.execute(
                self._sql(
                    "SELECT consumed FROM wukong_telegram_quota_ledger "
                    "WHERE subject = ? AND job_id = ? AND entry_type = 'consume'"
                ),
                (subject, job_id),
            )
            consumed_row = cursor.fetchone()
            if consumed_row is None:
                return False
            consumed = bool(consumed_row[0])
            lock = "" if self._dialect == "sqlite" else " FOR UPDATE"
            cursor.execute(
                self._sql(f"SELECT build_credits FROM wukong_telegram_users WHERE subject = ?{lock}"),
                (subject,),
            )
            profile_row = cursor.fetchone()
            if profile_row is None:
                return False
            balance = int(profile_row[0]) + (1 if consumed else 0)
            cursor.execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET build_credits = ?, "
                    "lifetime_used = CASE WHEN lifetime_used > 0 AND ? = 1 THEN lifetime_used - 1 ELSE lifetime_used END, "
                    "job_count = CASE WHEN ? = 0 AND job_count > 0 THEN job_count - 1 ELSE job_count END, "
                    "last_job_status = CASE WHEN last_job_id = ? THEN 'dispatch_failed' ELSE last_job_status END "
                    "WHERE subject = ?"
                ),
                (balance, int(consumed), int(retain_job), job_id, subject),
            )
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_telegram_quota_ledger "
                    "(ledger_id, subject, entry_type, delta, balance_after, job_id, idempotency_key, consumed, reason, created_at) "
                    "VALUES (?, ?, 'compensate', ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    uuid.uuid4().hex, subject, 1 if consumed else 0, balance,
                    job_id, compensation_key, int(consumed), str(reason or "")[:1024], utc_now(),
                ),
            )
            self._append_event(
                cursor,
                subject,
                "build_compensated",
                reason=reason,
                details={"jobId": job_id, "retainJob": bool(retain_job)},
            )
        return True

    def update_job_status(self, user_id: int | str, job_id: str, status: str) -> None:
        subject = self._subject(user_id)
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql(
                    "UPDATE wukong_telegram_users SET last_job_id = ?, last_job_status = ? WHERE subject = ?"
                ),
                (str(job_id), str(status or "")[:64], subject),
            )

    def list_users(
        self,
        *,
        actor: Identity,
        query: str = "",
        status: str = "",
        quota: str = "",
        activity: str = "",
        limit: int = 50,
        offset: int = 0,
        sort: str = "lastSeenAt",
        direction: str = "desc",
    ) -> dict[str, Any]:
        self._require_admin(actor)
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT {self._profile_columns()} FROM wukong_telegram_users")
            users = [self._profile_payload(row) for row in cursor.fetchall()]
        filtered = [user for user in users if user is not None]
        term = str(query or "").strip().casefold()
        if term:
            filtered = [
                user for user in filtered
                if term in " ".join(str(user.get(key) or "").casefold() for key in ("telegramId", "username", "displayName"))
            ]
        if status in {"pending", "approved", "revoked"}:
            filtered = [user for user in filtered if user["accessStatus"] == status]
        if quota == "available":
            filtered = [user for user in filtered if user["unlimited"] or int(user["buildCredits"] or 0) > 0]
        elif quota == "exhausted":
            filtered = [user for user in filtered if not user["unlimited"] and int(user["buildCredits"] or 0) == 0]
        elif quota == "unlimited":
            filtered = [user for user in filtered if user["unlimited"]]
        if activity == "active":
            filtered = [user for user in filtered if int(user["miniAppOpenCount"] or 0) > 0]
        elif activity == "never":
            filtered = [user for user in filtered if int(user["miniAppOpenCount"] or 0) == 0]
        elif activity == "jobs":
            filtered = [user for user in filtered if int(user["jobCount"] or 0) > 0]
        allowed_sort = {"lastSeenAt", "firstSeenAt", "miniAppOpenCount", "jobCount", "buildCredits", "telegramId"}
        sort_key = sort if sort in allowed_sort else "lastSeenAt"
        filtered.sort(key=lambda user: (user.get(sort_key) is not None, user.get(sort_key)), reverse=direction != "asc")
        total = len(filtered)
        start = max(0, offset)
        return {"users": filtered[start : start + max(1, min(limit, 100))], "total": total}

    def create_user(
        self,
        user_id: int | str,
        *,
        actor: Identity,
        username: str = "",
        display_name: str = "",
    ) -> dict[str, Any]:
        self._require_admin(actor)
        profile = self.observe_user(user_id, username=username, display_name=display_name)
        with self._lock, self._connection() as connection:
            self._append_event(connection.cursor(), profile["telegramId"], "created_by_admin", actor=actor.subject)
        return profile

    def user_events(self, user_id: int | str, *, actor: Identity) -> list[dict[str, Any]]:
        self._require_admin(actor)
        subject = self._subject(user_id)
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT event_id, event_type, actor_subject, reason, details_json, created_at "
                    "FROM wukong_telegram_user_events WHERE subject = ? ORDER BY created_at DESC, event_id DESC"
                ),
                (subject,),
            )
            return [
                {
                    "eventId": str(row[0]),
                    "telegramId": subject,
                    "type": str(row[1]),
                    "actorTelegramId": str(row[2]),
                    "reason": str(row[3]),
                    "details": dict(json.loads(str(row[4]))),
                    "createdAt": str(row[5]),
                }
                for row in cursor.fetchall()
            ]

    def backfill_jobs(self, manifests: list[JobManifest]) -> int:
        grouped: dict[str, list[JobManifest]] = {}
        for manifest in manifests:
            if manifest.owner.channel == "telegram":
                grouped.setdefault(manifest.owner.subject, []).append(manifest)
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            for subject, jobs in grouped.items():
                latest = max(jobs, key=lambda item: item.created_at)
                now = latest.created_at or utc_now()
                cursor.execute(
                    self._sql(
                        "INSERT INTO wukong_telegram_users "
                        "(subject, access_status, role, first_seen_at, last_seen_at, build_credits, unlimited, lifetime_granted) "
                        "VALUES (?, 'approved', ?, ?, ?, ?, ?, ?) ON CONFLICT (subject) DO NOTHING"
                    ),
                    (
                        subject,
                        latest.owner.role,
                        now,
                        now,
                        0 if latest.owner.role == "admin" else 1,
                        1 if latest.owner.role == "admin" else 0,
                        0 if latest.owner.role == "admin" else 1,
                    ),
                )
                cursor.execute(
                    self._sql(
                        "UPDATE wukong_telegram_users SET "
                        "job_count = CASE WHEN job_count < ? THEN ? ELSE job_count END, "
                        "last_job_id = ?, last_job_status = ? WHERE subject = ?"
                    ),
                    (len(jobs), len(jobs), latest.job_id, latest.status.value, subject),
                )
        return sum(len(jobs) for jobs in grouped.values())


class PostgresJobStore(_DatabaseStore):
    """Durable JobStore backed by PostgreSQL.

    A connection factory and the small SQLite dialect are exposed only so the
    public JobStore contract can be exercised without requiring a developer's
    workstation to run a database server. Production always uses PostgreSQL.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: ConnectionFactory | None = None,
        dialect: str = "postgresql",
    ) -> None:
        super().__init__(database_url, connect=connect, dialect=dialect)
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_jobs (
                    job_id TEXT PRIMARY KEY,
                    manifest_json TEXT NOT NULL,
                    recipe_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    next_event_sequence INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_job_events (
                    job_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (job_id, sequence),
                    FOREIGN KEY (job_id) REFERENCES wukong_jobs(job_id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS wukong_jobs_created_idx "
                "ON wukong_jobs(created_at DESC)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_control_plane_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def metadata(self, key: str) -> str | None:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT value FROM wukong_control_plane_metadata WHERE key = ?"),
                (key,),
            )
            row = cursor.fetchone()
        return str(row[0]) if row is not None else None

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql(
                    "INSERT INTO wukong_control_plane_metadata (key, value) VALUES (?, ?) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value"
                ),
                (key, value),
            )

    @staticmethod
    def _manifest_json(manifest: JobManifest) -> str:
        return json.dumps(manifest.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _manifest_from_row(row: Any) -> JobManifest | None:
        if row is None:
            return None
        return JobManifest.from_dict(json.loads(str(row[0])))

    def create(self, manifest: JobManifest, recipe: BuildRecipe) -> JobManifest:
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT 1 FROM wukong_jobs WHERE job_id = ?"),
                (manifest.job_id,),
            )
            if cursor.fetchone() is not None:
                raise OrchestrationError(f"Job already exists: {manifest.job_id}")
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_jobs "
                    "(job_id, manifest_json, recipe_json, created_at, next_event_sequence) "
                    "VALUES (?, ?, ?, ?, 1)"
                ),
                (
                    manifest.job_id,
                    self._manifest_json(manifest),
                    recipe.canonical_json,
                    manifest.created_at,
                ),
            )
        return JobManifest.from_dict(manifest.to_dict())

    def import_snapshot(
        self,
        manifest: JobManifest,
        recipe: BuildRecipe,
        events: list[JobEvent],
    ) -> bool:
        """Import one complete legacy job atomically, returning False if it exists."""

        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT 1 FROM wukong_jobs WHERE job_id = ?"),
                (manifest.job_id,),
            )
            if cursor.fetchone() is not None:
                return False
            next_sequence = max((event.sequence for event in events), default=0) + 1
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_jobs "
                    "(job_id, manifest_json, recipe_json, created_at, next_event_sequence) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                (
                    manifest.job_id,
                    self._manifest_json(manifest),
                    recipe.canonical_json,
                    manifest.created_at,
                    next_sequence,
                ),
            )
            for event in sorted(events, key=lambda entry: entry.sequence):
                cursor.execute(
                    self._sql(
                        "INSERT INTO wukong_job_events "
                        "(job_id, sequence, timestamp, event_type, payload_json) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (
                        event.job_id,
                        event.sequence,
                        event.timestamp,
                        event.type,
                        json.dumps(
                            event.payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                )
        return True

    def get(self, job_id: str) -> JobManifest | None:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT manifest_json FROM wukong_jobs WHERE job_id = ?"),
                (job_id,),
            )
            return self._manifest_from_row(cursor.fetchone())

    def recipe(self, job_id: str) -> BuildRecipe | None:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT recipe_json FROM wukong_jobs WHERE job_id = ?"),
                (job_id,),
            )
            row = cursor.fetchone()
            return BuildRecipe.from_dict(json.loads(str(row[0]))) if row is not None else None

    def update(self, job_id: str, **changes: object) -> JobManifest:
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT manifest_json FROM wukong_jobs WHERE job_id = ?"),
                (job_id,),
            )
            manifest = self._manifest_from_row(cursor.fetchone())
            if manifest is None:
                raise OrchestrationError("Job not found")
            for key, value in changes.items():
                if not hasattr(manifest, key):
                    raise OrchestrationError(f"Unknown job field: {key}")
                setattr(manifest, key, value)
            manifest.updated_at = utc_now()
            if manifest.status in TERMINAL_STATUSES and not manifest.finished_at:
                manifest.finished_at = manifest.updated_at
            cursor.execute(
                self._sql("UPDATE wukong_jobs SET manifest_json = ? WHERE job_id = ?"),
                (self._manifest_json(manifest), job_id),
            )
        return JobManifest.from_dict(manifest.to_dict())

    def replace_recipe(self, job_id: str, recipe: BuildRecipe) -> BuildRecipe:
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("UPDATE wukong_jobs SET recipe_json = ? WHERE job_id = ?"),
                (recipe.canonical_json, job_id),
            )
            if cursor.rowcount == 0:
                raise OrchestrationError("Job not found")
        return recipe

    def append_event(self, job_id: str, event_type: str, **payload: object) -> JobEvent:
        with self._lock, self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "UPDATE wukong_jobs "
                    "SET next_event_sequence = next_event_sequence + 1 "
                    "WHERE job_id = ? RETURNING next_event_sequence - 1"
                ),
                (job_id,),
            )
            sequence_row = cursor.fetchone()
            if sequence_row is None:
                raise OrchestrationError("Job not found")
            event = JobEvent(int(sequence_row[0]), job_id, utc_now(), event_type, dict(payload))
            cursor.execute(
                self._sql(
                    "INSERT INTO wukong_job_events "
                    "(job_id, sequence, timestamp, event_type, payload_json) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                (
                    event.job_id,
                    event.sequence,
                    event.timestamp,
                    event.type,
                    json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        return event

    def events(self, job_id: str, after: int = 0) -> list[JobEvent]:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql("SELECT 1 FROM wukong_jobs WHERE job_id = ?"),
                (job_id,),
            )
            if cursor.fetchone() is None:
                raise OrchestrationError("Job not found")
            cursor.execute(
                self._sql(
                    "SELECT sequence, timestamp, event_type, payload_json "
                    "FROM wukong_job_events WHERE job_id = ? AND sequence > ? "
                    "ORDER BY sequence"
                ),
                (job_id, after),
            )
            return [
                JobEvent(
                    sequence=int(row[0]),
                    job_id=job_id,
                    timestamp=str(row[1]),
                    type=str(row[2]),
                    payload=dict(json.loads(str(row[3]))),
                )
                for row in cursor.fetchall()
            ]

    def list(self) -> list[JobManifest]:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT manifest_json FROM wukong_jobs ORDER BY created_at DESC")
            return [
                manifest
                for row in cursor.fetchall()
                if (manifest := self._manifest_from_row(row)) is not None
            ]


def migrate_file_job_store(source: JobStore, target: PostgresJobStore) -> dict[str, int]:
    """Copy legacy JSON job state once without modifying the rollback source."""

    imported = 0
    skipped = 0
    for manifest in reversed(source.list()):
        recipe = source.recipe(manifest.job_id)
        if recipe is None:
            raise OrchestrationError(f"Legacy job recipe is missing: {manifest.job_id}")
        if target.import_snapshot(manifest, recipe, source.events(manifest.job_id)):
            imported += 1
        else:
            skipped += 1
    return {"imported": imported, "skipped": skipped}


def migrate_telegram_access_store(
    source: Any,
    target: PostgresTelegramAccessStore,
    *,
    actor: Identity,
) -> dict[str, int]:
    """Copy the legacy Telegram allowlist without duplicating configured admins."""

    snapshot = source.list_access(actor=actor)
    imported = 0
    unchanged = 0
    entries = [("admin", subject) for subject in snapshot.get("admins", [])]
    entries.extend(("user", subject) for subject in snapshot.get("users", []))
    for role, subject in entries:
        if target.is_configured_admin(subject):
            continue
        if target.import_identity(str(subject), role):
            imported += 1
        else:
            unchanged += 1
    return {"imported": imported, "unchanged": unchanged}


def migrate_telegram_ui_state_file(
    source_path: Path,
    target: PostgresTelegramUIStateStore,
) -> dict[str, int]:
    """Copy legacy UI preferences while retaining signed-URL sanitization."""

    if not source_path.is_file():
        return {"imported": 0, "unchanged": 0}
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"imported": 0, "unchanged": 0}
    languages = payload.get("languages", {}) if isinstance(payload, Mapping) else {}
    sessions = payload.get("sessions", {}) if isinstance(payload, Mapping) else {}
    job_refs = payload.get("jobRefs", {}) if isinstance(payload, Mapping) else {}
    languages = languages if isinstance(languages, Mapping) else {}
    sessions = sessions if isinstance(sessions, Mapping) else {}
    job_refs = job_refs if isinstance(job_refs, Mapping) else {}
    subjects = sorted({str(value) for value in (*languages.keys(), *sessions.keys(), *job_refs.keys())})
    imported = 0
    unchanged = 0
    for subject in subjects:
        changed = target.import_state(
            subject,
            language=str(languages.get(subject) or "vi"),
            session=(sessions.get(subject) if isinstance(sessions.get(subject), Mapping) else {}),
            job_refs=(job_refs.get(subject) if isinstance(job_refs.get(subject), Mapping) else {}),
        )
        if changed:
            imported += 1
        else:
            unchanged += 1
    return {"imported": imported, "unchanged": unchanged}

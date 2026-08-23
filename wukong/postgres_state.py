from __future__ import annotations

import json
import hashlib
import threading
from collections.abc import Callable
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from .models import BuildRecipe, Identity, JobManifest, JobStatus, utc_now
from .orchestrator import JobEvent, JobStore, OrchestrationError, TERMINAL_STATUSES


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
    """Telegram allowlist stored in PostgreSQL with configured admins immutable."""

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
            connection.cursor().execute(
                """
                CREATE TABLE IF NOT EXISTS wukong_telegram_access (
                    subject TEXT PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user'))
                )
                """
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
                self._sql("SELECT role FROM wukong_telegram_access WHERE subject = ?"),
                (subject,),
            )
            row = cursor.fetchone()
        return Identity("telegram", subject, str(row[0])) if row is not None else None

    def approve(self, user_id: int | str, *, actor: Identity) -> None:
        self._require_admin(actor)
        subject = str(user_id).strip()
        if not subject:
            raise ValueError("Telegram user ID is required")
        if subject in self._configured_admins:
            return
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql(
                    "INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user') "
                    "ON CONFLICT (subject) DO UPDATE SET role = 'user'"
                ),
                (subject,),
            )

    def revoke(self, user_id: int | str, *, actor: Identity) -> None:
        self._require_admin(actor)
        subject = str(user_id).strip()
        if subject in self._configured_admins:
            raise PermissionError("Configured Telegram admins cannot be revoked from the allowlist")
        with self._lock, self._connection() as connection:
            connection.cursor().execute(
                self._sql("DELETE FROM wukong_telegram_access WHERE subject = ?"),
                (subject,),
            )

    def list_access(self, *, actor: Identity) -> dict[str, list[str]]:
        self._require_admin(actor)
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT subject, role FROM wukong_telegram_access ORDER BY subject"
            )
            rows = cursor.fetchall()
        admins = set(self._configured_admins)
        admins.update(str(row[0]) for row in rows if str(row[1]) == "admin")
        users = sorted(str(row[0]) for row in rows if str(row[1]) == "user")
        return {"admins": sorted(admins), "users": users}

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
            connection.cursor().execute(
                self._sql(
                    "INSERT INTO wukong_telegram_access (subject, role) VALUES (?, ?) "
                    "ON CONFLICT (subject) DO UPDATE SET role = excluded.role"
                ),
                (normalized_subject, normalized_role),
            )
        return True

    def is_configured_admin(self, subject: int | str) -> bool:
        """Return whether an identity is supplied by immutable configuration."""

        return str(subject).strip() in self._configured_admins


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

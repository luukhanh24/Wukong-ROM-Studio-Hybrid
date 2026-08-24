from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .models import Identity, utc_now


class BuildQuotaError(PermissionError):
    """Raised when an approved Telegram user has no build credit left."""


def require_sensitive_admin_reason(
    reason: str,
    *,
    credits_before: int | None = None,
    credits_after: int | None = None,
    unlimited_before: bool | None = None,
    unlimited_after: bool | None = None,
    action: str = "this change",
) -> str:
    """Enforce the audit reason invariant for destructive access changes."""

    normalized = str(reason or "").strip()
    reduces_credits = (
        credits_before is not None
        and credits_after is not None
        and int(credits_after) < int(credits_before)
    )
    disables_unlimited = unlimited_before is True and unlimited_after is False
    if (reduces_credits or disables_unlimited or action == "revoke") and not normalized:
        raise ValueError(f"A reason is required to {action}")
    return normalized


class TelegramAccessStore:
    """Local fallback for Telegram profiles, access, audit and build credits."""

    def __init__(
        self,
        path: Path,
        *,
        admin_ids: Iterable[int | str] = (),
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.path = path.resolve()
        self._configured_admins = {str(value).strip() for value in admin_ids if str(value).strip()}
        self.on_change = on_change
        self._lock = threading.RLock()
        with self._lock:
            state = self._read()
            changed = False
            for subject in self._configured_admins:
                profile = self._ensure_profile(state, subject)
                before = dict(profile)
                profile.update(
                    {
                        "accessStatus": "approved",
                        "role": "admin",
                        "unlimited": True,
                        "buildCredits": 0,
                        "configuredAdmin": True,
                    }
                )
                changed = changed or profile != before
            if changed:
                self._write(state)

    @staticmethod
    def _subject(user_id: int | str) -> str:
        value = str(user_id).strip()
        if not value or not value.isascii() or not value.isdigit() or int(value) <= 0:
            raise ValueError("Telegram user ID is required")
        return value

    @staticmethod
    def _new_profile(subject: str) -> dict[str, Any]:
        now = utc_now()
        return {
            "telegramId": subject,
            "username": "",
            "displayName": "",
            "accessStatus": "pending",
            "role": "user",
            "firstSeenAt": now,
            "lastSeenAt": now,
            "miniAppOpenCount": 0,
            "jobCount": 0,
            "buildCredits": 0,
            "unlimited": False,
            "lifetimeGranted": 0,
            "lifetimeUsed": 0,
            "lastJobId": "",
            "lastJobStatus": "",
            "approvedAt": "",
            "revokedAt": "",
            "accessActor": "",
            "accessReason": "",
            "language": "",
            "platform": "",
            "appVersion": "",
            "configuredAdmin": False,
        }

    def _ensure_profile(self, state: dict[str, Any], subject: str) -> dict[str, Any]:
        profiles = state.setdefault("profiles", {})
        profile = profiles.get(subject)
        if not isinstance(profile, dict):
            profile = self._new_profile(subject)
            if subject in state.get("admins", []):
                profile.update({"accessStatus": "approved", "role": "admin", "unlimited": True})
            elif subject in state.get("users", []):
                profile.update(
                    {
                        "accessStatus": "approved",
                        "role": "user",
                        "buildCredits": 1,
                        "lifetimeGranted": 1,
                    }
                )
            profiles[subject] = profile
        defaults = self._new_profile(subject)
        for key, value in defaults.items():
            profile.setdefault(key, value)
        return profile

    @staticmethod
    def _event(
        state: dict[str, Any],
        subject: str,
        event_type: str,
        *,
        actor: str = "",
        reason: str = "",
        **details: object,
    ) -> None:
        state.setdefault("events", []).append(
            {
                "telegramId": subject,
                "type": event_type,
                "actorTelegramId": actor,
                "reason": reason,
                "details": details,
                "createdAt": utc_now(),
            }
        )

    def identity(self, user_id: int | str) -> Identity | None:
        try:
            subject = self._subject(user_id)
        except ValueError:
            return None
        with self._lock:
            state = self._read()
            if subject in self._configured_admins:
                return Identity("telegram", subject, "admin")
            profile = state.get("profiles", {}).get(subject)
            if isinstance(profile, Mapping) and profile.get("accessStatus") == "approved":
                return Identity("telegram", subject, str(profile.get("role") or "user"))
            if subject in state.get("admins", []):
                return Identity("telegram", subject, "admin")
            if subject in state.get("users", []):
                return Identity("telegram", subject, "user")
            return None

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
        with self._lock:
            state = self._read()
            created = subject not in state.get("profiles", {})
            profile = self._ensure_profile(state, subject)
            profile["lastSeenAt"] = utc_now()
            for key, value in (
                ("username", username),
                ("displayName", display_name),
                ("language", language),
                ("platform", platform),
                ("appVersion", app_version),
            ):
                cleaned = str(value or "").strip()[:256]
                if cleaned:
                    profile[key] = cleaned
            if subject in self._configured_admins:
                profile.update(
                    {
                        "accessStatus": "approved",
                        "role": "admin",
                        "unlimited": True,
                        "buildCredits": 0,
                        "configuredAdmin": True,
                    }
                )
            if created:
                self._event(state, subject, "first_seen")
            self._write(state)
            return dict(profile)

    def open_session(self, user_id: int | str, session_id: str) -> dict[str, Any]:
        subject = self._subject(user_id)
        normalized = str(session_id or "").strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("Mini App session ID is required")
        key = f"{subject}:{normalized}"
        with self._lock:
            state = self._read()
            profile = self._ensure_profile(state, subject)
            sessions = state.setdefault("sessions", {})
            if key not in sessions:
                sessions[key] = utc_now()
                profile["miniAppOpenCount"] = int(profile.get("miniAppOpenCount") or 0) + 1
                self._event(state, subject, "mini_app_open", sessionId=normalized)
            profile["lastSeenAt"] = utc_now()
            self._write(state)
            return dict(profile)

    def profile(self, user_id: int | str) -> dict[str, Any] | None:
        try:
            subject = self._subject(user_id)
        except ValueError:
            return None
        with self._lock:
            state = self._read()
            if subject not in state.get("profiles", {}) and subject not in self._configured_admins:
                return None
            profile = self._ensure_profile(state, subject)
            if subject in self._configured_admins:
                profile.update(
                    {
                        "accessStatus": "approved",
                        "role": "admin",
                        "unlimited": True,
                        "buildCredits": 0,
                        "configuredAdmin": True,
                    }
                )
            return dict(profile)

    def approve(
        self,
        user_id: int | str,
        *,
        actor: Identity,
        reason: str = "",
    ) -> None:
        self._require_admin(actor)
        subject = self._subject(user_id)
        with self._lock:
            state = self._read()
            profile = self._ensure_profile(state, subject)
            if subject in self._configured_admins:
                return
            if profile["accessStatus"] != "approved":
                profile.update(
                    {
                        "accessStatus": "approved",
                        "role": "user",
                        "buildCredits": 1,
                        "unlimited": False,
                        "approvedAt": utc_now(),
                        "revokedAt": "",
                        "accessActor": actor.subject,
                        "accessReason": str(reason or "").strip(),
                    }
                )
                profile["lifetimeGranted"] = int(profile.get("lifetimeGranted") or 0) + 1
                self._event(state, subject, "approved", actor=actor.subject, reason=reason, credits=1)
            state["users"] = sorted(set(state.get("users", [])) | {subject})
            self._write(state)

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
            raise PermissionError("Configured Telegram admins cannot be revoked")
        with self._lock:
            state = self._read()
            profile = self._ensure_profile(state, subject)
            previous = int(profile.get("buildCredits") or 0)
            profile.update(
                {
                    "accessStatus": "revoked",
                    "buildCredits": 0,
                    "unlimited": False,
                    "revokedAt": utc_now(),
                    "accessActor": actor.subject,
                        "accessReason": reason,
                }
            )
            state["users"] = [value for value in state.get("users", []) if value != subject]
            state["admins"] = [value for value in state.get("admins", []) if value != subject]
            self._event(
                state,
                subject,
                "revoked",
                actor=actor.subject,
                reason=reason,
                creditsRemoved=previous,
            )
            self._write(state)

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
        with self._lock:
            state = self._read()
            profile = self._ensure_profile(state, subject)
            if profile["accessStatus"] != "approved":
                raise PermissionError("Telegram account is not approved")
            before = int(profile.get("buildCredits") or 0)
            unlimited_before = bool(profile.get("unlimited"))
            unlimited_after = unlimited_before
            if operation == "add":
                after = before + int(value or 0)
            elif operation == "set":
                after = int(value if value is not None else -1)
            elif operation == "unlimited":
                if unlimited is None:
                    raise ValueError("Unlimited value is required")
                unlimited_after = bool(unlimited)
                after = before
            else:
                raise ValueError("Unsupported allowance operation")
            if after < 0:
                raise ValueError("Build credits cannot be negative")
            reason = require_sensitive_admin_reason(
                reason,
                credits_before=before,
                credits_after=after,
                unlimited_before=unlimited_before,
                unlimited_after=unlimited_after,
                action="reduce access",
            )
            profile["buildCredits"] = after
            profile["unlimited"] = unlimited_after
            delta = int(profile["buildCredits"]) - before
            if delta > 0:
                profile["lifetimeGranted"] = int(profile.get("lifetimeGranted") or 0) + delta
            self._event(
                state,
                subject,
                "allowance_changed",
                actor=actor.subject,
                reason=reason,
                operation=operation,
                delta=delta,
                balance=profile["buildCredits"],
                unlimited=profile["unlimited"],
            )
            self._write(state)
            return dict(profile)

    def reserve_build(
        self,
        user_id: int | str,
        *,
        job_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        subject = self._subject(user_id)
        request_key = str(idempotency_key or "").strip()
        if not request_key or len(request_key) > 128:
            raise ValueError("Build idempotency key is invalid")
        with self._lock:
            state = self._read()
            for entry in state.setdefault("ledger", []):
                if (
                    entry.get("type") == "consume"
                    and entry.get("telegramId") == subject
                    and entry.get("idempotencyKey") == request_key
                ):
                    return {
                        "jobId": str(entry["jobId"]),
                        "existing": True,
                        "consumed": bool(entry.get("consumed")),
                    }
            profile = self._ensure_profile(state, subject)
            if profile["accessStatus"] != "approved":
                raise PermissionError("Telegram account is not approved")
            consumed = not bool(profile.get("unlimited"))
            if consumed and int(profile.get("buildCredits") or 0) <= 0:
                raise BuildQuotaError("No build credits remain")
            if consumed:
                profile["buildCredits"] = int(profile["buildCredits"]) - 1
                profile["lifetimeUsed"] = int(profile.get("lifetimeUsed") or 0) + 1
            profile["jobCount"] = int(profile.get("jobCount") or 0) + 1
            profile["lastJobId"] = str(job_id)
            profile["lastJobStatus"] = "queued"
            state["ledger"].append(
                {
                    "type": "consume",
                    "telegramId": subject,
                    "jobId": str(job_id),
                    "idempotencyKey": request_key,
                    "consumed": consumed,
                    "delta": -1 if consumed else 0,
                    "balanceAfter": profile["buildCredits"],
                    "createdAt": utc_now(),
                }
            )
            self._event(
                state,
                subject,
                "build_reserved",
                jobId=job_id,
                consumed=consumed,
                balance=profile["buildCredits"],
            )
            self._write(state)
            return {"jobId": str(job_id), "existing": False, "consumed": consumed}

    def compensate_build(
        self,
        user_id: int | str,
        job_id: str,
        *,
        reason: str,
        retain_job: bool = False,
    ) -> bool:
        subject = self._subject(user_id)
        with self._lock:
            state = self._read()
            ledger = state.setdefault("ledger", [])
            consume = next(
                (
                    entry
                    for entry in ledger
                    if entry.get("type") == "consume"
                    and entry.get("telegramId") == subject
                    and entry.get("jobId") == job_id
                ),
                None,
            )
            if consume is None or any(
                entry.get("type") == "compensate" and entry.get("jobId") == job_id
                for entry in ledger
            ):
                return False
            profile = self._ensure_profile(state, subject)
            consumed = bool(consume.get("consumed"))
            if consumed:
                profile["buildCredits"] = int(profile.get("buildCredits") or 0) + 1
                profile["lifetimeUsed"] = max(0, int(profile.get("lifetimeUsed") or 0) - 1)
            if not retain_job:
                profile["jobCount"] = max(0, int(profile.get("jobCount") or 0) - 1)
            if profile.get("lastJobId") == job_id:
                profile["lastJobStatus"] = "dispatch_failed"
            ledger.append(
                {
                    "type": "compensate",
                    "telegramId": subject,
                    "jobId": job_id,
                    "consumed": consumed,
                    "delta": 1 if consumed else 0,
                    "balanceAfter": profile["buildCredits"],
                    "reason": str(reason or ""),
                    "retainJob": bool(retain_job),
                    "createdAt": utc_now(),
                }
            )
            self._event(
                state,
                subject,
                "build_compensated",
                reason=reason,
                jobId=job_id,
                retainJob=bool(retain_job),
            )
            self._write(state)
            return True

    def update_job_status(self, user_id: int | str, job_id: str, status: str) -> None:
        subject = self._subject(user_id)
        with self._lock:
            state = self._read()
            profile = self._ensure_profile(state, subject)
            profile["lastJobId"] = str(job_id)
            profile["lastJobStatus"] = str(status or "")[:64]
            self._write(state)

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
        with self._lock:
            state = self._read()
            for subject in self._configured_admins:
                self._ensure_profile(state, subject).update(
                    {"accessStatus": "approved", "role": "admin", "unlimited": True, "configuredAdmin": True}
                )
            users = [dict(value) for value in state.get("profiles", {}).values() if isinstance(value, Mapping)]
        term = str(query or "").strip().casefold()
        if term:
            users = [
                user
                for user in users
                if term in " ".join(
                    str(user.get(key) or "").casefold()
                    for key in ("telegramId", "username", "displayName")
                )
            ]
        if status in {"pending", "approved", "revoked"}:
            users = [user for user in users if user.get("accessStatus") == status]
        if quota == "available":
            users = [user for user in users if user.get("unlimited") or int(user.get("buildCredits") or 0) > 0]
        elif quota == "exhausted":
            users = [user for user in users if not user.get("unlimited") and int(user.get("buildCredits") or 0) == 0]
        elif quota == "unlimited":
            users = [user for user in users if user.get("unlimited")]
        if activity == "active":
            users = [user for user in users if int(user.get("miniAppOpenCount") or 0) > 0]
        elif activity == "never":
            users = [user for user in users if int(user.get("miniAppOpenCount") or 0) == 0]
        elif activity == "jobs":
            users = [user for user in users if int(user.get("jobCount") or 0) > 0]
        allowed_sort = {"lastSeenAt", "firstSeenAt", "miniAppOpenCount", "jobCount", "buildCredits", "telegramId"}
        sort_key = sort if sort in allowed_sort else "lastSeenAt"
        users.sort(key=lambda user: (user.get(sort_key) is not None, user.get(sort_key)), reverse=direction != "asc")
        total = len(users)
        start = max(0, offset)
        return {"users": users[start : start + max(1, min(limit, 100))], "total": total}

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
        with self._lock:
            state = self._read()
            self._event(state, profile["telegramId"], "created_by_admin", actor=actor.subject)
            self._write(state)
        return profile

    def user_events(self, user_id: int | str, *, actor: Identity) -> list[dict[str, Any]]:
        self._require_admin(actor)
        subject = self._subject(user_id)
        with self._lock:
            events = [
                dict(event)
                for event in self._read().get("events", [])
                if isinstance(event, Mapping) and event.get("telegramId") == subject
            ]
        return list(reversed(events))

    def backfill_jobs(self, manifests: Iterable[object]) -> int:
        """Populate historical counters once while preserving newer live values."""

        grouped: dict[str, list[object]] = {}
        for manifest in manifests:
            owner = getattr(manifest, "owner", None)
            if getattr(owner, "channel", "") == "telegram":
                grouped.setdefault(str(owner.subject), []).append(manifest)
        with self._lock:
            state = self._read()
            if state.get("jobBackfillComplete"):
                return 0
            for subject, jobs in grouped.items():
                profile = self._ensure_profile(state, subject)
                latest = max(jobs, key=lambda item: str(getattr(item, "created_at", "")))
                profile["jobCount"] = max(int(profile.get("jobCount") or 0), len(jobs))
                profile["lastJobId"] = str(getattr(latest, "job_id", ""))
                status = getattr(latest, "status", "")
                profile["lastJobStatus"] = str(getattr(status, "value", status))
            state["jobBackfillComplete"] = True
            self._write(state)
        return sum(len(jobs) for jobs in grouped.values())

    def list_access(self, *, actor: Identity) -> dict[str, list[str]]:
        self._require_admin(actor)
        with self._lock:
            state = self._read()
            admins = set(self._configured_admins)
            users: list[str] = []
            for subject, profile in state.get("profiles", {}).items():
                if profile.get("accessStatus") != "approved":
                    continue
                if profile.get("role") == "admin":
                    admins.add(subject)
                else:
                    users.append(subject)
            return {"admins": sorted(admins), "users": sorted(users)}

    def import_identity(self, subject: str, role: str) -> bool:
        normalized = self._subject(subject)
        normalized_role = str(role or "").strip().casefold()
        if normalized_role not in {"admin", "user"}:
            raise ValueError("Legacy Telegram access identity is invalid")
        with self._lock:
            state = self._read()
            existing = self.identity(normalized)
            if existing and existing.role == normalized_role:
                return False
            profile = self._ensure_profile(state, normalized)
            profile.update(
                {
                    "accessStatus": "approved",
                    "role": normalized_role,
                    "unlimited": normalized_role == "admin",
                    "buildCredits": 0 if normalized_role == "admin" else 1,
                    "lifetimeGranted": 0 if normalized_role == "admin" else 1,
                }
            )
            self._write(state)
            return True

    def is_configured_admin(self, subject: int | str) -> bool:
        return str(subject).strip() in self._configured_admins

    @staticmethod
    def _require_admin(actor: Identity) -> None:
        if actor.channel != "telegram" or actor.role != "admin":
            raise PermissionError("Admin access is required")

    def _read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.is_file():
                return {
                    "schemaVersion": 2,
                    "admins": [],
                    "users": [],
                    "profiles": {},
                    "events": [],
                    "ledger": [],
                    "sessions": {},
                }
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            return {
                "schemaVersion": 2,
                "admins": [str(value) for value in payload.get("admins", [])],
                "users": [str(value) for value in payload.get("users", [])],
                "profiles": dict(payload.get("profiles", {})) if isinstance(payload.get("profiles"), Mapping) else {},
                "events": list(payload.get("events", [])) if isinstance(payload.get("events"), list) else [],
                "ledger": list(payload.get("ledger", [])) if isinstance(payload.get("ledger"), list) else [],
                "sessions": dict(payload.get("sessions", {})) if isinstance(payload.get("sessions"), Mapping) else {},
                "jobBackfillComplete": bool(payload.get("jobBackfillComplete")),
            }

    def _write(self, state: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=self.path.name, dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump({"schemaVersion": 2, **state}, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                os.replace(temporary_name, self.path)
            finally:
                Path(temporary_name).unlink(missing_ok=True)
            if self.on_change:
                self.on_change()

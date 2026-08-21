from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterable

from .models import Identity


class TelegramAccessStore:
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

    def identity(self, user_id: int | str) -> Identity | None:
        subject = str(user_id).strip()
        state = self._read()
        if subject in self._configured_admins or subject in state["admins"]:
            return Identity("telegram", subject, "admin")
        if subject in state["users"]:
            return Identity("telegram", subject, "user")
        return None

    def approve(self, user_id: int | str, *, actor: Identity) -> None:
        self._require_admin(actor)
        subject = str(user_id).strip()
        if not subject:
            raise ValueError("Telegram user ID is required")
        state = self._read()
        if subject not in state["admins"] and subject not in self._configured_admins:
            state["users"] = sorted(set(state["users"]) | {subject})
        self._write(state)

    def revoke(self, user_id: int | str, *, actor: Identity) -> None:
        self._require_admin(actor)
        subject = str(user_id).strip()
        if subject in self._configured_admins:
            raise PermissionError("Configured Telegram admins cannot be revoked from the allowlist")
        state = self._read()
        state["users"] = [value for value in state["users"] if value != subject]
        state["admins"] = [value for value in state["admins"] if value != subject]
        self._write(state)

    def list_access(self, *, actor: Identity) -> dict[str, list[str]]:
        self._require_admin(actor)
        state = self._read()
        return {
            "admins": sorted(set(state["admins"]) | self._configured_admins),
            "users": sorted(state["users"]),
        }

    @staticmethod
    def _require_admin(actor: Identity) -> None:
        if actor.channel != "telegram" or actor.role != "admin":
            raise PermissionError("Admin access is required")

    def _read(self) -> dict[str, list[str]]:
        with self._lock:
            if not self.path.is_file():
                return {"admins": [], "users": []}
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {"admins": [], "users": []}
            return {
                "admins": [str(value) for value in payload.get("admins", [])],
                "users": [str(value) for value in payload.get("users", [])],
            }

    def _write(self, state: dict[str, list[str]]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=self.path.name, dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump({"schemaVersion": 1, **state}, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                os.replace(temporary_name, self.path)
            finally:
                Path(temporary_name).unlink(missing_ok=True)
            if self.on_change:
                self.on_change()

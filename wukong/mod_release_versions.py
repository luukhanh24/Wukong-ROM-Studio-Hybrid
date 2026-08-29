from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Callable, Mapping


# Labels are copied into ZIP names and Drive folder names. Keep the grammar
# portable across Windows and POSIX so an admin cannot save a value that later
# fails during packaging (or becomes a path component).
SAFE_RELEASE_LABEL = re.compile(
    r"^(?=.{1,64}$)(?!.*[ .]$)(?!\.+$)[^/\\\x00-\x1f<>:\"|?*]+$"
)
DEFAULT_MOD_RELEASE_VERSION = "V3.4"
DEFAULT_MOD_RELEASE_VERSIONS = {
    "ColorOS_15.0.1": "V3.4",
    "ColorOS_16.0.10": "V6.0",
    "ColorOS_16.0.5": "V3.4",
    "ColorOS_16.0.7": "V3.4",
    "ColorOS_16.0.8": "V4.1",
    "ColorOS_16.0.9": "V5.0",
    "RealmeUI_16.0.7": "V3.4",
    "RealmeUI_16.0.9": "V5.0",
}


def default_mod_release_version(mod_version: str) -> str:
    return DEFAULT_MOD_RELEASE_VERSIONS.get(mod_version.strip(), DEFAULT_MOD_RELEASE_VERSION)


class ModReleaseVersionStore:
    """Small atomic store for operator-facing labels keyed by MOD pack ID."""

    def __init__(
        self,
        path: Path,
        *,
        versions_provider: Callable[[], list[str]],
        default_provider: Callable[[str], str],
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.path = path.resolve()
        self.versions_provider = versions_provider
        self.default_provider = default_provider
        self.on_change = on_change
        self._lock = threading.RLock()

    def load(self) -> dict[str, str]:
        with self._lock:
            known = self.versions_provider()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if not isinstance(payload, Mapping):
                payload = {}
            return {
                version: self._validated(payload.get(version), self.default_provider(version))
                for version in known
            }

    def save(self, values: Mapping[str, str]) -> dict[str, str]:
        with self._lock:
            known = set(self.versions_provider())
            unknown = {str(key) for key in values} - known
            if unknown:
                raise ValueError(f"Unknown MOD pack: {', '.join(sorted(unknown))}")
            current = self.load()
            for version, value in values.items():
                label = str(value).strip()
                if not SAFE_RELEASE_LABEL.fullmatch(label):
                    raise ValueError("Release label must be 1–64 printable filename-safe characters")
                current[str(version)] = label
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                temporary.write_text(
                    json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
            if self.on_change:
                self.on_change()
            return current

    @staticmethod
    def _validated(value: object, fallback: str) -> str:
        candidate = str(value or "").strip()
        return candidate if SAFE_RELEASE_LABEL.fullmatch(candidate) else fallback

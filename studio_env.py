from __future__ import annotations

import os
from pathlib import Path

from studio_paths import DATA_ROOT, DESKTOP_MODE, SOURCE_ROOT


ROOT_DIR = SOURCE_ROOT
RUNTIME_DIR = DATA_ROOT
TELEGRAM_ENV_PATH = (
    RUNTIME_DIR / "Secrets" / "telegram.env"
    if DESKTOP_MODE
    else RUNTIME_DIR / "telegram.env"
)
TELEGRAM_ENV_KEYS = {
    "WUKONG_TELEGRAM_BOT_TOKEN",
    "WUKONG_TELEGRAM_ADMIN_IDS",
    "WUKONG_TELEGRAM_CHAT_ID",
    "WUKONG_TELEGRAM_PARSE_MODE",
    "WUKONG_TELEGRAM_TIMEOUT",
    "WUKONG_TELEGRAM_TIMEZONE",
}


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_local_env(path: Path = TELEGRAM_ENV_PATH, *, override: bool = False) -> dict[str, str]:
    if not path.is_file():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in TELEGRAM_ENV_KEYS:
            continue
        if not override and os.environ.get(key):
            continue
        loaded[key] = _unquote_env_value(value)
        os.environ[key] = loaded[key]
    return loaded

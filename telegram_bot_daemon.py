from __future__ import annotations

import json
import os
from pathlib import Path

from studio_core import list_mod_versions, list_mods, load_devices, stage_cache_status
from studio_env import load_local_env
from studio_paths import DATA_ROOT, JOBS_ROOT, WORKSPACE_ROOT
from studio_server import diagnostics
from wukong.orchestrator import FileJobStore, HybridOrchestrator
from wukong.routing import RunnerInventory
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import (
    TelegramBotController,
    TelegramLongPollingDaemon,
    TelegramUIStateStore,
)
from wukong.runtime import HybridRuntime
from wukong.security import validate_recipe_access


def _ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main() -> int:
    load_local_env()
    token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
    admins = _ids(os.environ.get("WUKONG_TELEGRAM_ADMIN_IDS", ""))
    if not token or not admins:
        print("Missing WUKONG_TELEGRAM_BOT_TOKEN or WUKONG_TELEGRAM_ADMIN_IDS")
        return 2
    store = FileJobStore(JOBS_ROOT / "hybrid")
    orchestrator = HybridOrchestrator(
        store=store,
        workspace_root=WORKSPACE_ROOT / ".wkstudio" / "hybrid",
        inventory_provider=lambda: RunnerInventory(False),
        access_validator=lambda recipe, identity: validate_recipe_access(
            recipe,
            identity,
            local_roots=[WORKSPACE_ROOT],
            allowed_remote=os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive"),
        ),
    )
    runtime = HybridRuntime(
        orchestrator=orchestrator,
        store=store,
        workspace_root=WORKSPACE_ROOT / ".wkstudio" / "hybrid",
        data_root=DATA_ROOT,
    )
    access = TelegramAccessStore(DATA_ROOT / "telegram-access.json", admin_ids=admins)
    controller = TelegramBotController(
        access=access,
        orchestrator=orchestrator,
        catalog_provider=lambda: {
            "devices": load_devices(),
            "modVersions": list_mod_versions(),
            "mods": {version: list_mods(version) for version in list_mod_versions()},
        },
        diagnostics_provider=lambda: {"system": diagnostics(), "cache": stage_cache_status()},
        cache_provider=stage_cache_status,
        cache_clearer=None,
        cloud_provider=lambda category: runtime.cloud_library(category=category),
        runtime=runtime,
        ui_state=TelegramUIStateStore(DATA_ROOT / "telegram-ui-state.json"),
    )
    TelegramLongPollingDaemon(token, controller).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
from pathlib import Path

from tools.export_mini_app_catalog import export_catalog


def _bootstrap_content_root() -> None:
    if os.environ.get("WUKONG_STUDIO_CONTENT_ROOT", "").strip():
        return
    configured = os.environ.get("WUKONG_TELEGRAM_CONTENT_ROOT", "").strip()
    candidate = Path(configured) if configured else Path(r"C:\WukongROMStudio\Content")
    if (candidate / "MOD").is_dir():
        os.environ["WUKONG_STUDIO_CONTENT_ROOT"] = str(candidate.resolve())


_bootstrap_content_root()

from studio_core import (
    LITE_DEFAULT_MODS,
    PLUS_DEFAULT_EXCLUDED_MODS,
    list_mod_versions,
    list_mods,
    load_devices,
    stage_cache_status,
)
from studio_env import load_local_env
from studio_paths import CONTENT_ROOT, DATA_ROOT, JOBS_ROOT, WORKSPACE_ROOT
from studio_server import diagnostics
from wukong.orchestrator import FileJobStore, HybridOrchestrator
from wukong.content_packs import validate_content_index
from wukong.routing import RunnerInventory
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import (
    TelegramBotController,
    TelegramLongPollingDaemon,
    TelegramUIStateStore,
)
from wukong.telegram_mini_api import (
    TelegramJobNotifier,
    TelegramMiniAppAPI,
    TelegramMiniAppAPIServer,
)
from wukong.runtime import HybridRuntime
from wukong.security import validate_recipe_access
from wukong.source_probe import probe_http_source


def _ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _configured_admin_ids() -> set[str]:
    configured = _ids(os.environ.get("WUKONG_TELEGRAM_ADMIN_IDS", ""))
    if configured:
        return configured
    private_chat = os.environ.get("WUKONG_TELEGRAM_CHAT_ID", "").strip()
    return {private_chat} if private_chat.isdigit() and int(private_chat) > 0 else set()


def _content_root() -> Path:
    configured = os.environ.get("WUKONG_TELEGRAM_CONTENT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    installed = Path(os.environ.get("WUKONG_STUDIO_INSTALL_ROOT", r"C:\WukongROMStudio")) / "Content"
    return installed.resolve() if (installed / "MOD").is_dir() else CONTENT_ROOT.resolve()


def build_telegram_catalog(content_root: Path, index_path: Path) -> dict[str, object]:
    mod_root = content_root.resolve() / "MOD"
    versions = list_mod_versions(mod_root=mod_root)
    available_github: list[str] = []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        validate_content_index(index)
    except (OSError, ValueError, json.JSONDecodeError):
        index = {}
    for pack in index.get("packs", []) if isinstance(index, dict) else []:
        pack_id = str(pack.get("id") or "") if isinstance(pack, dict) else ""
        archive = pack.get("archive") if isinstance(pack, dict) else None
        if pack_id.startswith("MOD/") and isinstance(archive, dict) and archive.get("sha256"):
            available_github.append(pack_id.split("/", 1)[1])
    mods_by_version = {
        version: list_mods(version, mod_root=mod_root)
        for version in versions
    }
    return {
        "devices": load_devices(),
        "modVersions": versions,
        "availableGitHubModVersions": sorted(set(available_github), key=str.casefold),
        "modsByVersion": mods_by_version,
        "presetDefaultsByVersion": {
            version: {
                "lite": [
                    name
                    for name in LITE_DEFAULT_MODS
                    if any(mod["name"] == name for mod in mods_by_version[version])
                ],
                "both": [
                    mod["name"]
                    for mod in mods_by_version[version]
                    if mod["name"] not in PLUS_DEFAULT_EXCLUDED_MODS
                ],
            }
            for version in versions
        },
    }

def build_control_plane_catalog(index_path: Path) -> dict[str, object]:
    """Build a catalog from the public manifest without installing private MOD files."""
    output = DATA_ROOT / "telegram-mini-catalog.json"
    return export_catalog(
        index_path,
        Path(__file__).resolve().parent / "devices_sizes.json",
        output,
    )


def main() -> int:
    load_local_env()
    token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
    admins = _configured_admin_ids()
    if not token or not admins:
        print("Missing WUKONG_TELEGRAM_BOT_TOKEN or WUKONG_TELEGRAM_ADMIN_IDS")
        return 2
    store = FileJobStore(JOBS_ROOT / "hybrid")
    access = TelegramAccessStore(DATA_ROOT / "telegram-access.json", admin_ids=admins)
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
    content_root = _content_root()
    index_path = Path(__file__).resolve().parent / "content-packs" / "index.json"
    runtime = HybridRuntime(
        orchestrator=orchestrator,
        store=store,
        workspace_root=WORKSPACE_ROOT / ".wkstudio" / "hybrid",
        data_root=DATA_ROOT,
        content_root=content_root,
        content_index=index_path,
        terminal_notifier=TelegramJobNotifier(token),
    )
    resumed_watchers = runtime.resume_cloud_watchers()
    if resumed_watchers:
        print(f"Resumed {resumed_watchers} cloud job watcher(s).", flush=True)
    if (content_root / "MOD").is_dir():
        catalog_provider = lambda: build_telegram_catalog(content_root, index_path)
    else:
        control_plane_catalog = build_control_plane_catalog(index_path)
        catalog_provider = lambda: control_plane_catalog
    diagnostics_provider = lambda: {"system": diagnostics(), "cache": stage_cache_status()}
    controller = TelegramBotController(
        access=access,
        orchestrator=orchestrator,
        catalog_provider=catalog_provider,
        diagnostics_provider=diagnostics_provider,
        cache_provider=stage_cache_status,
        cache_clearer=None,
        cloud_provider=lambda category: runtime.cloud_library(category=category),
        source_probe_provider=lambda uri: probe_http_source(uri).to_dict(),
        runtime=runtime,
        ui_state=TelegramUIStateStore(DATA_ROOT / "telegram-ui-state.json"),
    )
    mini_api_server: TelegramMiniAppAPIServer | None = None
    web_app_url = os.environ.get("WUKONG_TELEGRAM_WEB_APP_URL", "").strip()
    if web_app_url:
        try:
            mini_api = TelegramMiniAppAPI(
                bot_token=token,
                allowed_origin=web_app_url,
                access=access,
                orchestrator=orchestrator,
                runtime=runtime,
                catalog_provider=catalog_provider,
                diagnostics_provider=diagnostics_provider,
                source_probe_provider=lambda uri: probe_http_source(uri).to_dict(),
                cloud_provider=lambda category: runtime.cloud_library(category=category),
                cache_provider=stage_cache_status,
                max_init_data_age_seconds=int(
                    os.environ.get("WUKONG_TELEGRAM_MINI_APP_MAX_AUTH_AGE", "3600")
                ),
            )
            mini_api_server = TelegramMiniAppAPIServer(
                mini_api,
                host=os.environ.get("WUKONG_TELEGRAM_MINI_APP_API_BIND", "127.0.0.1"),
                port=int(os.environ.get("WUKONG_TELEGRAM_MINI_APP_API_PORT", "8766")),
            )
            mini_api_server.start()
            print(
                "Telegram Mini App API listening on "
                f"{mini_api_server.host}:{mini_api_server.port}",
                flush=True,
            )
        except (OSError, TypeError, ValueError) as exc:
            print(f"Telegram Mini App API could not start: {exc}", flush=True)
            return 2
    try:
        TelegramLongPollingDaemon(token, controller).run()
    finally:
        if mini_api_server:
            mini_api_server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

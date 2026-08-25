from __future__ import annotations

import atexit
import hashlib
import hmac
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask

from studio_paths import CONTENT_ROOT, DATA_ROOT, JOBS_ROOT, WORKSPACE_ROOT
from studio_server import diagnostics
from studio_core import default_studio_version
from telegram_bot_daemon import (
    _configured_admin_ids,
    _content_root,
    build_control_plane_catalog,
    build_telegram_catalog,
)
from wukong.cloud_tasks import CloudTaskDispatcher, CloudTasksOIDCVerifier
from wukong.control_plane_storage import ControlPlaneStores, open_control_plane_stores
from wukong.orchestrator import HybridOrchestrator
from wukong.routing import RunnerInventory
from wukong.runtime import HybridRuntime
from wukong.security import validate_recipe_access
from wukong.source_probe import probe_http_source
from wukong.telegram_bot import TelegramBotController, TelegramLongPollingDaemon
from wukong.telegram_mini_api import TelegramJobNotifier, TelegramMiniAppAPI, public_artifact_url


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for Cloud Run")
    return value


def _webhook_secret(token: str, api_url: str) -> str:
    configured = os.environ.get("WUKONG_TELEGRAM_WEBHOOK_SECRET", "").strip()
    if configured:
        return configured
    domain = (urlsplit(api_url).hostname or "").encode("utf-8")
    return hmac.new(
        token.encode("utf-8"),
        b"WukongTelegramWebhook\0" + domain,
        hashlib.sha256,
    ).hexdigest()


def create_cloud_run_app() -> Flask:
    """Build a stateless Wukong API without startup-time external side effects."""

    token = _required("WUKONG_TELEGRAM_BOT_TOKEN")
    database_url = _required("DATABASE_URL")
    api_url = _required("WUKONG_TELEGRAM_MINI_APP_API_URL").rstrip("/")
    web_app_url = _required("WUKONG_TELEGRAM_WEB_APP_URL").rstrip("/") + "/"
    repository = _required("WUKONG_GITHUB_REPOSITORY")
    if "/" not in repository:
        raise RuntimeError("WUKONG_GITHUB_REPOSITORY must be owner/repository")
    admins = sorted(_configured_admin_ids())
    for directory in (DATA_ROOT, WORKSPACE_ROOT, JOBS_ROOT):
        Path(directory).mkdir(parents=True, exist_ok=True)

    stores: ControlPlaneStores = open_control_plane_stores(
        database_url=database_url,
        data_root=DATA_ROOT,
        jobs_root=JOBS_ROOT / "hybrid",
        admin_ids=admins,
    )
    atexit.register(stores.close)
    orchestrator = HybridOrchestrator(
        store=stores.jobs,
        workspace_root=WORKSPACE_ROOT / ".wkstudio" / "hybrid",
        inventory_provider=lambda: RunnerInventory(False),
        access_validator=lambda recipe, identity: validate_recipe_access(
            recipe,
            identity,
            local_roots=[WORKSPACE_ROOT],
            allowed_remote=os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive"),
        ),
        submission_reserver=lambda identity, job_id: stores.access.reserve_build(
            identity.subject,
            job_id=job_id,
            idempotency_key=job_id,
        ),
        submission_compensator=lambda identity, job_id, reason, retain_job: (
            stores.access.compensate_build(
                identity.subject,
                job_id,
                reason=reason,
                retain_job=retain_job,
            )
            if identity.channel == "telegram"
            else False
        ),
    )
    content_root = _content_root()
    index_path = Path(__file__).resolve().parents[1] / "content-packs" / "index.json"
    runtime = HybridRuntime(
        orchestrator=orchestrator,
        store=stores.jobs,
        workspace_root=WORKSPACE_ROOT / ".wkstudio" / "hybrid",
        data_root=DATA_ROOT,
        content_root=content_root,
        content_index=index_path,
        terminal_notifier=TelegramJobNotifier(token),
    )
    if (content_root / "MOD").is_dir():
        base_catalog_provider = lambda: build_telegram_catalog(content_root, index_path)
    else:
        static_catalog = build_control_plane_catalog(index_path)
        base_catalog_provider = lambda: static_catalog

    def release_versions() -> dict[str, str]:
        return {
            str(version): default_studio_version(str(version))
            for version in base_catalog_provider().get("modVersions", [])
        }

    def catalog_provider() -> dict[str, object]:
        catalog = dict(base_catalog_provider())
        catalog["modReleaseVersions"] = release_versions()
        return catalog

    def artifact_download_url(manifest: object) -> str:
        return next(
            (
                public_artifact_url(artifact.public_url)
                for artifact in getattr(manifest, "artifacts", [])
                if public_artifact_url(artifact.public_url)
            ),
            "",
        )

    controller = TelegramBotController(
        access=stores.access,
        orchestrator=orchestrator,
        catalog_provider=catalog_provider,
        diagnostics_provider=lambda: {"system": diagnostics()},
        cache_provider=lambda: {"entryCount": 0, "totalBytes": 0},
        cache_clearer=None,
        cloud_provider=lambda category: runtime.cloud_library(category=category),
        source_probe_provider=lambda uri: probe_http_source(uri).to_dict(),
        runtime=runtime,
        ui_state=stores.ui_state,
        session_store=stores.sessions,
        artifact_download_url_provider=artifact_download_url,
    )
    telegram_transport = TelegramLongPollingDaemon(token, controller)
    webhook_secret = _webhook_secret(token, api_url)

    def configure_telegram(_release: str) -> None:
        telegram_transport.register_commands()
        telegram_transport.configure_webhook(api_url, webhook_secret)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT", "")).strip()
    location = os.environ.get("WUKONG_CLOUD_TASKS_LOCATION", "asia-southeast1").strip()
    task_service_account = _required("WUKONG_CLOUD_TASKS_SERVICE_ACCOUNT")
    task_dispatcher = CloudTaskDispatcher(
        project=project,
        location=location,
        base_url=api_url,
        service_account_email=task_service_account,
        audience=api_url,
    )
    task_verifier = CloudTasksOIDCVerifier(
        audience=api_url,
        service_account_email=task_service_account,
    )
    api = TelegramMiniAppAPI(
        bot_token=token,
        allowed_origin=web_app_url,
        access=stores.access,
        orchestrator=orchestrator,
        runtime=runtime,
        catalog_provider=catalog_provider,
        release_versions_provider=release_versions,
        release_versions_saver=None,
        diagnostics_provider=lambda: {"system": diagnostics()},
        source_probe_provider=lambda uri: probe_http_source(uri).to_dict(),
        cloud_provider=lambda category: runtime.cloud_library(category=category),
        cache_provider=lambda: {"entryCount": 0, "totalBytes": 0},
        cache_clearer=None,
        telegram_update_handler=telegram_transport.process_update,
        telegram_configuration_handler=configure_telegram,
        telegram_webhook_secret=webhook_secret,
        cloud_task_dispatcher=task_dispatcher,
        task_store=stores.tasks,
        task_token_verifier=task_verifier,
        actions_callback_secret=_required("WUKONG_ACTIONS_CALLBACK_SECRET"),
        readiness_provider=lambda: True,
        max_init_data_age_seconds=int(
            os.environ.get("WUKONG_TELEGRAM_MINI_APP_MAX_AUTH_AGE", "3600")
        ),
        session_store=stores.sessions,
        bot_username=os.environ.get("WUKONG_TELEGRAM_BOT_USERNAME", "WK_build_bot"),
        state_backend="postgresql",
    )
    return api.app


app = create_cloud_run_app()

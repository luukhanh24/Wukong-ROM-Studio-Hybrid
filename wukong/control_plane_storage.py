from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .models import Identity
from .orchestrator import FileJobStore, JobStore
from .postgres_state import (
    ConnectionFactory,
    PostgresJobStore,
    PostgresTelegramAccessStore,
    PostgresTelegramUIStateStore,
    migrate_file_job_store,
    migrate_telegram_access_store,
    migrate_telegram_ui_state_file,
)
from .telegram import TelegramAccessStore
from .telegram_bot import TelegramUIStateStore


LEGACY_MIGRATION_KEY = "legacy-file-state-v1"
TELEGRAM_PROFILE_BACKFILL_KEY = "telegram-profile-backfill-v1"


@dataclass(frozen=True)
class ControlPlaneStores:
    jobs: JobStore
    access: Any
    ui_state: Any
    migration: dict[str, dict[str, int]] = field(default_factory=dict)


def open_control_plane_stores(
    *,
    database_url: str,
    data_root: Path,
    jobs_root: Path,
    admin_ids: list[int | str] | tuple[int | str, ...],
    on_change: Callable[[], None] | None = None,
    connect: ConnectionFactory | None = None,
    dialect: str = "postgresql",
) -> ControlPlaneStores:
    """Open durable state and migrate the legacy files before serving traffic."""

    legacy_jobs = FileJobStore(jobs_root, on_change=on_change)
    legacy_access = TelegramAccessStore(
        data_root / "telegram-access.json",
        admin_ids=admin_ids,
        on_change=on_change,
    )
    legacy_ui = TelegramUIStateStore(
        data_root / "telegram-ui-state.json",
        on_change=on_change,
    )
    normalized_url = database_url.strip()
    if not normalized_url:
        legacy_access.backfill_jobs(legacy_jobs.list())
        return ControlPlaneStores(legacy_jobs, legacy_access, legacy_ui)

    shared_options: dict[str, object] = {"dialect": dialect}
    if connect is not None:
        shared_options["connect"] = connect
    jobs = PostgresJobStore(normalized_url, **shared_options)
    access = PostgresTelegramAccessStore(
        normalized_url,
        admin_ids=admin_ids,
        **shared_options,
    )
    ui_state = PostgresTelegramUIStateStore(normalized_url, **shared_options)
    configured_admins = [str(value).strip() for value in admin_ids if str(value).strip()]
    if not configured_admins:
        raise ValueError("At least one configured Telegram admin is required")
    actor = Identity("telegram", configured_admins[0], "admin")
    migration: dict[str, dict[str, int]] = {}
    if jobs.metadata(LEGACY_MIGRATION_KEY) != "complete":
        migration = {
            "jobs": migrate_file_job_store(legacy_jobs, jobs),
            "access": migrate_telegram_access_store(legacy_access, access, actor=actor),
            "ui": migrate_telegram_ui_state_file(
                data_root / "telegram-ui-state.json",
                ui_state,
            ),
        }
        jobs.set_metadata(LEGACY_MIGRATION_KEY, "complete")
    if jobs.metadata(TELEGRAM_PROFILE_BACKFILL_KEY) != "complete":
        access.backfill_jobs(jobs.list())
        jobs.set_metadata(TELEGRAM_PROFILE_BACKFILL_KEY, "complete")
    return ControlPlaneStores(jobs, access, ui_state, migration)

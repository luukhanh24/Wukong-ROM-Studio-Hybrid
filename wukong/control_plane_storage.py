from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .models import Identity
from .orchestrator import FileJobStore, JobStore
from .postgres_state import (
    ConnectionFactory,
    PostgresControlPlaneTaskStore,
    PostgresJobStore,
    PostgresTelegramAccessStore,
    PostgresTelegramSessionStore,
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
    sessions: Any
    tasks: Any
    migration: dict[str, dict[str, int]] = field(default_factory=dict)
    connection_pool: Any = None

    def close(self) -> None:
        if self.connection_pool is not None:
            self.connection_pool.close()


class _PooledConnection:
    def __init__(self, pool: Any, connection: Any) -> None:
        self._pool = pool
        self._connection = connection
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._pool.putconn(self._connection)


class _PooledConnectionFactory:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    def __call__(self) -> Any:
        return _PooledConnection(self.pool, self.pool.getconn(timeout=10))


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
        from .telegram_mini_api import TelegramMiniAppSessionStore

        legacy_access.backfill_jobs(legacy_jobs.list())
        return ControlPlaneStores(
            legacy_jobs,
            legacy_access,
            legacy_ui,
            TelegramMiniAppSessionStore(),
            None,
        )

    shared_options: dict[str, object] = {"dialect": dialect}
    connection_pool = None
    if connect is not None:
        shared_options["connect"] = connect
    elif dialect == "postgresql":
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError("psycopg-pool is required for PostgreSQL state") from exc
        import os

        maximum = max(1, min(int(os.environ.get("WUKONG_DATABASE_POOL_MAX", "8")), 32))
        connection_pool = ConnectionPool(
            conninfo=normalized_url,
            min_size=0,
            max_size=maximum,
            open=True,
        )
        shared_options["connect"] = _PooledConnectionFactory(connection_pool)
    jobs = PostgresJobStore(normalized_url, **shared_options)
    access = PostgresTelegramAccessStore(
        normalized_url,
        admin_ids=admin_ids,
        **shared_options,
    )
    ui_state = PostgresTelegramUIStateStore(normalized_url, **shared_options)
    sessions = PostgresTelegramSessionStore(normalized_url, **shared_options)
    tasks = PostgresControlPlaneTaskStore(normalized_url, **shared_options)
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
    return ControlPlaneStores(
        jobs,
        access,
        ui_state,
        sessions,
        tasks,
        migration,
        connection_pool,
    )

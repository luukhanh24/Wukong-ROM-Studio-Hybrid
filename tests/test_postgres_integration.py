from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from wukong.control_plane_storage import open_control_plane_stores
from wukong.models import BuildRecipe, Identity, JobManifest, JobStatus
from wukong.orchestrator import FileJobStore
from wukong.postgres_state import PostgresJobStore
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import TelegramUIStateStore


POSTGRES_URL = os.environ.get("WUKONG_TEST_POSTGRES_URL", "").strip()


def _recipe() -> BuildRecipe:
    return BuildRecipe.from_dict(
        {
            "task": "build",
            "device": "PKG110",
            "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
            "execution": {"target": "github-auto"},
        }
    )


@unittest.skipUnless(POSTGRES_URL, "WUKONG_TEST_POSTGRES_URL is not configured")
class PostgreSQLIntegrationTests(unittest.TestCase):
    TABLES = (
        "wukong_telegram_quota_ledger",
        "wukong_telegram_sessions",
        "wukong_telegram_user_events",
        "wukong_telegram_users",
        "wukong_job_events",
        "wukong_jobs",
        "wukong_telegram_access",
        "wukong_telegram_ui_state",
        "wukong_control_plane_metadata",
    )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self._drop_test_tables()
        self.addCleanup(self._drop_test_tables)

    def _connect(self):
        import psycopg

        return psycopg.connect(POSTGRES_URL)

    def _drop_test_tables(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            for table in self.TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    def test_real_postgres_crud_restart_event_sequence_and_one_time_migration(self) -> None:
        root = Path(self.temporary.name)
        data_root = root / "data"
        jobs_root = data_root / "jobs" / "hybrid"
        recipe = _recipe()
        legacy_jobs = FileJobStore(jobs_root)
        legacy_jobs.create(
            JobManifest(
                job_id="legacy-postgres-job",
                owner=Identity("telegram", "42", "admin"),
                recipe_digest=recipe.digest,
            ),
            recipe,
        )
        admin = Identity("telegram", "42", "admin")
        legacy_access = TelegramAccessStore(data_root / "telegram-access.json", admin_ids=[42])
        legacy_access.approve(99, actor=admin)
        legacy_ui = TelegramUIStateStore(data_root / "telegram-ui-state.json")
        legacy_ui.set_language(42, "en")

        stores = open_control_plane_stores(
            database_url=POSTGRES_URL,
            data_root=data_root,
            jobs_root=jobs_root,
            admin_ids=[42],
        )
        first = stores.jobs.append_event("legacy-postgres-job", "started")
        second = stores.jobs.append_event("legacy-postgres-job", "progress", value=50)
        stores.jobs.update(
            "legacy-postgres-job",
            status=JobStatus.RUNNING,
            progress=0.5,
        )

        self.assertEqual((1, 2), (first.sequence, second.sequence))
        self.assertEqual("user", stores.access.identity(99).role)
        self.assertEqual("en", stores.ui_state.language(42))
        self.assertTrue(stores.migration)

        stores.access.revoke(99, actor=admin)
        stores.ui_state.set_language(42, "vi")
        reopened = open_control_plane_stores(
            database_url=POSTGRES_URL,
            data_root=data_root,
            jobs_root=jobs_root,
            admin_ids=[42],
        )

        self.assertIsInstance(reopened.jobs, PostgresJobStore)
        self.assertEqual({}, reopened.migration)
        self.assertEqual(JobStatus.RUNNING, reopened.jobs.get("legacy-postgres-job").status)
        self.assertEqual([1, 2], [event.sequence for event in reopened.jobs.events("legacy-postgres-job")])
        self.assertIsNone(reopened.access.identity(99))
        self.assertEqual("vi", reopened.ui_state.language(42))


if __name__ == "__main__":
    unittest.main()

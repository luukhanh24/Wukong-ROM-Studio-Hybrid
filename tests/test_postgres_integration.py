from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

from wukong.control_plane_storage import open_control_plane_stores
from wukong.models import BuildRecipe, Identity, JobManifest, JobStatus
from wukong.orchestrator import FileJobStore
from wukong.postgres_state import PostgresJobStore, PostgresTelegramAccessStore
from wukong.telegram import BuildConcurrencyError, TelegramAccessStore
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
        "wukong_build_locks",
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

        stores.access.revoke(99, actor=admin, reason="integration test")
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

    def test_real_postgres_device_lock_accepts_only_one_concurrent_job(self) -> None:
        admin = Identity("telegram", "42", "admin")
        setup_access = PostgresTelegramAccessStore(
            database_url=POSTGRES_URL,
            admin_ids=[42],
        )
        for subject in (99, 100, 101):
            setup_access.approve(subject, actor=admin)
            setup_access.update_allowance(
                subject,
                actor=admin,
                operation="unlimited",
                unlimited=True,
            )
        recipe = _recipe()
        stores = [
            (
                PostgresJobStore(database_url=POSTGRES_URL),
                PostgresTelegramAccessStore(database_url=POSTGRES_URL, admin_ids=[42]),
            )
            for _ in range(2)
        ]
        barrier = threading.Barrier(3)
        results: list[tuple[str, str]] = []
        results_lock = threading.Lock()

        def submit(index: int, subject: str) -> None:
            jobs, access = stores[index]
            job_id = f"postgres-lock-{subject}"
            barrier.wait()
            try:
                access.reserve_and_create_job(
                    jobs,
                    JobManifest(
                        job_id=job_id,
                        owner=Identity("telegram", subject, "user"),
                        recipe_digest=recipe.digest,
                    ),
                    recipe,
                    idempotency_key=job_id,
                )
                outcome = ("accepted", job_id)
            except BuildConcurrencyError:
                outcome = ("conflict", job_id)
            with results_lock:
                results.append(outcome)

        threads = [
            threading.Thread(target=submit, args=(0, "99")),
            threading.Thread(target=submit, args=(1, "100")),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=15)

        self.assertEqual(["accepted", "conflict"], sorted(result[0] for result in results))
        accepted_job_id = next(job_id for outcome, job_id in results if outcome == "accepted")
        stores[0][0].update(accepted_job_id, status=JobStatus.SUCCEEDED)
        released = setup_access.reserve_and_create_job(
            PostgresJobStore(database_url=POSTGRES_URL),
            JobManifest(
                job_id="postgres-lock-released",
                owner=Identity("telegram", "101", "user"),
                recipe_digest=recipe.digest,
            ),
            recipe,
            idempotency_key="postgres-lock-released",
        )
        self.assertFalse(released["existing"])


if __name__ == "__main__":
    unittest.main()

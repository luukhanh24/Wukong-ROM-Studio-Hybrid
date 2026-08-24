from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from wukong.models import BuildRecipe, Identity, JobManifest, JobStatus
from wukong.orchestrator import FileJobStore
from wukong.postgres_state import (
    BuildQuotaError,
    PostgresJobStore,
    PostgresTelegramAccessStore,
    PostgresTelegramUIStateStore,
    migrate_file_job_store,
    migrate_telegram_access_store,
    migrate_telegram_ui_state_file,
)
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import TelegramUIStateStore
from wukong.control_plane_storage import open_control_plane_stores


def _recipe() -> BuildRecipe:
    return BuildRecipe.from_dict(
        {
            "schemaVersion": 1,
            "task": "build",
            "device": "PKG110",
            "source": {
                "kind": "https",
                "uri": "https://downloads.example/rom.zip",
                "sizeBytes": 8_718_572_190,
            },
            "build": {"preset": "plus", "modVersion": "ColorOS_16.0.10"},
            "execution": {"target": "github-auto"},
            "storage": {"remote": "wukong-gdrive", "publishArtifact": True},
        }
    )


class PostgresJobStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "control-plane.sqlite3"

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database)

    def test_job_state_survives_a_fresh_store_instance(self) -> None:
        recipe = _recipe()
        manifest = JobManifest(
            job_id="job-postgres-1",
            owner=Identity("telegram", "42", "admin"),
            recipe_digest=recipe.digest,
        )
        first = PostgresJobStore(connect=self.connect, dialect="sqlite")

        first.create(manifest, recipe)
        first.append_event(manifest.job_id, "submitted", channel="telegram")
        first.update(
            manifest.job_id,
            status=JobStatus.RUNNING,
            stage="extract",
            progress=0.35,
            external_run_id=123456,
        )

        restored = PostgresJobStore(connect=self.connect, dialect="sqlite")
        loaded = restored.get(manifest.job_id)

        self.assertIsNotNone(loaded)
        self.assertEqual(JobStatus.RUNNING, loaded.status)
        self.assertEqual("extract", loaded.stage)
        self.assertEqual(0.35, loaded.progress)
        self.assertEqual(123456, loaded.external_run_id)
        self.assertEqual(recipe.to_dict(), restored.recipe(manifest.job_id).to_dict())
        self.assertEqual("submitted", restored.events(manifest.job_id)[0].type)
        self.assertEqual([manifest.job_id], [job.job_id for job in restored.list()])

    def test_legacy_file_migration_is_complete_and_idempotent(self) -> None:
        recipe = _recipe()
        manifest = JobManifest(
            job_id="legacy-job-1",
            owner=Identity("telegram", "42", "admin"),
            recipe_digest=recipe.digest,
            status=JobStatus.SUCCEEDED,
        )
        legacy = FileJobStore(Path(self.temporary.name) / "legacy")
        legacy.create(manifest, recipe)
        original_event = legacy.append_event(
            manifest.job_id,
            "completed",
            artifactName="PKG110-plus.zip",
        )
        target = PostgresJobStore(connect=self.connect, dialect="sqlite")

        first_result = migrate_file_job_store(legacy, target)
        second_result = migrate_file_job_store(legacy, target)

        self.assertEqual({"imported": 1, "skipped": 0}, first_result)
        self.assertEqual({"imported": 0, "skipped": 1}, second_result)
        migrated_event = target.events(manifest.job_id)[0]
        self.assertEqual(original_event.to_dict(), migrated_event.to_dict())

    def test_telegram_access_is_durable_and_enforces_admin_role(self) -> None:
        admin = Identity("telegram", "42", "admin")
        first = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )

        first.approve(99, actor=admin)

        restored = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )
        self.assertEqual("admin", restored.identity(42).role)
        self.assertEqual("user", restored.identity(99).role)
        self.assertEqual({"admins": ["42"], "users": ["99"]}, restored.list_access(actor=admin))
        self.assertEqual(("42", "99"), restored.subjects())

        with self.assertRaisesRegex(ValueError, "reason"):
            restored.revoke(99, actor=admin)
        restored.revoke(99, actor=admin, reason="security review")
        self.assertIsNone(restored.identity(99))
        self.assertEqual(("42",), restored.subjects())
        with self.assertRaises(PermissionError):
            restored.approve(100, actor=Identity("telegram", "99", "user"))

    def test_telegram_user_profile_session_and_build_credit_are_durable_and_idempotent(self) -> None:
        admin = Identity("telegram", "42", "admin")
        store = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )

        pending = store.observe_user(
            99,
            username="fixture_user",
            display_name="Fixture User",
            language="vi",
            platform="android",
            app_version="2026.08",
        )
        self.assertEqual("pending", pending["accessStatus"])
        self.assertIsNone(store.identity(99))

        first_open = store.open_session(99, "launch-1")
        repeated_open = store.open_session(99, "launch-1")
        self.assertEqual(1, first_open["miniAppOpenCount"])
        self.assertEqual(1, repeated_open["miniAppOpenCount"])

        store.approve(99, actor=admin)
        approved = store.profile(99)
        self.assertEqual("approved", approved["accessStatus"])
        self.assertEqual(1, approved["buildCredits"])

        reserved = store.reserve_build(
            99,
            job_id="job-credit-1",
            idempotency_key="request-credit-1",
        )
        duplicate = store.reserve_build(
            99,
            job_id="different-job-id",
            idempotency_key="request-credit-1",
        )
        self.assertFalse(reserved["existing"])
        self.assertEqual("job-credit-1", duplicate["jobId"])
        self.assertTrue(duplicate["existing"])
        self.assertEqual(0, store.profile(99)["buildCredits"])
        self.assertEqual(1, store.profile(99)["jobCount"])
        with self.assertRaises(BuildQuotaError):
            store.reserve_build(99, job_id="job-credit-2", idempotency_key="request-credit-2")

        self.assertTrue(store.compensate_build(99, "job-credit-1", reason="dispatch failed"))
        self.assertFalse(store.compensate_build(99, "job-credit-1", reason="retry"))
        compensated = store.profile(99)
        self.assertEqual(1, compensated["buildCredits"])
        self.assertEqual(0, compensated["jobCount"])

        store.revoke(99, actor=admin, reason="manual review")
        revoked = store.profile(99)
        self.assertEqual("revoked", revoked["accessStatus"])
        self.assertEqual(0, revoked["buildCredits"])
        self.assertIsNone(store.identity(99))
        store.approve(99, actor=admin)
        self.assertEqual(1, store.profile(99)["buildCredits"])
        self.assertGreaterEqual(len(store.user_events(99, actor=admin)), 5)

    def test_configured_admin_is_unlimited_and_cannot_be_revoked(self) -> None:
        store = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )
        admin = store.identity(42)

        self.assertEqual("admin", admin.role)
        self.assertTrue(store.profile(42)["unlimited"])
        with self.assertRaises(PermissionError):
            store.revoke(42, actor=admin, reason="not allowed")
        reservation = store.reserve_build(
            42,
            job_id="admin-job",
            idempotency_key="admin-request",
        )
        self.assertFalse(reservation["consumed"])
        self.assertTrue(store.profile(42)["unlimited"])

    def test_postgres_job_and_credit_are_created_atomically_per_user_key(self) -> None:
        jobs = PostgresJobStore(connect=self.connect, dialect="sqlite")
        access = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )
        admin = access.identity(42)
        access.approve(99, actor=admin)
        access.approve(100, actor=admin)
        recipe = _recipe()
        first_manifest = JobManifest(
            job_id="atomic-job-99",
            owner=Identity("telegram", "99", "user"),
            recipe_digest=recipe.digest,
            runner="github-hosted",
        )

        created = access.reserve_and_create_job(
            jobs,
            first_manifest,
            recipe,
            idempotency_key="same-client-key",
        )
        duplicate = access.reserve_and_create_job(
            jobs,
            JobManifest(
                job_id="ignored-retry-job",
                owner=first_manifest.owner,
                recipe_digest=recipe.digest,
                runner="github-hosted",
            ),
            recipe,
            idempotency_key="same-client-key",
        )
        other_user = access.reserve_and_create_job(
            jobs,
            JobManifest(
                job_id="atomic-job-100",
                owner=Identity("telegram", "100", "user"),
                recipe_digest=recipe.digest,
                runner="github-hosted",
            ),
            recipe,
            idempotency_key="same-client-key",
        )

        self.assertFalse(created["existing"])
        self.assertTrue(duplicate["existing"])
        self.assertEqual("atomic-job-99", duplicate["jobId"])
        self.assertEqual("atomic-job-100", other_user["jobId"])
        self.assertEqual(0, access.profile(99)["buildCredits"])
        self.assertEqual(1, access.profile(99)["jobCount"])
        self.assertEqual("submitted", jobs.events("atomic-job-99")[0].type)

    def test_destructive_allowance_changes_require_a_reason(self) -> None:
        access = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )
        admin = access.identity(42)
        access.approve(99, actor=admin)
        access.update_allowance(99, actor=admin, operation="add", value=4)
        with self.assertRaisesRegex(ValueError, "reason"):
            access.update_allowance(99, actor=admin, operation="set", value=2)
        access.update_allowance(
            99,
            actor=admin,
            operation="set",
            value=2,
            reason="reduce test quota",
        )
        access.update_allowance(99, actor=admin, operation="unlimited", unlimited=True)
        with self.assertRaisesRegex(ValueError, "reason"):
            access.update_allowance(99, actor=admin, operation="unlimited", unlimited=False)

    def test_one_remaining_credit_accepts_only_one_concurrent_job(self) -> None:
        store = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )
        store.approve(99, actor=store.identity(42))
        barrier = threading.Barrier(3)
        results: list[str] = []

        def reserve(suffix: str) -> None:
            barrier.wait()
            try:
                store.reserve_build(
                    99,
                    job_id=f"race-job-{suffix}",
                    idempotency_key=f"race-request-{suffix}",
                )
                results.append("accepted")
            except BuildQuotaError:
                results.append("exhausted")

        threads = [threading.Thread(target=reserve, args=(suffix,)) for suffix in ("a", "b")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(["accepted", "exhausted"], sorted(results))
        self.assertEqual(0, store.profile(99)["buildCredits"])

    def test_legacy_access_migration_preserves_approved_users(self) -> None:
        admin = Identity("telegram", "42", "admin")
        legacy = TelegramAccessStore(
            Path(self.temporary.name) / "telegram-access.json",
            admin_ids=[42],
        )
        legacy.approve(99, actor=admin)
        target = PostgresTelegramAccessStore(
            connect=self.connect,
            dialect="sqlite",
            admin_ids=[42],
        )

        first_result = migrate_telegram_access_store(legacy, target, actor=admin)
        second_result = migrate_telegram_access_store(legacy, target, actor=admin)

        self.assertEqual({"imported": 1, "unchanged": 0}, first_result)
        self.assertEqual({"imported": 0, "unchanged": 1}, second_result)
        self.assertEqual("user", target.identity(99).role)

    def test_ui_preferences_persist_without_signed_source_urls(self) -> None:
        first = PostgresTelegramUIStateStore(connect=self.connect, dialect="sqlite")
        first.set_language(42, "en")
        first.set_session(
            42,
            {
                "step": "device",
                "source": {
                    "kind": "https",
                    "uri": "https://downloads.example/rom.zip?Signature=secret",
                },
            },
        )
        reference = first.remember_job(42, "job-private-reference")

        restored = PostgresTelegramUIStateStore(connect=self.connect, dialect="sqlite")

        self.assertEqual("en", restored.language(42))
        self.assertEqual({"step": "source_input", "awaiting": "url"}, restored.session(42))
        self.assertEqual("job-private-reference", restored.resolve_job(42, reference))
        restored.clear_session(42)
        self.assertEqual({}, restored.session(42))

    def test_legacy_ui_state_migration_preserves_preferences_and_job_refs(self) -> None:
        state_path = Path(self.temporary.name) / "telegram-ui-state.json"
        legacy = TelegramUIStateStore(state_path)
        legacy.set_language(42, "en")
        legacy.set_session(42, {"step": "preset", "device": "PKG110"})
        reference = legacy.remember_job(42, "legacy-job-42")
        target = PostgresTelegramUIStateStore(connect=self.connect, dialect="sqlite")

        first_result = migrate_telegram_ui_state_file(state_path, target)
        second_result = migrate_telegram_ui_state_file(state_path, target)

        self.assertEqual({"imported": 1, "unchanged": 0}, first_result)
        self.assertEqual({"imported": 0, "unchanged": 1}, second_result)
        self.assertEqual("en", target.language(42))
        self.assertEqual({"step": "preset", "device": "PKG110"}, target.session(42))
        self.assertEqual("legacy-job-42", target.resolve_job(42, reference))

    def test_control_plane_switches_to_postgres_after_migrating_legacy_state(self) -> None:
        data_root = Path(self.temporary.name) / "data"
        jobs_root = data_root / "jobs" / "hybrid"
        recipe = _recipe()
        legacy_jobs = FileJobStore(jobs_root)
        legacy_jobs.create(
            JobManifest(
                job_id="legacy-control-plane-job",
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

        configured = open_control_plane_stores(
            database_url="postgresql://fixture",
            data_root=data_root,
            jobs_root=jobs_root,
            admin_ids=[42],
            connect=self.connect,
            dialect="sqlite",
        )

        self.assertIsInstance(configured.jobs, PostgresJobStore)
        self.assertEqual("legacy-control-plane-job", configured.jobs.list()[0].job_id)
        self.assertEqual("user", configured.access.identity(99).role)
        self.assertEqual("en", configured.ui_state.language(42))
        self.assertEqual(
            {
                "jobs": {"imported": 1, "skipped": 0},
                "access": {"imported": 1, "unchanged": 0},
                "ui": {"imported": 1, "unchanged": 0},
            },
            configured.migration,
        )

        configured.access.revoke(99, actor=admin, reason="migration test")
        configured.ui_state.set_language(42, "vi")
        reopened = open_control_plane_stores(
            database_url="postgresql://fixture",
            data_root=data_root,
            jobs_root=jobs_root,
            admin_ids=[42],
            connect=self.connect,
            dialect="sqlite",
        )

        self.assertEqual({}, reopened.migration)
        self.assertIsNone(reopened.access.identity(99))
        self.assertEqual("vi", reopened.ui_state.language(42))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from wukong.adapters import LocalSourceAdapter, RcloneStorageAdapter, SourceIntegrityError
from wukong.cloud_sync import CloudJobSync
from wukong.cli import main as cli_main
from wukong.content_packs import ContentPackManager, build_content_index, upload_content_packs
from wukong.github import GitHubActionsAdapter, GitHubApiError
from wukong.models import BuildRecipe, Identity, JobStatus, RecipeValidationError
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore, OrchestrationError
from wukong.routing import RunnerInventory, RunnerRouter, RunnerUnavailableError
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import TelegramBotController
from wukong.security import validate_recipe_access


class BuildRecipeContractTests(unittest.TestCase):
    def test_recipe_round_trip_is_canonical_and_secret_free(self) -> None:
        payload = {
            "schemaVersion": 1,
            "task": "build",
            "device": "CPH2725",
            "source": {
                "kind": "https",
                "uri": "https://downloads.example/rom.zip",
                "sha256": "a" * 64,
                "sizeBytes": 2_000_000_000,
            },
            "build": {
                "preset": "custom",
                "mods": ["Gallery_mod", "Gapps"],
                "modVersion": "ColorOS_16.0.8",
                "package": True,
            },
            "execution": {"target": "github-auto"},
            "storage": {"remote": "wukong-gdrive", "publishArtifact": True},
        }

        recipe = BuildRecipe.from_dict(payload)
        serialized = recipe.to_dict()

        self.assertEqual(serialized, BuildRecipe.from_dict(serialized).to_dict())
        self.assertEqual(recipe.digest, hashlib.sha256(recipe.canonical_json.encode()).hexdigest())
        self.assertNotIn("token", recipe.canonical_json.casefold())
        self.assertEqual(recipe.to_legacy_spec()["romPath"], "https://downloads.example/rom.zip")
        self.assertEqual(recipe.to_legacy_spec()["modNames"], ["Gallery_mod", "Gapps"])

    def test_recipe_rejects_secrets_and_unsafe_remote_paths(self) -> None:
        base = {
            "schemaVersion": 1,
            "task": "source_mirror",
            "device": "CPH2725",
            "source": {"kind": "rclone", "uri": "wukong-gdrive:WukongROM/sources/rom.zip"},
        }
        with self.assertRaisesRegex(RecipeValidationError, "secret"):
            BuildRecipe.from_dict({**base, "accessToken": "do-not-store"})
        with self.assertRaisesRegex(RecipeValidationError, "traversal"):
            BuildRecipe.from_dict(
                {**base, "source": {"kind": "rclone", "uri": "wukong-gdrive:../secret"}}
            )

    def test_recipe_rejects_private_network_http_sources(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "private network"):
            BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "CPH2725",
                    "source": {"kind": "http", "uri": "http://127.0.0.1/rom.zip"},
                }
            )

    def test_recipe_rejects_path_unsafe_mod_names(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "path-safe"):
            BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "CPH2725",
                    "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                    "build": {"modVersion": "../secret"},
                }
            )

    def test_recipe_rejects_string_booleans(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "JSON boolean"):
            BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "CPH2725",
                    "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                    "storage": {"publishArtifact": "false"},
                }
            )

    def test_identity_is_supplied_outside_recipe(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "schemaVersion": 1,
                "task": "artifact_publish",
                "device": "CPH2725",
                "source": {"kind": "local", "uri": "C:/ROM/output.zip"},
                "requester": "admin",
            }
        )
        self.assertNotIn("requester", recipe.to_dict())
        self.assertEqual(Identity(channel="telegram", subject="42", role="user").subject, "42")


class RunnerRoutingContractTests(unittest.TestCase):
    def test_small_github_job_routes_to_pinned_hosted_runner(self) -> None:
        router = RunnerRouter()
        decision = router.choose(
            target="github-auto",
            estimated_workspace_bytes=9 * 1024**3,
            inventory=RunnerInventory(self_hosted_online=False),
        )
        self.assertEqual(decision.runner, "ubuntu-24.04")
        self.assertEqual(decision.kind, "github-hosted")

    def test_large_job_routes_to_qualified_self_hosted_runner(self) -> None:
        router = RunnerRouter()
        decision = router.choose(
            target="github-auto",
            estimated_workspace_bytes=20 * 1024**3,
            inventory=RunnerInventory(
                self_hosted_online=True,
                free_disk_bytes=180 * 1024**3,
                memory_bytes=32 * 1024**3,
                logical_cpus=12,
            ),
        )
        self.assertEqual(decision.labels, ("self-hosted", "linux", "x64", "wukong-rom"))

    def test_large_job_fails_fast_when_runner_is_offline(self) -> None:
        with self.assertRaisesRegex(RunnerUnavailableError, "offline"):
            RunnerRouter().choose(
                target="github-auto",
                estimated_workspace_bytes=20 * 1024**3,
                inventory=RunnerInventory(self_hosted_online=False),
            )

    def test_explicit_hosted_large_job_routes_to_self_hosted(self) -> None:
        decision = RunnerRouter().choose(
            target="github-hosted",
            estimated_workspace_bytes=20 * 1024**3,
            inventory=RunnerInventory(
                self_hosted_online=True,
                free_disk_bytes=180 * 1024**3,
                memory_bytes=32 * 1024**3,
                logical_cpus=12,
            ),
        )
        self.assertEqual(decision.kind, "self-hosted")

    def test_job_status_uses_hybrid_contract_names(self) -> None:
        self.assertEqual(JobStatus.SUCCEEDED.value, "succeeded")


class SourceAndStorageContractTests(unittest.TestCase):
    def test_local_source_is_copied_and_checksum_verified(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "rom.zip")
            source.write_bytes(b"known-rom")
            expected = "726e96014500c12d3f91501c159da58b7e8a626677584b1d7666fe261aff9066"
            target = Path(root, "workspace", "rom.zip")

            result = LocalSourceAdapter().materialize(source.as_posix(), target, expected)

            self.assertEqual(result.sha256, expected)
            self.assertEqual(target.read_bytes(), b"known-rom")

    def test_local_source_removes_bad_download_on_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "rom.zip")
            source.write_bytes(b"tampered")
            target = Path(root, "workspace", "rom.zip")
            with self.assertRaises(SourceIntegrityError):
                LocalSourceAdapter().materialize(source.as_posix(), target, "0" * 64)
            self.assertFalse(target.exists())

    def test_rclone_publish_writes_metadata_and_returns_public_link(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "artifact.zip")
            artifact.write_bytes(b"artifact")
            calls: list[list[str]] = []

            def fake_run(args: list[str], **_: object) -> str:
                calls.append(args)
                return "https://drive.example/public\n" if args[1] == "link" else ""

            storage = RcloneStorageAdapter(remote="wukong-gdrive", run_command=fake_run)
            record = storage.publish_artifact(artifact, device="CPH2725", build="V4.1")

            self.assertEqual(record.public_url, "https://drive.example/public")
            self.assertTrue(any(command[1] == "copyto" for command in calls))
            self.assertTrue(any(command[1] == "link" for command in calls))
            metadata = json.loads(Path(root, "artifact.zip.metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["sha256"], record.sha256)
            self.assertEqual(metadata["sizeBytes"], 8)

    def test_source_mirror_uploads_sha256_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom-source")
            copied: dict[str, bytes] = {}

            def fake_run(args: list[str], **_: object) -> str:
                if args[1] == "copyto":
                    copied[args[3]] = Path(args[2]).read_bytes()
                return ""

            record = RcloneStorageAdapter(run_command=fake_run).store_source(
                source,
                device="CPH2725",
            )
            metadata_uri = record.uri + ".metadata.json"
            self.assertIn(metadata_uri, copied)
            metadata = json.loads(copied[metadata_uri])
            self.assertEqual(metadata["sha256"], record.sha256)
            self.assertEqual(metadata["sizeBytes"], len(b"rom-source"))


class OrchestratorContractTests(unittest.TestCase):
    def _recipe(self, root: str, *, target: str = "local-windows") -> BuildRecipe:
        source = Path(root, "source.zip")
        source.write_bytes(b"rom")
        return BuildRecipe.from_dict(
            {
                "schemaVersion": 1,
                "task": "build",
                "device": "CPH2725",
                "source": {"kind": "local", "uri": source.as_posix(), "sizeBytes": 1},
                "execution": {"target": target, "estimatedWorkspaceBytes": 1024},
            }
        )

    def test_submit_and_inspect_are_owner_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "jobs"))
            owner = Identity("telegram", "100", "user")
            stranger = Identity("telegram", "200", "user")

            job = orchestrator.submit(self._recipe(root), owner)

            self.assertEqual(job.status, JobStatus.QUEUED)
            self.assertEqual(orchestrator.inspect(job.job_id, owner).job_id, job.job_id)
            with self.assertRaisesRegex(OrchestrationError, "not found"):
                orchestrator.inspect(job.job_id, stranger)

    def test_admin_can_cancel_any_job_and_user_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
            )
            owner = Identity("telegram", "100", "user")
            job = orchestrator.submit(self._recipe(root), owner)
            with self.assertRaisesRegex(OrchestrationError, "not found"):
                orchestrator.cancel(job.job_id, Identity("telegram", "200", "user"))
            cancelled = orchestrator.cancel(job.job_id, Identity("telegram", "1", "admin"))
            self.assertEqual(cancelled.status, JobStatus.CANCELLED)

    def test_resume_creates_new_job_with_checkpoint_reference(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
            )
            owner = Identity("windows", "local", "user")
            job = orchestrator.submit(self._recipe(root), owner)
            orchestrator.store.update(job.job_id, status=JobStatus.FAILED, checkpoint="stage://repack")

            resumed = orchestrator.resume(job.job_id, owner)

            self.assertNotEqual(resumed.job_id, job.job_id)
            self.assertEqual(resumed.checkpoint, "stage://repack")

    def test_expired_checkpoint_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
            )
            owner = Identity("windows", "local", "user")
            job = orchestrator.submit(self._recipe(root), owner)
            expired = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            orchestrator.store.update(
                job.job_id,
                status=JobStatus.FAILED,
                checkpoint="stage://repack",
                checkpoint_at=expired,
            )
            with self.assertRaisesRegex(OrchestrationError, "expired"):
                orchestrator.resume(job.job_id, owner)

    def test_telegram_user_cannot_submit_arbitrary_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(),
                workspace_root=Path(root, "jobs"),
                access_validator=validate_recipe_access,
            )
            with self.assertRaisesRegex(RecipeValidationError, "Telegram users"):
                orchestrator.submit(self._recipe(root), Identity("telegram", "100", "user"))


class CloudSyncContractTests(unittest.TestCase):
    def test_pull_imports_remote_events_once(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "workspace"))
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "CPH2725",
                    "source": {"kind": "local", "uri": str(source)},
                    "execution": {"target": "local-windows"},
                }
            )
            job = orchestrator.submit(recipe, Identity("windows", "local", "admin"))
            remote_manifest = job.to_dict() | {"status": "running", "stage": "repack", "progress": 0.5}
            remote_events = [{"sequence": 5, "jobId": job.job_id, "timestamp": "now", "type": "state", "stage": "repack"}]

            def fake_run(args: list[str], **_: object) -> str:
                destination = Path(args[3])
                if args[2].endswith("manifest.json"):
                    destination.write_text(json.dumps(remote_manifest), encoding="utf-8")
                else:
                    destination.write_text("\n".join(json.dumps(item) for item in remote_events), encoding="utf-8")
                return ""

            sync = CloudJobSync(store, RcloneStorageAdapter(run_command=fake_run))
            self.assertEqual(sync.pull(job.job_id).stage, "repack")
            sync.pull(job.job_id)
            imported = [event for event in store.events(job.job_id) if event.payload.get("remoteSequence") == 5]
            self.assertEqual(len(imported), 1)


class ControlAdapterContractTests(unittest.TestCase):
    def test_cli_validate_returns_same_recipe_digest_and_runner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recipe_path = Path(root, "recipe.json")
            recipe_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "task": "source_mirror",
                        "device": "CPH2725",
                        "source": {
                            "kind": "https",
                            "uri": "https://downloads.example/rom.zip",
                            "sizeBytes": 100,
                        },
                        "execution": {"target": "github-auto"},
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                status = cli_main(["validate", "--recipe", str(recipe_path)])

            result = json.loads(output.getvalue())
            recipe = BuildRecipe.from_dict(json.loads(recipe_path.read_text(encoding="utf-8")))
            self.assertEqual(status, 0)
            self.assertEqual(result["recipeDigest"], recipe.digest)
            self.assertEqual(result["runner"]["runner"], "ubuntu-24.04")

    def test_github_dispatch_uses_recipe_ref_and_never_serializes_token(self) -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, url: str, payload: dict[str, object] | None = None) -> object:
            requests.append((method, url, payload))
            return {}

        adapter = GitHubActionsAdapter(
            owner="luukhanh24",
            repository="Wukong-ROM-Studio-Hybrid",
            token="secret-token",
            transport=transport,
        )
        adapter.dispatch("wukong-build.yml", recipe_ref="wukong-gdrive:WukongROM/recipes/abc.json")

        serialized = json.dumps(requests)
        self.assertNotIn("secret-token", serialized)
        self.assertEqual(requests[0][2]["inputs"]["recipe_ref"], "wukong-gdrive:WukongROM/recipes/abc.json")

    def test_github_runner_inventory_requires_qualified_online_runner(self) -> None:
        def transport(method: str, url: str, payload: dict[str, object] | None = None) -> object:
            return {
                "runners": [
                    {"status": "online", "busy": False, "labels": [{"name": value} for value in ["self-hosted", "linux", "x64", "wukong-rom"]]}
                ]
            }

        inventory = GitHubActionsAdapter("owner", "repo", "token", transport=transport).runner_inventory()
        self.assertTrue(inventory.self_hosted_online)

    def test_github_api_error_redacts_token(self) -> None:
        adapter = GitHubActionsAdapter(
            "owner",
            "repo",
            "top-secret",
            transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("top-secret failed")),
        )
        with self.assertRaisesRegex(GitHubApiError, "redacted"):
            adapter.cancel(123)

    def test_cloud_recipe_fetch_is_limited_to_private_recipe_root(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                [
                    os.sys.executable,
                    "tools/fetch_recipe.py",
                    "wukong-gdrive:WukongROM/sources/recipe.json",
                    "--output",
                    str(Path(root, "recipe.json")),
                ],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WukongROM/recipes", result.stderr)

    def test_workflow_recipe_is_forced_to_github_auto(self) -> None:
        repository = Path(__file__).resolve().parent.parent
        scratch = repository / ".tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as root:
            recipe_path = Path(root, "local.json")
            output = Path(root, "out.json")
            recipe_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "task": "source_mirror",
                        "device": "CPH2725",
                        "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                        "execution": {"target": "local-windows"},
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    os.sys.executable,
                    "tools/fetch_recipe.py",
                    recipe_path.relative_to(repository).as_posix(),
                    "--output",
                    str(output),
                    "--force-github-auto",
                ],
                cwd=repository,
                check=True,
            )
            self.assertEqual(json.loads(output.read_text())["execution"]["target"], "github-auto")


class TelegramAccessContractTests(unittest.TestCase):
    def test_admin_approval_and_revocation_persist_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "telegram-access.json")
            access = TelegramAccessStore(path, admin_ids={1})
            self.assertEqual(access.identity(1).role, "admin")
            self.assertIsNone(access.identity(42))

            access.approve(42, actor=access.identity(1))
            self.assertEqual(TelegramAccessStore(path, admin_ids={1}).identity(42).role, "user")
            access.revoke(42, actor=access.identity(1))
            self.assertIsNone(access.identity(42))
            self.assertNotIn("token", path.read_text(encoding="utf-8").casefold())

    def test_non_admin_cannot_manage_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            access = TelegramAccessStore(Path(root, "access.json"), admin_ids={1})
            with self.assertRaisesRegex(PermissionError, "Admin"):
                access.approve(42, actor=Identity("telegram", "2", "user"))

    def test_bot_lists_only_requesting_users_jobs_and_cloud_library(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            access = TelegramAccessStore(Path(root, "access.json"), admin_ids={1})
            access.approve(42, actor=access.identity(1))
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(
                store=store,
                workspace_root=Path(root, "jobs"),
                access_validator=lambda _recipe, _identity: None,
            )
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {"schemaVersion": 1, "task": "source_mirror", "device": "CPH2725", "source": {"kind": "local", "uri": str(source)}, "execution": {"target": "local-windows"}}
            )
            own = orchestrator.submit(recipe, Identity("telegram", "42", "user"))
            other = orchestrator.submit(recipe, Identity("telegram", "99", "user"))
            controller = TelegramBotController(
                access=access,
                orchestrator=orchestrator,
                catalog_provider=lambda: {},
                diagnostics_provider=lambda: {},
                cloud_provider=lambda category: {"category": category, "entries": ["ok"]},
            )
            jobs = controller.handle(42, "/jobs")
            self.assertIn(own.job_id, jobs)
            self.assertNotIn(other.job_id, jobs)
            self.assertIn('"category": "sources"', controller.handle(42, "/cloud sources"))

    def test_regular_user_cannot_clear_shared_cache(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            access = TelegramAccessStore(Path(root, "access.json"), admin_ids={1})
            access.approve(42, actor=access.identity(1))
            controller = TelegramBotController(
                access=access,
                orchestrator=HybridOrchestrator(
                    store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
                ),
                catalog_provider=lambda: {},
                diagnostics_provider=lambda: {},
                cache_clearer=lambda: {"cleared": True},
            )
            self.assertIn("Admin access", controller.handle(42, "/cache_clear"))


class ContentPackContractTests(unittest.TestCase):
    def test_content_index_groups_mod_versions_and_hashes_every_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.8" / "Gallery").mkdir(parents=True)
            (content / "MOD" / "ColorOS_16.0.8" / "Gallery" / "app.apk").write_bytes(b"apk")
            (content / "TWRP").mkdir()
            (content / "TWRP" / "recovery.img").write_bytes(b"img")

            index = build_content_index(content, remote="wukong-gdrive:WukongROM/content-packs")

            self.assertEqual([pack["id"] for pack in index["packs"]], ["MOD/ColorOS_16.0.8", "TWRP/v1"])
            self.assertEqual(index["packs"][0]["files"][0]["sha256"], "dd37c2d7274f7ea982cb83390c36918fee9ce8889073c44b68cdc00bdb8c3e04")

    def test_install_downloads_to_staging_and_rejects_tampered_pack(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "Content")
            index = {
                "schemaVersion": 1,
                "packs": [
                    {
                        "id": "TWRP/v1",
                        "target": "TWRP",
                        "remote": "wukong-gdrive:WukongROM/content-packs/TWRP/v1",
                        "sizeBytes": 3,
                        "files": [
                            {
                                "path": "recovery.img",
                                "sizeBytes": 3,
                                "sha256": "b99b21156d9c07e16d0e5d6704601c8fda0f74bb2bfc4e919e36a52d1f2d3aa4",
                            }
                        ],
                    }
                ],
            }

            def fake_run(args: list[str], **_: object) -> str:
                destination = Path(args[3])
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "recovery.img").write_bytes(b"bad")
                return ""

            manager = ContentPackManager(target, run_command=fake_run)
            with self.assertRaisesRegex(SourceIntegrityError, "content-pack"):
                manager.install(index, "TWRP/v1")
            self.assertFalse((target / "TWRP" / "recovery.img").exists())

    def test_upload_downloads_each_pack_and_verifies_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "TWRP").mkdir(parents=True)
            (content / "TWRP" / "recovery.img").write_bytes(b"img")
            index = build_content_index(content, remote="wukong-gdrive:WukongROM/content-packs")

            def fake_run(args: list[str], **_: object) -> str:
                if args[1] == "copy" and args[2].startswith("wukong-gdrive:"):
                    destination = Path(args[3])
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "recovery.img").write_bytes(b"img")
                return ""

            upload_content_packs(content, index, run_command=fake_run)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import studio_server
from wukong.adapters import MaterializedSource, sha256_file
from wukong.cli import main as cli_main
from wukong.content_packs import build_content_index
from wukong.executor import (
    CHECKPOINT_STAGES,
    DEFAULT_CLOUD_CHECKPOINT_STAGES,
    LocalJobExecutor,
    checkpoint_stages_for_environment,
    source_target_for,
)
from wukong.models import ArtifactRecord, BuildRecipe, Identity, JobStatus
from wukong.orchestrator import FileJobStore, HybridOrchestrator, InMemoryJobStore, JobStore
from wukong.routing import RunnerInventory
from wukong.security import validate_recipe_access
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import TelegramBotController


class _FixtureSourceAdapter:
    def __init__(self, fixture: Path) -> None:
        self.fixture = fixture

    def materialize(self, _uri: str, target: Path, expected_sha256: str | None) -> MaterializedSource:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.fixture.read_bytes())
        digest = sha256_file(target)
        if expected_sha256 and expected_sha256 != digest:
            raise AssertionError("fixture checksum mismatch")
        return MaterializedSource(target, digest, target.stat().st_size)


class _FixtureStorage:
    def publish_artifact(self, artifact: Path, *, device: str, build: str) -> ArtifactRecord:
        return ArtifactRecord(
            name=artifact.name,
            uri=f"wukong-gdrive:WukongROM/artifacts/{device}/{build}/{artifact.name}",
            sha256=sha256_file(artifact),
            size_bytes=artifact.stat().st_size,
            public_url=f"https://drive.google.com/fixture/{artifact.name}",
        )


class HybridChannelParityContractTests(unittest.TestCase):
    def test_daniel_build_page_materializes_to_zip_filename(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "task": "build",
                "device": "PKG110",
                "source": {
                    "kind": "https",
                    "uri": "https://roms.danielspringer.at/index.php?view=ota&build=fixture",
                },
            }
        )

        target = source_target_for(recipe, Path("workspace") / "job")

        self.assertEqual("index.zip", target.name)

    def test_executor_rejects_source_size_mismatch_before_upload_or_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.zip"
            source.write_bytes(b"short-rom")
            recipe = BuildRecipe.from_dict(
                {
                    "task": "source_mirror",
                    "device": "PKG110",
                    "source": {"kind": "local", "uri": str(source), "sizeBytes": 999},
                    "execution": {"target": "local-windows"},
                }
            )
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=root / "jobs")
            job = orchestrator.submit(recipe, Identity("windows", "owner", "admin"))

            with patch("wukong.executor.source_adapter_for", return_value=_FixtureSourceAdapter(source)):
                result = LocalJobExecutor(store=store, workspace_root=root / "jobs").execute(job.job_id)

        self.assertEqual(JobStatus.FAILED, result.status)
        self.assertIn("ROM size mismatch", result.error or "")

    def test_checkpoint_policy_skips_read_only_and_terminal_stages(self) -> None:
        self.assertNotIn("inspect_rom", CHECKPOINT_STAGES)
        self.assertNotIn("package_zip", CHECKPOINT_STAGES)
        self.assertNotIn("notify_telegram", CHECKPOINT_STAGES)
        self.assertIn("extract_payload", CHECKPOINT_STAGES)
        self.assertIn("unpack_partitions", CHECKPOINT_STAGES)
        self.assertIn("repack_partitions", CHECKPOINT_STAGES)
        self.assertIn("patch_vendor_boot", CHECKPOINT_STAGES)

    def test_actions_checkpoint_policy_keeps_only_high_value_extract_snapshot(self) -> None:
        self.assertEqual({"extract_payload"}, DEFAULT_CLOUD_CHECKPOINT_STAGES)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False):
            self.assertEqual({"extract_payload"}, checkpoint_stages_for_environment())
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}, clear=False):
            self.assertEqual(CHECKPOINT_STAGES, checkpoint_stages_for_environment())

    def test_actions_checkpoint_failure_does_not_stop_or_repeat_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rom = root / "source.zip"
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=checkpoint-fixture\n",
                )
                archive.writestr("payload.bin", b"fixture")
            content_root = root / "content"
            packs = []
            for pack_id, target in (
                ("MOD/ColorOS_16.0.8", "MOD/ColorOS_16.0.8"),
                ("STARK/common", "STARK"),
                ("Flash_script/common", "Flash_script"),
                ("copy-image/v1", "copy-image"),
                ("OFX/v1", "OFX"),
                ("TWRP/v1", "TWRP"),
            ):
                directory = content_root / target
                directory.mkdir(parents=True)
                fixture = directory / "fixture.txt"
                fixture.write_text("fixture\n", encoding="utf-8")
                packs.append(
                    {
                        "id": pack_id,
                        "target": target,
                        "remote": f"wukong-gdrive:WukongROM/content-packs/{pack_id}",
                        "fileCount": 1,
                        "sizeBytes": fixture.stat().st_size,
                        "files": [{"path": fixture.name, "sha256": sha256_file(fixture), "sizeBytes": fixture.stat().st_size}],
                    }
                )
            content_index = root / "content-index.json"
            content_index.write_text(json.dumps({"schemaVersion": 1, "packs": packs}), encoding="utf-8")
            recipe = BuildRecipe.from_dict(
                {
                    "task": "build",
                    "device": "PKG110",
                    "source": {"kind": "local", "uri": str(rom), "sha256": sha256_file(rom)},
                    "build": {"preset": "custom", "modVersion": "ColorOS_16.0.8"},
                    "execution": {"target": "local-windows"},
                    "storage": {"publishArtifact": False},
                }
            )
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=root / "jobs")
            manifest = orchestrator.submit(recipe, Identity("actions", "100", "user"), job_id="checkpoint-warning")

            class FailingCheckpointStorage(_FixtureStorage):
                attempts = 0

                def sync_tree(self, _source: Path, _relative: str) -> str:
                    self.attempts += 1
                    raise OSError("Drive quota exceeded")

            storage = FailingCheckpointStorage()

            def legacy_build(_job_id, _spec, workspace, callback):
                workspace.mkdir(parents=True, exist_ok=True)
                callback({"type": "step", "step": "extract_payload", "status": "success"})
                callback({"type": "step", "step": "unpack_partitions", "status": "success"})
                output = workspace / "artifact.zip"
                output.write_bytes(b"artifact")
                return {"outputZip": str(output)}

            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), patch(
                "wukong.executor.source_adapter_for", return_value=_FixtureSourceAdapter(rom)
            ):
                completed = LocalJobExecutor(
                    store=store,
                    workspace_root=root / "jobs",
                    build_workspace_root=root / "build",
                    content_root=content_root,
                    content_index=content_index,
                    storage_factory=lambda _remote: storage,
                    legacy_build=legacy_build,
                ).execute(manifest.job_id)

            self.assertEqual(completed.status, JobStatus.SUCCEEDED, completed.error)
            self.assertEqual(storage.attempts, 1)
            warnings = [event for event in store.events(manifest.job_id) if event.type == "warning"]
            self.assertTrue(any("remaining checkpoints are disabled" in event.payload["warning"] for event in warnings))

    def test_failed_checkpoint_restore_continues_with_clean_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rom = root / "source.zip"
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=resume-fixture\n",
                )
                archive.writestr("payload.bin", b"fixture")
            content_root = root / "content"
            packs = []
            for pack_id, target in (
                ("MOD/ColorOS_16.0.8", "MOD/ColorOS_16.0.8"),
                ("STARK/common", "STARK"),
                ("Flash_script/common", "Flash_script"),
                ("copy-image/v1", "copy-image"),
                ("OFX/v1", "OFX"),
                ("TWRP/v1", "TWRP"),
            ):
                directory = content_root / target
                directory.mkdir(parents=True)
                fixture = directory / "fixture.txt"
                fixture.write_text("fixture\n", encoding="utf-8")
                packs.append(
                    {
                        "id": pack_id,
                        "target": target,
                        "remote": f"wukong-gdrive:WukongROM/content-packs/{pack_id}",
                        "fileCount": 1,
                        "sizeBytes": fixture.stat().st_size,
                        "files": [
                            {
                                "path": fixture.name,
                                "sha256": sha256_file(fixture),
                                "sizeBytes": fixture.stat().st_size,
                            }
                        ],
                    }
                )
            content_index = root / "content-index.json"
            content_index.write_text(json.dumps({"schemaVersion": 1, "packs": packs}), encoding="utf-8")
            recipe = BuildRecipe.from_dict(
                {
                    "task": "build",
                    "device": "PKG110",
                    "source": {"kind": "local", "uri": str(rom), "sha256": sha256_file(rom)},
                    "build": {"preset": "custom", "modVersion": "ColorOS_16.0.8"},
                    "execution": {"target": "local-windows"},
                    "storage": {"publishArtifact": False},
                }
            )
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=root / "jobs")
            manifest = orchestrator.submit(recipe, Identity("actions", "100", "user"), job_id="resume-soft")
            store.update(
                manifest.job_id,
                checkpoint="wukong-gdrive:WukongROM/checkpoints/resume-soft/extract_payload/dead.tar",
                checkpoint_at="2026-08-13T14:58:57.313337Z",
            )

            class FailingRestoreStorage(_FixtureStorage):
                def restore_tree(self, _uri: str, _destination: Path) -> Path:
                    raise OSError("quota exceeded while restoring checkpoint")

            seen_presets: list[str] = []

            def legacy_build(_job_id, spec, workspace, callback):
                seen_presets.append(str(spec.get("preset")))
                workspace.mkdir(parents=True, exist_ok=True)
                callback({"type": "step", "step": "extract_payload", "status": "success"})
                output = workspace / "artifact.zip"
                output.write_bytes(b"artifact")
                return {"outputZip": str(output)}

            with patch("wukong.executor.source_adapter_for", return_value=_FixtureSourceAdapter(rom)):
                completed = LocalJobExecutor(
                    store=store,
                    workspace_root=root / "jobs",
                    build_workspace_root=root / "build",
                    content_root=content_root,
                    content_index=content_index,
                    storage_factory=lambda _remote: FailingRestoreStorage(),
                    legacy_build=legacy_build,
                ).execute(manifest.job_id)

            self.assertEqual(completed.status, JobStatus.SUCCEEDED, completed.error)
            self.assertEqual(seen_presets, ["custom"])
            # Cloud checkpoint is discarded on restore failure; a later local
            # checkpoint from a successful stage is allowed.
            final = store.get(manifest.job_id)
            self.assertIsNotNone(final)
            assert final is not None
            if final.checkpoint:
                self.assertTrue(str(final.checkpoint).startswith("local:"))
            warnings = [event for event in store.events(manifest.job_id) if event.type == "warning"]
            self.assertTrue(any("Checkpoint restore failed" in event.payload["warning"] for event in warnings))

    def test_local_build_without_cloud_publish_records_artifact_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rom = root / "source.zip"
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=local-fixture\n",
                )
                archive.writestr("payload.bin", b"fixture")
            content_root = root / "content"
            packs = []
            for pack_id, target in (
                ("MOD/ColorOS_16.0.8", "MOD/ColorOS_16.0.8"),
                ("STARK/common", "STARK"),
                ("Flash_script/common", "Flash_script"),
                ("copy-image/v1", "copy-image"),
                ("OFX/v1", "OFX"),
                ("TWRP/v1", "TWRP"),
            ):
                directory = content_root / target
                directory.mkdir(parents=True)
                fixture = directory / "fixture.txt"
                fixture.write_text("fixture\n", encoding="utf-8")
                packs.append(
                    {
                        "id": pack_id,
                        "target": target,
                        "remote": f"wukong-gdrive:WukongROM/content-packs/{pack_id}",
                        "fileCount": 1,
                        "sizeBytes": fixture.stat().st_size,
                        "files": [
                            {
                                "path": fixture.name,
                                "sha256": sha256_file(fixture),
                                "sizeBytes": fixture.stat().st_size,
                            }
                        ],
                    }
                )
            content_index = root / "content-index.json"
            content_index.write_text(
                json.dumps({"schemaVersion": 1, "packs": packs}),
                encoding="utf-8",
            )
            recipe = BuildRecipe.from_dict(
                {
                    "task": "build",
                    "device": "PKG110",
                    "source": {"kind": "local", "uri": str(rom), "sha256": sha256_file(rom)},
                    "build": {"preset": "custom", "modVersion": "ColorOS_16.0.8"},
                    "execution": {"target": "local-windows"},
                    "storage": {"publishArtifact": False},
                }
            )
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=root / "jobs")
            manifest = orchestrator.submit(recipe, Identity("windows", "local", "admin"), job_id="local-no-cloud")

            def legacy_build(_job_id, _spec, workspace, _callback):
                workspace.mkdir(parents=True, exist_ok=True)
                output = workspace / "local-artifact.zip"
                output.write_bytes(b"artifact")
                return {"outputZip": str(output)}

            completed = LocalJobExecutor(
                store=store,
                workspace_root=root / "jobs",
                build_workspace_root=root / "build",
                content_root=content_root,
                content_index=content_index,
                legacy_build=legacy_build,
            ).execute(manifest.job_id)

            self.assertEqual(completed.status, JobStatus.SUCCEEDED, completed.error)
            self.assertEqual(completed.artifacts[0].sha256, sha256_file(Path(completed.artifacts[0].uri)))

    @staticmethod
    def _cli_json(arguments: list[str]) -> dict[str, object]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = cli_main(arguments)
        if result != 0:
            raise AssertionError(output.getvalue())
        return json.loads(output.getvalue())

    def test_same_recipe_has_equivalent_plan_status_and_artifact_for_every_channel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rom = root / "source.zip"
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=parity-fixture\n",
                )
                archive.writestr("payload.bin", b"fixture")
            digest = sha256_file(rom)
            content_root = root / "content"
            for target in (
                content_root / "MOD" / "ColorOS_16.0.8",
                content_root / "STARK",
                content_root / "Flash_script",
                content_root / "copy-image",
                content_root / "OFX",
                content_root / "TWRP",
            ):
                target.mkdir(parents=True)
                (target / "fixture.txt").write_text("fixture\n", encoding="utf-8")
            content_index = root / "content-index.json"
            content_index.write_text(
                json.dumps(
                    build_content_index(
                        content_root,
                        remote="wukong-gdrive:WukongROM/content-packs/parity/v1",
                    )
                ),
                encoding="utf-8",
            )
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "PKG110",
                    "source": {
                        "kind": "https",
                        "uri": "https://downloads.example/parity.zip",
                        "sha256": digest,
                        "sizeBytes": rom.stat().st_size,
                    },
                    "build": {
                        "preset": "custom",
                        "mods": [],
                        "modVersion": "ColorOS_16.0.8",
                        "enabledSteps": ["inspect_rom", "extract_payload", "package_zip"],
                    },
                    "execution": {
                        "target": "github-auto",
                        "estimatedWorkspaceBytes": 9 * 1024**3,
                    },
                    "storage": {"remote": "wukong-gdrive", "publishArtifact": True},
                }
            )
            recipe_path = root / "recipe.json"
            recipe_path.write_text(json.dumps(recipe.to_dict()), encoding="utf-8")

            def legacy_build(job_id, spec, workspace, callback):
                workspace.mkdir(parents=True, exist_ok=True)
                for index, step in enumerate(spec["enabledSteps"], start=1):
                    callback({"type": "build", "step": step, "status": "success", "progress": index * 20})
                output = workspace / "Wukong_parity-fixture.zip"
                with zipfile.ZipFile(output, "w") as archive:
                    entry = zipfile.ZipInfo("parity.txt", date_time=(2024, 1, 1, 0, 0, 0))
                    entry.external_attr = 0o100644 << 16
                    archive.writestr(entry, "same pipeline\n")
                return {"outputZip": str(output)}

            channels: list[tuple[str, JobStore, str, Callable[[str], dict[str, object]]]] = []

            windows_jobs = root / "windows-jobs"
            windows_runtime = root / "windows-runtime"
            windows_store = FileJobStore(windows_jobs / "hybrid")
            with patch.object(studio_server, "JOBS_DIR", windows_jobs), patch.object(
                studio_server, "RUNTIME_DIR", windows_runtime
            ), patch.object(studio_server, "DATABASE_PATH", windows_runtime / "studio.db"), patch.object(
                studio_server, "FileJobStore", return_value=windows_store
            ):
                windows_app = studio_server.create_app(start_queue=False)
                windows_client = windows_app.test_client()
                headers = {"X-Studio-Token": studio_server.SESSION_TOKEN}
                response = windows_client.post("/api/v1/jobs", headers=headers, json=recipe.to_dict())
                self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
                windows_job = response.get_json()["job_id"]

                def inspect_windows(job_id: str) -> dict[str, object]:
                    inspected = windows_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
                    self.assertEqual(inspected.status_code, 200, inspected.get_data(as_text=True))
                    return inspected.get_json()

                channels.append(
                    (
                        "windows",
                        windows_store,
                        windows_job,
                        inspect_windows,
                    )
                )

            for name, channel, subject, role in (
                ("cli", "cli", "local-user", "admin"),
                ("actions", "actions", "12345", "user"),
            ):
                jobs_root = root / f"{name}-jobs" / "hybrid"
                workspace_root = root / f"{name}-workspace"
                submitted = self._cli_json(
                    [
                        "--jobs-root", str(jobs_root), "--workspace-root", str(workspace_root),
                        "submit", "--recipe", str(recipe_path), "--job-id", f"parity-{name}",
                        "--channel", channel, "--subject", subject, "--role", role,
                    ]
                )
                inspect_arguments = [
                    "--jobs-root", str(jobs_root), "--workspace-root", str(workspace_root),
                    "inspect", submitted["job_id"], "--channel", channel,
                    "--subject", subject, "--role", role,
                ]
                channels.append(
                    (
                        name,
                        FileJobStore(jobs_root),
                        str(submitted["job_id"]),
                        lambda _job_id, args=inspect_arguments: self._cli_json(args),
                    )
                )

            telegram_store = InMemoryJobStore()
            telegram_orchestrator = HybridOrchestrator(
                store=telegram_store,
                workspace_root=root / "telegram-workspace",
                inventory_provider=lambda: RunnerInventory(False),
                access_validator=validate_recipe_access,
            )
            telegram_access = TelegramAccessStore(root / "telegram-access.json", admin_ids=["67890"])
            telegram = TelegramBotController(
                access=telegram_access,
                orchestrator=telegram_orchestrator,
                catalog_provider=lambda: {},
                diagnostics_provider=lambda: {},
            )
            submitted_message = telegram.handle("67890", f"/submit {recipe.canonical_json}")
            telegram_job = submitted_message.splitlines()[0].rsplit(" ", 1)[-1]
            channels.append(
                (
                    "telegram",
                    telegram_store,
                    telegram_job,
                    lambda job_id: json.loads(telegram.handle("67890", f"/job {job_id}")),
                )
            )

            observations: list[dict[str, object]] = []
            for index, (name, store, job_id, inspect_channel) in enumerate(channels):
                executor = LocalJobExecutor(
                    store=store,
                    workspace_root=root / f"executor-jobs-{index}",
                    build_workspace_root=root / f"build-{index}",
                    content_root=content_root,
                    content_index=content_index,
                    storage_factory=lambda _remote: _FixtureStorage(),
                    legacy_build=legacy_build,
                )
                with patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), patch(
                    "wukong.executor.source_adapter_for",
                    return_value=_FixtureSourceAdapter(rom),
                ):
                    executor.execute(job_id)
                completed_payload = inspect_channel(job_id)
                build_events = [
                    event.payload["step"]
                    for event in store.events(job_id)
                    if event.type == "build"
                ]
                observations.append(
                    {
                        "channel": name,
                        "digest": completed_payload["recipe_digest"],
                        "runner": completed_payload["runner"],
                        "status": completed_payload["status"],
                        "plan": build_events,
                        "artifact": [
                            (item["name"], item["sha256"], item["size_bytes"])
                            for item in completed_payload["artifacts"]
                        ],
                    }
                )

            baseline = {key: value for key, value in observations[0].items() if key != "channel"}
            self.assertEqual(baseline["status"], JobStatus.SUCCEEDED.value)
            self.assertEqual(
                baseline["plan"],
                ["inspect_rom", "extract_payload", "package_zip"],
            )
            for observation in observations[1:]:
                self.assertEqual(
                    {key: value for key, value in observation.items() if key != "channel"},
                    baseline,
                    observation["channel"],
                )


if __name__ == "__main__":
    unittest.main()

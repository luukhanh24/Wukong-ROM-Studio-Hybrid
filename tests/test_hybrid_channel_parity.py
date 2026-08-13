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
from wukong.executor import LocalJobExecutor
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

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from wukong.adapters import MaterializedSource, sha256_file
from wukong.content_packs import build_content_index
from wukong.executor import LocalJobExecutor
from wukong.models import ArtifactRecord, BuildRecipe, Identity, JobStatus
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore
from wukong.routing import RunnerInventory
from wukong.security import validate_recipe_access


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
            identities = (
                Identity("windows", "local-user", "admin"),
                Identity("cli", "local-user", "admin"),
                Identity("actions", "12345", "user"),
                Identity("telegram", "67890", "user"),
            )
            observations: list[dict[str, object]] = []

            def legacy_build(job_id, spec, workspace, callback):
                workspace.mkdir(parents=True, exist_ok=True)
                for index, step in enumerate(spec["enabledSteps"], start=1):
                    callback({"type": "build", "step": step, "status": "success", "progress": index * 20})
                output = workspace / "Wukong_parity-fixture.zip"
                with zipfile.ZipFile(output, "w") as archive:
                    archive.writestr("parity.txt", "same pipeline\n")
                return {"outputZip": str(output)}

            for index, identity in enumerate(identities):
                store = InMemoryJobStore()
                orchestrator = HybridOrchestrator(
                    store=store,
                    workspace_root=root / f"jobs-{index}",
                    inventory_provider=lambda: RunnerInventory(False),
                    access_validator=validate_recipe_access,
                )
                manifest = orchestrator.submit(recipe, identity, job_id=f"parity-{index}")
                executor = LocalJobExecutor(
                    store=store,
                    workspace_root=root / f"jobs-{index}",
                    build_workspace_root=root / f"build-{index}",
                    content_root=content_root,
                    content_index=content_index,
                    storage_factory=lambda _remote: _FixtureStorage(),
                    legacy_build=legacy_build,
                )
                with patch("wukong.executor.source_adapter_for", return_value=_FixtureSourceAdapter(rom)):
                    completed = executor.execute(manifest.job_id)
                build_events = [
                    event.payload["step"]
                    for event in store.events(manifest.job_id)
                    if event.type == "build"
                ]
                observations.append(
                    {
                        "digest": completed.recipe_digest,
                        "runner": completed.runner,
                        "status": completed.status,
                        "plan": build_events,
                        "artifact": [
                            (item.name, item.sha256, item.size_bytes)
                            for item in completed.artifacts
                        ],
                    }
                )

            baseline = observations[0]
            self.assertEqual(baseline["status"], JobStatus.SUCCEEDED)
            self.assertEqual(
                baseline["plan"],
                ["inspect_rom", "extract_payload", "package_zip"],
            )
            for observation in observations[1:]:
                self.assertEqual(observation, baseline)


if __name__ == "__main__":
    unittest.main()

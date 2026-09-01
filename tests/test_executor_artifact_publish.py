from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from wukong.artifact_mirror import ArtifactMirrorPublisher, DCloudMirrorConfig
from wukong.executor import LocalJobExecutor
from wukong.models import ArtifactRecord


class ExecutorArtifactPublishTests(unittest.TestCase):
    def test_failed_mirror_is_left_for_asynchronous_repair_after_primary_upload(self) -> None:
        order: list[str] = []
        mirror_attempts = 0

        class RecoveringMirrorStorage:
            def mirror_artifact(self, artifact: Path, **_: object) -> ArtifactRecord:
                nonlocal mirror_attempts
                mirror_attempts += 1
                order.append(f"mirror:{mirror_attempts}")
                if mirror_attempts == 1:
                    raise RuntimeError("temporary DC Cloud failure")
                return ArtifactRecord(
                    artifact.name,
                    f"cloudreve://my/WukongROM/ROM/{artifact.name}",
                    "a" * 64,
                    artifact.stat().st_size,
                )

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            store = Mock()
            publisher = ArtifactMirrorPublisher(
                DCloudMirrorConfig(True, share_url="https://cloud.example/share"),
                storage_factory=lambda _remote: RecoveringMirrorStorage(),
                retry_attempts=1,
                sleep=lambda _: None,
            )
            executor = LocalJobExecutor(
                store=store,
                workspace_root=Path(root, "jobs"),
                mirror_publisher=publisher,
            )

            def publish_primary() -> ArtifactRecord:
                order.append("primary")
                return ArtifactRecord(
                    artifact.name,
                    "wukong-gdrive:WukongROM/ROM/V6/rom.zip",
                    "a" * 64,
                    artifact.stat().st_size,
                    "https://drive.google.com/open?id=fixture",
                )

            record = executor._publish_artifact_with_mirror(
                "job",
                artifact,
                "PKG110",
                "V6",
                "ROM/V6",
                publish_primary,
            )

        self.assertEqual(["mirror:1", "primary"], order)
        self.assertEqual("wukong-gdrive:WukongROM/ROM/V6/rom.zip", record.uri)
        self.assertEqual("failed", record.mirrors[0].status)
        store.append_event.assert_called_once_with(
            "job",
            "mirror_upload_failed",
            provider="dccloud",
            warning="DC Cloud mirror upload failed; primary artifact upload will continue.",
            errorCode="upload_failed",
        )

    def test_dccloud_upload_runs_from_local_zip_before_primary_upload(self) -> None:
        order: list[str] = []

        class MirrorStorage:
            def mirror_artifact(self, artifact: Path, **_: object) -> ArtifactRecord:
                order.append(f"mirror:{artifact.name}")
                return ArtifactRecord(
                    artifact.name,
                    f"cloudreve://my/WukongROM/ROM/{artifact.name}",
                    "a" * 64,
                    artifact.stat().st_size,
                )

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            publisher = ArtifactMirrorPublisher(
                DCloudMirrorConfig(True, share_url="https://cloud.example/share"),
                storage_factory=lambda _remote: MirrorStorage(),
                retry_attempts=1,
            )
            executor = LocalJobExecutor(
                store=Mock(),
                workspace_root=Path(root, "jobs"),
                mirror_publisher=publisher,
            )

            def publish_primary() -> ArtifactRecord:
                order.append("primary")
                return ArtifactRecord(
                    artifact.name,
                    "wukong-gdrive:ROM/rom.zip",
                    "b" * 64,
                    artifact.stat().st_size,
                )

            record = executor._publish_artifact_with_mirror(
                "job",
                artifact,
                "PKG110",
                "V6",
                None,
                publish_primary,
            )

        self.assertEqual(["mirror:rom.zip", "primary"], order)
        self.assertEqual("wukong-gdrive:ROM/rom.zip", record.uri)
        self.assertEqual("cloudreve://my/WukongROM/ROM/rom.zip", record.mirrors[0].uri)

    def test_drive_failure_keeps_successful_dccloud_artifact(self) -> None:
        class MirrorStorage:
            def mirror_artifact(self, artifact: Path, **_: object) -> ArtifactRecord:
                return ArtifactRecord(
                    artifact.name,
                    f"cloudreve://my/WukongROM/ROM/{artifact.name}",
                    "a" * 64,
                    artifact.stat().st_size,
                )

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            store = Mock()
            publisher = ArtifactMirrorPublisher(
                DCloudMirrorConfig(True, share_url="https://cloud.example/share"),
                storage_factory=lambda _remote: MirrorStorage(),
                retry_attempts=1,
            )
            executor = LocalJobExecutor(
                store=store,
                workspace_root=Path(root, "jobs"),
                mirror_publisher=publisher,
            )

            def fail_drive() -> ArtifactRecord:
                raise RuntimeError("Drive quota exceeded")

            record = executor._publish_artifact_with_mirror(
                "job",
                artifact,
                "PKG110",
                "V6",
                None,
                fail_drive,
            )

        self.assertEqual("cloudreve://my/WukongROM/ROM/rom.zip", record.uri)
        self.assertEqual("https://cloud.example/share", record.public_url)
        self.assertEqual("available", record.mirrors[0].status)
        store.append_event.assert_any_call(
            "job",
            "primary_upload_failed",
            provider="gdrive",
            warning="Google Drive upload failed; the DC Cloud artifact remains available.",
            errorType="RuntimeError",
        )

    def test_primary_failure_still_fails_when_dccloud_is_unavailable(self) -> None:
        class BrokenMirrorStorage:
            def mirror_artifact(self, artifact: Path, **_: object) -> ArtifactRecord:
                raise RuntimeError(f"DC Cloud unavailable for {artifact.name}")

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            publisher = ArtifactMirrorPublisher(
                DCloudMirrorConfig(True, share_url="https://cloud.example/share"),
                storage_factory=lambda _remote: BrokenMirrorStorage(),
                retry_attempts=1,
            )
            executor = LocalJobExecutor(
                store=Mock(),
                workspace_root=Path(root, "jobs"),
                mirror_publisher=publisher,
            )

            def fail_drive() -> ArtifactRecord:
                raise RuntimeError("Drive quota exceeded")

            with self.assertRaisesRegex(RuntimeError, "Drive quota exceeded"):
                executor._publish_artifact_with_mirror(
                    "job",
                    artifact,
                    "PKG110",
                    "V6",
                    None,
                    fail_drive,
                )


if __name__ == "__main__":
    unittest.main()

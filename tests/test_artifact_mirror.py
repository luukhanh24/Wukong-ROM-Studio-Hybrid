from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wukong.adapters import RcloneStorageAdapter
from wukong.artifact_mirror import ArtifactMirrorPublisher, DCloudMirrorConfig
from wukong.models import ArtifactMirrorRecord, ArtifactRecord, Identity, JobManifest
from wukong.telegram_mini_api import public_job_payload


class ArtifactMirrorTests(unittest.TestCase):
    def test_disabled_actions_config_does_not_change_manifest_schema(self) -> None:
        record = ArtifactRecord("rom.zip", "drive:rom.zip", "a" * 64, 3)
        payload = JobManifest("job", Identity("test", "1", "user"), "digest", artifacts=[record]).to_dict()
        self.assertNotIn("mirrors", payload["artifacts"][0])
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "false", "WUKONG_DCCLOUD_REMOTE": "bad value"}, clear=False):
            self.assertFalse(DCloudMirrorConfig.from_env().enabled)
        with patch.dict(
            "os.environ",
            {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Linux",
                "WUKONG_DCCLOUD_MIRROR_ENABLED": "true",
                "WUKONG_DCCLOUD_SHARE_URL": "https://cloud.example/share",
            },
            clear=False,
        ):
            self.assertTrue(DCloudMirrorConfig.from_env().enabled)
        with patch.dict(
            "os.environ",
            {
                "GITHUB_ACTIONS": "false",
                "WUKONG_DCCLOUD_MIRROR_ENABLED": "true",
            },
            clear=False,
        ):
            self.assertFalse(DCloudMirrorConfig.from_env().enabled)

    def test_webdav_upload_stages_checks_size_moves_and_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            calls: list[list[str]] = []

            def run(args: list[str], **_: object) -> str:
                calls.append(args)
                if args[1] == "lsjson":
                    return json.dumps({"Size": 3})
                if args[1] == "cat":
                    raise RuntimeError("not found")
                return ""

            storage = RcloneStorageAdapter(remote="wukong-dccloud", run_command=run)
            record = storage.mirror_artifact(
                artifact,
                relative_path="ROM/V5.0/Lite/rom.zip",
                staging_key="job/rom.zip",
            )
            self.assertEqual("wukong-dccloud:WukongROM/ROM/V5.0/Lite/rom.zip", record.uri)
            mkdir_index = next(index for index, command in enumerate(calls) if command[1] == "mkdir")
            move_index = next(index for index, command in enumerate(calls) if command[1] == "moveto")
            self.assertLess(mkdir_index, move_index)
            self.assertTrue(any(command[1] == "moveto" for command in calls))
            self.assertTrue(any(command[1] == "lsjson" and "--stat" in command for command in calls))
            self.assertTrue(any(command[1] == "copyto" and ".metadata.json" in command[3] for command in calls))

    def test_matching_metadata_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            digest = __import__("hashlib").sha256(b"rom").hexdigest()
            calls: list[list[str]] = []

            def run(args: list[str], **_: object) -> str:
                calls.append(args)
                return json.dumps({"sha256": digest, "sizeBytes": 3}) if args[1] == "cat" else ""

            storage = RcloneStorageAdapter(remote="wukong-dccloud", run_command=run)
            storage.mirror_artifact(artifact, relative_path="ROM/rom.zip", staging_key="job")
            self.assertFalse(any(command[1] == "copyto" for command in calls))

    def test_public_payload_strips_private_mirror_uri_and_error(self) -> None:
        record = ArtifactRecord(
            "rom.zip",
            "wukong-gdrive:WukongROM/ROM/rom.zip",
            "a" * 64,
            3,
            "https://drive.google.com/file/rom",
            [ArtifactMirrorRecord("dccloud", "available", "wukong-dccloud:WukongROM/ROM/rom.zip", "https://cloud.example/share", "secret")],
        )
        manifest = JobManifest("job", Identity("test", "1", "user"), "digest", artifacts=[record])
        artifact = public_job_payload(manifest)["artifacts"][0]
        self.assertEqual({"provider": "dccloud", "status": "available", "browseUrl": "https://cloud.example/share"}, artifact["mirrors"][0])
        self.assertNotIn("wukong-dccloud", json.dumps(artifact))
        self.assertNotIn("secret", json.dumps(artifact))

    def test_publisher_retries_and_sanitizes_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            attempts = 0

            class BrokenStorage:
                def mirror_artifact(self, *args: object, **kwargs: object) -> object:
                    nonlocal attempts
                    attempts += 1
                    raise RuntimeError("stderr includes credential")

            config = DCloudMirrorConfig(True, share_url="https://cloud.example/share")
            result = ArtifactMirrorPublisher(config, storage_factory=lambda _remote: BrokenStorage(), sleep=lambda _: None).publish(
                artifact, job_id="job", device="X", build="V5"
            )
            self.assertEqual("failed", result.status)
            self.assertEqual("upload_failed", result.error_code)
            self.assertEqual(3, attempts)
            self.assertNotIn("credential", result.error_code or "")

    def test_publisher_exposes_only_the_failed_remote_stage(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")

            def run(args: list[str], **_: object) -> str:
                if args[1] == "cat":
                    raise RuntimeError("missing")
                if args[1] == "lsjson":
                    return json.dumps({"Size": 3})
                if args[1] == "moveto":
                    raise RuntimeError("private WebDAV details")
                return ""

            config = DCloudMirrorConfig(True, share_url="https://cloud.example/share")
            result = ArtifactMirrorPublisher(
                config,
                storage_factory=lambda remote: RcloneStorageAdapter(remote=remote, run_command=run),
                sleep=lambda _: None,
            ).publish(artifact, job_id="job", device="X", build="V5")
            self.assertEqual("failed", result.status)
            self.assertEqual("remote_move_failed", result.error_code)
            self.assertNotIn("WebDAV", result.error_code or "")

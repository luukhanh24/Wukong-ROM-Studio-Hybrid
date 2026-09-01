from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.mirror_repair import _download_primary_artifact
from wukong.adapters import RcloneStorageAdapter
from wukong.models import ArtifactRecord


class MirrorRepairTests(unittest.TestCase):
    def test_drive_file_id_recovers_when_manifest_path_is_missing(self) -> None:
        calls: list[list[str]] = []

        def run(args: list[str], **_: object) -> str:
            calls.append(args)
            if args[1] == "copyto":
                raise subprocess.CalledProcessError(3, args)
            if args[1:3] == ["backend", "copyid"]:
                Path(args[5]).write_bytes(b"rom")
                return ""
            raise AssertionError(args)

        artifact = ArtifactRecord(
            name="rom.zip",
            uri="wukong-gdrive:WukongROM/ROM/V6/rom.zip",
            sha256="a" * 64,
            size_bytes=3,
            public_url="https://drive.google.com/open?id=1AbCdEfGhIjKlMnOp",
        )
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root, artifact.name)
            _download_primary_artifact(
                RcloneStorageAdapter(remote="wukong-gdrive", run_command=run),
                artifact,
                destination,
            )
            self.assertEqual(b"rom", destination.read_bytes())

        self.assertEqual("copyto", calls[0][1])
        self.assertEqual(
            ["rclone", "backend", "copyid", "wukong-gdrive:", "1AbCdEfGhIjKlMnOp"],
            calls[1][:5],
        )


if __name__ == "__main__":
    unittest.main()

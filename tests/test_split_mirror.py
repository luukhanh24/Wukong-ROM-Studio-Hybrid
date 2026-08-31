from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wukong.adapters import RcloneStorageAdapter
from wukong.split_mirror import RcloneSplitStorageAdapter


class SplitMirrorTests(unittest.TestCase):
    def test_split_mirror_uploads_bounded_parts_and_manifest_last(self) -> None:
        calls: list[list[str]] = []
        sizes: dict[str, int] = {}

        def run(args: list[str], **_: object) -> str:
            calls.append(args)
            if args[1] == "copyto":
                sizes[args[3]] = Path(args[2]).stat().st_size
                return ""
            if args[1] == "cat":
                raise RuntimeError("missing")
            if args[1] == "lsjson":
                return json.dumps({"Size": sizes.get(args[2], -1)})
            return ""

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"abcdefghij")
            storage = RcloneSplitStorageAdapter(
                RcloneStorageAdapter(remote="wukong-dccloud", run_command=run),
                part_size=4,
            )
            record = storage.mirror_artifact(
                artifact,
                relative_path="ROM/V6/Plus/rom.zip",
                staging_key="job",
            )

        destinations = [call[3] for call in calls if call[1] == "copyto"]
        self.assertEqual(3, len([item for item in destinations if item.endswith((".001", ".002", ".003"))]))
        self.assertTrue(record.uri.endswith("/rom.zip.parts"))
        self.assertTrue(destinations[-1].endswith("/manifest.json"))


if __name__ == "__main__":
    unittest.main()

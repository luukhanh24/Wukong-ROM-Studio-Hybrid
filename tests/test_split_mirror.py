from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from wukong.adapters import RcloneStorageAdapter, sha256_file
from wukong.split_mirror import RcloneSplitStorageAdapter


class SplitMirrorTests(unittest.TestCase):
    def test_split_mirror_uploads_bounded_parts_and_manifest_last(self) -> None:
        calls: list[list[str]] = []
        objects: dict[str, bytes] = {}

        def run(args: list[str], **_: object) -> str:
            calls.append(args)
            if args[1] == "copyto":
                source, destination = args[2], args[3]
                if source.startswith("wukong-dccloud:") and destination.startswith("wukong-dccloud:"):
                    objects[destination] = objects[source]
                elif destination.startswith("wukong-dccloud:"):
                    objects[destination] = Path(source).read_bytes()
                else:
                    Path(destination).write_bytes(objects[source])
                return ""
            if args[1] == "cat":
                if args[2] not in objects:
                    raise RuntimeError("missing")
                return objects[args[2]].decode()
            if args[1] == "lsjson":
                return json.dumps({"Size": len(objects[args[2]]) if args[2] in objects else -1})
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
        final_parts = [item for item in destinations if "/ROM/" in item and item.endswith((".001", ".002", ".003"))]
        self.assertEqual(3, len(final_parts))
        self.assertTrue(any("/_staging/job/" in item for item in destinations))
        self.assertTrue(record.uri.endswith("/rom.zip.parts"))
        self.assertTrue(destinations[-1].endswith("/manifest.json"))

    def test_same_size_corrupt_existing_part_is_not_reused(self) -> None:
        calls: list[list[str]] = []
        objects: dict[str, bytes] = {
            "wukong-dccloud:WukongROM/ROM/V6/Plus/rom.zip.parts/rom.zip.001": b"XXXXXXXX",
            "wukong-dccloud:WukongROM/ROM/V6/Plus/rom.zip.parts/manifest.json": b"{}",
        }

        def run(args: list[str], **_: object) -> str:
            calls.append(args)
            if args[1] == "copyto":
                source, destination = args[2], args[3]
                if source.startswith("wukong-dccloud:") and destination.startswith("wukong-dccloud:"):
                    objects[destination] = objects[source]
                elif destination.startswith("wukong-dccloud:"):
                    objects[destination] = Path(source).read_bytes()
                else:
                    Path(destination).write_bytes(objects[source])
                return ""
            if args[1] == "cat":
                if args[2] not in objects:
                    raise RuntimeError("missing")
                return objects[args[2]].decode("utf-8")
            if args[1] == "lsjson":
                return json.dumps({"Size": len(objects[args[2]])}) if args[2] in objects else json.dumps({"Size": -1})
            return ""

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"abcdefgh")
            adapter = RcloneSplitStorageAdapter(
                RcloneStorageAdapter(remote="wukong-dccloud", run_command=run),
                part_size=8,
            )
            adapter.mirror_artifact(artifact, relative_path="ROM/V6/Plus/rom.zip", staging_key="job")

        staging_uri = "wukong-dccloud:WukongROM/_staging/job/rom.zip.parts/rom.zip.001"
        self.assertTrue(any(call[1] == "copyto" and call[3] == staging_uri for call in calls))
        self.assertEqual(
            b"abcdefgh",
            objects["wukong-dccloud:WukongROM/ROM/V6/Plus/rom.zip.parts/rom.zip.001"],
        )
        invalidate_index = next(
            index
            for index, call in enumerate(calls)
            if call[1] == "copyto"
            and call[2].endswith("manifest.incomplete.json")
            and call[3].endswith("manifest.json")
        )
        promote_index = next(
            index
            for index, call in enumerate(calls)
            if call[1] == "copyto"
            and call[2].startswith("wukong-dccloud:")
            and call[3].startswith("wukong-dccloud:")
            and call[3].endswith("rom.zip.001")
        )
        self.assertLess(invalidate_index, promote_index)

    def test_incomplete_matching_manifest_is_not_accepted_as_complete(self) -> None:
        calls: list[list[str]] = []
        objects: dict[str, bytes] = {}

        def run(args: list[str], **_: object) -> str:
            calls.append(args)
            if args[1] == "copyto":
                source, destination = args[2], args[3]
                if source.startswith("wukong-dccloud:") and destination.startswith("wukong-dccloud:"):
                    objects[destination] = objects[source]
                elif destination.startswith("wukong-dccloud:"):
                    objects[destination] = Path(source).read_bytes()
                else:
                    Path(destination).write_bytes(objects[source])
                return ""
            if args[1] == "cat":
                if args[2] not in objects:
                    raise RuntimeError("missing")
                return objects[args[2]].decode("utf-8")
            if args[1] == "lsjson":
                return json.dumps({"Size": len(objects[args[2]])}) if args[2] in objects else json.dumps({"Size": -1})
            return ""

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"abcdefgh")
            manifest_uri = "wukong-dccloud:WukongROM/ROM/V6/Plus/rom.zip.parts/manifest.json"
            objects[manifest_uri] = json.dumps(
                {
                    "format": "wukong-raw-split-v1",
                    "sha256": sha256_file(artifact),
                    "sizeBytes": 8,
                    "partSizeBytes": 8,
                    "parts": [],
                }
            ).encode("utf-8")
            adapter = RcloneSplitStorageAdapter(
                RcloneStorageAdapter(remote="wukong-dccloud", run_command=run),
                part_size=8,
            )
            adapter.mirror_artifact(artifact, relative_path="ROM/V6/Plus/rom.zip", staging_key="job")

        self.assertTrue(
            any(
                call[1] == "copyto"
                and call[3].endswith("_staging/job/rom.zip.parts/rom.zip.001")
                for call in calls
            )
        )

    def test_missing_remote_stat_is_treated_as_not_found(self) -> None:
        def run(args: list[str], **_: object) -> str:
            raise subprocess.CalledProcessError(3, args, output="object not found")

        storage = RcloneStorageAdapter(remote="wukong-dccloud", run_command=run)

        self.assertIsNone(storage.stat_size("ROM/missing.part"))


if __name__ == "__main__":
    unittest.main()

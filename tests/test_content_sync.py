from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wukong.content_sync import (
    discover_pack_sources,
    migrate_shared_mods,
    refresh_content_index,
)


class ContentSyncTests(unittest.TestCase):
    def test_migration_copies_verifies_then_removes_version_local_shared_mods(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            local = install / "Content" / "MOD" / "ColorOS_16.0.10"
            for name in ("WK_Manager", "WK_Installer"):
                source = local / name / "system"
                source.mkdir(parents=True)
                (source / f"{name}.apk").write_bytes(name.encode())

            migrated = migrate_shared_mods(install, version="ColorOS_16.0.10")

            self.assertEqual(["WK_Installer", "WK_Manager"], migrated)
            for name in ("WK_Manager", "WK_Installer"):
                self.assertFalse((local / name).exists())
                self.assertTrue((install / "Runtime" / "STARK" / name / "system" / f"{name}.apk").is_file())

    def test_refresh_index_discovers_content_and_runtime_packs(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            (install / "Content" / "MOD" / "ColorOS_Test" / "Gapps").mkdir(parents=True)
            (install / "Content" / "MOD" / "ColorOS_Test" / "Gapps" / "app.apk").write_bytes(b"g")
            (install / "Runtime" / "STARK" / "WK_Manager").mkdir(parents=True)
            (install / "Runtime" / "STARK" / "WK_Manager" / "manager.apk").write_bytes(b"m")
            (install / "Runtime" / "Flash_script" / "bin").mkdir(parents=True)
            (install / "Runtime" / "Flash_script" / "bin" / "flash").write_bytes(b"f")
            index_path = install / "index.json"

            index, changed = refresh_content_index(
                install,
                index_path,
                remote="drive:WukongROM/content-packs",
            )

            ids = [pack["id"] for pack in index["packs"]]
            self.assertEqual(["Flash_script/common", "MOD/ColorOS_Test", "STARK/common"], ids)
            self.assertEqual(ids, changed)
            self.assertEqual("Runtime", discover_pack_sources(install)["STARK/common"].name)
            self.assertEqual(index, json.loads(index_path.read_text(encoding="utf-8")))

    def test_refresh_preserves_verified_archive_for_unchanged_pack(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            pack = install / "Runtime" / "STARK"
            pack.mkdir(parents=True)
            (pack / "smali").write_bytes(b"same")
            index_path = install / "index.json"
            index, _ = refresh_content_index(install, index_path, remote="drive:content-packs")
            index["packs"][0]["archive"] = {
                "uri": "drive:content-packs/STARK/common.tar.zst",
                "sha256": "a" * 64,
                "md5": "b" * 32,
                "sizeBytes": 4,
            }
            index_path.write_text(json.dumps(index), encoding="utf-8")

            refreshed, changed = refresh_content_index(install, index_path, remote="drive:content-packs")

            self.assertEqual([], changed)
            self.assertEqual("a" * 64, refreshed["packs"][0]["archive"]["sha256"])

    def test_refresh_marks_unchanged_pack_without_archive_for_upload(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            pack = install / "Runtime" / "STARK"
            pack.mkdir(parents=True)
            (pack / "smali").write_bytes(b"same")
            index_path = install / "index.json"
            refresh_content_index(install, index_path, remote="drive:content-packs")

            _refreshed, changed = refresh_content_index(
                install,
                index_path,
                remote="drive:content-packs",
            )

            self.assertEqual(["STARK/common"], changed)


if __name__ == "__main__":
    unittest.main()

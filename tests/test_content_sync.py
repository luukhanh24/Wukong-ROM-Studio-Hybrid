from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wukong.content_sync import (
    discover_pack_sources,
    migrate_shared_mods,
    refresh_content_index,
    resolve_selected_content_pack,
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
                self.assertTrue((install / "Content" / "STARK" / name / "system" / f"{name}.apk").is_file())
            self.assertFalse((install / "Runtime" / "STARK").exists())

    def test_refresh_index_discovers_content_and_runtime_packs(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            (install / "Content" / "MOD" / "ColorOS_Test" / "Gapps").mkdir(parents=True)
            (install / "Content" / "MOD" / "ColorOS_Test" / "Gapps" / "app.apk").write_bytes(b"g")
            (install / "Content" / "STARK" / "WK_Manager").mkdir(parents=True)
            (install / "Content" / "STARK" / "WK_Manager" / "manager.apk").write_bytes(b"m")
            (install / "Content" / "Flash_script" / "bin").mkdir(parents=True)
            (install / "Content" / "Flash_script" / "bin" / "flash").write_bytes(b"f")
            index_path = install / "index.json"

            index, changed = refresh_content_index(
                install,
                index_path,
                remote="drive:WukongROM/content-packs",
            )

            ids = [pack["id"] for pack in index["packs"]]
            self.assertEqual(["Flash_script/common", "MOD/ColorOS_Test", "STARK/common"], ids)
            self.assertEqual(ids, changed)
            self.assertEqual("Content", discover_pack_sources(install)["STARK/common"].name)
            self.assertEqual(index, json.loads(index_path.read_text(encoding="utf-8")))

    def test_refresh_preserves_verified_archive_for_unchanged_pack(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            pack = install / "Content" / "STARK"
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
            pack = install / "Content" / "STARK"
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

    def test_runtime_stark_is_ignored_when_content_stark_exists(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            content_pack = install / "Content" / "STARK"
            runtime_pack = install / "Runtime" / "STARK"
            content_pack.mkdir(parents=True)
            runtime_pack.mkdir(parents=True)
            (content_pack / "current.smali").write_bytes(b"current")
            (runtime_pack / "stale.smali").write_bytes(b"stale")

            index, changed = refresh_content_index(install, install / "index.json", remote="drive:packs")

            self.assertEqual(["STARK/common"], changed)
            self.assertEqual(["current.smali"], [item["path"] for item in index["packs"][0]["files"]])
            self.assertEqual((install / "Content").resolve(), discover_pack_sources(install)["STARK/common"])

    def test_selected_stark_subfolder_resolves_to_full_stark_pack(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            selected = install / "Content" / "STARK" / "WK_Manager"
            selected.mkdir(parents=True)

            pack_id, pack_root = resolve_selected_content_pack(install, selected)

            self.assertEqual("STARK/common", pack_id)
            self.assertEqual((install / "Content" / "STARK").resolve(), pack_root)

    def test_selected_sync_forces_only_its_pack_and_preserves_other_archives(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            stark = install / "Content" / "STARK"
            mod = install / "Content" / "MOD" / "ColorOS_Test"
            stark.mkdir(parents=True)
            mod.mkdir(parents=True)
            (stark / "manager.smali").write_bytes(b"stark-v1")
            (mod / "app.apk").write_bytes(b"mod-v1")
            index_path = install / "index.json"
            index, _ = refresh_content_index(install, index_path, remote="drive:packs")
            for pack in index["packs"]:
                pack["archive"] = {
                    "uri": f"drive:packs/{pack['id']}.tar.zst",
                    "sha256": "a" * 64,
                    "md5": "b" * 32,
                    "sizeBytes": 1,
                }
            index_path.write_text(json.dumps(index), encoding="utf-8")
            old_mod = next(pack for pack in index["packs"] if pack["id"] == "MOD/ColorOS_Test")
            (stark / "manager.smali").write_bytes(b"stark-v2")
            (mod / "app.apk").write_bytes(b"mod-v2")

            refreshed, changed = refresh_content_index(
                install,
                index_path,
                remote="drive:packs",
                only_pack_ids={"STARK/common"},
                force_pack_ids={"STARK/common"},
            )

            self.assertEqual(["STARK/common"], changed)
            refreshed_mod = next(pack for pack in refreshed["packs"] if pack["id"] == "MOD/ColorOS_Test")
            refreshed_stark = next(pack for pack in refreshed["packs"] if pack["id"] == "STARK/common")
            self.assertEqual(old_mod, refreshed_mod)
            self.assertNotIn("archive", refreshed_stark)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import sync_platform_content
from wukong.content_sync import refresh_content_index


class SyncPlatformContentCliTests(unittest.TestCase):
    def test_github_publish_uses_repaired_verified_index_without_rescanning_local_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            stark = install / "Content" / "STARK"
            stark.mkdir(parents=True)
            source = stark / "manager.smali"
            source.write_bytes(b"verified")
            baseline_path = install / "baseline.json"
            baseline, _ = refresh_content_index(install, baseline_path, remote="drive:packs")
            baseline["packs"][0]["archive"] = {
                "uri": "drive:packs/STARK/common.tar.zst",
                "sha256": "a" * 64,
                "md5": "b" * 32,
                "sizeBytes": 7,
            }
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            interrupted = json.loads(json.dumps(baseline))
            interrupted["packs"][0].pop("archive")
            index_path = install / "index.json"
            index_path.write_text(json.dumps(interrupted), encoding="utf-8")
            source.write_bytes(b"locally changed after the verified upload")
            argv = [
                "sync_platform_content",
                "--install-root", str(install),
                "--index", str(index_path),
                "--baseline-index", str(baseline_path),
                "--target", "github",
                "--repository", "owner/repository",
                "--run-id", "11111111111111111111111111111111",
            ]

            with (
                patch.object(sys, "argv", argv),
                patch.object(sync_platform_content, "publish_index_to_github", return_value="commit") as publish,
            ):
                result = sync_platform_content.main()

            self.assertEqual(0, result)
            publish.assert_called_once()
            published = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual("a" * 64, published["packs"][0]["archive"]["sha256"])

    def test_selected_upload_skips_global_migration_and_rolls_back_index_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            selected = install / "Content" / "MOD" / "Test" / "WK_Manager"
            selected.mkdir(parents=True)
            index_path = install / "Data" / "index.json"
            index_path.parent.mkdir(parents=True)
            original = {"schemaVersion": 1, "generatedAt": "verified", "packs": []}
            index_path.write_text(json.dumps(original), encoding="utf-8")
            rclone = install / "rclone.conf"
            rclone.write_text("", encoding="utf-8")
            baseline = install / "baseline.json"
            baseline.write_text(json.dumps(original), encoding="utf-8")
            repaired_paths: list[Path] = []

            def repair(working: Path, _baseline: Path) -> int:
                repaired_paths.append(working)
                working.write_text(json.dumps({**original, "generatedAt": "repaired"}), encoding="utf-8")
                return 1

            def refresh(_install: Path, working: Path, **_kwargs: object):
                changed = {"schemaVersion": 1, "generatedAt": "working", "packs": []}
                working.write_text(json.dumps(changed), encoding="utf-8")
                return changed, ["MOD/Test"]

            argv = [
                "sync_platform_content",
                "--install-root", str(install),
                "--index", str(index_path),
                "--baseline-index", str(baseline),
                "--target", "drive",
                "--rclone-config", str(rclone),
                "--folder", str(selected),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(sync_platform_content, "restore_incomplete_index", side_effect=repair),
                patch.object(sync_platform_content, "refresh_content_index", side_effect=refresh),
                patch.object(sync_platform_content, "upload_changed_packs", side_effect=RuntimeError("upload failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "upload failed"):
                    sync_platform_content.main()

            self.assertEqual(original, json.loads(index_path.read_text(encoding="utf-8")))
            self.assertEqual(1, len(repaired_paths))
            self.assertNotEqual(index_path, repaired_paths[0])
            self.assertEqual([], list(index_path.parent.glob(".*.working")))

    def test_selected_folder_and_global_migration_are_explicitly_incompatible(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            selected = install / "Content" / "STARK" / "WK_Manager"
            selected.mkdir(parents=True)
            argv = [
                "sync_platform_content",
                "--install-root", str(install),
                "--index", str(install / "index.json"),
                "--target", "refresh",
                "--migrate-shared",
                "--folder", str(selected),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as error:
                    sync_platform_content.main()
            self.assertEqual(2, error.exception.code)

    def test_github_publish_rejects_content_migration(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            install = Path(root)
            argv = [
                "sync_platform_content",
                "--install-root", str(install),
                "--index", str(install / "index.json"),
                "--target", "github",
                "--migrate-shared",
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as error:
                    sync_platform_content.main()
            self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()

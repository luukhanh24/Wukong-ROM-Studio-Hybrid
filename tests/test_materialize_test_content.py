from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import materialize_test_content


class MaterializeTestContentSafetyTests(unittest.TestCase):
    def test_refuses_to_overwrite_real_shared_wk_manager_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mod_root = root / "MOD"
            mod_root.mkdir()
            mod_marker = mod_root / ".wukong-test-fixture"
            mod_marker.write_text("fixture\n", encoding="utf-8")
            shared_root = root / "STARK" / "WK_Manager"
            shared_root.mkdir(parents=True)
            daemon = shared_root / "system" / "system" / "bin" / "wukong-system-powerd"
            daemon.parent.mkdir(parents=True)
            daemon.write_bytes(b"real-daemon")
            index = root / "index.json"
            index.write_text(json.dumps({"packs": []}), encoding="utf-8")

            with mock.patch.multiple(
                materialize_test_content,
                INDEX=index,
                MOD_ROOT=mod_root,
                MARKER=mod_marker,
                STARK_ROOT=root / "STARK",
                SHARED_WK_ROOT=shared_root,
                SHARED_WK_MARKER=shared_root / ".wukong-test-fixture",
            ):
                with self.assertRaisesRegex(SystemExit, "Refusing to modify"):
                    materialize_test_content.main()

            self.assertEqual(daemon.read_bytes(), b"real-daemon")


if __name__ == "__main__":
    unittest.main()

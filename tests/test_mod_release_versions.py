from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wukong.mod_release_versions import ModReleaseVersionStore


class ModReleaseVersionStoreTests(unittest.TestCase):
    def test_labels_are_atomic_persistent_and_not_limited_to_v_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            changed: list[bool] = []
            store = ModReleaseVersionStore(
                Path(root) / "versions.json",
                versions_provider=lambda: ["ColorOS_16.0.10"],
                default_provider=lambda _version: "V6.0",
                on_change=lambda: changed.append(True),
            )

            self.assertEqual({"ColorOS_16.0.10": "V6.0"}, store.load())
            self.assertEqual(
                "Stable 6",
                store.save({"ColorOS_16.0.10": "Stable 6"})["ColorOS_16.0.10"],
            )
            self.assertEqual("Stable 6", store.load()["ColorOS_16.0.10"])
            self.assertEqual([True], changed)
            with self.assertRaisesRegex(ValueError, "printable"):
                store.save({"ColorOS_16.0.10": "../unsafe"})


if __name__ == "__main__":
    unittest.main()

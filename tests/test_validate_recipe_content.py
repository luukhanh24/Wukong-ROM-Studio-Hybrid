from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_recipe_content import validate_recipe_content


class RecipeContentValidationTests(unittest.TestCase):
    def test_accepts_ready_mods_from_installed_content_pack(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.9" / "Camera_mod" / "system").mkdir(parents=True)
            recipe = Path(root, "recipe.json")
            recipe.write_text(json.dumps({
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "build": {"modVersion": "ColorOS_16.0.9", "mods": ["Camera_mod"]},
            }), encoding="utf-8")

            result = validate_recipe_content(recipe, content)

        self.assertTrue(result["ok"])
        self.assertEqual(["Camera_mod"], result["mods"])

    def test_rejects_missing_mod_before_rom_download(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.9" / "Camera_mod" / "system").mkdir(parents=True)
            recipe = Path(root, "recipe.json")
            recipe.write_text(json.dumps({
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "build": {"modVersion": "ColorOS_16.0.9", "mods": ["Fix_Metis"]},
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Fix_Metis"):
                validate_recipe_content(recipe, content)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_recipe_content import apply_resolved_mods, resolve_recipe_mods, validate_recipe_content
from wukong.models import BuildRecipe


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

            result = validate_recipe_content(recipe, content, drop_missing=False)

        self.assertTrue(result["ok"])
        self.assertEqual(["Camera_mod"], result["mods"])

    def test_rejects_missing_mod_in_strict_mode(self) -> None:
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
                validate_recipe_content(recipe, content, drop_missing=False)

    def test_drop_missing_rewrites_recipe_to_available_mods(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.9" / "Camera_mod" / "system").mkdir(parents=True)
            (content / "MOD" / "ColorOS_16.0.9" / "Gapps" / "system").mkdir(parents=True)
            recipe_path = Path(root, "recipe.json")
            recipe_path.write_text(json.dumps({
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "build": {
                    "modVersion": "ColorOS_16.0.9",
                    "mods": ["Camera_mod", "Fix_Metis"],
                    "preset": "custom",
                },
            }), encoding="utf-8")

            result = validate_recipe_content(
                recipe_path,
                content,
                drop_missing=True,
                rewrite=True,
            )

            self.assertEqual(["Camera_mod"], result["mods"])
            self.assertEqual(["Fix_Metis"], result["dropped"])
            rewritten = BuildRecipe.from_dict(json.loads(recipe_path.read_text(encoding="utf-8")))
            self.assertEqual(("Camera_mod",), rewritten.build.mods)

    def test_drop_missing_preserves_per_job_release_label(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.9" / "Camera_mod" / "system").mkdir(parents=True)
            recipe = BuildRecipe.from_dict({
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "build": {
                    "modVersion": "ColorOS_16.0.9",
                    "modReleaseVersion": "KhanhDZ",
                    "mods": ["Camera_mod", "Missing_mod"],
                    "preset": "custom",
                },
            })
            resolved = resolve_recipe_mods(recipe, content, drop_missing=True)
            updated = apply_resolved_mods(recipe, resolved)

        self.assertEqual(("Camera_mod",), updated.build.mods)
        self.assertEqual("KhanhDZ", updated.build.mod_release_version)

    def test_drop_missing_substitutes_lite_defaults_when_selection_empty(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.9" / "Gapps" / "system").mkdir(parents=True)
            recipe = BuildRecipe.from_dict({
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "build": {
                    "modVersion": "ColorOS_16.0.9",
                    "mods": ["Fix_Metis"],
                    "preset": "custom",
                },
            })
            resolved = resolve_recipe_mods(recipe, content, drop_missing=True)
            updated = apply_resolved_mods(recipe, resolved)
            self.assertIn("Gapps", updated.build.mods)
            self.assertNotIn("Fix_Metis", updated.build.mods)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.materialize_workflow_recipe import recipe_from_workflow_inputs, write_workflow_recipe
from wukong.models import RecipeValidationError


class WorkflowRecipeTests(unittest.TestCase):
    def test_builds_detailed_recipe_from_dispatch_inputs(self) -> None:
        recipe = recipe_from_workflow_inputs({
            "TASK": "build",
            "DEVICE": "PKG110",
            "SOURCE_URI": "https://downloads.example/rom.zip",
            "SOURCE_SHA256": "a" * 64,
            "SOURCE_SIZE_BYTES": "8680370027",
            "MOD_VERSION": "ColorOS_16.0.9",
            "PRESET": "both",
            "MODS": "Camera_mod, WK_Installer\nWK_Manager",
            "ENABLED_STEPS": "inspect_rom,extract_payload,package_zip",
            "DEBLOAT_PATHS": "my_stock/app/Browser\nmy_product/app/Video",
            "EXECUTION_TARGET": "github-hosted",
            "PACKAGE": "true",
            "PUBLISH_ARTIFACT": "true",
            "NOTIFY_TELEGRAM": "true",
        })

        self.assertEqual(recipe.source.size_bytes, 8680370027)
        self.assertEqual(recipe.execution.target, "github-hosted")
        self.assertEqual(recipe.build.mods, ("Camera_mod", "WK_Installer", "WK_Manager"))
        self.assertEqual(recipe.build.enabled_steps[-1], "package_zip")
        self.assertTrue(recipe.storage.publish_artifact)
        self.assertTrue(recipe.build.notify_telegram)

    def test_source_mirror_omits_build_only_options(self) -> None:
        recipe = recipe_from_workflow_inputs({
            "TASK": "source_mirror",
            "DEVICE": "PKG110",
            "SOURCE_URI": "wukong-gdrive:WukongROM/sources/PKG110/stock.zip",
            "EXECUTION_TARGET": "github-auto",
            "PUBLISH_ARTIFACT": "false",
        })

        self.assertEqual(recipe.source.kind, "rclone")
        self.assertEqual(recipe.task, "source_mirror")
        self.assertFalse(recipe.storage.publish_artifact)

    def test_artifact_publish_is_available_from_detailed_dispatch(self) -> None:
        recipe = recipe_from_workflow_inputs({
            "TASK": "artifact_publish",
            "DEVICE": "PKG110",
            "SOURCE_URI": "wukong-gdrive:WukongROM/jobs/example/output.zip",
            "EXECUTION_TARGET": "github-auto",
            "PUBLISH_ARTIFACT": "true",
        })

        self.assertEqual("artifact_publish", recipe.task)
        self.assertTrue(recipe.storage.publish_artifact)

    def test_rejects_missing_source_and_local_windows_target(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "source URL"):
            recipe_from_workflow_inputs({"TASK": "build", "DEVICE": "PKG110"})
        with self.assertRaisesRegex(RecipeValidationError, "GitHub execution"):
            recipe_from_workflow_inputs({
                "TASK": "build",
                "DEVICE": "PKG110",
                "SOURCE_URI": "https://downloads.example/rom.zip",
                "EXECUTION_TARGET": "local-windows",
            })

    def test_writer_emits_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = Path(root, "recipe.json")
            recipe = write_workflow_recipe({
                "TASK": "build",
                "DEVICE": "PKG110",
                "SOURCE_URI": "https://downloads.example/rom.zip",
                "MOD_VERSION": "ColorOS_16.0.9",
            }, output)

            self.assertTrue(output.is_file())
            self.assertIn(recipe.digest, recipe.digest)
            self.assertIn('"schemaVersion": 1', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

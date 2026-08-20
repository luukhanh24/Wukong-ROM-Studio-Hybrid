import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopScriptTests(unittest.TestCase):
    def test_script_path_defaults_are_resolved_after_parameter_binding(self):
        for relative_path in (
            "desktop/Scripts/publish.ps1",
            "desktop/Scripts/build-runtime.ps1",
            "desktop/Scripts/build-all-content-packs.ps1",
        ):
            content = (ROOT / relative_path).read_text(encoding="utf-8")
            parameter_block = content.split("\n)\n", 1)[0]
            self.assertNotIn(
                "$PSScriptRoot",
                parameter_block,
                f"{relative_path} evaluates PSScriptRoot before parameter binding completes",
            )

    def test_windows_installer_stages_only_the_windows_toolchain(self):
        content = (ROOT / "desktop/Scripts/build-runtime.ps1").read_text(encoding="utf-8")
        self.assertIn("Copy-Tree (Join-Path $source 'bin\\Windows')", content)
        self.assertNotIn("Copy-Tree (Join-Path $source 'bin')", content)

    def test_publish_python_test_list_keeps_every_module_in_one_command(self):
        content = (ROOT / "desktop/Scripts/publish.ps1").read_text(encoding="utf-8")
        self.assertIn("tests.test_wk_manager_patcher `\n            tests.test_wukong_hybrid", content)


if __name__ == "__main__":
    unittest.main()

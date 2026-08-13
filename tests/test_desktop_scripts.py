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


if __name__ == "__main__":
    unittest.main()

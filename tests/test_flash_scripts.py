import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FlashScriptTests(unittest.TestCase):
    def test_product_guard_is_removed_for_all_platforms(self):
        scripts = [
            ROOT / "Flash_script" / "Wukong_Flashing_Tool_Linux.sh",
            ROOT / "Flash_script" / "Wukong_Flashing_Tool_MacOS.sh",
            ROOT / "Flash_script" / "Wukong_Flashing_Tool_Windows.bat",
        ]
        for script in scripts:
            content = script.read_text(encoding="utf-8")
            self.assertNotIn("expected_product.txt", content)
            self.assertNotIn("getvar product", content)
            self.assertNotIn("verify_expected_product", content)

    def test_shell_scripts_parse(self):
        for name in [
            "Wukong_Flashing_Tool_Linux.sh",
            "Wukong_Flashing_Tool_MacOS.sh",
        ]:
            result = subprocess.run(
                ["bash", "-n", f"Flash_script/{name}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_integrity_progress_exists_for_all_platforms(self):
        windows = (
            ROOT / "Flash_script" / "Wukong_Flashing_Tool_Windows.bat"
        ).read_text(encoding="utf-8")
        self.assertIn('call :showProgress "CHECK" "%filename%"', windows)
        self.assertIn(":showProgress", windows)
        self.assertIn("progress_filled", windows)

        for name in [
            "Wukong_Flashing_Tool_Linux.sh",
            "Wukong_Flashing_Tool_MacOS.sh",
        ]:
            content = (ROOT / "Flash_script" / name).read_text(encoding="utf-8")
            self.assertIn('show_progress "CHECK" "$filename"', content)
            self.assertIn("show_progress()", content)
            self.assertIn("progress_total", content)

    def test_missing_unpack_source_returns_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "batch_unpack.py"), "__missing__", "__unused__"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tools" / "smoke_rom_fixture_linux.py"


class LinuxRomFixtureSmokeContractTests(unittest.TestCase):
    def test_plan_covers_every_required_rom_format(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SMOKE), "--plan"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(
            payload["formats"],
            ["ext4", "erofs", "payload", "super", "vbmeta", "vendor_boot", "zip"],
        )
        self.assertEqual(payload["platform"], "Linux/x86_64")


if __name__ == "__main__":
    unittest.main()

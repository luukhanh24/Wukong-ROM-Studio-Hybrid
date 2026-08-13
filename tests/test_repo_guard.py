from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools" / "repo_guard.py"


class RepositoryGuardContractTests(unittest.TestCase):
    def _run_guard(self, files: dict[str, bytes]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            subprocess.run(["git", "add", "--all"], cwd=root, check=True)
            return subprocess.run(
                [sys.executable, str(GUARD)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_rejects_tracked_git_lfs_pointer(self) -> None:
        result = self._run_guard(
            {
                "assets/tool.bin": (
                    b"version https://git-lfs.github.com/spec/v1\n"
                    b"oid sha256:" + b"a" * 64 + b"\n"
                    b"size 123456789\n"
                )
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git LFS pointer", result.stderr + result.stdout)

    def test_rejects_tracked_rclone_oauth_token(self) -> None:
        result = self._run_guard(
            {
                "config/example.txt": (
                    b'[wukong-gdrive]\ntype = drive\n'
                    b'token = {"access_token":"ya29.' + b"A" * 48 + b'","refresh_token":"1//secret"}\n'
                )
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret", (result.stderr + result.stdout).casefold())

    def test_accepts_small_secret_free_repository(self) -> None:
        result = self._run_guard({"README.md": b"fixture\n"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Repository guard passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

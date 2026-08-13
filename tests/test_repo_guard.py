from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
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

    def test_rejects_git_lfs_attributes_with_tab_whitespace(self) -> None:
        result = self._run_guard(
            {".gitattributes": b"*.bin\tfilter=lfs\tdiff=lfs\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git LFS configuration", result.stderr + result.stdout)

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

    def test_rejects_generated_rom_zip_under_arbitrary_name(self) -> None:
        payload = BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("META-INF/com/android/metadata", "oplus_product_name=PKG110\n")
            archive.writestr("payload.bin", b"CrAUfixture")

        result = self._run_guard({"release/customer-delivery.zip": payload.getvalue()})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generated ROM", result.stderr + result.stdout)

    def test_rejects_real_wukong_flashing_zip_layout(self) -> None:
        payload = BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("META-INF/com/android/metadata", "oplus_product_name=PKG110\n")
            archive.writestr("images/super.img", b"fixture-super")
            archive.writestr("Wukong_Flashing_Tool_Linux.sh", b"#!/bin/sh\n")

        result = self._run_guard({"release/customer-delivery.zip": payload.getvalue()})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generated ROM", result.stderr + result.stdout)

    def test_rejects_non_sha_action_reference(self) -> None:
        result = self._run_guard(
            {".github/workflows/ci.yml": b"steps:\n  - uses: actions/checkout@v7.0.1\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("40-character commit SHA", result.stderr + result.stdout)

    def test_rejects_floating_docker_action(self) -> None:
        result = self._run_guard(
            {".github/workflows/ci.yml": b"steps:\n  - uses: docker://vendor/tool:latest\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("40-character commit SHA", result.stderr + result.stdout)

    def test_accepts_digest_pinned_docker_action(self) -> None:
        digest = b"a" * 64
        result = self._run_guard(
            {
                ".github/workflows/ci.yml": (
                    b"steps:\n  - uses: docker://vendor/tool@sha256:" + digest + b"\n"
                )
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_accepts_pinned_and_local_action_references(self) -> None:
        sha = b"a" * 40
        result = self._run_guard(
            {
                ".github/workflows/ci.yml": (
                    b"steps:\n  - uses: actions/checkout@" + sha + b"\n"
                    b"  - uses: ./.github/actions/run-hybrid\n"
                )
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_accepts_small_secret_free_repository(self) -> None:
        result = self._run_guard({"README.md": b"fixture\n"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Repository guard passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

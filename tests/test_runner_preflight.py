from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tools import runner_preflight


class RunnerPreflightTests(unittest.TestCase):
    def test_rejects_full_root_even_when_workspace_has_enough_space(self) -> None:
        gib = 1024**3

        def disk_usage(path: str):
            free = 128 * 1024**2 if path == "/" else 100 * gib
            return type("Usage", (), {"free": free})()

        output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "runner_preflight",
                    "--path",
                    ".",
                    "--min-disk-gib",
                    "70",
                    "--root-path",
                    "/",
                    "--min-root-disk-gib",
                    "4",
                    "--min-memory-gib",
                    "0",
                    "--min-cpus",
                    "0",
                ],
            ),
            patch("tools.runner_preflight.shutil.disk_usage", side_effect=disk_usage),
            patch("tools.runner_preflight.os.sysconf", return_value=1, create=True),
            patch("tools.runner_preflight.os.cpu_count", return_value=2),
            redirect_stdout(output),
        ):
            result = runner_preflight.main()

        report = json.loads(output.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(report["rootFreeDiskBytes"], 128 * 1024**2)
        self.assertEqual(report["requiredRootDiskBytes"], 4 * gib)
        self.assertEqual(report["workspaceFreeDiskBytes"], 100 * gib)
        self.assertEqual(report["requiredWorkspaceDiskBytes"], 70 * gib)

    def test_accepts_runner_when_root_and_workspace_meet_thresholds(self) -> None:
        gib = 1024**3

        def disk_usage(path: str):
            free = 5 * gib if path == "/" else 100 * gib
            return type("Usage", (), {"free": free})()

        with (
            patch.object(
                sys,
                "argv",
                [
                    "runner_preflight",
                    "--path",
                    ".",
                    "--min-disk-gib",
                    "70",
                    "--root-path",
                    "/",
                    "--min-root-disk-gib",
                    "4",
                    "--min-memory-gib",
                    "0",
                    "--min-cpus",
                    "0",
                ],
            ),
            patch("tools.runner_preflight.shutil.disk_usage", side_effect=disk_usage),
            patch("tools.runner_preflight.os.sysconf", return_value=1, create=True),
            patch("tools.runner_preflight.os.cpu_count", return_value=2),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(runner_preflight.main(), 0)


if __name__ == "__main__":
    unittest.main()

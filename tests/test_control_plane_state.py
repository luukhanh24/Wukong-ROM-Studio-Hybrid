from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from wukong.control_plane_state import ControlPlaneStateBackup, ControlPlaneStateError


class _FakeRclone:
    def __init__(self, remote_payload: bytes | None = None, *, download_failures: int = 0) -> None:
        self.remote_payload = remote_payload
        self.download_failures = download_failures
        self.uploaded_payload: bytes | None = None
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        command = list(command)
        self.commands.append(command)
        operation = command[1]
        source, destination = command[2:4]
        if operation != "copyto":
            return subprocess.CompletedProcess(command, 2, "", "unsupported")
        if source.startswith("fixture:"):
            if self.download_failures > 0:
                self.download_failures -= 1
                return subprocess.CompletedProcess(command, 1, "", "temporary unavailable")
            if self.remote_payload is None:
                return subprocess.CompletedProcess(command, 1, "", "object not found")
            Path(destination).write_bytes(self.remote_payload)
        else:
            self.uploaded_payload = Path(source).read_bytes()
        return subprocess.CompletedProcess(command, 0, "", "")


def _archive(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


class ControlPlaneStateBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.config = self.root / "rclone.conf"
        self.config.write_text("[fixture]\ntype = local\n", encoding="utf-8")

    def _backup(self, runner: _FakeRclone) -> ControlPlaneStateBackup:
        return ControlPlaneStateBackup(
            self.data,
            remote="fixture",
            config_path=self.config,
            interval_seconds=1,
            restore_retry_seconds=0,
            run_command=runner,
        )

    def test_snapshot_contains_only_allowlisted_control_plane_state(self) -> None:
        job = self.data / "jobs" / "hybrid" / "job-123"
        job.mkdir(parents=True)
        (job / "manifest.json").write_text('{"jobId":"job-123"}\n', encoding="utf-8")
        (job / "recipe.json").write_text('{"schemaVersion":1}\n', encoding="utf-8")
        (job / "events.jsonl").write_text('{"sequence":1}\n', encoding="utf-8")
        (self.data / "telegram-access.json").write_text('{"users":["42"]}\n', encoding="utf-8")
        (self.data / "telegram-ui-state.json").write_text('{"languages":{}}\n', encoding="utf-8")
        secrets = self.data / "Secrets"
        secrets.mkdir()
        (secrets / "rclone.runtime.conf").write_text("token = secret\n", encoding="utf-8")
        (job / "private.log").write_text("secret log\n", encoding="utf-8")
        runner = _FakeRclone()

        self.assertTrue(self._backup(runner).backup())
        self.assertIsNotNone(runner.uploaded_payload)
        with zipfile.ZipFile(BytesIO(runner.uploaded_payload or b"")) as archive:
            names = set(archive.namelist())

        self.assertEqual(
            {
                "jobs/hybrid/job-123/events.jsonl",
                "jobs/hybrid/job-123/manifest.json",
                "jobs/hybrid/job-123/recipe.json",
                "telegram-access.json",
                "telegram-ui-state.json",
            },
            names,
        )
        self.assertFalse(any("secret" in name.casefold() for name in names))

    def test_restore_rehydrates_job_and_preferences(self) -> None:
        payload = _archive({
            "jobs/hybrid/job-123/manifest.json": b'{"jobId":"job-123"}\n',
            "jobs/hybrid/job-123/recipe.json": b'{"schemaVersion":1}\n',
            "jobs/hybrid/job-123/events.jsonl": b'{"sequence":1}\n',
            "telegram-access.json": json.dumps({"users": ["42"]}).encode(),
            "telegram-ui-state.json": json.dumps({"languages": {"42": "vi"}}).encode(),
        })

        self.assertTrue(self._backup(_FakeRclone(payload)).restore())

        self.assertTrue((self.data / "jobs/hybrid/job-123/manifest.json").is_file())
        self.assertEqual(
            ["42"],
            json.loads((self.data / "telegram-access.json").read_text(encoding="utf-8"))["users"],
        )

    def test_restore_retries_temporary_remote_failure_without_losing_state(self) -> None:
        payload = _archive({
            "jobs/hybrid/job-123/manifest.json": b'{"jobId":"job-123"}\n',
            "jobs/hybrid/job-123/recipe.json": b'{"schemaVersion":1}\n',
            "jobs/hybrid/job-123/events.jsonl": b'{"sequence":1}\n',
        })
        runner = _FakeRclone(payload, download_failures=2)

        self.assertTrue(self._backup(runner).restore())

        self.assertEqual(3, len(runner.commands))
        self.assertTrue((self.data / "jobs/hybrid/job-123/manifest.json").is_file())

    def test_missing_remote_snapshot_is_a_clean_first_start(self) -> None:
        self.assertFalse(self._backup(_FakeRclone()).restore())

    def test_restore_rejects_traversal_unknown_members_and_duplicates(self) -> None:
        invalid_payloads = [
            _archive({"../outside.json": b"bad"}),
            _archive({"Secrets/rclone.conf": b"bad"}),
        ]
        duplicate = BytesIO()
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("telegram-access.json", b"one")
            archive.writestr("telegram-access.json", b"two")
        invalid_payloads.append(duplicate.getvalue())

        for payload in invalid_payloads:
            with self.subTest(size=len(payload)):
                with self.assertRaises(ControlPlaneStateError):
                    self._backup(_FakeRclone(payload)).restore()

    def test_change_callbacks_are_compatible_with_state_backup_marker(self) -> None:
        backup = self._backup(_FakeRclone())
        self.assertFalse(backup._dirty.is_set())
        backup.mark_dirty()
        self.assertTrue(backup._dirty.is_set())


if __name__ == "__main__":
    unittest.main()

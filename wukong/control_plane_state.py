from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence


MAX_STATE_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_STATE_FILE_BYTES = 32 * 1024 * 1024
MAX_STATE_FILES = 10_000
STATE_FILE_NAMES = {"manifest.json", "recipe.json", "events.jsonl"}
STATE_ROOT_FILES = {"telegram-access.json", "telegram-ui-state.json"}
SAFE_JOB_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")


class ControlPlaneStateError(RuntimeError):
    pass


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


class ControlPlaneStateBackup:
    """Persist the small control-plane state tree on an rclone remote.

    Free container hosts use ephemeral local filesystems.  The ROM sources,
    build checkpoints, and artifacts already live in cloud storage; this
    snapshot contains only job manifests/recipes/events and Telegram UI/access
    preferences.  Runtime credentials are deliberately outside the allowlist.
    """

    def __init__(
        self,
        data_root: Path,
        *,
        remote: str,
        config_path: Path,
        remote_path: str = "WukongROM/control-plane/state-v1.zip",
        interval_seconds: float = 15.0,
        run_command: RunCommand = subprocess.run,
    ) -> None:
        self.data_root = data_root.resolve()
        self.remote = remote.strip().rstrip(":")
        self.config_path = config_path.resolve()
        normalized_remote_path = remote_path.replace("\\", "/").strip("/")
        remote_parts = PurePosixPath(normalized_remote_path).parts
        if (
            not self.remote
            or not normalized_remote_path
            or PurePosixPath(normalized_remote_path).is_absolute()
            or ".." in remote_parts
        ):
            raise ValueError("Control-plane state remote path is invalid")
        self.remote_uri = f"{self.remote}:{normalized_remote_path}"
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.run_command = run_command
        self._dirty = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._backup_lock = threading.Lock()
        self._last_backup = 0.0
        self._failure_count = 0
        self._retry_not_before = 0.0

    @classmethod
    def from_environment(cls, data_root: Path) -> ControlPlaneStateBackup | None:
        enabled = os.environ.get("WUKONG_CONTROL_PLANE_STATE_BACKUP_ENABLED", "").strip().casefold()
        if enabled not in {"1", "true", "yes", "on"}:
            return None
        config_value = os.environ.get("WUKONG_RCLONE_CONFIG", "").strip()
        config_path = Path(config_value).expanduser() if config_value else None
        if not config_path or not config_path.is_file():
            raise ControlPlaneStateError(
                "State backup is enabled but WUKONG_RCLONE_CONFIG is unavailable"
            )
        return cls(
            data_root,
            remote=os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive"),
            config_path=config_path,
            remote_path=os.environ.get(
                "WUKONG_CONTROL_PLANE_STATE_REMOTE_PATH",
                "WukongROM/control-plane/state-v1.zip",
            ),
            interval_seconds=float(
                os.environ.get("WUKONG_CONTROL_PLANE_STATE_BACKUP_INTERVAL", "15")
            ),
        )

    def mark_dirty(self) -> None:
        self._dirty.set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="wukong-control-plane-state-backup",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, flush: bool = True) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=min(self.interval_seconds + 5.0, 30.0))
        if flush and self._dirty.is_set():
            try:
                self.backup()
            except ControlPlaneStateError as exc:
                print(f"Control-plane state flush failed: {exc}", flush=True)

    def restore(self) -> bool:
        self.data_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wukong-state-restore-") as root:
            archive = Path(root) / "state.zip"
            result = self._rclone(
                "copyto",
                self.remote_uri,
                str(archive),
                "--retries",
                "2",
                "--low-level-retries",
                "2",
                check=False,
            )
            if result.returncode != 0:
                details = f"{result.stdout}\n{result.stderr}".casefold()
                if any(
                    marker in details
                    for marker in ("not found", "directory not found", "object not found")
                ):
                    print("No restorable control-plane state snapshot was found.", flush=True)
                    return False
                raise ControlPlaneStateError("rclone could not download the state snapshot")
            if not archive.is_file():
                raise ControlPlaneStateError("rclone reported success without a state snapshot")
            if archive.stat().st_size > MAX_STATE_ARCHIVE_BYTES:
                raise ControlPlaneStateError("Remote state snapshot exceeds the size limit")
            self._restore_archive(archive)
        print("Restored control-plane state from cloud storage.", flush=True)
        return True

    def backup(self) -> bool:
        with self._backup_lock:
            files = self._state_files()
            if not files:
                self._dirty.clear()
                return False
            with tempfile.TemporaryDirectory(prefix="wukong-state-backup-") as root:
                archive = Path(root) / "state.zip"
                with zipfile.ZipFile(
                    archive,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                    strict_timestamps=False,
                ) as output:
                    for path in files:
                        output.write(path, path.relative_to(self.data_root).as_posix())
                if archive.stat().st_size > MAX_STATE_ARCHIVE_BYTES:
                    raise ControlPlaneStateError("Local state snapshot exceeds the size limit")
                result = self._rclone(
                    "copyto",
                    str(archive),
                    self.remote_uri,
                    "--retries",
                    "3",
                    "--low-level-retries",
                    "3",
                    check=False,
                )
                if result.returncode != 0:
                    self._dirty.set()
                    raise ControlPlaneStateError("rclone could not upload the state snapshot")
            self._dirty.clear()
            self._last_backup = time.monotonic()
            self._failure_count = 0
            self._retry_not_before = 0.0
            print(f"Backed up {len(files)} control-plane state file(s).", flush=True)
            return True

    def _run_loop(self) -> None:
        while not self._stop.wait(1.0):
            if not self._dirty.is_set():
                continue
            now = time.monotonic()
            if now < self._retry_not_before or now - self._last_backup < self.interval_seconds:
                continue
            try:
                self.backup()
            except ControlPlaneStateError as exc:
                self._failure_count += 1
                self._retry_not_before = time.monotonic() + min(
                    300.0,
                    self.interval_seconds * (2 ** min(self._failure_count - 1, 5)),
                )
                print(f"Control-plane state backup deferred: {exc}", flush=True)

    def _state_files(self) -> list[Path]:
        files: list[Path] = []
        for name in sorted(STATE_ROOT_FILES):
            candidate = self.data_root / name
            if candidate.is_file() and candidate.stat().st_size <= MAX_STATE_FILE_BYTES:
                files.append(candidate)
        jobs = self.data_root / "jobs" / "hybrid"
        if jobs.is_dir():
            for candidate in sorted(jobs.glob("*/*")):
                if (
                    candidate.is_file()
                    and candidate.name in STATE_FILE_NAMES
                    and SAFE_JOB_ID.fullmatch(candidate.parent.name)
                ):
                    if candidate.stat().st_size > MAX_STATE_FILE_BYTES:
                        raise ControlPlaneStateError(
                            f"State file exceeds the size limit: {candidate.name}"
                        )
                    files.append(candidate)
                    if len(files) > MAX_STATE_FILES:
                        raise ControlPlaneStateError("State snapshot contains too many files")
        return files

    def _restore_archive(self, archive: Path) -> None:
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            if len(infos) > MAX_STATE_FILES:
                raise ControlPlaneStateError("Remote state snapshot contains too many files")
            total = 0
            names: set[str] = set()
            for info in infos:
                relative = PurePosixPath(info.filename.replace("\\", "/"))
                normalized = relative.as_posix()
                if normalized in names:
                    raise ControlPlaneStateError("Remote state snapshot contains duplicate files")
                names.add(normalized)
                if not self._allowed_member(relative):
                    raise ControlPlaneStateError(
                        f"Remote state snapshot contains an unsafe member: {info.filename}"
                    )
                if info.is_dir() or info.file_size > MAX_STATE_FILE_BYTES:
                    raise ControlPlaneStateError("Remote state snapshot contains an invalid file")
                unix_mode = (info.external_attr >> 16) & 0o170000
                if unix_mode == 0o120000:
                    raise ControlPlaneStateError("Remote state snapshot contains a symbolic link")
                total += info.file_size
                if total > MAX_STATE_ARCHIVE_BYTES:
                    raise ControlPlaneStateError("Remote state snapshot expands beyond the size limit")
            for info in infos:
                relative = PurePosixPath(info.filename.replace("\\", "/"))
                destination = self.data_root.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=destination.name + ".",
                    dir=destination.parent,
                )
                try:
                    with os.fdopen(descriptor, "wb") as output, source.open(info) as input_file:
                        while chunk := input_file.read(1024 * 1024):
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary_name, destination)
                finally:
                    Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _allowed_member(path: PurePosixPath) -> bool:
        if path.is_absolute() or ".." in path.parts:
            return False
        if len(path.parts) == 1:
            return path.name in STATE_ROOT_FILES
        return (
            len(path.parts) == 4
            and path.parts[:2] == ("jobs", "hybrid")
            and bool(SAFE_JOB_ID.fullmatch(path.parts[2]))
            and path.parts[3] in STATE_FILE_NAMES
        )

    def _rclone(self, *values: str, check: bool) -> subprocess.CompletedProcess[str]:
        command: Sequence[str] = (
            "rclone",
            *values,
            "--config",
            str(self.config_path),
            "--contimeout",
            "15s",
            "--timeout",
            "60s",
        )
        try:
            result = self.run_command(
                list(command),
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ControlPlaneStateError("rclone state operation could not run") from exc
        if check and result.returncode != 0:
            raise ControlPlaneStateError("rclone state operation failed")
        return result

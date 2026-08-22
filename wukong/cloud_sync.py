from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath

from .adapters import RcloneStorageAdapter
from .models import JobManifest, JobStatus
from .orchestrator import JobStore


class CloudJobSync:
    STATE_OPERATION_TIMEOUT_SECONDS = 8.0
    STATE_PULL_ATTEMPTS = 2
    PULL_WARNING_INTERVAL_SECONDS = 600.0
    # Instances are short-lived (one per refresh call), so the throttle lives
    # on the class to stay effective across requests within a process.
    _pull_warning_lock = threading.Lock()
    _pull_warning_at: dict[str, float] = {}

    def __init__(self, store: JobStore, storage: RcloneStorageAdapter) -> None:
        self.store = store
        self.storage = storage

    def push(self, job_id: str) -> None:
        manifest = self.store.get(job_id)
        if not manifest:
            return
        with tempfile.TemporaryDirectory(prefix="wukong-job-sync-") as root:
            directory = Path(root)
            manifest_path = directory / "manifest.json"
            events_path = directory / "events.jsonl"
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            events_path.write_text(
                "".join(
                    json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
                    for event in self.store.events(job_id)
                ),
                encoding="utf-8",
            )
            self.storage.copy_file(
                manifest_path,
                f"jobs/{job_id}/manifest.json",
                timeout=self.STATE_OPERATION_TIMEOUT_SECONDS,
            )
            self.storage.copy_file(
                events_path,
                f"jobs/{job_id}/events.jsonl",
                timeout=self.STATE_OPERATION_TIMEOUT_SECONDS,
            )

    def pull(self, job_id: str) -> JobManifest | None:
        local = self.store.get(job_id)
        if not local:
            return None
        if local.status == JobStatus.CANCELLED:
            return local
        remote, timed_out = self._read_remote_manifest(job_id)
        if remote is None:
            if timed_out:
                self._warn_stale_pull(job_id)
            return local
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        # A workflow that fails before the shared executor starts cannot
        # publish a newer Drive manifest. In that case the control plane
        # reconciles the terminal GitHub result itself; never let the old
        # queued Drive snapshot roll that terminal state backwards.
        if local.status in terminal and remote.status not in terminal:
            return local
        updated = self.store.update(
            job_id,
            status=remote.status,
            stage=remote.stage,
            progress=remote.progress,
            runner=remote.runner or local.runner,
            external_run_id=remote.external_run_id or local.external_run_id,
            checkpoint=remote.checkpoint,
            checkpoint_at=remote.checkpoint_at,
            artifacts=remote.artifacts,
            error=remote.error,
            finished_at=remote.finished_at,
        )
        self._merge_events(job_id)
        return updated

    def _read_remote_manifest(self, job_id: str) -> tuple[JobManifest | None, bool]:
        """Fetch the executor's manifest from cloud storage.

        Returns ``(manifest, timed_out)``. ``timed_out`` marks a state
        operation that exhausted every attempt against a slow/throttled
        transport; fast object errors (for example a job that failed before
        the executor published anything) are reported as a plain miss.
        """
        with tempfile.TemporaryDirectory(prefix="wukong-job-pull-") as root:
            destination = Path(root) / "manifest.json"
            args = self.storage._args(
                "copyto",
                self.storage.remote_uri(f"jobs/{job_id}/manifest.json"),
                str(destination),
                "--retries",
                "1",
            )
            timed_out = False
            for _attempt in range(max(1, self.STATE_PULL_ATTEMPTS)):
                try:
                    self.storage.run_command(
                        args,
                        timeout=self.STATE_OPERATION_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired:
                    timed_out = True
                    continue
                except Exception:
                    return None, False
                if not destination.is_file():
                    return None, False
                try:
                    remote = JobManifest.from_dict(
                        json.loads(destination.read_text(encoding="utf-8"))
                    )
                except (OSError, ValueError, json.JSONDecodeError):
                    return None, False
                return remote, False
            return None, timed_out

    def _warn_stale_pull(self, job_id: str) -> None:
        now = time.monotonic()
        with self._pull_warning_lock:
            last = self._pull_warning_at.get(job_id, 0.0)
            if now - last < self.PULL_WARNING_INTERVAL_SECONDS:
                return
            self._pull_warning_at[job_id] = now
        self.store.append_event(
            job_id,
            "warning",
            source="cloud-pull",
            warning=(
                "Cloud state sync is temporarily unreachable "
                f"(state timeout after {int(self.STATE_PULL_ATTEMPTS)} attempts); "
                "keeping the last known job status."
            ),
        )

    def pull_checkpoint(self, job_id: str) -> JobManifest | None:
        local = self.store.get(job_id)
        if not local:
            return None
        with tempfile.TemporaryDirectory(prefix="wukong-checkpoint-pull-") as root:
            destination = Path(root) / "manifest.json"
            try:
                self.storage.run_command(
                    self.storage._args(
                        "copyto",
                        self.storage.remote_uri(f"jobs/{job_id}/manifest.json"),
                        str(destination),
                        "--retries",
                        "1",
                    ),
                    timeout=self.STATE_OPERATION_TIMEOUT_SECONDS,
                )
            except Exception:
                return local
            if not destination.is_file():
                return local
            try:
                remote = JobManifest.from_dict(json.loads(destination.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError):
                return local
            if (
                remote.job_id != local.job_id
                or remote.recipe_digest != local.recipe_digest
                or remote.owner != local.owner
            ):
                return local
            if not remote.checkpoint:
                return local
            try:
                checkpoint_time = datetime.fromisoformat(
                    str(remote.checkpoint_at or "").replace("Z", "+00:00")
                )
            except ValueError:
                return local
            if (
                checkpoint_time.tzinfo is None
                or datetime.now(timezone.utc) - checkpoint_time > timedelta(days=7)
                or checkpoint_time - datetime.now(timezone.utc) > timedelta(minutes=5)
            ):
                return local
            prefix = f"{self.storage.remote}:WukongROM/checkpoints/"
            if not remote.checkpoint.startswith(prefix):
                return local
            checkpoint_path = PurePosixPath(remote.checkpoint[len(prefix) :].replace("\\", "/"))
            if (
                not checkpoint_path.parts
                or checkpoint_path.is_absolute()
                or ".." in checkpoint_path.parts
                or not remote.checkpoint.casefold().endswith(".tar")
            ):
                return local
            return self.store.update(
                job_id,
                checkpoint=remote.checkpoint,
                checkpoint_at=remote.checkpoint_at,
            )

    def _merge_events(self, job_id: str) -> None:
        with tempfile.TemporaryDirectory(prefix="wukong-events-pull-") as root:
            destination = Path(root) / "events.jsonl"
            try:
                self.storage.run_command(
                    self.storage._args(
                        "copyto",
                        self.storage.remote_uri(f"jobs/{job_id}/events.jsonl"),
                        str(destination),
                        "--retries",
                        "1",
                    ),
                    timeout=self.STATE_OPERATION_TIMEOUT_SECONDS,
                )
            except Exception:
                return
            if not destination.is_file():
                return
            imported_sequences = {
                int(event.payload["remoteSequence"])
                for event in self.store.events(job_id)
                if isinstance(event.payload.get("remoteSequence"), int)
            }
            try:
                entries = destination.read_text(encoding="utf-8").splitlines()
                for line in entries:
                    item = json.loads(line)
                    sequence = int(item.get("sequence") or 0)
                    if sequence <= 0 or sequence in imported_sequences:
                        continue
                    known = {"sequence", "jobId", "timestamp", "type"}
                    payload = {key: value for key, value in item.items() if key not in known}
                    payload["remoteSequence"] = sequence
                    self.store.append_event(job_id, str(item.get("type") or "remote"), **payload)
            except (OSError, ValueError, json.JSONDecodeError):
                return

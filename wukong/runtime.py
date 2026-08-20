from __future__ import annotations

import base64
import os
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .adapters import RcloneStorageAdapter, sha256_file
from .executor import LocalJobExecutor
from .github import GitHubActionsAdapter
from .cloud_sync import CloudJobSync
from .models import BuildRecipe, Identity, JobManifest, JobStatus, SourceSpec
from .orchestrator import HybridOrchestrator, JobStore


class HybridRuntime:
    CLOUD_WATCH_MAX_AGE_SECONDS = 12 * 60 * 60

    def __init__(
        self,
        *,
        orchestrator: HybridOrchestrator,
        store: JobStore,
        workspace_root: Path,
        data_root: Path,
        content_root: Path | None = None,
        content_index: Path | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.store = store
        self.workspace_root = workspace_root.resolve()
        self.content_root = content_root.resolve() if content_root else None
        self.content_index = content_index.resolve() if content_index else None
        self.rclone_config = self._materialize_rclone_config(data_root)

    def start(self, manifest: JobManifest) -> None:
        worker = threading.Thread(
            target=self._execute_local if manifest.runner == "windows" else self._dispatch_github,
            args=(manifest.job_id,),
            name=f"wukong-hybrid-{manifest.job_id[:8]}",
            daemon=True,
        )
        worker.start()

    def resume_cloud_watchers(self) -> int:
        """Resume cloud-state polling for jobs that survived a daemon restart."""
        if not self.rclone_config:
            return 0
        resumed = 0
        for manifest in self.store.list():
            if manifest.runner == "windows" or manifest.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                continue
            if self._cloud_watch_expired(manifest):
                continue
            recipe = self.store.recipe(manifest.job_id)
            if not recipe:
                continue
            storage = RcloneStorageAdapter(
                remote=recipe.storage.remote,
                config_path=self.rclone_config,
            )
            watcher = threading.Thread(
                target=self._watch_cloud_job,
                args=(manifest.job_id, storage),
                name=f"wukong-cloud-watch-{manifest.job_id[:8]}",
                daemon=True,
            )
            watcher.start()
            resumed += 1
        return resumed

    def refresh(self, manifest: JobManifest) -> JobManifest:
        if manifest.runner == "windows" or not self.rclone_config:
            return self.store.get(manifest.job_id) or manifest
        recipe = self.store.recipe(manifest.job_id)
        if not recipe:
            return manifest
        return (
            CloudJobSync(
                self.store,
                RcloneStorageAdapter(remote=recipe.storage.remote, config_path=self.rclone_config),
            ).pull(manifest.job_id)
            or manifest
        )

    def cloud_library(self, *, category: str = "artifacts") -> dict[str, object]:
        if category not in {"sources", "artifacts"}:
            raise ValueError("Cloud library category must be sources or artifacts")
        if not self.rclone_config:
            return {"available": False, "category": category, "entries": []}
        remote = os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive").strip() or "wukong-gdrive"
        storage = RcloneStorageAdapter(remote=remote, config_path=self.rclone_config)
        return {
            "available": True,
            "category": category,
            "entries": storage.list_library(category),
        }

    def cancel_external(self, manifest: JobManifest) -> None:
        if manifest.runner == "windows":
            return
        token = os.environ.get("WUKONG_GITHUB_TOKEN", "").strip()
        repository = os.environ.get("WUKONG_GITHUB_REPOSITORY", "").strip()
        if not token or "/" not in repository:
            return
        owner, name = repository.split("/", 1)
        try:
            github = GitHubActionsAdapter(owner, name, token)
            run_id = manifest.external_run_id or github.cancel_job("wukong-build.yml", manifest.job_id)
            if run_id is not None:
                if manifest.external_run_id:
                    github.cancel(run_id)
                self.store.update(manifest.job_id, external_run_id=run_id)
        except Exception as exc:
            self.store.append_event(manifest.job_id, "warning", warning=str(exc))

    def resume(self, job_id: str, identity: Identity) -> JobManifest:
        # Keep orchestration and runtime startup in one operation for control
        # adapters so a successful resume can never remain queued accidentally.
        resumed = self.orchestrator.resume(job_id, identity)
        self.start(resumed)
        return resumed

    def _execute_local(self, job_id: str) -> None:
        LocalJobExecutor(
            store=self.store,
            workspace_root=self.workspace_root,
            rclone_config=self.rclone_config,
            build_workspace_root=self.workspace_root.parent.parent,
            content_root=self.content_root,
            content_index=self.content_index,
        ).execute(job_id)

    def _dispatch_github(self, job_id: str) -> None:
        recipe = self.store.recipe(job_id)
        if not recipe:
            self._fail(job_id, "Job recipe is unavailable")
            return
        token = self._github_token()
        repository = os.environ.get("WUKONG_GITHUB_REPOSITORY", "").strip()
        missing = []
        if not token:
            missing.append("GitHub authentication (WUKONG_GITHUB_TOKEN or gh auth login)")
        if "/" not in repository:
            missing.append("WUKONG_GITHUB_REPOSITORY=owner/repository")
        if not self.rclone_config:
            missing.append("rclone configuration")
        if missing:
            self._fail(job_id, "Cloud dispatch is not configured: " + "; ".join(missing))
            return
        try:
            self.store.update(job_id, status=JobStatus.PREFLIGHT, stage="cloud-dispatch")
            storage = RcloneStorageAdapter(
                remote=recipe.storage.remote,
                config_path=self.rclone_config,
            )
            dispatch_recipe = recipe
            if recipe.source.kind == "local":
                source = Path(recipe.source.uri).expanduser().resolve()
                if not source.is_file():
                    raise FileNotFoundError(source)
                digest = recipe.source.sha256 or sha256_file(source)
                source_record = storage.store_source(source, device=recipe.device, digest=digest)
                dispatch_recipe = replace(
                    recipe,
                    source=SourceSpec(
                        kind="rclone",
                        uri=source_record.uri,
                        sha256=digest,
                        size_bytes=source.stat().st_size,
                    ),
                )
            recipe_path = self.workspace_root / job_id / "dispatch-recipe.json"
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(dispatch_recipe.canonical_json + "\n", encoding="utf-8")
            recipe_ref = storage.copy_file(recipe_path, f"recipes/{job_id}.json")
            owner, name = repository.split("/", 1)
            github = GitHubActionsAdapter(owner, name, token)
            self.store.update(job_id, status=JobStatus.QUEUED, stage="github-actions")
            self.store.append_event(job_id, "dispatched", recipeRef=recipe_ref)
            CloudJobSync(self.store, storage).push(job_id)
            github.dispatch(
                "wukong-build.yml",
                recipe_ref=recipe_ref,
                job_id=job_id,
            )
            # The dispatch request is the point of no return: once GitHub has
            # accepted it, a temporary failure while looking the run back up
            # must not mark the local job as failed.  The workflow may already
            # be building (and will keep publishing its state through Drive),
            # so retain a truthful queued state and let refresh/cancel retry.
            try:
                run_id = github.find_run("wukong-build.yml", job_id)
            except Exception as exc:
                run_id = None
                self.store.append_event(
                    job_id,
                    "warning",
                    warning=f"Workflow was dispatched but its run ID is not available yet: {exc}",
                )
            self.store.update(
                job_id,
                status=JobStatus.QUEUED,
                stage="github-actions",
                external_run_id=run_id,
            )
            watcher = threading.Thread(
                target=self._watch_cloud_job,
                args=(job_id, storage),
                name=f"wukong-cloud-watch-{job_id[:8]}",
                daemon=True,
            )
            watcher.start()
        except Exception as exc:
            self._fail(job_id, str(exc))

    def _watch_cloud_job(self, job_id: str, storage: RcloneStorageAdapter) -> None:
        sync = CloudJobSync(self.store, storage)
        failures = 0
        while True:
            manifest = self.store.get(job_id)
            if not manifest or manifest.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                return
            if self._cloud_watch_expired(manifest):
                self.store.append_event(
                    job_id,
                    "warning",
                    warning="Cloud watcher stopped after 12 hours without a terminal state",
                )
                return
            before = self._cloud_progress_key(manifest)
            refreshed = sync.pull(job_id)
            if refreshed and self._cloud_progress_key(refreshed) != before:
                failures = 0
            else:
                failures += 1
            # A temporary Drive/API outage must not turn a running job into a
            # failure; interactive inspect calls continue to retry as well.
            time.sleep(5 if failures < 12 else 30)

    @classmethod
    def _cloud_watch_expired(cls, manifest: JobManifest) -> bool:
        try:
            created = datetime.fromisoformat(manifest.created_at.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return True
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).total_seconds() > cls.CLOUD_WATCH_MAX_AGE_SECONDS

    @staticmethod
    def _cloud_progress_key(manifest: JobManifest) -> tuple[object, ...]:
        return (
            manifest.status,
            manifest.stage,
            manifest.progress,
            manifest.checkpoint,
            manifest.finished_at,
            manifest.error,
            tuple((item.name, item.uri, item.sha256, item.public_url) for item in manifest.artifacts),
        )

    def _fail(self, job_id: str, error: str) -> None:
        self.store.append_event(job_id, "error", error=error)
        self.store.update(job_id, status=JobStatus.FAILED, stage="dispatch-failed", error=error)

    @staticmethod
    def _github_token() -> str:
        for name in ("WUKONG_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            token = os.environ.get(name, "").strip()
            if token:
                return token
        executable = shutil.which("gh")
        if not executable:
            return ""
        options: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "timeout": 10,
            "check": False,
        }
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            completed = subprocess.run([executable, "auth", "token"], **options)
        except (OSError, subprocess.SubprocessError):
            return ""
        return completed.stdout.strip() if completed.returncode == 0 else ""

    @staticmethod
    def _materialize_rclone_config(data_root: Path) -> Path | None:
        encoded = os.environ.get("WUKONG_RCLONE_CONFIG_CONTENT_B64", "").strip()
        configured = os.environ.get("WUKONG_RCLONE_CONFIG", "").strip()
        if configured and Path(configured).is_file():
            return Path(configured).resolve()
        if not encoded:
            return None
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError:
            return None
        path = data_root.resolve() / "Secrets" / "rclone.runtime.conf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path

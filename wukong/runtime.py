from __future__ import annotations

import base64
import os
import threading
import time
from dataclasses import replace
from pathlib import Path

from .adapters import RcloneStorageAdapter, sha256_file
from .executor import LocalJobExecutor
from .github import GitHubActionsAdapter
from .cloud_sync import CloudJobSync
from .models import BuildRecipe, Identity, JobManifest, JobStatus, SourceSpec
from .orchestrator import HybridOrchestrator, JobStore


class HybridRuntime:
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
        token = os.environ.get("WUKONG_GITHUB_TOKEN", "").strip()
        repository = os.environ.get("WUKONG_GITHUB_REPOSITORY", "").strip()
        if not token or "/" not in repository or not self.rclone_config:
            self._fail(job_id, "GitHub or rclone credentials are not configured")
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
            run_id = github.find_run("wukong-build.yml", job_id)
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
            refreshed = sync.pull(job_id)
            if refreshed and refreshed.updated_at != manifest.updated_at:
                failures = 0
            else:
                failures += 1
            # A temporary Drive/API outage must not turn a running job into a
            # failure; interactive inspect calls continue to retry as well.
            time.sleep(5 if failures < 12 else 30)

    def _fail(self, job_id: str, error: str) -> None:
        self.store.append_event(job_id, "error", error=error)
        self.store.update(job_id, status=JobStatus.FAILED, stage="dispatch-failed", error=error)

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

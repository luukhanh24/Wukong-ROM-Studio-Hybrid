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
from typing import Callable

from .adapters import RcloneStorageAdapter, sha256_file
from .executor import LocalJobExecutor
from .github import GitHubActionsAdapter, GitHubApiError
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
        terminal_notifier: Callable[[JobManifest, BuildRecipe], None] | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.store = store
        self.workspace_root = workspace_root.resolve()
        self.content_root = content_root.resolve() if content_root else None
        self.content_index = content_index.resolve() if content_index else None
        self.terminal_notifier = terminal_notifier
        self._notification_lock = threading.RLock()
        self._github_refresh_lock = threading.RLock()
        self._github_refresh_at: dict[str, float] = {}
        self._cloud_refresh_lock = threading.RLock()
        self._cloud_refresh_inflight: set[str] = set()
        self.rclone_config = self._materialize_rclone_config(data_root)
        self.cloud_watchers_enabled = os.environ.get(
            "WUKONG_CONTROL_PLANE_BACKGROUND_WATCHERS", "true"
        ).strip().casefold() not in {"0", "false", "no", "off"}

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
        if not self.rclone_config or not self.cloud_watchers_enabled:
            return 0
        resumed = 0
        for manifest in self.store.list():
            if manifest.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                self.notify_terminal(manifest)
                continue
            if manifest.runner == "windows":
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

    def refresh(self, manifest: JobManifest, *, force_cloud: bool = False) -> JobManifest:
        if manifest.runner == "windows" or not self.rclone_config:
            return self.store.get(manifest.job_id) or manifest
        recipe = self.store.recipe(manifest.job_id)
        if not recipe:
            return manifest
        storage = RcloneStorageAdapter(
            remote=recipe.storage.remote,
            config_path=self.rclone_config,
        )
        sync = CloudJobSync(self.store, storage)
        # Background watchers already keep the durable store synchronized with
        # the executor's Drive manifest. Avoid blocking every interactive API
        # request on a fresh rclone process; Render/Drive can occasionally take
        # the full retry timeout even though the workflow is healthy. Terminal
        # callbacks force one pull so artifact delivery and notification still
        # observe the executor's final manifest before returning.
        refreshed = self.store.get(manifest.job_id) or manifest
        if force_cloud:
            refreshed = sync.pull(manifest.job_id) or refreshed
        refreshed = self._refresh_github_state(refreshed, sync=sync)
        if (
            not force_cloud
            and not self.cloud_watchers_enabled
            and refreshed.status not in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }
        ):
            self._schedule_cloud_refresh(refreshed.job_id, storage)
        if manifest.status not in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            self.notify_terminal(refreshed)
        return refreshed

    def _schedule_cloud_refresh(
        self,
        job_id: str,
        storage: RcloneStorageAdapter,
    ) -> None:
        """Refresh Drive state lazily without delaying an interactive request."""
        with self._cloud_refresh_lock:
            if job_id in self._cloud_refresh_inflight:
                return
            self._cloud_refresh_inflight.add(job_id)
        threading.Thread(
            target=self._refresh_cloud_job_once,
            args=(job_id, storage),
            name=f"wukong-cloud-refresh-{job_id[:8]}",
            daemon=True,
        ).start()

    def _refresh_cloud_job_once(
        self,
        job_id: str,
        storage: RcloneStorageAdapter,
    ) -> None:
        try:
            refreshed = CloudJobSync(self.store, storage).pull(job_id)
            if refreshed is not None:
                self.notify_terminal(refreshed)
        finally:
            with self._cloud_refresh_lock:
                self._cloud_refresh_inflight.discard(job_id)

    def reconcile_actions_callback(
        self,
        manifest: JobManifest,
        *,
        run_id: int,
        conclusion: str,
    ) -> JobManifest:
        """Apply the authenticated result reported by the workflow's final job."""
        current = self.store.get(manifest.job_id) or manifest
        if current.external_run_id != run_id:
            current = self.store.update(current.job_id, external_run_id=run_id)
            self.store.append_event(current.job_id, "github_run", runId=run_id)
        normalized = conclusion.strip().casefold()
        if normalized in {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}:
            current = self._finish_github_failure(current, normalized, run_id=run_id)
        return current

    def verify_actions_bearer(
        self,
        token: str,
        run_id: int,
        claimed_conclusion: str = "",
    ) -> str:
        """Validate an Actions callback bearer token against GitHub itself.

        The runner presents its own repository token; trusting the run only
        after GitHub confirms it keeps callback authentication immune to a
        desynchronized copy of the token stored on the control plane.
        The terminal callback is itself the workflow's final job, so GitHub
        reports the run as ``in_progress`` until this request returns. In that
        state, accept the final job's already-normalized conclusion only after
        GitHub confirms that the short-lived runner token can read this run.
        """
        repository = os.environ.get("WUKONG_GITHUB_REPOSITORY", "").strip()
        owner, separator, name = repository.partition("/")
        if not separator or not name:
            raise PermissionError("Actions callback is not bound to a repository")
        github = GitHubActionsAdapter(owner.strip(), name.strip(), token)
        try:
            state = github.run_state(run_id)
        except (GitHubApiError, OSError, ValueError) as exc:
            raise PermissionError("Actions callback authentication failed") from exc
        allowed = {
            "success",
            "failure",
            "cancelled",
            "timed_out",
            "action_required",
            "startup_failure",
        }
        status = str(state.get("status") or "").casefold()
        conclusion = str(state.get("conclusion") or "").casefold()
        if status == "in_progress":
            conclusion = claimed_conclusion.strip().casefold()
        elif status != "completed":
            raise PermissionError("Actions callback run is not ready for its terminal callback")
        if conclusion not in allowed:
            raise PermissionError("Actions callback run has no usable conclusion")
        return conclusion

    def notify_terminal(self, manifest: JobManifest) -> None:
        if manifest.status not in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        } or self.terminal_notifier is None or manifest.owner.channel != "telegram":
            return
        recipe = self.store.recipe(manifest.job_id)
        if not recipe or not recipe.build.notify_telegram:
            return
        with self._notification_lock:
            if any(
                event.type == "telegram_terminal_notified"
                for event in self.store.events(manifest.job_id)
            ):
                return
            try:
                self.terminal_notifier(manifest, recipe)
                self.store.append_event(
                    manifest.job_id,
                    "telegram_terminal_notified",
                    status=manifest.status.value,
                    recipient=manifest.owner.subject,
                )
            except Exception as exc:
                self.store.append_event(
                    manifest.job_id,
                    "warning",
                    warning=f"Terminal Telegram notification failed: {exc}",
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
        result = LocalJobExecutor(
            store=self.store,
            workspace_root=self.workspace_root,
            rclone_config=self.rclone_config,
            build_workspace_root=self.workspace_root.parent.parent,
            content_root=self.content_root,
            content_index=self.content_index,
        ).execute(job_id)
        self.notify_terminal(result)

    def _dispatch_github(self, job_id: str) -> None:
        recipe = self.store.recipe(job_id)
        if not recipe:
            self._fail_before_dispatch(job_id, "Job recipe is unavailable")
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
            self._fail_before_dispatch(job_id, "Cloud dispatch is not configured: " + "; ".join(missing))
            return
        dispatched = False
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
                        metadata=recipe.source.metadata,
                    ),
                )
            recipe_path = self.workspace_root / job_id / "dispatch-recipe.json"
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(dispatch_recipe.canonical_json + "\n", encoding="utf-8")
            recipe_ref = storage.copy_file(
                recipe_path,
                f"recipes/{job_id}.json",
                timeout=60.0,
            )
            owner, name = repository.split("/", 1)
            github = GitHubActionsAdapter(owner, name, token)
            self.store.update(job_id, status=JobStatus.QUEUED, stage="github-actions")
            github.dispatch(
                "wukong-build.yml",
                recipe_ref=recipe_ref,
                job_id=job_id,
            )
            dispatched = True
            self.store.append_event(job_id, "dispatched", recipeRef=recipe_ref)
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
            if run_id is not None:
                self.store.append_event(job_id, "github_run", runId=run_id)
            # Do not upload this queued manifest after dispatch. The runner may
            # already have published a newer running manifest while find_run
            # was polling; a late queued upload would roll cloud progress back.
            # The private recipe is already on Drive and the control-plane
            # state backup persists this local manifest independently.
            if self.cloud_watchers_enabled:
                watcher = threading.Thread(
                    target=self._watch_cloud_job,
                    args=(job_id, storage),
                    name=f"wukong-cloud-watch-{job_id[:8]}",
                    daemon=True,
                )
                watcher.start()
        except Exception as exc:
            if dispatched:
                try:
                    self.store.append_event(
                        job_id,
                        "warning",
                        warning=f"Workflow was accepted but local dispatch finalization failed: {exc}",
                    )
                except Exception:
                    pass
            else:
                self._fail_before_dispatch(job_id, str(exc))

    def _fail_before_dispatch(self, job_id: str, error: str) -> None:
        manifest = self.store.get(job_id)
        if manifest is not None:
            try:
                self.orchestrator.compensate_submission(
                    manifest.owner,
                    job_id,
                    error,
                    retain_job=True,
                )
            except Exception as exc:
                self.store.append_event(
                    job_id,
                    "warning",
                    warning=f"Build-credit compensation failed: {exc}",
                )
        self._fail(job_id, error)

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
            if refreshed and refreshed.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                self.notify_terminal(refreshed)
                return
            # A temporary Drive/API outage must not turn a running job into a
            # failure; interactive inspect calls continue to retry as well.
            time.sleep(5 if failures < 12 else 30)

    def _refresh_github_state(
        self,
        manifest: JobManifest,
        *,
        sync: CloudJobSync,
    ) -> JobManifest:
        if manifest.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return manifest
        now = time.monotonic()
        with self._github_refresh_lock:
            if now - self._github_refresh_at.get(manifest.job_id, 0.0) < 15.0:
                return manifest
            self._github_refresh_at[manifest.job_id] = now
        token = self._github_token()
        repository = os.environ.get("WUKONG_GITHUB_REPOSITORY", "").strip()
        if not token or "/" not in repository:
            return manifest
        owner, name = repository.split("/", 1)
        github = GitHubActionsAdapter(owner, name, token)
        try:
            run_id = manifest.external_run_id or github.find_run(
                "wukong-build.yml",
                manifest.job_id,
                attempts=1,
                delay=0,
            )
            if run_id is None:
                return manifest
            if manifest.external_run_id != run_id:
                manifest = self.store.update(manifest.job_id, external_run_id=run_id)
                self.store.append_event(manifest.job_id, "github_run", runId=run_id)
            state = github.run_state(run_id)
            github_status = str(state.get("status") or "").casefold()
            if github_status != "completed":
                # Drive remains the source of exact stage progress. This
                # GitHub fallback prevents a temporarily slow Drive pull from
                # leaving an actively executing workflow displayed as queued.
                if github_status == "in_progress" and manifest.status == JobStatus.QUEUED:
                    manifest = self.store.update(
                        manifest.job_id,
                        status=JobStatus.RUNNING,
                        stage="github-actions-running",
                        progress=max(manifest.progress, 0.02),
                    )
                    self.store.append_event(
                        manifest.job_id,
                        "running",
                        stage="github-actions-running",
                    )
                return manifest
            conclusion = str(state.get("conclusion") or "failure")
            if conclusion in {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}:
                terminal = self._finish_github_failure(
                    manifest,
                    conclusion,
                    run_id=run_id,
                    run_url=str(state.get("url") or ""),
                )
                try:
                    sync.push(terminal.job_id)
                except Exception as exc:
                    self.store.append_event(
                        terminal.job_id,
                        "warning",
                        warning=f"Terminal GitHub state could not be synchronized to Drive: {exc}",
                    )
                return terminal
            return manifest
        except Exception as exc:
            # Interactive refresh remains available during a temporary GitHub
            # outage. Avoid adding a warning every 15 seconds to the timeline.
            if not any(
                event.type == "warning" and event.payload.get("source") == "github-refresh"
                for event in self.store.events(manifest.job_id)
            ):
                self.store.append_event(
                    manifest.job_id,
                    "warning",
                    source="github-refresh",
                    warning=f"GitHub run status is temporarily unavailable: {exc}",
                )
            return self.store.get(manifest.job_id) or manifest

    def _finish_github_failure(
        self,
        manifest: JobManifest,
        conclusion: str,
        *,
        run_id: int,
        run_url: str = "",
    ) -> JobManifest:
        if manifest.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return manifest
        cancelled = conclusion == "cancelled"
        label = "cancelled" if cancelled else f"failed ({conclusion})"
        suffix = f" See {run_url}" if run_url else ""
        error = f"GitHub Actions {label} before a terminal build result was synchronized.{suffix}"
        self.store.append_event(
            manifest.job_id,
            "error",
            error=error,
            externalRunId=run_id,
            runUrl=run_url or None,
        )
        terminal = self.store.update(
            manifest.job_id,
            status=JobStatus.CANCELLED if cancelled else JobStatus.FAILED,
            stage="github-actions-failed",
            external_run_id=run_id,
            error=error,
        )
        self.notify_terminal(terminal)
        return terminal

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
            tuple(
                (
                    item.name,
                    item.uri,
                    item.sha256,
                    item.public_url,
                    tuple((mirror.provider, mirror.status, mirror.uri, mirror.browse_url) for mirror in item.mirrors),
                )
                for item in manifest.artifacts
            ),
        )

    def _fail(self, job_id: str, error: str) -> None:
        self.store.append_event(job_id, "error", error=error)
        failed = self.store.update(
            job_id,
            status=JobStatus.FAILED,
            stage="dispatch-failed",
            error=error,
        )
        self.notify_terminal(failed)

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

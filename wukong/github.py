from __future__ import annotations

import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .routing import RunnerInventory, SELF_HOSTED_LABELS


Transport = Callable[[str, str, dict[str, object] | None], object]


class GitHubApiError(RuntimeError):
    pass


class GitHubActionsAdapter:
    def __init__(
        self,
        owner: str,
        repository: str,
        token: str,
        *,
        transport: Transport | None = None,
        api_url: str = "https://api.github.com",
    ) -> None:
        if not owner or not repository or not token:
            raise ValueError("GitHub owner, repository, and token are required")
        self.owner = owner
        self.repository = repository
        self._token = token
        self.api_url = api_url.rstrip("/")
        self.transport = transport or self._request

    @property
    def repo_url(self) -> str:
        return f"{self.api_url}/repos/{self.owner}/{self.repository}"

    def dispatch(
        self,
        workflow: str,
        *,
        recipe_ref: str,
        job_id: str | None = None,
        ref: str = "main",
    ) -> None:
        inputs = {"recipe_ref": recipe_ref}
        if job_id:
            inputs["job_id"] = job_id
        self._call(
            "POST",
            f"{self.repo_url}/actions/workflows/{workflow}/dispatches",
            {"ref": ref, "inputs": inputs},
        )

    def cancel(self, run_id: int) -> None:
        self._call("POST", f"{self.repo_url}/actions/runs/{int(run_id)}/cancel", None)

    def cancel_job(self, workflow: str, job_id: str) -> int | None:
        run_id = self.find_run(workflow, job_id, attempts=1, delay=0)
        if run_id is not None:
            self.cancel(run_id)
        return run_id

    def find_run(self, workflow: str, job_id: str, *, attempts: int = 12, delay: float = 5.0) -> int | None:
        # Keep this in sync with ``run-name`` in wukong-build.yml. The legacy
        # title remains accepted so an upgraded control plane can still find
        # runs created by an older workflow revision.
        expected = {f"{job_id} · Wukong Hybrid", f"Wukong {job_id}"}
        for attempt in range(max(1, attempts)):
            result = self._call(
                "GET",
                f"{self.repo_url}/actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=30",
                None,
            )
            runs = result.get("workflow_runs", []) if isinstance(result, dict) else []
            for run in runs:
                if isinstance(run, dict) and run.get("display_title") in expected:
                    return int(run["id"])
            if attempt + 1 < attempts:
                time.sleep(delay)
        return None

    def run_state(self, run_id: int) -> dict[str, str | None]:
        result = self._call("GET", f"{self.repo_url}/actions/runs/{int(run_id)}", None)
        if not isinstance(result, dict):
            raise GitHubApiError("GitHub returned an invalid workflow run response")
        return {
            "status": str(result.get("status") or "").casefold() or None,
            "conclusion": str(result.get("conclusion") or "").casefold() or None,
            "url": str(result.get("html_url") or "") or None,
        }

    def runner_inventory(self) -> RunnerInventory:
        try:
            result = self._call("GET", f"{self.repo_url}/actions/runners?per_page=100", None)
        except GitHubApiError as exc:
            # The workflow-scoped GITHUB_TOKEN can dispatch and inspect runs,
            # but GitHub does not grant it repository runner-administration
            # permission. Runner discovery is an optional optimization for
            # github-auto, so an authorization failure means "no usable
            # self-hosted runner is visible" rather than aborting the build.
            if "HTTP 403" not in str(exc):
                raise
            return RunnerInventory(False)
        entries = result.get("runners", []) if isinstance(result, dict) else []
        required = set(SELF_HOSTED_LABELS)
        online = False
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("status") != "online":
                continue
            labels = {
                str(label.get("name"))
                for label in entry.get("labels", [])
                if isinstance(label, dict) and label.get("name")
            }
            if required.issubset(labels):
                online = True
                break
        # GitHub's repository runner API does not expose hardware. The workflow
        # executes a second local preflight and reports its measured resources.
        return RunnerInventory(
            self_hosted_online=online,
            free_disk_bytes=150 * 1024**3 if online else 0,
            memory_bytes=16 * 1024**3 if online else 0,
            logical_cpus=8 if online else 0,
        )

    def _call(self, method: str, url: str, payload: dict[str, object] | None) -> object:
        try:
            return self.transport(method, url, payload)
        except Exception as exc:
            message = str(exc).replace(self._token, "[redacted]")
            raise GitHubApiError(f"GitHub API request failed: {message}") from exc

    def _request(self, method: str, url: str, payload: dict[str, object] | None = None) -> object:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Wukong-ROM-Studio/1",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitHubApiError(f"GitHub returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GitHubApiError(f"GitHub is unavailable: {exc.reason}") from exc

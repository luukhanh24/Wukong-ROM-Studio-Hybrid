from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

import requests


REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
RELEASE_RE = re.compile(r"[0-9a-f]{40}\Z")
RENDER_HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com\Z")


class RenderBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderBinding:
    repository: str
    token: str
    api_url: str
    release_sha: str
    mini_app_url: str
    branch: str = "main"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.api_url.rstrip("/"))
        mini_app = urlsplit(self.mini_app_url)
        if (
            not REPOSITORY_RE.fullmatch(self.repository)
            or len(self.token) < 20
            or parsed.scheme.casefold() != "https"
            or not parsed.hostname
            or not RENDER_HOST_RE.fullmatch(parsed.hostname.casefold())
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or not RELEASE_RE.fullmatch(self.release_sha.casefold())
            or not re.fullmatch(r"[A-Za-z0-9._/-]{1,255}", self.branch)
            or mini_app.scheme.casefold() != "https"
            or not mini_app.hostname
            or mini_app.username
            or mini_app.password
            or mini_app.query
            or mini_app.fragment
        ):
            raise ValueError("Render binding configuration is invalid")


class RenderOriginBinder:
    VARIABLE_NAME = "WUKONG_TELEGRAM_MINI_APP_API_URL"
    PAGES_WORKFLOW = "telegram-mini-app-pages.yml"

    def __init__(
        self,
        binding: RenderBinding,
        *,
        http: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.binding = binding
        self.http = http or requests.Session()
        self.sleep = sleep
        self._thread: threading.Thread | None = None

    def start(self, *, attempts: int = 20, delay_seconds: float = 30.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self.bind_with_retry,
            kwargs={"attempts": attempts, "delay_seconds": delay_seconds},
            name="wukong-render-origin-binder",
            daemon=True,
        )
        self._thread.start()

    def bind_with_retry(self, *, attempts: int = 20, delay_seconds: float = 30.0) -> bool:
        for attempt in range(1, max(1, attempts) + 1):
            try:
                self.bind_once()
                print(
                    f"Bound Render control plane to Vercel: {self.binding.api_url.rstrip('/')}",
                    flush=True,
                )
                return True
            except RenderBindingError as exc:
                if attempt >= max(1, attempts):
                    print(f"Render origin binding failed: {exc}", flush=True)
                    return False
                self.sleep(max(1.0, delay_seconds))
        return False

    def bind_once(self) -> None:
        base = f"https://api.github.com/repos/{self.binding.repository}"
        variable = f"{base}/actions/variables/{self.VARIABLE_NAME}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.binding.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Wukong-ROM-Studio-Control-Plane",
        }
        try:
            current = self.http.get(variable, headers=headers, timeout=20)
            if current.status_code == 404:
                changed = self.http.post(
                    f"{base}/actions/variables",
                    headers=headers,
                    json={"name": self.VARIABLE_NAME, "value": self.binding.api_url.rstrip("/")},
                    timeout=20,
                )
                if changed.status_code != 201:
                    raise RenderBindingError(
                        f"GitHub rejected repository variable creation (HTTP {changed.status_code})"
                    )
            elif current.status_code == 200:
                payload = current.json()
                same_origin = (
                    str(payload.get("value") or "").rstrip("/")
                    == self.binding.api_url.rstrip("/")
                )
                if same_origin and self._published_page_is_current(headers):
                    return
                if not same_origin:
                    changed = self.http.patch(
                        variable,
                        headers=headers,
                        json={"name": self.VARIABLE_NAME, "value": self.binding.api_url.rstrip("/")},
                        timeout=20,
                    )
                    if changed.status_code != 204:
                        raise RenderBindingError(
                            f"GitHub rejected repository variable update (HTTP {changed.status_code})"
                        )
            else:
                raise RenderBindingError(
                    f"GitHub repository variable lookup failed (HTTP {current.status_code})"
                )
            dispatched = self.http.post(
                f"{base}/actions/workflows/{self.PAGES_WORKFLOW}/dispatches",
                headers=headers,
                json={
                    "ref": self.binding.branch,
                    "inputs": {"release_sha": self.binding.release_sha},
                },
                timeout=20,
            )
        except (requests.RequestException, ValueError) as exc:
            raise RenderBindingError("GitHub origin binding request failed") from exc
        if dispatched.status_code != 204:
            raise RenderBindingError(
                f"GitHub rejected Mini App publication (HTTP {dispatched.status_code})"
            )

    def _published_page_is_current(self, headers: dict[str, str]) -> bool:
        try:
            response = self.http.get(
                self.binding.mini_app_url,
                headers={
                    "Cache-Control": "no-cache",
                    "User-Agent": headers["User-Agent"],
                },
                params={"release": self.binding.release_sha},
                timeout=20,
            )
        except requests.RequestException:
            return False
        if response.status_code != 200:
            return False
        content = response.text
        return (
            self.binding.api_url.rstrip("/") in content
            and (
                f'name="wukong-release" content="{self.binding.release_sha}"' in content
                or f"app.js?v={self.binding.release_sha}" in content
            )
        )

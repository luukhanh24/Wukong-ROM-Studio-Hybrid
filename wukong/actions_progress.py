from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from .models import JobManifest


class ActionsProgressReporter:
    """Send bounded, signed progress callbacks from an Actions executor."""

    def __init__(
        self,
        *,
        endpoint: str,
        secret: str,
        run_id: int,
        minimum_interval: float = 15.0,
        post: Callable[..., Any] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
    ) -> None:
        self.endpoint = str(endpoint or "").strip()
        self.secret = str(secret or "").strip()
        self.run_id = int(run_id)
        if not self.endpoint.startswith("https://") or len(self.secret) < 20 or self.run_id <= 0:
            raise ValueError("Actions progress callback configuration is invalid")
        if post is None:
            import requests

            post = requests.post
        self.post = post
        self.minimum_interval = max(1.0, float(minimum_interval))
        self.monotonic = monotonic
        self.wall_time = wall_time
        self._lock = threading.RLock()
        self._last_sent_at = 0.0
        self._last_stage = ""
        self._sequence = 0

    @classmethod
    def from_environment(cls) -> "ActionsProgressReporter | None":
        endpoint = os.environ.get("WUKONG_ACTIONS_PROGRESS_URL", "").strip()
        secret = os.environ.get("WUKONG_ACTIONS_CALLBACK_SECRET", "").strip()
        raw_run_id = os.environ.get("WUKONG_ACTIONS_RUN_ID", os.environ.get("GITHUB_RUN_ID", ""))
        if not endpoint or not secret or not str(raw_run_id).strip():
            return None
        try:
            return cls(
                endpoint=endpoint,
                secret=secret,
                run_id=int(raw_run_id),
                minimum_interval=float(
                    os.environ.get("WUKONG_ACTIONS_PROGRESS_INTERVAL", "15") or "15"
                ),
            )
        except (TypeError, ValueError):
            return None

    def publish(self, manifest: JobManifest, *, force: bool = False) -> bool:
        now = self.monotonic()
        stage = str(manifest.stage or "")
        with self._lock:
            if (
                not force
                and stage == self._last_stage
                and self._last_sent_at > 0
                and now - self._last_sent_at < self.minimum_interval
            ):
                return False
            sequence = self._sequence + 1
            issued_at = str(int(self.wall_time()))
            payload = {
                "jobId": manifest.job_id,
                "runId": self.run_id,
                "sequence": sequence,
                "status": manifest.status.value,
                "stage": stage,
                "progress": max(0.0, min(float(manifest.progress), 1.0)),
                "checkpoint": str(manifest.checkpoint or ""),
                "timestamp": manifest.updated_at,
            }
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            key = hmac.new(
                b"WukongActionsCallback\0",
                self.secret.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            signature = hmac.new(
                key,
                issued_at.encode("ascii") + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            try:
                response = self.post(
                    self.endpoint,
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Wukong-Timestamp": issued_at,
                        "X-Wukong-Signature": signature,
                    },
                    timeout=10,
                )
                response.raise_for_status()
            except Exception as exc:  # noqa: BLE001 - progress is best effort
                print(f"[!] Actions progress callback failed: {type(exc).__name__}", flush=True)
                return False
            self._sequence = sequence
            self._last_stage = stage
            self._last_sent_at = now
            return True

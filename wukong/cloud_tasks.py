from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any


class CloudTaskDispatcher:
    """Create idempotently named HTTP tasks for the stateless control plane."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        base_url: str,
        service_account_email: str,
        audience: str | None = None,
        telegram_queue: str = "wukong-telegram",
        dispatch_queue: str = "wukong-dispatch",
        client: object | None = None,
    ) -> None:
        self.project = self._required(project, "Cloud Tasks project")
        self.location = self._required(location, "Cloud Tasks location")
        self.base_url = self._required(base_url, "Cloud Tasks base URL").rstrip("/")
        if not self.base_url.startswith("https://"):
            raise ValueError("Cloud Tasks base URL must use HTTPS")
        self.service_account_email = self._required(
            service_account_email,
            "Cloud Tasks service account",
        )
        self.audience = (audience or self.base_url).rstrip("/")
        self.telegram_queue = self._queue_name(telegram_queue)
        self.dispatch_queue = self._queue_name(dispatch_queue)
        if client is None:
            try:
                from google.cloud import tasks_v2
            except ImportError as exc:  # pragma: no cover - deployment dependency
                raise RuntimeError("google-cloud-tasks is required for Cloud Tasks") from exc
            client = tasks_v2.CloudTasksClient()
        self.client = client

    @staticmethod
    def _required(value: str, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{label} is required")
        return normalized

    @staticmethod
    def _queue_name(value: str) -> str:
        normalized = str(value or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,98}[a-z0-9]", normalized):
            raise ValueError("Cloud Tasks queue name is invalid")
        return normalized

    @staticmethod
    def _task_suffix(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]", "-", str(value or "").strip())
        if not normalized or len(normalized) > 500:
            raise ValueError("Cloud Task identity is invalid")
        return normalized

    def enqueue_telegram_update(self, update_id: int, update: Mapping[str, object]) -> bool:
        normalized_id = int(update_id)
        if normalized_id < 0:
            raise ValueError("Telegram update ID is invalid")
        return self._enqueue(
            queue=self.telegram_queue,
            task_id=f"telegram-{normalized_id}",
            path="/internal/tasks/telegram-update",
            payload={"updateId": normalized_id, "update": dict(update)},
        )

    def enqueue_job_dispatch(self, job_id: str) -> bool:
        normalized_id = self._task_suffix(job_id)
        return self._enqueue(
            queue=self.dispatch_queue,
            task_id=f"job-{normalized_id}",
            path="/internal/tasks/job-dispatch",
            payload={"jobId": str(job_id)},
        )

    def _enqueue(
        self,
        *,
        queue: str,
        task_id: str,
        path: str,
        payload: Mapping[str, object],
    ) -> bool:
        parent = self.client.queue_path(self.project, self.location, queue)
        task = {
            "name": f"{parent}/tasks/{self._task_suffix(task_id)}",
            "http_request": {
                "http_method": "POST",
                "url": f"{self.base_url}{path}",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    dict(payload),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                "oidc_token": {
                    "service_account_email": self.service_account_email,
                    "audience": self.audience,
                },
            },
        }
        try:
            self.client.create_task(request={"parent": parent, "task": task})
        except Exception as exc:  # noqa: BLE001 - avoid importing Google errors in local tests
            if type(exc).__name__ == "AlreadyExists":
                return False
            raise
        return True


class CloudTasksOIDCVerifier:
    """Verify that an internal request came from the configured task identity."""

    def __init__(
        self,
        *,
        audience: str,
        service_account_email: str,
        verify: Callable[[str, str], Mapping[str, object]] | None = None,
    ) -> None:
        self.audience = str(audience or "").strip().rstrip("/")
        self.service_account_email = str(service_account_email or "").strip().casefold()
        if not self.audience.startswith("https://") or not self.service_account_email:
            raise ValueError("Cloud Tasks OIDC configuration is invalid")
        self._verify = verify or self._google_verify

    @staticmethod
    def _google_verify(token: str, audience: str) -> Mapping[str, object]:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError("google-auth is required for Cloud Tasks OIDC") from exc
        return id_token.verify_oauth2_token(token, Request(), audience=audience)

    def __call__(self, authorization: str) -> bool:
        scheme, separator, token = str(authorization or "").partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or len(token.strip()) < 8:
            return False
        try:
            claims = self._verify(token.strip(), self.audience)
        except Exception:  # noqa: BLE001 - authentication failures are intentionally uniform
            return False
        email = str(claims.get("email") or "").strip().casefold()
        verified = claims.get("email_verified")
        return (
            email == self.service_account_email
            and verified in {True, "true", "True", 1}
            and str(claims.get("aud") or "").rstrip("/") == self.audience
        )

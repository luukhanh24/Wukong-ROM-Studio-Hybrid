from __future__ import annotations

import json
import os
import shlex
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests

from .models import BuildRecipe, Identity, JobStatus, RecipeValidationError
from .orchestrator import HybridOrchestrator, OrchestrationError
from .telegram import TelegramAccessStore
from .runtime import HybridRuntime


HELP_USER = """Wukong ROM Studio Hybrid
/catalog - xem thiết bị, preset và MOD
/submit <recipe JSON> - tạo job build/mirror/upload
/job <job_id> - xem trạng thái job của bạn
/events <job_id> - xem event gần nhất
/cancel <job_id> - hủy job của bạn
/resume <job_id> - tiếp tục từ checkpoint
/diagnostics - trạng thái runner, cloud và cache
/cache - xem stage cache
/cache_clear - xóa stage cache
/cloud [sources|artifacts] - xem thư viện Google Drive
/jobs - xem lịch sử job của bạn
/artifacts <job_id> - nhận link artifact
"""
HELP_ADMIN = HELP_USER + """/approve <telegram_user_id> - duyệt người dùng
/revoke <telegram_user_id> - thu hồi quyền
/users - xem allowlist
"""


class TelegramBotController:
    def __init__(
        self,
        *,
        access: TelegramAccessStore,
        orchestrator: HybridOrchestrator,
        catalog_provider: Callable[[], dict[str, object]],
        diagnostics_provider: Callable[[], dict[str, object]],
        cache_provider: Callable[[], dict[str, object]] | None = None,
        cache_clearer: Callable[[], dict[str, object]] | None = None,
        cloud_provider: Callable[[str], dict[str, object]] | None = None,
        runtime: HybridRuntime | None = None,
    ) -> None:
        self.access = access
        self.orchestrator = orchestrator
        self.catalog_provider = catalog_provider
        self.diagnostics_provider = diagnostics_provider
        self.cache_provider = cache_provider or (lambda: {})
        self.cache_clearer = cache_clearer
        self.cloud_provider = cloud_provider
        self.runtime = runtime

    def handle(self, user_id: int | str, text: str) -> str:
        identity = self.access.identity(user_id)
        if not identity:
            return "Bạn chưa được cấp quyền. Hãy gửi Telegram user ID cho quản trị viên."
        command, _, argument = (text or "").strip().partition(" ")
        command = command.split("@", 1)[0].casefold()
        argument = argument.strip()
        try:
            if command in {"/start", "/help", "/menu"}:
                return HELP_ADMIN if identity.role == "admin" else HELP_USER
            if command == "/catalog":
                return self._render_json(self.catalog_provider())
            if command == "/diagnostics":
                return self._render_json(self.diagnostics_provider())
            if command == "/cache":
                return self._render_json(self.cache_provider())
            if command == "/cache_clear":
                if identity.role != "admin":
                    raise PermissionError("Admin access is required to clear shared cache")
                if not self.cache_clearer:
                    return "Chức năng xóa cache chưa được cấu hình."
                return self._render_json(self.cache_clearer())
            if command == "/cloud":
                category = argument.casefold() or "artifacts"
                if category not in {"sources", "artifacts"}:
                    return "Cú pháp: /cloud [sources|artifacts]"
                provider = self.cloud_provider or (
                    (lambda value: self.runtime.cloud_library(category=value)) if self.runtime else None
                )
                if not provider:
                    return "Thư viện cloud chưa được cấu hình."
                return self._render_json(provider(category))
            if command == "/jobs":
                return self._render_json(
                    {"jobs": [job.to_dict() for job in self.orchestrator.list(identity)]}
                )
            if command == "/submit":
                if not argument:
                    return "Cú pháp: /submit <recipe JSON>"
                recipe = BuildRecipe.from_dict(json.loads(argument))
                job = self.orchestrator.submit(recipe, identity)
                if self.runtime:
                    self.runtime.start(job)
                return f"Đã tạo job {job.job_id}\nRunner: {job.runner}\nTrạng thái: {job.status.value}"
            if command in {"/job", "/events", "/cancel", "/resume", "/artifacts"}:
                if not argument:
                    return f"Cú pháp: {command} <job_id>"
                return self._job_command(command, argument, identity)
            if command == "/approve":
                self.access.approve(argument, actor=identity)
                return f"Đã duyệt Telegram user {argument}."
            if command == "/revoke":
                self.access.revoke(argument, actor=identity)
                return f"Đã thu hồi Telegram user {argument}."
            if command == "/users":
                return self._render_json(self.access.list_access(actor=identity))
            return "Lệnh không hợp lệ. Dùng /menu để xem chức năng."
        except (json.JSONDecodeError, RecipeValidationError, OrchestrationError, PermissionError, ValueError) as exc:
            return f"Không thể thực hiện: {exc}"

    def _job_command(self, command: str, job_id: str, identity: Identity) -> str:
        if command == "/job":
            job = self.orchestrator.inspect(job_id, identity)
            if self.runtime:
                job = self.runtime.refresh(job)
            return self._render_json(job.to_dict())
        if command == "/events":
            events = self.orchestrator.events(job_id, identity)
            return self._render_json({"events": [event.to_dict() for event in events[-10:]]})
        if command == "/cancel":
            current = self.orchestrator.inspect(job_id, identity)
            cancelled = self.orchestrator.cancel(job_id, identity)
            if self.runtime:
                self.runtime.cancel_external(current)
            return self._render_json(cancelled.to_dict())
        if command == "/resume":
            resumed = (
                self.runtime.resume(job_id, identity)
                if self.runtime
                else self.orchestrator.resume(job_id, identity)
            )
            return self._render_json(resumed.to_dict())
        job = self.orchestrator.inspect(job_id, identity)
        if self.runtime:
            job = self.runtime.refresh(job)
        return "\n".join(
            f"{artifact.name}\n{artifact.public_url or artifact.uri}\nSHA-256: {artifact.sha256}"
            for artifact in job.artifacts
        ) or "Job chưa có artifact."

    @staticmethod
    def _render_json(payload: object) -> str:
        value = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        return value if len(value) <= 3900 else value[:3880] + "\n…"


class TelegramLongPollingDaemon:
    def __init__(self, token: str, controller: TelegramBotController) -> None:
        self._token = token
        self.controller = controller
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        offset = 0
        while not self._stop.is_set():
            try:
                response = requests.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": offset, "timeout": 30, "allowed_updates": json.dumps(["message"])},
                    timeout=40,
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = max(offset, int(update["update_id"]) + 1)
                    message = update.get("message") or {}
                    sender = message.get("from") or {}
                    chat = message.get("chat") or {}
                    text = message.get("text")
                    if not sender.get("id") or not chat.get("id") or not isinstance(text, str):
                        continue
                    answer = self.controller.handle(sender["id"], text)
                    requests.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": chat["id"],
                            "text": answer,
                            "disable_web_page_preview": True,
                        },
                        timeout=20,
                    ).raise_for_status()
            except requests.RequestException:
                self._stop.wait(5)


class TelegramWebhookAdapter:
    """Transport adapter retained for a future VPS/webhook deployment."""

    def __init__(self, controller: TelegramBotController) -> None:
        self.controller = controller

    def handle_update(self, update: dict[str, Any]) -> str | None:
        message = update.get("message") or {}
        sender = message.get("from") or {}
        text = message.get("text")
        if not sender.get("id") or not isinstance(text, str):
            return None
        return self.controller.handle(sender["id"], text)

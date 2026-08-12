from __future__ import annotations

import html
import os
import queue
import threading
import time
from typing import Any


TERMINAL_STATUSES = {"success", "failed", "cancelled"}


def _safe(value: Any, maximum: int = 600) -> str:
    text = str(value or "-").strip() or "-"
    if len(text) > maximum:
        text = text[: maximum - 1].rstrip() + "…"
    return html.escape(text)


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _progress_bar(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    filled = min(20, max(0, round(percent / 5)))
    return "█" * filled + "░" * (20 - filled)


def render_progress_message(snapshot: dict[str, Any]) -> str:
    locale = "en" if snapshot.get("locale") == "en" else "vi"
    status = str(snapshot.get("status") or "running")
    percent = max(0, min(100, int(snapshot.get("percent") or 0)))
    steps = list(snapshot.get("steps") or [])
    current_label = snapshot.get("currentLabel") or "-"
    detail = snapshot.get("progressMessage") or ""
    error = snapshot.get("error") or ""

    if locale == "en":
        headers = {
            "queued": "🕓 <b>ROM BUILD QUEUED</b>",
            "running": "🚀 <b>ROM BUILD IN PROGRESS</b>",
            "packaging": "📦 <b>PACKAGING ROM</b>",
            "success": "✅ <b>ROM BUILD COMPLETED</b>",
            "failed": "❌ <b>ROM BUILD FAILED</b>",
            "cancelled": "⛔ <b>ROM BUILD CANCELLED</b>",
        }
        current_title = "Current stage"
        timeline_title = "Pipeline timeline"
        elapsed_title = "Elapsed"
        progress_title = "Overall progress"
        job_title = "Job"
        error_title = "Error"
        if status == "success":
            footer = (
                "Detailed artifact report has been sent separately."
                if snapshot.get("finalReportSent")
                else "Build completed, but delivery of the detailed artifact report could not be confirmed."
            )
        else:
            footer = "This message updates automatically while the build is running."
    else:
        headers = {
            "queued": "🕓 <b>ROM ĐANG CHỜ BUILD</b>",
            "running": "🚀 <b>ĐANG BUILD ROM</b>",
            "packaging": "📦 <b>ĐANG ĐÓNG GÓI ROM</b>",
            "success": "✅ <b>BUILD ROM HOÀN TẤT</b>",
            "failed": "❌ <b>BUILD ROM THẤT BẠI</b>",
            "cancelled": "⛔ <b>BUILD ROM ĐÃ HỦY</b>",
        }
        current_title = "Bước hiện tại"
        timeline_title = "Tiến trình pipeline"
        elapsed_title = "Đã chạy"
        progress_title = "Tiến độ tổng"
        job_title = "Job"
        error_title = "Lỗi"
        if status == "success":
            footer = (
                "Báo cáo artifact chi tiết đã được gửi ở tin nhắn riêng."
                if snapshot.get("finalReportSent")
                else "Build đã hoàn tất nhưng chưa xác nhận được việc gửi báo cáo artifact chi tiết."
            )
        else:
            footer = "Tin nhắn này tự cập nhật trong suốt quá trình build."

    step_icons = {
        "success": "✅",
        "running": "🔄",
        "failed": "❌",
        "skipped": "⏭",
        "cancelled": "⛔",
        "pending": "▫️",
    }
    timeline = [
        f"{step_icons.get(str(step.get('status') or 'pending'), '▫️')} {_safe(step.get('label'), 180)}"
        for step in steps
    ]
    lines = [
        headers.get(status, headers["running"]),
        (
            f"<blockquote><b>Wukong {_safe(snapshot.get('edition'), 80)} "
            f"{_safe(snapshot.get('studioVersion'), 40)}</b>\n"
            f"<code>{_safe(snapshot.get('versionName'), 260)}</code></blockquote>"
        ),
        f"📱 <b>{_safe(snapshot.get('deviceName'), 180)}</b> · <code>{_safe(snapshot.get('productName'), 100)}</code>",
        "",
        f"📊 <b>{progress_title}:</b> <code>{_progress_bar(percent)} {percent:3d}%</code>",
        f"🎯 <b>{current_title}:</b> {_safe(current_label, 220)}",
    ]
    if detail:
        lines.append(f"   <i>{_safe(detail, 300)}</i>")
    lines.extend(["", f"🧭 <b>{timeline_title}</b>", *timeline])
    if error:
        lines.extend(["", f"⚠️ <b>{error_title}:</b> <code>{_safe(error, 700)}</code>"])
    lines.extend(
        [
            "",
            f"⏱ <b>{elapsed_title}:</b> <code>{_duration(float(snapshot.get('elapsedSeconds') or 0))}</code>",
            f"🆔 <b>{job_title}:</b> <code>{_safe(snapshot.get('jobId'), 100)}</code>",
            f"<i>{footer}</i>",
        ]
    )
    return "\n".join(lines)


class TelegramProgressReporter:
    def __init__(self, minimum_interval: float | None = None) -> None:
        configured = os.environ.get("WUKONG_TELEGRAM_PROGRESS_INTERVAL", "3")
        try:
            interval = float(configured)
        except ValueError:
            interval = 3.0
        self.minimum_interval = max(1.0, interval) if minimum_interval is None else max(0.0, minimum_interval)
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._message_ids: dict[str, int] = {}
        self._signatures: dict[str, tuple[Any, ...]] = {}
        self._terminal_jobs: dict[str, None] = {}
        self._last_request_at = 0.0

    def publish(self, snapshot: dict[str, Any], *, force: bool = False) -> bool:
        token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("WUKONG_TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return False
        job_id = str(snapshot.get("jobId") or "").strip()
        if not job_id:
            return False
        status = str(snapshot.get("status") or "running")
        steps = tuple((step.get("label"), step.get("status")) for step in snapshot.get("steps") or [])
        signature = (
            status,
            snapshot.get("currentLabel"),
            int(snapshot.get("percent") or 0) // 5,
            steps,
            snapshot.get("error"),
        )
        with self._lock:
            if job_id in self._terminal_jobs:
                return False
            if not force and self._signatures.get(job_id) == signature:
                return False
            self._signatures[job_id] = signature
            if status in TERMINAL_STATUSES:
                self._terminal_jobs[job_id] = None
                while len(self._terminal_jobs) > 512:
                    self._terminal_jobs.pop(next(iter(self._terminal_jobs)))
            self._ensure_thread()
            self._queue.put(dict(snapshot))
        return True

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="telegram-progress",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while True:
            first = self._queue.get()
            wait = self.minimum_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            pending = {str(first["jobId"]): first}
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                pending[str(item["jobId"])] = item
            for snapshot in pending.values():
                if self._last_request_at:
                    wait = self.minimum_interval - (time.monotonic() - self._last_request_at)
                    if wait > 0:
                        time.sleep(wait)
                self._deliver(snapshot)
                self._last_request_at = time.monotonic()

    def _deliver(self, snapshot: dict[str, Any]) -> bool:
        import requests

        token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("WUKONG_TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return False
        job_id = str(snapshot["jobId"])
        text = render_progress_message(snapshot)
        timeout = int(os.environ.get("WUKONG_TELEGRAM_TIMEOUT", "10") or "10")
        with self._lock:
            message_id = self._message_ids.get(job_id)
        method = "editMessageText" if message_id is not None else "sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if message_id is not None:
            payload["message_id"] = message_id
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/{method}",
                json=payload,
                timeout=timeout,
            )
            if response.status_code == 400 and "message is not modified" in response.text.lower():
                return True
            response.raise_for_status()
            body = response.json()
            returned_id = (body.get("result") or {}).get("message_id")
            if message_id is None and returned_id is not None:
                with self._lock:
                    self._message_ids[job_id] = int(returned_id)
            return True
        except (requests.RequestException, ValueError, TypeError) as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            label = f"HTTP {status_code}" if status_code else type(exc).__name__
            print(f"[!] Telegram progress update failed: {label}", flush=True)
            return False

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

import requests

from .models import BuildRecipe, Identity, JobManifest, JobStatus, RecipeValidationError
from .orchestrator import HybridOrchestrator, OrchestrationError
from .routing import RunnerUnavailableError
from .runtime import HybridRuntime
from .telegram import TelegramAccessStore


LANGUAGES = {"vi", "en"}
CALLBACK_VERSION = "v1"
STATUS_LABELS = {
    "vi": {
        "queued": "đang chờ",
        "preflight": "đang kiểm tra",
        "downloading": "đang tải ROM",
        "running": "đang build",
        "uploading": "đang tải lên",
        "succeeded": "thành công",
        "failed": "thất bại",
        "cancelled": "đã hủy",
    },
    "en": {},
}
EVENT_LABELS = {
    "vi": {
        "submitted": "đã tạo job",
        "status": "cập nhật trạng thái",
        "build": "bước build",
        "cancelled": "đã hủy",
        "resumed": "đã tiếp tục",
        "warning": "cảnh báo",
        "artifact": "artifact sẵn sàng",
    },
    "en": {},
}
STAGE_LABELS = {
    "vi": {
        "preflight": "kiểm tra trước khi chạy",
        "download": "tải ROM",
        "build": "build ROM",
        "upload": "tải artifact lên cloud",
        "complete": "hoàn tất",
    },
    "en": {},
}


class ExpiredCallbackError(ValueError):
    pass

TEXT = {
    "vi": {
        "welcome": "Wukong ROM Studio\n\nChọn “Tạo bản build” để bắt đầu hoặc “Công việc của tôi” để theo dõi. Bạn không cần nhớ lệnh hay viết JSON.",
        "new": "Tạo bản build",
        "jobs": "Công việc của tôi",
        "library": "Kho ROM",
        "diagnostics": "Chẩn đoán",
        "mini_app": "Mở Wukong Mini App",
        "mini_app_prompt": "Chạm nút bên dưới để mở Wukong Mini App. Telegram xác thực tài khoản; cấu hình, tiến trình, lịch sử và link tải tiếp tục hiển thị ngay trong Mini App.",
        "language": "English",
        "back": "Quay lại menu",
        "refresh": "Làm mới",
        "events": "Nhật ký",
        "artifact": "Tải artifact",
        "cancel": "Hủy job",
        "resume": "Tiếp tục",
        "choose_task": "Bạn muốn làm gì?",
        "task_build": "Build ROM đầy đủ",
        "task_mirror": "Chỉ lưu ROM gốc lên cloud",
        "task_publish": "Phát hành file artifact lên cloud",
        "choose_run": "Chọn nơi chạy job.",
        "run_github": "GitHub Actions",
        "run_windows": "Windows hiện tại",
        "choose_source": "Chọn nguồn ROM.",
        "source_library": "ROM có sẵn trên Drive",
        "source_url": "Nhập URL tải ROM",
        "source_drive": "Nhập đường dẫn Google Drive",
        "source_local": "Nhập đường dẫn file Windows",
        "send_url": "Gửi URL HTTP/HTTPS của ROM trong tin nhắn tiếp theo.",
        "send_drive": "Gửi đường dẫn rclone riêng tư, ví dụ:\n{remote}:WukongROM/sources/PKG110/sha256/rom.zip",
        "send_local": "Gửi đường dẫn đầy đủ tới file ROM trên máy Windows.",
        "choose_device": "Chọn thiết bị cho bản ROM.",
        "choose_mod_version": "Chọn phiên bản bộ MOD.",
        "choose_preset": "Chọn cấu hình build.",
        "choose_mods": "Chọn MOD cần áp dụng",
        "mod_page": "Trang {page}/{pages} · đã chọn {selected}/{total} MOD",
        "mod_selected": "Đã chọn · {name}",
        "mod_unselected": "Chọn · {name}",
        "mods_select_all": "Chọn tất cả",
        "mods_clear_all": "Bỏ chọn tất cả",
        "mods_previous": "Trang trước",
        "mods_next": "Trang sau",
        "mods_done": "Xong, kiểm tra cấu hình",
        "mods_empty": "Phiên bản này không có MOD sẵn sàng. Bạn vẫn có thể tiếp tục build không MOD.",
        "mods_both_required": "Cấu hình tạo cả Lite và Plus cần ít nhất một MOD. Hãy chọn MOD hoặc đổi preset.",
        "preset_lite": "Lite — gọn nhẹ",
        "preset_plus": "Plus — đầy đủ",
        "preset_both": "Tạo cả Lite và Plus",
        "confirm": "Xác nhận và tạo job",
        "edit": "Làm lại",
        "advanced": "Tùy chọn nâng cao dùng lệnh /submit.",
        "created": "Job {job_id} đã được tạo.\nRunner: {runner}\nTrạng thái: {status}",
        "no_jobs": "Bạn chưa có job nào. Chọn “Tạo bản build” để bắt đầu.",
        "no_roms": "Kho ROM chưa có file phù hợp hoặc Drive chưa sẵn sàng.",
        "expired": "Nút này đã hết hạn hoặc không còn hợp lệ. Hãy mở lại menu để tiếp tục.",
        "denied": "Bạn chưa được cấp quyền. Hãy gửi Telegram user ID của bạn cho quản trị viên.",
        "failed": "Không thể thực hiện: {error}\n\nBạn có thể quay lại menu và thử lại.",
        "job_not_found": "Không thể mở job này. Job không tồn tại hoặc không thuộc tài khoản của bạn.",
        "input_invalid": "Dữ liệu chưa hợp lệ: {error}\nHãy gửi lại giá trị đúng hoặc quay về menu.",
        "status": "Job {job_id}\nTrạng thái: {status}\nGiai đoạn: {stage}\nTiến độ: {progress}%\nRunner: {runner}",
        "summary": "Kiểm tra cấu hình\n\nTác vụ: {task}\nNơi chạy: {run}\nNguồn: {source}\nThiết bị: {device}\nBộ MOD: {mod_version}\nPreset: {preset}\nMOD đã chọn ({mod_count}): {mods}\n\n{advanced}",
        "library_title": "Kho ROM trên Google Drive",
        "diagnostics_title": "Chẩn đoán hệ thống",
        "events_title": "Nhật ký gần nhất của {job_id}",
        "no_artifact": "Job chưa có artifact. Hãy thử lại khi build hoàn tất.",
        "probe_result": "Đã nhận diện ROM\n\nNhà cung cấp: {provider}\nTệp: {filename}\nDung lượng: {size}\nProduct: {product}\nThiết bị: {device}\nPhiên bản: {version}\nAndroid: {android_version}\nBản vá bảo mật: {security_patch}\nNgày build: {build_date}\nLoại OTA: {ota_type}\nPhân tích sâu: {deep}",
    },
    "en": {
        "welcome": "Wukong ROM Studio\n\nSelect “New build” to begin or “My jobs” to monitor progress. No commands or JSON are required.",
        "new": "New build",
        "jobs": "My jobs",
        "library": "ROM library",
        "diagnostics": "Diagnostics",
        "mini_app": "Open Wukong Mini App",
        "mini_app_prompt": "Tap below to open Wukong Mini App. Telegram authenticates your account; configuration, progress, history and download links remain inside the Mini App.",
        "language": "Tiếng Việt",
        "back": "Back to menu",
        "refresh": "Refresh",
        "events": "Events",
        "artifact": "Get artifact",
        "cancel": "Cancel job",
        "resume": "Resume",
        "choose_task": "What would you like to do?",
        "task_build": "Build a complete ROM",
        "task_mirror": "Mirror the stock ROM to cloud only",
        "task_publish": "Publish an artifact file to cloud",
        "choose_run": "Choose where this job will run.",
        "run_github": "GitHub Actions",
        "run_windows": "This Windows PC",
        "choose_source": "Choose the ROM source.",
        "source_library": "ROM already on Drive",
        "source_url": "Enter a ROM URL",
        "source_drive": "Enter a Google Drive path",
        "source_local": "Enter a Windows file path",
        "send_url": "Send the ROM HTTP/HTTPS URL in your next message.",
        "send_drive": "Send a private rclone path, for example:\n{remote}:WukongROM/sources/PKG110/sha256/rom.zip",
        "send_local": "Send the full path to the ROM file on this Windows PC.",
        "choose_device": "Choose the target device.",
        "choose_mod_version": "Choose the MOD pack version.",
        "choose_preset": "Choose a build preset.",
        "choose_mods": "Choose MODs to apply",
        "mod_page": "Page {page}/{pages} · {selected}/{total} MODs selected",
        "mod_selected": "Selected · {name}",
        "mod_unselected": "Select · {name}",
        "mods_select_all": "Select all",
        "mods_clear_all": "Clear all",
        "mods_previous": "Previous page",
        "mods_next": "Next page",
        "mods_done": "Done, review build",
        "mods_empty": "This version has no ready MODs. You can continue without MODs.",
        "mods_both_required": "Building both Lite and Plus requires at least one MOD. Select a MOD or change the preset.",
        "preset_lite": "Lite — streamlined",
        "preset_plus": "Plus — complete",
        "preset_both": "Build both Lite and Plus",
        "confirm": "Confirm and create job",
        "edit": "Start over",
        "advanced": "Advanced options remain available through /submit.",
        "created": "Job {job_id} was created.\nRunner: {runner}\nStatus: {status}",
        "no_jobs": "You do not have any jobs yet. Select “New build” to begin.",
        "no_roms": "No suitable ROM files were found or Drive is unavailable.",
        "expired": "This button has expired or is no longer valid. Open the menu to continue.",
        "denied": "You do not have access yet. Send your Telegram user ID to an administrator.",
        "failed": "Unable to complete the action: {error}\n\nReturn to the menu and try again.",
        "job_not_found": "This job cannot be opened. It does not exist or belongs to another user.",
        "input_invalid": "That value is not valid: {error}\nSend a corrected value or return to the menu.",
        "status": "Job {job_id}\nStatus: {status}\nStage: {stage}\nProgress: {progress}%\nRunner: {runner}",
        "summary": "Review build configuration\n\nTask: {task}\nRun on: {run}\nSource: {source}\nDevice: {device}\nMOD pack: {mod_version}\nPreset: {preset}\nSelected MODs ({mod_count}): {mods}\n\n{advanced}",
        "library_title": "Google Drive ROM library",
        "diagnostics_title": "System diagnostics",
        "events_title": "Recent events for {job_id}",
        "no_artifact": "This job does not have an artifact yet. Try again after the build completes.",
        "probe_result": "ROM identified\n\nProvider: {provider}\nFile: {filename}\nSize: {size}\nProduct: {product}\nDevice: {device}\nVersion: {version}\nAndroid: {android_version}\nSecurity patch: {security_patch}\nBuild date: {build_date}\nOTA type: {ota_type}\nDeep inspection: {deep}",
    },
}


HELP_USER_VI = """Wukong ROM Studio Hybrid
/start - mở menu nút / open the button menu
/app - mở Telegram Mini App / open Telegram Mini App
/new - tạo bản build / new build
/jobs - công việc của tôi / my jobs
/cloud - kho ROM / ROM library
/diagnostics - chẩn đoán / diagnostics
/language - đổi ngôn ngữ / change language
/submit <recipe JSON> - chế độ nâng cao / advanced mode
/job <job_id> - trạng thái job
/events <job_id> - nhật ký job
/cancel <job_id> - hủy job
/resume <job_id> - tiếp tục từ checkpoint
/artifacts <job_id> - nhận link artifact
"""
HELP_ADMIN_VI = HELP_USER_VI + """/approve <telegram_user_id> - duyệt người dùng
/revoke <telegram_user_id> - thu hồi quyền
/users - xem allowlist
/cache - xem stage cache
/cache_clear - xóa stage cache
"""
HELP_USER_EN = """Wukong ROM Studio Hybrid
/start - open the button menu
/app - open Telegram Mini App
/new - create a ROM build
/jobs - view my jobs
/cloud - browse the ROM library
/diagnostics - view system diagnostics
/language - switch language
/submit <recipe JSON> - advanced mode
/job <job_id> - inspect a job
/events <job_id> - view job events
/cancel <job_id> - cancel a job
/resume <job_id> - resume from checkpoint
/artifacts <job_id> - get artifact links
"""
HELP_ADMIN_EN = HELP_USER_EN + """/approve <telegram_user_id> - approve a user
/revoke <telegram_user_id> - revoke a user
/users - view the allowlist
/cache - inspect stage cache
/cache_clear - clear stage cache
"""


@dataclass(frozen=True)
class BotResponse:
    text: str
    reply_markup: dict[str, object] = field(default_factory=dict)

    def telegram_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "text": self.text[:4096],
            "disable_web_page_preview": True,
        }
        if self.reply_markup:
            payload["reply_markup"] = self.reply_markup
        return payload


class TelegramUIStateStore:
    """Small atomic preference/session store keyed only by authenticated Telegram ID."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path.resolve() if path else None
        self._memory: dict[str, object] = {
            "schemaVersion": 1,
            "languages": {},
            "sessions": {},
            "jobRefs": {},
        }
        self._lock = threading.RLock()
        if self.path and self.path.is_file():
            self._memory = self._load_path()

    def language(self, user_id: int | str) -> str:
        state = self._read()
        value = str(state["languages"].get(str(user_id), "vi"))
        return value if value in LANGUAGES else "vi"

    def set_language(self, user_id: int | str, language: str) -> None:
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")
        state = self._read()
        state["languages"][str(user_id)] = language
        self._write(state)

    def session(self, user_id: int | str) -> dict[str, Any]:
        state = self._read()
        value = state["sessions"].get(str(user_id), {})
        return dict(value) if isinstance(value, dict) else {}

    def set_session(self, user_id: int | str, session: Mapping[str, Any]) -> None:
        state = self._read()
        state["sessions"][str(user_id)] = dict(session)
        self._write(state)

    def clear_session(self, user_id: int | str) -> None:
        state = self._read()
        state["sessions"].pop(str(user_id), None)
        self._write(state)

    def remember_job(self, user_id: int | str, job_id: str) -> str:
        state = self._read()
        subject = str(user_id)
        refs = state["jobRefs"].setdefault(subject, {})
        digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()
        length = 12
        reference = digest[:length]
        while reference in refs and refs[reference] != job_id:
            length += 4
            reference = digest[:length]
        refs[reference] = job_id
        self._write(state)
        return reference

    def resolve_job(self, user_id: int | str, reference: str) -> str | None:
        state = self._read()
        refs = state["jobRefs"].get(str(user_id), {})
        return str(refs.get(reference)) if isinstance(refs, dict) and refs.get(reference) else None

    def _read(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._memory))

    def _load_path(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8")) if self.path else {}
        except (OSError, json.JSONDecodeError):
            payload = {}
        return {
            "schemaVersion": 1,
            "languages": payload.get("languages", {}) if isinstance(payload.get("languages"), dict) else {},
            "sessions": payload.get("sessions", {}) if isinstance(payload.get("sessions"), dict) else {},
            "jobRefs": payload.get("jobRefs", {}) if isinstance(payload.get("jobRefs"), dict) else {},
        }

    @staticmethod
    def _safe_for_disk(state: dict[str, Any]) -> dict[str, Any]:
        persisted = json.loads(json.dumps(state))
        for subject, session in list(persisted.get("sessions", {}).items()):
            source = session.get("source") if isinstance(session, dict) else None
            uri = str(source.get("uri") or "") if isinstance(source, dict) else ""
            if source and source.get("kind") in {"http", "https"} and "?" in uri:
                sanitized = dict(session)
                sanitized.pop("source", None)
                sanitized.update({"step": "source_input", "awaiting": "url"})
                persisted["sessions"][subject] = sanitized
        return persisted

    def _write(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._memory = json.loads(json.dumps(state))
            if not self.path:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=self.path.name, dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(self._safe_for_disk(state), handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, self.path)
            finally:
                Path(temporary_name).unlink(missing_ok=True)


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
        source_probe_provider: Callable[[str], dict[str, object]] | None = None,
        runtime: HybridRuntime | None = None,
        ui_state: TelegramUIStateStore | None = None,
        storage_remote: str | None = None,
        web_app_url: str | None = None,
    ) -> None:
        self.access = access
        self.orchestrator = orchestrator
        self.catalog_provider = catalog_provider
        self.diagnostics_provider = diagnostics_provider
        self.cache_provider = cache_provider or (lambda: {})
        self.cache_clearer = cache_clearer
        self.cloud_provider = cloud_provider
        self.source_probe_provider = source_probe_provider
        self.runtime = runtime
        self.ui_state = ui_state or TelegramUIStateStore()
        self.storage_remote = (storage_remote or os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive")).rstrip(":")
        configured_web_app = (web_app_url or os.environ.get("WUKONG_TELEGRAM_WEB_APP_URL", "")).strip()
        if configured_web_app:
            parsed_web_app = urlsplit(configured_web_app)
            if (
                parsed_web_app.scheme.casefold() != "https"
                or not parsed_web_app.netloc
                or parsed_web_app.username
                or parsed_web_app.password
            ):
                raise ValueError("Telegram Mini App URL must be a public HTTPS URL")
        self.web_app_url = configured_web_app

    def command_sets(self) -> dict[str, list[dict[str, str]]]:
        return {
            "vi": [
                {"command": "start", "description": "Mở menu chính"},
                {"command": "app", "description": "Mở Wukong Mini App"},
                {"command": "new", "description": "Tạo bản build"},
                {"command": "jobs", "description": "Công việc của tôi"},
                {"command": "cloud", "description": "Kho ROM trên Drive"},
                {"command": "diagnostics", "description": "Chẩn đoán hệ thống"},
                {"command": "language", "description": "Đổi sang English"},
                {"command": "help", "description": "Xem trợ giúp"},
            ],
            "en": [
                {"command": "start", "description": "Open the main menu"},
                {"command": "app", "description": "Open Wukong Mini App"},
                {"command": "new", "description": "Create a ROM build"},
                {"command": "jobs", "description": "View my jobs"},
                {"command": "cloud", "description": "Browse the ROM library"},
                {"command": "diagnostics", "description": "View diagnostics"},
                {"command": "language", "description": "Switch to Tiếng Việt"},
                {"command": "help", "description": "Show help"},
            ],
        }

    def handle(self, user_id: int | str, text: str) -> str:
        """Compatibility text interface used by existing tests and adapters."""
        identity = self.access.identity(user_id)
        if not identity:
            return TEXT["vi"]["denied"]
        return self._handle_command(identity, text)

    def handle_ui(self, user_id: int | str, text: str) -> BotResponse:
        identity = self.access.identity(user_id)
        language = self.ui_state.language(user_id)
        if not identity:
            return BotResponse(TEXT[language]["denied"])
        normalized = (text or "").strip()
        command = normalized.partition(" ")[0].split("@", 1)[0].casefold()
        session = self.ui_state.session(user_id)
        if session.get("awaiting") and not normalized.startswith("/"):
            return self._wizard_input(identity, normalized, language, session)
        if command in {"/start", "/menu"}:
            self.ui_state.clear_session(user_id)
            return self._main_menu(language)
        if command == "/app":
            return self._mini_app_launcher(language)
        if command == "/new":
            return self.handle_callback(user_id, "v1:new")
        if command == "/jobs":
            return self._jobs_menu(identity, language)
        if command == "/cloud":
            return self._cloud_menu(language)
        if command == "/diagnostics":
            return self._diagnostics_menu(language)
        if command == "/language":
            return self.handle_callback(user_id, f"v1:lang:{'en' if language == 'vi' else 'vi'}")
        if command in {"/help", ""}:
            return BotResponse(self._help(identity, language), self._back_markup(language))
        result = self._handle_command(identity, normalized)
        return BotResponse(result, self._back_markup(language))

    def handle_web_app_data(self, user_id: int | str, raw_data: str) -> BotResponse:
        identity = self.access.identity(user_id)
        language = self.ui_state.language(user_id)
        if not identity:
            return BotResponse(TEXT[language]["denied"])
        try:
            if len(raw_data.encode("utf-8")) > 4096:
                raise ValueError("Mini App request exceeds Telegram's 4096-byte limit")
            request = json.loads(raw_data)
            if not isinstance(request, dict) or int(request.get("version", 0)) != 1:
                raise ValueError("Unsupported Mini App request version")
            action = str(request.get("action") or "").strip().casefold()
            if action == "submit_recipe":
                payload = request.get("recipe")
                if not isinstance(payload, dict):
                    raise ValueError("Mini App build recipe is missing")
                recipe = BuildRecipe.from_dict(payload)
                job = self.orchestrator.submit(recipe, identity)
                if self.runtime:
                    self.runtime.start(job)
                return BotResponse(
                    TEXT[language]["created"].format(
                        job_id=job.job_id,
                        runner=job.runner or "—",
                        status=job.status.value,
                    ),
                    self._job_markup(job, language, identity.subject),
                )
            if action == "jobs":
                return self._jobs_menu(identity, language)
            if action == "cloud":
                return self._cloud_menu(language)
            if action == "diagnostics":
                return self._diagnostics_menu(language)
            if action == "cache":
                return BotResponse(
                    self._render_details(self.cache_provider()),
                    self._back_markup(language),
                )
            if action == "cache_clear":
                if identity.role != "admin":
                    raise PermissionError("Admin access is required to clear shared cache")
                if not self.cache_clearer:
                    raise ValueError("Cache clearing is not configured")
                return BotResponse(
                    self._render_details(self.cache_clearer()),
                    self._back_markup(language),
                )
            if action == "probe_source":
                if not self.source_probe_provider:
                    raise ValueError("ROM source analysis is not configured")
                uri = str(request.get("uri") or "").strip()
                if not uri or len(uri) > 8192:
                    raise ValueError("A valid ROM source URL is required")
                result = self.source_probe_provider(uri)
                size = result.get("sizeBytes")
                size_text = (
                    f"{int(size) / (1024 ** 3):.2f} GiB ({int(size):,} bytes)"
                    if isinstance(size, int) and size > 0
                    else "—"
                )
                return BotResponse(
                    TEXT[language]["probe_result"].format(
                        provider=result.get("provider") or "—",
                        filename=result.get("filename") or "—",
                        size=size_text,
                        product=result.get("productName") or "—",
                        device=result.get("device") or "—",
                        version=result.get("version") or "—",
                        android_version=result.get("androidVersion") or "—",
                        security_patch=result.get("securityPatch") or "—",
                        build_date=result.get("buildDate") or "—",
                        ota_type=result.get("otaType") or "—",
                        deep="Có" if language == "vi" and result.get("deepInspected") else "Yes" if result.get("deepInspected") else "Không" if language == "vi" else "No",
                    ),
                    self._back_markup(language),
                )
            if action in {"job", "events", "artifact", "cancel", "resume"}:
                job_id = str(request.get("jobId") or "").strip()
                if not job_id:
                    raise ValueError("Mini App job ID is required")
                return self._job_callback(action, job_id, identity, language)
            raise ValueError("Unsupported Mini App action")
        except (
            json.JSONDecodeError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            RecipeValidationError,
            OrchestrationError,
            RunnerUnavailableError,
            PermissionError,
        ) as exc:
            return BotResponse(TEXT[language]["failed"].format(error=exc), self._back_markup(language))

    def handle_callback(self, user_id: int | str, data: str) -> BotResponse:
        identity = self.access.identity(user_id)
        language = self.ui_state.language(user_id)
        if not identity:
            return BotResponse(TEXT[language]["denied"])
        try:
            parts = data.split(":")
            if not parts or parts[0] != CALLBACK_VERSION:
                return self._recovery(language)
            action = parts[1] if len(parts) > 1 else ""
            value = parts[2] if len(parts) > 2 else ""
            if action == "menu":
                self.ui_state.clear_session(user_id)
                return self._main_menu(language)
            if action == "app":
                return self._mini_app_launcher(language)
            if action == "lang" and value in LANGUAGES:
                self.ui_state.set_language(user_id, value)
                self.ui_state.clear_session(user_id)
                return self._main_menu(value)
            if action == "new":
                self.ui_state.set_session(user_id, {"step": "task"})
                return BotResponse(
                    TEXT[language]["choose_task"],
                    self._inline([
                        [(TEXT[language]["task_build"], "v1:task:build")],
                        [(TEXT[language]["task_mirror"], "v1:task:mirror")],
                        [(TEXT[language]["task_publish"], "v1:task:publish")],
                        [(TEXT[language]["back"], "v1:menu")],
                    ]),
                )
            if action == "task" and value in {"build", "mirror", "publish"}:
                self._require_step(user_id, "task")
                tasks = {"build": "build", "mirror": "source_mirror", "publish": "artifact_publish"}
                session = {"step": "run", "task": tasks[value]}
                self.ui_state.set_session(user_id, session)
                return self._run_picker(language)
            if action == "run" and value in {"github", "local"}:
                session = self._require_step(user_id, "run")
                session.update({"step": "source", "execution": "github-auto" if value == "github" else "local-windows"})
                self.ui_state.set_session(user_id, session)
                return self._source_picker(identity, language, session)
            if action == "src" and value in {"url", "drive", "local", "library"}:
                session = self._require_step(user_id, "source")
                if value == "library":
                    return self._source_library(identity, language, session)
                if value == "local" and (session.get("execution") != "local-windows" or identity.role != "admin"):
                    raise PermissionError("Local ROM files require an administrator running on Windows")
                session.update({"step": "source_input", "awaiting": value})
                self.ui_state.set_session(user_id, session)
                key = {"url": "send_url", "drive": "send_drive", "local": "send_local"}[value]
                prompt = TEXT[language][key]
                if value == "drive":
                    prompt = prompt.format(remote=self.storage_remote)
                return BotResponse(prompt, self._back_markup(language))
            if action == "lib":
                session = self._require_step(user_id, "library")
                sources = session.get("library")
                index = int(value)
                if not isinstance(sources, list) or index < 0 or index >= len(sources):
                    return self._recovery(language)
                selected = sources[index]
                session["source"] = {
                    "kind": "rclone",
                    "uri": f"{self.storage_remote}:WukongROM/sources/{selected['path']}",
                    **({"sizeBytes": selected["sizeBytes"]} if int(selected.get("sizeBytes") or 0) > 0 else {}),
                }
                session.pop("library", None)
                session["step"] = "device"
                self.ui_state.set_session(user_id, session)
                return self._device_picker(user_id, language, session)
            if action == "dev":
                session = self._require_step(user_id, "device")
                devices = session.get("device_options")
                index = int(value)
                if not isinstance(devices, list) or index < 0 or index >= len(devices):
                    return self._recovery(language)
                session["device"] = str(devices[index][0])
                session.pop("device_options", None)
                if session.get("task") != "build":
                    session.update({"step": "confirm"})
                    self.ui_state.set_session(user_id, session)
                    return self._confirmation(language, session)
                session["step"] = "mod_version"
                self.ui_state.set_session(user_id, session)
                return self._mod_version_picker(user_id, language, session)
            if action == "mv":
                session = self._require_step(user_id, "mod_version")
                versions = session.get("mod_version_options")
                index = int(value)
                if not isinstance(versions, list) or index < 0 or index >= len(versions):
                    return self._recovery(language)
                session.update({"step": "preset", "mod_version": str(versions[index])})
                session.pop("mod_version_options", None)
                self.ui_state.set_session(user_id, session)
                return self._preset_picker(language)
            if action == "pre" and value in {"lite", "plus", "both"}:
                session = self._require_step(user_id, "preset")
                session.update({"step": "mods", "preset": value})
                self.ui_state.set_session(user_id, session)
                return self._start_mod_picker(user_id, language, session)
            if action == "mods":
                session = self._require_step(user_id, "mods")
                return self._mod_picker(language, session, page=int(value or 0))
            if action == "mod":
                session = self._require_step(user_id, "mods")
                options = session.get("mod_options")
                index = int(value)
                if not isinstance(options, list) or index < 0 or index >= len(options):
                    return self._recovery(language)
                selected = set(str(item) for item in session.get("selected_mods", []))
                name = str(options[index])
                if name in selected:
                    selected.remove(name)
                else:
                    selected.add(name)
                session["selected_mods"] = [item for item in options if item in selected]
                self.ui_state.set_session(user_id, session)
                return self._mod_picker(language, session, page=index // 8)
            if action == "mods_all" and value in {"0", "1"}:
                session = self._require_step(user_id, "mods")
                options = session.get("mod_options")
                if not isinstance(options, list):
                    return self._recovery(language)
                session["selected_mods"] = list(options) if value == "1" else []
                self.ui_state.set_session(user_id, session)
                return self._mod_picker(language, session, page=0)
            if action == "mods_done":
                session = self._require_step(user_id, "mods")
                if session.get("preset") == "both" and not session.get("selected_mods"):
                    response = self._mod_picker(language, session, page=0)
                    return BotResponse(
                        f"{TEXT[language]['mods_both_required']}\n\n{response.text}",
                        response.reply_markup,
                    )
                session.update({"step": "confirm"})
                self.ui_state.set_session(user_id, session)
                return self._confirmation(language, session)
            if action == "confirm":
                session = self._require_step(user_id, "confirm")
                recipe = self._recipe_from_session(session)
                job = self.orchestrator.submit(recipe, identity)
                if self.runtime:
                    self.runtime.start(job)
                self.ui_state.clear_session(user_id)
                return BotResponse(
                    TEXT[language]["created"].format(
                        job_id=job.job_id, runner=job.runner or "—", status=job.status.value
                    ),
                    self._job_markup(job, language, identity.subject),
                )
            if action == "jobs":
                return self._jobs_menu(identity, language)
            if action in {"job", "events", "artifact", "cancel", "resume"} and value:
                job_id = self.ui_state.resolve_job(user_id, value) or value
                return self._job_callback(action, job_id, identity, language)
            if action == "cloud":
                return self._cloud_menu(language)
            if action == "diag":
                return self._diagnostics_menu(language)
            return self._recovery(language)
        except ExpiredCallbackError:
            return self._recovery(language)
        except (IndexError, TypeError, KeyError, ValueError, RecipeValidationError, OrchestrationError, RunnerUnavailableError, PermissionError) as exc:
            return BotResponse(TEXT[language]["failed"].format(error=exc), self._back_markup(language))

    def _handle_command(self, identity: Identity, text: str) -> str:
        command, _, argument = (text or "").strip().partition(" ")
        command = command.split("@", 1)[0].casefold()
        argument = argument.strip()
        try:
            if command in {"/start", "/help", "/menu"}:
                return HELP_ADMIN_VI if identity.role == "admin" else HELP_USER_VI
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
                return self._render_json({"jobs": [job.to_dict() for job in self.orchestrator.list(identity)]})
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
        except (json.JSONDecodeError, RecipeValidationError, OrchestrationError, RunnerUnavailableError, PermissionError, ValueError) as exc:
            return f"Không thể thực hiện: {exc}"

    def _wizard_input(
        self, identity: Identity, value: str, language: str, session: dict[str, Any]
    ) -> BotResponse:
        awaiting = str(session.get("awaiting") or "")
        try:
            if awaiting == "url":
                source = {"kind": "https" if value.casefold().startswith("https://") else "http", "uri": value}
            elif awaiting == "drive":
                source = {"kind": "rclone", "uri": value}
            elif awaiting == "local" and identity.role == "admin" and session.get("execution") == "local-windows":
                source = {"kind": "local", "uri": value}
            else:
                return self._recovery(language)
            probe = {
                "schemaVersion": 1,
                "task": "source_mirror",
                "device": "probe",
                "source": source,
                "execution": {"target": session.get("execution", "github-auto")},
            }
            BuildRecipe.from_dict(probe)
            session.pop("awaiting", None)
            session.update({"step": "device", "source": source})
            self.ui_state.set_session(identity.subject, session)
            return self._device_picker(identity.subject, language, session)
        except (RecipeValidationError, ValueError) as exc:
            return BotResponse(TEXT[language]["input_invalid"].format(error=exc), self._back_markup(language))

    def _source_library(self, identity: Identity, language: str, session: dict[str, Any]) -> BotResponse:
        provider = self.cloud_provider or (
            (lambda value: self.runtime.cloud_library(category=value)) if self.runtime else None
        )
        if not provider:
            return BotResponse(TEXT[language]["no_roms"], self._back_markup(language))
        payload = provider("sources")
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        usable = [
            entry for entry in entries
            if isinstance(entry, dict)
            and str(entry.get("path") or "")
            and not str(entry.get("path") or "").endswith(".metadata.json")
        ][:12]
        if not usable:
            return BotResponse(TEXT[language]["no_roms"], self._back_markup(language))
        session.update({"step": "library", "library": usable})
        self.ui_state.set_session(identity.subject, session)
        rows = [[(self._trim(str(item.get("name") or item["path"]), 44), f"v1:lib:{index}")]
                for index, item in enumerate(usable)]
        rows.append([(TEXT[language]["back"], "v1:menu")])
        names = "\n".join(f"• {item.get('name') or item['path']}" for item in usable)
        return BotResponse(f"{TEXT[language]['library_title']}\n\n{names}", self._inline(rows))

    def _source_picker(self, identity: Identity, language: str, session: dict[str, Any]) -> BotResponse:
        rows = [
            [(TEXT[language]["source_library"], "v1:src:library")],
            [(TEXT[language]["source_url"], "v1:src:url")],
            [(TEXT[language]["source_drive"], "v1:src:drive")],
        ]
        if session.get("execution") == "local-windows" and identity.role == "admin":
            rows.append([(TEXT[language]["source_local"], "v1:src:local")])
        rows.append([(TEXT[language]["back"], "v1:menu")])
        return BotResponse(TEXT[language]["choose_source"], self._inline(rows))

    def _run_picker(self, language: str) -> BotResponse:
        return BotResponse(TEXT[language]["choose_run"], self._inline([
            [(TEXT[language]["run_github"], "v1:run:github")],
            [(TEXT[language]["back"], "v1:menu")],
        ]))

    def _device_picker(
        self, user_id: int | str, language: str, session: dict[str, Any] | None = None
    ) -> BotResponse:
        devices = self._devices()
        active = session or self._require_session(user_id)
        active["device_options"] = [list(item) for item in devices[:30]]
        self.ui_state.set_session(user_id, active)
        rows = [[(self._trim(f"{product} — {name}", 50), f"v1:dev:{index}")]
                for index, (product, name) in enumerate(devices[:30])]
        rows.append([(TEXT[language]["back"], "v1:menu")])
        names = "\n".join(f"• {product} — {name}" for product, name in devices[:30])
        return BotResponse(f"{TEXT[language]['choose_device']}\n\n{names}", self._inline(rows))

    def _mod_version_picker(
        self, user_id: int | str, language: str, session: dict[str, Any] | None = None
    ) -> BotResponse:
        active = session or self._require_session(user_id)
        versions = self._mod_versions(active)
        active["mod_version_options"] = versions[:20]
        self.ui_state.set_session(user_id, active)
        rows = [[(version, f"v1:mv:{index}")] for index, version in enumerate(versions[:20])]
        rows.append([(TEXT[language]["back"], "v1:menu")])
        return BotResponse(TEXT[language]["choose_mod_version"], self._inline(rows))

    def _preset_picker(self, language: str) -> BotResponse:
        return BotResponse(TEXT[language]["choose_preset"], self._inline([
            [(TEXT[language]["preset_lite"], "v1:pre:lite")],
            [(TEXT[language]["preset_plus"], "v1:pre:plus")],
            [(TEXT[language]["preset_both"], "v1:pre:both")],
            [(TEXT[language]["back"], "v1:menu")],
        ]))

    def _start_mod_picker(
        self, user_id: int | str, language: str, session: dict[str, Any]
    ) -> BotResponse:
        catalog = self.catalog_provider()
        version = str(session.get("mod_version") or "")
        raw_by_version = catalog.get("modsByVersion", catalog.get("mods", {}))
        raw_mods = raw_by_version.get(version, []) if isinstance(raw_by_version, dict) else []
        options = [
            str(item.get("name") or "") if isinstance(item, dict) else str(item).strip()
            for item in raw_mods
            if (
                isinstance(item, str) and item.strip()
            ) or (
                isinstance(item, dict)
                and item.get("ready")
                and str(item.get("name") or "")
            )
        ]
        defaults_by_version = catalog.get("presetDefaultsByVersion", {})
        version_defaults = defaults_by_version.get(version, {}) if isinstance(defaults_by_version, dict) else {}
        preset_key = "lite" if session.get("preset") == "lite" else "both"
        defaults = version_defaults.get(preset_key, []) if isinstance(version_defaults, dict) else []
        if session.get("preset") == "both":
            compatible = {str(item) for item in defaults}
            options = [name for name in options if name in compatible]
        selected = {str(item) for item in defaults if str(item) in options}
        session["mod_options"] = options
        session["selected_mods"] = [item for item in options if item in selected]
        self.ui_state.set_session(user_id, session)
        return self._mod_picker(language, session, page=0)

    def _mod_picker(self, language: str, session: dict[str, Any], *, page: int) -> BotResponse:
        options = session.get("mod_options")
        selected = set(str(item) for item in session.get("selected_mods", []))
        if not isinstance(options, list):
            return self._recovery(language)
        page_size = 8
        pages = max(1, (len(options) + page_size - 1) // page_size)
        current = max(0, min(page, pages - 1))
        start = current * page_size
        rows: list[list[tuple[str, str]]] = []
        for index, raw_name in enumerate(options[start : start + page_size], start=start):
            name = str(raw_name)
            key = "mod_selected" if name in selected else "mod_unselected"
            rows.append([(
                self._trim(TEXT[language][key].format(name=name), 52),
                f"v1:mod:{index}",
            )])
        if pages > 1:
            navigation: list[tuple[str, str]] = []
            if current > 0:
                navigation.append((TEXT[language]["mods_previous"], f"v1:mods:{current - 1}"))
            if current + 1 < pages:
                navigation.append((TEXT[language]["mods_next"], f"v1:mods:{current + 1}"))
            if navigation:
                rows.append(navigation)
        rows.append([
            (TEXT[language]["mods_select_all"], "v1:mods_all:1"),
            (TEXT[language]["mods_clear_all"], "v1:mods_all:0"),
        ])
        rows.append([(TEXT[language]["mods_done"], "v1:mods_done")])
        rows.append([(TEXT[language]["back"], "v1:menu")])
        status = TEXT[language]["mod_page"].format(
            page=current + 1,
            pages=pages,
            selected=len(selected),
            total=len(options),
        )
        message = f"{TEXT[language]['choose_mods']}\n{status}"
        if not options:
            message += f"\n\n{TEXT[language]['mods_empty']}"
        else:
            message += "\n\n" + "\n".join(str(item) for item in options[start : start + page_size])
        return BotResponse(message, self._inline(rows))

    def _confirmation(self, language: str, session: dict[str, Any]) -> BotResponse:
        task_key = {
            "build": "task_build",
            "source_mirror": "task_mirror",
            "artifact_publish": "task_publish",
        }.get(str(session.get("task")), "task_build")
        task = TEXT[language][task_key]
        run = TEXT[language]["run_github"] if session.get("execution") == "github-auto" else TEXT[language]["run_windows"]
        source = self._trim(self._display_source(session.get("source", {})), 80)
        selected_mods = [str(item) for item in session.get("selected_mods", [])]
        visible_mods = ", ".join(selected_mods[:12])
        if len(selected_mods) > 12:
            visible_mods += f" +{len(selected_mods) - 12}"
        text = TEXT[language]["summary"].format(
            task=task,
            run=run,
            source=source,
            device=session.get("device", "—"),
            mod_version=session.get("mod_version", "—"),
            preset=session.get("preset", "—"),
            mod_count=len(selected_mods),
            mods=visible_mods or "—",
            advanced=TEXT[language]["advanced"],
        )
        return BotResponse(text, self._inline([
            [(TEXT[language]["confirm"], "v1:confirm")],
            [(TEXT[language]["edit"], "v1:new")],
            [(TEXT[language]["back"], "v1:menu")],
        ]))

    def _recipe_from_session(self, session: dict[str, Any]) -> BuildRecipe:
        if session.get("step") != "confirm":
            raise ValueError("Build wizard is incomplete")
        task = str(session["task"])
        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "task": task,
            "device": session["device"],
            "source": session["source"],
            "execution": {"target": session["execution"]},
            "storage": {"remote": self.storage_remote, "publishArtifact": True},
        }
        if task == "build":
            payload["build"] = {
                "preset": session["preset"],
                "modVersion": session["mod_version"],
                "mods": list(session.get("selected_mods", [])),
                "package": True,
                "notifyTelegram": True,
            }
        return BuildRecipe.from_dict(payload)

    def _jobs_menu(self, identity: Identity, language: str) -> BotResponse:
        jobs = self.orchestrator.list(identity)[:12]
        if not jobs:
            return BotResponse(TEXT[language]["no_jobs"], self._inline([
                [(TEXT[language]["new"], "v1:new")],
                [(TEXT[language]["back"], "v1:menu")],
            ]))
        rows = [[
            (
                f"{self._status_label(job.status.value, language)} · {job.job_id[:12]}",
                f"v1:job:{self.ui_state.remember_job(identity.subject, job.job_id)}",
            )
        ] for job in jobs]
        rows.append([(TEXT[language]["back"], "v1:menu")])
        return BotResponse(TEXT[language]["jobs"], self._inline(rows))

    def _job_callback(self, action: str, job_id: str, identity: Identity, language: str) -> BotResponse:
        try:
            if action == "events":
                events = self.orchestrator.events(job_id, identity)[-10:]
                lines = [
                    f"{event.sequence}. {self._event_label(event.type, language)}"
                    for event in events
                ] or ["—"]
                job = self.orchestrator.inspect(job_id, identity)
                return BotResponse(
                    TEXT[language]["events_title"].format(job_id=job_id) + "\n\n" + "\n".join(lines),
                    self._job_markup(job, language, identity.subject),
                )
            if action == "cancel":
                current = self.orchestrator.inspect(job_id, identity)
                job = self.orchestrator.cancel(job_id, identity)
                if self.runtime:
                    self.runtime.cancel_external(current)
                    self.runtime.notify_terminal(job)
                return BotResponse(self._render_job(job, language), self._job_markup(job, language, identity.subject))
            if action == "resume":
                job = self.runtime.resume(job_id, identity) if self.runtime else self.orchestrator.resume(job_id, identity)
                return BotResponse(self._render_job(job, language), self._job_markup(job, language, identity.subject))
            job = self.orchestrator.inspect(job_id, identity)
            if self.runtime:
                job = self.runtime.refresh(job)
            if action == "artifact":
                text = "\n\n".join(
                    f"{item.name}\n{item.public_url or item.uri}\nSHA-256: {item.sha256}"
                    for item in job.artifacts
                ) or TEXT[language]["no_artifact"]
                return BotResponse(text, self._job_markup(job, language, identity.subject))
            return BotResponse(self._render_job(job, language), self._job_markup(job, language, identity.subject))
        except (OrchestrationError, PermissionError):
            return BotResponse(TEXT[language]["job_not_found"], self._back_markup(language))

    def _render_job(self, job: JobManifest, language: str) -> str:
        return TEXT[language]["status"].format(
            job_id=job.job_id,
            status=self._status_label(job.status.value, language),
            stage=self._stage_label(job.stage, language),
            progress=round(job.progress * 100),
            runner=job.runner or "—",
        )

    def _job_markup(
        self, job: JobManifest, language: str, viewer_id: int | str
    ) -> dict[str, object]:
        reference = self.ui_state.remember_job(viewer_id, job.job_id)
        rows = [[
            (TEXT[language]["refresh"], f"v1:job:{reference}"),
            (TEXT[language]["events"], f"v1:events:{reference}"),
        ]]
        if job.artifacts:
            rows.append([(TEXT[language]["artifact"], f"v1:artifact:{reference}")])
        if job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            rows.append([(TEXT[language]["cancel"], f"v1:cancel:{reference}")])
        if job.status in {JobStatus.FAILED, JobStatus.CANCELLED} and job.checkpoint:
            rows.append([(TEXT[language]["resume"], f"v1:resume:{reference}")])
        rows.append([(TEXT[language]["jobs"], "v1:jobs"), (TEXT[language]["back"], "v1:menu")])
        return self._inline(rows)

    def _cloud_menu(self, language: str) -> BotResponse:
        provider = self.cloud_provider or (
            (lambda value: self.runtime.cloud_library(category=value)) if self.runtime else None
        )
        if not provider:
            return BotResponse(TEXT[language]["no_roms"], self._back_markup(language))
        try:
            payload = provider("sources")
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            names = [str(item.get("name") or item.get("path")) for item in entries[:20] if isinstance(item, dict)]
            text = TEXT[language]["library_title"] + "\n\n" + ("\n".join(f"• {name}" for name in names) or TEXT[language]["no_roms"])
            return BotResponse(text, self._inline([
                [(TEXT[language]["new"], "v1:new")],
                [(TEXT[language]["back"], "v1:menu")],
            ]))
        except (OSError, ValueError, RuntimeError) as exc:
            return BotResponse(TEXT[language]["failed"].format(error=exc), self._back_markup(language))

    def _diagnostics_menu(self, language: str) -> BotResponse:
        text = TEXT[language]["diagnostics_title"] + "\n\n" + self._render_details(self.diagnostics_provider())
        return BotResponse(text, self._back_markup(language))

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
                self.runtime.notify_terminal(cancelled)
            return self._render_json(cancelled.to_dict())
        if command == "/resume":
            resumed = self.runtime.resume(job_id, identity) if self.runtime else self.orchestrator.resume(job_id, identity)
            return self._render_json(resumed.to_dict())
        job = self.orchestrator.inspect(job_id, identity)
        if self.runtime:
            job = self.runtime.refresh(job)
        return "\n".join(
            f"{artifact.name}\n{artifact.public_url or artifact.uri}\nSHA-256: {artifact.sha256}"
            for artifact in job.artifacts
        ) or "Job chưa có artifact."

    def _devices(self) -> list[tuple[str, str]]:
        payload = self.catalog_provider()
        raw = payload.get("devices", []) if isinstance(payload, dict) else []
        devices = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            product = str(
                item.get("product_name")
                or item.get("productName")
                or item.get("product")
                or item.get("device")
                or ""
            ).strip()
            if product:
                devices.append((product, str(item.get("name") or product).strip()))
        if not devices:
            raise ValueError("Device catalog is empty")
        return devices

    def _mod_versions(self, session: Mapping[str, Any] | None = None) -> list[str]:
        payload = self.catalog_provider()
        raw = payload.get("modVersions", []) if isinstance(payload, dict) else []
        versions = [str(item).strip() for item in raw if str(item).strip()]
        if session and str(session.get("execution") or "").startswith("github"):
            available = payload.get("availableGitHubModVersions") if isinstance(payload, dict) else None
            if isinstance(available, list):
                allowed = {str(item) for item in available}
                versions = [version for version in versions if version in allowed]
        if not versions:
            raise ValueError("No MOD content-pack is available for the selected runner")
        return versions

    def _require_session(self, user_id: int | str) -> dict[str, Any]:
        session = self.ui_state.session(user_id)
        if not session:
            raise ValueError("Build session has expired")
        return session

    def _require_step(self, user_id: int | str, expected: str) -> dict[str, Any]:
        session = self._require_session(user_id)
        if session.get("step") != expected:
            raise ExpiredCallbackError("Callback does not match the active wizard step")
        return session

    @staticmethod
    def _help(identity: Identity, language: str) -> str:
        if language == "en":
            return HELP_ADMIN_EN if identity.role == "admin" else HELP_USER_EN
        return HELP_ADMIN_VI if identity.role == "admin" else HELP_USER_VI

    def _main_menu(self, language: str) -> BotResponse:
        markup = self._inline([
            [(TEXT[language]["new"], "v1:new")],
            [(TEXT[language]["jobs"], "v1:jobs"), (TEXT[language]["library"], "v1:cloud")],
            [(TEXT[language]["diagnostics"], "v1:diag"), (TEXT[language]["language"], f"v1:lang:{'en' if language == 'vi' else 'vi'}")],
        ])
        if self.web_app_url:
            markup["inline_keyboard"].insert(
                0, [{"text": TEXT[language]["mini_app"], "callback_data": "v1:app"}]
            )
        return BotResponse(TEXT[language]["welcome"], markup)

    def _mini_app_launcher(self, language: str) -> BotResponse:
        if not self.web_app_url:
            return BotResponse(TEXT[language]["failed"].format(error="Mini App URL is not configured"), self._back_markup(language))
        return BotResponse(
            TEXT[language]["mini_app_prompt"],
            {
                "keyboard": [[{
                    "text": TEXT[language]["mini_app"],
                    "web_app": {"url": self.web_app_url},
                }]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
                "input_field_placeholder": TEXT[language]["mini_app"],
            },
        )

    def _recovery(self, language: str) -> BotResponse:
        return BotResponse(TEXT[language]["expired"], self._back_markup(language))

    @staticmethod
    def _status_label(status: str, language: str) -> str:
        return STATUS_LABELS.get(language, {}).get(status, status)

    @classmethod
    def _stage_label(cls, stage: str | None, language: str) -> str:
        if not stage:
            return "—"
        return STAGE_LABELS.get(language, {}).get(stage, stage)

    @staticmethod
    def _event_label(event_type: str, language: str) -> str:
        return EVENT_LABELS.get(language, {}).get(event_type, event_type)

    @staticmethod
    def _display_source(source: object) -> str:
        if not isinstance(source, dict):
            return "—"
        uri = str(source.get("uri") or "—")
        if source.get("kind") not in {"http", "https"} or "?" not in uri:
            return uri
        parsed = urlsplit(uri)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "…", ""))

    def _back_markup(self, language: str) -> dict[str, object]:
        return self._inline([[(TEXT[language]["back"], "v1:menu")]])

    @staticmethod
    def _inline(rows: list[list[tuple[str, str]]]) -> dict[str, object]:
        return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}

    @staticmethod
    def _trim(value: str, length: int) -> str:
        return value if len(value) <= length else value[: length - 1] + "…"

    @staticmethod
    def _render_json(payload: object) -> str:
        value = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        return value if len(value) <= 3900 else value[:3880] + "\n…"

    @classmethod
    def _render_details(cls, payload: object, prefix: str = "") -> str:
        lines: list[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                label = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, (dict, list)):
                    lines.extend(cls._render_details(value, label).splitlines())
                else:
                    lines.append(f"{label}: {value}")
        elif isinstance(payload, list):
            for index, value in enumerate(payload):
                label = f"{prefix}[{index}]"
                if isinstance(value, (dict, list)):
                    lines.extend(cls._render_details(value, label).splitlines())
                else:
                    lines.append(f"{label}: {value}")
        else:
            lines.append(f"{prefix or 'value'}: {payload}")
        rendered = "\n".join(lines) or "—"
        return rendered if len(rendered) <= 3900 else rendered[:3880] + "\n…"


class TelegramLongPollingDaemon:
    def __init__(
        self,
        token: str,
        controller: TelegramBotController,
        *,
        http: requests.Session | None = None,
    ) -> None:
        self._token = token
        self.controller = controller
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._http = http if http is not None else requests.Session()
        self._stop = threading.Event()
        self._probe_threads: set[threading.Thread] = set()
        self._probe_threads_lock = threading.Lock()

    def stop(self) -> None:
        self._stop.set()

    def configure_webhook(self, public_api_url: str, secret: str) -> None:
        base_url = public_api_url.strip().rstrip("/")
        if not base_url.startswith("https://") or not secret:
            raise ValueError("Telegram webhook requires a public HTTPS API URL and secret")
        response = self._http.post(
            f"{self.base_url}/setWebhook",
            json={
                "url": f"{base_url}/telegram/webhook",
                "secret_token": secret,
                "allowed_updates": ["message", "callback_query"],
                "max_connections": 1,
                "drop_pending_updates": False,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise requests.RequestException("Telegram rejected the webhook configuration")

    @staticmethod
    def _is_probe_request(raw_data: str) -> bool:
        try:
            payload = json.loads(raw_data)
            return isinstance(payload, dict) and str(payload.get("action") or "").casefold() == "probe_source"
        except (json.JSONDecodeError, TypeError):
            return False

    def _complete_source_probe(self, user_id: int | str, chat_id: int | str, raw_data: str) -> None:
        try:
            response = self.controller.handle_web_app_data(user_id, raw_data)
            with requests.Session() as session:
                session.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": chat_id, **response.telegram_payload()},
                    timeout=20,
                ).raise_for_status()
        except (OSError, RuntimeError, requests.RequestException):
            pass
        finally:
            current = threading.current_thread()
            with self._probe_threads_lock:
                self._probe_threads.discard(current)

    def _defer_source_probe(self, user_id: int | str, chat_id: int | str, raw_data: str) -> bool:
        worker = threading.Thread(
            target=self._complete_source_probe,
            args=(user_id, chat_id, raw_data),
            name="wukong-telegram-source-probe",
            daemon=True,
        )
        with self._probe_threads_lock:
            # Bound concurrent probes so untrusted users cannot create an
            # unbounded number of network workers through the Mini App.
            active = {thread for thread in self._probe_threads if thread.is_alive()}
            self._probe_threads = active
            if len(active) >= 2:
                return False
            active.add(worker)
        worker.start()
        return True

    def register_commands(self) -> None:
        command_sets = self.controller.command_sets()
        self._http.post(
            f"{self.base_url}/setMyCommands",
            json={"commands": command_sets["vi"]},
            timeout=20,
        ).raise_for_status()
        self._http.post(
            f"{self.base_url}/setMyCommands",
            json={"commands": command_sets["en"], "language_code": "en"},
            timeout=20,
        ).raise_for_status()

    def process_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query") or {}
        if callback:
            sender = callback.get("from") or {}
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            data = callback.get("data")
            callback_id = callback.get("id")
            if not sender.get("id") or not chat.get("id") or not isinstance(data, str):
                return
            if callback_id:
                try:
                    self._http.post(
                        f"{self.base_url}/answerCallbackQuery",
                        json={"callback_query_id": callback_id},
                        timeout=20,
                    ).raise_for_status()
                except requests.RequestException:
                    pass
            response = self.controller.handle_callback(sender["id"], data)
            payload = {"chat_id": chat["id"], **response.telegram_payload()}
            if message.get("message_id") and "keyboard" not in response.reply_markup:
                payload["message_id"] = message["message_id"]
                endpoint = "editMessageText"
            else:
                endpoint = "sendMessage"
            try:
                self._http.post(
                    f"{self.base_url}/{endpoint}", json=payload, timeout=20
                ).raise_for_status()
            except requests.RequestException:
                if endpoint != "editMessageText":
                    raise
                payload.pop("message_id", None)
                self._http.post(
                    f"{self.base_url}/sendMessage", json=payload, timeout=20
                ).raise_for_status()
            return
        message = update.get("message") or {}
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        web_app_data = message.get("web_app_data") or {}
        if (
            sender.get("id")
            and chat.get("id")
            and isinstance(web_app_data, dict)
            and isinstance(web_app_data.get("data"), str)
        ):
            if self._is_probe_request(web_app_data["data"]):
                if not self._defer_source_probe(sender["id"], chat["id"], web_app_data["data"]):
                    self._http.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": chat["id"],
                            "text": "Hệ thống đang phân tích hai ROM khác. Hãy thử lại sau ít phút.\n\nTwo ROM analyses are already running. Please try again shortly.",
                        },
                        timeout=20,
                    ).raise_for_status()
                return
            response = self.controller.handle_web_app_data(sender["id"], web_app_data["data"])
            self._http.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat["id"], **response.telegram_payload()},
                timeout=20,
            ).raise_for_status()
            return
        text = message.get("text")
        if not sender.get("id") or not chat.get("id") or not isinstance(text, str):
            return
        response = self.controller.handle_ui(sender["id"], text)
        self._http.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": chat["id"], **response.telegram_payload()},
            timeout=20,
        ).raise_for_status()

    def run(self) -> None:
        offset = 0
        commands_registered = False
        next_registration_attempt = 0.0
        while not self._stop.is_set():
            if not commands_registered and time.monotonic() >= next_registration_attempt:
                try:
                    self.register_commands()
                    commands_registered = True
                except requests.RequestException:
                    next_registration_attempt = time.monotonic() + 60
            try:
                response = self._http.get(
                    f"{self.base_url}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": json.dumps(["message", "callback_query"]),
                    },
                    timeout=40,
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = max(offset, int(update["update_id"]) + 1)
                    self.process_update(update)
            except requests.RequestException:
                self._stop.wait(5)


class TelegramWebhookAdapter:
    """Transport adapter retained for a future VPS/webhook deployment."""

    def __init__(self, controller: TelegramBotController) -> None:
        self.controller = controller

    def handle_update(self, update: dict[str, Any]) -> BotResponse | None:
        callback = update.get("callback_query") or {}
        if callback:
            sender = callback.get("from") or {}
            data = callback.get("data")
            if sender.get("id") and isinstance(data, str):
                return self.controller.handle_callback(sender["id"], data)
            return None
        message = update.get("message") or {}
        sender = message.get("from") or {}
        text = message.get("text")
        if not sender.get("id") or not isinstance(text, str):
            return None
        return self.controller.handle_ui(sender["id"], text)

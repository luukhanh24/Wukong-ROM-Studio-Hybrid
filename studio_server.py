from __future__ import annotations

import argparse
import ctypes
import io
import importlib.util
import json
import os
import queue
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from studio_env import load_local_env
from studio_core import (
    DUAL_PHASE_STEPS,
    DUAL_SHARED_STEPS,
    JOBS_DIR,
    MOD_DIR,
    ROM_BUILD_DONE,
    ROOT_DIR,
    RUNTIME_DIR,
    STEP_DEFINITIONS,
    BuildSpec,
    StudioError,
    analyze_partition_layout,
    apply_rom_renames,
    build_edition_name,
    build_spec_fingerprint,
    claim_workspace,
    cleanup_workspace,
    clear_stage_cache,
    default_debloat_paths,
    default_studio_version,
    device_catalog_path,
    find_device,
    inspect_rom,
    is_managed_workspace,
    is_resume_compatible_workspace,
    list_mods,
    list_mod_versions,
    load_devices,
    normalize_device_catalog,
    normalize_studio_version,
    normalize_zip_validation_mode,
    plan_steps,
    preview_rom_renames,
    preset_default_mods,
    read_rom_metadata,
    rom_sha256,
    sanitize_version_name,
    save_devices,
    stage_cache_status,
    studio_version_name,
    validate_debloat_paths,
    workspace_for_version,
)
from studio_worker import EVENT_PREFIX
from telegram_progress import TelegramProgressReporter
from studio_paths import (
    BIN_ROOT,
    CONTENT_ROOT,
    DESKTOP_MODE,
    INSTALL_ROOT,
    LOG_ROOT,
    PATHS,
    WEB_ROOT,
    WORKSPACE_ROOT,
    platform_bin_dir,
    platform_tool_path,
)
from werkzeug.serving import make_server
from wukong.models import BuildRecipe, Identity, JobStatus, RecipeValidationError, preset_edition_label
from wukong.orchestrator import FileJobStore, HybridOrchestrator, OrchestrationError
from wukong.routing import RunnerInventory, RunnerUnavailableError
from wukong.github import GitHubActionsAdapter
from wukong.runtime import HybridRuntime
from wukong.security import validate_recipe_access
from wukong.source_probe import probe_http_source
from wukong.telegram import PRIMARY_TELEGRAM_ADMIN_ID, TelegramAccessStore
from wukong.telegram_bot import TelegramBotController, TelegramLongPollingDaemon
from wukong.telegram_mini_api import (
    TelegramJobNotifier,
    TelegramMiniAppAPI,
    TelegramMiniAppAPIServer,
)


STATIC_DIR = WEB_ROOT
SETTINGS_PATH = RUNTIME_DIR / "settings.json"
DATABASE_PATH = RUNTIME_DIR / "studio.db"
TERMINAL_STATUSES = {"success", "failed", "cancelled"}
SESSION_TOKEN = os.environ.get("WUKONG_STUDIO_SESSION_TOKEN", "").strip() or secrets.token_urlsafe(32)
SERVER_DESKTOP_MODE = DESKTOP_MODE
SERVER_SHUTDOWN: Callable[[], None] | None = None
DB_LOCK = threading.RLock()
PICKER_LOCK = threading.Lock()
STEP_UPDATE_LOCK = threading.RLock()
PACKAGE_LOCK = threading.RLock()
SETTINGS_LOCK = threading.RLock()
PACKAGE_SLOT = threading.Semaphore(1)
PACKAGE_TRACKERS: dict[str, dict[str, Any]] = {}
PACKAGE_PROCESSES: dict[str, dict[str, subprocess.Popen[str]]] = {}
TELEGRAM_PROGRESS = TelegramProgressReporter()
TELEGRAM_PROGRESS_LOCK = threading.RLock()
TELEGRAM_PROGRESS_HISTORY: dict[str, dict[str, Any]] = {}
UI_LOG_TAIL_BYTES = 192 * 1024
UI_LOG_BATCH_LINES = 100
PROCESS_LOG_FLUSH_BYTES = 64 * 1024
PROCESS_LOG_FLUSH_INTERVAL = 0.1
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ARTIFACT_VERSION_RE = re.compile(
    r"^Wukong_(?:Lite|Plus|Custom)_V[0-9]+(?:\.[0-9]+){1,3}_(?P<version>.+)_China_Stable_[0-9a-f]{8}\.zip$",
    re.IGNORECASE,
)


class _ProcessLogWriter:
    def __init__(
        self,
        handle: TextIO,
        *,
        flush_bytes: int = PROCESS_LOG_FLUSH_BYTES,
        flush_interval: float = PROCESS_LOG_FLUSH_INTERVAL,
    ) -> None:
        self.handle = handle
        self.flush_bytes = max(1, flush_bytes)
        self.flush_interval = max(0.01, flush_interval)
        self.pending_bytes = 0
        self.last_flush = time.monotonic()

    def write(self, line: str) -> None:
        self.handle.write(line)
        self.pending_bytes += len(line.encode("utf-8", errors="replace"))
        now = time.monotonic()
        if (
            line.startswith(EVENT_PREFIX)
            or self.pending_bytes >= self.flush_bytes
            or now - self.last_flush >= self.flush_interval
        ):
            self.flush(now)

    def flush(self, now: float | None = None) -> None:
        self.handle.flush()
        self.pending_bytes = 0
        self.last_flush = time.monotonic() if now is None else now
CONTENT_PACKS_PATH = RUNTIME_DIR / "content-packs.json"

load_local_env()


def _telegram_configured() -> bool:
    load_local_env(override=True)
    return bool(
        os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN")
        and os.environ.get("WUKONG_TELEGRAM_CHAT_ID")
    )


TELEGRAM_STEP_LABELS_VI = {
    "inspect_rom": "Phân tích ROM",
    "extract_payload": "Trích xuất payload",
    "unpack_partitions": "Giải nén phân vùng",
    "debloat": "Xóa ứng dụng không cần thiết",
    "apply_mod": "Áp dụng MOD",
    "sync_configs": "Đồng bộ fs_config và SELinux",
    "repack_partitions": "Đóng gói phân vùng",
    "repack_super": "Tạo super.img",
    "patch_vbmeta": "Vá vbmeta",
    "patch_vendor_boot": "Vá vendor_boot",
    "package_zip": "Đóng gói ROM ZIP",
    "notify_telegram": "Gửi báo cáo Telegram",
}
TELEGRAM_STEP_LABELS_EN = {step: label for step, label, _ in STEP_DEFINITIONS}


def _telegram_progress_enabled(job: dict[str, Any]) -> bool:
    return any(step.get("id") == "notify_telegram" for step in job.get("steps") or []) and bool(
        os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN")
        and os.environ.get("WUKONG_TELEGRAM_CHAT_ID")
    )


def _telegram_progress_expected(job: dict[str, Any]) -> list[tuple[str | None, str]]:
    step_ids = [str(step.get("id")) for step in job.get("steps") or [] if step.get("id")]
    if str((job.get("spec") or {}).get("preset") or "").lower() != "both":
        return [(None, step) for step in step_ids]
    shared = [
        step
        for step in step_ids
        if step in DUAL_SHARED_STEPS or step not in DUAL_PHASE_STEPS | {"notify_telegram"}
    ]
    phased = [step for step in step_ids if step in DUAL_PHASE_STEPS or step == "notify_telegram"]
    return (
        [(None, step) for step in shared]
        + [("Lite", step) for step in phased]
        + [("Plus", step) for step in phased]
    )


def _telegram_progress_phase(details: dict[str, Any]) -> str | None:
    phase = str(details.get("phase") or "").strip().lower()
    if phase in {"lite", "plus"}:
        return phase.title()
    task_id = str(details.get("taskId") or "").lower()
    if "lite" in task_id:
        return "Lite"
    if "plus" in task_id or "resume" in task_id:
        return "Plus"
    return None


def _telegram_progress_state(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job["id"])
    state = TELEGRAM_PROGRESS_HISTORY.get(job_id)
    expected = _telegram_progress_expected(job)
    if state is None or state.get("expected") != expected:
        state = {
            "expected": expected,
            "entries": {
                key: {"status": "pending", "details": {}}
                for key in expected
            },
            "lastKey": None,
        }
        TELEGRAM_PROGRESS_HISTORY[job_id] = state
    return state


def _record_telegram_progress_event(
    job: dict[str, Any],
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    state = _telegram_progress_state(job)
    if not payload or payload.get("type") != "step":
        return state
    step = str(payload.get("step") or "")
    if not step:
        return state
    details = dict(payload.get("details") or {})
    preset = str((job.get("spec") or {}).get("preset") or "").lower()
    phase = _telegram_progress_phase(details) if preset == "both" else None
    if preset == "both" and step in DUAL_PHASE_STEPS | {"notify_telegram"} and phase is None:
        return state
    key = (phase, step)
    if key not in state["entries"]:
        state["expected"].append(key)
        state["entries"][key] = {"status": "pending", "details": {}}
    entry = state["entries"][key]
    entry["status"] = str(payload.get("status") or entry["status"])
    entry["details"] = {**entry.get("details", {}), **details}
    state["lastKey"] = key
    return state


def _telegram_progress_snapshot(
    job: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    spec_payload = dict(job.get("spec") or {})
    locale = "en" if spec_payload.get("locale") == "en" else "vi"
    labels = TELEGRAM_STEP_LABELS_EN if locale == "en" else TELEGRAM_STEP_LABELS_VI
    timeline = []
    completed = 0.0
    for phase, step in state["expected"]:
        entry = state["entries"].get((phase, step), {"status": "pending", "details": {}})
        status = str(entry.get("status") or "pending")
        if status in {"success", "skipped"}:
            completed += 1.0
        elif status == "running":
            try:
                completed += max(0.0, min(100.0, float((entry.get("details") or {}).get("progress") or 0))) / 100
            except (TypeError, ValueError):
                pass
        label = labels.get(step, step)
        timeline.append(
            {
                "id": step,
                "label": f"{phase} · {label}" if phase else label,
                "status": status,
            }
        )
    status = str(job.get("status") or "running")
    percent = 100 if status == "success" else round(completed * 100 / max(1, len(timeline)))
    final_report_sent = any(
        step == "notify_telegram"
        and entry.get("status") == "success"
        and (entry.get("details") or {}).get("notified") is True
        for (phase, step), entry in state["entries"].items()
    )
    current_key = state.get("lastKey")
    current_entry = state["entries"].get(current_key, {}) if current_key else {}
    current_phase, current_step = current_key if current_key else (None, None)
    if status == "success":
        current_label = "Completed" if locale == "en" else "Đã hoàn tất"
    elif status == "cancelled":
        current_label = "Cancelled" if locale == "en" else "Đã hủy"
    elif current_step:
        current_label = labels.get(current_step, current_step)
        if current_phase:
            current_label = f"{current_phase} · {current_label}"
    else:
        current_label = "Starting worker" if locale == "en" else "Đang khởi động worker"
    started_at = job.get("startedAt")
    elapsed = 0.0
    if started_at:
        try:
            elapsed = max(0.0, time.time() - datetime.fromisoformat(str(started_at)).timestamp())
        except ValueError:
            pass
    spec = BuildSpec.from_dict(spec_payload)
    edition = preset_edition_label(spec.preset, spec.editionLabels)
    return {
        "jobId": job["id"],
        "status": status,
        "versionName": job.get("versionName"),
        "edition": edition,
        "studioVersion": studio_version_name(spec),
        "deviceName": spec_payload.get("deviceName") or "Wukong device",
        "productName": spec_payload.get("productName") or "-",
        "percent": percent,
        "currentLabel": current_label,
        "progressMessage": (current_entry.get("details") or {}).get("progressMessage"),
        "elapsedSeconds": elapsed,
        "steps": timeline,
        "error": job.get("error"),
        "locale": locale,
        "finalReportSent": final_report_sent,
    }


def _publish_telegram_progress(
    job_id: str,
    payload: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> None:
    job = get_job(job_id)
    if not job or not _telegram_progress_enabled(job):
        return
    with TELEGRAM_PROGRESS_LOCK:
        state = _record_telegram_progress_event(job, payload)
        snapshot = _telegram_progress_snapshot(job, state)
        terminal = snapshot["status"] in TERMINAL_STATUSES
        TELEGRAM_PROGRESS.publish(snapshot, force=force or terminal)
        if terminal:
            TELEGRAM_PROGRESS_HISTORY.pop(job_id, None)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_content_packs() -> list[dict[str, Any]]:
    if not CONTENT_PACKS_PATH.is_file():
        return []
    try:
        payload = json.loads(CONTENT_PACKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    packs = []
    content_root = CONTENT_ROOT.resolve()
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "").replace("/", os.sep)
        target_path = (content_root / target).resolve()
        safe_target = target_path == content_root or content_root in target_path.parents
        packs.append(
            {
                "id": str(item.get("id") or ""),
                "displayName": str(item.get("displayName") or item.get("id") or "Content pack"),
                "version": str(item.get("version") or "-"),
                "target": str(item.get("target") or ""),
                "installedAt": item.get("installedAt"),
                "healthy": safe_target and target_path.is_dir(),
            }
        )
    return packs


def _workspace_root() -> Path:
    return WORKSPACE_ROOT if SERVER_DESKTOP_MODE else ROOT_DIR


def _bin_root() -> Path:
    return BIN_ROOT if SERVER_DESKTOP_MODE else ROOT_DIR / "bin"


def _log_tail_offset(path: Path, max_bytes: int = UI_LOG_TAIL_BYTES) -> int:
    size = path.stat().st_size
    if size <= max_bytes:
        return 0
    with path.open("rb") as handle:
        start = size - max_bytes
        handle.seek(start - 1)
        if handle.read(1) != b"\n":
            handle.readline()
        return handle.tell()


def _clean_ui_log_line(line: str) -> str:
    return ANSI_ESCAPE_RE.sub("", line.rstrip())


def default_settings() -> dict[str, Any]:
    studio_versions = {
        version: default_studio_version(version)
        for version in list_mod_versions()
    }
    return {
        "roots": [str(INSTALL_ROOT if SERVER_DESKTOP_MODE else ROOT_DIR)],
        "locale": "vi",
        "theme": "light",
        "defaultPreset": "lite",
        "notifyTelegram": True,
        "debloatPaths": None,
        "stageCacheEnabled": True,
        "stageCacheMaxGb": 40,
        "zipValidationMode": "fast",
        "studioVersions": studio_versions,
    }


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_roots(roots: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in roots:
        path = Path(value).expanduser().resolve()
        if path.is_dir() and path.is_absolute() and str(path) not in normalized:
            normalized.append(str(path))
    if not normalized:
        normalized.append(str(INSTALL_ROOT if SERVER_DESKTOP_MODE else ROOT_DIR))
    return normalized


def load_settings() -> dict[str, Any]:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_PATH.is_file():
        try:
            settings = default_settings() | json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            corrupt = SETTINGS_PATH.with_name(
                f"{SETTINGS_PATH.name}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            try:
                os.replace(SETTINGS_PATH, corrupt)
            except OSError:
                pass
            settings = default_settings()
        except OSError:
            settings = default_settings()
    else:
        settings = default_settings()
    settings["roots"] = _normalize_roots(settings.get("roots", []))
    if settings.get("defaultPreset") == "standard":
        settings["defaultPreset"] = "lite"
    if isinstance(settings.get("debloatPaths"), list):
        try:
            settings["debloatPaths"] = validate_debloat_paths(settings["debloatPaths"])
        except StudioError:
            settings["debloatPaths"] = None
    else:
        settings["debloatPaths"] = None
    settings["locale"] = "en" if settings.get("locale") == "en" else "vi"
    settings["theme"] = "dark" if settings.get("theme") == "dark" else "light"
    settings["stageCacheEnabled"] = bool(settings.get("stageCacheEnabled", True))
    settings["zipValidationMode"] = normalize_zip_validation_mode(
        settings.get("zipValidationMode")
    )
    try:
        settings["stageCacheMaxGb"] = max(5, min(int(settings.get("stageCacheMaxGb", 40)), 500))
    except (TypeError, ValueError):
        settings["stageCacheMaxGb"] = 40
    raw_studio_versions = settings.get("studioVersions")
    if not isinstance(raw_studio_versions, dict):
        raw_studio_versions = {}
    settings["studioVersions"] = {
        version: normalize_studio_version(
            raw_studio_versions.get(version),
            default_studio_version(version),
        )
        for version in list_mod_versions()
    }
    return settings


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    with SETTINGS_LOCK:
        return _save_settings(payload)


def _save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    raw_debloat_paths = payload.get("debloatPaths", current.get("debloatPaths"))
    debloat_paths = (
        validate_debloat_paths(raw_debloat_paths)
        if isinstance(raw_debloat_paths, list)
        else None
    )
    raw_studio_versions = payload.get("studioVersions", current.get("studioVersions", {}))
    if not isinstance(raw_studio_versions, dict):
        raw_studio_versions = {}
    studio_versions = {
        version: normalize_studio_version(
            raw_studio_versions.get(version),
            current.get("studioVersions", {}).get(version, default_studio_version(version)),
        )
        for version in list_mod_versions()
    }
    settings = {
        "roots": _normalize_roots(payload.get("roots", current["roots"])),
        "locale": "en" if payload.get("locale") == "en" else "vi",
        "theme": "dark" if payload.get("theme") == "dark" else "light",
        "defaultPreset": (
            "lite"
            if payload.get("defaultPreset") == "standard"
            else payload.get("defaultPreset")
        )
        if payload.get("defaultPreset") in {"lite", "standard", "resume", "both", "custom"}
        else "lite",
        "notifyTelegram": bool(payload.get("notifyTelegram", False)) and _telegram_configured(),
        "debloatPaths": debloat_paths,
        "stageCacheEnabled": bool(payload.get("stageCacheEnabled", current.get("stageCacheEnabled", True))),
        "stageCacheMaxGb": max(
            5,
            min(int(payload.get("stageCacheMaxGb", current.get("stageCacheMaxGb", 40))), 500),
        ),
        "zipValidationMode": normalize_zip_validation_mode(
            payload.get("zipValidationMode", current.get("zipValidationMode"))
        ),
        "studioVersions": studio_versions,
    }
    _write_json_atomic(SETTINGS_PATH, settings)
    return settings


def _authorize_rom_path(value: str) -> Path:
    raw = str(value).strip().strip('"')
    if not raw:
        raise ValueError("ROM path is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("ROM path must be absolute")
    path = path.resolve()
    if not path.is_file():
        raise ValueError("ROM ZIP does not exist")
    if path.suffix.lower() != ".zip":
        raise ValueError("ROM must be a .zip file")

    settings = load_settings()
    if not _path_is_under(path, settings["roots"]):
        settings["roots"] = _normalize_roots([*settings["roots"], str(path.parent)])
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return path


def bind_recipe_mod_release_version(recipe: BuildRecipe) -> BuildRecipe:
    label = load_settings()["studioVersions"].get(
        recipe.build.mod_version,
        default_studio_version(recipe.build.mod_version),
    )
    return replace(recipe, build=replace(recipe.build, mod_release_version=label))


def _authorize_layout_source(value: str) -> Path:
    raw = str(value).strip().strip('"')
    if not raw:
        raise ValueError("Layout source path is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("Layout source path must be absolute")
    path = path.resolve()
    if not path.is_file():
        raise ValueError("Layout source does not exist")
    if path.suffix.casefold() not in {".img", ".txt", ".json"}:
        raise ValueError("Layout source must be super.img, lpdump .txt or metadata .json")
    settings = load_settings()
    if not _path_is_under(path, settings["roots"]):
        settings["roots"] = _normalize_roots([*settings["roots"], str(path.parent)])
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return path


def _pick_rom_file() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Native file picker is unavailable") from exc

    with PICKER_LOCK:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError("Native file picker could not be opened") from exc
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            selected = filedialog.askopenfilename(
                parent=root,
                title="Select ROM ZIP",
                initialdir=str(Path.home()),
                filetypes=[("ROM ZIP files", "*.zip"), ("ZIP files", "*.zip")],
            )
        finally:
            root.destroy()
    return _authorize_rom_path(selected) if selected else None


def _authorize_rom_folder(value: str) -> dict[str, Any]:
    raw = str(value).strip().strip('"')
    if not raw:
        raise ValueError("ROM folder path is required")
    folder = Path(raw).expanduser()
    if not folder.is_absolute():
        raise ValueError("ROM folder path must be absolute")
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError("ROM folder does not exist")

    settings = load_settings()
    if not _path_is_under(folder, settings["roots"]):
        settings["roots"] = _normalize_roots([*settings["roots"], str(folder)])
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    roms = sorted(
        (child.resolve() for child in folder.iterdir() if child.is_file() and child.suffix.lower() == ".zip"),
        key=lambda path: path.name.lower(),
    )
    return {"folder": str(folder), "roms": [str(path) for path in roms]}


def _pick_windows_rom_folder() -> dict[str, Any] | None:
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class WukongFolderPicker
{
    [ComImport]
    [Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
    private class FileOpenDialog
    {
    }

    [ComImport]
    [Guid("42F85136-DB7E-439C-85F1-E4075D135FC8")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileDialog
    {
        [PreserveSig] int Show(IntPtr parent);
        void SetFileTypes(uint count, IntPtr filterSpec);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IShellItem shellItem);
        void SetFolder(IShellItem shellItem);
        void GetFolder(out IShellItem shellItem);
        void GetCurrentSelection(out IShellItem shellItem);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void GetResult(out IShellItem shellItem);
        void AddPlace(IShellItem shellItem, uint alignment);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
        void Close(int result);
        void SetClientGuid(ref Guid guid);
        void ClearClientData();
        void SetFilter(IntPtr filter);
    }

    [ComImport]
    [Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void BindToHandler(IntPtr bindContext, ref Guid handler, ref Guid interfaceId, out IntPtr result);
        void GetParent(out IShellItem shellItem);
        void GetDisplayName(uint displayNameType, out IntPtr name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(IShellItem shellItem, uint hint, out int order);
    }

    public static string PickFolder(string title)
    {
        const uint FOS_PICKFOLDERS = 0x00000020;
        const uint FOS_FORCEFILESYSTEM = 0x00000040;
        const uint FOS_PATHMUSTEXIST = 0x00000800;
        const uint FOS_DONTADDTORECENT = 0x02000000;
        const uint SIGDN_FILESYSPATH = 0x80058000;
        const int ERROR_CANCELLED = unchecked((int)0x800704C7);

        object dialogObject = new FileOpenDialog();
        IFileDialog dialog = (IFileDialog)dialogObject;
        try
        {
            uint options;
            dialog.GetOptions(out options);
            dialog.SetOptions(options | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_DONTADDTORECENT);
            dialog.SetTitle(title);
            dialog.SetOkButtonLabel("Select folder");

            int result = dialog.Show(IntPtr.Zero);
            if (result == ERROR_CANCELLED)
                return "";
            Marshal.ThrowExceptionForHR(result);

            IShellItem shellItem;
            dialog.GetResult(out shellItem);
            try
            {
                IntPtr pathPointer;
                shellItem.GetDisplayName(SIGDN_FILESYSPATH, out pathPointer);
                try
                {
                    return Marshal.PtrToStringUni(pathPointer) ?? "";
                }
                finally
                {
                    Marshal.FreeCoTaskMem(pathPointer);
                }
            }
            finally
            {
                Marshal.ReleaseComObject(shellItem);
            }
        }
        finally
        {
            Marshal.ReleaseComObject(dialogObject);
        }
    }
}
'@
[Console]::Out.Write([WukongFolderPicker]::PickFolder("Select folder containing ROM ZIP files"))
"""
    if not PICKER_LOCK.acquire(blocking=False):
        raise RuntimeError("A folder picker is already open")
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-STA",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Native folder picker timed out") from exc
    finally:
        PICKER_LOCK.release()
    if result.returncode != 0:
        message = result.stderr.strip() or "Native folder picker could not be opened"
        raise RuntimeError(message)
    selected = result.stdout.strip()
    return _authorize_rom_folder(selected) if selected else None


def _pick_rom_folder() -> dict[str, Any] | None:
    if os.name == "nt":
        return _pick_windows_rom_folder()
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Native folder picker is unavailable") from exc

    with PICKER_LOCK:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError("Native folder picker could not be opened") from exc
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(
                parent=root,
                title="Select ROM folder",
                initialdir=str(Path.home()),
                mustexist=True,
            )
        finally:
            root.destroy()
    return _authorize_rom_folder(selected) if selected else None


def _infer_job_version_name(
    job_id: str,
    spec_json: str,
    workspace: str,
    output_zip: str | None,
) -> str:
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError:
        spec = {}
    rom_path = Path(str(spec.get("romPath") or ""))
    if rom_path.is_file():
        try:
            return str(read_rom_metadata(rom_path)["version_name"])
        except (OSError, StudioError):
            pass
    if output_zip:
        match = ARTIFACT_VERSION_RE.match(Path(output_zip).name)
        if match:
            return sanitize_version_name(match.group("version"), fallback=job_id)
    workspace_path = Path(workspace)
    workspace_name = workspace_path.name
    if (
        workspace_name
        and workspace_name != job_id
        and workspace_path.parent.resolve() == _workspace_root().resolve()
    ):
        return sanitize_version_name(workspace_name, fallback=job_id)
    return sanitize_version_name(rom_path.stem, fallback=job_id)


def init_database() -> None:
    PATHS.ensure_writable_layout()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    ROM_BUILD_DONE.mkdir(parents=True, exist_ok=True)
    with DB_LOCK, closing(sqlite3.connect(DATABASE_PATH)) as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                version_name TEXT,
                status TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                current_step TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                output_zip TEXT,
                workspace TEXT NOT NULL,
                log_path TEXT NOT NULL,
                error TEXT,
                pid INTEGER
            )
            """
        )
        columns = {row[1] for row in database.execute("PRAGMA table_info(jobs)")}
        if "version_name" not in columns:
            backup_dir = INSTALL_ROOT / "Backups" / "database"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"studio-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
            with closing(sqlite3.connect(backup_path)) as backup:
                database.backup(backup)
            database.execute("ALTER TABLE jobs ADD COLUMN version_name TEXT")
        for job_id, spec_json, workspace, output_zip in database.execute(
            """
            SELECT id, spec_json, workspace, output_zip
            FROM jobs
            WHERE version_name IS NULL OR version_name = ''
            """
        ):
            database.execute(
                "UPDATE jobs SET version_name = ? WHERE id = ?",
                (
                    _infer_job_version_name(job_id, spec_json, workspace, output_zip),
                    job_id,
                ),
            )
        database.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                finished_at = COALESCE(finished_at, ?),
                error = COALESCE(error, 'Studio server restarted while job was running'),
                pid = NULL
            WHERE status IN ('running', 'packaging')
            """,
            (utc_now(),),
        )
        database.commit()


def _db_rows(query: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with DB_LOCK, closing(sqlite3.connect(DATABASE_PATH)) as database:
        database.row_factory = sqlite3.Row
        return list(database.execute(query, parameters).fetchall())


def _db_execute(query: str, parameters: tuple[Any, ...] = ()) -> None:
    with DB_LOCK, closing(sqlite3.connect(DATABASE_PATH)) as database:
        database.execute(query, parameters)
        database.commit()


def row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["versionName"] = data.pop("version_name", "") or data["id"]
    data["spec"] = json.loads(data.pop("spec_json"))
    data["steps"] = json.loads(data.pop("steps_json"))
    data["currentStep"] = data.pop("current_step")
    data["createdAt"] = data.pop("created_at")
    data["startedAt"] = data.pop("started_at")
    data["finishedAt"] = data.pop("finished_at")
    data["outputZip"] = data.pop("output_zip")
    data["logPath"] = data.pop("log_path")
    return data


def get_job(job_id: str) -> dict[str, Any] | None:
    rows = _db_rows("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return row_to_job(rows[0]) if rows else None


def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    return [
        row_to_job(row)
        for row in _db_rows("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
    ]


def list_artifacts(limit: int = 200) -> list[dict[str, Any]]:
    artifacts = []
    for job in list_jobs(limit):
        outputs: list[str] = []
        for step in job.get("steps", []):
            details = step.get("details") or {}
            for output in details.get("outputZips") or []:
                if output and output not in outputs:
                    outputs.append(output)
        if job.get("outputZip") and job["outputZip"] not in outputs:
            outputs.append(job["outputZip"])
        for output in outputs:
            artifact = dict(job)
            artifact["outputZip"] = output
            artifact["artifactExists"] = Path(output).is_file()
            artifacts.append(artifact)
    return artifacts


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    _db_execute(
        f"UPDATE jobs SET {columns} WHERE id = ?",
        tuple(fields.values()) + (job_id,),
    )


def create_job(spec_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        spec = BuildSpec.from_dict(spec_payload)
    except StudioError as exc:
        raise ValueError(str(exc)) from exc
    previous: dict[str, Any] | None = None
    resume_from_job_id = spec.resumeFromJobId
    if resume_from_job_id:
        previous = get_job(resume_from_job_id)
        if not previous:
            raise ValueError("Resume source job does not exist")
        if previous["status"] not in {"failed", "cancelled"}:
            raise ValueError("Only failed or cancelled UI jobs can be resumed")
        requested_rom_path = spec.romPath
        previous_spec = BuildSpec.from_dict(previous["spec"])
        if not previous_spec.romSha256 or not previous_spec.specFingerprint:
            raise ValueError("Resume source job predates the current workspace validation format")
        spec = previous_spec
        spec.romPath = requested_rom_path
        spec.resumeFromJobId = resume_from_job_id
        spec.resumePreset = previous_spec.resumePreset or previous_spec.preset
        spec.preset = "resume"

    requested_steps = plan_steps(spec)
    if not requested_steps:
        raise ValueError("Build plan must contain at least one step")
    if (spec.notifyTelegram or "notify_telegram" in requested_steps) and not _telegram_configured():
        raise ValueError("Telegram environment variables are not configured")
    preflight = inspect_rom(
        spec.romPath,
        spec.modName,
        mod_names=spec.selected_mod_names(),
        mod_version=spec.modVersion,
        debloat_paths=spec.debloatPaths,
        required_steps=requested_steps,
    )
    if not preflight["ok"]:
        raise ValueError("; ".join(preflight["errors"]))

    rom_digest = rom_sha256(spec.romPath)
    if previous:
        if rom_digest != previous["spec"].get("romSha256"):
            raise ValueError("Resume ROM does not match the source job SHA-256")
        spec_fingerprint = str(previous["spec"]["specFingerprint"])
    else:
        spec_fingerprint = build_spec_fingerprint(spec)
    spec.romSha256 = rom_digest
    spec.specFingerprint = spec_fingerprint

    job_id = secrets.token_hex(8)
    metadata = preflight.get("metadata") or {}
    version_name = str(metadata.get("version_name") or Path(spec.romPath).stem or "rom")
    try:
        workspace = workspace_for_version(
            version_name,
            fallback=Path(spec.romPath).stem or "rom",
            root=_workspace_root(),
        )
    except StudioError as exc:
        raise ValueError(str(exc)) from exc
    version_name = workspace.name
    if previous:
        previous_workspace = Path(previous["workspace"]).resolve()
        if previous_workspace != workspace:
            raise ValueError("Resume workspace does not match ROM version_name")
        if not is_resume_compatible_workspace(
            previous_workspace,
            root=_workspace_root(),
            rom_sha256=rom_digest,
            spec_fingerprint=spec_fingerprint,
        ):
            raise ValueError("Resume workspace is unavailable or uses an outdated pipeline")
        workspace = previous_workspace
    try:
        claim_workspace(
            workspace,
            job_id,
            version_name,
            root=_workspace_root(),
            rom_sha256=rom_digest,
            spec_fingerprint=spec_fingerprint,
        )
    except StudioError as exc:
        raise ValueError(str(exc)) from exc
    log_path = JOBS_DIR / f"{job_id}.log"
    spec_file = JOBS_DIR / f"{job_id}.json"
    spec_dict = {
        "romPath": spec.romPath,
        "modName": spec.modName,
        "modNames": spec.selected_mod_names(),
        "modVersion": spec.modVersion,
        "debloatPaths": spec.debloatPaths,
        "preset": spec.preset,
        "enabledSteps": spec.enabledSteps,
        "resumeFromJobId": spec.resumeFromJobId,
        "notifyTelegram": spec.notifyTelegram,
        "romSha256": spec.romSha256,
        "specFingerprint": spec.specFingerprint,
        "resumePreset": spec.resumePreset,
        "versionName": version_name,
        "productName": metadata.get("product_name"),
        "deviceName": (preflight.get("device") or {}).get("name"),
        "soc": (preflight.get("device") or {}).get("soc"),
        "locale": load_settings().get("locale", "vi"),
    }
    spec_file.write_text(json.dumps(spec_dict, indent=2), encoding="utf-8")
    steps = plan_steps(spec, workspace)
    step_state = [{"id": step, "status": "pending"} for step in steps]
    _db_execute(
        """
        INSERT INTO jobs (
            id, version_name, status, spec_json, steps_json, current_step, created_at,
            workspace, log_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            version_name,
            "queued",
            json.dumps(spec_dict),
            json.dumps(step_state),
            None,
            utc_now(),
            str(workspace),
            str(log_path),
        ),
    )
    return get_job(job_id)  # type: ignore[return-value]


def _update_step(job_id: str, payload: dict[str, Any]) -> None:
    with STEP_UPDATE_LOCK:
        job = get_job(job_id)
        if not job:
            return
        steps = job["steps"]
        target = next((step for step in steps if step["id"] == payload["step"]), None)
        if target is None:
            target = {"id": payload["step"], "status": "pending"}
            steps.append(target)
        status = payload.get("status", target["status"])
        details = dict(target.get("details") or {})
        details.update(payload.get("details") or {})
        if (
            payload["step"] == "package_zip"
            and status == "success"
            and details.get("packagingPending")
        ):
            status = "running"
        target["status"] = status
        if payload.get("message"):
            target["message"] = payload["message"]
        if details:
            target["details"] = details
        fields = {
            "current_step": payload["step"],
            "steps_json": json.dumps(steps),
            "error": payload.get("message") if payload.get("status") == "failed" else job["error"],
        }
        if (
            payload["step"] == "package_zip"
            and payload.get("status") == "success"
            and not details.get("packagingPending")
        ):
            fields["output_zip"] = details.get("outputZip")
        update_job(job_id, **fields)


def _handle_worker_event(job_id: str, payload: dict[str, Any]) -> None:
    if payload.get("type") == "plan":
        steps = [{"id": step, "status": "pending"} for step in payload.get("steps", [])]
        update_job(job_id, steps_json=json.dumps(steps))
        _publish_telegram_progress(job_id, force=True)
    elif payload.get("type") == "step":
        _update_step(job_id, payload)
        _publish_telegram_progress(job_id, payload)
    elif payload.get("type") == "worker":
        if payload.get("status") == "success":
            update_job(job_id, output_zip=payload.get("outputZip"))
        elif payload.get("status") == "failed":
            update_job(job_id, error=payload.get("error", "Worker failed"))


def _kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


def _worker_environment(task_name: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    environment["WUKONG_STUDIO_ASYNC_PACKAGE"] = "1"
    if task_name:
        environment["WUKONG_STUDIO_TASK_NAME"] = task_name
    return environment


def _worker_command(job: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "-u",
        str(ROOT_DIR / "studio_worker.py"),
        "--job-id",
        job["id"],
        "--spec-file",
        str(JOBS_DIR / f"{job['id']}.json"),
        "--workspace",
        job["workspace"],
        "--task-name",
        job["versionName"],
    ]


def _packager_command(task_file: str | Path) -> list[str]:
    return [
        sys.executable,
        "-u",
        str(ROOT_DIR / "studio_packager.py"),
        "--task-file",
        str(task_file),
    ]


def _package_tracker(job_id: str) -> dict[str, Any]:
    return PACKAGE_TRACKERS.setdefault(
        job_id,
        {
            "active": set(),
            "completed": [],
            "expected": [],
            "failed": None,
            "workerDone": False,
            "timings": {},
        },
    )


def _package_timing_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    timing = dict(payload.get("timing") or {})
    validation = dict(payload.get("validation") or {})

    def seconds(name: str) -> float:
        value = timing.get(name, validation.get(name, 0))
        try:
            return round(max(0.0, float(value or 0)), 3)
        except (TypeError, ValueError):
            return 0.0

    staging_seconds = seconds("stagingSeconds")
    compression_seconds = seconds("compressionSeconds")
    validation_seconds = seconds("validationSeconds")
    calculated_total = staging_seconds + compression_seconds + validation_seconds
    try:
        total_seconds = max(0.0, float(timing.get("totalSeconds") or calculated_total))
    except (TypeError, ValueError):
        total_seconds = calculated_total
    return {
        "stagingSeconds": staging_seconds,
        "compressionSeconds": compression_seconds,
        "validationSeconds": validation_seconds,
        "totalSeconds": round(total_seconds, 3),
        "validationMode": normalize_zip_validation_mode(
            timing.get("validationMode") or validation.get("validationMode")
        ),
    }


def _aggregate_package_timings(tracker: dict[str, Any] | None) -> dict[str, Any]:
    timings = dict((tracker or {}).get("timings") or {})
    if not timings:
        return {"packageTimings": {}}
    staging_seconds = round(sum(item["stagingSeconds"] for item in timings.values()), 3)
    compression_seconds = round(sum(item["compressionSeconds"] for item in timings.values()), 3)
    validation_seconds = round(sum(item["validationSeconds"] for item in timings.values()), 3)
    total_seconds = round(sum(item["totalSeconds"] for item in timings.values()), 3)
    modes = {str(item.get("validationMode") or "fast") for item in timings.values()}
    return {
        "packageTimings": timings,
        "packageTaskCount": len(timings),
        "stagingSeconds": staging_seconds,
        "compressionSeconds": compression_seconds,
        "validationSeconds": validation_seconds,
        "totalSeconds": total_seconds,
        "durationSeconds": total_seconds,
        "validationMode": modes.pop() if len(modes) == 1 else "mixed",
    }


def _merge_package_step_details(job_id: str, output_zip: str | None = None) -> list[str]:
    with PACKAGE_LOCK:
        job = get_job(job_id)
        if not job:
            return []
        step = next((item for item in job["steps"] if item["id"] == "package_zip"), None)
        details = dict((step or {}).get("details") or {})
        tracker = PACKAGE_TRACKERS.get(job_id)
        outputs = list((tracker or {}).get("completed") or details.get("outputZips") or [])
        timing_details = _aggregate_package_timings(tracker)
        if output_zip and output_zip not in outputs:
            outputs.append(output_zip)
        details.update(
            {
                "outputZip": output_zip or details.get("outputZip"),
                "outputZips": outputs,
                "packagingPending": True,
                "progress": 100 if output_zip else int(details.get("progress") or 0),
                "progressMessage": "ZIP validated" if output_zip else "ZIP running in background",
                **timing_details,
            }
        )
        _update_step(
            job_id,
            {
                "step": "package_zip",
                "status": "running",
                "details": details,
            },
        )
        return outputs


def _finalize_packaging(job_id: str) -> None:
    with PACKAGE_LOCK:
        tracker = PACKAGE_TRACKERS.get(job_id)
        if not tracker:
            return
        active = bool(tracker["active"])
        worker_done = bool(tracker["workerDone"])
        failure = tracker["failed"]
        completed = list(tracker["completed"])
        expected = list(tracker["expected"])
        timing_details = _aggregate_package_timings(tracker)
    job = get_job(job_id)
    if job and job["status"] == "cancelled":
        _publish_telegram_progress(job_id, force=True)
        if not active:
            with PACKAGE_LOCK:
                PACKAGE_TRACKERS.pop(job_id, None)
                PACKAGE_PROCESSES.pop(job_id, None)
        return
    if worker_done and not active and expected and set(completed) != set(expected):
        missing = sorted(set(expected) - set(completed))
        failure = f"Background packaging did not complete expected artifacts: {', '.join(missing)}"
    if failure:
        update_job(
            job_id,
            status="failed",
            finished_at=utc_now(),
            pid=None,
            current_step="package_zip",
            error=str(failure),
        )
        job = get_job(job_id)
        if job:
            _update_step(
                job_id,
                {
                    "step": "package_zip",
                    "status": "failed",
                    "message": str(failure),
                    "details": {
                        "outputZips": completed,
                        "packagingPending": False,
                        **timing_details,
                    },
                },
            )
        _publish_telegram_progress(
            job_id,
            {
                "type": "step",
                "step": "package_zip",
                "status": "failed",
                "message": str(failure),
                "details": {"progressMessage": str(failure)},
            },
            force=True,
        )
        if not active:
            with PACKAGE_LOCK:
                PACKAGE_TRACKERS.pop(job_id, None)
                PACKAGE_PROCESSES.pop(job_id, None)
        return
    if not worker_done or active:
        return
    outputs = expected or completed
    final_output = outputs[-1] if outputs else None
    cleanup_details: dict[str, Any] = {"workspaceCleaned": False}
    if job:
        workspace = Path(job["workspace"]).resolve()
        try:
            cleanup_details["workspaceCleaned"] = cleanup_workspace(
                workspace,
                root=_workspace_root(),
                expected_job_id=job_id,
            )
            if cleanup_details["workspaceCleaned"]:
                log_path = Path(job["logPath"])
                with log_path.open("a", encoding="utf-8", newline="\n") as log:
                    log.write(f"[*] Cleaned workspace after validated package: {workspace}\n")
        except (OSError, StudioError) as exc:
            cleanup_details["cleanupWarning"] = str(exc)
    _update_step(
        job_id,
        {
            "step": "package_zip",
            "status": "success",
            "details": {
                "outputZip": final_output,
                "outputZips": outputs,
                "packagingPending": False,
                "progress": 100,
                "progressMessage": "ZIP 100%",
                "finishedAt": utc_now(),
                **timing_details,
                **cleanup_details,
            },
        },
    )
    update_job(
        job_id,
        status="success",
        finished_at=utc_now(),
        pid=None,
        current_step=None,
        output_zip=final_output,
        error=None,
    )
    _publish_telegram_progress(job_id, force=True)
    with PACKAGE_LOCK:
        PACKAGE_TRACKERS.pop(job_id, None)
        PACKAGE_PROCESSES.pop(job_id, None)


def _handle_package_event(job_id: str, payload: dict[str, Any]) -> None:
    event_type = payload.get("type")
    if event_type == "step":
        _update_step(job_id, payload)
        _publish_telegram_progress(job_id, payload)
        return
    if event_type != "package":
        return
    status = payload.get("status")
    if status == "success":
        output_zip = str(payload.get("outputZip") or "")
        task_id = str(payload.get("taskId") or "")
        timing = _package_timing_from_payload(payload)
        timing.update(
            {
                "phase": payload.get("phase"),
                "outputZip": output_zip or None,
            }
        )
        with PACKAGE_LOCK:
            tracker = _package_tracker(job_id)
            if output_zip and output_zip not in tracker["completed"]:
                tracker["completed"].append(output_zip)
            if task_id:
                tracker.setdefault("timings", {})[task_id] = timing
        _merge_package_step_details(job_id, output_zip or None)
        _publish_telegram_progress(
            job_id,
            {
                "type": "step",
                "step": "package_zip",
                "status": "success",
                "details": {
                    "taskId": payload.get("taskId"),
                    "phase": payload.get("phase"),
                    "progress": 100,
                    "progressMessage": "ZIP validated",
                },
            },
        )
    elif status == "failed":
        with PACKAGE_LOCK:
            _package_tracker(job_id)["failed"] = payload.get("error") or "Background packaging failed"
        _publish_telegram_progress(
            job_id,
            {
                "type": "step",
                "step": "package_zip",
                "status": "failed",
                "message": payload.get("error"),
                "details": {
                    "taskId": payload.get("taskId"),
                    "phase": payload.get("phase"),
                    "progressMessage": payload.get("error") or "Background packaging failed",
                },
            },
            force=True,
        )


def _run_background_packager(job_id: str, task_id: str, task_file: str, log_path: Path) -> None:
    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True
    process: subprocess.Popen[str] | None = None
    slot_acquired = False
    try:
        PACKAGE_SLOT.acquire()
        slot_acquired = True
        with PACKAGE_LOCK:
            tracker = _package_tracker(job_id)
            if tracker["failed"]:
                return
        process = subprocess.Popen(
            _packager_command(task_file),
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
            env=_worker_environment(),
            **popen_kwargs,
        )
        with PACKAGE_LOCK:
            PACKAGE_PROCESSES.setdefault(job_id, {})[task_id] = process
        with log_path.open("a", encoding="utf-8", newline="\n") as log:
            log_writer = _ProcessLogWriter(log)
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    log_writer.write(line)
                    if line.startswith(EVENT_PREFIX):
                        try:
                            payload = json.loads(line[len(EVENT_PREFIX) :])
                            payload.setdefault("taskId", task_id)
                            if payload.get("type") == "step":
                                details = dict(payload.get("details") or {})
                                details.setdefault("taskId", task_id)
                                payload["details"] = details
                            _handle_package_event(job_id, payload)
                        except json.JSONDecodeError:
                            pass
            finally:
                log_writer.flush()
        return_code = process.wait()
        if return_code != 0:
            with PACKAGE_LOCK:
                tracker = _package_tracker(job_id)
                if not tracker["failed"]:
                    tracker["failed"] = f"Packager {task_id} exited with code {return_code}"
    except OSError as exc:
        with PACKAGE_LOCK:
            _package_tracker(job_id)["failed"] = str(exc)
    finally:
        with PACKAGE_LOCK:
            tracker = _package_tracker(job_id)
            tracker["active"].discard(task_id)
            PACKAGE_PROCESSES.get(job_id, {}).pop(task_id, None)
            failure = tracker["failed"]
        if failure:
            job = get_job(job_id)
            if job and job.get("pid"):
                _kill_process_tree(int(job["pid"]))
            with PACKAGE_LOCK:
                siblings = list(PACKAGE_PROCESSES.get(job_id, {}).values())
            for sibling in siblings:
                if not process or sibling.pid != process.pid:
                    _kill_process_tree(sibling.pid)
        if slot_acquired:
            PACKAGE_SLOT.release()
        _finalize_packaging(job_id)


def _start_background_packager(job_id: str, details: dict[str, Any], log_path: Path) -> None:
    task_id = str(details.get("taskId") or "")
    task_file = str(details.get("taskFile") or "")
    if not task_id or not task_file:
        return
    with PACKAGE_LOCK:
        tracker = _package_tracker(job_id)
        if task_id in tracker["active"] or task_id in PACKAGE_PROCESSES.get(job_id, {}):
            return
        tracker["active"].add(task_id)
    thread = threading.Thread(
        target=_run_background_packager,
        args=(job_id, task_id, task_file, log_path),
        name=f"studio-package-{job_id[:8]}-{task_id}",
        daemon=True,
    )
    thread.start()


def _cancel_package_processes(job_id: str, reason: str = "Cancelled by user") -> None:
    with PACKAGE_LOCK:
        processes = list(PACKAGE_PROCESSES.get(job_id, {}).values())
        tracker = PACKAGE_TRACKERS.get(job_id)
        if tracker and not tracker["failed"]:
            tracker["failed"] = reason
    for process in processes:
        _kill_process_tree(process.pid)


class QueueManager:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.wakeup = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="studio-queue", daemon=True)
        self.thread.start()

    def notify(self) -> None:
        self.wakeup.set()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        self.wakeup.set()
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout)

    def _next_job(self) -> dict[str, Any] | None:
        rows = _db_rows(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC, rowid ASC LIMIT 1"
        )
        return row_to_job(rows[0]) if rows else None

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            job = self._next_job()
            if not job:
                self.wakeup.wait(1)
                self.wakeup.clear()
                continue
            self._run_job(job)

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        latest = get_job(job_id)
        if not latest or latest["status"] != "queued":
            return
        update_job(job_id, status="running", started_at=utc_now())
        _publish_telegram_progress(job_id, force=True)
        log_path = Path(job["logPath"])
        task_name = job["versionName"]
        command = _worker_command(job)
        creationflags = 0
        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            popen_kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(
                command,
            cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                env=_worker_environment(task_name),
                **popen_kwargs,
            )
        except OSError as exc:
            update_job(job_id, status="failed", finished_at=utc_now(), error=str(exc))
            _publish_telegram_progress(job_id, force=True)
            return
        latest = get_job(job_id)
        if latest and latest["status"] == "cancelled":
            _kill_process_tree(process.pid)
        else:
            update_job(job_id, pid=process.pid)
        worker_result: dict[str, Any] | None = None
        with log_path.open("a", encoding="utf-8", newline="\n") as log:
            log_writer = _ProcessLogWriter(log)
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    log_writer.write(line)
                    if line.startswith(EVENT_PREFIX):
                        try:
                            payload = json.loads(line[len(EVENT_PREFIX) :])
                            _handle_worker_event(job_id, payload)
                            if payload.get("type") == "step":
                                details = payload.get("details") or {}
                                if (
                                    payload.get("step") == "package_zip"
                                    and payload.get("status") == "success"
                                    and details.get("packagingPending")
                                ):
                                    _start_background_packager(job_id, details, log_path)
                            elif payload.get("type") == "worker" and payload.get("status") == "success":
                                worker_result = payload
                        except json.JSONDecodeError:
                            pass
            finally:
                log_writer.flush()
        return_code = process.wait()
        latest = get_job(job_id)
        if latest and latest["status"] == "cancelled":
            _cancel_package_processes(job_id)
            update_job(job_id, finished_at=utc_now(), pid=None)
            _publish_telegram_progress(job_id, force=True)
        elif return_code == 0:
            with PACKAGE_LOCK:
                tracker = PACKAGE_TRACKERS.get(job_id)
                if tracker:
                    tracker["workerDone"] = True
                    tracker["expected"] = list((worker_result or {}).get("outputZips") or [])
                    active = bool(tracker["active"])
                    failure = tracker["failed"]
                else:
                    active = False
                    failure = None
            if tracker:
                if failure:
                    _finalize_packaging(job_id)
                elif active:
                    update_job(
                        job_id,
                        status="packaging",
                        pid=None,
                        current_step="package_zip",
                    )
                    _publish_telegram_progress(job_id, force=True)
                else:
                    _finalize_packaging(job_id)
            else:
                update_job(job_id, status="success", finished_at=utc_now(), pid=None, current_step=None)
                _publish_telegram_progress(job_id, force=True)
        else:
            _cancel_package_processes(job_id, "Build worker failed before packaging completed")
            update_job(
                job_id,
                status="failed",
                finished_at=utc_now(),
                pid=None,
                error=(latest or {}).get("error") or f"Worker exited with code {return_code}",
            )
            _publish_telegram_progress(job_id, force=True)


QUEUE_MANAGER = QueueManager()


def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port is not None
        )
    except ValueError:
        return False


def _path_is_under(path: Path, roots: Iterable[str]) -> bool:
    resolved = path.resolve()
    for root in roots:
        root_path = Path(root).resolve()
        if resolved == root_path or root_path in resolved.parents:
            return True
    return False


def _filesystem_listing(value: str | None) -> dict[str, Any]:
    settings = load_settings()
    roots = settings["roots"]
    path = Path(value).expanduser().resolve() if value else Path(roots[0]).resolve()
    if not _path_is_under(path, roots):
        raise ValueError("Path is outside configured roots")
    if not path.is_dir():
        raise ValueError("Path is not a directory")
    entries = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.is_dir() or (child.is_file() and child.suffix.lower() == ".zip"):
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "type": "directory" if child.is_dir() else "zip",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
    parent = path.parent if path.parent != path and _path_is_under(path.parent, roots) else None
    return {"path": str(path), "parent": str(parent) if parent else None, "entries": entries}


def diagnostics() -> dict[str, Any]:
    workspace_root = _workspace_root()
    workspace_root.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(workspace_root)
    bin_dir = platform_bin_dir(_bin_root())
    seven_zip = shutil.which("7z") or shutil.which("7zz")
    bundled_seven_zip = platform_tool_path("7z", _bin_root())
    if not seven_zip and bundled_seven_zip.is_file():
        seven_zip = str(bundled_seven_zip)
    binaries = {
        name: platform_tool_path(name, _bin_root()).is_file()
        for name in ["extract.erofs", "mkfs.erofs", "lpmake", "magiskboot", "cpio"]
    }
    def package_exists(name: str) -> bool:
        try:
            return bool(importlib.util.find_spec(name))
        except (ImportError, ModuleNotFoundError):
            return False

    packages = {
        name: package_exists(name)
        for name in ["flask", "requests", "toml", "zstandard", "google.protobuf"]
    }

    def version(command: list[str]) -> str:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=5, check=False
            )
            return (result.stdout or result.stderr).splitlines()[0].strip()
        except (OSError, subprocess.TimeoutExpired, IndexError):
            return "unavailable"

    return {
        "python": sys.version.split()[0],
        "java": version(["java", "-version"]),
        "sevenZip": seven_zip or "Python zipfile fallback",
        "disk": {"free": disk.free, "total": disk.total},
        "binaries": binaries,
        "packages": packages,
        "telegramConfigured": _telegram_configured(),
        "unsignedBinaryWarning": True,
        "md5AuthenticityWarning": True,
        "apktool": {
            "ready": (bin_dir / "apktool_3.0.2.jar").is_file(),
            "path": str(bin_dir / "apktool_3.0.2.jar"),
        },
    }


def _filetime_seconds(value: Any) -> float:
    return ((int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)) / 10_000_000


def _process_metrics(pid: int | None) -> dict[str, Any]:
    if not pid or pid <= 0:
        return {"available": False}
    if os.name != "nt":
        stat_path = Path("/proc") / str(pid) / "stat"
        status_path = Path("/proc") / str(pid) / "status"
        try:
            stat = stat_path.read_text(encoding="utf-8").split()
            ticks = os.sysconf("SC_CLK_TCK")
            memory = 0
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    memory = int(line.split()[1]) * 1024
                    break
            return {
                "available": True,
                "workingSetBytes": memory,
                "privateBytes": memory,
                "cpuTimeSeconds": round((int(stat[13]) + int(stat[14])) / ticks, 3),
            }
        except (OSError, ValueError, IndexError):
            return {"available": False}

    class FileTime(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("PageFaultCount", ctypes.c_uint32),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
    ]
    kernel32.GetProcessTimes.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCountersEx),
        ctypes.c_uint32,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not handle:
        return {"available": False}
    try:
        creation = FileTime()
        exit_time = FileTime()
        kernel = FileTime()
        user = FileTime()
        memory = ProcessMemoryCountersEx()
        memory.cb = ctypes.sizeof(ProcessMemoryCountersEx)
        times_ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        memory_ok = psapi.GetProcessMemoryInfo(
            handle,
            ctypes.byref(memory),
            memory.cb,
        )
        if not times_ok and not memory_ok:
            return {"available": False}
        return {
            "available": True,
            "workingSetBytes": int(memory.WorkingSetSize) if memory_ok else 0,
            "privateBytes": int(memory.PrivateUsage) if memory_ok else 0,
            "cpuTimeSeconds": round(
                _filetime_seconds(kernel) + _filetime_seconds(user),
                3,
            ) if times_ok else 0,
        }
    finally:
        kernel32.CloseHandle(handle)


def _job_metrics(job: dict[str, Any]) -> dict[str, Any]:
    log_path = Path(job["logPath"])
    output_path = Path(job["outputZip"]) if job.get("outputZip") else None
    workspace = Path(job["workspace"])
    disk = shutil.disk_usage(workspace.parent if workspace.parent.exists() else _workspace_root())
    steps = []
    for step in job.get("steps", []):
        details = step.get("details") or {}
        steps.append(
            {
                "id": step.get("id"),
                "status": step.get("status"),
                "durationSeconds": float(details.get("durationSeconds") or 0),
                "cacheHit": details.get("cacheHit"),
                "phase": details.get("phase"),
            }
        )
    return {
        "jobId": job["id"],
        "status": job["status"],
        "pid": job.get("pid"),
        "process": _process_metrics(job.get("pid")),
        "logBytes": log_path.stat().st_size if log_path.is_file() else 0,
        "artifactBytes": output_path.stat().st_size if output_path and output_path.is_file() else 0,
        "diskFreeBytes": disk.free,
        "diskTotalBytes": disk.total,
        "steps": steps,
        "stageCache": stage_cache_status(),
        "capturedAt": utc_now(),
    }


def _diagnostics_bundle(job: dict[str, Any]) -> bytes:
    public_job = dict(job)
    public_job.pop("logPath", None)
    public_job.pop("pid", None)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("job.json", json.dumps(public_job, ensure_ascii=False, indent=2))
        archive.writestr("metrics.json", json.dumps(_job_metrics(job), ensure_ascii=False, indent=2))
        archive.writestr("diagnostics.json", json.dumps(diagnostics(), ensure_ascii=False, indent=2))
        archive.writestr("settings-public.json", json.dumps(load_settings(), ensure_ascii=False, indent=2))
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "createdAt": utc_now(),
                    "studioVersion": "1.0.0",
                    "containsSecrets": False,
                },
                indent=2,
            ),
        )
        log_path = Path(job["logPath"])
        if log_path.is_file():
            archive.write(log_path, "build.log")
    return buffer.getvalue()


def create_app(*, start_queue: bool = True) -> Flask:
    init_database()
    app = Flask(__name__, static_folder=None)
    hybrid_store = FileJobStore(JOBS_DIR / "hybrid")
    def hybrid_inventory() -> RunnerInventory:
        token = os.environ.get("WUKONG_GITHUB_TOKEN", "").strip()
        repository = os.environ.get("WUKONG_GITHUB_REPOSITORY", "").strip()
        if not token or "/" not in repository:
            return RunnerInventory(False)
        owner, name = repository.split("/", 1)
        try:
            return GitHubActionsAdapter(owner, name, token).runner_inventory()
        except Exception:
            return RunnerInventory(False)

    hybrid_orchestrator = HybridOrchestrator(
        store=hybrid_store,
        workspace_root=_workspace_root() / ".wkstudio" / "hybrid",
        inventory_provider=hybrid_inventory,
        access_validator=lambda recipe, identity: validate_recipe_access(
            recipe,
            identity,
            local_roots=load_settings()["roots"],
            allowed_remote=os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive"),
        ),
    )
    hybrid_runtime = HybridRuntime(
        orchestrator=hybrid_orchestrator,
        store=hybrid_store,
        workspace_root=_workspace_root() / ".wkstudio" / "hybrid",
        data_root=RUNTIME_DIR,
    )
    windows_identity = Identity("windows", "local", "admin")
    def clear_hybrid_cache() -> dict[str, Any]:
        active = [
            job
            for job in hybrid_orchestrator.list(windows_identity)
            if job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        ]
        if active:
            raise OrchestrationError("Cannot clear cache while hybrid jobs are active")
        return clear_stage_cache()

    telegram_daemon: TelegramLongPollingDaemon | None = None
    telegram_mini_api_server: TelegramMiniAppAPIServer | None = None
    telegram_token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
    telegram_admins = {
        item.strip()
        for item in os.environ.get("WUKONG_TELEGRAM_ADMIN_IDS", "").split(",")
        if item.strip()
    }
    telegram_admins.add(PRIMARY_TELEGRAM_ADMIN_ID)
    if start_queue and telegram_token and telegram_admins:
        access = TelegramAccessStore(RUNTIME_DIR / "telegram-access.json", admin_ids=telegram_admins)
        hybrid_runtime.terminal_notifier = TelegramJobNotifier(telegram_token)
        telegram_catalog_provider = lambda: {
            "devices": load_devices(),
            "modVersions": list_mod_versions(),
            "modsByVersion": {version: list_mods(version) for version in list_mod_versions()},
            "modReleaseVersions": {
                version: default_studio_version(version)
                for version in list_mod_versions()
            },
        }
        fixed_telegram_release_versions = lambda: {
            version: default_studio_version(version)
            for version in list_mod_versions()
        }
        telegram_diagnostics_provider = lambda: {
            "system": diagnostics(),
            "cache": stage_cache_status(),
        }
        controller = TelegramBotController(
            access=access,
            orchestrator=hybrid_orchestrator,
            catalog_provider=telegram_catalog_provider,
            diagnostics_provider=telegram_diagnostics_provider,
            cache_provider=stage_cache_status,
            cache_clearer=clear_hybrid_cache,
            cloud_provider=lambda category: hybrid_runtime.cloud_library(category=category),
            source_probe_provider=lambda uri: probe_http_source(uri).to_dict(),
            runtime=hybrid_runtime,
        )
        telegram_daemon = TelegramLongPollingDaemon(telegram_token, controller)
        threading.Thread(
            target=telegram_daemon.run,
            name="wukong-telegram-long-polling",
            daemon=True,
        ).start()
        web_app_url = os.environ.get("WUKONG_TELEGRAM_WEB_APP_URL", "").strip()
        if web_app_url:
            mini_api = TelegramMiniAppAPI(
                bot_token=telegram_token,
                allowed_origin=web_app_url,
                access=access,
                orchestrator=hybrid_orchestrator,
                runtime=hybrid_runtime,
                catalog_provider=telegram_catalog_provider,
                diagnostics_provider=telegram_diagnostics_provider,
                source_probe_provider=lambda uri: probe_http_source(uri).to_dict(),
                release_versions_provider=fixed_telegram_release_versions,
                release_versions_saver=None,
                cloud_provider=lambda category: hybrid_runtime.cloud_library(category=category),
                cache_provider=stage_cache_status,
                cache_clearer=clear_hybrid_cache,
                max_init_data_age_seconds=int(
                    os.environ.get("WUKONG_TELEGRAM_MINI_APP_MAX_AUTH_AGE", "3600")
                ),
            )
            telegram_mini_api_server = TelegramMiniAppAPIServer(
                mini_api,
                host=os.environ.get("WUKONG_TELEGRAM_MINI_APP_API_BIND", "127.0.0.1"),
                port=int(os.environ.get("WUKONG_TELEGRAM_MINI_APP_API_PORT", "8766")),
            )
            telegram_mini_api_server.start()
    app.extensions["wukong_telegram_daemon"] = telegram_daemon
    app.extensions["wukong_telegram_mini_api_server"] = telegram_mini_api_server

    @app.before_request
    def protect_api() -> None:
        if not request.path.startswith("/api/"):
            return
        if not _is_allowed_origin(request.headers.get("Origin")):
            abort(403)
        supplied = request.headers.get("X-Studio-Token")
        if request.path.endswith("/events"):
            supplied = supplied or request.args.get("token")
        if not secrets.compare_digest(supplied or "", SESSION_TOKEN):
            abort(403)

    @app.get("/")
    def index() -> Response:
        content = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return Response(content.replace("__STUDIO_TOKEN__", SESSION_TOKEN), mimetype="text/html")

    @app.get("/static/<path:filename>")
    def static_file(filename: str) -> Response:
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/health")
    def health() -> Response:
        return jsonify(
            {
                "status": "ready",
                "version": "1.0.0",
                "desktopMode": SERVER_DESKTOP_MODE,
                "installRoot": str(INSTALL_ROOT),
                "contentReady": MOD_DIR.is_dir() and platform_bin_dir(BIN_ROOT).is_dir(),
            }
        )

    @app.post("/api/v1/recipes/validate")
    def hybrid_recipe_validate() -> Response:
        try:
            recipe = bind_recipe_mod_release_version(
                BuildRecipe.from_dict(request.get_json(force=True) or {})
            )
            hybrid_orchestrator.validate_access(recipe, windows_identity)
            decision = hybrid_orchestrator.validate(recipe)
            return jsonify(
                {
                    "ok": True,
                    "recipe": recipe.to_dict(),
                    "recipeDigest": recipe.digest,
                    "runner": decision.to_dict(),
                }
            )
        except (RecipeValidationError, RunnerUnavailableError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/v1/sources/probe")
    def hybrid_source_probe() -> Response:
        try:
            payload = request.get_json(force=True) or {}
            uri = str(payload.get("uri") or "").strip()
            if not uri:
                raise ValueError("ROM source URL is required")
            return jsonify(probe_http_source(uri).to_dict())
        except (ValueError, OSError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/v1/jobs")
    def hybrid_job_create() -> Response:
        try:
            recipe = bind_recipe_mod_release_version(
                BuildRecipe.from_dict(request.get_json(force=True) or {})
            )
            manifest = hybrid_orchestrator.submit(recipe, windows_identity)
            if start_queue:
                hybrid_runtime.start(manifest)
            return jsonify(manifest.to_dict()), 201
        except (RecipeValidationError, RunnerUnavailableError, OrchestrationError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/v1/jobs")
    def hybrid_jobs_list() -> Response:
        return jsonify(
            {
                "jobs": [
                    hybrid_runtime.refresh(manifest).to_dict()
                    for manifest in hybrid_orchestrator.list(windows_identity)
                ]
            }
        )

    @app.get("/api/v1/catalog")
    def hybrid_catalog() -> Response:
        versions = list_mod_versions()
        return jsonify(
            {
                "devices": load_devices(),
                "presets": ["lite", "plus", "both", "custom"],
                "modVersions": versions,
                "modsByVersion": {version: list_mods(version) for version in versions},
                "contentPacks": list_content_packs(),
            }
        )

    @app.get("/api/v1/diagnostics")
    def hybrid_diagnostics() -> Response:
        inventory = hybrid_inventory()
        return jsonify(
            {
                "system": diagnostics(),
                "runner": {
                    "selfHostedOnline": inventory.self_hosted_online,
                    "freeDiskBytes": inventory.free_disk_bytes,
                    "memoryBytes": inventory.memory_bytes,
                    "logicalCpus": inventory.logical_cpus,
                },
                "cloudConfigured": hybrid_runtime.rclone_config is not None,
            }
        )

    @app.get("/api/v1/cache")
    def hybrid_cache_status() -> Response:
        return jsonify(stage_cache_status())

    @app.post("/api/v1/cache/clear")
    def hybrid_cache_clear() -> Response:
        try:
            return jsonify(clear_hybrid_cache())
        except OrchestrationError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.get("/api/v1/cloud/library")
    def hybrid_cloud_library() -> Response:
        try:
            return jsonify(hybrid_runtime.cloud_library(category=request.args.get("category", "artifacts")))
        except (ValueError, OSError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/v1/jobs/<job_id>")
    def hybrid_job_detail(job_id: str) -> Response:
        try:
            manifest = hybrid_orchestrator.inspect(job_id, windows_identity)
            return jsonify(hybrid_runtime.refresh(manifest).to_dict())
        except OrchestrationError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/v1/jobs/<job_id>/events")
    def hybrid_job_events(job_id: str) -> Response:
        try:
            after = max(0, int(request.args.get("after", "0")))
            return jsonify(
                {
                    "events": [
                        event.to_dict()
                        for event in hybrid_orchestrator.events(job_id, windows_identity, after=after)
                    ]
                }
            )
        except ValueError:
            return jsonify({"error": "Event cursor must be an integer"}), 400
        except OrchestrationError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/v1/jobs/<job_id>/cancel")
    def hybrid_job_cancel(job_id: str) -> Response:
        try:
            current = hybrid_orchestrator.inspect(job_id, windows_identity)
            cancelled = hybrid_orchestrator.cancel(job_id, windows_identity)
            hybrid_runtime.cancel_external(current)
            return jsonify(cancelled.to_dict())
        except OrchestrationError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/v1/jobs/<job_id>/resume")
    def hybrid_job_resume(job_id: str) -> Response:
        try:
            resumed = (
                hybrid_runtime.resume(job_id, windows_identity)
                if start_queue
                else hybrid_orchestrator.resume(job_id, windows_identity)
            )
            return jsonify(resumed.to_dict()), 201
        except OrchestrationError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.post("/api/shutdown")
    def shutdown() -> Response:
        if not SERVER_DESKTOP_MODE:
            return jsonify({"error": "Shutdown is only available in desktop mode"}), 404
        active = [
            job
            for job in list_jobs(100)
            if job["status"] in {"queued", "running", "packaging"}
        ]
        if active:
            return jsonify({"error": "Build jobs are still active", "jobs": active}), 409
        if SERVER_SHUTDOWN is None:
            return jsonify({"error": "Server shutdown is unavailable"}), 503
        if telegram_daemon:
            telegram_daemon.stop()
        if telegram_mini_api_server:
            telegram_mini_api_server.stop()
        threading.Timer(0.1, SERVER_SHUTDOWN).start()
        return jsonify({"ok": True})

    @app.get("/api/bootstrap")
    def bootstrap() -> Response:
        settings = load_settings()
        return jsonify(
            {
                "name": "Wukong ROM Studio",
                "settings": settings,
                "devices": load_devices(),
                "deviceCatalogPath": str(device_catalog_path()),
                "modVersions": list_mod_versions(),
                "modsByVersion": {
                    version: list_mods(version)
                    for version in list_mod_versions()
                },
                "mods": list_mods(),
                "contentPacks": list_content_packs(),
                "defaultDebloatPaths": default_debloat_paths(),
                "presetDefaultsByVersion": {
                    version: {
                        "lite": preset_default_mods("lite", version),
                        "resume": preset_default_mods("resume", version),
                        "both": preset_default_mods("both", version),
                        "custom": [],
                    }
                    for version in list_mod_versions()
                },
                "presetDefaults": {
                    "lite": preset_default_mods("lite"),
                    "resume": preset_default_mods("resume"),
                    "both": preset_default_mods("both"),
                    "custom": [],
                },
                "jobs": list_jobs(30),
                "artifacts": list_artifacts(100),
                "steps": [
                    {"id": step, "label": label, "required": required}
                    for step, label, required in STEP_DEFINITIONS
                    if step != "patch_vendor_boot"
                ],
                "diagnostics": diagnostics(),
                "stageCache": stage_cache_status(),
            }
        )

    def device_catalog_response(devices: list[dict[str, Any]]) -> Response:
        return jsonify({"devices": devices, "storagePath": str(device_catalog_path())})

    @app.get("/api/devices")
    def devices_list() -> Response:
        try:
            return device_catalog_response(load_devices())
        except StudioError as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/devices")
    def devices_create() -> Response:
        try:
            candidate = normalize_device_catalog([request.get_json(force=True) or {}])[0]
            devices = load_devices()
            if any(
                device["product_name"].casefold() == candidate["product_name"].casefold()
                for device in devices
            ):
                return jsonify({"error": f"Thiết bị {candidate['product_name']} đã tồn tại"}), 409
            devices.append(candidate)
            return device_catalog_response(save_devices(devices)), 201
        except StudioError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.put("/api/devices/<product_name>")
    def devices_update(product_name: str) -> Response:
        try:
            candidate = normalize_device_catalog([request.get_json(force=True) or {}])[0]
            devices = load_devices()
            index = next(
                (
                    position
                    for position, device in enumerate(devices)
                    if device["product_name"].casefold() == product_name.casefold()
                ),
                None,
            )
            if index is None:
                return jsonify({"error": f"Không tìm thấy thiết bị {product_name}"}), 404
            duplicate = next(
                (
                    device
                    for position, device in enumerate(devices)
                    if position != index
                    and device["product_name"].casefold() == candidate["product_name"].casefold()
                ),
                None,
            )
            if duplicate is not None:
                return jsonify({"error": f"Thiết bị {candidate['product_name']} đã tồn tại"}), 409
            devices[index] = candidate
            return device_catalog_response(save_devices(devices))
        except StudioError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/devices/<product_name>")
    def devices_delete(product_name: str) -> Response:
        try:
            devices = load_devices()
            remaining = [
                device
                for device in devices
                if device["product_name"].casefold() != product_name.casefold()
            ]
            if len(remaining) == len(devices):
                return jsonify({"error": f"Không tìm thấy thiết bị {product_name}"}), 404
            return device_catalog_response(save_devices(remaining))
        except StudioError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/fs/authorize-layout-source")
    def fs_authorize_layout_source() -> Response:
        payload = request.get_json(force=True) or {}
        try:
            return jsonify({"path": str(_authorize_layout_source(payload.get("path", "")))})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/layout/analyze")
    def layout_analyze() -> Response:
        payload = request.get_json(force=True) or {}
        source_path = payload.get("sourcePath")
        try:
            if source_path:
                source = Path(str(source_path)).expanduser().resolve()
                if not _path_is_under(source, load_settings()["roots"]):
                    raise ValueError("Layout source is outside configured roots")
                source_path = str(source)
            raw_device = payload.get("device")
            if not isinstance(raw_device, dict):
                product_name = str(payload.get("productName") or "")
                raw_device = find_device(product_name)
                if raw_device is None:
                    raise ValueError(f"Device is not configured: {product_name}")
            return jsonify(analyze_partition_layout(raw_device, source_path))
        except (StudioError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/cache")
    def cache_status() -> Response:
        return jsonify(stage_cache_status())

    @app.post("/api/cache/clear")
    def cache_clear() -> Response:
        active = [
            job
            for job in list_jobs(100)
            if job["status"] in {"queued", "running", "packaging"}
        ]
        if active:
            return jsonify({"error": "Không thể xóa cache khi còn job đang hoạt động"}), 409
        return jsonify(clear_stage_cache())

    @app.get("/api/fs/roots")
    def fs_roots() -> Response:
        return jsonify({"roots": load_settings()["roots"]})

    @app.get("/api/fs/list")
    def fs_list() -> Response:
        try:
            return jsonify(_filesystem_listing(request.args.get("path")))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/fs/authorize-rom")
    def fs_authorize_rom() -> Response:
        payload = request.get_json(force=True) or {}
        try:
            return jsonify({"path": str(_authorize_rom_path(payload.get("romPath", "")))})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/fs/pick-rom")
    def fs_pick_rom() -> Response:
        if SERVER_DESKTOP_MODE:
            return jsonify({"error": "Use the WinUI native picker", "nativePickerRequired": True}), 409
        try:
            path = _pick_rom_file()
            return jsonify({"path": str(path) if path else None})
        except (RuntimeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/fs/pick-rom-folder")
    def fs_pick_rom_folder() -> Response:
        if SERVER_DESKTOP_MODE:
            return jsonify({"error": "Use the WinUI native picker", "nativePickerRequired": True}), 409
        try:
            result = _pick_rom_folder()
            return jsonify(result if result else {"folder": None, "roms": []})
        except (RuntimeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/fs/authorize-rom-folder")
    def fs_authorize_rom_folder() -> Response:
        payload = request.get_json(force=True) or {}
        try:
            return jsonify(_authorize_rom_folder(payload.get("folderPath", "")))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/tools/rom-renamer/preview")
    def rom_renamer_preview() -> Response:
        payload = request.get_json(force=True) or {}
        try:
            rom_path = str(payload.get("romPath") or "").strip()
            folder_path = str(payload.get("folderPath") or "").strip()
            if bool(rom_path) == bool(folder_path):
                raise ValueError("Select exactly one ROM ZIP or one folder")
            if rom_path:
                paths = [_authorize_rom_path(rom_path)]
            else:
                authorized = _authorize_rom_folder(folder_path)
                paths = [Path(path) for path in authorized["roms"]]
            return jsonify(preview_rom_renames(paths))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/tools/rom-renamer/apply")
    def rom_renamer_apply() -> Response:
        payload = request.get_json(force=True) or {}
        entries = payload.get("entries")
        if not isinstance(entries, list) or not entries:
            return jsonify({"error": "ROM rename entries are required"}), 400
        roots = load_settings()["roots"]
        try:
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("Invalid ROM rename entry")
                source = Path(str(entry.get("sourcePath") or "")).expanduser().resolve()
                target = Path(str(entry.get("targetPath") or "")).expanduser().resolve()
                if not _path_is_under(source, roots) or not _path_is_under(target, roots):
                    raise ValueError("ROM rename path is outside configured roots")
                if source.parent != target.parent or target.suffix.casefold() != ".zip":
                    raise ValueError("ROM rename target must be a ZIP in the source folder")
            return jsonify(apply_rom_renames(entries))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except StudioError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.post("/api/roms/inspect")
    def rom_inspect() -> Response:
        payload = request.get_json(force=True) or {}
        path = Path(str(payload.get("romPath", ""))).expanduser().resolve()
        if not _path_is_under(path, load_settings()["roots"]):
            return jsonify({"error": "ROM path is outside configured roots"}), 400
        try:
            spec = BuildSpec.from_dict(payload)
        except StudioError as exc:
            return jsonify({"error": str(exc)}), 400
        requested_steps = plan_steps(spec)
        result = inspect_rom(
            path,
            payload.get("modName"),
            mod_names=spec.selected_mod_names(),
            mod_version=spec.modVersion,
            debloat_paths=spec.debloatPaths,
            required_steps=requested_steps,
        )
        if "notify_telegram" in requested_steps and not _telegram_configured():
            result["errors"].append("Telegram environment variables are not configured")
            result["ok"] = False
        return jsonify(result)

    @app.get("/api/jobs")
    def jobs_list() -> Response:
        return jsonify({"jobs": list_jobs()})

    @app.post("/api/jobs")
    def jobs_create() -> Response:
        payload = request.get_json(force=True) or {}
        specs = payload.get("specs") or [payload]
        jobs = []
        try:
            for spec in specs:
                path = Path(str(spec.get("romPath", ""))).expanduser().resolve()
                if not _path_is_under(path, load_settings()["roots"]):
                    raise ValueError("ROM path is outside configured roots")
                jobs.append(create_job(spec))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        QUEUE_MANAGER.notify()
        return jsonify({"jobs": jobs}), 201

    @app.get("/api/jobs/<job_id>")
    def job_detail(job_id: str) -> Response:
        job = get_job(job_id)
        return jsonify(job) if job else (jsonify({"error": "Job not found"}), 404)

    @app.get("/api/jobs/<job_id>/metrics")
    def job_metrics(job_id: str) -> Response:
        job = get_job(job_id)
        return jsonify(_job_metrics(job)) if job else (jsonify({"error": "Job not found"}), 404)

    @app.get("/api/jobs/<job_id>/diagnostics-bundle")
    def job_diagnostics_bundle(job_id: str) -> Response:
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        filename = sanitize_version_name(job.get("versionName") or job_id, fallback=job_id)
        return Response(
            _diagnostics_bundle(job),
            content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}-diagnostics.zip"'},
        )

    @app.post("/api/jobs/<job_id>/cancel")
    def job_cancel(job_id: str) -> Response:
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        if job["status"] in TERMINAL_STATUSES:
            return jsonify(job)
        update_job(job_id, status="cancelled", finished_at=utc_now(), error="Cancelled by user")
        _publish_telegram_progress(job_id, force=True)
        if job.get("pid"):
            _kill_process_tree(int(job["pid"]))
        _cancel_package_processes(job_id)
        return jsonify(get_job(job_id))

    @app.get("/api/jobs/<job_id>/log")
    def job_log(job_id: str) -> Response:
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        log_path = Path(job["logPath"]).resolve()
        if log_path.parent != JOBS_DIR.resolve():
            return jsonify({"error": "Job log path is invalid"}), 400
        if not log_path.is_file():
            return jsonify({"error": "Job log is not available"}), 404
        filename = sanitize_version_name(job.get("versionName") or job_id, fallback=job_id)
        offset_value = request.args.get("offset")
        if offset_value is not None:
            try:
                offset = int(offset_value)
                limit = max(1, min(int(request.args.get("limit", 131072)), 262144))
            except ValueError:
                return jsonify({"error": "Log offset and limit must be integers"}), 400
            log_size = log_path.stat().st_size
            follow = request.args.get("follow") in {"1", "true", "yes"}
            reset = offset < 0 or offset > log_size
            if follow and not reset and log_size - offset > limit * 4:
                reset = True
            start = _log_tail_offset(log_path, max_bytes=limit) if reset else offset
            with log_path.open("rb") as handle:
                handle.seek(start)
                content = handle.read(limit).decode("utf-8", errors="replace").replace("\r\n", "\n")
                next_offset = handle.tell()
            return Response(
                content,
                content_type="text/plain; charset=utf-8",
                headers={
                    "Cache-Control": "no-store",
                    "X-Log-Next-Offset": str(next_offset),
                    "X-Log-Reset": "1" if reset else "0",
                },
            )
        return Response(
            log_path.read_text(encoding="utf-8", errors="replace"),
            content_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.log"'},
        )

    @app.get("/api/jobs/<job_id>/events")
    def job_events(job_id: str) -> Response:
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        log_path = Path(job["logPath"])

        def stream() -> Iterable[str]:
            offset = _log_tail_offset(log_path) if log_path.is_file() else 0
            last_status = ""
            idle_after_terminal = 0
            while True:
                if log_path.is_file():
                    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(offset)
                        lines: list[str] = []
                        while line := handle.readline():
                            offset = handle.tell()
                            if not line.startswith(EVENT_PREFIX):
                                lines.append(_clean_ui_log_line(line))
                                if len(lines) >= UI_LOG_BATCH_LINES:
                                    yield "event: log\ndata: " + json.dumps({"lines": lines}) + "\n\n"
                                    lines = []
                        if lines:
                            yield "event: log\ndata: " + json.dumps({"lines": lines}) + "\n\n"
                latest = get_job(job_id)
                if latest and latest["status"] != last_status:
                    last_status = latest["status"]
                    yield "event: state\ndata: " + json.dumps(latest) + "\n\n"
                if latest and latest["status"] in TERMINAL_STATUSES:
                    idle_after_terminal += 1
                    if idle_after_terminal >= 3:
                        break
                else:
                    idle_after_terminal = 0
                time.sleep(0.5)

        return Response(
            stream(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/artifacts")
    def artifacts() -> Response:
        return jsonify({"artifacts": list_artifacts()})

    @app.post("/api/artifacts/open")
    def artifacts_open() -> Response:
        payload = request.get_json(force=True) or {}
        path = Path(str(payload.get("path", ""))).resolve()
        if path.parent != ROM_BUILD_DONE.resolve() or not path.is_file():
            return jsonify({"error": "Artifact path is invalid"}), 400
        if os.name == "nt":
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
        return jsonify({"ok": True})

    @app.get("/api/diagnostics")
    def diagnostics_route() -> Response:
        return jsonify(diagnostics())

    @app.get("/api/settings")
    def settings_get() -> Response:
        return jsonify(load_settings())

    @app.post("/api/settings")
    def settings_post() -> Response:
        try:
            return jsonify(save_settings(request.get_json(force=True) or {}))
        except (StudioError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    if start_queue:
        QUEUE_MANAGER.start()
    return app


def _parent_process_alive(parent_pid: int) -> bool:
    if parent_pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(parent_pid, 0)
            return True
        except OSError:
            return False

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(process_query_limited_information, False, parent_pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _watch_parent_process(parent_pid: int, shutdown_callback: Callable[[], None]) -> None:
    while True:
        if not _parent_process_alive(parent_pid):
            shutdown_callback()
            return
        time.sleep(2)


def main() -> int:
    global SERVER_DESKTOP_MODE, SERVER_SHUTDOWN
    parser = argparse.ArgumentParser(description="Wukong ROM Studio local server")
    parser.add_argument("--port", type=int, default=54321)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--desktop-mode", action="store_true")
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    SERVER_DESKTOP_MODE = SERVER_DESKTOP_MODE or args.desktop_mode
    app = create_app(start_queue=True)
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser and not SERVER_DESKTOP_MODE:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Wukong ROM Studio: {url}")
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    SERVER_SHUTDOWN = server.shutdown
    if args.parent_pid:
        threading.Thread(
            target=_watch_parent_process,
            args=(args.parent_pid, server.shutdown),
            name="studio-parent-watch",
            daemon=True,
        ).start()
    try:
        server.serve_forever()
    finally:
        QUEUE_MANAGER.stop()
        SERVER_SHUTDOWN = None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

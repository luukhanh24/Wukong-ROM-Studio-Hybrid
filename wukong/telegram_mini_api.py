from __future__ import annotations

import base64
import copy
import hashlib
import html
import hmac
import json
import os
import queue
import re
import secrets
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

from flask import Flask, Response, jsonify, redirect, request
from werkzeug.serving import BaseWSGIServer, make_server

from .models import BuildRecipe, Identity, JobManifest, JobStatus, RecipeValidationError, SourceSpec
from .orchestrator import HybridOrchestrator, OrchestrationError
from .routing import RunnerUnavailableError
from .runtime import HybridRuntime
from .source_probe import validate_direct_signed_url_ttl
from .telegram import BuildConcurrencyError, BuildQuotaError, TelegramAccessStore

TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
SOURCE_METADATA_KEYS = (
    "provider",
    "filename",
    "resolvedHost",
    "productName",
    "device",
    "version",
    "androidVersion",
    "securityPatch",
    "buildDate",
    "otaType",
    "contentType",
    "lastModified",
    "md5",
    "deepInspected",
    "warning",
)


def _encode_audit_cursor(event: Mapping[str, object]) -> str:
    payload = json.dumps(
        [str(event.get("createdAt") or ""), str(event.get("eventId") or "")],
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_audit_cursor(value: str) -> tuple[str, str] | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        padding = "=" * (-len(normalized) % 4)
        decoded = json.loads(
            base64.urlsafe_b64decode(normalized + padding).decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Audit cursor is invalid") from exc
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not all(isinstance(item, str) and item for item in decoded)
    ):
        raise ValueError("Audit cursor is invalid")
    return decoded[0], decoded[1]
RELEASE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ACTIONS_CALLBACK_MAX_AGE_SECONDS = 5 * 60
TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS = 60 * 60
TELEGRAM_PAIRING_MAX_AGE_SECONDS = 5 * 60
TELEGRAM_SOURCE_DRAFT_MAX_AGE_SECONDS = 24 * 60 * 60
ARTIFACT_DOWNLOAD_TICKET_SECONDS = 5 * 60
MOD_RELEASE_VERSION_RE = re.compile(r"^[^/\\\x00-\x1f]{1,64}$")


class TelegramInitDataError(PermissionError):
    pass


class TelegramMiniAppSessionStore:
    """Short-lived bridge for Telegram clients that omit Mini App initData."""

    def __init__(
        self,
        *,
        pairing_max_age_seconds: int = TELEGRAM_PAIRING_MAX_AGE_SECONDS,
        draft_max_age_seconds: int = TELEGRAM_SOURCE_DRAFT_MAX_AGE_SECONDS,
    ) -> None:
        self.pairing_max_age_seconds = max(60, min(int(pairing_max_age_seconds), 15 * 60))
        self.draft_max_age_seconds = max(60, min(int(draft_max_age_seconds), 7 * 24 * 60 * 60))
        self._pairs: dict[str, dict[str, object]] = {}
        self._drafts: dict[str, tuple[int, str]] = {}
        self._lock = threading.RLock()

    def _cleanup(self, now: int) -> None:
        self._pairs = {
            pair_id: record
            for pair_id, record in self._pairs.items()
            if int(record.get("expiresAt") or 0) >= now
        }
        self._drafts = {
            user_id: draft
            for user_id, draft in self._drafts.items()
            if draft[0] + self.draft_max_age_seconds >= now
        }

    def begin(self, bot_username: str, *, now: int | None = None) -> dict[str, object]:
        username = str(bot_username or "").strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
            raise ValueError("Telegram bot username is not configured")
        current = int(time.time()) if now is None else int(now)
        pair_id = secrets.token_urlsafe(12).rstrip("=")
        pair_secret = secrets.token_urlsafe(24).rstrip("=")
        expires_at = current + self.pairing_max_age_seconds
        with self._lock:
            self._cleanup(current)
            self._pairs[pair_id] = {
                "secretHash": hashlib.sha256(pair_secret.encode("ascii")).digest(),
                "createdAt": current,
                "expiresAt": expires_at,
                "userId": None,
            }
            if len(self._pairs) > 512:
                oldest = min(self._pairs, key=lambda key: int(self._pairs[key].get("createdAt") or 0))
                self._pairs.pop(oldest, None)
        return {
            "pairId": pair_id,
            "pairSecret": pair_secret,
            "botLink": f"https://t.me/{username}?start=pair_{pair_id}",
            "expiresIn": self.pairing_max_age_seconds,
        }

    def confirm(self, pair_id: str, user_id: int | str, *, now: int | None = None) -> bool:
        current = int(time.time()) if now is None else int(now)
        try:
            subject = int(user_id)
        except (TypeError, ValueError):
            return False
        if subject <= 0:
            return False
        with self._lock:
            self._cleanup(current)
            record = self._pairs.get(str(pair_id or ""))
            if not record:
                return False
            confirmed_user = record.get("userId")
            if confirmed_user is not None and int(confirmed_user) != subject:
                return False
            record["userId"] = subject
            return True

    def launch_token(
        self,
        pair_id: str,
        pair_secret: str,
        bot_token: str,
        *,
        now: int | None = None,
    ) -> str | None:
        current = int(time.time()) if now is None else int(now)
        supplied_hash = hashlib.sha256(str(pair_secret or "").encode("utf-8")).digest()
        with self._lock:
            self._cleanup(current)
            record = self._pairs.get(str(pair_id or ""))
            if not record or not hmac.compare_digest(supplied_hash, record["secretHash"]):
                raise TelegramInitDataError("Telegram pairing request is invalid or expired")
            user_id = record.get("userId")
        if user_id is None:
            return None
        return issue_telegram_launch_token(int(user_id), bot_token, now=current)

    def remember_source(self, user_id: int | str, uri: str, *, now: int | None = None) -> bool:
        value = str(uri or "").strip()
        try:
            subject = str(int(user_id))
            parsed = urlsplit(value)
        except (TypeError, ValueError):
            return False
        if (
            len(value) > 8192
            or parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            return False
        current = int(time.time()) if now is None else int(now)
        with self._lock:
            self._cleanup(current)
            self._drafts[subject] = (current, value)
        return True

    def source_draft(self, user_id: int | str, *, now: int | None = None) -> str:
        current = int(time.time()) if now is None else int(now)
        try:
            subject = str(int(user_id))
        except (TypeError, ValueError):
            return ""
        with self._lock:
            self._cleanup(current)
            draft = self._drafts.get(subject)
            return draft[1] if draft else ""


def _telegram_launch_key(bot_token: str) -> bytes:
    return hmac.new(
        b"WukongMiniAppLaunch\0",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def issue_telegram_launch_token(
    user_id: int | str,
    bot_token: str,
    *,
    now: int | None = None,
    lifetime_seconds: int = TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS,
) -> str:
    try:
        subject = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Telegram launch user is invalid") from exc
    if subject <= 0 or not bot_token:
        raise ValueError("Telegram launch user is invalid")
    issued_at = int(time.time()) if now is None else int(now)
    lifetime = max(60, min(int(lifetime_seconds), TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS))
    payload = f"v1.{subject}.{issued_at}.{issued_at + lifetime}"
    signature = hmac.new(
        _telegram_launch_key(bot_token),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_telegram_launch_token(
    token: str,
    bot_token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS,
) -> int:
    parts = token.split(".") if isinstance(token, str) else []
    if (
        len(parts) != 5
        or parts[0] != "v1"
        or any(not re.fullmatch(r"[0-9]+", value) for value in parts[1:4])
        or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[4])
    ):
        raise TelegramInitDataError("Telegram launch signature is invalid")
    payload = ".".join(parts[:4])
    expected = hmac.new(
        _telegram_launch_key(bot_token),
        payload.encode("ascii", errors="strict"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(parts[4].casefold(), expected):
        raise TelegramInitDataError("Telegram launch signature is invalid")
    try:
        subject = int(parts[1])
        issued_at = int(parts[2])
        expires_at = int(parts[3])
    except ValueError as exc:
        raise TelegramInitDataError("Telegram launch signature is invalid") from exc
    current = int(time.time()) if now is None else int(now)
    maximum_age = max(60, min(int(max_age_seconds), TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS))
    if subject <= 0 or issued_at > current + 60 or expires_at <= issued_at:
        raise TelegramInitDataError("Telegram launch signature is invalid")
    if expires_at - issued_at > maximum_age or current > expires_at:
        raise TelegramInitDataError("Telegram launch authentication has expired")
    return subject


def issue_artifact_download_ticket(
    job_id: str,
    subject: int | str,
    bot_token: str,
    *,
    now: int | None = None,
) -> str:
    expires_at = (int(time.time()) if now is None else int(now)) + ARTIFACT_DOWNLOAD_TICKET_SECONDS
    payload = f"v1.{subject}.{expires_at}"
    signature = hmac.new(
        _telegram_launch_key(bot_token),
        f"download\0{job_id}\0{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = 3600,
) -> dict[str, object]:
    if not init_data or len(init_data.encode("utf-8")) > 16384:
        raise TelegramInitDataError("Telegram Mini App authentication is missing")
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    values: dict[str, str] = {}
    for key, value in pairs:
        if key in values:
            raise TelegramInitDataError("Telegram Mini App authentication contains duplicate fields")
        values[key] = value
    supplied_hash = values.pop("hash", "").casefold()
    if len(supplied_hash) != 64:
        raise TelegramInitDataError("Telegram Mini App signature is invalid")
    data_check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_hash, expected_hash):
        raise TelegramInitDataError("Telegram Mini App signature is invalid")
    try:
        auth_date = int(values["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramInitDataError("Telegram Mini App auth_date is invalid") from exc
    current = int(time.time()) if now is None else int(now)
    if auth_date > current + 60 or current - auth_date > max(60, max_age_seconds):
        raise TelegramInitDataError("Telegram Mini App authentication has expired")
    try:
        user = json.loads(values["user"])
        user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramInitDataError("Telegram Mini App user is invalid") from exc
    if not isinstance(user, dict) or user_id <= 0:
        raise TelegramInitDataError("Telegram Mini App user is invalid")
    return {**values, "user": user}


def _origin_from_web_app_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        raise ValueError("Telegram Mini App URL must be public HTTPS")
    return f"https://{parsed.netloc.casefold()}"


def public_artifact_url(value: object) -> str:
    candidate = str(value or "").strip()
    if (
        not candidate
        or "\\" in candidate
        or any(character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in candidate)
        or re.search(r"%(?![0-9A-Fa-f]{2})", candidate)
    ):
        return ""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    hostname = (parsed.hostname or "").casefold()
    blocked_hosts = {"wukong-mini-api.onrender.com"}
    try:
        configured_host = (
            urlsplit(os.environ.get("WUKONG_TELEGRAM_MINI_APP_API_URL", "")).hostname
            or ""
        ).casefold()
    except ValueError:
        configured_host = ""
    if configured_host:
        blocked_hosts.add(configured_host)
    if (
        parsed.scheme.casefold() != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or hostname in blocked_hosts
    ):
        return ""
    return candidate


def public_job_payload(
    manifest: JobManifest,
    recipe: BuildRecipe | None = None,
) -> dict[str, object]:
    payload = manifest.to_dict()
    payload.pop("owner", None)
    payload.pop("external_run_id", None)
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                cloud_url = public_artifact_url(
                    artifact.get("public_url") or artifact.get("publicUrl")
                )
                artifact.pop("uri", None)
                artifact.pop("public_url", None)
                artifact.pop("publicUrl", None)
                artifact["downloadAvailable"] = bool(cloud_url)
                if cloud_url:
                    artifact["publicUrl"] = cloud_url
    if recipe:
        payload["recipe"] = {
            "task": recipe.task,
            "device": recipe.device,
            "source": {
                "kind": recipe.source.kind,
                "sizeBytes": recipe.source.size_bytes,
                "metadata": dict(recipe.source.metadata),
            },
            "build": recipe.build.to_dict(),
            "execution": recipe.execution.to_dict(),
            "storage": {"publishArtifact": recipe.storage.publish_artifact},
        }
    sanitized = sanitize_public_value(payload)
    result = dict(sanitized) if isinstance(sanitized, Mapping) else {}
    sanitized_artifacts = result.get("artifacts")
    if isinstance(artifacts, list) and isinstance(sanitized_artifacts, list):
        for original, public in zip(artifacts, sanitized_artifacts, strict=False):
            if not isinstance(original, dict) or not isinstance(public, dict):
                continue
            cloud_url = public_artifact_url(
                original.get("publicUrl") or original.get("public_url")
            )
            public["downloadAvailable"] = bool(cloud_url)
            if cloud_url:
                public["publicUrl"] = cloud_url
            else:
                public.pop("publicUrl", None)
    return result


_PRIVATE_EVENT_KEYS = {
    "actionsurl",
    "externalrunid",
    "githuburl",
    "githubrepository",
    "htmlurl",
    "repository",
    "repositoryurl",
    "repo",
    "runid",
    "url",
    "workflowurl",
}

_PRIVATE_VALUE_KEYS = {
    "accesstoken",
    "authorization",
    "bottoken",
    "clientsecret",
    "connectionstring",
    "credential",
    "credentials",
    "databaseuri",
    "databaseurl",
    "githubtoken",
    "initdata",
    "password",
    "rcloneconfig",
    "refreshtoken",
    "secret",
    "token",
}


def _private_value_key(key: object) -> bool:
    normalized = str(key).replace("_", "").replace("-", "").casefold()
    return (
        normalized in _PRIVATE_VALUE_KEYS
        or normalized.startswith(("authorization", "rcloneconfig"))
        or normalized.endswith(
            (
                "apikey",
                "credential",
                "credentials",
                "initdata",
                "password",
                "privatekey",
                "secret",
                "token",
            )
        )
    )


def _redact_public_url_queries(match: re.Match[str]) -> str:
    url = match.group(0)
    redact_all = (
        any(
            marker in url.casefold()
            for marker in ("/downloadcheck?", "allawnfs.com/", "allawntech.com/")
        )
        or re.search(
            r"[?&](?:(?:x-amz|x-goog)-)?signature=",
            url,
            flags=re.IGNORECASE,
        )
        is not None
    )
    key_pattern = (
        r"[A-Za-z0-9_.~-]+"
        if redact_all
        else r"(?:(?:[A-Za-z0-9_.~-]+[_-])?(?:access[_-]?key|access[_-]?token|api[_-]?key|client[_-]?secret|credential|password|passwd|private[_-]?key|refresh[_-]?token|secret)|awsaccesskeyid|auth|expires|key|s|sign|signature|token|x-amz-[a-z-]+|x-goog-[a-z-]+)"
    )
    return re.sub(
        rf"([?&]{key_pattern})=[^&\s'\",;)\]]+",
        r"\1=[redacted]",
        url,
        flags=re.IGNORECASE,
    )


def sanitize_public_value(value: object) -> object:
    """Remove infrastructure identities, paths and credentials from public data."""

    if isinstance(value, str):
        sanitized = re.sub(
            r"https?://(?:api\.)?github\.com/\S+",
            "[internal build reference]",
            value,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\bAuthorization\s*:\s*(?:Basic|Bearer|TMA|WLA)\s+[A-Za-z0-9._~+/=%&-]+",
            "[redacted authorization]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?<![?&])\b(?:ACCESS_KEY|API_KEY|DATABASE_URL|PASSWORD|PRIVATE_KEY|RCLONE_CONFIG(?:_CONTENT)?_B64|RCLONE_CONFIG_PASS|TELEGRAM_INIT_DATA|WUKONG_GITHUB_REPOSITORY|[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|CREDENTIALS?|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)\b\s*(?:=|:)\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;)\]]+)",
            "[private setting]=[redacted]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\bpostgres(?:ql)?://[^\s'\",;)\]]+",
            "[private database reference]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|\d{6,12}:[A-Za-z0-9_-]{20,})\b",
            "[redacted credential]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?P<quote>['\"])/(?:home/runner/work|(?:[^/'\"]+/)*_work|__w|github/workspace|var/lib/wukong|tmp/wukong-[^/'\"]+)(?:/[^'\"]*)?(?P=quote)",
            "[internal path]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?<![A-Za-z0-9])/(?:home/runner/work|(?:[^/\s,;:)\]\r\n]+/)*_work|__w|github/workspace|var/lib/wukong|tmp/wukong-[^/\s,;:)\]\r\n]+)(?:/[^\s,;:)\]\r\n]+)*",
            "[internal path]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?P<quote>['\"])[A-Za-z]:\\(?:Users\\[^\\'\"]+\\AppData\\Local\\Temp|Android\\Auto_Build_WK|WukongROMStudio|a|(?:[^\\'\"]+\\)*_work)(?:\\[^'\"]*)?(?P=quote)",
            "[internal path]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b[A-Za-z]:\\(?:Users\\[^,;:)\]\r\n]+?\\AppData\\Local\\Temp|Android\\Auto_Build_WK|WukongROMStudio|a|(?:[^\\,;:)\]\r\n]+\\)*_work)(?:\\[^,;:)\]\r\n]+)*",
            "[internal path]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b(rclone\s+(?:cat|check|copy|copyto|delete|ls|lsd|lsl|md5sum|mkdir|move|moveto|purge|sha1sum|size|sync)(?:\s+[^\s'\",;)]+){0,3}\s+)[A-Za-z][A-Za-z0-9_.-]*:(?!//)[A-Za-z0-9_.@%+=,/-]+",
            r"\1[private storage]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b((?:remote|storage)\s+)[A-Za-z][A-Za-z0-9_.-]*:(?!//)[A-Za-z0-9_.@%+=,/-]+",
            r"\1[private storage]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?<![A-Za-z0-9_.-])[A-Za-z][A-Za-z0-9_.-]+:(?!//)(?=[^\s'\",;)\]]*/)[^\s'\",;)\]]+",
            "[private storage]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b((?:(?:github|repository|repo)(?:\s+|[:=]\s*)|(?:dispatch|workflow|build)\s+failed\s+for\s+|failed\s+checkout\s+of\s+|(?:cannot|could\s+not)\s+access\s+|repository\s+lookup\s+|(?:checkout|clone|fetch|pull|push)\s+))[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b",
            r"\1[internal repository]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?<![\w.-])(?:[A-Za-z0-9_.-]+/)?Wukong-ROM-Studio-Hybrid(?![\w.-])",
            "[internal repository]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b(?:rclone(?:\.runtime)?\.conf|(?:service[-_])?account(?:[-_]key)?\.json)\b",
            "[private configuration]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b(?:DATABASE_URL|GITHUB_TOKEN|WUKONG_GITHUB_REPOSITORY|WUKONG_TELEGRAM_BOT_TOKEN)\b",
            "[private setting]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?<![A-Za-z0-9_.-])[A-Za-z][A-Za-z0-9_.-]+:(?!//)[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,16}\b",
            "[private storage]",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"https?://[^\s'\",;)\]]+",
            _redact_public_url_queries,
            sanitized,
            flags=re.IGNORECASE,
        )
        return re.sub(
            r"\b(?:authorization:\s*)?(?:bearer|tma|wla)\s+[A-Za-z0-9._~+/=%&-]+",
            "[redacted authorization]",
            sanitized,
            flags=re.IGNORECASE,
        )
    if isinstance(value, Mapping):
        return {
            key: "[redacted]" if _private_value_key(key) else sanitize_public_value(item)
            for key, item in value.items()
            if str(key).replace("_", "").casefold() not in _PRIVATE_EVENT_KEYS
        }
    if isinstance(value, list):
        return [sanitize_public_value(item) for item in value]
    return value


def public_event_payload(event: object) -> dict[str, object]:
    payload = event.to_dict() if hasattr(event, "to_dict") else {}
    sanitized = sanitize_public_value(payload)
    return dict(sanitized) if isinstance(sanitized, Mapping) else {}


class TelegramMiniAppAPI:
    def __init__(
        self,
        *,
        bot_token: str,
        allowed_origin: str,
        access: TelegramAccessStore,
        orchestrator: HybridOrchestrator,
        runtime: HybridRuntime,
        catalog_provider: Callable[[], dict[str, object]],
        release_versions_provider: Callable[[], Mapping[str, str]] | None = None,
        release_versions_saver: Callable[[Mapping[str, str]], Mapping[str, str]] | None = None,
        diagnostics_provider: Callable[[], dict[str, object]],
        source_probe_provider: Callable[[str], dict[str, object]],
        cloud_provider: Callable[[str], dict[str, object]] | None = None,
        cache_provider: Callable[[], dict[str, object]] | None = None,
        cache_clearer: Callable[[], dict[str, object]] | None = None,
        telegram_update_handler: Callable[[dict[str, object]], None] | None = None,
        telegram_webhook_secret: str | None = None,
        actions_callback_secret: str | None = None,
        readiness_provider: Callable[[], bool] | None = None,
        max_init_data_age_seconds: int = 3600,
        probe_cache_seconds: int = 15 * 60,
        session_store: TelegramMiniAppSessionStore | None = None,
        bot_username: str | None = None,
        state_backend: str = "file",
    ) -> None:
        self.bot_token = bot_token
        self.allowed_origin = _origin_from_web_app_url(allowed_origin)
        configured_origins = {
            _origin_from_web_app_url(value)
            for value in os.environ.get("WUKONG_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        }
        self.allowed_origins = {self.allowed_origin, *configured_origins}
        self.access = access
        self.orchestrator = orchestrator
        self.runtime = runtime
        self.catalog_provider = catalog_provider
        self.release_versions_provider = release_versions_provider or (lambda: {})
        self.release_versions_saver = release_versions_saver
        self.diagnostics_provider = diagnostics_provider
        self.source_probe_provider = source_probe_provider
        self.cloud_provider = cloud_provider
        self.cache_provider = cache_provider
        self.cache_clearer = cache_clearer
        self.telegram_update_handler = telegram_update_handler
        self.telegram_webhook_secret = (telegram_webhook_secret or "").strip()
        self.actions_callback_secret = (actions_callback_secret or "").strip()
        if bool(self.telegram_update_handler) != bool(self.telegram_webhook_secret):
            raise ValueError("Telegram webhook handler and secret must be configured together")
        self._telegram_update_queue: queue.Queue[dict[str, object]] | None = None
        if self.telegram_update_handler:
            self._telegram_update_queue = queue.Queue(maxsize=128)
            threading.Thread(
                target=self._run_telegram_update_worker,
                name="wukong-telegram-webhook-worker",
                daemon=True,
            ).start()
        self.readiness_provider = readiness_provider or (lambda: True)
        self.max_init_data_age_seconds = max(60, max_init_data_age_seconds)
        self.probe_cache_seconds = max(60, probe_cache_seconds)
        self.session_store = session_store or TelegramMiniAppSessionStore()
        self.bot_username = (
            bot_username or os.environ.get("WUKONG_TELEGRAM_BOT_USERNAME", "WK_build_bot")
        ).strip().lstrip("@")
        self.state_backend = state_backend.strip().casefold() or "unknown"
        self._probe_cache: dict[tuple[str, str], tuple[float, dict[str, object]]] = {}
        self._probe_lock = threading.RLock()
        self._probe_slots = threading.BoundedSemaphore(2)
        self._profile_touch: dict[str, float] = {}
        self._profile_touch_lock = threading.RLock()
        self.app = self._create_app()

    def _run_telegram_update_worker(self) -> None:
        update_queue = self._telegram_update_queue
        handler = self.telegram_update_handler
        if update_queue is None or handler is None:
            return
        while True:
            payload = update_queue.get()
            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001 - keep the webhook worker alive
                print(f"Telegram webhook processing failed: {type(exc).__name__}", flush=True)
            finally:
                update_queue.task_done()

    def _create_app(self) -> Flask:
        app = Flask("wukong-telegram-mini-api", static_folder=None)
        app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

        @app.errorhandler(TelegramInitDataError)
        def telegram_permission_error(exc: TelegramInitDataError) -> tuple[Response, int]:
            return jsonify({"error": str(exc), "code": "admin_required"}), 403

        @app.before_request
        def authenticate() -> Response | None:
            if request.path in {"/healthz", "/readyz"}:
                return None
            if request.path == "/internal/actions/callback":
                authorization = request.headers.get("Authorization", "")
                scheme, separator, credential = authorization.partition(" ")
                if separator == " " and scheme.casefold() == "bearer":
                    # The Actions runner presents its own repository token.
                    # Trust is deferred to the handler, which verifies the
                    # run directly against GitHub so a rotated token can
                    # never desynchronize callback authentication again.
                    credential = credential.strip()
                    if len(credential) < 20:
                        return jsonify({"error": "Actions callback authentication failed"}), 403
                    request.environ["wukong.actions_bearer"] = credential
                    return None
                if len(self.actions_callback_secret) < 20:
                    return jsonify({"error": "Actions callback is not configured"}), 503
                timestamp = request.headers.get("X-Wukong-Timestamp", "")
                signature = request.headers.get("X-Wukong-Signature", "").casefold()
                try:
                    issued_at = int(timestamp)
                except ValueError:
                    return jsonify({"error": "Actions callback authentication failed"}), 403
                if abs(int(time.time()) - issued_at) > ACTIONS_CALLBACK_MAX_AGE_SECONDS:
                    return jsonify({"error": "Actions callback authentication failed"}), 403
                body = request.get_data(cache=True)
                key = hmac.new(
                    b"WukongActionsCallback\0",
                    self.actions_callback_secret.encode("utf-8"),
                    hashlib.sha256,
                ).digest()
                expected = hmac.new(
                    key,
                    timestamp.encode("ascii") + b"." + body,
                    hashlib.sha256,
                ).hexdigest()
                if len(signature) != 64 or not hmac.compare_digest(signature, expected):
                    return jsonify({"error": "Actions callback authentication failed"}), 403
                return None
            if request.path == "/telegram/webhook":
                supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if not self.telegram_webhook_secret or not hmac.compare_digest(
                    supplied,
                    self.telegram_webhook_secret,
                ):
                    return jsonify({"error": "Telegram webhook authentication failed"}), 403
                return None
            if re.fullmatch(r"/v1/jobs/[A-Za-z0-9-]{1,64}/download", request.path) and request.args.get("ticket"):
                return None
            origin = (request.headers.get("Origin") or "").rstrip("/").casefold()
            if origin not in {value.casefold() for value in self.allowed_origins}:
                return jsonify({"error": "This Mini App origin is not allowed"}), 403
            if request.method == "OPTIONS":
                return Response(status=204)
            if request.path in {"/v1/session/pair", "/v1/session/pair/status"}:
                return None
            # Source inspection is a read-only preview. It remains available
            # when Telegram omits initData, while jobs and private routes
            # below still require a validated Telegram identity.
            if (
                request.path == "/v1/sources/probe"
                and request.method == "POST"
                and not request.headers.get("Authorization")
            ):
                return None
            authorization = request.headers.get("Authorization", "")
            scheme, separator, credential = authorization.partition(" ")
            if separator != " " or scheme.casefold() not in {"tma", "wla"}:
                return jsonify({"error": "Telegram Mini App authentication is required"}), 401
            try:
                user: Mapping[str, object] = {}
                profile: Mapping[str, object] = {}
                if scheme.casefold() == "tma":
                    telegram = validate_telegram_init_data(
                        credential,
                        self.bot_token,
                        max_age_seconds=self.max_init_data_age_seconds,
                    )
                    user = telegram["user"] if isinstance(telegram["user"], Mapping) else {}
                    user_id = str(user["id"]) if isinstance(user, Mapping) else ""
                else:
                    user_id = str(validate_telegram_launch_token(credential, self.bot_token))
                if user_id:
                    display_name = " ".join(
                        value
                        for value in (
                            str(user.get("first_name") or "").strip(),
                            str(user.get("last_name") or "").strip(),
                        )
                        if value
                    )
                    with self._profile_touch_lock:
                        last_touch = self._profile_touch.get(user_id, 0.0)
                        should_touch = time.monotonic() - last_touch >= 60.0
                    profile = self.access.profile(user_id)
                    if profile is None or should_touch:
                        profile = self.access.observe_user(
                            user_id,
                            username=str(user.get("username") or ""),
                            display_name=display_name,
                            language=str(user.get("language_code") or ""),
                            platform=request.headers.get("X-Telegram-Platform", ""),
                            app_version=request.headers.get("X-Wukong-Client-Version", ""),
                            photo_url=str(user.get("photo_url") or ""),
                        )
                        with self._profile_touch_lock:
                            self._profile_touch[user_id] = time.monotonic()
                    request.environ["wukong.telegram_subject"] = user_id
                    request.environ["wukong.telegram_profile"] = profile
                identity = self.access.identity(user_id) if user_id else None
                if not identity:
                    if request.path in {"/v1/session/open", "/v1/me"}:
                        return None
                    status = str(profile.get("accessStatus") or "pending") if user_id else "pending"
                    return jsonify(
                        {
                            "error": "Telegram account is revoked" if status == "revoked" else "Telegram account is awaiting approval",
                            "code": "access_revoked" if status == "revoked" else "access_pending",
                        }
                    ), 403
                request.environ["wukong.identity"] = identity
            except (TelegramInitDataError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 401
            return None

        @app.after_request
        def add_cors_headers(response: Response) -> Response:
            origin = (request.headers.get("Origin") or "").rstrip("/").casefold()
            allowed = {value.casefold(): value for value in self.allowed_origins}
            if origin in allowed:
                response.headers["Access-Control-Allow-Origin"] = allowed[origin]
                response.headers["Access-Control-Allow-Headers"] = (
                    "Authorization, Content-Type, Idempotency-Key, X-Wukong-Session-Id, "
                    "X-Wukong-Client-Version, X-Telegram-Platform"
                )
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
                response.headers["Access-Control-Max-Age"] = "600"
                response.headers["Vary"] = "Origin"
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.get("/v1/catalog")
        def catalog() -> Response:
            return jsonify(self.catalog_provider())

        @app.get("/v1/mod-release-versions")
        def mod_release_versions() -> Response:
            return jsonify(
                {
                    "modReleaseVersions": dict(self.release_versions_provider()),
                    "editable": self._identity().role == "admin",
                }
            )

        @app.put("/v1/mod-release-versions")
        def save_mod_release_versions() -> Response:
            if self._identity().role != "admin":
                return jsonify({"error": "Admin access is required to edit MOD release versions"}), 403
            if self.release_versions_saver is None:
                return jsonify({"error": "MOD release version editing is not configured"}), 503
            payload = request.get_json(force=True) or {}
            values = payload.get("modReleaseVersions") if isinstance(payload, Mapping) else None
            if not isinstance(values, Mapping):
                return jsonify({"error": "modReleaseVersions must be an object"}), 400
            catalog = self.catalog_provider()
            known = {str(value) for value in catalog.get("modVersions", [])}
            if set(values) - known:
                return jsonify({"error": "Unknown MOD pack in release versions"}), 400
            normalized: dict[str, str] = {}
            for pack, label in values.items():
                value = str(label).strip()
                if not MOD_RELEASE_VERSION_RE.fullmatch(value):
                    return jsonify({"error": "Release version must be 1–64 printable characters without / or \\"}), 400
                normalized[str(pack)] = value
            try:
                saved = self.release_versions_saver(normalized)
                return jsonify({"modReleaseVersions": dict(saved)})
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 409

        @app.get("/healthz")
        def health() -> Response:
            release = os.environ.get("WUKONG_RELEASE_SHA", "").strip().casefold()
            ready = bool(self.readiness_provider())
            return jsonify(
                {
                    "status": "ready" if ready else "starting",
                    "service": "wukong-control-plane",
                    "stateBackend": self.state_backend,
                    "release": release if RELEASE_SHA_RE.fullmatch(release) else "development",
                }
            ), 200 if ready else 503

        @app.get("/readyz")
        def readiness() -> Response:
            ready = bool(self.readiness_provider())
            return jsonify({"status": "ready" if ready else "starting"}), 200 if ready else 503

        @app.post("/v1/session/open")
        def session_open() -> Response:
            subject = self._telegram_subject()
            session_id = request.headers.get("X-Wukong-Session-Id", "").strip()
            try:
                profile = self.access.open_session(subject, session_id)
                return jsonify({"user": profile})
            except ValueError as exc:
                return jsonify({"error": str(exc), "code": "invalid_session"}), 400

        @app.get("/v1/me")
        def me() -> Response:
            profile = self.access.profile(self._telegram_subject())
            if not profile:
                return jsonify({"error": "Telegram profile is unavailable"}), 404
            return jsonify({"user": profile})

        @app.post("/v1/session/pair")
        def begin_session_pairing() -> Response:
            try:
                return jsonify(self.session_store.begin(self.bot_username)), 201
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 503

        @app.post("/v1/session/pair/status")
        def session_pairing_status() -> Response:
            payload = request.get_json(silent=True) or {}
            try:
                launch_token = self.session_store.launch_token(
                    str(payload.get("pairId") or ""),
                    str(payload.get("pairSecret") or ""),
                    self.bot_token,
                )
            except TelegramInitDataError as exc:
                return jsonify({"error": str(exc)}), 404
            if not launch_token:
                return jsonify({"status": "pending"}), 202
            return jsonify({"status": "confirmed", "launchToken": launch_token})

        @app.post("/telegram/webhook")
        def telegram_webhook() -> Response:
            if self.telegram_update_handler is None:
                return jsonify({"error": "Telegram webhook is not configured"}), 503
            payload = request.get_json(force=True)
            if not isinstance(payload, dict):
                return jsonify({"error": "Telegram update must be an object"}), 400
            update_kind = "callback" if payload.get("callback_query") else "message" if payload.get("message") else "other"
            print(f"Telegram webhook update queued: {update_kind}", flush=True)
            if self._telegram_update_queue is None:
                return jsonify({"error": "Telegram webhook is not configured"}), 503
            try:
                self._telegram_update_queue.put_nowait(payload)
            except queue.Full:
                return jsonify({"error": "Telegram webhook queue is full"}), 503
            return Response(status=204)

        @app.post("/internal/actions/callback")
        def actions_callback() -> Response:
            payload = request.get_json(force=True)
            job_id = str(payload.get("jobId") or "") if isinstance(payload, dict) else ""
            if not job_id.isascii() or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}", job_id):
                return jsonify({"error": "Actions callback job is invalid"}), 400
            manifest = self.orchestrator.store.get(job_id)
            if manifest is None:
                return jsonify({"error": "Job not found"}), 404
            run_id: int | None = None
            conclusion = ""
            if isinstance(payload, dict) and payload.get("runId") is not None:
                try:
                    run_id = int(payload["runId"])
                except (TypeError, ValueError):
                    return jsonify({"error": "Actions callback run is invalid"}), 400
                conclusion = str(payload.get("workflowResult") or "").strip().casefold()
                if run_id <= 0 or conclusion not in {"success", "failure", "cancelled"}:
                    return jsonify({"error": "Actions callback result is invalid"}), 400
            bearer = request.environ.get("wukong.actions_bearer")
            if isinstance(bearer, str) and bearer:
                # Runner-authenticated callback: GitHub is the trust anchor.
                if run_id is None:
                    return jsonify({"error": "Actions callback authentication failed"}), 403
                try:
                    conclusion = self.runtime.verify_actions_bearer(
                        bearer,
                        run_id,
                        conclusion,
                    )
                except PermissionError as exc:
                    return jsonify({"error": str(exc)}), 403
            # A pre-executor failure has no newer Drive manifest to fetch.
            # Reconcile it immediately so the callback can wake a cold free
            # instance well within the workflow's request timeout.
            pre_executor_failure = bool(
                isinstance(payload, dict) and payload.get("preExecutorFailure") is True
            )
            if run_id is not None and pre_executor_failure and conclusion in {"failure", "cancelled"}:
                refreshed = self.runtime.reconcile_actions_callback(
                    manifest,
                    run_id=run_id,
                    conclusion=conclusion,
                )
            else:
                refreshed = self.runtime.refresh(manifest, force_cloud=True)
                if run_id is not None:
                    refreshed = self.runtime.reconcile_actions_callback(
                        refreshed,
                        run_id=run_id,
                        conclusion=conclusion,
                    )
            self.runtime.notify_terminal(refreshed)
            if refreshed.owner.channel == "telegram":
                self.access.update_job_status(
                    refreshed.owner.subject,
                    refreshed.job_id,
                    refreshed.status.value,
                )
            return jsonify(
                {
                    "jobId": refreshed.job_id,
                    "status": refreshed.status.value,
                    "terminal": refreshed.status in TERMINAL_STATUSES,
                }
            )

        @app.post("/v1/sources/probe")
        def probe_source() -> Response:
            try:
                payload = request.get_json(force=True) or {}
                uri = str(payload.get("uri") or "").strip()
                if not uri or len(uri) > 8192:
                    raise ValueError("A valid ROM source URL is required")
                if not self._probe_slots.acquire(blocking=False):
                    return jsonify({"error": "Two ROM probes are already running; try again shortly"}), 429
                try:
                    result = self.source_probe_provider(uri)
                finally:
                    self._probe_slots.release()
                identity = request.environ.get("wukong.identity")
                if isinstance(identity, Identity):
                    self._remember_probe(identity, uri, result)
                return jsonify({key: value for key, value in result.items() if key != "metadata"})
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                message = str(exc)
                error_code = (
                    "source_signed_url_expired"
                    if "signed ROM download URL" in message
                    else "source_unreachable"
                )
                return jsonify({"error": message, "code": error_code}), 400

        @app.post("/v1/jobs")
        def create_job() -> Response:
            identity = self._identity()
            reservation: Mapping[str, object] | None = None
            job_created = False
            try:
                payload = request.get_json(force=True) or {}
                if not isinstance(payload, Mapping):
                    raise RecipeValidationError("Build recipe must be an object")
                recipe = self._verified_recipe(payload, identity)
                idempotency_key = request.headers.get("Idempotency-Key", "").strip()
                if not idempotency_key:
                    idempotency_key = uuid.uuid4().hex
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", idempotency_key):
                    raise ValueError("Build idempotency key is invalid")
                requested_job_id = uuid.uuid4().hex
                atomic_creator = getattr(self.access, "reserve_and_create_job", None)
                if callable(atomic_creator):
                    prepared = self.orchestrator.prepare_submission(
                        recipe,
                        identity,
                        job_id=requested_job_id,
                    )
                    reservation = atomic_creator(
                        self.orchestrator.store,
                        prepared,
                        recipe,
                        idempotency_key=idempotency_key,
                    )
                else:
                    reservation = self.access.reserve_build(
                        identity.subject,
                        job_id=requested_job_id,
                        idempotency_key=idempotency_key,
                    )
                job_id = str(reservation["jobId"])
                if reservation.get("existing"):
                    existing = self.orchestrator.inspect(job_id, identity)
                    return jsonify(
                        public_job_payload(existing, self.orchestrator.store.recipe(job_id))
                    ), 200
                manifest_value = reservation.get("manifest")
                manifest = (
                    manifest_value
                    if isinstance(manifest_value, JobManifest)
                    else self.orchestrator.submit(
                        recipe,
                        identity,
                        job_id=job_id,
                        reservation_already_made=True,
                    )
                )
                job_created = True
                self.runtime.start(manifest)
                return jsonify(public_job_payload(manifest, recipe)), 201
            except BuildQuotaError as exc:
                return jsonify({"error": str(exc), "code": "build_quota_exhausted"}), 403
            except BuildConcurrencyError as exc:
                return jsonify({"error": str(exc), "code": "build_concurrency_conflict"}), 409
            except PermissionError as exc:
                return jsonify({"error": str(exc), "code": "access_denied"}), 403
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                RecipeValidationError,
                RunnerUnavailableError,
                OrchestrationError,
            ) as exc:
                if reservation and not reservation.get("existing"):
                    self.access.compensate_build(
                        identity.subject,
                        str(reservation["jobId"]),
                        reason=str(exc),
                        retain_job=job_created,
                    )
                return jsonify({"error": str(exc)}), 400

        @app.get("/v1/jobs")
        def list_jobs() -> Response:
            identity = self._identity()
            jobs = self.orchestrator.list(identity)[:100]
            return jsonify(
                {
                    "jobs": [
                        public_job_payload(
                            manifest,
                            self.orchestrator.store.recipe(manifest.job_id),
                        )
                        for manifest in jobs
                    ]
                }
            )

        @app.get("/v1/drafts/source")
        def source_draft() -> Response:
            identity = self._identity()
            return jsonify({"uri": self.session_store.source_draft(identity.subject)})

        @app.get("/v1/jobs/<job_id>")
        def job_detail(job_id: str) -> Response:
            try:
                manifest = self.orchestrator.inspect(job_id, self._identity())
                refreshed = self.runtime.refresh(manifest)
                if refreshed.owner.channel == "telegram":
                    self.access.update_job_status(refreshed.owner.subject, job_id, refreshed.status.value)
                return jsonify(
                    public_job_payload(refreshed, self.orchestrator.store.recipe(job_id))
                )
            except OrchestrationError as exc:
                return jsonify({"error": str(exc)}), 404

        @app.get("/v1/jobs/<job_id>/events")
        def job_events(job_id: str) -> Response:
            try:
                after = max(0, int(request.args.get("after", "0")))
                events = self.orchestrator.events(job_id, self._identity(), after=after)
                return jsonify({"events": [public_event_payload(event) for event in events]})
            except ValueError:
                return jsonify({"error": "Event cursor must be an integer"}), 400
            except OrchestrationError as exc:
                return jsonify({"error": str(exc)}), 404

        @app.post("/v1/jobs/<job_id>/cancel")
        def cancel_job(job_id: str) -> Response:
            try:
                current = self.orchestrator.inspect(job_id, self._identity())
                cancelled = self.orchestrator.cancel(job_id, self._identity())
                self.runtime.cancel_external(current)
                self.runtime.notify_terminal(cancelled)
                if cancelled.owner.channel == "telegram":
                    self.access.update_job_status(cancelled.owner.subject, job_id, cancelled.status.value)
                return jsonify(
                    public_job_payload(cancelled, self.orchestrator.store.recipe(job_id))
                )
            except OrchestrationError as exc:
                return jsonify({"error": str(exc)}), 404

        @app.get("/v1/jobs/<job_id>/download")
        def job_download(job_id: str) -> Response:
            ticket = request.args.get("ticket", "")
            if ticket:
                try:
                    subject = self._validate_download_ticket(job_id, ticket)
                except TelegramInitDataError as exc:
                    return jsonify({"error": str(exc)}), 403
                manifest = self.orchestrator.store.get(job_id)
                identity = self.access.identity(subject)
                if manifest is None or not identity or not (
                    identity.role == "admin"
                    or (manifest.owner.channel == "telegram" and manifest.owner.subject == subject)
                ):
                    return jsonify({"error": "Artifact download is not available"}), 404
            else:
                try:
                    manifest = self.orchestrator.inspect(job_id, self._identity())
                except OrchestrationError as exc:
                    return jsonify({"error": str(exc)}), 404
            target = next(
                (
                    public_artifact_url(item.public_url)
                    for item in manifest.artifacts
                    if public_artifact_url(item.public_url)
                ),
                "",
            )
            if not target:
                return jsonify({"error": "Artifact download is not available yet"}), 409
            if not ticket:
                return jsonify(
                    {
                        "downloadUrl": target,
                        "provider": urlsplit(target).hostname,
                    }
                )
            return redirect(target, code=302)

        @app.get("/v1/admin/users")
        def admin_users() -> Response:
            actor = self._require_admin_identity()
            try:
                return jsonify(
                    self.access.list_users(
                        actor=actor,
                        query=request.args.get("query", ""),
                        status=request.args.get("status", ""),
                        quota=request.args.get("quota", ""),
                        activity=request.args.get("activity", ""),
                        limit=int(request.args.get("limit", "50")),
                        offset=int(request.args.get("offset", "0")),
                        sort=request.args.get("sort", "lastSeenAt"),
                        direction=request.args.get("direction", "desc"),
                    )
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

        @app.post("/v1/admin/users")
        def admin_create_user() -> Response:
            actor = self._require_admin_identity()
            payload = request.get_json(force=True) or {}
            try:
                profile = self.access.create_user(
                    payload.get("telegramId"),
                    actor=actor,
                    username=str(payload.get("username") or ""),
                    display_name=str(payload.get("displayName") or ""),
                )
                return jsonify({"user": profile}), 201
            except (TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400

        @app.get("/v1/admin/users/<telegram_id>")
        def admin_user_detail(telegram_id: str) -> Response:
            actor = self._require_admin_identity()
            profile = self.access.profile(telegram_id)
            if not profile:
                return jsonify({"error": "Telegram user was not found"}), 404
            jobs = [
                public_job_payload(job, self.orchestrator.store.recipe(job.job_id))
                for job in self.orchestrator.list(actor)
                if job.owner.channel == "telegram" and job.owner.subject == str(telegram_id)
            ][:50]
            event_page = self.access.user_events(
                telegram_id,
                actor=actor,
                limit=101,
            )
            visible_events = event_page[:100]
            return jsonify(
                {
                    "user": profile,
                    "events": visible_events,
                    "eventsHasMore": len(event_page) > 100,
                    "eventsNextCursor": (
                        _encode_audit_cursor(visible_events[-1])
                        if len(event_page) > 100 and visible_events
                        else ""
                    ),
                    "jobs": jobs,
                }
            )

        @app.get("/v1/admin/users/<telegram_id>/events")
        def admin_user_events(telegram_id: str) -> Response:
            actor = self._require_admin_identity()
            try:
                limit = max(1, min(int(request.args.get("limit", "100")), 100))
                before = _decode_audit_cursor(request.args.get("cursor", ""))
                event_page = self.access.user_events(
                    telegram_id,
                    actor=actor,
                    limit=limit + 1,
                    before=before,
                )
                visible_events = event_page[:limit]
                has_more = len(event_page) > limit
                return jsonify(
                    {
                        "events": visible_events,
                        "hasMore": has_more,
                        "nextCursor": (
                            _encode_audit_cursor(visible_events[-1])
                            if has_more and visible_events
                            else ""
                        ),
                    }
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

        @app.post("/v1/admin/users/<telegram_id>/approve")
        def admin_approve_user(telegram_id: str) -> Response:
            actor = self._require_admin_identity()
            payload = request.get_json(silent=True) or {}
            try:
                self.access.approve(telegram_id, actor=actor, reason=str(payload.get("reason") or ""))
                self._notify_access_change(telegram_id, "Tài khoản Wukong ROM Studio đã được duyệt. Bạn có 1 lượt build.")
                return jsonify({"user": self.access.profile(telegram_id)})
            except (PermissionError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 409

        @app.post("/v1/admin/users/<telegram_id>/revoke")
        def admin_revoke_user(telegram_id: str) -> Response:
            actor = self._require_admin_identity()
            payload = request.get_json(silent=True) or {}
            reason = str(payload.get("reason") or "").strip()
            if not reason:
                return jsonify({"error": "A reason is required to revoke access"}), 400
            try:
                self.access.revoke(telegram_id, actor=actor, reason=reason)
                self._notify_access_change(telegram_id, f"Quyền truy cập Wukong ROM Studio đã bị thu hồi. Lý do: {reason}")
                return jsonify({"user": self.access.profile(telegram_id)})
            except (PermissionError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 409

        @app.post("/v1/admin/users/<telegram_id>/allowance")
        def admin_user_allowance(telegram_id: str) -> Response:
            actor = self._require_admin_identity()
            payload = request.get_json(force=True) or {}
            operation = str(payload.get("operation") or "").strip().casefold()
            reason = str(payload.get("reason") or "").strip()
            try:
                value = int(payload["value"]) if payload.get("value") is not None else None
                unlimited = payload.get("unlimited")
                if operation == "unlimited" and unlimited is not True and unlimited is not False:
                    raise ValueError("Unlimited value must be a boolean")
                profile = self.access.update_allowance(
                    telegram_id,
                    actor=actor,
                    operation=operation,
                    value=value,
                    unlimited=unlimited if isinstance(unlimited, bool) else None,
                    reason=reason,
                )
                quota = "không giới hạn" if profile.get("unlimited") else f"{profile.get('buildCredits', 0)} lượt"
                self._notify_access_change(telegram_id, f"Hạn mức Wukong ROM Studio đã thay đổi: {quota}.")
                return jsonify({"user": profile})
            except (PermissionError, TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 409

        @app.post("/v1/jobs/<job_id>/resume")
        def resume_job(job_id: str) -> Response:
            try:
                resumed = self.runtime.resume(job_id, self._identity())
                return jsonify(
                    public_job_payload(resumed, self.orchestrator.store.recipe(resumed.job_id))
                ), 201
            except OrchestrationError as exc:
                return jsonify({"error": str(exc)}), 409

        @app.get("/v1/diagnostics")
        def diagnostics() -> Response:
            return jsonify(self.diagnostics_provider())

        @app.get("/v1/cache")
        def cache_status() -> Response:
            return jsonify(self.cache_provider() if self.cache_provider else {})

        @app.post("/v1/cache/clear")
        def clear_cache() -> Response:
            if self._identity().role != "admin":
                return jsonify({"error": "Admin access is required to clear shared cache"}), 403
            if not self.cache_clearer:
                return jsonify({"error": "Cache clearing is not configured"}), 503
            try:
                return jsonify(self.cache_clearer())
            except (OSError, RuntimeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 409

        @app.get("/v1/cloud/library")
        def cloud_library() -> Response:
            if not self.cloud_provider:
                return jsonify({"available": False, "entries": []})
            try:
                category = request.args.get("category", "artifacts")
                return jsonify(self.cloud_provider(category))
            except (OSError, RuntimeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400

        return app

    def _identity(self) -> Identity:
        identity = request.environ.get("wukong.identity")
        if not isinstance(identity, Identity):
            raise TelegramInitDataError("Telegram Mini App authentication is required")
        return identity

    def _telegram_subject(self) -> str:
        subject = str(request.environ.get("wukong.telegram_subject") or "").strip()
        if subject:
            return subject
        return self._identity().subject

    def _require_admin_identity(self) -> Identity:
        identity = self._identity()
        if identity.role != "admin":
            raise TelegramInitDataError("Admin access is required")
        return identity

    def _notify_access_change(self, telegram_id: int | str, text: str) -> None:
        """Send an access/quota update without delaying the admin response."""

        def send() -> None:
            try:
                import requests

                response = requests.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": str(telegram_id),
                        "text": str(text)[:4096],
                        "disable_web_page_preview": True,
                    },
                    timeout=15,
                )
                response.raise_for_status()
            except Exception as exc:  # noqa: BLE001 - notification is best effort
                print(f"Telegram access notification failed: {type(exc).__name__}", flush=True)

        threading.Thread(target=send, name="wukong-access-notification", daemon=True).start()

    def _issue_download_ticket(self, job_id: str, subject: str) -> str:
        return issue_artifact_download_ticket(job_id, subject, self.bot_token)

    def _validate_download_ticket(self, job_id: str, ticket: str) -> str:
        parts = str(ticket or "").split(".")
        if (
            len(parts) != 4
            or parts[0] != "v1"
            or not parts[1].isdigit()
            or not parts[2].isdigit()
            or not re.fullmatch(r"[0-9a-f]{64}", parts[3], re.IGNORECASE)
        ):
            raise TelegramInitDataError("Artifact download ticket is invalid")
        payload = ".".join(parts[:3])
        expected = hmac.new(
            _telegram_launch_key(self.bot_token),
            f"download\0{job_id}\0{payload}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(parts[3].casefold(), expected) or int(parts[2]) < int(time.time()):
            raise TelegramInitDataError("Artifact download ticket is invalid or expired")
        return parts[1]

    def _remember_probe(
        self, identity: Identity, uri: str, result: Mapping[str, object]
    ) -> None:
        safe = {key: value for key, value in result.items() if key != "metadata"}
        with self._probe_lock:
            self._probe_cache[(identity.subject, uri)] = (time.monotonic(), copy.deepcopy(safe))

    def _cached_probe(self, identity: Identity, uri: str) -> dict[str, object] | None:
        with self._probe_lock:
            entry = self._probe_cache.get((identity.subject, uri))
            if not entry or time.monotonic() - entry[0] > self.probe_cache_seconds:
                self._probe_cache.pop((identity.subject, uri), None)
                return None
            return copy.deepcopy(entry[1])

    def _verified_recipe(self, payload: Mapping[str, object], identity: Identity) -> BuildRecipe:
        clean_payload = copy.deepcopy(dict(payload))
        source_payload = clean_payload.get("source")
        if not isinstance(source_payload, dict):
            raise RecipeValidationError("ROM source is required")
        source_payload.pop("metadata", None)
        preliminary = BuildRecipe.from_dict(clean_payload)
        release_versions = self.release_versions_provider()
        release_version = str(release_versions.get(preliminary.build.mod_version) or "").strip()
        if not MOD_RELEASE_VERSION_RE.fullmatch(release_version):
            release_version = preliminary.build.mod_release_version or preliminary.build.mod_version
        preliminary = replace(
            preliminary,
            build=replace(preliminary.build, mod_release_version=release_version),
        )
        if preliminary.source.kind not in {"http", "https"}:
            return preliminary
        # Probe results may remain cached while a direct signed URL continues
        # counting down. Re-check at submission so it cannot expire in the
        # cloud queue after an earlier successful preview.
        validate_direct_signed_url_ttl(preliminary.source.uri)
        result = self._cached_probe(identity, preliminary.source.uri)
        if result is None:
            if not self._probe_slots.acquire(blocking=False):
                raise RuntimeError("Two ROM probes are already running; try again shortly")
            try:
                result = self.source_probe_provider(preliminary.source.uri)
            finally:
                self._probe_slots.release()
            self._remember_probe(identity, preliminary.source.uri, result)
        metadata = {
            key: str(result.get(key) or "").strip()
            for key in SOURCE_METADATA_KEYS
            if str(result.get(key) or "").strip()
        }
        size = result.get("sizeBytes")
        size_bytes = int(size) if isinstance(size, int) and size > 0 else preliminary.source.size_bytes
        source = replace(preliminary.source, size_bytes=size_bytes, metadata=metadata)
        return replace(preliminary, source=source)


class TelegramMiniAppAPIServer:
    def __init__(self, api: TelegramMiniAppAPI, *, host: str, port: int) -> None:
        self.api = api
        self.host = host
        self.port = port
        self._server: BaseWSGIServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._server = make_server(self.host, self.port, self.api.app, threaded=True)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="wukong-telegram-mini-api",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)


class TelegramJobNotifier:
    def __init__(self, bot_token: str, *, http_post: Callable[..., object] | None = None) -> None:
        self.bot_token = bot_token
        self.endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        if http_post is None:
            import requests

            http_post = requests.post
        self.http_post = http_post

    def __call__(self, manifest: JobManifest, recipe: BuildRecipe) -> None:
        if manifest.owner.channel != "telegram" or not recipe.build.notify_telegram:
            return
        metadata = recipe.source.metadata
        succeeded = manifest.status == JobStatus.SUCCEEDED
        title = "Build ROM hoàn tất" if succeeded else "Build ROM cần kiểm tra"
        status = "Thành công" if succeeded else manifest.status.value

        def escape(value: object, limit: int = 240) -> str:
            return html.escape(str(value or "—")[:limit], quote=False)

        lines = [
            "<b>Wukong ROM Studio</b>",
            f"<b>{title}</b>",
            "",
            "<b>Thông tin bản ROM</b>",
            f"Trạng thái  <b>{escape(status)}</b>",
            f"Job  <code>{escape(manifest.job_id, 32)}</code>",
            f"Thiết bị  <code>{escape(recipe.device)}</code>",
            f"Phiên bản  <code>{escape(metadata.get('version'))}</code>",
            f"Android  <code>{escape(metadata.get('androidVersion'))}</code>",
            f"Bản vá  <code>{escape(metadata.get('securityPatch'))}</code>",
            f"Ngày build  <code>{escape(metadata.get('buildDate'))}</code>",
            "",
            "<b>Cấu hình</b>",
            f"Preset  <code>{escape(recipe.build.preset)}</code>",
            f"MOD pack  <code>{escape(recipe.build.mod_version)}</code>",
            f"Phát hành  <code>{escape(recipe.build.mod_release_version)}</code>",
            f"Runner  <code>{escape(manifest.runner)}</code>",
        ]
        duration = self._duration(manifest.created_at, manifest.finished_at)
        if duration:
            lines.append(f"Thời gian  <code>{duration}</code>")
        if manifest.error:
            lines.extend(
                [
                    "",
                    "<b>Thông tin cần lưu ý</b>",
                    escape(sanitize_public_value(manifest.error), 640),
                ]
            )
        keyboard: list[list[dict[str, object]]] = []
        if manifest.artifacts:
            lines.extend(["", "<b>Artifact</b>"])
            for index, artifact in enumerate(manifest.artifacts[:8], start=1):
                cloud_url = public_artifact_url(artifact.public_url)
                edition = (
                    "Lite"
                    if "lite" in artifact.name.casefold()
                    else "Plus"
                    if "plus" in artifact.name.casefold()
                    else f"File {index}"
                )
                lines.extend(
                    [
                        f"{index}. <b>{escape(edition)}</b> · {self._size(artifact.size_bytes)}",
                        f"<code>{escape(artifact.name)}</code>",
                        f"SHA-256  <code>{escape(artifact.sha256)}</code>",
                    ]
                )
                if cloud_url:
                    keyboard.append(
                        [
                            {
                                "text": f"Tải {edition} · {self._size(artifact.size_bytes)}",
                                "url": cloud_url,
                            }
                        ]
                    )
        web_app_url = os.environ.get("WUKONG_TELEGRAM_WEB_APP_URL", "").strip()
        if web_app_url.startswith("https://"):
            keyboard.append(
                [
                    {
                        "text": "Mở Wukong Mini App",
                        "web_app": {"url": web_app_url},
                    }
                ]
            )
        payload: dict[str, object] = {
            "chat_id": manifest.owner.subject,
            "text": self._bounded_html_message(lines),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        response = self.http_post(
            self.endpoint,
            json=payload,
            timeout=20,
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()

    @staticmethod
    def _size(value: int) -> str:
        size = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024 or unit == "TiB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
            size /= 1024
        return f"{value} B"

    @staticmethod
    def _bounded_html_message(lines: list[str], limit: int = 4096) -> str:
        output: list[str] = []
        suffix = "<i>…</i>"
        for line in lines:
            candidate = "\n".join([*output, line])
            if len(candidate) <= limit:
                output.append(line)
                continue
            while output and len("\n".join([*output, suffix])) > limit:
                output.pop()
            if len("\n".join([*output, suffix])) <= limit:
                output.append(suffix)
            break
        return "\n".join(output)

    @staticmethod
    def _duration(start: str, end: str | None) -> str:
        if not end:
            return ""
        try:
            started = datetime.fromisoformat(start.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(end.replace("Z", "+00:00"))
            seconds = max(0, round((finished - started).total_seconds()))
        except ValueError:
            return ""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

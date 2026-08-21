from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

from flask import Flask, Response, jsonify, request
from werkzeug.serving import BaseWSGIServer, make_server

from .models import BuildRecipe, Identity, JobManifest, JobStatus, RecipeValidationError, SourceSpec
from .orchestrator import HybridOrchestrator, OrchestrationError
from .routing import RunnerUnavailableError
from .runtime import HybridRuntime
from .telegram import TelegramAccessStore

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
RELEASE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


class TelegramInitDataError(PermissionError):
    pass


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


def _public_job(manifest: JobManifest, recipe: BuildRecipe | None) -> dict[str, object]:
    payload = manifest.to_dict()
    payload.pop("owner", None)
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
    return payload


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
        diagnostics_provider: Callable[[], dict[str, object]],
        source_probe_provider: Callable[[str], dict[str, object]],
        cloud_provider: Callable[[str], dict[str, object]] | None = None,
        cache_provider: Callable[[], dict[str, object]] | None = None,
        cache_clearer: Callable[[], dict[str, object]] | None = None,
        telegram_update_handler: Callable[[dict[str, object]], None] | None = None,
        telegram_webhook_secret: str | None = None,
        readiness_provider: Callable[[], bool] | None = None,
        max_init_data_age_seconds: int = 3600,
        probe_cache_seconds: int = 15 * 60,
    ) -> None:
        self.bot_token = bot_token
        self.allowed_origin = _origin_from_web_app_url(allowed_origin)
        self.access = access
        self.orchestrator = orchestrator
        self.runtime = runtime
        self.catalog_provider = catalog_provider
        self.diagnostics_provider = diagnostics_provider
        self.source_probe_provider = source_probe_provider
        self.cloud_provider = cloud_provider
        self.cache_provider = cache_provider
        self.cache_clearer = cache_clearer
        self.telegram_update_handler = telegram_update_handler
        self.telegram_webhook_secret = (telegram_webhook_secret or "").strip()
        if bool(self.telegram_update_handler) != bool(self.telegram_webhook_secret):
            raise ValueError("Telegram webhook handler and secret must be configured together")
        self.readiness_provider = readiness_provider or (lambda: True)
        self.max_init_data_age_seconds = max(60, max_init_data_age_seconds)
        self.probe_cache_seconds = max(60, probe_cache_seconds)
        self._probe_cache: dict[tuple[str, str], tuple[float, dict[str, object]]] = {}
        self._probe_lock = threading.RLock()
        self._probe_slots = threading.BoundedSemaphore(2)
        self.app = self._create_app()

    def _create_app(self) -> Flask:
        app = Flask("wukong-telegram-mini-api", static_folder=None)
        app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

        @app.before_request
        def authenticate() -> Response | None:
            if request.path == "/healthz":
                return None
            if request.path == "/telegram/webhook":
                supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if not self.telegram_webhook_secret or not hmac.compare_digest(
                    supplied,
                    self.telegram_webhook_secret,
                ):
                    return jsonify({"error": "Telegram webhook authentication failed"}), 403
                return None
            origin = (request.headers.get("Origin") or "").rstrip("/").casefold()
            if origin != self.allowed_origin.casefold():
                return jsonify({"error": "This Mini App origin is not allowed"}), 403
            if request.method == "OPTIONS":
                return Response(status=204)
            authorization = request.headers.get("Authorization", "")
            scheme, separator, init_data = authorization.partition(" ")
            if separator != " " or scheme.casefold() != "tma":
                return jsonify({"error": "Telegram Mini App authentication is required"}), 401
            try:
                telegram = validate_telegram_init_data(
                    init_data,
                    self.bot_token,
                    max_age_seconds=self.max_init_data_age_seconds,
                )
                user = telegram["user"]
                identity = self.access.identity(str(user["id"])) if isinstance(user, dict) else None
                if not identity:
                    return jsonify({"error": "Telegram account is not approved"}), 403
                request.environ["wukong.identity"] = identity
            except (TelegramInitDataError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 401
            return None

        @app.after_request
        def add_cors_headers(response: Response) -> Response:
            origin = (request.headers.get("Origin") or "").rstrip("/").casefold()
            if origin == self.allowed_origin.casefold():
                response.headers["Access-Control-Allow-Origin"] = self.allowed_origin
                response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Max-Age"] = "600"
                response.headers["Vary"] = "Origin"
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.get("/v1/catalog")
        def catalog() -> Response:
            return jsonify(self.catalog_provider())

        @app.get("/healthz")
        def health() -> Response:
            release = os.environ.get("WUKONG_RELEASE_SHA", "").strip().casefold()
            ready = bool(self.readiness_provider())
            return jsonify(
                {
                    "status": "ready" if ready else "starting",
                    "service": "wukong-control-plane",
                    "release": release if RELEASE_SHA_RE.fullmatch(release) else "development",
                }
            ), 200 if ready else 503

        @app.post("/telegram/webhook")
        def telegram_webhook() -> Response:
            if self.telegram_update_handler is None:
                return jsonify({"error": "Telegram webhook is not configured"}), 503
            payload = request.get_json(force=True)
            if not isinstance(payload, dict):
                return jsonify({"error": "Telegram update must be an object"}), 400
            self.telegram_update_handler(payload)
            return Response(status=204)

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
                self._remember_probe(self._identity(), uri, result)
                return jsonify({key: value for key, value in result.items() if key != "metadata"})
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400

        @app.post("/v1/jobs")
        def create_job() -> Response:
            try:
                payload = request.get_json(force=True) or {}
                if not isinstance(payload, Mapping):
                    raise RecipeValidationError("Build recipe must be an object")
                recipe = self._verified_recipe(payload, self._identity())
                manifest = self.orchestrator.submit(recipe, self._identity())
                self.runtime.start(manifest)
                return jsonify(_public_job(manifest, recipe)), 201
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                RecipeValidationError,
                RunnerUnavailableError,
                OrchestrationError,
            ) as exc:
                return jsonify({"error": str(exc)}), 400

        @app.get("/v1/jobs")
        def list_jobs() -> Response:
            identity = self._identity()
            jobs = self.orchestrator.list(identity)[:100]
            return jsonify(
                {
                    "jobs": [
                        _public_job(manifest, self.orchestrator.store.recipe(manifest.job_id))
                        for manifest in jobs
                    ]
                }
            )

        @app.get("/v1/jobs/<job_id>")
        def job_detail(job_id: str) -> Response:
            try:
                manifest = self.orchestrator.inspect(job_id, self._identity())
                refreshed = self.runtime.refresh(manifest)
                return jsonify(_public_job(refreshed, self.orchestrator.store.recipe(job_id)))
            except OrchestrationError as exc:
                return jsonify({"error": str(exc)}), 404

        @app.get("/v1/jobs/<job_id>/events")
        def job_events(job_id: str) -> Response:
            try:
                after = max(0, int(request.args.get("after", "0")))
                events = self.orchestrator.events(job_id, self._identity(), after=after)
                return jsonify({"events": [event.to_dict() for event in events]})
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
                return jsonify(_public_job(cancelled, self.orchestrator.store.recipe(job_id)))
            except OrchestrationError as exc:
                return jsonify({"error": str(exc)}), 404

        @app.post("/v1/jobs/<job_id>/resume")
        def resume_job(job_id: str) -> Response:
            try:
                resumed = self.runtime.resume(job_id, self._identity())
                return jsonify(
                    _public_job(resumed, self.orchestrator.store.recipe(resumed.job_id))
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
        if preliminary.source.kind not in {"http", "https"}:
            return preliminary
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
        self.endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        if http_post is None:
            import requests

            http_post = requests.post
        self.http_post = http_post

    def __call__(self, manifest: JobManifest, recipe: BuildRecipe) -> None:
        if manifest.owner.channel != "telegram" or not recipe.build.notify_telegram:
            return
        metadata = recipe.source.metadata
        lines = [
            "Wukong ROM Studio · Build report",
            "",
            f"Job: {manifest.job_id}",
            f"Status: {manifest.status.value}",
            f"Device: {recipe.device}",
            f"Product: {metadata.get('productName') or recipe.device}",
            f"Version: {metadata.get('version') or '—'}",
            f"Android: {metadata.get('androidVersion') or '—'}",
            f"Security patch: {metadata.get('securityPatch') or '—'}",
            f"Build date: {metadata.get('buildDate') or '—'}",
            f"Preset / MOD pack: {recipe.build.preset} / {recipe.build.mod_version}",
            f"Runner: {manifest.runner or '—'}",
        ]
        duration = self._duration(manifest.created_at, manifest.finished_at)
        if duration:
            lines.append(f"Duration: {duration}")
        if manifest.error:
            lines.extend(["", f"Error: {manifest.error}"])
        if manifest.artifacts:
            lines.extend(["", "Artifacts:"])
            for artifact in manifest.artifacts:
                lines.extend(
                    [
                        f"• {artifact.name} ({self._size(artifact.size_bytes)})",
                        f"  SHA-256: {artifact.sha256}",
                        f"  {artifact.public_url or artifact.uri}",
                    ]
                )
        response = self.http_post(
            self.endpoint,
            json={
                "chat_id": manifest.owner.subject,
                "text": "\n".join(lines)[:4096],
                "disable_web_page_preview": True,
            },
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

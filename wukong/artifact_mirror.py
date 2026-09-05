"""Best-effort DC Cloud artifact mirroring for GitHub Actions.

The mirror intentionally has no authentication client of its own.  rclone's
WebDAV remote is provisioned as a GitHub secret and the public folder URL is
configuration, so local Windows runs remain completely unchanged.
"""

from __future__ import annotations

from .artifacts import PreparedArtifact

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

from .adapters import RcloneStorageAdapter
from .cloudreve import CloudreveClient, CloudreveStorageAdapter
from .split_mirror import RcloneSplitStorageAdapter
from .models import ArtifactMirrorRecord, ArtifactRecord


_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_ROOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)*$")
_ERROR_CODE_RE = re.compile(r"^remote_(?:upload|stat|mkdir|move|metadata)_failed$")
_ERROR_CODES = {
    "FileNotFoundError": "source_missing",
    "SourceIntegrityError": "integrity_mismatch",
    "TimeoutExpired": "timeout",
    "CalledProcessError": "remote_command_failed",
    "PermissionError": "permission_denied",
}


@dataclass(frozen=True)
class DCloudMirrorConfig:
    enabled: bool
    remote: str = "wukong-dccloud"
    root: str = "ROM"
    share_url: str = ""
    config_path: Path | None = None
    cloudreve_version: str = ""
    validation_error: str | None = None
    webdav_url: str = ""
    upload_mode: str = "multipart"
    api_url: str = ""
    refresh_token: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, *, config_path: Path | None = None) -> "DCloudMirrorConfig":
        actions = (
            os.environ.get("GITHUB_ACTIONS", "").casefold() == "true"
            and os.environ.get("RUNNER_OS", "Linux").casefold() == "linux"
        )
        enabled = actions and os.environ.get("WUKONG_DCCLOUD_MIRROR_ENABLED", "false").casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
        remote = os.environ.get("WUKONG_DCCLOUD_REMOTE", "wukong-dccloud").strip()
        root = os.environ.get("WUKONG_DCCLOUD_ROOT", "ROM").strip().strip("/\\")
        share_url = os.environ.get("WUKONG_DCCLOUD_SHARE_URL", "").strip()
        webdav_url = os.environ.get("WUKONG_DCCLOUD_WEBDAV_URL", "").strip()
        upload_mode = os.environ.get("WUKONG_DCCLOUD_UPLOAD_MODE", "multipart").strip().casefold()
        api_url = os.environ.get("WUKONG_DCCLOUD_API_URL", "").strip()
        refresh_token = os.environ.get("WUKONG_DCCLOUD_REFRESH_TOKEN", "").strip()
        validation_error = None
        if enabled and upload_mode not in {"webdav", "native", "multipart"}:
            validation_error = "WUKONG_DCCLOUD_UPLOAD_MODE must be webdav, native, or multipart"
        elif enabled and upload_mode in {"webdav", "multipart"} and not _REMOTE_RE.fullmatch(remote):
            validation_error = "WUKONG_DCCLOUD_REMOTE is invalid"
        elif enabled and not _ROOT_RE.fullmatch(root):
            validation_error = "WUKONG_DCCLOUD_ROOT is invalid"
        elif enabled and not share_url:
            validation_error = "WUKONG_DCCLOUD_SHARE_URL is required when mirroring is enabled"
        elif enabled and upload_mode == "native" and not api_url:
            validation_error = "WUKONG_DCCLOUD_API_URL is required for native upload"
        elif enabled and upload_mode == "native" and not refresh_token:
            validation_error = "WUKONG_DCCLOUD_REFRESH_TOKEN is required for native upload"
        elif enabled and upload_mode == "native":
            try:
                parsed_api = urlsplit(api_url)
            except ValueError:
                parsed_api = None
            if (
                parsed_api is None
                or parsed_api.scheme.casefold() != "https"
                or not parsed_api.hostname
                or parsed_api.username
                or parsed_api.password
                or parsed_api.query
                or parsed_api.fragment
            ):
                validation_error = "WUKONG_DCCLOUD_API_URL must be HTTPS without credentials"
        elif enabled and webdav_url:
            try:
                parsed_webdav = urlsplit(webdav_url)
            except ValueError:
                parsed_webdav = None
            if (
                parsed_webdav is None
                or parsed_webdav.scheme.casefold() != "https"
                or not parsed_webdav.hostname
                or parsed_webdav.username
                or parsed_webdav.password
                or parsed_webdav.query
                or parsed_webdav.fragment
            ):
                validation_error = "WUKONG_DCCLOUD_WEBDAV_URL must be HTTPS without credentials"
        if enabled and share_url and validation_error is None:
            try:
                parsed = urlsplit(share_url)
            except ValueError:
                parsed = None
            if parsed is None or parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
                validation_error = "WUKONG_DCCLOUD_SHARE_URL must be public HTTPS"
        return cls(
            enabled=enabled,
            remote=remote,
            root=root,
            share_url=share_url,
            webdav_url=webdav_url,
            upload_mode=upload_mode,
            api_url=api_url,
            refresh_token=refresh_token,
            config_path=config_path,
            cloudreve_version=os.environ.get("WUKONG_DCCLOUD_CLOUDREVE_VERSION", "").strip(),
            validation_error=validation_error,
        )


def _relative_artifact_path(
    *,
    mirror_root: str,
    device: str,
    build: str,
    name: str,
    relative_root: str | None,
) -> str:
    if relative_root:
        root = relative_root.replace("\\", "/").strip("/")
        prefix = mirror_root.rstrip("/") + "/"
        if root.casefold().startswith(prefix.casefold()):
            root = root[len(prefix) :]
        return f"{mirror_root.strip('/')}/{root}/{build}/{name}".replace("//", "/")
    return f"{mirror_root.strip('/')}/artifacts/{device}/{build}/{name}"


class ArtifactMirrorPublisher:
    """Upload one ZIP and its checksum metadata with bounded retries."""

    def __init__(
        self,
        config: DCloudMirrorConfig,
        *,
        storage_factory: Callable[[str], RcloneStorageAdapter] | None = None,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        if storage_factory is not None:
            self.storage_factory = storage_factory
        elif config.upload_mode == "native":
            self.storage_factory = lambda _remote: CloudreveStorageAdapter(
                CloudreveClient(config.api_url, config.refresh_token)
            )
        elif config.upload_mode == "multipart":
            self.storage_factory = lambda remote: RcloneSplitStorageAdapter(
                RcloneStorageAdapter(
                    remote=remote,
                    root="",
                    webdav_url=config.webdav_url or None,
                    config_path=config.config_path,
                )
            )
        else:
            self.storage_factory = lambda remote: RcloneStorageAdapter(
                remote=remote,
                # The WebDAV device is already scoped to My Files/WukongROM;
                # WUKONG_DCCLOUD_ROOT is therefore the first remote segment.
                root="",
                webdav_url=config.webdav_url or None,
                config_path=config.config_path,
            )
        self.retry_attempts = max(1, min(3, retry_attempts))
        self.sleep = sleep

    def publish(
        self,
        artifact: Path,
        *,
        job_id: str,
        device: str,
        build: str,
        relative_root: str | None = None,
        relative_path: str | None = None,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
        prepared: PreparedArtifact | None = None,
    ) -> ArtifactMirrorRecord:
        browse_url = self.config.share_url or None
        if not self.config.enabled:
            return ArtifactMirrorRecord("dccloud", "pending", browse_url=browse_url)
        if self.config.validation_error:
            return ArtifactMirrorRecord(
                "dccloud",
                "failed",
                browse_url=browse_url,
                error_code="config_invalid",
            )
        final_path = relative_path or _relative_artifact_path(
            mirror_root=self.config.root,
            device=device,
            build=build,
            name=artifact.name,
            relative_root=relative_root,
        )
        last_error: Exception | None = None
        for attempt in range(self.retry_attempts):
            try:
                storage = self.storage_factory(self.config.remote)
                record = storage.mirror_artifact(
                    artifact,
                    relative_path=final_path,
                    staging_key=job_id,
                    progress_callback=progress_callback,
                    **({"prepared": prepared} if prepared is not None and isinstance(storage, (RcloneStorageAdapter, CloudreveStorageAdapter, RcloneSplitStorageAdapter)) else {}),
                )
                return ArtifactMirrorRecord(
                    provider="dccloud",
                    status="available",
                    uri=record.uri,
                    browse_url=browse_url,
                )
            except Exception as exc:  # mirror is explicitly best effort
                last_error = exc
                if attempt + 1 < self.retry_attempts:
                    self.sleep(2**attempt)
        stage_error = getattr(last_error, "error_code", None)
        error_code = (
            stage_error
            if isinstance(stage_error, str) and _ERROR_CODE_RE.fullmatch(stage_error)
            else _ERROR_CODES.get(type(last_error).__name__, "upload_failed")
        )
        return ArtifactMirrorRecord(
            provider="dccloud",
            status="failed",
            browse_url=browse_url,
            error_code=error_code,
        )


def attach_mirror(record: ArtifactRecord, mirror: ArtifactMirrorRecord) -> ArtifactRecord:
    # A repair run is an upsert for the provider, not a new list entry. This
    # keeps repeated repair attempts idempotent while preserving other mirrors.
    mirrors = [item for item in record.mirrors if item.provider.casefold() != mirror.provider.casefold()]
    return ArtifactRecord(
        name=record.name,
        uri=record.uri,
        sha256=record.sha256,
        size_bytes=record.size_bytes,
        public_url=record.public_url,
        mirrors=[*mirrors, mirror],
    )

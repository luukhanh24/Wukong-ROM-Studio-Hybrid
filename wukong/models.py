from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlparse

from .pipeline import PIPELINE_STEP_NAMES
from .mod_release_versions import SAFE_RELEASE_LABEL, default_mod_release_version


SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*:(?P<path>.*)$")
SECRET_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "credential",
    "privatekey",
    "private_key",
    "clientid",
    "client_id",
)
SENSITIVE_URL_PARAMETER_FRAGMENTS = (
    "access_token",
    "auth",
    "credential",
    "password",
    "secret",
    "signature",
    "token",
)
# Signed OPlus / Allawn OTA CDN links use short-lived AWS-style query auth.
# Allow those parameter names only on known public OEM hosts so recipes can
# reference real downloadCheck / gauss-compota URLs without embedding tokens
# for arbitrary third-party sites.
SIGNED_OTA_URL_PARAMETER_FRAGMENTS = (
    "awsaccesskeyid",
    "expires",
    "s",
    "sign",
    "signature",
    "t",
    "x-amz-algorithm",
    "x-amz-credential",
    "x-amz-date",
    "x-amz-expires",
    "x-amz-security-token",
    "x-amz-signature",
    "x-amz-signedheaders",
)
SIGNED_OTA_HOST_SUFFIXES = (
    ".allawnfs.com",
    ".allawntech.com",
    ".coloros.com",
    ".heytapdownload.com",
    ".heytapimage.com",
    ".heytapmobi.com",
    ".oppomobile.com",
    ".realme.com",
)
TASKS = {"source_mirror", "build", "artifact_publish"}
SOURCE_KINDS = {"local", "http", "https", "rclone"}
EXECUTION_TARGETS = {"local-windows", "github-auto", "github-hosted", "self-hosted-linux"}
ROLES = {"admin", "user"}
SOURCE_METADATA_KEYS = {
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
}


def _host_allows_signed_ota(hostname: str | None) -> bool:
    host = (hostname or "").rstrip(".").casefold()
    if not host:
        return False
    return any(host == suffix[1:] or host.endswith(suffix) for suffix in SIGNED_OTA_HOST_SUFFIXES)


class RecipeValidationError(ValueError):
    pass


def _boolean(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise RecipeValidationError(f"{key} must be a JSON boolean")
    return value


class JobStatus(str, Enum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    DOWNLOADING = "downloading"
    RUNNING = "running"
    UPLOADING = "uploading"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).replace("-", "").casefold()
            if any(fragment.replace("_", "") in normalized for fragment in SECRET_KEY_FRAGMENTS):
                return True
            if _contains_secret_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _safe_remote_uri(uri: str) -> bool:
    match = REMOTE_RE.fullmatch(uri)
    if not match:
        return False
    parts = PurePosixPath(match.group("path").replace("\\", "/")).parts
    return ".." not in parts


@dataclass(frozen=True)
class Identity:
    channel: str
    subject: str
    role: str = "user"

    def __post_init__(self) -> None:
        if not self.channel.strip() or not self.subject.strip():
            raise ValueError("Identity channel and subject are required")
        if self.role not in ROLES:
            raise ValueError(f"Unsupported identity role: {self.role}")


@dataclass(frozen=True)
class SourceSpec:
    kind: str
    uri: str
    sha256: str | None = None
    size_bytes: int | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceSpec":
        kind = str(payload.get("kind") or "").strip().casefold()
        uri = str(payload.get("uri") or "").strip()
        sha256 = str(payload.get("sha256") or "").strip().casefold() or None
        raw_size = payload.get("sizeBytes")
        size_bytes = int(raw_size) if raw_size is not None else None
        raw_metadata = payload.get("metadata", {})
        if not isinstance(raw_metadata, Mapping):
            raise RecipeValidationError("ROM source metadata must be an object")
        metadata: dict[str, str] = {}
        for key, raw_value in raw_metadata.items():
            name = str(key)
            if name not in SOURCE_METADATA_KEYS:
                raise RecipeValidationError(f"Unsupported ROM source metadata field: {name}")
            if not isinstance(raw_value, str):
                raise RecipeValidationError(f"ROM source metadata {name} must be text")
            value = raw_value.strip()
            if value:
                if len(value) > 1024 or any(ord(character) < 32 for character in value):
                    raise RecipeValidationError(f"ROM source metadata {name} is invalid")
                metadata[name] = value
        if kind not in SOURCE_KINDS:
            raise RecipeValidationError(f"Unsupported ROM source kind: {kind or '<empty>'}")
        if not uri:
            raise RecipeValidationError("ROM source URI is required")
        if kind in {"http", "https"}:
            parsed = urlparse(uri)
            if parsed.scheme.casefold() != kind or not parsed.netloc or parsed.username or parsed.password:
                raise RecipeValidationError(f"Invalid {kind.upper()} ROM source URI")
            query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
            allow_signed = _host_allows_signed_ota(parsed.hostname)
            for key in query_keys:
                if any(fragment in key for fragment in SENSITIVE_URL_PARAMETER_FRAGMENTS):
                    if allow_signed and any(fragment in key for fragment in SIGNED_OTA_URL_PARAMETER_FRAGMENTS):
                        continue
                    raise RecipeValidationError("ROM source URL must not contain credential parameters")
            # The adapter performs a DNS-aware check immediately before every
            # request/redirect. Reject obvious loopback and private IP literals
            # here so unsafe recipes never enter a job store.
            from .security import validate_http_url

            validate_http_url(uri)
        if kind == "rclone" and not _safe_remote_uri(uri):
            raise RecipeValidationError("Rclone URI is invalid or contains path traversal")
        if sha256 is not None and not SHA256_RE.fullmatch(sha256):
            raise RecipeValidationError("ROM SHA-256 must contain exactly 64 hexadecimal characters")
        if size_bytes is not None and size_bytes <= 0:
            raise RecipeValidationError("ROM source size must be positive")
        return cls(
            kind=kind,
            uri=uri,
            sha256=sha256,
            size_bytes=size_bytes,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": self.kind, "uri": self.uri}
        if self.sha256:
            result["sha256"] = self.sha256
        if self.size_bytes is not None:
            result["sizeBytes"] = self.size_bytes
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True)
class BuildOptions:
    preset: str = "lite"
    mods: tuple[str, ...] = ()
    mod_version: str = "ColorOS_16.0.7"
    mod_release_version: str | None = None
    enabled_steps: tuple[str, ...] = ()
    debloat_paths: tuple[str, ...] | None = None
    package: bool = True
    notify_telegram: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "BuildOptions":
        data = payload or {}
        preset = str(data.get("preset") or "lite").strip().casefold()
        if preset not in {"lite", "plus", "both", "custom", "resume", "standard"}:
            raise RecipeValidationError(f"Unsupported build preset: {preset}")
        mods = tuple(dict.fromkeys(str(value).strip() for value in data.get("mods", []) if str(value).strip()))
        steps = tuple(dict.fromkeys(str(value).strip() for value in data.get("enabledSteps", []) if str(value).strip()))
        mod_version = str(data.get("modVersion") or "ColorOS_16.0.7").strip()
        safe_name = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
        if not safe_name.fullmatch(mod_version):
            raise RecipeValidationError("MOD version must be path-safe")
        if any(not safe_name.fullmatch(value) for value in (*mods, *steps)):
            raise RecipeValidationError("MOD and enabled-step names must be path-safe")
        unknown_steps = [value for value in steps if value not in PIPELINE_STEP_NAMES]
        if unknown_steps:
            raise RecipeValidationError(
                f"Unsupported pipeline step: {', '.join(unknown_steps)}"
            )
        if "patch_vendor_boot" in steps:
            raise RecipeValidationError(
                "patch_vendor_boot is disabled by the system-only modification policy"
            )
        mod_release_version = str(
            data.get("modReleaseVersion")
            or default_mod_release_version(mod_version)
        ).strip()
        if not SAFE_RELEASE_LABEL.fullmatch(mod_release_version):
            raise RecipeValidationError("MOD release version must be 1–64 printable path-safe characters")
        raw_debloat = data.get("debloatPaths")
        debloat = None
        if raw_debloat is not None:
            if not isinstance(raw_debloat, list):
                raise RecipeValidationError("debloatPaths must be a list")
            debloat = tuple(str(value).strip() for value in raw_debloat if str(value).strip())
        return cls(
            preset=preset,
            mods=mods,
            mod_version=mod_version,
            mod_release_version=mod_release_version,
            enabled_steps=steps,
            debloat_paths=debloat,
            package=_boolean(data, "package", True),
            notify_telegram=_boolean(data, "notifyTelegram", False),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "preset": self.preset,
            "mods": list(self.mods),
            "modVersion": self.mod_version,
            "package": self.package,
        }
        if self.mod_release_version:
            result["modReleaseVersion"] = self.mod_release_version
        if self.enabled_steps:
            result["enabledSteps"] = list(self.enabled_steps)
        if self.debloat_paths is not None:
            result["debloatPaths"] = list(self.debloat_paths)
        if self.notify_telegram:
            result["notifyTelegram"] = True
        return result


@dataclass(frozen=True)
class ExecutionOptions:
    target: str = "github-auto"
    estimated_workspace_bytes: int | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "ExecutionOptions":
        data = payload or {}
        target = str(data.get("target") or "github-auto").strip().casefold()
        if target not in EXECUTION_TARGETS:
            raise RecipeValidationError(f"Unsupported execution target: {target}")
        estimate = data.get("estimatedWorkspaceBytes")
        parsed = int(estimate) if estimate is not None else None
        if parsed is not None and parsed <= 0:
            raise RecipeValidationError("Estimated workspace size must be positive")
        return cls(target=target, estimated_workspace_bytes=parsed)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"target": self.target}
        if self.estimated_workspace_bytes is not None:
            result["estimatedWorkspaceBytes"] = self.estimated_workspace_bytes
        return result


@dataclass(frozen=True)
class StorageOptions:
    remote: str = "wukong-gdrive"
    publish_artifact: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "StorageOptions":
        data = payload or {}
        remote = str(data.get("remote") or "wukong-gdrive").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", remote):
            raise RecipeValidationError("Storage remote name is invalid")
        return cls(remote=remote, publish_artifact=_boolean(data, "publishArtifact", True))

    def to_dict(self) -> dict[str, Any]:
        return {"remote": self.remote, "publishArtifact": self.publish_artifact}


@dataclass(frozen=True)
class BuildRecipe:
    task: str
    device: str
    source: SourceSpec
    build: BuildOptions = field(default_factory=BuildOptions)
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    storage: StorageOptions = field(default_factory=StorageOptions)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BuildRecipe":
        if not isinstance(payload, Mapping):
            raise RecipeValidationError("Build recipe must be an object")
        if _contains_secret_key(payload):
            raise RecipeValidationError("Build recipes must not contain secrets or credentials")
        version = int(payload.get("schemaVersion", SCHEMA_VERSION))
        if version != SCHEMA_VERSION:
            raise RecipeValidationError(f"Unsupported build recipe schema version: {version}")
        task = str(payload.get("task") or "").strip().casefold()
        if task not in TASKS:
            raise RecipeValidationError(f"Unsupported task: {task or '<empty>'}")
        device = str(payload.get("device") or "").strip()
        if not device or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", device):
            raise RecipeValidationError("Device identifier is required and must be path-safe")
        source_payload = payload.get("source")
        if not isinstance(source_payload, Mapping):
            raise RecipeValidationError("ROM source is required")
        return cls(
            task=task,
            device=device,
            source=SourceSpec.from_dict(source_payload),
            build=BuildOptions.from_dict(payload.get("build") if isinstance(payload.get("build"), Mapping) else None),
            execution=ExecutionOptions.from_dict(
                payload.get("execution") if isinstance(payload.get("execution"), Mapping) else None
            ),
            storage=StorageOptions.from_dict(
                payload.get("storage") if isinstance(payload.get("storage"), Mapping) else None
            ),
            schema_version=version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "task": self.task,
            "device": self.device,
            "source": self.source.to_dict(),
            "build": self.build.to_dict(),
            "execution": self.execution.to_dict(),
            "storage": self.storage.to_dict(),
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()

    @property
    def estimated_workspace_bytes(self) -> int:
        if self.execution.estimated_workspace_bytes:
            return self.execution.estimated_workspace_bytes
        source_size = self.source.size_bytes or 3 * 1024**3
        if self.task != "build":
            return source_size * 2
        return source_size * 5 + 4 * 1024**3

    def to_legacy_spec(self, *, local_rom_path: str | None = None) -> dict[str, Any]:
        steps = list(self.build.enabled_steps)
        if self.task == "build" and not self.build.package:
            steps = [step for step in steps if step != "package_zip"]
        result: dict[str, Any] = {
            "romPath": local_rom_path or self.source.uri,
            "modNames": list(self.build.mods),
            "modVersion": self.build.mod_version,
            "preset": self.build.preset,
            "enabledSteps": steps,
            "notifyTelegram": self.build.notify_telegram,
            "romSha256": self.source.sha256,
        }
        if self.build.debloat_paths is not None:
            result["debloatPaths"] = list(self.build.debloat_paths)
        return result


@dataclass(frozen=True)
class ArtifactRecord:
    name: str
    uri: str
    sha256: str
    size_bytes: int
    public_url: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRecord":
        return cls(
            name=str(payload.get("name") or ""),
            uri=str(payload.get("uri") or ""),
            sha256=str(payload.get("sha256") or ""),
            size_bytes=int(payload.get("size_bytes", payload.get("sizeBytes", 0))),
            public_url=(str(payload.get("public_url", payload.get("publicUrl")) or "") or None),
        )


@dataclass
class JobManifest:
    job_id: str
    owner: Identity
    recipe_digest: str
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    progress: float = 0.0
    runner: str | None = None
    external_run_id: int | None = None
    checkpoint: str | None = None
    checkpoint_at: str | None = None
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    finished_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobManifest":
        owner = payload.get("owner") if isinstance(payload.get("owner"), Mapping) else {}
        return cls(
            job_id=str(payload.get("job_id", payload.get("jobId")) or ""),
            owner=Identity(
                channel=str(owner.get("channel") or "unknown"),
                subject=str(owner.get("subject") or "unknown"),
                role=str(owner.get("role") or "user"),
            ),
            recipe_digest=str(payload.get("recipe_digest", payload.get("recipeDigest")) or ""),
            status=JobStatus(str(payload.get("status") or JobStatus.QUEUED.value)),
            stage=(str(payload.get("stage") or "") or None),
            progress=float(payload.get("progress") or 0),
            runner=(str(payload.get("runner") or "") or None),
            external_run_id=(
                int(payload.get("external_run_id", payload.get("externalRunId")))
                if payload.get("external_run_id", payload.get("externalRunId")) is not None
                else None
            ),
            checkpoint=(str(payload.get("checkpoint") or "") or None),
            checkpoint_at=(str(payload.get("checkpoint_at", payload.get("checkpointAt")) or "") or None),
            artifacts=[
                ArtifactRecord.from_dict(item)
                for item in payload.get("artifacts", [])
                if isinstance(item, Mapping)
            ],
            error=(str(payload.get("error") or "") or None),
            created_at=str(payload.get("created_at", payload.get("createdAt")) or utc_now()),
            updated_at=str(payload.get("updated_at", payload.get("updatedAt")) or utc_now()),
            finished_at=(str(payload.get("finished_at", payload.get("finishedAt")) or "") or None),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["owner"] = asdict(self.owner)
        result["status"] = self.status.value
        result["artifacts"] = [asdict(artifact) for artifact in self.artifacts]
        return result

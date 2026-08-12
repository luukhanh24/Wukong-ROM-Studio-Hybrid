from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import ArtifactRecord
from .security import validate_http_url


CHUNK_SIZE = 4 * 1024 * 1024


class SourceError(RuntimeError):
    pass


class SourceIntegrityError(SourceError):
    pass


@dataclass(frozen=True)
class MaterializedSource:
    path: Path
    sha256: str
    size_bytes: int


class SourceAdapter(Protocol):
    def materialize(self, uri: str, target: Path, expected_sha256: str | None) -> MaterializedSource: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalize_materialized(target: Path, expected_sha256: str | None) -> MaterializedSource:
    actual = sha256_file(target)
    if expected_sha256 and actual.casefold() != expected_sha256.casefold():
        target.unlink(missing_ok=True)
        raise SourceIntegrityError(
            f"ROM checksum mismatch: expected {expected_sha256.casefold()}, got {actual}"
        )
    return MaterializedSource(target, actual, target.stat().st_size)


class LocalSourceAdapter:
    def materialize(self, uri: str, target: Path, expected_sha256: str | None = None) -> MaterializedSource:
        source = Path(uri).expanduser().resolve()
        if not source.is_file():
            raise SourceError(f"Local ROM source does not exist: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target.resolve():
            temporary = target.with_suffix(target.suffix + ".partial")
            temporary.unlink(missing_ok=True)
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return _finalize_materialized(target, expected_sha256)


class HttpSourceAdapter:
    def __init__(self, *, attempts: int = 3, timeout: int = 60) -> None:
        self.attempts = max(1, attempts)
        self.timeout = timeout

    def materialize(self, uri: str, target: Path, expected_sha256: str | None = None) -> MaterializedSource:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        opener = build_opener(_SafeRedirectHandler())
        for attempt in range(1, self.attempts + 1):
            try:
                validate_http_url(uri, resolve_dns=True)
                offset = temporary.stat().st_size if temporary.is_file() else 0
                headers = {"User-Agent": "Wukong-ROM-Studio/1"}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                request = Request(uri, headers=headers)
                with opener.open(request, timeout=self.timeout) as response:
                    validate_http_url(response.geturl(), resolve_dns=True)
                    append = offset > 0 and getattr(response, "status", response.getcode()) == 206
                    with temporary.open("ab" if append else "wb") as handle:
                        shutil.copyfileobj(response, handle, CHUNK_SIZE)
                os.replace(temporary, target)
                return _finalize_materialized(target, expected_sha256)
            except (HTTPError, URLError, TimeoutError, OSError, SourceError) as exc:
                if attempt >= self.attempts:
                    temporary.unlink(missing_ok=True)
                    raise SourceError(f"ROM download failed after {self.attempts} attempts: {exc}") from exc
                time.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        validate_http_url(newurl, resolve_dns=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


RunCommand = Callable[..., str]


def _run_text(args: list[str], **kwargs: object) -> str:
    completed = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )
    return completed.stdout


class RcloneSourceAdapter:
    def __init__(self, *, run_command: RunCommand = _run_text, config_path: Path | None = None) -> None:
        self.run_command = run_command
        self.config_path = config_path

    def materialize(self, uri: str, target: Path, expected_sha256: str | None = None) -> MaterializedSource:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        temporary.unlink(missing_ok=True)
        args = ["rclone", "copyto", uri, str(temporary), "--retries", "3", "--low-level-retries", "10"]
        if self.config_path:
            args.extend(["--config", str(self.config_path)])
        try:
            self.run_command(args)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return _finalize_materialized(target, expected_sha256)


class RcloneStorageAdapter:
    def __init__(
        self,
        *,
        remote: str = "wukong-gdrive",
        root: str = "WukongROM",
        run_command: RunCommand = _run_text,
        config_path: Path | None = None,
    ) -> None:
        self.remote = remote.rstrip(":")
        self.root = root.strip("/\\")
        self.run_command = run_command
        self.config_path = config_path

    def _args(self, *values: str) -> list[str]:
        args = ["rclone", *values]
        if self.config_path:
            args.extend(["--config", str(self.config_path)])
        return args

    def remote_uri(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized or ".." in PurePosixPath(normalized).parts:
            raise ValueError("Cloud storage path is empty or contains path traversal")
        return f"{self.remote}:{self.root}/{normalized}"

    def copy_file(self, source: Path, relative_path: str) -> str:
        uri = self.remote_uri(relative_path)
        self.run_command(self._args("copyto", str(source), uri, "--retries", "3"))
        return uri

    def copy_tree(self, source: Path, relative_path: str) -> str:
        source = source.resolve()
        if not source.is_dir():
            raise FileNotFoundError(source)
        uri = self.remote_uri(relative_path)
        self.run_command(self._args("copy", str(source), uri, "--retries", "3"))
        return uri

    def sync_tree(self, source: Path, relative_path: str) -> str:
        source = source.resolve()
        if not source.is_dir():
            raise FileNotFoundError(source)
        uri = self.remote_uri(relative_path)
        self.run_command(self._args("sync", str(source), uri, "--retries", "3"))
        return uri

    def restore_tree(self, uri: str, destination: Path) -> Path:
        destination = destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        self.run_command(self._args("copy", uri, str(destination), "--retries", "3"))
        return destination

    def publish_artifact(self, artifact: Path, *, device: str, build: str) -> ArtifactRecord:
        artifact = artifact.resolve()
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        digest = sha256_file(artifact)
        record = {
            "schemaVersion": 1,
            "name": artifact.name,
            "sha256": digest,
            "sizeBytes": artifact.stat().st_size,
        }
        metadata_path = artifact.with_name(artifact.name + ".metadata.json")
        metadata_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        relative = f"artifacts/{device}/{build}/{artifact.name}"
        uri = self.copy_file(artifact, relative)
        self.copy_file(metadata_path, relative + ".metadata.json")
        public_url = self.run_command(self._args("link", uri)).strip() or None
        return ArtifactRecord(
            name=artifact.name,
            uri=uri,
            sha256=digest,
            size_bytes=artifact.stat().st_size,
            public_url=public_url,
        )

    def store_source(self, source: Path, *, device: str, digest: str | None = None) -> ArtifactRecord:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        file_digest = sha256_file(source)
        actual_digest = digest or file_digest
        if digest and actual_digest.casefold() != file_digest.casefold():
            raise SourceIntegrityError("Source checksum changed before cloud upload")
        relative = f"sources/{device}/{actual_digest}/{source.name}"
        uri = self.copy_file(source, relative)
        metadata = {
            "schemaVersion": 1,
            "name": source.name,
            "sha256": actual_digest,
            "sizeBytes": source.stat().st_size,
        }
        with tempfile.TemporaryDirectory(prefix="wukong-source-metadata-") as root:
            metadata_path = Path(root) / (source.name + ".metadata.json")
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.copy_file(metadata_path, relative + ".metadata.json")
        return ArtifactRecord(source.name, uri, actual_digest, source.stat().st_size)

    def list_library(self, relative_path: str = "", *, max_entries: int = 500) -> list[dict[str, object]]:
        uri = self.remote_uri(relative_path)
        output = self.run_command(
            self._args(
                "lsjson",
                uri,
                "--recursive",
                "--files-only",
                "--max-depth",
                "8",
            )
        )
        entries = json.loads(output or "[]")
        result: list[dict[str, object]] = []
        for item in entries[: max(1, min(max_entries, 2000))]:
            if not isinstance(item, dict):
                continue
            result.append(
                {
                    "path": str(item.get("Path") or item.get("Name") or ""),
                    "name": str(item.get("Name") or ""),
                    "sizeBytes": int(item.get("Size") or 0),
                    "modifiedAt": item.get("ModTime"),
                    "mimeType": item.get("MimeType"),
                }
            )
        return result


def source_adapter_for(kind: str, *, config_path: Path | None = None) -> SourceAdapter:
    if kind == "local":
        return LocalSourceAdapter()
    if kind in {"http", "https"}:
        return HttpSourceAdapter()
    if kind == "rclone":
        return RcloneSourceAdapter(config_path=config_path)
    raise SourceError(f"No source adapter is available for {kind}")

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import ArtifactRecord
from .security import validate_http_url


CHUNK_SIZE = 4 * 1024 * 1024
RESOLVER_SNIFF_SIZE = 64 * 1024
MAX_RESOLVER_BYTES = 1024 * 1024
DEFAULT_PARALLEL_THRESHOLD_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_CONNECTIONS = 16
OPLUS_RESOLVER_USER_AGENT = "okhttp/3.12.12"
OPLUS_RESOLVER_USER_ID = "oplus-ota|16002018"


class SourceError(RuntimeError):
    pass


class SourceIntegrityError(SourceError):
    pass


class SourceResolutionError(SourceError):
    pass


class RangeProtocolError(SourceError):
    pass


@dataclass(frozen=True)
class MaterializedSource:
    path: Path
    sha256: str
    size_bytes: int


class SourceAdapter(Protocol):
    def materialize(self, uri: str, target: Path, expected_sha256: str | None) -> MaterializedSource: ...


class HttpOpener(Protocol):
    def open(self, request: Request, *, timeout: int) -> Any: ...


HttpOpenerFactory = Callable[[], HttpOpener]


@dataclass(frozen=True)
class _ByteRange:
    start: int
    end: int
    path: Path

    @property
    def size(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class _HttpSourceIdentity:
    url: str
    size_bytes: int
    etag: str | None = None
    last_modified: str | None = None

    @property
    def validator(self) -> str | None:
        if self.etag and not self.etag.casefold().startswith("w/"):
            return self.etag
        return self.last_modified

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "sizeBytes": self.size_bytes,
            "etag": self.etag,
            "lastModified": self.last_modified,
        }

    @classmethod
    def from_dict(cls, value: object) -> "_HttpSourceIdentity | None":
        if not isinstance(value, dict):
            return None
        try:
            url = value["url"]
            size_bytes = value["sizeBytes"]
            etag = value.get("etag")
            last_modified = value.get("lastModified")
            if not isinstance(url, str) or not isinstance(size_bytes, int):
                return None
            if etag is not None and not isinstance(etag, str):
                return None
            if last_modified is not None and not isinstance(last_modified, str):
                return None
            return cls(url, size_bytes, etag, last_modified)
        except KeyError:
            return None


@dataclass(frozen=True)
class _ParallelTransfer:
    url: str
    identity: _HttpSourceIdentity


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
    def __init__(
        self,
        *,
        attempts: int = 3,
        timeout: int = 60,
        opener: HttpOpener | None = None,
        opener_factory: HttpOpenerFactory | None = None,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        parallel_threshold_bytes: int = DEFAULT_PARALLEL_THRESHOLD_BYTES,
    ) -> None:
        self.attempts = max(1, attempts)
        self.timeout = timeout
        default_factory: HttpOpenerFactory = lambda: build_opener(_SafeRedirectHandler())
        self.opener = opener or default_factory()
        self.opener_factory = opener_factory or (default_factory if opener is None else None)
        self.max_connections = max(1, min(max_connections, DEFAULT_MAX_CONNECTIONS))
        self.parallel_threshold_bytes = max(1, parallel_threshold_bytes)

    def materialize(self, uri: str, target: Path, expected_sha256: str | None = None) -> MaterializedSource:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        for attempt in range(1, self.attempts + 1):
            try:
                self._download(uri, temporary)
                os.replace(temporary, target)
                return _finalize_materialized(target, expected_sha256)
            except SourceResolutionError:
                temporary.unlink(missing_ok=True)
                self._cleanup_range_files(temporary)
                self._checkpoint_path(temporary).unlink(missing_ok=True)
                raise
            except (HTTPError, URLError, TimeoutError, OSError, SourceError) as exc:
                if attempt >= self.attempts:
                    raise SourceError(f"ROM download failed after {self.attempts} attempts: {exc}") from exc
                time.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")

    def _download(self, uri: str, temporary: Path) -> None:
        validate_http_url(uri, resolve_dns=True)

        is_oplus_resolver = self._is_oplus_resolver_url(uri)
        offset = temporary.stat().st_size if temporary.is_file() else 0
        headers = self._request_headers(uri)
        if offset and not is_oplus_resolver:
            headers["Range"] = f"bytes={offset}-"
        request = Request(uri, headers=headers)
        parallel_source: _ParallelTransfer | None = None
        with self.opener.open(request, timeout=self.timeout) as response:
            final_url = response.geturl()
            validate_http_url(final_url, resolve_dns=True)
            prefix = response.read(RESOLVER_SNIFF_SIZE)
            content_type = str(response.headers.get("Content-Type", "")).casefold()
            if self._looks_like_json(content_type, prefix):
                raw_payload = prefix + response.read(MAX_RESOLVER_BYTES - len(prefix) + 1)
                if len(raw_payload) > MAX_RESOLVER_BYTES:
                    raise SourceResolutionError(
                        f"OTA resolver response exceeds {MAX_RESOLVER_BYTES} bytes"
                    )
                encoding = str(response.headers.get("Content-Encoding", "")).casefold()
                payload = self._decode_resolver_payload(raw_payload, encoding)
                self._raise_resolver_error(payload)
            if is_oplus_resolver and final_url == uri:
                raise SourceResolutionError(
                    "OPlus OTA resolver did not redirect to a ROM download"
                )

            total_size = self._parallel_total_size(response) if is_oplus_resolver else None
            identity = (
                self._parallel_identity(response, final_url, total_size)
                if total_size is not None
                else None
            )
            if (
                total_size is not None
                and identity is not None
                and identity.validator is not None
                and self._probe_parallel(final_url, total_size)
            ):
                self._prepare_parallel_checkpoint(temporary, identity)
                parallel_source = _ParallelTransfer(final_url, identity)
            else:
                self._cleanup_range_files(temporary)
                self._checkpoint_path(temporary).unlink(missing_ok=True)
                status = getattr(response, "status", response.getcode())
                append = offset > 0 and status == 206
                with temporary.open("ab" if append else "wb") as handle:
                    handle.write(prefix)
                    shutil.copyfileobj(response, handle, CHUNK_SIZE)

        if parallel_source is not None:
            try:
                self._download_parallel(parallel_source, temporary)
            except RangeProtocolError:
                temporary.unlink(missing_ok=True)
                self._cleanup_range_files(temporary)
                self._checkpoint_path(temporary).unlink(missing_ok=True)
                self._download_sequential(parallel_source.url, temporary)

    def _parallel_total_size(self, response: Any) -> int | None:
        if self.opener_factory is None or self.max_connections < 2:
            return None
        if str(response.headers.get("Accept-Ranges", "")).strip().casefold() != "bytes":
            return None
        try:
            total_size = int(response.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            return None
        if total_size < self.parallel_threshold_bytes:
            return None
        return total_size

    def _probe_parallel(self, final_url: str, total_size: int) -> bool:
        if self.opener_factory is None:
            return False
        request = Request(
            final_url,
            headers={
                "User-Agent": "Wukong-ROM-Studio/1",
                "Accept-Encoding": "identity",
                "Range": "bytes=0-0",
            },
        )
        try:
            with self.opener_factory().open(request, timeout=self.timeout) as response:
                validate_http_url(response.geturl(), resolve_dns=True)
                status = getattr(response, "status", response.getcode())
                if status != 206:
                    return False
                start, end, response_total = self._parse_content_range(
                    str(response.headers.get("Content-Range", ""))
                )
                body = response.read(2)
                return start == 0 and end == 0 and response_total == total_size and len(body) == 1
        except (HTTPError, URLError, TimeoutError, OSError, SourceError):
            return False

    @staticmethod
    def _parallel_identity(
        response: Any,
        final_url: str,
        total_size: int,
    ) -> _HttpSourceIdentity:
        parsed = urlparse(final_url)
        stable_url = parsed._replace(query="", fragment="").geturl()
        return _HttpSourceIdentity(
            stable_url,
            total_size,
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
        )

    def _prepare_parallel_checkpoint(
        self,
        temporary: Path,
        identity: _HttpSourceIdentity,
    ) -> None:
        checkpoint = self._checkpoint_path(temporary)
        existing: _HttpSourceIdentity | None = None
        if checkpoint.is_file():
            try:
                loaded = json.loads(checkpoint.read_text(encoding="utf-8"))
                existing = _HttpSourceIdentity.from_dict(loaded)
            except (OSError, json.JSONDecodeError):
                existing = None
        has_partial_state = temporary.is_file() or any(
            temporary.parent.glob(temporary.name + ".range-*")
        )
        if has_partial_state and existing != identity:
            temporary.unlink(missing_ok=True)
            self._cleanup_range_files(temporary)

        staged = checkpoint.with_suffix(checkpoint.suffix + ".partial")
        staged.write_text(json.dumps(identity.to_dict(), sort_keys=True), encoding="utf-8")
        os.replace(staged, checkpoint)

    def _download_parallel(
        self,
        transfer: _ParallelTransfer,
        temporary: Path,
    ) -> None:
        final_url = transfer.url
        identity = transfer.identity
        total_size = identity.size_bytes
        offset = temporary.stat().st_size if temporary.is_file() else 0
        if offset > total_size:
            temporary.unlink(missing_ok=True)
            offset = 0
        if offset == total_size:
            self._cleanup_range_files(temporary)
            self._checkpoint_path(temporary).unlink(missing_ok=True)
            return

        ranges = self._build_ranges(temporary, offset, total_size)
        with ThreadPoolExecutor(max_workers=len(ranges), thread_name_prefix="wukong-http") as pool:
            list(
                pool.map(
                    lambda item: self._download_range(
                        final_url,
                        total_size,
                        identity,
                        item,
                    ),
                    ranges,
                )
            )
        self._assemble_ranges(temporary, total_size, ranges)

    def _build_ranges(self, temporary: Path, offset: int, total_size: int) -> list[_ByteRange]:
        remaining = total_size - offset
        connection_count = min(self.max_connections, remaining)
        chunk_size = (remaining + connection_count - 1) // connection_count
        ranges: list[_ByteRange] = []
        for index in range(connection_count):
            start = offset + index * chunk_size
            if start >= total_size:
                break
            end = min(total_size - 1, start + chunk_size - 1)
            path = temporary.with_name(f"{temporary.name}.range-{start}-{end}")
            ranges.append(_ByteRange(start, end, path))
        return ranges

    def _download_range(
        self,
        final_url: str,
        total_size: int,
        identity: _HttpSourceIdentity,
        item: _ByteRange,
    ) -> None:
        if self.opener_factory is None:
            raise SourceError("Parallel HTTP opener is unavailable")
        existing = item.path.stat().st_size if item.path.is_file() else 0
        if existing > item.size:
            item.path.unlink(missing_ok=True)
            existing = 0

        while existing < item.size:
            request_start = item.start + existing
            headers = {
                "User-Agent": "Wukong-ROM-Studio/1",
                "Accept-Encoding": "identity",
                "Range": f"bytes={request_start}-{item.end}",
                "If-Range": identity.validator or "",
            }
            request = Request(final_url, headers=headers)
            with self.opener_factory().open(request, timeout=self.timeout) as response:
                validate_http_url(response.geturl(), resolve_dns=True)
                status = getattr(response, "status", response.getcode())
                if status != 206:
                    raise RangeProtocolError(
                        f"ROM range download expected HTTP 206, got {status}"
                    )
                response_start, response_end, response_total = self._parse_content_range(
                    str(response.headers.get("Content-Range", ""))
                )
                if (
                    response_start != request_start
                    or response_end > item.end
                    or response_total != total_size
                ):
                    raise RangeProtocolError(
                        "ROM range response does not match the requested bytes"
                    )
                expected_etag = identity.etag
                response_etag = response.headers.get("ETag")
                if expected_etag and response_etag and expected_etag != response_etag:
                    raise RangeProtocolError("ROM range response ETag changed during download")
                expected_modified = identity.last_modified
                response_modified = response.headers.get("Last-Modified")
                if (
                    not expected_etag
                    and expected_modified
                    and response_modified
                    and expected_modified != response_modified
                ):
                    raise RangeProtocolError(
                        "ROM range response Last-Modified changed during download"
                    )
                before = item.path.stat().st_size if item.path.is_file() else 0
                with item.path.open("ab") as handle:
                    shutil.copyfileobj(response, handle, CHUNK_SIZE)
                existing = item.path.stat().st_size
                if existing - before != response_end - response_start + 1:
                    raise RangeProtocolError(
                        "ROM range response size does not match Content-Range"
                    )

    def _download_sequential(self, uri: str, temporary: Path) -> None:
        if self.opener_factory is None:
            raise SourceError("Sequential HTTP fallback opener is unavailable")
        request = Request(uri, headers={"User-Agent": "Wukong-ROM-Studio/1"})
        with self.opener_factory().open(request, timeout=self.timeout) as response:
            validate_http_url(response.geturl(), resolve_dns=True)
            status = getattr(response, "status", response.getcode())
            if status < 200 or status >= 300:
                raise SourceError(f"Sequential ROM fallback returned HTTP {status}")
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle, CHUNK_SIZE)

    @staticmethod
    def _parse_content_range(value: str) -> tuple[int, int, int]:
        try:
            unit, bounds = value.strip().split(None, 1)
            byte_range, total = bounds.split("/", 1)
            start, end = byte_range.split("-", 1)
            if unit.casefold() != "bytes":
                raise ValueError
            return int(start), int(end), int(total)
        except (TypeError, ValueError) as exc:
            raise RangeProtocolError(f"Invalid ROM Content-Range header: {value!r}") from exc

    def _assemble_ranges(
        self,
        temporary: Path,
        total_size: int,
        ranges: list[_ByteRange],
    ) -> None:
        assembled = temporary.with_name(temporary.name + ".assembled")
        assembled.unlink(missing_ok=True)
        try:
            with assembled.open("wb") as output:
                if temporary.is_file():
                    with temporary.open("rb") as prefix:
                        shutil.copyfileobj(prefix, output, CHUNK_SIZE)
                for item in ranges:
                    if not item.path.is_file() or item.path.stat().st_size != item.size:
                        raise SourceError(f"ROM range checkpoint is incomplete: {item.start}-{item.end}")
                    with item.path.open("rb") as segment:
                        shutil.copyfileobj(segment, output, CHUNK_SIZE)
            if assembled.stat().st_size != total_size:
                raise SourceError(
                    f"Assembled ROM size mismatch: expected {total_size}, got {assembled.stat().st_size}"
                )
            os.replace(assembled, temporary)
            self._cleanup_range_files(temporary)
            self._checkpoint_path(temporary).unlink(missing_ok=True)
        finally:
            assembled.unlink(missing_ok=True)

    @staticmethod
    def _cleanup_range_files(temporary: Path) -> None:
        for path in temporary.parent.glob(temporary.name + ".range-*"):
            if path.is_file():
                path.unlink(missing_ok=True)

    @staticmethod
    def _checkpoint_path(temporary: Path) -> Path:
        return temporary.with_name(temporary.name + ".http.json")

    @staticmethod
    def _looks_like_json(content_type: str, prefix: bytes) -> bool:
        media_type = content_type.split(";", 1)[0].strip()
        return (
            media_type in {"application/json", "text/json"}
            or media_type.endswith("+json")
            or prefix.lstrip().startswith((b"{", b"["))
        )

    @staticmethod
    def _request_headers(uri: str) -> dict[str, str]:
        if HttpSourceAdapter._is_oplus_resolver_url(uri):
            return {
                "User-Agent": OPLUS_RESOLVER_USER_AGENT,
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "Keep-Alive",
                "Cache-Control": "no-cache",
                "userId": OPLUS_RESOLVER_USER_ID,
            }
        return {"User-Agent": "Wukong-ROM-Studio/1"}

    @staticmethod
    def _is_oplus_resolver_url(uri: str) -> bool:
        return urlparse(uri).path.rstrip("/").casefold().endswith("/downloadcheck")

    @staticmethod
    def _decode_resolver_payload(payload: bytes, encoding: str) -> bytes:
        if encoding in {"gzip", "x-gzip"}:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            decoder = zlib.decompressobj()
        else:
            return payload
        try:
            decoded = decoder.decompress(payload, MAX_RESOLVER_BYTES + 1)
        except zlib.error as exc:
            raise SourceResolutionError(f"OTA resolver returned invalid {encoding} data") from exc
        if len(decoded) > MAX_RESOLVER_BYTES or decoder.unconsumed_tail:
            raise SourceResolutionError(
                f"OTA resolver response exceeds {MAX_RESOLVER_BYTES} bytes after decompression"
            )
        return decoded

    @staticmethod
    def _raise_resolver_error(payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceResolutionError(f"OTA resolver returned invalid JSON: {exc}") from exc

        if isinstance(data, dict):
            diagnostics = HttpSourceAdapter._resolver_diagnostics(data)
            if data.get("body") is None and diagnostics:
                raise SourceResolutionError(
                    f"OTA resolver rejected request: {diagnostics}"
                )
        details = HttpSourceAdapter._resolver_diagnostics(data)
        suffix = f" ({details})" if details else ""
        raise SourceResolutionError(
            "OTA resolver returned JSON instead of redirecting to a ROM download" + suffix
        )

    @staticmethod
    def _resolver_diagnostics(value: object) -> str:
        if not isinstance(value, dict):
            return ""
        code = value.get("responseCode")
        message = value.get("errMsg")
        if code is None and message is None:
            return ""
        return (
            f"responseCode={code if code is not None else 'unknown'}, "
            f"errMsg={message if message is not None else 'unknown'}"
        )

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

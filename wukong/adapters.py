from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

from .models import ArtifactRecord
from .security import validate_http_url


CHUNK_SIZE = 4 * 1024 * 1024
RESOLVER_SNIFF_SIZE = 64 * 1024
MAX_RESOLVER_BYTES = 1024 * 1024
MAX_CATALOG_PAGE_BYTES = 2 * 1024 * 1024
DEFAULT_PARALLEL_THRESHOLD_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_CONNECTIONS = 16
OPLUS_RESOLVER_USER_AGENT = "okhttp/3.12.12"
OPLUS_RESOLVER_USER_ID = "oplus-ota|16002018"


class SourceError(RuntimeError):
    pass


class SourceIntegrityError(SourceError):
    pass


class MirrorCommandError(RuntimeError):
    """A credential-free identifier for the failed WebDAV operation."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class SourceResolutionError(SourceError):
    pass


class RangeProtocolError(SourceError):
    pass


class _DanielOtaPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.result: dict[str, str] = {}
        self.metadata: dict[str, str] = {}
        self._capture: str | None = None
        self._capture_depth = 0
        self._text: list[str] = []
        self._version_parts: list[str] = []
        self._detail_label = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        classes = {item.casefold() for item in values.get("class", "").split()}
        normalized_tag = tag.casefold()
        if normalized_tag == "div" and values.get("id") == "resultBox":
            self.result = {
                "url": unescape(values.get("data-url", "")).strip(),
                "key": values.get("data-ota-key", "").strip(),
                "csrf": values.get("data-csrf", "").strip(),
            }
        if self._capture is not None:
            self._capture_depth += 1
            return
        capture = None
        if normalized_tag == "p" and "ota-version-name" in classes:
            capture = "version"
        elif normalized_tag == "span" and "ota-chip" in classes:
            capture = "chip"
        elif normalized_tag == "h3" and "ota-package-title" in classes:
            capture = "product-label"
        elif normalized_tag == "dt":
            capture = "detail-label"
        elif normalized_tag == "dd":
            capture = "detail-value"
        if capture:
            self._capture = capture
            self._capture_depth = 1
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._text.append(data)

    def handle_endtag(self, _tag: str) -> None:
        if self._capture is None:
            return
        self._capture_depth -= 1
        if self._capture_depth > 0:
            return
        capture = self._capture
        value = " ".join("".join(self._text).split())
        self._capture = None
        self._text = []
        if capture == "version":
            self.metadata["version"] = value.replace(" ", "")
        elif capture == "chip" and value.casefold().startswith("patch:"):
            self.metadata["securityPatch"] = value.split(":", 1)[1].strip()
        elif capture == "product-label" and value:
            self.metadata["productLabel"] = value
        elif capture == "detail-label":
            self._detail_label = value
        elif capture == "detail-value" and self._detail_label.casefold() == "ota build":
            self.metadata["otaBuild"] = value


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
        if target.is_file() and expected_sha256:
            cached_sha256 = sha256_file(target)
            if cached_sha256 == expected_sha256.casefold():
                return MaterializedSource(target, cached_sha256, target.stat().st_size)
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
        default_factory: HttpOpenerFactory = lambda: build_opener(
            _SafeRedirectHandler(), HTTPCookieProcessor(CookieJar())
        )
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

        is_catalog_page = self._is_daniel_ota_page_url(uri)
        if is_catalog_page:
            uri = self._resolve_daniel_ota_page(uri)
            validate_http_url(uri, resolve_dns=True)

        is_oplus_resolver = self._is_oplus_resolver_url(uri)
        parallel_candidate = (
            is_catalog_page
            or is_oplus_resolver
            or self._is_oplus_download_host(uri)
        )
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

            total_size = (
                self._parallel_total_size(response)
                if parallel_candidate
                else None
            )
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
                before = temporary.stat().st_size if append and temporary.is_file() else 0
                with temporary.open("ab" if append else "wb") as handle:
                    handle.write(prefix)
                    shutil.copyfileobj(response, handle, CHUNK_SIZE)
                written = temporary.stat().st_size - before
                self._validate_sequential_response(
                    response,
                    status=status,
                    requested_offset=offset,
                    appended=append,
                    written=written,
                    materialized_size=temporary.stat().st_size,
                )

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
            size = temporary.stat().st_size
            self._validate_sequential_response(
                response,
                status=status,
                requested_offset=0,
                appended=False,
                written=size,
                materialized_size=size,
            )

    def _validate_sequential_response(
        self,
        response: Any,
        *,
        status: int,
        requested_offset: int,
        appended: bool,
        written: int,
        materialized_size: int,
    ) -> None:
        raw_length = response.headers.get("Content-Length")
        if raw_length not in {None, ""}:
            try:
                declared_length = int(raw_length)
            except (TypeError, ValueError) as exc:
                raise RangeProtocolError(
                    f"Invalid ROM Content-Length header: {raw_length!r}"
                ) from exc
            if declared_length < 0 or written != declared_length:
                raise SourceError(
                    f"ROM response ended early: expected {declared_length} bytes, got {written}"
                )
        raw_content_range = response.headers.get("Content-Range")
        if raw_content_range in {None, ""}:
            if status == 206:
                raise RangeProtocolError("ROM partial response omitted Content-Range")
            return
        start, end, total = self._parse_content_range(
            str(raw_content_range)
        )
        expected_start = requested_offset if appended else 0
        if start != expected_start or written != end - start + 1:
            raise RangeProtocolError("ROM partial response does not match the requested bytes")
        if materialized_size != total:
            raise SourceError(
                f"ROM partial response is incomplete: expected {total} bytes, got {materialized_size}"
            )
        if status != 206:
            raise RangeProtocolError("ROM server returned Content-Range without HTTP 206")

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
    def _is_oplus_download_host(uri: str) -> bool:
        host = (urlparse(uri).hostname or "").rstrip(".").casefold()
        return host.endswith((".allawnfs.com", ".allawntech.com"))

    @staticmethod
    def _is_daniel_ota_page_url(uri: str) -> bool:
        parsed = urlparse(uri)
        if (parsed.hostname or "").rstrip(".").casefold() != "roms.danielspringer.at":
            return False
        if parsed.path.rstrip("/").casefold() != "/index.php":
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        return query.get("view", [""])[0].casefold() == "ota" and bool(
            query.get("build", [""])[0].strip()
        )

    def _resolve_daniel_ota_page(self, uri: str) -> str:
        resolved, _metadata = self._resolve_daniel_ota_page_details(uri)
        return resolved

    def _resolve_daniel_ota_page_details(self, uri: str) -> tuple[str, dict[str, str]]:
        request = Request(
            uri,
            headers={
                "User-Agent": "Wukong-ROM-Studio/1.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Encoding": "identity",
            },
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            page_url = response.geturl()
            validate_http_url(page_url, resolve_dns=True)
            payload = response.read(MAX_CATALOG_PAGE_BYTES + 1)
        if len(payload) > MAX_CATALOG_PAGE_BYTES:
            raise SourceResolutionError("Daniel Springer OTA page exceeds the resolver limit")
        try:
            page = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SourceResolutionError("Daniel Springer OTA page is not valid UTF-8") from exc

        parser = _DanielOtaPageParser()
        parser.feed(page)
        page_metadata = dict(parser.metadata)
        resolved = parser.result.get("url", "")
        if resolved:
            validate_http_url(resolved, resolve_dns=True)
            return resolved, page_metadata

        ota_key = parser.result.get("key", "")
        csrf = parser.result.get("csrf", "")
        if not ota_key or not csrf:
            raise SourceResolutionError(
                "Daniel Springer OTA page does not contain resolver state; "
                "the build page may be invalid or unavailable"
            )
        endpoint = urljoin(page_url, "/index.php?view=ota&ota_action=resolve_json")
        validate_http_url(endpoint, resolve_dns=True)
        body = urlencode({"k": ota_key, "csrf": csrf}).encode("ascii")
        resolve_request = Request(
            endpoint,
            data=body,
            headers={
                "User-Agent": "Wukong-ROM-Studio/1.0",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://roms.danielspringer.at",
                "Referer": page_url,
            },
            method="POST",
        )
        with self.opener.open(resolve_request, timeout=self.timeout) as response:
            validate_http_url(response.geturl(), resolve_dns=True)
            raw = response.read(MAX_RESOLVER_BYTES + 1)
        if len(raw) > MAX_RESOLVER_BYTES:
            raise SourceResolutionError("Daniel Springer OTA resolver response is too large")
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceResolutionError("Daniel Springer OTA resolver returned invalid JSON") from exc
        resolved = str(data.get("url") or "") if isinstance(data, dict) else ""
        if not isinstance(data, dict) or data.get("ok") is not True or not resolved:
            message = str(data.get("message") or "OTA link could not be prepared") if isinstance(data, dict) else "OTA link could not be prepared"
            raise SourceResolutionError(f"Daniel Springer OTA resolver failed: {message}")
        validate_http_url(resolved, resolve_dns=True)
        return resolved, page_metadata

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
StreamCommand = Callable[[list[str], bytes | None], bytes]


class _HashingWriter:
    def __init__(self, destination: Any) -> None:
        self.destination = destination
        self.digest = hashlib.sha256()
        self.size_bytes = 0

    def write(self, payload: bytes) -> int:
        written = self.destination.write(payload)
        if written is None:
            written = len(payload)
        if written != len(payload):
            raise OSError("Checkpoint archive stream was only partially written")
        self.digest.update(payload)
        self.size_bytes += len(payload)
        return written


class _CountingWriter:
    def __init__(self) -> None:
        self.size_bytes = 0

    def write(self, payload: bytes) -> int:
        self.size_bytes += len(payload)
        return len(payload)


class _HashingReader:
    def __init__(self, source: Any) -> None:
        self.source = source
        self.digest = hashlib.sha256()
        self.size_bytes = 0

    def read(self, size: int = -1) -> bytes:
        payload = self.source.read(size)
        if payload:
            self.digest.update(payload)
            self.size_bytes += len(payload)
        return payload


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


def _parse_rclone_progress(line: str) -> dict[str, object] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    stats = payload.get("stats")
    if not isinstance(stats, Mapping):
        return None
    transfers = stats.get("transferring")
    active = transfers[0] if isinstance(transfers, list) and transfers and isinstance(transfers[0], Mapping) else {}
    transferred = int(active.get("bytes", stats.get("bytes", 0)) or 0)
    total = int(active.get("size", stats.get("totalBytes", 0)) or 0)
    speed = float(active.get("speed", stats.get("speed", 0)) or 0)
    eta_value = active.get("eta", stats.get("eta"))
    eta = float(eta_value) if isinstance(eta_value, (int, float)) else None
    return {
        "bytes": transferred,
        "totalBytes": total,
        "speedBytesPerSecond": speed,
        "etaSeconds": eta,
        "percent": min(100.0, max(0.0, transferred * 100.0 / total if total > 0 else 0.0)),
    }


def _run_rclone_copy_with_progress(
    args: list[str],
    progress_callback: Callable[[Mapping[str, object]], None],
) -> str:
    process = subprocess.Popen(
        [
            *args,
            "--use-json-log",
            "--stats", "500ms",
            "--stats-one-line",
            "--stats-log-level", "NOTICE",
            "--log-level", "NOTICE",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            output.append(line)
            progress = _parse_rclone_progress(line)
            if progress is not None:
                progress_callback(progress)
        return_code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        raise
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, args, output="".join(output))
    return "".join(output)


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
        webdav_url: str | None = None,
        run_command: RunCommand = _run_text,
        stream_command: StreamCommand | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.remote = remote.rstrip(":")
        self.root = root.strip("/\\")
        self.webdav_url = webdav_url.strip() if webdav_url else None
        self.run_command = run_command
        self.stream_command = stream_command
        self.config_path = config_path

    def _args(self, *values: str) -> list[str]:
        args = ["rclone", *values]
        if self.webdav_url:
            args.extend(["--webdav-url", self.webdav_url])
        if self.config_path:
            args.extend(["--config", str(self.config_path)])
        return args

    def remote_uri(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized or ".." in PurePosixPath(normalized).parts:
            raise ValueError("Cloud storage path is empty or contains path traversal")
        if self.root:
            return f"{self.remote}:{self.root}/{normalized}"
        return f"{self.remote}:{normalized}"

    def copy_file(
        self,
        source: Path,
        relative_path: str,
        *,
        timeout: float | None = None,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> str:
        uri = self.remote_uri(relative_path)
        options = {"timeout": timeout} if timeout is not None else {}
        args = self._args("copyto", str(source), uri, "--retries", "3")
        if progress_callback is not None and self.run_command is _run_text and timeout is None:
            _run_rclone_copy_with_progress(args, progress_callback)
        else:
            self.run_command(args, **options)
        return uri

    def make_dir(self, relative_path: str) -> str:
        uri = self.remote_uri(relative_path)
        self.run_command(self._args("mkdir", uri))
        return uri

    def stat_size(self, relative_path: str) -> int | None:
        uri = self.remote_uri(relative_path)
        try:
            payload = json.loads(self.run_command(self._args("lsjson", uri, "--stat")))
            size = payload.get("Size")
            return int(size) if isinstance(size, int) and size >= 0 else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError):
            return None

    def read_text(self, relative_path: str) -> str:
        return self.run_command(self._args("cat", self.remote_uri(relative_path)))

    def download_file(self, relative_path: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        self.run_command(
            self._args("copyto", self.remote_uri(relative_path), str(target), "--retries", "3")
        )

    def copy_remote(self, source_path: str, destination_path: str) -> str:
        destination = self.remote_uri(destination_path)
        self.run_command(
            self._args("copyto", self.remote_uri(source_path), destination, "--retries", "3")
        )
        return destination

    def remove_tree(self, relative_path: str) -> None:
        self.run_command(self._args("purge", self.remote_uri(relative_path)))

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
        self._validate_checkpoint_source(source)
        uri = self.remote_uri(f"{relative_path}/{uuid.uuid4().hex}.tar")
        staging_uri = uri + ".partial"
        metadata_uri = uri + ".metadata.json"
        staging_metadata_uri = metadata_uri + ".partial"

        def write_archive(output: Any) -> tuple[str, int]:
            writer = _HashingWriter(output)
            self._write_checkpoint_archive(source, writer)
            return writer.digest.hexdigest(), writer.size_bytes

        counter = _CountingWriter()
        self._write_checkpoint_archive(source, counter)
        archive_size = counter.size_bytes
        try:
            digest, size_bytes = self._upload_stream(
                self._args("rcat", staging_uri, "--size", str(archive_size)),
                write_archive,
            )
            if size_bytes != archive_size:
                raise SourceError(
                    f"Checkpoint changed while archiving: expected {archive_size} bytes, got {size_bytes}"
                )
            metadata = {
                "schemaVersion": 1,
                "format": "tar",
                "sha256": digest,
                "sizeBytes": size_bytes,
            }
            with tempfile.TemporaryDirectory(prefix="wukong-checkpoint-metadata-") as root:
                metadata_path = Path(root) / "checkpoint.metadata.json"
                metadata_path.write_text(
                    json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                self.run_command(
                    self._args(
                        "copyto",
                        str(metadata_path),
                        staging_metadata_uri,
                        "--retries",
                        "3",
                    )
                )
            self.run_command(self._args("moveto", staging_uri, uri))
            self.run_command(self._args("moveto", staging_metadata_uri, metadata_uri))
            return uri
        except Exception:
            for candidate in (staging_uri, staging_metadata_uri, uri, metadata_uri):
                try:
                    self.run_command(self._args("deletefile", candidate))
                except Exception:
                    pass
            raise

    @staticmethod
    def _write_checkpoint_archive(source: Path, output: Any) -> None:
        # A size hint makes rclone stream reliably to Drive. Counting the TAR
        # first costs one extra disk pass but avoids a same-sized local copy.
        with tarfile.open(fileobj=output, mode="w|", dereference=False) as archive:
            for child in sorted(source.iterdir(), key=lambda item: item.name.casefold()):
                archive.add(
                    child,
                    arcname=child.name,
                    recursive=True,
                    filter=RcloneStorageAdapter._checkpoint_tar_filter,
                )

    @staticmethod
    def _checkpoint_tar_filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
        RcloneStorageAdapter._validate_checkpoint_member(member)
        return member

    @staticmethod
    def _validate_checkpoint_source(source: Path) -> None:
        for directory, directory_names, file_names in os.walk(source, followlinks=False):
            current = Path(directory)
            for name in [*directory_names, *file_names]:
                path = current / name
                if path.is_symlink():
                    link_name = os.readlink(path)
                    if not link_name or "\x00" in link_name:
                        raise SourceIntegrityError(
                            f"Checkpoint workspace contains an invalid symbolic link: {path.relative_to(source)}"
                        )

    def restore_tree(self, uri: str, destination: Path) -> Path:
        destination = destination.resolve()
        if uri.casefold().endswith(".tar"):
            return self._restore_checkpoint_archive(uri, destination)
        destination.mkdir(parents=True, exist_ok=True)
        self.run_command(self._args("copy", uri, str(destination), "--retries", "3"))
        return destination

    def _upload_stream(
        self,
        args: list[str],
        write_payload: Callable[[Any], tuple[str, int]],
    ) -> tuple[str, int]:
        if self.stream_command is not None:
            buffer = io.BytesIO()
            result = write_payload(buffer)
            self.stream_command(args, buffer.getvalue())
            return result

        with tempfile.TemporaryFile() as error_log:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=error_log,
            )
            assert process.stdin is not None
            try:
                result = write_payload(process.stdin)
                process.stdin.close()
                return_code = process.wait()
            except Exception:
                process.kill()
                process.wait()
                raise
            error_log.seek(0)
            stderr = error_log.read()
        if return_code != 0:
            details = stderr.decode("utf-8", errors="replace").strip()
            raise SourceError(f"Checkpoint upload failed: {details or f'rclone exited {return_code}'}")
        return result

    def _download_stream(self, args: list[str], read_payload: Callable[[Any], Path]) -> Path:
        if self.stream_command is not None:
            return read_payload(io.BytesIO(self.stream_command(args, None)))

        with tempfile.TemporaryFile() as error_log:
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=error_log,
            )
            assert process.stdout is not None
            try:
                result = read_payload(process.stdout)
                return_code = process.wait()
            except Exception:
                process.kill()
                process.wait()
                raise
            error_log.seek(0)
            stderr = error_log.read()
        if return_code != 0:
            details = stderr.decode("utf-8", errors="replace").strip()
            raise SourceError(f"Checkpoint download failed: {details or f'rclone exited {return_code}'}")
        return result

    def _restore_checkpoint_archive(self, uri: str, destination: Path) -> Path:
        try:
            metadata = json.loads(
                self.run_command(self._args("cat", uri + ".metadata.json"))
            )
            expected_sha256 = str(metadata["sha256"]).casefold()
            expected_size = int(metadata["sizeBytes"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SourceIntegrityError("Checkpoint archive metadata is invalid") from exc
        if (
            len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
            or expected_size < 0
        ):
            raise SourceIntegrityError("Checkpoint archive metadata is invalid")

        def download_archive(input_stream: Any, archive_path: Path) -> Path:
            reader = _HashingReader(input_stream)
            with archive_path.open("wb") as output:
                for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
                    output.write(chunk)
            if reader.size_bytes != expected_size:
                raise SourceIntegrityError(
                    f"Checkpoint archive size mismatch: expected {expected_size}, got {reader.size_bytes}"
                )
            actual_sha256 = reader.digest.hexdigest()
            if actual_sha256 != expected_sha256:
                raise SourceIntegrityError(
                    f"Checkpoint archive checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
                )
            return archive_path

        staging = destination.with_name(destination.name + ".restore-partial")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Hosted Actions may mount the workspace on a large build volume while
        # the system /tmp remains on a nearly-full root filesystem. Keep the
        # verified TAR beside its restore destination so both use that volume.
        with tempfile.TemporaryDirectory(
            prefix=".wukong-checkpoint-",
            dir=destination.parent,
        ) as temporary:
            archive_path = Path(temporary, "checkpoint.tar")
            self._download_stream(
                self._args("cat", uri),
                lambda input_stream: download_archive(input_stream, archive_path),
            )
            try:
                with tarfile.open(archive_path, mode="r:*") as archive:
                    members = archive.getmembers()
                    symbolic_links = self._validate_checkpoint_members(members)
                    if staging.exists():
                        shutil.rmtree(staging)
                    staging.mkdir(parents=True)
                    for member in members:
                        if not member.issym():
                            archive.extract(member, staging, filter="data")
                    self._restore_checkpoint_symlinks(staging, symbolic_links)
                if destination.exists():
                    shutil.rmtree(destination)
                os.replace(staging, destination)
            except (tarfile.TarError, OSError, ValueError) as exc:
                if staging.exists():
                    shutil.rmtree(staging)
                if isinstance(exc, SourceIntegrityError):
                    raise
                raise SourceIntegrityError(f"Invalid checkpoint archive: {exc}") from exc
            except Exception:
                if staging.exists():
                    shutil.rmtree(staging)
                raise
        return destination

    @classmethod
    def _validate_checkpoint_members(
        cls, members: list[tarfile.TarInfo]
    ) -> list[tuple[str, str]]:
        symbolic_paths: set[PurePosixPath] = set()
        members_by_path: dict[PurePosixPath, tarfile.TarInfo] = {}
        symbolic_links: list[tuple[str, str]] = []
        for member in members:
            cls._validate_checkpoint_member(member)
            path = PurePosixPath(member.name.replace("\\", "/"))
            if path in members_by_path:
                raise SourceIntegrityError(
                    f"Checkpoint archive contains a duplicate member: {member.name!r}"
                )
            members_by_path[path] = member
            if member.issym():
                symbolic_paths.add(path)
                symbolic_links.append((member.name, member.linkname))
        for member in members:
            path = PurePosixPath(member.name.replace("\\", "/"))
            if any(parent in symbolic_paths for parent in path.parents):
                raise SourceIntegrityError(
                    f"Checkpoint archive member has a symbolic-link parent: {member.name!r}"
                )
            if member.islnk():
                target_path = PurePosixPath(member.linkname.replace("\\", "/"))
                target = members_by_path.get(target_path)
                if target is None or not target.isfile():
                    raise SourceIntegrityError(
                        f"Checkpoint hardlink target is not a regular archive member: {member.name!r}"
                    )
                if any(parent in symbolic_paths for parent in target_path.parents):
                    raise SourceIntegrityError(
                        f"Checkpoint hardlink target has a symbolic-link parent: {member.name!r}"
                    )
        return symbolic_links

    @staticmethod
    def _restore_checkpoint_symlinks(staging: Path, links: list[tuple[str, str]]) -> None:
        # Create links only after every ordinary member and the archive digest
        # have been validated. A TAR cannot then use an earlier symlink as a
        # path-traversal pivot for a later file member.
        for member_name, link_name in links:
            relative = PurePosixPath(member_name.replace("\\", "/"))
            destination = staging.joinpath(*relative.parts)
            current = staging
            for part in relative.parts[:-1]:
                current = current / part
                if current.is_symlink():
                    raise SourceIntegrityError(
                        f"Checkpoint symbolic link has a symbolic-link parent: {member_name!r}"
                    )
                if current.exists() and not current.is_dir():
                    raise SourceIntegrityError(
                        f"Checkpoint symbolic link has a non-directory parent: {member_name!r}"
                    )
                current.mkdir(exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise SourceIntegrityError(
                    f"Checkpoint symbolic link conflicts with an extracted member: {member_name!r}"
                )
            try:
                os.symlink(link_name, destination)
            except OSError as exc:
                raise SourceIntegrityError(
                    f"Could not restore checkpoint symbolic link: {member_name!r}"
                ) from exc

    @staticmethod
    def _validate_checkpoint_member(member: tarfile.TarInfo) -> None:
        normalized = member.name.replace("\\", "/")
        path = PurePosixPath(normalized)
        link_is_unsafe = False
        if member.islnk() or member.issym():
            link_name = member.linkname.replace("\\", "/")
            link_path = PurePosixPath(link_name)
            link_is_unsafe = (
                not link_name
                or "\x00" in link_name
                or (
                    member.islnk()
                    and (
                        link_path.is_absolute()
                        or ".." in link_path.parts
                        or (link_path.parts and link_path.parts[0].endswith(":"))
                    )
                )
            )
        if (
            not normalized
            or "\x00" in normalized
            or path.is_absolute()
            or ".." in path.parts
            or (path.parts and path.parts[0].endswith(":"))
            or link_is_unsafe
            or not (member.isdir() or member.isfile() or member.islnk() or member.issym())
        ):
            raise SourceIntegrityError(
                f"unsafe checkpoint archive member: {member.name!r}"
            )

    def publish_artifact(
        self,
        artifact: Path,
        *,
        device: str,
        build: str,
        relative_root: str | None = None,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> ArtifactRecord:
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
        relative = (
            f"{relative_root.strip('/')}/{build}/{artifact.name}"
            if relative_root
            else f"artifacts/{device}/{build}/{artifact.name}"
        )
        uri = self.copy_file(artifact, relative, progress_callback=progress_callback)
        self.copy_file(metadata_path, relative + ".metadata.json")
        public_url = self.run_command(self._args("link", uri)).strip() or None
        return ArtifactRecord(
            name=artifact.name,
            uri=uri,
            sha256=digest,
            size_bytes=artifact.stat().st_size,
            public_url=public_url,
        )

    def mirror_artifact(
        self,
        artifact: Path,
        *,
        relative_path: str,
        staging_key: str,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> ArtifactRecord:
        """Publish an artifact atomically without asking the backend for a link.

        This is deliberately separate from ``publish_artifact``: WebDAV
        backends generally do not implement ``rclone link``.  The staged
        upload and final metadata write also make a partially uploaded ZIP
        invisible to the public share.
        """

        artifact = artifact.resolve()
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        normalized = relative_path.replace("\\", "/").strip("/")
        staging = staging_key.replace("\\", "/").strip("/")
        if (
            not normalized
            or not staging
            or ".." in PurePosixPath(normalized).parts
            or ".." in PurePosixPath(staging).parts
        ):
            raise ValueError("Mirror path is empty or contains path traversal")
        digest = sha256_file(artifact)
        size_bytes = artifact.stat().st_size
        final_uri = self.remote_uri(normalized)
        metadata_uri = final_uri + ".metadata.json"
        try:
            remote_metadata = self.run_command(self._args("cat", metadata_uri))
            payload = json.loads(remote_metadata)
            if (
                str(payload.get("sha256") or "").casefold() == digest.casefold()
                and int(payload.get("sizeBytes", -1)) == size_bytes
            ):
                # A metadata sidecar is the completion marker. When the
                # backend exposes size information, use it to detect a
                # stale sidecar; otherwise preserve the documented
                # checksum-based idempotency contract.
                stale = False
                try:
                    size_output = self.run_command(self._args("lsjson", final_uri, "--stat"))
                    if size_output.strip():
                        current_size = int(json.loads(size_output).get("Size", -1))
                        if current_size != size_bytes:
                            stale = True
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
                if not stale:
                    return ArtifactRecord(artifact.name, final_uri, digest, size_bytes)
        except Exception:
            # A missing or malformed metadata object is a normal first upload.
            pass

        stage_uri = self.remote_uri(f"_staging/{staging}/{artifact.name}.partial")
        try:
            self.copy_file(
                artifact,
                f"_staging/{staging}/{artifact.name}.partial",
                progress_callback=progress_callback,
            )
        except Exception as exc:
            raise MirrorCommandError("remote_upload_failed") from exc
        # ``rclone size`` treats its target as a directory. Some WebDAV
        # servers take a long time and then reject that operation for a file.
        # A direct stat is both bounded to one object and gives the exact size.
        try:
            size_output = self.run_command(self._args("lsjson", stage_uri, "--stat"))
        except Exception as exc:
            raise MirrorCommandError("remote_stat_failed") from exc
        try:
            remote_size = int(json.loads(size_output).get("Size", -1))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SourceIntegrityError("Mirror size check returned invalid data") from exc
        if remote_size != size_bytes:
            raise SourceIntegrityError(
                f"Mirror size mismatch: expected {size_bytes}, got {remote_size}"
            )
        final_parent = str(PurePosixPath(normalized).parent)
        if final_parent and final_parent != ".":
            try:
                self.run_command(self._args("mkdir", self.remote_uri(final_parent)))
            except Exception as exc:
                raise MirrorCommandError("remote_mkdir_failed") from exc
        try:
            self.run_command(self._args("moveto", stage_uri, final_uri, "--retries", "3"))
        except Exception as move_exc:
            # Cloudreve versions in the wild may reject WebDAV MOVE even
            # though scoped read/write and ordinary uploads work. The staged
            # object is already complete, but remote-to-remote COPY can hang
            # on WebDAV implementations that do not support server-side
            # copy. Re-upload from the verified local artifact instead, then
            # verify the final object and clean up staging. A metadata sidecar
            # is still written last, keeping the public completion marker
            # atomic.
            try:
                self.copy_file(
                    artifact,
                    normalized,
                    progress_callback=progress_callback,
                )
                final_size_output = self.run_command(self._args("lsjson", final_uri, "--stat"))
                final_size = int(json.loads(final_size_output).get("Size", -1))
                if final_size != size_bytes:
                    raise SourceIntegrityError(
                        f"Mirror final size mismatch: expected {size_bytes}, got {final_size}"
                    )
                self.run_command(self._args("deletefile", stage_uri))
            except SourceIntegrityError:
                raise
            except Exception as copy_exc:
                raise MirrorCommandError("remote_move_failed") from copy_exc
        with tempfile.TemporaryDirectory(prefix="wukong-mirror-metadata-") as root:
            metadata_path = Path(root) / (artifact.name + ".metadata.json")
            metadata_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "name": artifact.name,
                        "sha256": digest,
                        "sizeBytes": size_bytes,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            try:
                self.copy_file(metadata_path, normalized + ".metadata.json")
            except Exception as exc:
                raise MirrorCommandError("remote_metadata_failed") from exc
        return ArtifactRecord(artifact.name, final_uri, digest, size_bytes)

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

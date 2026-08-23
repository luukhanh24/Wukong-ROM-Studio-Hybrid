from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request

from .adapters import (
    HttpOpener,
    HttpOpenerFactory,
    HttpSourceAdapter,
    SourceError,
    SourceResolutionError,
)
from .security import validate_http_url


MAX_REMOTE_READ_BYTES = 8 * 1024 * 1024
MAX_PROBE_TRANSFER_BYTES = 16 * 1024 * 1024
MAX_RANGE_REQUESTS = 64
MAX_PROBE_DURATION_SECONDS = 45
MAX_METADATA_FILE_BYTES = 2 * 1024 * 1024
MAX_METADATA_FILES = 8
MAX_METADATA_FIELDS = 256
MAX_METADATA_TEXT_BYTES = 4 * 1024 * 1024
SIGNED_URL_CLOCK_SKEW_SECONDS = 15
MIN_DIRECT_SIGNED_URL_TTL_SECONDS = 30 * 60
METADATA_SUFFIXES = (
    "meta-inf/com/android/metadata",
    "payload_properties.txt",
    "android-info.txt",
)


def _signed_url_expiry(uri: str) -> int | None:
    query = {
        key.casefold(): values
        for key, values in parse_qs(urlparse(uri).query, keep_blank_values=True).items()
    }
    for key in ("expires", "x-oss-expires"):
        values = query.get(key)
        if not values:
            continue
        try:
            value = int(values[0])
        except (TypeError, ValueError):
            continue
        if value > 1_000_000_000:
            return value
    for duration_key, date_key in (
        ("x-amz-expires", "x-amz-date"),
        ("x-oss-expires", "x-oss-date"),
    ):
        duration_values = query.get(duration_key)
        date_values = query.get(date_key)
        if not duration_values or not date_values:
            continue
        try:
            duration = int(duration_values[0])
            signed_at = datetime.strptime(date_values[0], "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return int(signed_at.timestamp()) + duration
    return None


def _looks_like_signed_download(uri: str) -> bool:
    keys = {key.casefold() for key in parse_qs(urlparse(uri).query, keep_blank_values=True)}
    return bool(keys & {"signature", "x-oss-signature", "x-amz-signature"})


def validate_direct_signed_url_ttl(
    uri: str,
    *,
    refreshable: bool = False,
    now: int | None = None,
    minimum_ttl_seconds: int = MIN_DIRECT_SIGNED_URL_TTL_SECONDS,
) -> None:
    """Reject a direct signed URL that cannot safely survive cloud queueing."""
    if refreshable or not _looks_like_signed_download(uri):
        return
    expires_at = _signed_url_expiry(uri)
    if expires_at is None:
        return
    checked_at = int(time.time()) if now is None else int(now)
    if expires_at <= checked_at + SIGNED_URL_CLOCK_SKEW_SECONDS:
        raise SourceResolutionError(
            "The signed ROM download URL has expired; "
            "paste the original OPlus downloadCheck or Daniel Springer page"
        )
    if minimum_ttl_seconds > 0 and expires_at <= checked_at + minimum_ttl_seconds:
        raise SourceResolutionError(
            "The signed ROM download URL expires too soon for a cloud build; "
            "paste the original OPlus downloadCheck or Daniel Springer page"
        )


def _open_initial_probe(adapter: HttpSourceAdapter, request: Request, timeout: int) -> Any:
    for attempt in range(1, 4):
        try:
            return adapter.opener.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code in {401, 403} and _looks_like_signed_download(request.full_url):
                raise SourceResolutionError(
                    "The signed ROM download URL was rejected or has expired; "
                    "paste the original OPlus downloadCheck or Daniel Springer page"
                ) from exc
            if exc.code not in {408, 425, 429, 500, 502, 503, 504} or attempt == 3:
                raise
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 3:
                raise SourceResolutionError(
                    "The ROM server did not respond after 3 attempts"
                ) from exc
        time.sleep(0.2 * attempt)
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class SourceProbeResult:
    original_uri: str
    provider: str
    filename: str
    resolved_host: str
    size_bytes: int | None = None
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    md5: str | None = None
    product_name: str | None = None
    device: str | None = None
    version: str | None = None
    android_version: str | None = None
    security_patch: str | None = None
    build_date: str | None = None
    ota_type: str | None = None
    deep_inspected: bool = False
    warning: str | None = None
    signed_url_expires_at: int | None = None
    cloud_build_ready: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)
    resolved_url: str = field(default="", repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        """Return a log/UI-safe result without the short-lived signed URL."""
        return {
            "provider": self.provider,
            "filename": self.filename,
            "resolvedHost": self.resolved_host,
            "sizeBytes": self.size_bytes,
            "contentType": self.content_type,
            "etag": self.etag,
            "lastModified": self.last_modified,
            "md5": self.md5,
            "productName": self.product_name,
            "device": self.device,
            "version": self.version,
            "androidVersion": self.android_version,
            "securityPatch": self.security_patch,
            "buildDate": self.build_date,
            "otaType": self.ota_type,
            "deepInspected": self.deep_inspected,
            "warning": self.warning,
            "signedUrlExpiresAt": self.signed_url_expires_at,
            "cloudBuildReady": self.cloud_build_ready,
            "metadata": dict(self.metadata),
        }


class _HttpRangeReader(io.RawIOBase):
    def __init__(
        self,
        url: str,
        size_bytes: int,
        *,
        opener_factory: HttpOpenerFactory,
        timeout: int,
        validator: str | None,
    ) -> None:
        super().__init__()
        self.url = url
        self.size_bytes = size_bytes
        self.opener_factory = opener_factory
        self.timeout = timeout
        self.validator = validator
        self.position = 0
        self.transferred_bytes = 0
        self.request_count = 0
        self.started_at = time.monotonic()

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self.position + offset
        elif whence == io.SEEK_END:
            target = self.size_bytes + offset
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if target < 0:
            # zipfile probes a fixed-size end record even when a broken/tiny
            # response is shorter than that record. A normal buffered stream
            # effectively lets the parser inspect from byte zero in this case.
            if whence == io.SEEK_END:
                target = 0
            else:
                raise ValueError("Cannot seek before the start of the remote ROM")
        self.position = min(target, self.size_bytes)
        return self.position

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.size_bytes:
            return b""
        remaining = self.size_bytes - self.position
        requested = remaining if size is None or size < 0 else min(size, remaining)
        if requested > MAX_REMOTE_READ_BYTES:
            raise SourceResolutionError(
                f"Remote ZIP metadata read exceeds {MAX_REMOTE_READ_BYTES} bytes"
            )
        if self.request_count >= MAX_RANGE_REQUESTS:
            raise SourceResolutionError("Remote ZIP metadata requires too many range requests")
        if time.monotonic() - self.started_at > MAX_PROBE_DURATION_SECONDS:
            raise SourceResolutionError("Remote ZIP metadata probe exceeded its time limit")
        if self.transferred_bytes + requested > MAX_PROBE_TRANSFER_BYTES:
            raise SourceResolutionError("Remote ZIP metadata exceeds the aggregate probe limit")
        start = self.position
        end = start + requested - 1
        headers = {
            "User-Agent": "Wukong-ROM-Studio/1",
            "Accept-Encoding": "identity",
            "Range": f"bytes={start}-{end}",
        }
        if self.validator:
            headers["If-Range"] = self.validator
        request = Request(self.url, headers=headers)
        validate_http_url(self.url, resolve_dns=True)
        self.request_count += 1
        with self.opener_factory().open(request, timeout=self.timeout) as response:
            validate_http_url(response.geturl(), resolve_dns=True)
            status = getattr(response, "status", response.getcode())
            if status != 206:
                raise SourceResolutionError(
                    f"Remote ZIP probe expected HTTP 206, got {status}"
                )
            content_range = str(response.headers.get("Content-Range", ""))
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range.strip())
            if not match:
                raise SourceResolutionError("Remote ZIP probe returned an invalid Content-Range")
            response_start, response_end, response_total = map(int, match.groups())
            if response_start != start or response_end != end or response_total != self.size_bytes:
                raise SourceResolutionError("Remote ZIP probe range does not match the source")
            payload = response.read(requested + 1)
        if len(payload) != requested:
            raise SourceResolutionError("Remote ZIP probe returned an incomplete range")
        self.position += len(payload)
        self.transferred_bytes += len(payload)
        return payload


def _provider_for(uri: str, original_uri: str) -> str:
    hosts = {
        (urlparse(uri).hostname or "").casefold(),
        (urlparse(original_uri).hostname or "").casefold(),
    }
    original_host = (urlparse(original_uri).hostname or "").casefold()
    if original_host == "roms.danielspringer.at":
        return "daniel-springer"
    if any("allawn" in host or "oppo" in host or "coloros" in host for host in hosts):
        return "oplus"
    if urlparse(original_uri).path.casefold().rstrip("/").endswith("/downloadcheck"):
        return "oplus"
    return "http"


def _filename_from_headers(headers: Any, final_url: str) -> str:
    disposition = str(headers.get("Content-Disposition", ""))
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", disposition, flags=re.IGNORECASE)
    quoted = re.search(r'filename="([^"]+)"', disposition, flags=re.IGNORECASE)
    plain = re.search(r"filename=([^;]+)", disposition, flags=re.IGNORECASE)
    candidate = (
        unquote(encoded.group(1))
        if encoded
        else quoted.group(1)
        if quoted
        else plain.group(1).strip()
        if plain
        else unquote(urlparse(final_url).path.rsplit("/", 1)[-1])
    )
    candidate = candidate.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return candidate[:255] or "rom.zip"


def _source_size(headers: Any) -> int | None:
    content_range = str(headers.get("Content-Range", ""))
    match = re.search(r"/(\d+)$", content_range)
    if match:
        return int(match.group(1))
    try:
        value = int(headers.get("Content-Length", ""))
        return value if value > 1 else None
    except (TypeError, ValueError):
        return None


def _read_zip_metadata(reader: _HttpRangeReader) -> dict[str, str]:
    values: dict[str, str] = {}
    metadata_files = 0
    metadata_text_bytes = 0
    with zipfile.ZipFile(reader, "r") as archive:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/").casefold()
            if not any(normalized.endswith(suffix) for suffix in METADATA_SUFFIXES):
                continue
            if info.file_size > MAX_METADATA_FILE_BYTES:
                continue
            metadata_files += 1
            if metadata_files > MAX_METADATA_FILES:
                raise SourceResolutionError("ROM ZIP exposes too many metadata files")
            raw_content = archive.read(info)
            metadata_text_bytes += len(raw_content)
            if metadata_text_bytes > MAX_METADATA_TEXT_BYTES:
                raise SourceResolutionError("ROM ZIP metadata exceeds the inspection limit")
            content = raw_content.decode("utf-8", errors="replace")
            for line in content.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                normalized_key = key.strip().casefold().replace("_", "-")
                if normalized_key and len(normalized_key) <= 128:
                    values[normalized_key] = value.strip()[:1024]
                    if len(values) > MAX_METADATA_FIELDS:
                        raise SourceResolutionError("ROM ZIP metadata contains too many fields")
    return values


def _first(values: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value:
            return value
    return None

def _android_version(values: Mapping[str, str], version: str | None) -> str | None:
    explicit = _first(
        values,
        "android-version",
        "post-android-version",
    )
    if explicit:
        return explicit
    sdk = _first(values, "post-sdk-level", "sdk-level")
    sdk_versions = {
        "36": "16",
        "35": "15",
        "34": "14",
        "33": "13",
        "32": "12L",
        "31": "12",
        "30": "11",
        "29": "10",
    }
    if sdk in sdk_versions:
        return sdk_versions[sdk]
    match = re.search(r"(?:^|_)(\d{2})(?:\.|_)", version or "")
    return match.group(1) if match else None

def _build_date(values: Mapping[str, str]) -> str | None:
    explicit = _first(values, "build-date", "post-build-date", "build-timestamp")
    if explicit:
        try:
            parsed = datetime.fromisoformat(explicit.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?", explicit):
                return explicit.replace("T", " ")
    timestamp = _first(values, "post-timestamp", "timestamp")
    if timestamp:
        try:
            numeric = int(timestamp)
            if numeric > 10_000_000_000:
                numeric //= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            pass
    ota_build = _first(values, "ota-build")
    match = re.search(r"_(\d{12})(?:\D|$)", ota_build or "")
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d%H%M").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


def probe_http_source(
    uri: str,
    *,
    opener: HttpOpener | None = None,
    opener_factory: HttpOpenerFactory | None = None,
    timeout: int = 20,
) -> SourceProbeResult:
    """Resolve an HTTP ROM and inspect its remote ZIP metadata using byte ranges."""
    validate_http_url(uri, resolve_dns=True)
    adapter = HttpSourceAdapter(
        attempts=1,
        timeout=timeout,
        opener=opener,
        opener_factory=opener_factory,
    )
    resolved_input = uri
    page_metadata: dict[str, str] = {}
    is_daniel_ota_page = adapter._is_daniel_ota_page_url(uri)
    if is_daniel_ota_page:
        resolved_input, page_metadata = adapter._resolve_daniel_ota_page_details(uri)
        validate_http_url(resolved_input, resolve_dns=True)
    is_oplus_resolver = adapter._is_oplus_resolver_url(resolved_input)
    refreshable_source = is_daniel_ota_page or is_oplus_resolver
    checked_at = int(time.time())
    validate_direct_signed_url_ttl(
        resolved_input,
        refreshable=refreshable_source,
        now=checked_at,
        minimum_ttl_seconds=0,
    )
    signed_url_expires_at = (
        _signed_url_expiry(resolved_input)
        if not refreshable_source and _looks_like_signed_download(resolved_input)
        else None
    )
    cloud_build_ready = (
        signed_url_expires_at is None
        or signed_url_expires_at > checked_at + MIN_DIRECT_SIGNED_URL_TTL_SECONDS
    )
    headers = adapter._request_headers(resolved_input)
    headers["Range"] = "bytes=0-0"
    request = Request(resolved_input, headers=headers)
    with _open_initial_probe(adapter, request, timeout) as response:
        final_url = response.geturl()
        validate_http_url(final_url, resolve_dns=True)
        if is_oplus_resolver and final_url == resolved_input:
            prefix = response.read(64 * 1024)
            if adapter._looks_like_json(
                str(response.headers.get("Content-Type", "")).casefold(), prefix
            ):
                adapter._raise_resolver_error(prefix)
            raise SourceResolutionError("OPlus OTA resolver did not redirect to a ROM download")
        response_headers = response.headers
        size_bytes = _source_size(response_headers)
        filename = _filename_from_headers(response_headers, final_url)
        content_type = str(response_headers.get("Content-Type", "")) or None
        etag = str(response_headers.get("ETag", "")) or None
        last_modified = str(response_headers.get("Last-Modified", "")) or None
        md5 = str(response_headers.get("x-amz-meta-filemd5", "")) or None

    metadata: dict[str, str] = {
        "product-name": str(page_metadata.get("version") or "").split("_", 1)[0],
        "version-name": str(page_metadata.get("version") or ""),
        "post-security-patch-level": str(page_metadata.get("securityPatch") or ""),
        "ota-build": str(page_metadata.get("otaBuild") or ""),
    }
    metadata = {key: value for key, value in metadata.items() if value}
    deep_inspected = False
    warning: str | None = None
    range_factory = opener_factory or adapter.opener_factory
    if size_bytes and range_factory and filename.casefold().endswith(".zip"):
        reader = _HttpRangeReader(
            final_url,
            size_bytes,
            opener_factory=range_factory,
            timeout=timeout,
            validator=etag or last_modified,
        )
        try:
            zip_metadata = _read_zip_metadata(reader)
            metadata.update(zip_metadata)
            deep_inspected = bool(zip_metadata)
            if not zip_metadata and not metadata:
                warning = "ROM ZIP does not expose recognized metadata files"
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile, SourceError) as exc:
            warning = f"Remote ZIP metadata is unavailable: {exc}"

    product_name = _first(metadata, "oplus-product-name", "product-name")
    device = _first(metadata, "pre-device", "product-name", "oplus-product-name")
    version = _first(
        metadata,
        "oplus-version-name",
        "version-name",
        "post-build-incremental",
        "post-build",
    )
    return SourceProbeResult(
        original_uri=uri,
        provider=_provider_for(final_url, uri),
        filename=filename,
        resolved_host=(urlparse(final_url).hostname or ""),
        size_bytes=size_bytes,
        content_type=content_type,
        etag=etag,
        last_modified=last_modified,
        md5=md5,
        product_name=product_name,
        device=device,
        version=version,
        android_version=_android_version(metadata, version),
        security_patch=_first(metadata, "post-security-patch-level"),
        build_date=_build_date(metadata),
        ota_type=_first(metadata, "ota-type"),
        deep_inspected=deep_inspected,
        warning=warning,
        signed_url_expires_at=signed_url_expires_at,
        cloud_build_ready=cloud_build_ready,
        metadata=metadata,
        resolved_url=final_url,
    )

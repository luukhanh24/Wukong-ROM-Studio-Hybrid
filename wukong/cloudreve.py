"""Cloudreve v4 native uploader used by the DC Cloud mirror.

The client deliberately accepts only a refresh token. Password login belongs
to the local bootstrap tool and never runs in GitHub Actions.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

import requests

from .models import ArtifactRecord


MAX_PROXY_CHUNK_BYTES = 95 * 1024 * 1024
ONEDRIVE_CHUNK_GRANULARITY = 320 * 1024
ONEDRIVE_MAX_CHUNK_BYTES = 60 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CloudreveError(RuntimeError):
    """A sanitized native API failure safe to map to a mirror error code."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class CloudreveClient:
    def __init__(
        self,
        base_url: str,
        refresh_token: str,
        *,
        request: Callable[..., Any] = requests.request,
        timeout: tuple[float, float] = (20, 120),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed = urlsplit(base_url.strip())
        if (
            parsed.scheme.casefold() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Cloudreve base URL must be HTTPS without credentials")
        if not refresh_token.strip():
            raise ValueError("Cloudreve refresh token is required")
        self.base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
        self._refresh_token = refresh_token.strip()
        self._access_token = ""
        self._request = request
        self.timeout = timeout
        self.sleep = sleep

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", "api/v4/" + path.lstrip("/"))

    @staticmethod
    def _unwrap(response: Any, *, allow_error: bool = False) -> Any:
        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            if allow_error:
                return None
            raise CloudreveError("api_transport_failed") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            if allow_error:
                return None
            raise CloudreveError("api_request_failed")
        return payload.get("data")

    def _json(
        self,
        method: str,
        path_or_url: str,
        *,
        authenticated: bool = True,
        allow_error: bool = False,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        if authenticated:
            headers["Authorization"] = f"Bearer {self.access_token()}"
        headers.setdefault("User-Agent", "Wukong-ROM-Studio/1 CloudreveNative")
        url = path_or_url if path_or_url.startswith(("http://", "https://")) else self._url(path_or_url)
        try:
            response = self._request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        except Exception as exc:
            if allow_error:
                return None
            raise CloudreveError("api_transport_failed") from exc
        return self._unwrap(response, allow_error=allow_error)

    def access_token(self) -> str:
        if self._access_token:
            return self._access_token
        data = self._json(
            "POST",
            "session/token/refresh",
            authenticated=False,
            json={"refresh_token": self._refresh_token},
        )
        if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
            raise CloudreveError("token_refresh_failed")
        self._access_token = data["access_token"]
        return self._access_token

    def get_file(self, uri: str) -> dict[str, Any] | None:
        data = self._json(
            "GET",
            "file/info?" + urlencode({"uri": uri}),
            allow_error=True,
        )
        return data if isinstance(data, dict) else None

    def list_children(self, uri: str) -> list[dict[str, Any]]:
        data = self._json(
            "GET",
            "file?" + urlencode({"uri": uri}),
        )
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, list):
            raise CloudreveError("remote_list_failed")
        return [item for item in files if isinstance(item, dict)]

    def ensure_folder(self, uri: str) -> None:
        prefix, separator, raw_path = uri.partition("/WukongROM")
        if separator != "/WukongROM" or not prefix.startswith("cloudreve://"):
            raise CloudreveError("path_invalid")
        current = prefix + separator
        for part in PurePosixPath(raw_path.strip("/")).parts:
            current += "/" + part
            if self.get_file(current) is not None:
                continue
            created = self._json(
                "POST",
                "file/create",
                allow_error=True,
                json={"uri": current, "type": "folder", "err_on_conflict": True},
            )
            if created is None and self.get_file(current) is None:
                raise CloudreveError("remote_mkdir_failed")

    def upload_file(
        self,
        source: Path,
        uri: str,
        *,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> dict[str, Any]:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        size = source.stat().st_size
        session = self._json(
            "PUT",
            "file/upload",
            json={
                "uri": uri,
                "size": size,
                "last_modified": int(source.stat().st_mtime * 1000),
                "mime_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            },
        )
        if not isinstance(session, dict):
            raise CloudreveError("upload_session_invalid")
        if session.get("encrypt_metadata"):
            raise CloudreveError("encryption_unsupported")
        session_id = str(session.get("session_id") or "")
        chunk_size = int(session.get("chunk_size") or 0)
        expires = int(session.get("expires") or 0)
        policy = session.get("storage_policy")
        policy = policy if isinstance(policy, dict) else {}
        policy_type = str(policy.get("type") or "")
        relay = bool(policy.get("relay"))
        if not session_id or chunk_size <= 0:
            raise CloudreveError("upload_session_invalid")
        if chunk_size > MAX_PROXY_CHUNK_BYTES:
            raise CloudreveError("chunk_too_large")
        if policy_type not in {"local", "remote", "onedrive"}:
            raise CloudreveError("storage_policy_unsupported")
        if policy_type == "onedrive" and (
            chunk_size >= ONEDRIVE_MAX_CHUNK_BYTES
            or (size > chunk_size and chunk_size % ONEDRIVE_CHUNK_GRANULARITY != 0)
        ):
            raise CloudreveError("chunk_size_invalid")

        transferred = 0
        with source.open("rb") as stream:
            index = 0
            while transferred < size:
                if expires and time.time() >= expires - 30:
                    raise CloudreveError("upload_session_expired")
                body = stream.read(min(chunk_size, size - transferred))
                if not body:
                    raise CloudreveError("source_changed")
                if policy_type == "onedrive":
                    upload_urls = session.get("upload_urls")
                    if not isinstance(upload_urls, list) or not upload_urls:
                        raise CloudreveError("upload_session_invalid")
                    upload_url = str(upload_urls[0])
                    authorization = ""
                    range_start = transferred
                    pending = body
                elif policy_type == "local" or relay:
                    upload_url = self._url(f"file/upload/{quote(session_id, safe='')}/{index}")
                    authorization = f"Bearer {self.access_token()}"
                else:
                    upload_urls = session.get("upload_urls")
                    credential = session.get("credential")
                    if not isinstance(upload_urls, list) or not upload_urls or not isinstance(credential, str):
                        raise CloudreveError("upload_session_invalid")
                    parsed = urlsplit(str(upload_urls[0]))
                    query = parsed.query + ("&" if parsed.query else "") + urlencode({"chunk": index})
                    upload_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
                    authorization = f"Bearer {credential}"
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        if policy_type == "onedrive":
                            response = self._request(
                                "PUT",
                                upload_url,
                                headers={
                                    "Content-Type": "application/octet-stream",
                                    "Content-Length": str(len(pending)),
                                    "Content-Range": (
                                        f"bytes {range_start}-{transferred + len(body) - 1}/{size}"
                                    ),
                                },
                                data=pending,
                                timeout=self.timeout,
                            )
                            response.raise_for_status()
                        else:
                            self._json(
                                "POST",
                                upload_url,
                                authenticated=False,
                                headers={
                                    "Authorization": authorization,
                                    "Content-Type": "application/octet-stream",
                                    "Content-Length": str(len(body)),
                                },
                                data=body,
                            )
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        if policy_type == "onedrive":
                            try:
                                status = self._request(
                                    "GET",
                                    upload_url,
                                    timeout=self.timeout,
                                )
                                status.raise_for_status()
                                status_payload = status.json()
                                ranges = (
                                    status_payload.get("nextExpectedRanges")
                                    if isinstance(status_payload, dict)
                                    else None
                                )
                                if not ranges:
                                    last_error = None
                                    break
                                expected_start = int(str(ranges[0]).split("-", 1)[0])
                                range_end = transferred + len(body)
                                if expected_start >= range_end:
                                    last_error = None
                                    break
                                if expected_start > transferred:
                                    range_start = expected_start
                                    pending = body[expected_start - transferred :]
                            except Exception as status_exc:
                                status_code = getattr(
                                    getattr(status_exc, "response", None),
                                    "status_code",
                                    None,
                                )
                                if (
                                    transferred + len(body) == size
                                    and status_code in {404, 410}
                                ):
                                    # OneDrive removes a completed upload
                                    # session.  Let Cloudreve's authenticated
                                    # callback and the final size check decide
                                    # whether the lost final PUT succeeded.
                                    last_error = None
                                    break
                        if attempt < 2:
                            self.sleep(2**attempt)
                if last_error is not None:
                    raise CloudreveError("remote_upload_failed") from last_error
                transferred += len(body)
                index += 1
                if progress_callback is not None:
                    progress_callback(
                        {
                            "provider": "dccloud",
                            "bytesTransferred": transferred,
                            "totalBytes": size,
                        }
                    )
        if policy_type == "onedrive":
            callback_secret = str(session.get("callback_secret") or "")
            if not callback_secret:
                raise CloudreveError("upload_session_invalid")
            self._json(
                "POST",
                (
                    f"callback/onedrive/{quote(session_id, safe='')}/"
                    f"{quote(callback_secret, safe='')}"
                ),
            )
        uploaded: dict[str, Any] | None = None
        for attempt in range(5):
            uploaded = self.get_file(uri)
            if uploaded is not None:
                break
            if attempt < 4:
                self.sleep(1)
        if uploaded is None or int(uploaded.get("size", -1)) != size:
            raise CloudreveError("remote_stat_failed")
        return uploaded

    def move(self, uri: str, destination: str) -> None:
        self._json("POST", "file/move", json={"uris": [uri], "dst": destination, "copy": False})

    def delete(self, uri: str) -> None:
        self._json(
            "DELETE",
            "file",
            json={"uris": [uri], "unlink": False, "skip_soft_delete": False},
        )

    def capacity(self) -> dict[str, Any]:
        data = self._json("GET", "user/capacity")
        if not isinstance(data, dict):
            raise CloudreveError("quota_response_invalid")
        return data

    def read_json_file(self, uri: str) -> dict[str, Any] | None:
        if self.get_file(uri) is None:
            return None
        response = self._download_response(uri)
        try:
            payload = json.loads(response.content)
        except Exception as exc:
            raise CloudreveError("remote_metadata_failed") from exc
        return payload if isinstance(payload, dict) else None

    def download_file(self, uri: str, destination: Path) -> None:
        response = self._download_response(uri)
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise CloudreveError("remote_download_failed") from exc

    def _download_response(self, uri: str) -> Any:
        data = self._json(
            "POST",
            "file/url",
            json={"uris": [uri], "download": True, "no_cache": True},
        )
        urls = data.get("urls") if isinstance(data, dict) else None
        first = urls[0].get("url") if isinstance(urls, list) and urls and isinstance(urls[0], dict) else None
        if not isinstance(first, str):
            raise CloudreveError("remote_metadata_failed")
        try:
            response = self._request(
                "GET",
                urljoin(self.base_url + "/", first),
                timeout=self.timeout,
                headers={"User-Agent": "Wukong-ROM-Studio/1 CloudreveNative"},
            )
            response.raise_for_status()
        except Exception as exc:
            raise CloudreveError("remote_metadata_failed") from exc
        return response


class CloudreveStorageAdapter:
    """Artifact mirror adapter matching ``RcloneStorageAdapter.mirror_artifact``."""

    def __init__(self, client: CloudreveClient, *, account_root: str = "cloudreve://my/WukongROM") -> None:
        self.client = client
        self.account_root = account_root.rstrip("/")

    def _uri(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized or ".." in PurePosixPath(normalized).parts:
            raise ValueError("Cloud storage path is empty or contains path traversal")
        return f"{self.account_root}/{normalized}"

    def mirror_artifact(
        self,
        artifact: Path,
        *,
        relative_path: str,
        staging_key: str,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> ArtifactRecord:
        artifact = artifact.resolve()
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        staging_key = staging_key.replace("\\", "/").strip("/")
        if not staging_key or ".." in PurePosixPath(staging_key).parts:
            raise ValueError("Mirror staging path is invalid")
        digest = _sha256_file(artifact)
        size = artifact.stat().st_size
        final_uri = self._uri(relative_path)
        metadata_uri = final_uri + ".metadata.json"
        metadata = self.client.read_json_file(metadata_uri)
        final = self.client.get_file(final_uri)
        if (
            isinstance(metadata, dict)
            and str(metadata.get("sha256") or "").casefold() == digest.casefold()
            and int(metadata.get("sizeBytes", -1)) == size
            and isinstance(final, dict)
            and int(final.get("size", -1)) == size
        ):
            return ArtifactRecord(artifact.name, final_uri, digest, size)

        final_parent = final_uri.rsplit("/", 1)[0]
        staging_parent = self._uri(f"_staging/{staging_key}")
        staging_uri = f"{staging_parent}/{artifact.name}"
        self.client.ensure_folder(staging_parent)
        self.client.ensure_folder(final_parent)
        staged = self.client.get_file(staging_uri)
        if not isinstance(staged, dict) or int(staged.get("size", -1)) != size:
            self.client.upload_file(artifact, staging_uri, progress_callback=progress_callback)
        self.client.move(staging_uri, final_parent)
        moved = self.client.get_file(final_uri)
        if not isinstance(moved, dict) or int(moved.get("size", -1)) != size:
            raise CloudreveError("remote_move_failed")

        with TemporaryDirectory(prefix="wukong-cloudreve-metadata-") as root:
            metadata_path = Path(root, artifact.name + ".metadata.json")
            metadata_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "name": artifact.name,
                        "sha256": digest,
                        "sizeBytes": size,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self.client.upload_file(metadata_path, metadata_uri)
        return ArtifactRecord(artifact.name, final_uri, digest, size)

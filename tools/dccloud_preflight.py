"""Validate the opt-in DC Cloud WebDAV mirror from a GitHub runner."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from wukong.artifact_mirror import DCloudMirrorConfig
from wukong.adapters import RcloneStorageAdapter


def _version_at_least(value: str, minimum: tuple[int, int, int] = (4, 16, 1)) -> bool:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value.strip())
    return bool(match) and tuple(int(match.group(index)) for index in range(1, 4)) >= minimum


def _run(args: list[str]) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)
    return completed.stdout


def _anonymous_share_list_url(share_url: str) -> str:
    parsed = urlsplit(share_url)
    share_id = ""
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) == 2 and path_parts[0] == "s":
        share_id = path_parts[1]
    else:
        share_path = parse_qs(parsed.query).get("path", [""])[0]
        match = re.fullmatch(r"cloudreve://([^/@]+)@share/?", share_path)
        if match:
            share_id = match.group(1)
    if not share_id or not re.fullmatch(r"[A-Za-z0-9_-]+", share_id):
        raise ValueError("WUKONG_DCCLOUD_SHARE_URL must be a Cloudreve folder share")
    query = urlencode({"uri": f"cloudreve://{share_id}@share"})
    return urlunsplit((parsed.scheme, parsed.netloc, "/api/v4/file", query, ""))


def _capability_enabled(encoded: str, flag: int) -> bool:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise SystemExit("DC Cloud public share returned an invalid capability set") from exc
    return flag < len(raw) * 8 and bool(raw[flag // 8] & (1 << (flag % 8)))


def _verify_read_only_capability(encoded: str) -> None:
    required = {7, 9}  # DownloadFile, ListChildren
    forbidden = {0, 1, 6, 8, 14, 16, 18}  # Create, rename, upload, update, delete, share
    if not all(_capability_enabled(encoded, flag) for flag in required):
        raise SystemExit("DC Cloud public share does not allow anonymous list/download")
    if any(_capability_enabled(encoded, flag) for flag in forbidden):
        raise SystemExit("DC Cloud public share grants anonymous write permissions")


def _verify_anonymous_share(
    share_url: str,
    expected_root: str,
    *,
    probe_name: str | None = None,
    probe_body: bytes | None = None,
) -> None:
    list_url = _anonymous_share_list_url(share_url)
    request = Request(
        list_url,
        headers={"User-Agent": "Wukong-DCCloud-Preflight/1"},
    )
    with urlopen(request, timeout=20) as response:
        if not (200 <= int(response.status) < 300):
            raise SystemExit(f"DC Cloud public share API returned HTTP {response.status}")
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) else None
    parent = data.get("parent") if isinstance(data, dict) else None
    root_name = parent.get("name") if isinstance(parent, dict) else None
    if not isinstance(payload, dict) or payload.get("code") != 0 or root_name != expected_root.rsplit("/", 1)[-1]:
        raise SystemExit("DC Cloud public share is not anonymously listable at the configured root")
    props = data.get("props") if isinstance(data, dict) else None
    capability = props.get("capability") if isinstance(props, dict) else None
    if not isinstance(capability, str):
        raise SystemExit("DC Cloud public share did not return its anonymous capability set")
    _verify_read_only_capability(capability)
    if probe_name is None:
        return
    files = data.get("files") if isinstance(data, dict) else None
    probe = next(
        (item for item in files or [] if isinstance(item, dict) and item.get("name") == probe_name),
        None,
    )
    context_hint = data.get("context_hint") if isinstance(data, dict) else None
    if not isinstance(probe, dict) or not isinstance(probe.get("path"), str) or not isinstance(context_hint, str):
        raise SystemExit("DC Cloud public share probe is not anonymously listable")
    body = json.dumps({"uris": [probe["path"]], "download": True}).encode("utf-8")
    download_request = Request(
        urlunsplit((*urlsplit(list_url)[:2], "/api/v4/file/url", "", "")),
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Wukong-DCCloud-Preflight/1",
            "X-Cr-Context-Hint": context_hint,
        },
        method="POST",
    )
    with urlopen(download_request, timeout=20) as response:
        download_payload = json.load(response)
    download_data = download_payload.get("data") if isinstance(download_payload, dict) else None
    urls = download_data.get("urls") if isinstance(download_data, dict) else None
    first_url = urls[0].get("url") if isinstance(urls, list) and urls and isinstance(urls[0], dict) else None
    if not isinstance(download_payload, dict) or download_payload.get("code") != 0 or not isinstance(first_url, str):
        raise SystemExit("DC Cloud public share did not issue an anonymous download URL")
    with urlopen(urljoin(share_url, first_url), timeout=20) as response:
        downloaded = response.read(len(probe_body or b"") + 1)
    if probe_body is None or downloaded != probe_body:
        raise SystemExit("DC Cloud anonymous probe download did not match its uploaded content")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight the DC Cloud WebDAV mirror")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--write-test", action="store_true")
    args = parser.parse_args()
    config = DCloudMirrorConfig.from_env(config_path=args.config)
    if not config.enabled:
        print("DC Cloud mirror disabled")
        return 0
    if config.validation_error:
        raise SystemExit(config.validation_error)
    if not _version_at_least(config.cloudreve_version):
        raise SystemExit("WUKONG_DCCLOUD_CLOUDREVE_VERSION must be Cloudreve >= 4.16.1")
    storage = RcloneStorageAdapter(remote=config.remote, root="", config_path=args.config)
    # Listing the configured root proves that the remote exists and the
    # scoped account can read it without exposing rclone's stderr.
    _run(storage._args("lsd", storage.remote_uri(config.root), "--max-depth", "1"))
    if args.write_test:
        key = f"{uuid.uuid4().hex}.preflight"
        with tempfile.TemporaryDirectory(prefix="wukong-dccloud-preflight-") as root:
            probe = Path(root) / "probe"
            probe_body = b"wukong-dccloud-preflight\n"
            probe.write_bytes(probe_body)
            target = storage.remote_uri(f"_staging/{key}")
            _run(storage._args("copyto", str(probe), target, "--retries", "1"))
            _run(storage._args("deletefile", target))
            public_target = storage.remote_uri(f"{config.root}/{key}")
            _run(storage._args("copyto", str(probe), public_target, "--retries", "1"))
            try:
                last_error: SystemExit | None = None
                for attempt in range(5):
                    try:
                        _verify_anonymous_share(
                            config.share_url,
                            config.root,
                            probe_name=key,
                            probe_body=probe_body,
                        )
                        last_error = None
                        break
                    except SystemExit as exc:
                        last_error = exc
                        if attempt < 4:
                            time.sleep(2)
                if last_error is not None:
                    raise last_error
            finally:
                _run(storage._args("deletefile", public_target))
    else:
        _verify_anonymous_share(config.share_url, config.root)
    print(json.dumps({"remote": config.remote, "root": config.root, "share": "readable"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate the opt-in DC Cloud WebDAV mirror from a GitHub runner."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from wukong.artifact_mirror import DCloudMirrorConfig
from wukong.adapters import RcloneStorageAdapter


def _version_at_least(value: str, minimum: tuple[int, int, int] = (4, 16, 1)) -> bool:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value.strip())
    return bool(match) and tuple(int(match.group(index)) for index in range(1, 4)) >= minimum


def _run(args: list[str]) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)
    return completed.stdout


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
            probe.write_bytes(b"wukong-dccloud-preflight\n")
            target = storage.remote_uri(f"_staging/{key}")
            _run(storage._args("copyto", str(probe), target, "--retries", "1"))
            _run(storage._args("deletefile", target))
    request = Request(config.share_url, headers={"User-Agent": "Wukong-DCCloud-Preflight/1"})
    with urlopen(request, timeout=20) as response:
        if not (200 <= int(response.status) < 400):
            raise SystemExit(f"DC Cloud public share returned HTTP {response.status}")
    print(json.dumps({"remote": config.remote, "root": config.root, "share": "readable"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

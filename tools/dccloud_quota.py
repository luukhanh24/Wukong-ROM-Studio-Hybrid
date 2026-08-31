"""Report DC Cloud quota without making quota exhaustion fatal."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from wukong.artifact_mirror import DCloudMirrorConfig
from wukong.adapters import RcloneStorageAdapter
from wukong.cloudreve import CloudreveClient


def main() -> int:
    config_path = Path(os.environ.get("WUKONG_RCLONE_CONFIG", ".wkstudio/secrets/rclone.conf"))
    config = DCloudMirrorConfig.from_env(config_path=config_path)
    if not config.enabled:
        return 0
    try:
        if config.upload_mode == "native":
            payload = CloudreveClient(config.api_url, config.refresh_token).capacity()
        else:
            output = subprocess.run(
                RcloneStorageAdapter(
                    remote=config.remote,
                    root="",
                    webdav_url=config.webdav_url or None,
                    config_path=config_path,
                )._args(
                    "about", f"{config.remote}:", "--json"
                ),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout
            payload = json.loads(output)
        used = float(payload.get("used", 0) or 0)
        total = float(payload.get("total", 0) or 0)
        ratio = used / total if total > 0 else 0
        if ratio >= 0.8:
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as handle:
                    handle.write(f"\n> ⚠️ DC Cloud quota is {ratio:.0%} used.\n")
            print(f"DC Cloud quota warning: {ratio:.0%} used")
    except Exception as exc:
        print(f"DC Cloud quota check unavailable: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

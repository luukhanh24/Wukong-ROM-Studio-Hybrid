from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Mapping, Sequence

from .control_plane_preflight import (
    BOT_TOKEN_RE,
    DOMAIN_RE,
    RELEASE_RE,
    REMOTE_RE,
    REPOSITORY_RE,
    ControlPlaneConfigurationError,
)


ENVIRONMENT_KEYS = (
    "WUKONG_MINI_API_DOMAIN",
    "WUKONG_RELEASE_SHA",
    "WUKONG_TELEGRAM_BOT_TOKEN",
    "WUKONG_TELEGRAM_ADMIN_IDS",
    "WUKONG_TELEGRAM_TRANSPORT",
    "WUKONG_TELEGRAM_WEBHOOK_SECRET",
    "WUKONG_TELEGRAM_WEB_APP_URL",
    "WUKONG_TELEGRAM_MINI_APP_API_URL",
    "WUKONG_TELEGRAM_MINI_APP_MAX_AUTH_AGE",
    "WUKONG_GITHUB_REPOSITORY",
    "WUKONG_GITHUB_TOKEN",
    "WUKONG_RCLONE_REMOTE",
    "WUKONG_RCLONE_CONFIG",
)
ADMIN_IDS_RE = re.compile(r"[0-9]+(?:,[0-9]+)*\Z")


def _required(values: Mapping[str, str], name: str) -> str:
    value = str(values.get(name, "")).strip()
    if not value:
        raise ControlPlaneConfigurationError(f"Missing required setting: {name}")
    if any(character in value for character in ("\0", "\r", "\n")):
        raise ControlPlaneConfigurationError(f"Setting contains an invalid character: {name}")
    return value


def render_environment(
    values: Mapping[str, str],
    *,
    domain: str,
    release_sha: str,
) -> str:
    domain = domain.strip().casefold().rstrip(".")
    release_sha = release_sha.strip().casefold()
    if not DOMAIN_RE.fullmatch(domain):
        raise ControlPlaneConfigurationError("The control-plane domain is invalid")
    if not RELEASE_RE.fullmatch(release_sha):
        raise ControlPlaneConfigurationError("The release SHA is invalid")

    bot_token = _required(values, "WUKONG_TELEGRAM_BOT_TOKEN")
    admin_ids = _required(values, "WUKONG_TELEGRAM_ADMIN_IDS")
    web_app_url = _required(values, "WUKONG_TELEGRAM_WEB_APP_URL").rstrip("/") + "/"
    repository = _required(values, "WUKONG_GITHUB_REPOSITORY")
    github_token = _required(values, "WUKONG_GITHUB_TOKEN")
    webhook_secret = _required(values, "WUKONG_TELEGRAM_WEBHOOK_SECRET")
    remote = str(values.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive")).strip()
    if not BOT_TOKEN_RE.fullmatch(bot_token):
        raise ControlPlaneConfigurationError("The Telegram bot token format is invalid")
    if not ADMIN_IDS_RE.fullmatch(admin_ids) or any(int(item) <= 0 for item in admin_ids.split(",")):
        raise ControlPlaneConfigurationError("Telegram admin IDs are invalid")
    if not web_app_url.startswith("https://"):
        raise ControlPlaneConfigurationError("The Telegram Mini App URL must use HTTPS")
    if not REPOSITORY_RE.fullmatch(repository):
        raise ControlPlaneConfigurationError("The GitHub repository is invalid")
    if len(github_token) < 20:
        raise ControlPlaneConfigurationError("The GitHub token is too short")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", webhook_secret):
        raise ControlPlaneConfigurationError("The Telegram webhook secret is invalid")
    if not REMOTE_RE.fullmatch(remote):
        raise ControlPlaneConfigurationError("The rclone remote is invalid")

    environment = {
        "WUKONG_MINI_API_DOMAIN": domain,
        "WUKONG_RELEASE_SHA": release_sha,
        "WUKONG_TELEGRAM_BOT_TOKEN": bot_token,
        "WUKONG_TELEGRAM_ADMIN_IDS": admin_ids,
        "WUKONG_TELEGRAM_TRANSPORT": "webhook",
        "WUKONG_TELEGRAM_WEBHOOK_SECRET": webhook_secret,
        "WUKONG_TELEGRAM_WEB_APP_URL": web_app_url,
        "WUKONG_TELEGRAM_MINI_APP_API_URL": f"https://{domain}",
        "WUKONG_TELEGRAM_MINI_APP_MAX_AUTH_AGE": "3600",
        "WUKONG_GITHUB_REPOSITORY": repository,
        "WUKONG_GITHUB_TOKEN": github_token,
        "WUKONG_RCLONE_REMOTE": remote,
        "WUKONG_RCLONE_CONFIG": "/var/lib/wukong/data/Secrets/rclone.runtime.conf",
    }
    return "".join(f"{key}={json.dumps(environment[key])}\n" for key in ENVIRONMENT_KEYS)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the VPS control-plane environment")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = render_environment(
            os.environ,
            domain=args.domain,
            release_sha=args.release_sha,
        )
    except ControlPlaneConfigurationError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    try:
        args.output.chmod(0o600)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

import requests


DOMAIN_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
REMOTE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
RELEASE_RE = re.compile(r"[0-9a-f]{40}\Z")
BOT_TOKEN_RE = re.compile(r"[0-9]{6,12}:[A-Za-z0-9_-]{20,}\Z")


class ControlPlaneConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ControlPlaneConfiguration:
    domain: str
    mini_app_url: str
    api_url: str
    bot_token: str
    admin_ids: tuple[str, ...]
    telegram_transport: str
    telegram_webhook_secret: str | None
    github_repository: str
    github_token: str
    rclone_remote: str
    rclone_config: Path
    release_sha: str | None


def _required(environ: Mapping[str, str], name: str) -> str:
    value = str(environ.get(name, "")).strip()
    if not value:
        raise ControlPlaneConfigurationError(f"Missing required setting: {name}")
    if "\n" in value or "\r" in value:
        raise ControlPlaneConfigurationError(f"Setting contains an invalid newline: {name}")
    return value


def _https_url(value: str, name: str, *, allow_path: bool) -> tuple[str, str]:
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (not allow_path and parsed.path not in {"", "/"})
    ):
        raise ControlPlaneConfigurationError(f"{name} must be a public HTTPS URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ControlPlaneConfigurationError(f"{name} contains an invalid port") from exc
    if port not in {None, 443}:
        raise ControlPlaneConfigurationError(f"{name} must use the standard HTTPS port")
    return parsed.hostname.casefold(), value.rstrip("/")


def load_configuration(
    environ: Mapping[str, str] | None = None,
) -> ControlPlaneConfiguration:
    values = os.environ if environ is None else environ
    domain = _required(values, "WUKONG_MINI_API_DOMAIN").casefold().rstrip(".")
    if not DOMAIN_RE.fullmatch(domain):
        raise ControlPlaneConfigurationError(
            "WUKONG_MINI_API_DOMAIN must be a DNS hostname without a scheme or path"
        )
    mini_app_host, mini_app_url = _https_url(
        _required(values, "WUKONG_TELEGRAM_WEB_APP_URL"),
        "WUKONG_TELEGRAM_WEB_APP_URL",
        allow_path=True,
    )
    api_host, api_url = _https_url(
        _required(values, "WUKONG_TELEGRAM_MINI_APP_API_URL"),
        "WUKONG_TELEGRAM_MINI_APP_API_URL",
        allow_path=False,
    )
    if api_host != domain:
        raise ControlPlaneConfigurationError(
            "WUKONG_TELEGRAM_MINI_APP_API_URL must use WUKONG_MINI_API_DOMAIN"
        )
    if mini_app_host == domain:
        raise ControlPlaneConfigurationError(
            "The Mini App site and control-plane API must use separate origins"
        )

    bot_token = _required(values, "WUKONG_TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN_RE.fullmatch(bot_token):
        raise ControlPlaneConfigurationError("WUKONG_TELEGRAM_BOT_TOKEN has an invalid format")
    raw_admins = _required(values, "WUKONG_TELEGRAM_ADMIN_IDS")
    admin_ids = tuple(dict.fromkeys(item.strip() for item in raw_admins.split(",") if item.strip()))
    if not admin_ids or any(not item.isascii() or not item.isdigit() or int(item) <= 0 for item in admin_ids):
        raise ControlPlaneConfigurationError(
            "WUKONG_TELEGRAM_ADMIN_IDS must contain positive Telegram IDs"
        )
    transport = str(values.get("WUKONG_TELEGRAM_TRANSPORT", "polling")).strip().casefold()
    if transport not in {"polling", "webhook"}:
        raise ControlPlaneConfigurationError("WUKONG_TELEGRAM_TRANSPORT must be polling or webhook")
    webhook_secret = str(values.get("WUKONG_TELEGRAM_WEBHOOK_SECRET", "")).strip() or None
    if transport == "webhook" and (
        not webhook_secret
        or len(webhook_secret) < 32
        or len(webhook_secret) > 256
        or not re.fullmatch(r"[A-Za-z0-9_-]+", webhook_secret)
    ):
        raise ControlPlaneConfigurationError(
            "WUKONG_TELEGRAM_WEBHOOK_SECRET must contain 32-256 safe characters"
        )

    repository = _required(values, "WUKONG_GITHUB_REPOSITORY")
    if not REPOSITORY_RE.fullmatch(repository):
        raise ControlPlaneConfigurationError("WUKONG_GITHUB_REPOSITORY must be owner/repository")
    github_token = _required(values, "WUKONG_GITHUB_TOKEN")
    if len(github_token) < 20:
        raise ControlPlaneConfigurationError("WUKONG_GITHUB_TOKEN is too short")
    remote = _required(values, "WUKONG_RCLONE_REMOTE")
    if not REMOTE_RE.fullmatch(remote):
        raise ControlPlaneConfigurationError("WUKONG_RCLONE_REMOTE has an invalid name")
    config = Path(_required(values, "WUKONG_RCLONE_CONFIG")).expanduser().resolve()
    if not config.is_file() or config.stat().st_size <= 0:
        raise ControlPlaneConfigurationError("WUKONG_RCLONE_CONFIG is missing or empty")
    if os.name != "nt" and stat.S_IMODE(config.stat().st_mode) & 0o077:
        raise ControlPlaneConfigurationError("WUKONG_RCLONE_CONFIG must use file mode 0600")

    release = str(values.get("WUKONG_RELEASE_SHA", "")).strip().casefold() or None
    if release and not RELEASE_RE.fullmatch(release):
        raise ControlPlaneConfigurationError("WUKONG_RELEASE_SHA must be a 40-character Git SHA")
    return ControlPlaneConfiguration(
        domain=domain,
        mini_app_url=mini_app_url,
        api_url=api_url,
        bot_token=bot_token,
        admin_ids=admin_ids,
        telegram_transport=transport,
        telegram_webhook_secret=webhook_secret,
        github_repository=repository,
        github_token=github_token,
        rclone_remote=remote,
        rclone_config=config,
        release_sha=release,
    )


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
HttpGet = Callable[..., requests.Response]


def _run(command: Sequence[str], run_command: RunCommand, label: str) -> str:
    try:
        result = run_command(
            list(command),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ControlPlaneConfigurationError(f"{label} could not run") from exc
    if result.returncode != 0:
        raise ControlPlaneConfigurationError(f"{label} failed")
    return result.stdout


def run_preflight(
    *,
    online: bool = False,
    environ: Mapping[str, str] | None = None,
    run_command: RunCommand = subprocess.run,
    http_get: HttpGet = requests.get,
) -> dict[str, object]:
    config = load_configuration(environ)
    remotes = {
        item.rstrip(":")
        for item in _run(
            ["rclone", "listremotes", "--config", str(config.rclone_config)],
            run_command,
            "rclone configuration check",
        ).splitlines()
        if item.strip()
    }
    if config.rclone_remote not in remotes:
        raise ControlPlaneConfigurationError(
            "WUKONG_RCLONE_REMOTE is not present in the rclone configuration"
        )

    checks: dict[str, object] = {
        "configuration": "ready",
        "rcloneConfiguration": "ready",
        "release": config.release_sha or "development",
    }
    if not online:
        return checks

    try:
        telegram = http_get(
            f"https://api.telegram.org/bot{config.bot_token}/getMe",
            timeout=15,
        )
        telegram_payload = telegram.json()
    except (requests.RequestException, ValueError) as exc:
        raise ControlPlaneConfigurationError("Telegram credential check failed") from exc
    if telegram.status_code != 200 or not isinstance(telegram_payload, dict) or telegram_payload.get("ok") is not True:
        raise ControlPlaneConfigurationError("Telegram credential check failed")
    checks["telegram"] = "ready"

    try:
        github = http_get(
            "https://api.github.com/repos/"
            f"{config.github_repository}/actions/workflows/wukong-build.yml",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {config.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ControlPlaneConfigurationError("GitHub Actions credential check failed") from exc
    if github.status_code != 200:
        raise ControlPlaneConfigurationError("GitHub Actions credential check failed")
    checks["githubActions"] = "ready"

    _run(
        [
            "rclone",
            "lsd",
            f"{config.rclone_remote}:",
            "--config",
            str(config.rclone_config),
            "--max-depth",
            "1",
            "--contimeout",
            "10s",
            "--timeout",
            "20s",
            "--retries",
            "1",
        ],
        run_command,
        "Google Drive access check",
    )
    checks["googleDrive"] = "ready"
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the always-on control plane")
    parser.add_argument("--online", action="store_true", help="also verify external credentials")
    args = parser.parse_args(argv)
    try:
        result = run_preflight(online=args.online)
    except ControlPlaneConfigurationError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "ready", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bootstrap a Cloudreve refresh token without persisting the user password."""

from __future__ import annotations

import argparse
import getpass
import subprocess
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from wukong.cloudreve import CloudreveClient


def _base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit("DC Cloud API URL must be HTTPS without credentials")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def exchange_password_for_refresh_token(
    api_url: str,
    email: str,
    password: str,
    *,
    request: Callable[..., Any] = requests.request,
) -> str:
    base = _base_url(api_url)
    try:
        response = request(
            "POST",
            urljoin(base + "/", "api/v4/session/token"),
            json={"email": email.strip(), "password": password},
            headers={"User-Agent": "Wukong-ROM-Studio/1 DCCloudBootstrap"},
            timeout=(20, 60),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise SystemExit("DC Cloud login request failed") from exc
    if not isinstance(payload, dict):
        raise SystemExit("DC Cloud login returned an invalid response")
    code = payload.get("code")
    if code != 0:
        if isinstance(payload.get("data"), str) and code in {203, 20300}:
            raise SystemExit("DC Cloud login requires 2FA; disable 2FA temporarily or extend the bootstrap flow")
        message = str(payload.get("msg") or "login rejected").replace("\r", " ").replace("\n", " ")[:160]
        raise SystemExit(f"DC Cloud login rejected (code {code}): {message}")
    data = payload.get("data")
    token_pair = data.get("token") if isinstance(data, dict) else None
    refresh_token = token_pair.get("refresh_token") if isinstance(token_pair, dict) else None
    if not isinstance(refresh_token, str) or not refresh_token:
        raise SystemExit("DC Cloud login did not return a refresh token")
    return refresh_token


def _set_github_secret(name: str, value: str, repo: str | None) -> None:
    args = ["gh", "secret", "set", name]
    if repo:
        args.extend(["--repo", repo])
    try:
        subprocess.run(
            args,
            input=value + "\n",
            text=True,
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("Could not store the DC Cloud refresh token in GitHub Secrets") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log in to DC Cloud once and store only its refresh token in GitHub Secrets"
    )
    parser.add_argument("--api-url", default="https://cloud.dabeecao.org")
    parser.add_argument("--email", required=True)
    parser.add_argument("--repo")
    parser.add_argument("--secret-name", default="WUKONG_DCCLOUD_REFRESH_TOKEN")
    args = parser.parse_args()
    password = getpass.getpass("DC Cloud password (hidden, never stored): ")
    try:
        refresh_token = exchange_password_for_refresh_token(
            args.api_url,
            args.email,
            password,
        )
    finally:
        password = ""
    # Validate the refresh token before transmitting it to GitHub.
    CloudreveClient(args.api_url, refresh_token).access_token()
    _set_github_secret(args.secret_name, refresh_token, args.repo)
    print(f"Stored {args.secret_name} in GitHub Secrets; password was not stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

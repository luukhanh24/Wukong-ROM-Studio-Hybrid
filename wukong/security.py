from __future__ import annotations

import ipaddress
import socket
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from urllib.parse import urlparse

from .models import BuildRecipe, Identity, RecipeValidationError, REMOTE_RE


Resolver = Callable[..., list[tuple[object, ...]]]
PRIVATE_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
ALLOWED_CLOUD_SOURCE_ROOTS = ("WukongROM/sources", "WukongROM/artifacts")


def _is_non_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return not address.is_global


def validate_http_url(url: str, *, resolve_dns: bool = False, resolver: Resolver = socket.getaddrinfo) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
        raise RecipeValidationError("ROM URL must use HTTP or HTTPS")
    if parsed.username or parsed.password:
        raise RecipeValidationError("ROM URL must not contain credentials")
    if hostname in PRIVATE_HOSTNAMES or hostname.endswith(".localhost") or _is_non_public_address(hostname):
        raise RecipeValidationError("ROM URL must not target localhost or a private network")
    if not resolve_dns:
        return
    try:
        addresses = {
            str(entry[4][0]).split("%", 1)[0]
            for entry in resolver(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise RecipeValidationError(f"ROM URL host cannot be resolved: {hostname}") from exc
    if not addresses or any(_is_non_public_address(address) for address in addresses):
        raise RecipeValidationError("ROM URL resolves to localhost or a private network")


def validate_rclone_source(uri: str, *, allowed_remote: str = "wukong-gdrive") -> None:
    match = REMOTE_RE.fullmatch(uri)
    if not match or uri.split(":", 1)[0].casefold() != allowed_remote.rstrip(":").casefold():
        raise RecipeValidationError(f"Rclone ROM source must use the {allowed_remote.rstrip(':')}: remote")
    normalized = str(PurePosixPath(match.group("path").replace("\\", "/"))).strip("/")
    if not any(normalized == root or normalized.startswith(root + "/") for root in ALLOWED_CLOUD_SOURCE_ROOTS):
        raise RecipeValidationError("Rclone ROM source must be inside WukongROM/sources or WukongROM/artifacts")


def path_is_under(path: Path, roots: Iterable[str | Path]) -> bool:
    resolved = path.expanduser().resolve()
    for value in roots:
        root = Path(value).expanduser().resolve()
        if resolved == root or root in resolved.parents:
            return True
    return False


def validate_recipe_access(
    recipe: BuildRecipe,
    identity: Identity,
    *,
    local_roots: Iterable[str | Path] = (),
    allowed_remote: str | None = None,
) -> None:
    if recipe.source.kind == "local":
        if identity.channel == "actions":
            raise RecipeValidationError("GitHub Actions recipes cannot reference a local file")
        if identity.channel == "telegram" and identity.role != "admin":
            raise RecipeValidationError("Telegram users cannot reference arbitrary local files")
        source = Path(recipe.source.uri).expanduser().resolve()
        roots = list(local_roots)
        if roots and not path_is_under(source, roots):
            raise RecipeValidationError("Local ROM source is outside configured roots")
    elif recipe.source.kind in {"http", "https"}:
        validate_http_url(recipe.source.uri)
    elif recipe.source.kind == "rclone":
        validate_rclone_source(recipe.source.uri, allowed_remote=allowed_remote or recipe.storage.remote)

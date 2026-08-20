from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .catalog import SHARED_MOD_NAMES
from .content_packs import (
    build_content_pack_record,
    upload_content_packs,
    validate_content_index,
)


DEFAULT_REMOTE = "wukong-gdrive:WukongROM/content-packs"
STANDARD_PACKS = {
    "copy-image/v1": "copy-image",
    "OFX/v1": "OFX",
    "TWRP/v1": "TWRP",
}
RUNTIME_PACKS = {
    "STARK/common": "STARK",
    "Flash_script/common": "Flash_script",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tree_manifest(root: Path) -> list[tuple[str, int, str]]:
    records: list[tuple[str, int, str]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append((path.relative_to(root).as_posix(), path.stat().st_size, digest.hexdigest()))
    return records


def _directory_is_writable(root: Path) -> bool:
    root.mkdir(parents=True, exist_ok=True)
    probe = root / f".wukong-write-{uuid.uuid4().hex}"
    try:
        probe.mkdir()
        return True
    except PermissionError:
        return False
    finally:
        try:
            probe.rmdir()
        except FileNotFoundError:
            pass


def _merge_runtime_tree_into_staging(install: Path, name: str) -> Path:
    runtime_tree = install / "Runtime" / name
    staged_tree = install / "Content" / name
    if runtime_tree.is_dir():
        staged_tree.mkdir(parents=True, exist_ok=True)
        shutil.copytree(runtime_tree, staged_tree, dirs_exist_ok=True, copy_function=shutil.copy2)
    return staged_tree


def migrate_shared_mods(install_root: Path, *, version: str = "ColorOS_16.0.10") -> list[str]:
    """Move verified shared MOD trees from a version pack into Runtime/STARK."""
    install = install_root.resolve()
    source_root = install / "Content" / "MOD" / version
    runtime_target = install / "Runtime" / "STARK"
    target_root = runtime_target if _directory_is_writable(runtime_target) else _merge_runtime_tree_into_staging(install, "STARK")
    staging_root = install / "Data" / "ContentSync" / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    migrated: list[str] = []
    for name in sorted(SHARED_MOD_NAMES, key=str.casefold):
        source = source_root / name
        if not source.is_dir():
            continue
        source_manifest = _tree_manifest(source)
        if not source_manifest:
            raise ValueError(f"Shared MOD source is empty: {source}")
        target = target_root / name
        if target.exists():
            if not target.is_dir() or _tree_manifest(target) != source_manifest:
                raise ValueError(
                    f"Shared MOD destination differs from {source}; merge it manually before migration: {target}"
                )
        else:
            target_root.mkdir(parents=True, exist_ok=True)
            staging = staging_root / f"{name}-{uuid.uuid4().hex}"
            try:
                shutil.copytree(source, staging, copy_function=shutil.copy2)
                if _tree_manifest(staging) != source_manifest:
                    raise OSError(f"Shared MOD verification failed: {name}")
                os.replace(staging, target)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        if _tree_manifest(target) != source_manifest:
            raise OSError(f"Shared MOD verification failed after migration: {name}")
        shutil.rmtree(source)
        migrated.append(name)
    return migrated


def discover_pack_sources(install_root: Path) -> dict[str, Path]:
    """Map each available pack ID to the root used by content-pack tooling."""
    install = install_root.resolve()
    content = install / "Content"
    runtime = install / "Runtime"
    result: dict[str, Path] = {}
    mod_root = content / "MOD"
    if mod_root.is_dir():
        for version in sorted((item for item in mod_root.iterdir() if item.is_dir()), key=lambda item: item.name.casefold()):
            if any(path.is_file() for path in version.rglob("*")):
                result[f"MOD/{version.name}"] = content
    for pack_id, target in STANDARD_PACKS.items():
        root = content / target
        if root.is_dir() and any(path.is_file() for path in root.rglob("*")):
            result[pack_id] = content
    for pack_id, target in RUNTIME_PACKS.items():
        source_base = runtime
        root = runtime / target
        if pack_id == "STARK/common":
            staged = content / "STARK"
            if staged.is_dir() and any((staged / name).is_dir() for name in SHARED_MOD_NAMES):
                _merge_runtime_tree_into_staging(install, "STARK")
                source_base = content
                root = staged
        elif pack_id == "Flash_script/common":
            staged = _merge_runtime_tree_into_staging(install, "Flash_script")
            source_base = content
            root = staged
        if root.is_dir() and any(path.is_file() for path in root.rglob("*")):
            result[pack_id] = source_base
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


def _pack_payload_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(key) == right.get(key) for key in ("id", "target", "remote", "sizeBytes", "files"))


def _atomic_write_index(path: Path, index: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def refresh_content_index(
    install_root: Path,
    index_path: Path,
    *,
    remote: str = DEFAULT_REMOTE,
) -> tuple[dict[str, Any], list[str]]:
    existing: dict[str, Any]
    if index_path.is_file():
        existing = json.loads(index_path.read_text(encoding="utf-8"))
        validate_content_index(existing)
    else:
        existing = {"schemaVersion": 1, "generatedAt": _timestamp(), "packs": []}
    old_by_id = {str(pack["id"]): pack for pack in existing["packs"]}
    packs: list[dict[str, Any]] = []
    changed: list[str] = []
    for pack_id, source_root in discover_pack_sources(install_root).items():
        generated = build_content_pack_record(source_root, remote=remote, pack_id=pack_id)
        old = old_by_id.get(pack_id)
        if old is not None and _pack_payload_equal(old, generated) and old.get("archive") is not None:
            generated = dict(generated)
            generated["archive"] = dict(old["archive"])
        else:
            changed.append(pack_id)
        packs.append(generated)
    index: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": _timestamp(),
        "packs": sorted(packs, key=lambda pack: str(pack["id"]).casefold()),
    }
    validate_content_index(index)
    _atomic_write_index(index_path, index)
    return index, changed


def upload_changed_packs(
    install_root: Path,
    index_path: Path,
    index: dict[str, Any],
    changed_pack_ids: list[str],
    *,
    rclone_config: Path,
    verify_download: bool = True,
) -> None:
    sources = discover_pack_sources(install_root)
    archive_root = install_root.resolve() / "Data" / "ContentSync" / "archives"
    for pack_id in changed_pack_ids:
        source_root = sources.get(pack_id)
        if source_root is None:
            raise KeyError(f"Content-pack source disappeared during sync: {pack_id}")
        upload_content_packs(
            source_root,
            index,
            rclone_config=rclone_config,
            verify_download=verify_download,
            archive_root=archive_root,
            pack_id=pack_id,
        )
        _atomic_write_index(index_path, index)


def assert_publishable(index: Mapping[str, Any]) -> None:
    validate_content_index(index)
    missing = [str(pack["id"]) for pack in index["packs"] if not isinstance(pack.get("archive"), Mapping)]
    if missing:
        raise ValueError(
            "Upload changed packs to Drive before publishing the GitHub manifest: " + ", ".join(missing)
        )


def publish_index_to_github(
    index_path: Path,
    *,
    repository: str,
    token: str,
    branch: str = "main",
    api_base: str = "https://api.github.com",
) -> str:
    if repository.count("/") != 1 or not all(part.strip() for part in repository.split("/")):
        raise ValueError("GitHub repository must be owner/name")
    if not token.strip():
        raise ValueError("GitHub token is required")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert_publishable(index)
    owner, name = repository.split("/", 1)
    endpoint = f"{api_base.rstrip('/')}/repos/{quote(owner)}/{quote(name)}/contents/content-packs/index.json"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Wukong-ROM-Studio/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    current_sha: str | None = None
    try:
        with urlopen(Request(f"{endpoint}?ref={quote(branch)}", headers=headers), timeout=30) as response:
            current_sha = str(json.loads(response.read())["sha"])
    except HTTPError as exc:
        if exc.code != 404:
            raise
    body: dict[str, Any] = {
        "message": "chore(content): sync verified platform packs",
        "content": base64.b64encode(index_path.read_bytes()).decode("ascii"),
        "branch": branch,
    }
    if current_sha:
        body["sha"] = current_sha
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read())
    return str(payload.get("commit", {}).get("sha") or "")

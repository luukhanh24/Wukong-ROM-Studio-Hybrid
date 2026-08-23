from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
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
SHARED_PACKS = {
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


def migrate_shared_mods(install_root: Path, *, version: str = "ColorOS_16.0.10") -> list[str]:
    """Move verified shared MOD trees into the canonical Content/STARK tree."""
    install = install_root.resolve()
    source_root = install / "Content" / "MOD" / version
    target_root = install / "Content" / "STARK"
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
    for pack_id, target in SHARED_PACKS.items():
        root = content / target
        if root.is_dir() and any(path.is_file() for path in root.rglob("*")):
            result[pack_id] = content
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_selected_content_pack(install_root: Path, selected_folder: Path) -> tuple[str, Path]:
    """Resolve a picked folder to the complete content-pack that must replace Drive."""
    install = install_root.resolve()
    selected = selected_folder.resolve()
    if not selected.is_dir():
        raise ValueError(f"Selected sync folder does not exist: {selected}")

    content = install / "Content"
    candidates = {**STANDARD_PACKS, **SHARED_PACKS}
    for pack_id, target in candidates.items():
        pack_root = content / target
        if pack_root.is_dir() and _is_within(selected, pack_root):
            return pack_id, pack_root

    mod_root = content / "MOD"
    if mod_root.is_dir() and _is_within(selected, mod_root) and selected != mod_root:
        relative = selected.relative_to(mod_root)
        version_root = mod_root / relative.parts[0]
        if version_root.is_dir():
            return f"MOD/{relative.parts[0]}", version_root

    raise ValueError(
        "Selected folder is not managed by content sync. Choose Content\\STARK, "
        "Content\\Flash_script, Content\\MOD\\<version>, Content\\copy-image, Content\\OFX, or Content\\TWRP."
    )


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


def restore_incomplete_index(index_path: Path, baseline_path: Path) -> int:
    """Restore interrupted pack records from the last shipped verified index."""
    index_path = index_path.resolve()
    baseline_path = baseline_path.resolve()
    if not index_path.is_file() or not baseline_path.is_file():
        return 0
    current = json.loads(index_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    validate_content_index(current)
    validate_content_index(baseline)
    baseline_by_id = {str(pack["id"]): dict(pack) for pack in baseline["packs"]}
    repaired = 0
    packs: list[dict[str, Any]] = []
    for pack in current["packs"]:
        current_pack = dict(pack)
        pack_id = str(current_pack["id"])
        fallback = baseline_by_id.get(pack_id)
        if not isinstance(current_pack.get("archive"), Mapping) and isinstance(
            fallback and fallback.get("archive"), Mapping
        ):
            packs.append(fallback)
            repaired += 1
        else:
            packs.append(current_pack)
    if repaired:
        restored = {
            "schemaVersion": 1,
            "generatedAt": current.get("generatedAt") or baseline.get("generatedAt") or _timestamp(),
            "packs": sorted(packs, key=lambda pack: str(pack["id"]).casefold()),
        }
        validate_content_index(restored)
        _atomic_write_index(index_path, restored)
    return repaired


def refresh_content_index(
    install_root: Path,
    index_path: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    only_pack_ids: set[str] | None = None,
    force_pack_ids: set[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    existing: dict[str, Any]
    if index_path.is_file():
        existing = json.loads(index_path.read_text(encoding="utf-8"))
        validate_content_index(existing)
    else:
        existing = {"schemaVersion": 1, "generatedAt": _timestamp(), "packs": []}
    old_by_id = {str(pack["id"]): pack for pack in existing["packs"]}
    sources = discover_pack_sources(install_root)
    selected = set(only_pack_ids) if only_pack_ids is not None else None
    forced = set(force_pack_ids or ())
    if selected is not None:
        missing = sorted(selected.difference(sources), key=str.casefold)
        if missing:
            raise ValueError("Selected content-pack source is missing: " + ", ".join(missing))
        if not forced.issubset(selected):
            raise ValueError("Forced content-packs must also be selected")
    packs: list[dict[str, Any]] = []
    changed: list[str] = []
    if selected is not None:
        packs.extend(dict(pack) for pack in existing["packs"] if str(pack["id"]) not in selected)
        source_items = ((pack_id, sources[pack_id]) for pack_id in sorted(selected, key=str.casefold))
    else:
        source_items = sources.items()
    for pack_id, source_root in source_items:
        generated = build_content_pack_record(source_root, remote=remote, pack_id=pack_id)
        old = old_by_id.get(pack_id)
        if (pack_id not in forced
                and old is not None
                and _pack_payload_equal(old, generated)
                and old.get("archive") is not None):
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
    progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    run_id: str | None = None,
) -> None:
    sources = discover_pack_sources(install_root)
    archive_root = install_root.resolve() / "Data" / "ContentSync" / "archives"
    for pack_index, pack_id in enumerate(changed_pack_ids, start=1):
        source_root = sources.get(pack_id)
        if source_root is None:
            raise KeyError(f"Content-pack source disappeared during sync: {pack_id}")
        def report(values: Mapping[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({
                    **values,
                    "packIndex": pack_index,
                    "packCount": len(changed_pack_ids),
                })

        upload_content_packs(
            source_root,
            index,
            rclone_config=rclone_config,
            verify_download=verify_download,
            archive_root=archive_root,
            pack_id=pack_id,
            progress_callback=report if progress_callback is not None else None,
            run_id=run_id,
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

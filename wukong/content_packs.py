from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

from .adapters import SourceIntegrityError, sha256_file


CONTENT_GROUPS = ("MOD", "copy-image", "OFX", "TWRP")
RunCommand = Callable[..., str]


def _run_text(args: list[str], **kwargs: object) -> str:
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )
    return result.stdout


def _file_records(root: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted((entry for entry in root.rglob("*") if entry.is_file()), key=lambda value: value.as_posix()):
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sizeBytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def build_content_index(content_root: Path, *, remote: str) -> dict[str, object]:
    content_root = content_root.resolve()
    base_remote = remote.rstrip("/")
    packs: list[dict[str, object]] = []
    mod_root = content_root / "MOD"
    if mod_root.is_dir():
        for version in sorted((entry for entry in mod_root.iterdir() if entry.is_dir()), key=lambda value: value.name):
            files = _file_records(version)
            if files:
                packs.append(
                    {
                        "id": f"MOD/{version.name}",
                        "target": f"MOD/{version.name}",
                        "remote": f"{base_remote}/MOD/{version.name}",
                        "sizeBytes": sum(int(item["sizeBytes"]) for item in files),
                        "files": files,
                    }
                )
    for name in ("copy-image", "OFX", "TWRP"):
        root = content_root / name
        if not root.is_dir():
            continue
        files = _file_records(root)
        if files:
            packs.append(
                {
                    "id": f"{name}/v1",
                    "target": name,
                    "remote": f"{base_remote}/{name}/v1",
                    "sizeBytes": sum(int(item["sizeBytes"]) for item in files),
                    "files": files,
                }
            )
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "packs": packs,
    }


def write_content_index(content_root: Path, output: Path, *, remote: str) -> dict[str, object]:
    index = build_content_index(content_root, remote=remote)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def validate_content_index(index: Mapping[str, Any]) -> None:
    if index.get("schemaVersion") != 1 or not isinstance(index.get("packs"), list):
        raise ValueError("Unsupported content-pack index")
    ids: set[str] = set()
    for pack in index["packs"]:
        if not isinstance(pack, Mapping):
            raise ValueError("Invalid content-pack entry")
        pack_id = str(pack.get("id") or "")
        target = str(pack.get("target") or "")
        if not pack_id or pack_id in ids or ".." in PurePosixPath(pack_id).parts:
            raise ValueError(f"Invalid or duplicate content-pack ID: {pack_id}")
        if not target or ".." in PurePosixPath(target).parts:
            raise ValueError(f"Invalid content-pack target: {target}")
        ids.add(pack_id)
        seen: set[str] = set()
        total = 0
        for item in pack.get("files", []):
            path = str(item.get("path") or "")
            if not path or path in seen or ".." in PurePosixPath(path).parts:
                raise ValueError(f"Invalid content-pack file path: {path}")
            seen.add(path)
            total += int(item.get("sizeBytes") or 0)
        if total != int(pack.get("sizeBytes") or 0):
            raise ValueError(f"Content-pack size total does not match: {pack_id}")


class ContentPackManager:
    def __init__(
        self,
        content_root: Path,
        *,
        run_command: RunCommand = _run_text,
        rclone_config: Path | None = None,
    ) -> None:
        self.content_root = content_root.resolve()
        self.run_command = run_command
        self.rclone_config = rclone_config

    def _rclone(self, *args: str) -> list[str]:
        command = ["rclone", *args]
        if self.rclone_config:
            command.extend(["--config", str(self.rclone_config)])
        return command

    def install(self, index: Mapping[str, Any], pack_id: str) -> Path:
        validate_content_index(index)
        pack = next((item for item in index["packs"] if item["id"] == pack_id), None)
        if not pack:
            raise KeyError(f"Unknown content-pack: {pack_id}")
        self.content_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="wukong-pack-", dir=self.content_root))
        target = (self.content_root / str(pack["target"])).resolve()
        if self.content_root not in target.parents:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError("Content-pack target escapes the content root")
        try:
            self.run_command(self._rclone("copy", str(pack["remote"]), str(staging), "--retries", "3"))
            self.verify(staging, pack)
            backup = target.with_name(target.name + ".previous")
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.rename(backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                staging.rename(target)
            except Exception:
                if backup.exists() and not target.exists():
                    backup.rename(target)
                raise
            shutil.rmtree(backup, ignore_errors=True)
            return target
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            backup = target.with_name(target.name + ".previous")
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise

    @staticmethod
    def verify(root: Path, pack: Mapping[str, Any]) -> None:
        expected = {str(item["path"]): item for item in pack.get("files", [])}
        actual = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file()
        }
        if set(actual) != set(expected):
            raise SourceIntegrityError(f"Invalid content-pack file set: {pack.get('id')}")
        for relative, item in expected.items():
            path = actual[relative]
            if path.stat().st_size != int(item["sizeBytes"]) or sha256_file(path) != item["sha256"]:
                raise SourceIntegrityError(f"Invalid content-pack checksum: {pack.get('id')}/{relative}")


def upload_content_packs(
    content_root: Path,
    index: Mapping[str, Any],
    *,
    run_command: RunCommand = _run_text,
    rclone_config: Path | None = None,
    verify_download: bool = True,
) -> None:
    validate_content_index(index)
    for pack in index["packs"]:
        source = content_root / str(pack["target"])
        args = ["rclone", "copy", str(source), str(pack["remote"]), "--checksum", "--retries", "3"]
        if rclone_config:
            args.extend(["--config", str(rclone_config)])
        run_command(args)
        if verify_download:
            with tempfile.TemporaryDirectory(prefix="wukong-pack-download-verify-") as root:
                manager = ContentPackManager(
                    Path(root),
                    run_command=run_command,
                    rclone_config=rclone_config,
                )
                installed = manager.install(index, str(pack["id"]))
                manager.verify(installed, pack)

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

from .adapters import SourceIntegrityError, sha256_file


CONTENT_GROUPS = ("MOD", "copy-image", "OFX", "TWRP", "STARK", "Flash_script")
SHARED_RUNTIME_PACKS = {
    "STARK/common": "STARK",
    "Flash_script/common": "Flash_script",
}
RunCommand = Callable[..., str]
ProgressCallback = Callable[[Mapping[str, object]], None]
ARCHIVE_CHUNK_SIZE = 1024 * 1024
ARCHIVE_FINALIZE_ATTEMPTS = 7
ARCHIVE_FINALIZE_RETRY_SECONDS = 0.1


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


def _parse_rclone_progress(line: str) -> dict[str, object] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    stats = payload.get("stats")
    if not isinstance(stats, Mapping):
        return None
    transfers = stats.get("transferring")
    active = transfers[0] if isinstance(transfers, list) and transfers and isinstance(transfers[0], Mapping) else {}
    transferred = int(active.get("bytes", stats.get("bytes", 0)) or 0)
    total = int(active.get("size", stats.get("totalBytes", 0)) or 0)
    speed = float(active.get("speed", stats.get("speed", 0)) or 0)
    eta_value = active.get("eta", stats.get("eta"))
    eta = float(eta_value) if isinstance(eta_value, (int, float)) else None
    percent = min(100.0, max(0.0, (transferred * 100.0 / total) if total > 0 else 0.0))
    return {
        "bytes": transferred,
        "totalBytes": total,
        "speedBytesPerSecond": speed,
        "etaSeconds": eta,
        "percent": percent,
    }


def _run_rclone_copy(args: list[str], progress_callback: ProgressCallback) -> str:
    command = [
        *args,
        "--use-json-log",
        "--stats", "500ms",
        "--stats-one-line",
        "--stats-log-level", "NOTICE",
        "--log-level", "NOTICE",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output.append(line)
        progress = _parse_rclone_progress(line)
        if progress is not None:
            progress_callback(progress)
    return_code = process.wait()
    combined = "".join(output)
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command, output=combined)
    return combined


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


def _relative_parts(value: object, *, label: str) -> tuple[str, ...]:
    raw = str(value or "").replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or "\x00" in raw
        or path.is_absolute()
        or raw != path.as_posix()
        or any(part in ("", ".", "..") for part in raw.split("/"))
        or any(":" in part for part in path.parts)
    ):
        raise ValueError(f"Invalid {label}: {value}")
    return path.parts


def build_content_pack_record(
    content_root: Path,
    *,
    remote: str,
    pack_id: str,
) -> dict[str, object]:
    parts = _relative_parts(pack_id, label="content-pack ID")
    if len(parts) == 2 and parts[0] == "MOD":
        target = f"MOD/{parts[1]}"
    elif len(parts) == 2 and parts[0] in {"copy-image", "OFX", "TWRP"} and parts[1] == "v1":
        target = parts[0]
    elif pack_id in SHARED_RUNTIME_PACKS:
        target = SHARED_RUNTIME_PACKS[pack_id]
    else:
        raise KeyError(f"Unknown content-pack: {pack_id}")
    root = content_root.resolve().joinpath(*PurePosixPath(target).parts)
    if not root.is_dir():
        raise KeyError(f"Content-pack source does not exist: {pack_id}")
    files = _file_records(root)
    if not files:
        raise ValueError(f"Content-pack source is empty: {pack_id}")
    return {
        "id": pack_id,
        "target": target,
        "remote": f"{remote.rstrip('/')}/{pack_id}",
        "sizeBytes": sum(int(item["sizeBytes"]) for item in files),
        "files": files,
    }


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
    for pack_id, target in SHARED_RUNTIME_PACKS.items():
        root = content_root / target
        if not root.is_dir():
            continue
        files = _file_records(root)
        if files:
            packs.append(
                {
                    "id": pack_id,
                    "target": target,
                    "remote": f"{base_remote}/{pack_id}",
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


def merge_content_index_pack(
    existing: Mapping[str, Any],
    generated: Mapping[str, Any],
    pack_id: str,
) -> dict[str, object]:
    validate_content_index(existing)
    validate_content_index(generated)
    replacement = next(
        (dict(pack) for pack in generated["packs"] if pack.get("id") == pack_id),
        None,
    )
    if replacement is None:
        raise KeyError(f"Unknown generated content-pack: {pack_id}")
    packs = [dict(pack) for pack in existing["packs"] if pack.get("id") != pack_id]
    packs.append(replacement)
    packs.sort(key=lambda pack: str(pack.get("id") or "").casefold())
    return {
        "schemaVersion": 1,
        "generatedAt": generated.get("generatedAt"),
        "packs": packs,
    }


def validate_content_index(index: Mapping[str, Any]) -> None:
    if index.get("schemaVersion") != 1 or not isinstance(index.get("packs"), list):
        raise ValueError("Unsupported content-pack index")
    ids: set[str] = set()
    for pack in index["packs"]:
        if not isinstance(pack, Mapping):
            raise ValueError("Invalid content-pack entry")
        pack_id = str(pack.get("id") or "")
        target = str(pack.get("target") or "")
        try:
            _relative_parts(pack_id, label="content-pack ID")
        except ValueError as exc:
            raise ValueError(f"Invalid or duplicate content-pack ID: {pack_id}") from exc
        if pack_id in ids:
            raise ValueError(f"Invalid or duplicate content-pack ID: {pack_id}")
        _relative_parts(target, label="content-pack target")
        ids.add(pack_id)
        seen: set[str] = set()
        total = 0
        for item in pack.get("files", []):
            path = str(item.get("path") or "")
            try:
                _relative_parts(path, label="content-pack file path")
            except ValueError as exc:
                raise ValueError(f"Invalid content-pack file path: {path}") from exc
            if path in seen:
                raise ValueError(f"Invalid content-pack file path: {path}")
            seen.add(path)
            total += int(item.get("sizeBytes") or 0)
        if total != int(pack.get("sizeBytes") or 0):
            raise ValueError(f"Content-pack size total does not match: {pack_id}")
        archive = pack.get("archive")
        if archive is not None:
            if not isinstance(archive, Mapping):
                raise ValueError(f"Invalid content-pack archive: {pack_id}")
            uri = str(archive.get("uri") or "")
            digest = str(archive.get("sha256") or "").casefold()
            md5 = str(archive.get("md5") or "").casefold()
            size = int(archive.get("sizeBytes") or -1)
            if (
                not uri
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or len(md5) != 32
                or any(character not in "0123456789abcdef" for character in md5)
                or size < 0
            ):
                raise ValueError(f"Invalid content-pack archive: {pack_id}")


def _archive_tar_filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    member.mtime = 0
    member.mode = 0o755 if member.isdir() else 0o644
    member.pax_headers = {}
    return member


def _md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(ARCHIVE_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_archive_members(
    archive: tarfile.TarFile,
    pack: Mapping[str, Any] | None = None,
) -> list[tarfile.TarInfo]:
    expected = None if pack is None else {str(item["path"]): item for item in pack.get("files", [])}
    members: list[tarfile.TarInfo] = []
    seen: set[str] = set()
    for member in archive.getmembers():
        normalized = member.name.replace("\\", "/")
        try:
            _relative_parts(normalized, label="content-pack archive member")
        except ValueError as exc:
            raise SourceIntegrityError(
                f"unsafe content-pack archive member: {member.name!r}"
            ) from exc
        if normalized in seen or not (member.isdir() or member.isfile()):
            raise SourceIntegrityError(f"unsafe content-pack archive member: {member.name!r}")
        seen.add(normalized)
        members.append(member)
    if expected is not None:
        files = {member.name.replace("\\", "/"): member for member in members if member.isfile()}
        if set(files) != set(expected):
            raise SourceIntegrityError(f"Invalid content-pack archive file set: {pack.get('id')}")
        for relative, item in expected.items():
            member = files[relative]
            if member.size != int(item["sizeBytes"]):
                raise SourceIntegrityError(
                    f"Invalid content-pack archive checksum: {pack.get('id')}/{relative}"
                )
            source = archive.extractfile(member)
            if source is None:
                raise SourceIntegrityError(f"Invalid content-pack archive member: {relative!r}")
            digest = hashlib.sha256()
            with source:
                for chunk in iter(lambda: source.read(ARCHIVE_CHUNK_SIZE), b""):
                    digest.update(chunk)
            if digest.hexdigest() != item["sha256"]:
                raise SourceIntegrityError(
                    f"Invalid content-pack archive checksum: {pack.get('id')}/{relative}"
                )
    file_paths = {
        PurePosixPath(member.name.replace("\\", "/"))
        for member in members
        if member.isfile()
    }
    for member in members:
        path = PurePosixPath(member.name.replace("\\", "/"))
        if any(parent in file_paths for parent in path.parents):
            raise SourceIntegrityError(
                f"unsafe content-pack archive member has a file parent: {member.name!r}"
            )
    return members


def _zstd_binary() -> str:
    bundled = Path(__file__).resolve().parents[1] / "bin" / "Windows" / "AMD64" / "zstd.exe"
    if os.name == "nt" and bundled.is_file():
        return str(bundled)
    executable = shutil.which("zstd")
    if not executable:
        raise RuntimeError("zstd is required to create or install compressed content-packs")
    return executable


def _finalize_archive(source: Path, destination: Path) -> None:
    """Atomically publish an archive despite short-lived Windows file locks."""
    for attempt in range(ARCHIVE_FINALIZE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if destination.exists():
                try:
                    destination.chmod(destination.stat().st_mode | stat.S_IWRITE)
                except (FileNotFoundError, PermissionError):
                    pass
            if attempt + 1 == ARCHIVE_FINALIZE_ATTEMPTS:
                raise
            time.sleep(min(ARCHIVE_FINALIZE_RETRY_SECONDS * (2**attempt), 1.0))


def create_content_pack_archive(
    content_root: Path,
    pack: Mapping[str, Any],
    output: Path,
) -> dict[str, object]:
    """Create a deterministic, regular-file-only TAR payload for one pack."""
    content_root = content_root.resolve()
    target_parts = _relative_parts(pack["target"], label="content-pack target")
    source = content_root.joinpath(*target_parts).resolve()
    if content_root not in source.parents:
        raise ValueError("Content-pack source escapes the content root")
    if not source.is_dir():
        raise FileNotFoundError(source)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    compressed = output.name.casefold().endswith((".tar.zst", ".tzst"))
    tar_path = output.with_suffix("") if compressed else output
    if compressed and tar_path.suffix.casefold() != ".tar":
        tar_path = output.with_name(output.name + ".tar")
    temporary_tar = tar_path.with_name(tar_path.name + ".partial")
    temporary_output = output.with_name(output.name + ".partial")
    try:
        with tarfile.open(temporary_tar, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for item in pack.get("files", []):
                relative = PurePosixPath(
                    *_relative_parts(item["path"], label="content-pack file path")
                )
                path = source.joinpath(*relative.parts)
                resolved_path = path.resolve()
                if (
                    source not in resolved_path.parents
                    or path.is_symlink()
                    or not resolved_path.is_file()
                ):
                    raise SourceIntegrityError(
                        f"Content-pack contains a missing or symbolic file: {pack.get('id')}/{relative}"
                    )
                archive.add(
                    resolved_path,
                    arcname=relative.as_posix(),
                    recursive=False,
                    filter=_archive_tar_filter,
                )
        with tarfile.open(temporary_tar, mode="r:") as archive:
            _validate_archive_members(archive, pack)
        if compressed:
            subprocess.run(
                # Content packs can be multi-GB. zstd's automatic worker count
                # keeps the archive format/checksum validation unchanged while
                # avoiding a single-core bottleneck in the Windows sync flow.
                [_zstd_binary(), "-q", "-f", "-T0", "-3", str(temporary_tar), "-o", str(temporary_output)],
                check=True,
            )
            _finalize_archive(temporary_output, output)
        else:
            _finalize_archive(temporary_tar, output)
        return {
            "uri": str(pack["remote"]).rstrip("/") + (".tar.zst" if compressed else ".tar"),
            "sizeBytes": output.stat().st_size,
            "sha256": sha256_file(output),
            "md5": _md5_file(output),
        }
    finally:
        temporary_tar.unlink(missing_ok=True)
        temporary_output.unlink(missing_ok=True)


def _extract_content_pack_archive(
    archive_path: Path,
    destination: Path,
    *,
    maximum_tar_bytes: int,
) -> None:
    tar_path = archive_path
    temporary_tar: Path | None = None
    if archive_path.name.casefold().endswith((".tar.zst", ".tzst")):
        temporary_tar = archive_path.with_name(archive_path.name + ".expanded.tar")
        with temporary_tar.open("wb") as output:
            process = subprocess.Popen(
                [_zstd_binary(), "-q", "-d", "-c", str(archive_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert process.stdout is not None
            expanded = 0
            try:
                for chunk in iter(lambda: process.stdout.read(ARCHIVE_CHUNK_SIZE), b""):
                    expanded += len(chunk)
                    if expanded > maximum_tar_bytes:
                        raise SourceIntegrityError("Content-pack archive exceeds its safe expanded size")
                    output.write(chunk)
                stderr = process.communicate()[1]
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, process.args, stderr=stderr)
            except Exception:
                process.kill()
                process.wait()
                raise
        tar_path = temporary_tar
    try:
        with tarfile.open(tar_path, mode="r:") as archive:
            members = _validate_archive_members(archive)
            destination.mkdir(parents=True, exist_ok=True)
            for member in members:
                relative = PurePosixPath(member.name.replace("\\", "/"))
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise SourceIntegrityError(
                        f"Invalid content-pack archive member: {member.name!r}"
                    )
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, ARCHIVE_CHUNK_SIZE)
    except (tarfile.TarError, OSError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, SourceIntegrityError):
            raise
        raise SourceIntegrityError(f"Invalid content-pack archive: {exc}") from exc
    finally:
        if temporary_tar is not None:
            temporary_tar.unlink(missing_ok=True)


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
        archive_path: Path | None = None
        target = (self.content_root / str(pack["target"])).resolve()
        if self.content_root not in target.parents:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError("Content-pack target escapes the content root")
        try:
            archive = pack.get("archive")
            if archive:
                archive_uri = str(archive["uri"])
                suffix = ".tar.zst" if archive_uri.casefold().endswith((".tar.zst", ".tzst")) else ".tar"
                archive_path = staging.with_name(staging.name + suffix)
                self.run_command(
                    self._rclone("copyto", archive_uri, str(archive_path), "--retries", "3")
                )
                expected_size = int(archive["sizeBytes"])
                actual_size = archive_path.stat().st_size
                if actual_size != expected_size:
                    raise SourceIntegrityError(
                        f"Content-pack archive size mismatch: expected {expected_size}, got {actual_size}"
                    )
                expected_digest = str(archive["sha256"]).casefold()
                actual_digest = sha256_file(archive_path)
                if actual_digest != expected_digest:
                    raise SourceIntegrityError(
                        f"Content-pack archive checksum mismatch: expected {expected_digest}, got {actual_digest}"
                    )
                file_count = len(pack.get("files", []))
                maximum_tar_bytes = int(pack["sizeBytes"]) + file_count * 4096 + 16 * 1024 * 1024
                _extract_content_pack_archive(
                    archive_path,
                    staging,
                    maximum_tar_bytes=maximum_tar_bytes,
                )
                archive_path.unlink(missing_ok=True)
            else:
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
            if archive_path is not None:
                archive_path.unlink(missing_ok=True)
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
    archive_root: Path | None = None,
    pack_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    validate_content_index(index)
    archive_root = (archive_root or content_root / ".wkstudio" / "content-pack-archives").resolve()
    selected = [pack for pack in index["packs"] if pack_id is None or pack["id"] == pack_id]
    if pack_id is not None and not selected:
        raise KeyError(f"Unknown content-pack: {pack_id}")
    for pack_index, pack in enumerate(selected, start=1):
        def report(phase: str, **values: object) -> None:
            if progress_callback is not None:
                progress_callback({
                    "phase": phase,
                    "packId": str(pack["id"]),
                    "packIndex": pack_index,
                    "packCount": len(selected),
                    **values,
                })

        ContentPackManager.verify(content_root / str(pack["target"]), pack)
        archive_root.mkdir(parents=True, exist_ok=True)
        archive_stem = str(pack["id"]).replace("/", "-")
        archive_path = archive_root / f"{archive_stem}.{uuid.uuid4().hex}.tar.zst"
        try:
            report("archive")
            archive_record = create_content_pack_archive(content_root, pack, archive_path)
            report(
                "upload",
                bytes=0,
                totalBytes=int(archive_record["sizeBytes"]),
                speedBytesPerSecond=0.0,
                etaSeconds=None,
                percent=0.0,
            )
            args = [
                "rclone", "copyto", str(archive_path), str(archive_record["uri"]),
                "--retries", "3", "--transfers", "1", "--checkers", "1", "--tpslimit", "2",
            ]
            if rclone_config:
                args.extend(["--config", str(rclone_config)])
            if progress_callback is not None and run_command is _run_text:
                _run_rclone_copy(args, lambda values: report("upload", **values))
            else:
                run_command(args)
            report("verify-remote", bytes=int(archive_record["sizeBytes"]), totalBytes=int(archive_record["sizeBytes"]), percent=100.0)
            size_args = ["rclone", "size", str(archive_record["uri"]), "--json"]
            if rclone_config:
                size_args.extend(["--config", str(rclone_config)])
            remote_size = json.loads(run_command(size_args))
            if int(remote_size.get("count", 0)) != 1 or int(remote_size.get("bytes", -1)) != int(
                archive_record["sizeBytes"]
            ):
                raise SourceIntegrityError(f"Remote content-pack size mismatch: {pack['id']}")
            md5_args = ["rclone", "md5sum", str(archive_record["uri"])]
            if rclone_config:
                md5_args.extend(["--config", str(rclone_config)])
            remote_md5 = run_command(md5_args).strip().split(maxsplit=1)[0].casefold()
            if remote_md5 != archive_record["md5"]:
                raise SourceIntegrityError(f"Remote content-pack checksum mismatch: {pack['id']}")
            if verify_download:
                report("verify-download", bytes=int(archive_record["sizeBytes"]), totalBytes=int(archive_record["sizeBytes"]), percent=100.0)
                with tempfile.TemporaryDirectory(prefix="wukong-pack-download-verify-") as root:
                    verification_index = dict(index)
                    verification_index["packs"] = [
                        ({**candidate, "archive": archive_record} if candidate is pack else candidate)
                        for candidate in index["packs"]
                    ]
                    manager = ContentPackManager(
                        Path(root),
                        run_command=run_command,
                        rclone_config=rclone_config,
                    )
                    installed = manager.install(verification_index, str(pack["id"]))
                    manager.verify(installed, pack)
            pack["archive"] = archive_record
            report("complete", bytes=int(archive_record["sizeBytes"]), totalBytes=int(archive_record["sizeBytes"]), percent=100.0)
        finally:
            archive_path.unlink(missing_ok=True)

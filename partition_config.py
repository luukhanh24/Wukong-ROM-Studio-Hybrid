from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


FC_SPECIAL_CHARS = re.compile(r"([.+\[\](){}^$|?*])")
TREE_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class PartitionConfigError(RuntimeError):
    pass


def fc_escape(path: str) -> str:
    return FC_SPECIAL_CHARS.sub(r"\\\1", path)


def _fc_unescape(path: str) -> str:
    return re.sub(r"\\(.)", r"\1", path)


def _is_literal_context_pattern(pattern: str) -> bool:
    escaped = False
    for char in pattern:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in ".+[](){}^$|?*":
            return False
    return True


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized or "/"


def _read_required_lines(path: Path, label: str) -> list[str]:
    if not path.is_file():
        raise PartitionConfigError(f"Missing {label}: {path}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not any(line.strip() for line in lines):
        raise PartitionConfigError(f"Empty {label}: {path}")
    return lines


def validate_partition_configs(
    unpacked_dir: str | Path,
    part_name: str,
    filesystem_type: str | None = None,
) -> dict[str, Path]:
    unpacked = Path(unpacked_dir)
    data_dir = unpacked / part_name
    config_dir = unpacked / "config"
    fs_config = config_dir / f"{part_name}_fs_config"
    file_contexts = config_dir / f"{part_name}_file_contexts"
    if not data_dir.is_dir():
        raise PartitionConfigError(f"Missing extracted partition directory: {data_dir}")
    _read_required_lines(fs_config, "fs_config")
    _read_required_lines(file_contexts, "file_contexts")
    paths = {
        "dataDir": data_dir,
        "configDir": config_dir,
        "fsConfig": fs_config,
        "fileContexts": file_contexts,
    }
    if filesystem_type == "erofs":
        fs_options = config_dir / f"{part_name}_fs_options"
        _read_required_lines(fs_options, "EROFS options")
        paths["fsOptions"] = fs_options
    elif filesystem_type == "ext4":
        size_config = config_dir / f"{part_name}_size.txt"
        lines = _read_required_lines(size_config, "EXT4 source size")
        try:
            if int(lines[0].strip()) <= 0:
                raise ValueError
        except ValueError as exc:
            raise PartitionConfigError(f"Invalid EXT4 source size: {size_config}") from exc
        paths["sizeConfig"] = size_config
    return paths


def _actual_paths(data_dir: Path) -> set[str]:
    data_parent = data_dir.parent
    paths: set[str] = set()
    for root, dirs, files in os.walk(data_dir, followlinks=False):
        root_path = Path(root)
        relative_root = root_path.relative_to(data_parent).as_posix()
        paths.add(_normalized_path(relative_root))
        for name in files:
            paths.add(_normalized_path(f"{relative_root}/{name}"))
        for name in dirs:
            full_path = root_path / name
            if full_path.is_symlink():
                paths.add(_normalized_path(f"{relative_root}/{name}"))
    return paths


def _parse_fs_entries(lines: list[str]) -> dict[str, str]:
    entries = {}
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            entries.setdefault(_normalized_path(parts[0]), line.strip())
    return entries


def _parse_fc_entries(lines: list[str]) -> list[tuple[str, str]]:
    entries = []
    for line in lines:
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1]))
    return entries


def _parent_paths(path: str) -> list[str]:
    current = _normalized_path(path)
    parents = []
    while "/" in current:
        current = current.rsplit("/", 1)[0]
        if not current:
            break
        parents.append(current)
    return parents


def _fs_owner(entries: dict[str, str], path: str) -> tuple[str, str]:
    for parent in _parent_paths(path):
        line = entries.get(parent)
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            return parts[1], parts[2]
    return "0", "0"


def _new_fs_line(data_parent: Path, path: str, entries: dict[str, str]) -> str:
    full_path = data_parent / Path(path)
    uid, gid = _fs_owner(entries, path)
    if full_path.is_symlink():
        target = os.readlink(full_path).replace("\\", "/")
        return f"{path} {uid} {gid} 0644 {target}"
    if full_path.is_dir():
        return f"{path} {uid} {gid} 0755"
    executable = "/bin/" in f"/{path}" or "/xbin/" in f"/{path}" or path.endswith(".sh")
    return f"{path} {uid} {gid} {'0755' if executable else '0644'}"


class _ContextIndex:
    def __init__(self, entries: list[tuple[str, str]]) -> None:
        self._next_order = 0
        self._exact: dict[str, tuple[int, str]] = {}
        self._regex: list[tuple[int, re.Pattern[str], str]] = []
        for pattern, context in entries:
            self.add(pattern, context)

    def add(self, pattern: str, context: str) -> None:
        order = self._next_order
        self._next_order += 1
        if _is_literal_context_pattern(pattern):
            self._exact[_fc_unescape(pattern)] = (order, context)
            return
        try:
            compiled = re.compile(pattern)
        except re.error:
            self._exact[pattern] = (order, context)
            return
        self._regex.append((order, compiled, context))

    def matches(self, path: str) -> bool:
        if path in self._exact:
            return True
        return any(pattern.fullmatch(path) is not None for _order, pattern, _context in self._regex)

    def context_for(self, path: str) -> str | None:
        exact = self._exact.get(path)
        exact_order = exact[0] if exact else -1
        for order, pattern, context in reversed(self._regex):
            if order <= exact_order:
                break
            if pattern.fullmatch(path) is not None:
                return context
        return exact[1] if exact else None


def _context_for_path(
    index: _ContextIndex,
    path: str,
    part_name: str,
) -> str:
    for parent in _parent_paths(path.lstrip("/")):
        candidate = f"/{parent}"
        context = index.context_for(candidate)
        if context is not None:
            return context
    if "/etc/init" in path and part_name in {"vendor", "odm"}:
        return "u:object_r:vendor_configs_file:s0"
    if part_name in {"vendor", "vendor_dlkm", "odm", "my_heytap", "my_stock", "my_company", "my_preload"}:
        return "u:object_r:vendor_file:s0"
    return "u:object_r:system_file:s0"


def _write_text_lf(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode(encoding))


def sync_partition_configs(unpacked_dir: str | Path, part_name: str) -> dict[str, Any]:
    paths = validate_partition_configs(unpacked_dir, part_name)
    data_dir = paths["dataDir"]
    fs_config = paths["fsConfig"]
    file_contexts = paths["fileContexts"]
    actual_paths = _actual_paths(data_dir)

    fs_lines = _read_required_lines(fs_config, "fs_config")
    fs_entries = _parse_fs_entries(fs_lines)
    added_fs_entries = []
    for path in sorted(actual_paths):
        if path in fs_entries:
            continue
        line = _new_fs_line(data_dir.parent, path, fs_entries)
        fs_lines.append(line)
        fs_entries[path] = line
        added_fs_entries.append(line)
    if added_fs_entries:
        _write_text_lf(fs_config, "\n".join(fs_lines) + "\n")

    fc_lines = _read_required_lines(file_contexts, "file_contexts")
    fc_entries = _parse_fc_entries(fc_lines)
    fc_index = _ContextIndex(fc_entries)
    added_fc_entries = []
    for relative_path in sorted(actual_paths):
        path = f"/{relative_path}"
        if fc_index.matches(path):
            continue
        escaped = fc_escape(path)
        context = _context_for_path(fc_index, path, part_name)
        line = f"{escaped} {context}"
        fc_lines.append(line)
        fc_entries.append((escaped, context))
        fc_index.add(escaped, context)
        added_fc_entries.append(line)
    if added_fc_entries:
        _write_text_lf(file_contexts, "\n".join(fc_lines) + "\n")

    return {
        "partition": part_name,
        "scannedPaths": len(actual_paths),
        "addedFs": len(added_fs_entries),
        "addedFileContexts": len(added_fc_entries),
        "addedFsEntries": added_fs_entries,
        "addedFileContextEntries": added_fc_entries,
        "removedFs": 0,
        "removedFileContexts": 0,
    }


def sync_all_partition_configs(rom_unpack_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(rom_unpack_dir)
    if not root.is_dir():
        raise PartitionConfigError(f"Missing unpack directory: {root}")
    reports = []
    for unpacked in sorted(root.glob("*_unpacked"), key=lambda path: path.name):
        part_name = unpacked.name.removesuffix("_unpacked")
        print(f"[*] Sync metadata: {part_name}", flush=True)
        report = sync_partition_configs(unpacked, part_name)
        reports.append(report)
        print(
            f"    [OK] {part_name}: scanned={report['scannedPaths']} "
            f"fs_config(+{report['addedFs']}) "
            f"file_contexts(+{report['addedFileContexts']})",
            flush=True,
        )
    if not reports:
        raise PartitionConfigError(f"No unpacked partitions found: {root}")
    return reports


def _normalized_config_line(line: str) -> str:
    return " ".join(line.split())


def _fs_config_entries(lines: list[str]) -> dict[str, tuple[str, str, str, tuple[str, ...]]]:
    entries = {}
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            extras = tuple(
                sorted(
                    value
                    for value in parts[4:]
                    if value.lower() not in {"capabilities=0", "capabilities=0x0"}
                )
            )
            entries[_normalized_path(parts[0])] = (parts[1], parts[2], parts[3], extras)
    return entries


def _tree_profile(root: Path) -> dict[str, tuple[str, str | None]]:
    profile = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            profile[relative] = ("link", os.readlink(path).replace("\\", "/"))
        elif path.is_dir():
            profile[relative] = ("dir", None)
        else:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            profile[relative] = ("file", digest.hexdigest())
    return profile


def partition_tree_fingerprint(root: str | Path) -> str:
    data_dir = Path(root)
    if not data_dir.is_dir():
        raise PartitionConfigError(f"Missing partition data directory: {data_dir}")
    digest = hashlib.sha256()
    for relative, (entry_type, value) in sorted(_tree_profile(data_dir).items()):
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(entry_type.encode("ascii"))
        digest.update(b"\0")
        if value is not None:
            digest.update(value.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\n")
    return digest.hexdigest()


def partition_repack_fingerprint(unpacked_dir: str | Path, part_name: str) -> str:
    unpacked = Path(unpacked_dir)
    digest = hashlib.sha256()
    digest.update(partition_tree_fingerprint(unpacked / part_name).encode("ascii"))
    digest.update(b"\n")
    config_dir = unpacked / "config"
    for suffix in ("fs_config", "file_contexts", "fs_options", "size.txt"):
        path = config_dir / f"{part_name}_{suffix}"
        if not path.is_file():
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\n")
    return digest.hexdigest()


def partition_tree_fingerprint_path(unpacked_dir: str | Path, part_name: str) -> Path:
    return Path(unpacked_dir) / "config" / f"{part_name}_tree.sha256"


def write_partition_tree_fingerprint(unpacked_dir: str | Path, part_name: str) -> str:
    unpacked = Path(unpacked_dir)
    fingerprint = partition_repack_fingerprint(unpacked, part_name)
    path = partition_tree_fingerprint_path(unpacked, part_name)
    _write_text_lf(path, f"{fingerprint}\n", encoding="ascii")
    return fingerprint


def read_partition_tree_fingerprint(unpacked_dir: str | Path, part_name: str) -> str:
    path = partition_tree_fingerprint_path(unpacked_dir, part_name)
    if not path.is_file():
        raise PartitionConfigError(
            f"{part_name}: missing unpack fingerprint; unpack the ROM again before repacking"
        )
    fingerprint = path.read_text(encoding="ascii", errors="replace").strip()
    if not TREE_FINGERPRINT_RE.fullmatch(fingerprint):
        raise PartitionConfigError(f"{part_name}: invalid unpack fingerprint: {path}")
    return fingerprint


def _validate_config_roundtrip(
    expected_config_dir: Path,
    actual_config_dir: Path,
    data_dir: Path,
    part_name: str,
) -> dict[str, int]:
    actual_paths = _actual_paths(data_dir)
    expected_fs = _fs_config_entries(
        _read_required_lines(expected_config_dir / f"{part_name}_fs_config", "fs_config")
    )
    actual_fs = _fs_config_entries(
        _read_required_lines(actual_config_dir / f"{part_name}_fs_config", "round-trip fs_config")
    )
    expected_contexts = _ContextIndex(
        _parse_fc_entries(
            _read_required_lines(
                expected_config_dir / f"{part_name}_file_contexts",
                "file_contexts",
            )
        )
    )
    actual_contexts = _ContextIndex(
        _parse_fc_entries(
            _read_required_lines(
                actual_config_dir / f"{part_name}_file_contexts",
                "round-trip file_contexts",
            )
        )
    )
    for relative_path in sorted(actual_paths):
        expected_line = expected_fs.get(relative_path)
        actual_line = actual_fs.get(relative_path)
        if expected_line is None:
            raise PartitionConfigError(f"{part_name}: fs_config is missing input path: {relative_path}")
        if actual_line != expected_line:
            raise PartitionConfigError(
                f"{part_name}: fs_config changed after repack: {relative_path}; "
                f"expected={expected_line!r}, actual={actual_line!r}"
            )
        path = f"/{relative_path}"
        expected_context = expected_contexts.context_for(path)
        actual_context = actual_contexts.context_for(path)
        if expected_context is None:
            raise PartitionConfigError(f"{part_name}: SELinux context is missing input path: {path}")
        if actual_context != expected_context:
            raise PartitionConfigError(
                f"{part_name}: SELinux context changed after repack: {path}"
            )
    return {"paths": len(actual_paths)}


EROFS_LISTING_RE = re.compile(
    r"^Extract: type=(?P<type>[A-Z]+) .*?fsConfig=\[(?P<config>/.*?)\] "
    r"seLabel=\[(?P<context>.*?)\]$"
)
WINDOWS_SYMLINK_MAGIC = b"!<symlink>"


def _expected_erofs_type(path: Path) -> str:
    if path.is_symlink():
        return "LINK"
    if path.is_dir():
        return "DIR"
    if path.is_file():
        with path.open("rb") as handle:
            if handle.read(len(WINDOWS_SYMLINK_MAGIC)) == WINDOWS_SYMLINK_MAGIC:
                return "LINK"
        return "FILE"
    raise PartitionConfigError(f"Unsupported extracted filesystem entry: {path}")


def _validate_erofs_roundtrip(
    unpacked_dir: Path,
    part_name: str,
    output_img: Path,
    extract_erofs: str | Path,
) -> dict[str, int]:
    command = [str(extract_erofs), "-i", str(output_img), "-p"]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise PartitionConfigError(f"{part_name}: cannot inspect repacked EROFS image")
    expected_config_dir = unpacked_dir / "config"
    expected_fs = _fs_config_entries(
        _read_required_lines(expected_config_dir / f"{part_name}_fs_config", "fs_config")
    )
    expected_contexts = _ContextIndex(
        _parse_fc_entries(
            _read_required_lines(
                expected_config_dir / f"{part_name}_file_contexts",
                "file_contexts",
            )
        )
    )
    entries: dict[str, tuple[str, tuple[str, str, str, tuple[str, ...]], str]] = {}
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        match = EROFS_LISTING_RE.match(line)
        if not match:
            continue
        config_parts = match.group("config").split()
        if len(config_parts) < 4:
            raise PartitionConfigError(f"{part_name}: invalid EROFS fs_config listing")
        image_path = config_parts[0]
        relative_path = part_name if image_path == "/" else f"{part_name}{image_path}"
        normalized_path = _normalized_path(relative_path)
        if normalized_path in entries:
            raise PartitionConfigError(
                f"{part_name}: duplicate EROFS listing path: {normalized_path}"
            )
        actual_fs = _fs_config_entries(
            [" ".join([normalized_path, *config_parts[1:]])]
        ).get(normalized_path)
        if actual_fs is None:
            raise PartitionConfigError(
                f"{part_name}: invalid EROFS fs_config for {normalized_path}"
            )
        entries[normalized_path] = (
            match.group("type"),
            actual_fs,
            match.group("context"),
        )
    data_dir = unpacked_dir / part_name
    actual_paths = _actual_paths(data_dir)
    if set(entries) != actual_paths:
        missing = sorted(actual_paths - set(entries))
        extra = sorted(set(entries) - actual_paths)
        raise PartitionConfigError(
            f"{part_name}: EROFS path mismatch after repack; missing={missing[:3]}, extra={extra[:3]}"
        )
    for relative_path, (output_type, actual_fs, actual_context) in entries.items():
        disk_path = data_dir.parent / Path(relative_path)
        expected_type = "DIR" if relative_path == part_name else _expected_erofs_type(disk_path)
        if output_type != expected_type:
            raise PartitionConfigError(
                f"{part_name}: EROFS type changed after repack: {relative_path} "
                f"({expected_type} -> {output_type})"
            )
        expected_fs_entry = expected_fs.get(relative_path)
        if expected_fs_entry is None:
            raise PartitionConfigError(
                f"{part_name}: fs_config is missing input path: {relative_path}"
            )
        if actual_fs != expected_fs_entry:
            raise PartitionConfigError(
                f"{part_name}: fs_config changed after repack: {relative_path}; "
                f"expected={expected_fs_entry!r}, actual={actual_fs!r}"
            )
        expected_context = expected_contexts.context_for(f"/{relative_path}")
        if expected_context is None:
            raise PartitionConfigError(
                f"{part_name}: SELinux context is missing input path: /{relative_path}"
            )
        if actual_context != expected_context:
            raise PartitionConfigError(
                f"{part_name}: SELinux context changed after repack: /{relative_path}; "
                f"expected={expected_context!r}, actual={actual_context!r}"
            )
    return {"paths": len(entries)}


def _full_erofs_audit_enabled() -> bool:
    value = os.environ.get("WUKONG_STUDIO_REPACK_AUDIT", "metadata").strip().lower()
    return value in {"1", "true", "yes", "full", "strict"}


def validate_repacked_partition(
    unpacked_dir: str | Path,
    part_name: str,
    output_img: str | Path,
    filesystem_type: str,
    *,
    extract_erofs: str | Path | None = None,
    full_audit: bool | None = None,
) -> dict[str, Any]:
    unpacked = Path(unpacked_dir)
    output = Path(output_img)
    validate_partition_configs(unpacked, part_name, filesystem_type)
    if not output.is_file() or output.stat().st_size <= 0:
        raise PartitionConfigError(f"{part_name}: repacked image is missing")
    if filesystem_type == "erofs":
        if not extract_erofs:
            raise PartitionConfigError("extract.erofs is required for round-trip validation")
        report = _validate_erofs_roundtrip(unpacked, part_name, output, extract_erofs)
        use_full_audit = _full_erofs_audit_enabled() if full_audit is None else full_audit
        if use_full_audit:
            with tempfile.TemporaryDirectory(prefix=f"wkstudio-{part_name}-audit-") as temp:
                audit = Path(temp)
                result = subprocess.run(
                    [str(extract_erofs), "-i", str(output), "-o", str(audit), "-x", "-s"],
                    check=False,
                )
                if result.returncode != 0:
                    raise PartitionConfigError(f"{part_name}: cannot extract repacked EROFS image")
                expected_tree = _tree_profile(unpacked / part_name)
                actual_tree = _tree_profile(audit / part_name)
                if actual_tree != expected_tree:
                    missing = sorted(set(expected_tree) - set(actual_tree))
                    extra = sorted(set(actual_tree) - set(expected_tree))
                    changed = sorted(
                        path
                        for path in set(expected_tree).intersection(actual_tree)
                        if expected_tree[path] != actual_tree[path]
                    )
                    raise PartitionConfigError(
                        f"{part_name}: EROFS content changed after repack; "
                        f"missing={missing[:3]}, extra={extra[:3]}, changed={changed[:3]}"
                    )
                report.update(
                    _validate_config_roundtrip(
                        unpacked / "config",
                        audit / "config",
                        unpacked / part_name,
                        part_name,
                    )
                )
        return {
            "partition": part_name,
            "filesystem": filesystem_type,
            "audit": "full" if use_full_audit else "metadata",
            **report,
        }
    if filesystem_type == "ext4":
        from src.core.imgextractor import Extractor

        with tempfile.TemporaryDirectory(prefix=f"wkstudio-{part_name}-ext4-") as temp:
            audit = Path(temp)
            Extractor().main(str(output), str(audit), str(audit), target_type="img")
            expected_tree = _tree_profile(unpacked / part_name)
            actual_tree = _tree_profile(audit / part_name)
            if "lost+found" not in expected_tree:
                actual_tree = {
                    path: value
                    for path, value in actual_tree.items()
                    if path != "lost+found" and not path.startswith("lost+found/")
                }
            if actual_tree != expected_tree:
                missing = sorted(set(expected_tree) - set(actual_tree))
                extra = sorted(set(actual_tree) - set(expected_tree))
                changed = sorted(
                    path
                    for path in set(expected_tree).intersection(actual_tree)
                    if expected_tree[path] != actual_tree[path]
                )
                raise PartitionConfigError(
                    f"{part_name}: EXT4 content changed after repack; "
                    f"missing={missing[:3]}, extra={extra[:3]}, changed={changed[:3]}"
                )
            report = _validate_config_roundtrip(
                unpacked / "config",
                audit / "config",
                unpacked / part_name,
                part_name,
            )
        return {"partition": part_name, "filesystem": filesystem_type, **report}
    raise PartitionConfigError(f"{part_name}: unsupported filesystem type: {filesystem_type}")

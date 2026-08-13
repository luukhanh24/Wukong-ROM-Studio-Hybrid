#!/usr/bin/env python3
"""Patch Android DTBO thermal trip temperatures in place.

This intentionally does not decompile/recompile DTB blobs. It edits only the
4-byte big-endian value of selected FDT properties and preserves the original
DTBO table, DTB sizes, offsets, symbols, and fixups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


DTBO_MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


@dataclass
class DtboEntry:
    index: int
    dt_size: int
    dt_offset: int
    entry_offset: int
    id: int
    rev: int
    custom: tuple[int, int, int, int]


@dataclass
class PropRef:
    path: str
    name: str
    data_offset: int
    data_len: int
    old_value: int | None


def be32(buf: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">I", buf, offset)[0]


def put_be32(buf: bytearray, offset: int, value: int) -> None:
    struct.pack_into(">I", buf, offset, value)


def align4(value: int) -> int:
    return (value + 3) & ~3


def read_c_string(buf: bytes | bytearray, offset: int) -> str:
    end = buf.find(b"\0", offset)
    if end < 0:
        raise ValueError(f"unterminated string at 0x{offset:x}")
    return buf[offset:end].decode("utf-8", errors="replace")


def parse_dtbo_entries(buf: bytes | bytearray) -> list[DtboEntry]:
    if len(buf) < 32:
        raise ValueError("file is too small for a DTBO header")
    magic, _total_size, _header_size, entry_size, entry_count, entries_offset, _page_size, _version = struct.unpack_from(
        ">8I", buf, 0
    )
    if magic != DTBO_MAGIC:
        raise ValueError(f"not an Android DTBO image: magic=0x{magic:08x}")
    if entry_size < 32:
        raise ValueError(f"unsupported DTBO entry size: {entry_size}")

    entries: list[DtboEntry] = []
    for index in range(entry_count):
        entry_offset = entries_offset + index * entry_size
        if entry_offset + 32 > len(buf):
            raise ValueError(f"DTBO entry {index} is outside file")
        dt_size, dt_offset, entry_id, rev, c0, c1, c2, c3 = struct.unpack_from(">8I", buf, entry_offset)
        if dt_offset + dt_size > len(buf):
            raise ValueError(f"DTB entry {index} points outside file")
        entries.append(
            DtboEntry(
                index=index,
                dt_size=dt_size,
                dt_offset=dt_offset,
                entry_offset=entry_offset,
                id=entry_id,
                rev=rev,
                custom=(c0, c1, c2, c3),
            )
        )
    return entries


def iter_fdt_props(blob: bytes | bytearray, base_offset: int) -> list[PropRef]:
    if len(blob) < 40:
        raise ValueError("DTB is too small for an FDT header")
    magic = be32(blob, 0)
    if magic != FDT_MAGIC:
        raise ValueError(f"not an FDT blob: magic=0x{magic:08x}")

    totalsize = be32(blob, 4)
    off_struct = be32(blob, 8)
    off_strings = be32(blob, 12)
    size_strings = be32(blob, 32)
    size_struct = be32(blob, 36)
    if totalsize > len(blob):
        raise ValueError("FDT totalsize is larger than extracted DTB size")
    if off_struct + size_struct > totalsize or off_strings + size_strings > totalsize:
        raise ValueError("FDT block offsets are invalid")

    props: list[PropRef] = []
    stack: list[str] = []
    pos = off_struct
    struct_end = off_struct + size_struct
    strings_end = off_strings + size_strings

    while pos < struct_end:
        token = be32(blob, pos)
        pos += 4

        if token == FDT_BEGIN_NODE:
            name = read_c_string(blob, pos)
            pos = align4(pos + len(name.encode("utf-8", errors="replace")) + 1)
            stack.append(name)
        elif token == FDT_END_NODE:
            if stack:
                stack.pop()
        elif token == FDT_PROP:
            data_len = be32(blob, pos)
            nameoff = be32(blob, pos + 4)
            pos += 8
            if off_strings + nameoff >= strings_end:
                raise ValueError(f"property name offset outside strings block: 0x{nameoff:x}")
            prop_name = read_c_string(blob, off_strings + nameoff)
            data_offset = pos
            old_value = be32(blob, data_offset) if data_len == 4 else None
            path = "/" + "/".join(part for part in stack if part)
            props.append(
                PropRef(
                    path=path,
                    name=prop_name,
                    data_offset=base_offset + data_offset,
                    data_len=data_len,
                    old_value=old_value,
                )
            )
            pos = align4(pos + data_len)
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"unknown FDT token 0x{token:x} at struct offset 0x{pos - 4:x}")

    return props


def parse_patch_spec(spec: str) -> tuple[re.Pattern[str], int | None, int]:
    parts = spec.split("=")
    if len(parts) not in (2, 3):
        raise ValueError("patch spec must be NODE_REGEX=NEW_MC or NODE_REGEX=OLD_MC=NEW_MC")
    node_regex = re.compile(parts[0])
    old_value = int(parts[1], 0) if len(parts) == 3 else None
    new_value = int(parts[-1], 0)
    if not 0 <= new_value <= 0xFFFFFFFF:
        raise ValueError(f"new value out of uint32 range: {new_value}")
    return node_regex, old_value, new_value


def sha256_hex(buf: bytes | bytearray) -> str:
    return hashlib.sha256(buf).hexdigest().upper()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Patch selected DTBO/FDT temperature properties in place without dtc rebuild."
    )
    parser.add_argument("--input", required=True, help="source dtbo.img")
    parser.add_argument("--output", help="patched output dtbo image")
    parser.add_argument(
        "--set",
        dest="patch_specs",
        action="append",
        default=[],
        metavar="NODE_REGEX=OLD_MC=NEW_MC",
        help=(
            "patch temperature under paths matching NODE_REGEX. "
            "Use OLD_MC to guard against wrong firmware, e.g. xo-config0=78000=65000"
        ),
    )
    parser.add_argument("--list", action="store_true", help="list all 4-byte temperature properties")
    parser.add_argument(
        "--entry",
        type=int,
        action="append",
        default=[],
        help="only process a specific DTBO entry index; may be repeated",
    )
    parser.add_argument("--report", help="write JSON report")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None
    if output_path and input_path.resolve() == output_path.resolve():
        raise SystemExit("refusing to overwrite input; choose a different --output path")
    if not args.list and not args.patch_specs:
        raise SystemExit("use --list or at least one --set rule")

    original = input_path.read_bytes()
    patched = bytearray(original)
    entries = parse_dtbo_entries(patched)
    selected = set(args.entry)
    specs = [parse_patch_spec(spec) for spec in args.patch_specs]

    report: dict[str, object] = {
        "input": str(input_path),
        "input_sha256": sha256_hex(original),
        "entry_count": len(entries),
        "rules": args.patch_specs,
        "listed": [],
        "patched": [],
    }

    for entry in entries:
        if selected and entry.index not in selected:
            continue
        blob = patched[entry.dt_offset : entry.dt_offset + entry.dt_size]
        props = iter_fdt_props(blob, entry.dt_offset)
        for prop in props:
            if prop.name != "temperature" or prop.data_len != 4:
                continue
            item = {
                "entry": entry.index,
                "path": prop.path,
                "old_millicelsius": prop.old_value,
                "old_hex": f"0x{prop.old_value:08x}" if prop.old_value is not None else None,
            }
            if args.list:
                report["listed"].append(item)
            for pattern, old_guard, new_value in specs:
                if not pattern.search(prop.path):
                    continue
                if old_guard is not None and prop.old_value != old_guard:
                    continue
                put_be32(patched, prop.data_offset, new_value)
                changed = dict(item)
                changed["new_millicelsius"] = new_value
                changed["new_hex"] = f"0x{new_value:08x}"
                changed["byte_offset"] = prop.data_offset
                report["patched"].append(changed)

    diff_byte_count = sum(1 for old, new in zip(original, patched) if old != new)
    report["diff_byte_count"] = diff_byte_count
    report["output"] = str(output_path) if output_path else None
    report["output_sha256"] = sha256_hex(patched) if output_path else None

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(text)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(patched)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

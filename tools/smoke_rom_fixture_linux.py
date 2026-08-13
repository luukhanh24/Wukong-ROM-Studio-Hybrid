from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORMATS = ["ext4", "erofs", "payload", "super", "vbmeta", "vendor_boot", "zip"]


def _pad(data: bytes, alignment: int) -> bytes:
    return data + b"\0" * (-len(data) % alignment)


def _newc_entry(name: str, data: bytes, *, inode: int) -> bytes:
    encoded_name = name.encode("utf-8") + b"\0"
    fields = (
        inode,
        stat.S_IFREG | 0o644,
        0,
        0,
        1,
        0,
        len(data),
        0,
        0,
        0,
        0,
        len(encoded_name),
        0,
    )
    header = b"070701" + b"".join(f"{value:08x}".encode("ascii") for value in fields)
    return _pad(header + encoded_name, 4) + _pad(data, 4)


def _newc_archive() -> bytes:
    body = _newc_entry("init", b"#!/system/bin/sh\necho wukong\n", inode=1)
    body += _newc_entry("TRAILER!!!", b"", inode=2)
    return _pad(body, 512)


def _vendor_boot_v3(ramdisk: bytes) -> bytes:
    page_size = 4096
    header_size = 2112
    header = struct.pack(
        "<8s5I2048sI16sIIQ",
        b"VNDRBOOT",
        3,
        page_size,
        0,
        0,
        len(ramdisk),
        b"console=ttyS0",
        0,
        b"wukong-fixture",
        header_size,
        0,
        0,
    )
    return _pad(header, page_size) + _pad(ramdisk, page_size)


def _payload(partition_data: bytes) -> bytes:
    from src.core import update_metadata_pb2

    manifest = update_metadata_pb2.DeltaArchiveManifest()
    manifest.block_size = 4096
    manifest.minor_version = 0
    partition = manifest.partitions.add()
    partition.partition_name = "system"
    partition.new_partition_info.size = len(partition_data)
    partition.new_partition_info.hash = hashlib.sha256(partition_data).digest()
    operation = partition.operations.add()
    operation.type = update_metadata_pb2.InstallOperation.REPLACE
    operation.data_offset = 0
    operation.data_length = len(partition_data)
    operation.data_sha256_hash = hashlib.sha256(partition_data).digest()
    extent = operation.dst_extents.add()
    extent.start_block = 0
    extent.num_blocks = len(partition_data) // manifest.block_size
    encoded_manifest = manifest.SerializeToString()
    return (
        struct.pack(">4sQQI", b"CrAU", 2, len(encoded_manifest), 1)
        + encoded_manifest
        + b"\0"
        + partition_data
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _run_fixture(root: Path) -> dict[str, object]:
    from img_tool import ImageTool
    from src.core.payload_extract import extract_partitions_from_payload
    from super_tool import SuperPacker
    from vendor_boot_tool import VendorBootTool

    fixture_data = b"wukong-linux-smoke\n"
    source_parent = root / "source"
    source = source_parent / "system"
    source.mkdir(parents=True)
    (source / "fixture.txt").write_bytes(fixture_data)
    image_tool = ImageTool()
    results: dict[str, object] = {}

    ext4_image = root / "system.img"
    _require(image_tool.repack_ext4(str(source), str(ext4_image), size_mb=8), "EXT4 repack failed")
    ext4_out = root / "ext4-out"
    _require(image_tool.unpack(str(ext4_image), str(ext4_out)), "EXT4 unpack failed")
    _require((ext4_out / "system" / "fixture.txt").read_bytes() == fixture_data, "EXT4 content mismatch")
    results["ext4"] = ext4_image.stat().st_size

    erofs_image = root / "vendor.img"
    vendor_source = source_parent / "vendor"
    vendor_source.mkdir()
    (vendor_source / "fixture.txt").write_bytes(fixture_data)
    _require(image_tool.repack_erofs(str(vendor_source), str(erofs_image)), "EROFS repack failed")
    erofs_out = root / "erofs-out"
    _require(image_tool.unpack(str(erofs_image), str(erofs_out)), "EROFS unpack failed")
    _require((erofs_out / "vendor" / "fixture.txt").read_bytes() == fixture_data, "EROFS content mismatch")
    results["erofs"] = erofs_image.stat().st_size

    partition_data = fixture_data.ljust(4096, b"\0")
    payload = _payload(partition_data)
    payload_path = root / "payload.bin"
    payload_path.write_bytes(payload)
    payload_out = root / "payload-out"
    with payload_path.open("rb") as stream:
        extract_partitions_from_payload(stream, ["system"], str(payload_out), max_workers=2)
    _require((payload_out / "system.img").read_bytes() == partition_data, "Payload content mismatch")
    results["payload"] = payload_path.stat().st_size

    super_image = root / "super.img"
    _require(
        SuperPacker().pack(
            str(super_image),
            32 * 1024 * 1024,
            "qti_dynamic_partitions",
            16 * 1024 * 1024,
            [str(ext4_image)],
            sparse=True,
            is_ab=False,
        ),
        "Super repack failed",
    )
    super_out = root / "super-out"
    _require(image_tool.unpack(str(super_image), str(super_out)), "Super unpack failed")
    _require((super_out / "system.img").is_file(), "Super partition is missing")
    results["super"] = super_image.stat().st_size

    vbmeta = root / "vbmeta.img"
    vbmeta.write_bytes(b"AVB0" + b"\0" * 252)
    completed = subprocess.run(
        [sys.executable, str(ROOT / "vbmate-patch.py"), str(vbmeta)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    _require(completed.returncode == 0, f"VBMeta patch failed: {completed.stdout} {completed.stderr}")
    patched_vbmeta = root / "Build" / "vbmeta.img"
    _require(struct.unpack(">I", patched_vbmeta.read_bytes()[120:124])[0] == 3, "VBMeta flags mismatch")
    results["vbmeta"] = patched_vbmeta.stat().st_size

    vendor_boot_source = root / "vendor-boot-source"
    vendor_boot_source.mkdir()
    vendor_boot = vendor_boot_source / "vendor_boot.img"
    vendor_boot.write_bytes(_vendor_boot_v3(_newc_archive()))
    vendor_unpack = root / "vendor-boot-unpack"
    vendor_build = root / "vendor-boot-build"
    vendor_tool = VendorBootTool()
    previous = Path.cwd()
    try:
        _require(vendor_tool.unpack(str(vendor_boot_source), str(vendor_unpack)), "vendor_boot unpack failed")
        _require(
            vendor_tool.repack(str(vendor_unpack), str(vendor_build), str(vendor_boot_source)),
            "vendor_boot repack failed",
        )
    finally:
        os.chdir(previous)
    _require((vendor_build / "vendor_boot.img").is_file(), "Repacked vendor_boot is missing")
    results["vendor_boot"] = (vendor_build / "vendor_boot.img").stat().st_size

    rom_zip = root / "fixture-rom.zip"
    with zipfile.ZipFile(rom_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "META-INF/com/android/metadata",
            "oplus_product_name=PKG110\noplus_version_name=linux-smoke\n",
        )
        archive.write(payload_path, "payload.bin")
        archive.write(vbmeta, "vbmeta.img")
        archive.write(vendor_boot, "vendor_boot.img")
    with zipfile.ZipFile(rom_zip) as archive:
        _require(archive.testzip() is None, "ZIP CRC validation failed")
        _require("payload.bin" in archive.namelist(), "ZIP payload is missing")
    results["zip"] = rom_zip.stat().st_size

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a generated ROM fixture on Linux")
    parser.add_argument("--plan", action="store_true", help="Print the fixture coverage without executing tools")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({"platform": "Linux/x86_64", "formats": FORMATS}))
        return 0
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Linux x86_64 is required")
    with tempfile.TemporaryDirectory(prefix="wukong-linux-smoke-") as temporary:
        results = _run_fixture(Path(temporary))
    print(json.dumps({"ok": True, "formats": FORMATS, "results": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

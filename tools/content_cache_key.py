"""Fingerprint only the content installed by the hybrid build action."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SHARED_PACKS = ("STARK/common", "Flash_script/common", "copy-image/v1", "OFX/v1", "TWRP/v1")


def content_cache_key(index: dict[str, Any], mod_version: str, toolchain: bytes) -> str:
    required = {f"MOD/{mod_version}", *SHARED_PACKS}
    packs = {pack["id"]: pack for pack in index["packs"] if pack["id"] in required}
    if set(packs) != required:
        raise ValueError("Missing required content packs: " + ", ".join(sorted(required - packs.keys())))
    material = []
    for pack_id, pack in sorted(packs.items()):
        material.append({"id": pack_id, "files": sorted(
            ({"path": value["path"], "sizeBytes": value["sizeBytes"], "sha256": value["sha256"]} for value in pack["files"]),
            key=lambda value: value["path"]
        )})
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode())
    digest.update(toolchain)
    return "wukong-content-v2-" + digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod_version")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(content_cache_key(json.loads((root / "content-packs/index.json").read_text(encoding="utf-8")), args.mod_version,
        (root / "tools/linux-x86_64.json").read_bytes() + (root / "tools/bootstrap_linux.py").read_bytes()))


if __name__ == "__main__":
    main()

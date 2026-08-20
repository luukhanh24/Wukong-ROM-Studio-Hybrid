from __future__ import annotations

import argparse
import json
from pathlib import Path

from wukong.catalog import LITE_DEFAULT_MODS, PLUS_DEFAULT_EXCLUDED_MODS
from wukong.content_packs import validate_content_index
from wukong.pipeline import DEFAULT_PIPELINE_STEPS, PIPELINE_STEP_DEFINITIONS


def export_catalog(index_path: Path, devices_path: Path, output: Path) -> dict[str, object]:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    validate_content_index(index)
    devices_payload = json.loads(devices_path.read_text(encoding="utf-8"))
    devices = [
        {
            "product": str(item.get("product_name") or ""),
            "name": str(item.get("name") or item.get("product_name") or ""),
        }
        for item in devices_payload
        if isinstance(item, dict) and str(item.get("product_name") or "")
    ]
    mods_by_version: dict[str, list[str]] = {}
    for pack in index["packs"]:
        pack_id = str(pack.get("id") or "")
        archive = pack.get("archive")
        if not pack_id.startswith("MOD/") or not isinstance(archive, dict) or not archive.get("sha256"):
            continue
        version = pack_id.split("/", 1)[1]
        mods_by_version[version] = sorted(
            {
                str(item.get("path") or "").replace("\\", "/").split("/", 1)[0]
                for item in pack.get("files", [])
                if str(item.get("path") or "").strip()
            },
            key=str.casefold,
        )
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "devices": devices,
        "modVersions": sorted(mods_by_version, key=str.casefold),
        "modsByVersion": mods_by_version,
        "pipelineSteps": [
            {"id": step_id, "label": label, "default": step_id in DEFAULT_PIPELINE_STEPS}
            for step_id, label, _required in PIPELINE_STEP_DEFINITIONS
            if step_id != "notify_telegram"
        ],
        "presetDefaultsByVersion": {
            version: {
                "lite": [name for name in LITE_DEFAULT_MODS if name in mods],
                "plus": [name for name in mods if name not in PLUS_DEFAULT_EXCLUDED_MODS],
                "both": [name for name in mods if name not in PLUS_DEFAULT_EXCLUDED_MODS],
                "custom": [],
            }
            for version, mods in mods_by_version.items()
        },
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a public compact catalog for Telegram Mini App")
    parser.add_argument("--index", default="content-packs/index.json")
    parser.add_argument("--devices", default="devices_sizes.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = export_catalog(Path(args.index), Path(args.devices), Path(args.output))
    print(f"Exported {len(payload['devices'])} devices and {len(payload['modVersions'])} MOD versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

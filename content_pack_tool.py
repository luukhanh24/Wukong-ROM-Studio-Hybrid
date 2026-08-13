from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from wukong.content_packs import ContentPackManager, upload_content_packs, write_content_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, upload, install and verify Wukong content-packs")
    parser.add_argument("command", choices=["index", "upload", "install", "verify"])
    parser.add_argument("--content-root", default=".")
    parser.add_argument("--index", default="content-packs/index.json")
    parser.add_argument("--remote", default="wukong-gdrive:WukongROM/content-packs")
    parser.add_argument("--pack")
    parser.add_argument("--rclone-config", default=os.environ.get("WUKONG_RCLONE_CONFIG"))
    parser.add_argument("--verify-download", action="store_true")
    parser.add_argument("--skip-download-verify", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    content_root = Path(args.content_root).resolve()
    index_path = Path(args.index).resolve()
    config = Path(args.rclone_config).resolve() if args.rclone_config else None
    if args.command == "index":
        index = write_content_index(content_root, index_path, remote=args.remote)
        print(json.dumps({"packs": len(index["packs"]), "index": str(index_path)}))
        return 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if args.command == "upload":
        upload_content_packs(
            content_root,
            index,
            rclone_config=config,
            verify_download=args.verify_download and not args.skip_download_verify,
            pack_id=args.pack,
        )
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif args.command == "install":
        if not args.pack:
            parser.error("--pack is required for install")
        ContentPackManager(content_root, rclone_config=config).install(index, args.pack)
    else:
        if not args.pack:
            parser.error("--pack is required for verify")
        pack = next(item for item in index["packs"] if item["id"] == args.pack)
        ContentPackManager.verify(content_root / pack["target"], pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

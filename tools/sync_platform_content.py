from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from wukong.content_sync import (
    DEFAULT_REMOTE,
    assert_publishable,
    migrate_shared_mods,
    publish_index_to_github,
    refresh_content_index,
    upload_changed_packs,
)


def emit(stage: str, **values: object) -> None:
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Wukong Content and Runtime packs")
    parser.add_argument("--install-root", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--target", choices=("refresh", "drive", "github", "all"), required=True)
    parser.add_argument("--rclone-config")
    parser.add_argument("--repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--migrate-shared", action="store_true")
    parser.add_argument("--skip-download-verify", action="store_true")
    args = parser.parse_args()

    install = Path(args.install_root).resolve()
    index_path = Path(args.index).resolve()
    if args.migrate_shared:
        migrated = migrate_shared_mods(install)
        emit("migrate", mods=migrated)
    index, changed = refresh_content_index(install, index_path, remote=args.remote)
    emit("index", packs=len(index["packs"]), changed=changed)
    if args.target in {"drive", "all"}:
        if not args.rclone_config:
            parser.error("--rclone-config is required for Drive sync")
        upload_changed_packs(
            install,
            index_path,
            index,
            changed,
            rclone_config=Path(args.rclone_config).resolve(),
            verify_download=not args.skip_download_verify,
        )
        emit("drive", uploaded=changed)
    if args.target in {"github", "all"}:
        assert_publishable(index)
        repository = args.repository or os.environ.get("WUKONG_GITHUB_REPOSITORY", "")
        token = os.environ.get("WUKONG_GITHUB_TOKEN", "")
        sha = publish_index_to_github(
            index_path,
            repository=repository,
            token=token,
            branch=args.branch,
        )
        emit("github", commit=sha)
    emit("complete", packs=len(index["packs"]), changed=len(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from pathlib import Path

from wukong.content_sync import (
    DEFAULT_REMOTE,
    assert_publishable,
    migrate_shared_mods,
    preview_content_pack,
    publish_index_to_github,
    refresh_content_index,
    resolve_selected_content_pack,
    restore_incomplete_index,
    upload_changed_packs,
)


def emit(stage: str, **values: object) -> None:
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Wukong Content and Runtime packs")
    parser.add_argument("--install-root", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--baseline-index")
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument(
        "--target",
        choices=("preview", "refresh", "drive", "github", "all"),
        required=True,
    )
    parser.add_argument("--rclone-config")
    parser.add_argument("--repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--migrate-shared", action="store_true")
    parser.add_argument("--skip-download-verify", action="store_true")
    parser.add_argument("--folder", help="Managed Content folder whose complete pack must replace Drive")
    parser.add_argument("--run-id", help="UUID used to scope transactional artifacts for this run")
    args = parser.parse_args()

    if args.folder and args.migrate_shared:
        parser.error("--folder and --migrate-shared cannot be used together")
    if args.target == "github" and (args.folder or args.migrate_shared):
        parser.error(
            "--target github publishes the verified index as-is; "
            "--folder and --migrate-shared are not allowed"
        )
    if args.target == "preview" and not args.folder:
        parser.error("--folder is required for preview")
    try:
        run_id = uuid.UUID(args.run_id).hex if args.run_id else uuid.uuid4().hex
    except ValueError:
        parser.error("--run-id must be a UUID")

    install = Path(args.install_root).resolve()
    index_path = Path(args.index).resolve()
    selected_pack_ids: set[str] | None = None
    forced_pack_ids: set[str] | None = None
    if args.folder:
        selected_pack_id, selected_pack_root = resolve_selected_content_pack(install, Path(args.folder))
        selected_pack_ids = {selected_pack_id}
        forced_pack_ids = selected_pack_ids if args.target in {"drive", "all"} else set()
        emit(
            "selection",
            folder=str(Path(args.folder).resolve()),
            packId=selected_pack_id,
            packRoot=str(selected_pack_root),
            replace=True,
        )
    if args.target == "preview":
        emit(
            "preview",
            **preview_content_pack(
                install,
                index_path,
                selected_pack_id,
                remote=args.remote,
            ),
        )
        return 0
    if args.migrate_shared:
        migrated = migrate_shared_mods(install)
        emit("migrate", mods=migrated)

    working_index_path = index_path
    transaction_path: Path | None = None
    if args.target in {"drive", "all"}:
        if not args.rclone_config:
            parser.error("--rclone-config is required for Drive sync")
        transaction_path = index_path.with_name(f".{index_path.name}.{run_id}.working")
        transaction_path.parent.mkdir(parents=True, exist_ok=True)
        if index_path.is_file():
            shutil.copy2(index_path, transaction_path)
        working_index_path = transaction_path
    try:
        if args.baseline_index:
            repaired = restore_incomplete_index(working_index_path, Path(args.baseline_index))
            if repaired:
                emit("repair", packs=repaired)
        if args.target == "github":
            if not working_index_path.is_file():
                raise FileNotFoundError(f"Content-pack index does not exist: {working_index_path}")
            index = json.loads(working_index_path.read_text(encoding="utf-8"))
            changed = []
        else:
            index, changed = refresh_content_index(
                install,
                working_index_path,
                remote=args.remote,
                only_pack_ids=selected_pack_ids,
                force_pack_ids=forced_pack_ids,
            )
        emit("index", packs=len(index["packs"]), changed=changed)
        if args.target in {"drive", "all"}:
            upload_changed_packs(
                install,
                working_index_path,
                index,
                changed,
                rclone_config=Path(args.rclone_config).resolve(),
                verify_download=not args.skip_download_verify,
                progress_callback=lambda values: emit("content-progress", **values),
                run_id=run_id,
            )
            os.replace(working_index_path, index_path)
            transaction_path = None
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
    finally:
        if transaction_path is not None:
            transaction_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path

from studio_paths import JOBS_ROOT
from wukong.adapters import RcloneStorageAdapter
from wukong.cloud_sync import CloudJobSync
from wukong.orchestrator import FileJobStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize one Wukong job to cloud storage")
    parser.add_argument("job_id")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--pull-checkpoint",
        action="store_true",
        help="Import only a validated cloud checkpoint before execution",
    )
    args = parser.parse_args()
    store = FileJobStore(JOBS_ROOT / "hybrid")
    if not store.get(args.job_id):
        print(f"Job manifest is unavailable: {args.job_id}")
        return 1
    sync = CloudJobSync(
        store,
        RcloneStorageAdapter(config_path=Path(args.config)),
    )
    if args.pull_checkpoint:
        sync.pull_checkpoint(args.job_id)
    else:
        sync.push(args.job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

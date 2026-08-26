from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Wukong runner resources")
    parser.add_argument("--path", default=".")
    parser.add_argument("--min-disk-gib", type=int, default=150)
    parser.add_argument("--root-path")
    parser.add_argument("--min-root-disk-gib", type=int, default=0)
    parser.add_argument("--min-memory-gib", type=int, default=16)
    parser.add_argument("--min-cpus", type=int, default=8)
    parser.add_argument("--recipe")
    parser.add_argument("--reserve-gib", type=int, default=0)
    args = parser.parse_args()
    workspace_disk = shutil.disk_usage(args.path).free
    root_disk = shutil.disk_usage(args.root_path).free if args.root_path else None
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    cpus = os.cpu_count() or 0
    required_workspace_disk = args.min_disk_gib * 1024**3
    required_root_disk = args.min_root_disk_gib * 1024**3
    if args.recipe:
        from wukong.models import BuildRecipe

        recipe = BuildRecipe.from_dict(json.loads(Path(args.recipe).read_text(encoding="utf-8")))
        required_workspace_disk = max(
            required_workspace_disk,
            recipe.estimated_workspace_bytes + args.reserve_gib * 1024**3,
        )
    result = {
        "workspaceFreeDiskBytes": workspace_disk,
        "requiredWorkspaceDiskBytes": required_workspace_disk,
        "rootFreeDiskBytes": root_disk,
        "requiredRootDiskBytes": required_root_disk,
        "memoryBytes": memory,
        "logicalCpus": cpus,
    }
    print(json.dumps(result, sort_keys=True))
    if (
        workspace_disk < required_workspace_disk
        or (root_disk is not None and root_disk < required_root_disk)
        or memory < args.min_memory_gib * 1024**3
        or cpus < args.min_cpus
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

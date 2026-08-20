from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath


REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*:(?P<path>.+)$")
ALLOWED_RECIPE_ROOT = "WukongROM/recipes"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a Wukong build recipe safely")
    parser.add_argument("recipe_ref")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rclone-config")
    parser.add_argument("--force-github-auto", action="store_true")
    parser.add_argument(
        "--coerce-github",
        action="store_true",
        help="Replace local-windows with github-auto while preserving explicit GitHub targets",
    )
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    match = REMOTE_RE.fullmatch(args.recipe_ref)
    if match:
        path = str(PurePosixPath(match.group("path").replace("\\", "/"))).strip("/")
        expected_remote = os.environ.get("WUKONG_RCLONE_REMOTE", "wukong-gdrive").rstrip(":")
        if args.recipe_ref.split(":", 1)[0].casefold() != expected_remote.casefold():
            raise ValueError(f"Recipe reference must use the {expected_remote}: remote")
        if ".." in PurePosixPath(path).parts:
            raise ValueError("Recipe reference contains path traversal")
        if not path.startswith(ALLOWED_RECIPE_ROOT + "/") or not path.casefold().endswith(".json"):
            raise ValueError("Cloud recipe reference must be a JSON file inside WukongROM/recipes")
        command = ["rclone", "copyto", args.recipe_ref, str(output), "--retries", "3"]
        if args.rclone_config:
            command.extend(["--config", args.rclone_config])
        subprocess.run(command, check=True)
    else:
        root = Path.cwd().resolve()
        source = (root / args.recipe_ref).resolve()
        if root not in source.parents or source.suffix.casefold() != ".json" or not source.is_file():
            raise ValueError("Repository recipe reference must be a safe JSON path")
        output.write_bytes(source.read_bytes())
    if args.force_github_auto or args.coerce_github:
        payload = json.loads(output.read_text(encoding="utf-8"))
        execution = payload.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            payload["execution"] = execution
        current = str(execution.get("target") or "github-auto").strip().casefold()
        if args.force_github_auto or current == "local-windows":
            execution["target"] = "github-auto"
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

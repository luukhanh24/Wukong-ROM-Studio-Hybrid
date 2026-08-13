from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from studio_core import (
    BuildSpec,
    StudioError,
    execute_build,
    prepare_workspace,
    read_rom_metadata,
    workspace_for_version,
)


EVENT_PREFIX = "@@STUDIO_EVENT@@"


def configure_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def emit(payload: dict[str, Any]) -> None:
    print(EVENT_PREFIX + json.dumps(payload, ensure_ascii=True), flush=True)


def main() -> int:
    configure_utf8_streams()
    parser = argparse.ArgumentParser(description="Wukong ROM Studio build worker")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task-name")
    args = parser.parse_args()

    spec = BuildSpec.from_dict(json.loads(Path(args.spec_file).read_text(encoding="utf-8")))
    workspace = Path(args.workspace).resolve()
    task_name = args.task_name or workspace.name
    os.environ["WUKONG_STUDIO_TASK_NAME"] = task_name
    emit({"type": "worker", "status": "running", "pid": os.getpid(), "taskName": task_name})
    try:
        metadata = read_rom_metadata(spec.romPath)
        expected_workspace = workspace_for_version(metadata.get("version_name"))
        if workspace != expected_workspace:
            raise StudioError(
                f"Workspace does not match ROM version_name: expected {expected_workspace}"
            )
        prepare_workspace(
            workspace,
            args.job_id,
            str(metadata["version_name"]),
            resume=bool(spec.resumeFromJobId),
            rom_sha256=spec.romSha256,
            spec_fingerprint=spec.specFingerprint,
        )
        result = execute_build(args.job_id, spec, workspace, emit)
    except Exception as exc:
        traceback.print_exc()
        emit({"type": "worker", "status": "failed", "error": str(exc)})
        return 1
    emit({"type": "worker", "status": "success", **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

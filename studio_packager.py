from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from studio_core import complete_package_task
from studio_worker import EVENT_PREFIX, configure_utf8_streams


def emit(payload: dict[str, Any]) -> None:
    print(EVENT_PREFIX + json.dumps(payload, ensure_ascii=True), flush=True)


def main() -> int:
    configure_utf8_streams()
    parser = argparse.ArgumentParser(description="Wukong ROM Studio background packager")
    parser.add_argument("--task-file", required=True)
    args = parser.parse_args()
    task_file = Path(args.task_file).resolve()
    try:
        task = json.loads(task_file.read_text(encoding="utf-8"))
        emit(
            {
                "type": "package",
                "status": "running",
                "taskId": task["taskId"],
                "outputZip": task["outputZip"],
            }
        )
        result = complete_package_task(task_file, emit)
    except Exception as exc:
        traceback.print_exc()
        emit(
            {
                "type": "package",
                "status": "failed",
                "taskFile": str(task_file),
                "error": str(exc),
            }
        )
        return 1
    emit({"type": "package", "status": "success", **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

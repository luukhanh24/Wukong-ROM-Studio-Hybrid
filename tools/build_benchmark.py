from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence


def _expand(command: Sequence[str], *, mode: str, run: int) -> list[str]:
    return [part.replace("{mode}", mode).replace("{run}", str(run)) for part in command]


def _run(command: Sequence[str], *, env: dict[str, str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result: dict[str, Any] = {
        "command": list(command),
        "returnCode": completed.returncode,
        "durationSeconds": round(time.perf_counter() - started, 3),
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }
    events: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and ("stage" in value or "durationSeconds" in value):
            events.append(value)
    if events:
        result["stageMetrics"] = events
    return result


def benchmark(
    root: Path,
    command: Sequence[str],
    *,
    clear_command: Sequence[str] | None = None,
    runs: int = 3,
    label: str = "candidate",
) -> dict[str, Any]:
    if not command:
        raise ValueError("A build command is required")
    records: list[dict[str, Any]] = []
    for mode in ("cold", "warm"):
        for run in range(1, max(1, runs) + 1):
            if mode == "cold" and clear_command:
                cleared = _run(_expand(clear_command, mode=mode, run=run), env=dict(os.environ), cwd=root)
                if cleared["returnCode"] != 0:
                    raise RuntimeError(f"Cache clear command failed: {cleared['stderr']}")
            env = dict(os.environ)
            env.update({"WUKONG_BENCHMARK_LABEL": label, "WUKONG_BENCHMARK_MODE": mode, "WUKONG_BENCHMARK_RUN": str(run)})
            record = _run(_expand(command, mode=mode, run=run), env=env, cwd=root)
            record.update({"label": label, "mode": mode, "run": run})
            records.append(record)
            if record["returnCode"] != 0:
                raise RuntimeError(f"Build benchmark failed on {mode} run {run}")
    totals: dict[str, list[float]] = {"cold": [], "warm": []}
    for record in records:
        totals[record["mode"]].append(float(record["durationSeconds"]))
    return {
        "label": label,
        "runsPerMode": max(1, runs),
        "records": records,
        "medianSeconds": {mode: sorted(values)[len(values) // 2] for mode, values in totals.items()},
        "assumptions": {
            "sameRunnerAndRecipe": True,
            "coldCacheRequiresExplicitClearCommand": bool(clear_command),
            "command": shlex.join(command),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run reproducible cold/warm ROM build measurements")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--label", default="candidate")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--clear-command", nargs="*", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Build command; use {mode} and {run} placeholders")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    result = benchmark(args.root.resolve(), command, clear_command=args.clear_command, runs=args.runs, label=args.label)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

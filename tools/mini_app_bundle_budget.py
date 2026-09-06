from __future__ import annotations

import argparse
import gzip
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence


def _git_file(ref: str, path: str, root: Path) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=root)


def _static_closure(meta: dict[str, Any], entry: str) -> set[str]:
    outputs = meta.get("outputs", {})
    seen: set[str] = set()

    def visit(path: str) -> None:
        if path in seen or path not in outputs:
            return
        seen.add(path)
        for imported in outputs[path].get("imports", []):
            if imported.get("kind") != "dynamic-import":
                visit(str(imported.get("path") or ""))

    visit(entry)
    return seen


def measure(root: Path, *, baseline: str, dist: Path | None = None) -> dict[str, Any]:
    frontend = root / "telegram_mini_app"
    output_dir = dist or frontend / "dist"
    meta = json.loads((output_dir / "bundle-meta.json").read_text(encoding="utf-8"))
    outputs = meta["outputs"]
    entry = next(path for path, value in outputs.items() if value.get("entryPoint") == "app.js")
    initial = _static_closure(meta, entry)
    current = [(frontend / path).read_bytes() for path in initial]
    baseline_files = ["telegram_mini_app/app.js", "telegram_mini_app/fflate.js"]
    old = [_git_file(baseline, path, root) for path in baseline_files]

    def compressed(values: list[bytes]) -> int:
        return sum(len(gzip.compress(value, compresslevel=9, mtime=0)) for value in values)

    old_raw, new_raw = sum(map(len, old)), sum(map(len, current))
    old_gzip, new_gzip = compressed(old), compressed(current)
    reduction = lambda before, after: round((1 - after / before) * 100, 1) if before else 0.0
    return {
        "scope": "First-party initial JS static import closure",
        "baseline": baseline,
        "initialFiles": sorted(initial),
        "deferredFiles": sorted(path for path in outputs if path.endswith(".js") and path not in initial),
        "oldRaw": old_raw,
        "newRaw": new_raw,
        "oldGzip": old_gzip,
        "newGzip": new_gzip,
        "rawReductionPercent": reduction(old_raw, new_raw),
        "gzipReductionPercent": reduction(old_gzip, new_gzip),
        "targetMet": reduction(old_gzip, new_gzip) >= 30.0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the Mini App's initial JavaScript budget")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", default="8dededd")
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = measure(args.root.resolve(), baseline=args.baseline, dist=args.dist.resolve() if args.dist else None)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["targetMet"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from wukong.models import BuildRecipe, SOURCE_METADATA_KEYS


def _metadata_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def merge_source_probe(recipe_path: Path, probe_path: Path) -> dict[str, Any]:
    recipe_payload = json.loads(recipe_path.read_text(encoding="utf-8"))
    probe_payload = json.loads(probe_path.read_text(encoding="utf-8"))
    if not isinstance(recipe_payload, dict) or not isinstance(probe_payload, Mapping):
        raise ValueError("Recipe and source probe must be JSON objects")
    source = recipe_payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("Recipe source must be a JSON object")

    current = source.get("metadata")
    metadata = dict(current) if isinstance(current, Mapping) else {}
    for key in SOURCE_METADATA_KEYS:
        value = _metadata_text(probe_payload.get(key))
        if value:
            metadata[key] = value
    source["metadata"] = metadata

    size = probe_payload.get("sizeBytes")
    if isinstance(size, (int, float)) and not isinstance(size, bool) and int(size) > 0:
        source["sizeBytes"] = int(size)

    validated = BuildRecipe.from_dict(recipe_payload).to_dict()
    content = json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=recipe_path.parent,
        prefix=f".{recipe_path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, recipe_path)
    finally:
        temporary.unlink(missing_ok=True)
    return validated


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge safe source-probe metadata into a build recipe")
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    merge_source_probe(args.recipe, args.probe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

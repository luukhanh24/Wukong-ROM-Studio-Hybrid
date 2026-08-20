from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from wukong.models import BuildRecipe, RecipeValidationError


TRUE_VALUES = {"1", "true", "yes", "on"}
GITHUB_TARGETS = {"github-auto", "github-hosted", "self-hosted-linux"}


def _boolean(value: str | None, default: bool) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().casefold() in TRUE_VALUES


def _items(value: str | None) -> list[str]:
    return list(dict.fromkeys(
        item.strip()
        for item in re.split(r"[,\r\n]+", str(value or ""))
        if item.strip()
    ))


def _source_kind(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme.casefold() in {"http", "https"}:
        return parsed.scheme.casefold()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*:.+", uri):
        return "rclone"
    raise RecipeValidationError("Workflow source URL must be HTTP(S) or an rclone reference")


def recipe_from_workflow_inputs(values: Mapping[str, str]) -> BuildRecipe:
    task = str(values.get("TASK") or "build").strip().casefold()
    device = str(values.get("DEVICE") or "").strip()
    source_uri = str(values.get("SOURCE_URI") or "").strip()
    if not source_uri:
        raise RecipeValidationError("Workflow source URL is required when recipe_ref is empty")
    target = str(values.get("EXECUTION_TARGET") or "github-auto").strip().casefold()
    if target not in GITHUB_TARGETS:
        raise RecipeValidationError("Workflow recipes require a GitHub execution target")

    source: dict[str, object] = {
        "kind": _source_kind(source_uri),
        "uri": source_uri,
    }
    sha256 = str(values.get("SOURCE_SHA256") or "").strip()
    if sha256:
        source["sha256"] = sha256
    size = str(values.get("SOURCE_SIZE_BYTES") or "").strip()
    if size:
        source["sizeBytes"] = int(size)

    payload: dict[str, object] = {
        "schemaVersion": 1,
        "task": task,
        "device": device,
        "source": source,
        "execution": {"target": target},
        "storage": {
            "remote": str(values.get("STORAGE_REMOTE") or "wukong-gdrive").strip(),
            "publishArtifact": _boolean(values.get("PUBLISH_ARTIFACT"), True),
        },
    }
    estimate = str(values.get("ESTIMATED_WORKSPACE_BYTES") or "").strip()
    if estimate:
        payload["execution"]["estimatedWorkspaceBytes"] = int(estimate)  # type: ignore[index]
    if task == "build":
        build: dict[str, object] = {
            "preset": str(values.get("PRESET") or "lite").strip().casefold(),
            "modVersion": str(values.get("MOD_VERSION") or "ColorOS_16.0.9").strip(),
            "mods": _items(values.get("MODS")),
            "package": _boolean(values.get("PACKAGE"), True),
            "notifyTelegram": _boolean(values.get("NOTIFY_TELEGRAM"), True),
        }
        steps = _items(values.get("ENABLED_STEPS"))
        if steps:
            build["enabledSteps"] = steps
        debloat = _items(values.get("DEBLOAT_PATHS"))
        if debloat:
            build["debloatPaths"] = debloat
        payload["build"] = build
    return BuildRecipe.from_dict(payload)


def write_workflow_recipe(values: Mapping[str, str], output: Path) -> BuildRecipe:
    recipe = recipe_from_workflow_inputs(values)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(recipe.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return recipe


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Wukong recipe from workflow_dispatch inputs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    values = {
        key.removeprefix("WUKONG_INPUT_"): value
        for key, value in os.environ.items()
        if key.startswith("WUKONG_INPUT_")
    }
    recipe = write_workflow_recipe(values, Path(args.output))
    print(json.dumps({"recipeDigest": recipe.digest, "recipe": str(Path(args.output).resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from studio_core import list_mods, preset_default_mods
from wukong.models import BuildOptions, BuildRecipe


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def resolve_recipe_mods(
    recipe: BuildRecipe,
    content_root: Path,
    *,
    drop_missing: bool | None = None,
) -> dict[str, object]:
    """Resolve recipe MOD names against installed content.

    When drop_missing is true (default on GitHub Actions via env), unavailable
    MODs are removed and lite defaults are substituted when the selection would
    otherwise be empty — matching NothingsVN-style "build with what is present".
    """
    if recipe.task != "build":
        return {
            "ok": True,
            "task": recipe.task,
            "mods": [],
            "missing": [],
            "dropped": [],
            "rewritten": False,
        }

    if drop_missing is None:
        drop_missing = _env_flag("WUKONG_DROP_MISSING_MODS", default=_env_flag("GITHUB_ACTIONS"))

    available_items = list_mods(recipe.build.mod_version, mod_root=content_root.resolve() / "MOD")
    available = {str(item["name"]) for item in available_items if item.get("ready")}
    requested = list(recipe.build.mods)
    if not requested:
        requested = preset_default_mods(recipe.build.preset, recipe.build.mod_version, mod_root=content_root.resolve() / "MOD")
    missing = [name for name in requested if name not in available]
    kept = [name for name in requested if name in available]
    dropped = list(missing)
    rewritten = False
    if missing and not drop_missing:
        raise ValueError(
            f"MOD selection is unavailable in {recipe.build.mod_version}: {', '.join(missing)}. "
            f"Upload/rebuild content-pack MOD/{recipe.build.mod_version} or enable "
            "WUKONG_DROP_MISSING_MODS=1 to skip missing MODs."
        )
    if missing and drop_missing and not kept:
        kept = [
            name
            for name in preset_default_mods("lite", recipe.build.mod_version, mod_root=content_root.resolve() / "MOD")
            if name in available
        ]
        rewritten = True
    if missing and drop_missing:
        rewritten = rewritten or bool(dropped)
    return {
        "ok": True,
        "modVersion": recipe.build.mod_version,
        "mods": kept,
        "missing": missing,
        "dropped": dropped if drop_missing else [],
        "availableMods": len(available),
        "rewritten": rewritten,
        "dropMissing": drop_missing,
    }


def apply_resolved_mods(recipe: BuildRecipe, resolved: dict[str, object]) -> BuildRecipe:
    mods = tuple(str(item) for item in (resolved.get("mods") or ()))
    if tuple(recipe.build.mods) == mods:
        return recipe
    build = BuildOptions(
        preset=recipe.build.preset,
        mods=mods,
        mod_version=recipe.build.mod_version,
        enabled_steps=recipe.build.enabled_steps,
        debloat_paths=recipe.build.debloat_paths,
        package=recipe.build.package,
        notify_telegram=recipe.build.notify_telegram,
    )
    return BuildRecipe(
        task=recipe.task,
        device=recipe.device,
        source=recipe.source,
        build=build,
        execution=recipe.execution,
        storage=recipe.storage,
        schema_version=recipe.schema_version,
    )


def validate_recipe_content(
    recipe_path: Path,
    content_root: Path,
    *,
    drop_missing: bool | None = None,
    rewrite: bool = False,
) -> dict[str, object]:
    recipe = BuildRecipe.from_dict(json.loads(recipe_path.read_text(encoding="utf-8")))
    resolved = resolve_recipe_mods(recipe, content_root, drop_missing=drop_missing)
    if rewrite and resolved.get("rewritten"):
        updated = apply_resolved_mods(recipe, resolved)
        recipe_path.write_text(
            json.dumps(updated.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        resolved = {**resolved, "recipeRewritten": True, "recipeDigest": updated.digest}
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate recipe MODs against installed content")
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--content-root", default=".")
    parser.add_argument(
        "--drop-missing",
        action="store_true",
        help="Drop unavailable MODs instead of failing (default on GitHub Actions)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any selected MOD is missing from the installed pack",
    )
    parser.add_argument(
        "--rewrite",
        action="store_true",
        help="Rewrite the recipe JSON when MODs are dropped or substituted",
    )
    args = parser.parse_args()
    drop_missing: bool | None
    if args.strict:
        drop_missing = False
    elif args.drop_missing:
        drop_missing = True
    else:
        drop_missing = None
    result = validate_recipe_content(
        Path(args.recipe),
        Path(args.content_root),
        drop_missing=drop_missing,
        rewrite=args.rewrite,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

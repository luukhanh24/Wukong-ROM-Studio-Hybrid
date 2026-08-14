from __future__ import annotations

import argparse
import json
from pathlib import Path

from studio_core import list_mods
from wukong.models import BuildRecipe


def validate_recipe_content(recipe_path: Path, content_root: Path) -> dict[str, object]:
    recipe = BuildRecipe.from_dict(json.loads(recipe_path.read_text(encoding="utf-8")))
    if recipe.task != "build":
        return {"ok": True, "task": recipe.task, "mods": []}
    available = {
        str(item["name"])
        for item in list_mods(recipe.build.mod_version, mod_root=content_root.resolve() / "MOD")
        if item.get("ready")
    }
    missing = [name for name in recipe.build.mods if name not in available]
    if missing:
        raise ValueError(
            f"MOD selection is unavailable in {recipe.build.mod_version}: {', '.join(missing)}"
        )
    return {
        "ok": True,
        "modVersion": recipe.build.mod_version,
        "mods": list(recipe.build.mods),
        "availableMods": len(available),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate recipe MODs against installed content")
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--content-root", default=".")
    args = parser.parse_args()
    result = validate_recipe_content(Path(args.recipe), Path(args.content_root))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

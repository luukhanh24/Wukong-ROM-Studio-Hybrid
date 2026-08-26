from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

from tools.export_mini_app_catalog import export_catalog


ASSET_NAMES = (
    "index.html",
    "styles.css",
    "app.js",
    "fflate.js",
    "fflate.LICENSE.txt",
    "WukongStudio.svg",
)

PRODUCTION_API_ORIGIN = "https://wukong-control-plane.luuxuankhanh98.workers.dev"


def _api_origin(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("WUKONG_TELEGRAM_MINI_APP_API_URL must be a public HTTPS origin")
    return normalized


def configured_api_origin(environ: Mapping[str, str] = os.environ) -> str:
    return environ.get("WUKONG_TELEGRAM_MINI_APP_API_URL", "").strip() or PRODUCTION_API_ORIGIN


def build_site(
    repository_root: Path,
    output: Path,
    *,
    api_url: str,
    release: str,
) -> Path:
    root = repository_root.resolve()
    destination = output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    source = root / "telegram_mini_app"
    for name in ASSET_NAMES:
        shutil.copyfile(source / name, destination / name)
    safe_release = quote(release.strip() or "production", safe="-._")
    index_path = destination / "index.html"
    index = index_path.read_text(encoding="utf-8")
    index = index.replace("__WUKONG_TELEGRAM_MINI_APP_API_URL__", _api_origin(api_url))
    index = re.sub(r"\./styles\.css(?:\?v=[^\"']+)?", f"./styles.css?v={safe_release}", index)
    index = re.sub(r"\./app\.js(?:\?v=[^\"']+)?", f"./app.js?v={safe_release}", index)
    index_path.write_text(index, encoding="utf-8", newline="\n")
    export_catalog(
        root / "content-packs" / "index.json",
        root / "devices_sizes.json",
        destination / "catalog.json",
    )
    return destination


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / ".vercel-static"
    build_site(
        root,
        output,
        api_url=configured_api_origin(),
        release=(
            os.environ.get("WUKONG_RELEASE_SHA")
            or os.environ.get("VERCEL_GIT_COMMIT_SHA")
            or os.environ.get("VERCEL_URL")
            or "production"
        ),
    )
    print(f"Built privacy-safe Mini App at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

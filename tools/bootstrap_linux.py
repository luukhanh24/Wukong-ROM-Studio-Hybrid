from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_urls(url: str) -> list[str]:
    """Prefer the pinned URL, then stable GitHub raw CDN mirrors on transient failures."""
    candidates = [url]
    prefix = "https://raw.githubusercontent.com/"
    if url.startswith(prefix):
        rest = url[len(prefix) :]
        candidates.append(f"https://cdn.jsdelivr.net/gh/{rest.replace('/', '@', 1)}")
        # jsdelivr uses owner/repo@version/path — convert owner/repo/commit/path
        parts = rest.split("/", 3)
        if len(parts) == 4:
            owner, repo, commit, path = parts
            candidates.append(f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{commit}/{path}")
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _download(url: str, destination: Path, *, attempts: int = 5) -> None:
    last_error: Exception | None = None
    for index in range(attempts):
        for candidate in _candidate_urls(url):
            try:
                request = urllib.request.Request(
                    candidate,
                    headers={"User-Agent": "Wukong-ROM-Studio/1"},
                )
                with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as handle:
                    shutil.copyfileobj(response, handle, 1024 * 1024)
                return
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                destination.unlink(missing_ok=True)
        time.sleep(min(2 ** index, 20))
    raise RuntimeError(f"Failed to download {url} after {attempts} attempts: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install pinned Wukong Linux toolchain")
    parser.add_argument("--manifest", default="tools/linux-x86_64.json")
    parser.add_argument("--destination", default="bin/Linux/x86_64")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or manifest.get("platform") != "Linux/x86_64":
        raise RuntimeError("Unsupported Linux tool manifest")
    destination = Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for tool in manifest["tools"]:
        required = {"name", "url", "sha256", "sizeBytes", "license", "source"}
        if not required.issubset(tool) or not str(tool["url"]).startswith("https://"):
            raise RuntimeError(f"Incomplete provenance for Linux tool: {tool.get('name', '<unknown>')}")
        target = destination / tool["name"]
        if not target.is_file() or sha256(target) != tool["sha256"]:
            partial = target.with_suffix(target.suffix + ".partial")
            partial.unlink(missing_ok=True)
            _download(str(tool["url"]), partial)
            if partial.stat().st_size != int(tool["sizeBytes"]) or sha256(partial) != tool["sha256"]:
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"Checksum or size mismatch for {tool['name']}")
            os.replace(partial, target)
        if not target.name.endswith(".jar"):
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    for name, source_value in manifest.get("systemTools", {}).items():
        source = Path(source_value)
        if not source.is_file():
            raise RuntimeError(f"Required system tool is unavailable: {source}")
        target = destination / name
        target.unlink(missing_ok=True)
        target.symlink_to(source)
    print(json.dumps({"ok": True, "destination": str(destination), "tools": len(manifest["tools"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

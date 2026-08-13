from __future__ import annotations

import re
import subprocess
from pathlib import Path


FORBIDDEN_ROOTS = {"MOD", "copy-image", "OFX", "TWRP", "Workspace", "Temp", "ROM_BUILD_DONE"}
SECRET_PATTERNS = (
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"[0-9]{8,12}:[A-Za-z0-9_-]{30,}"),
    re.compile(rb"ya29\.[A-Za-z0-9_-]{20,}"),
    re.compile(rb'(?m)^\s*token\s*=\s*\{[^\r\n}]*(?:"access_token"|"refresh_token")'),
    re.compile(rb"(?m)^\s*client_secret\s*=\s*\S{8,}"),
)
LFS_POINTER = re.compile(
    rb"\Aversion https://git-lfs\.github\.com/spec/v1\r?\n"
    rb"oid sha256:[0-9a-f]{64}\r?\nsize [0-9]+\r?\n?\Z"
)


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    problems: list[str] = []
    total = 0
    for raw in tracked:
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape")
        path = Path(relative)
        if path.parts and path.parts[0] in FORBIDDEN_ROOTS:
            problems.append(f"Tracked content/runtime path: {relative}")
        if path.name == "Auto_Build_WK_3.0.zip" or path.suffix.casefold() in {".apk", ".apex", ".img"}:
            problems.append(f"Tracked large content file: {relative}")
        if path.is_file():
            size = path.stat().st_size
            total += size
            if size <= 5 * 1024 * 1024:
                data = path.read_bytes()
                if LFS_POINTER.fullmatch(data):
                    problems.append(f"Tracked Git LFS pointer: {relative}")
                if path.name == ".gitattributes" and b"filter=lfs" in data.replace(b" ", b""):
                    problems.append(f"Tracked Git LFS configuration: {relative}")
                if any(pattern.search(data) for pattern in SECRET_PATTERNS):
                    problems.append(f"Potential tracked secret: {relative}")
    if total > 500 * 1024 * 1024:
        problems.append(f"Tracked checkout is larger than 500 MiB: {total} bytes")
    if problems:
        raise SystemExit("\n".join(problems))
    print(f"Repository guard passed: {len(tracked) - 1} files, {total} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

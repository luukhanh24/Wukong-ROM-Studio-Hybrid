from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path


REQUIRED = ("extract.erofs", "mkfs.erofs", "lpmake", "magiskboot", "cpio", "mke2fs", "e2fsdroid")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Wukong Linux binaries")
    parser.add_argument("--bin-dir", default="bin/Linux/x86_64")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Linux x86_64 is required")
    root = Path(args.bin_dir).resolve()
    results = {}
    for name in REQUIRED:
        path = root / name
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Missing executable: {path}")
        header = path.read_bytes()[:4]
        if header != b"\x7fELF" and not path.is_symlink():
            raise RuntimeError(f"Unexpected executable format: {path}")
        completed = subprocess.run([str(path), "--help"], capture_output=True, timeout=10, check=False)
        results[name] = completed.returncode
    print(json.dumps({"ok": True, "commands": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


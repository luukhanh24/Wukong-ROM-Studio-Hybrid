"""Verified metadata for an immutable, finalized artifact within one build."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PreparedArtifact:
    path: Path
    sha256: str
    size_bytes: int
    identity: tuple[int, int, int, int, int]

    def matches(self, path: Path) -> bool:
        return self.path == path.resolve() and self.identity == _identity(path)


def prepare_artifact(
    path: Path, previous: PreparedArtifact | None = None, *, hasher: Callable[[Path], str] = _sha256
) -> PreparedArtifact:
    path = path.resolve()
    if previous is not None and previous.matches(path):
        return previous
    before = _identity(path)
    digest = hasher(path)
    if _identity(path) != before:
        raise RuntimeError("Artifact changed while computing its checksum")
    return PreparedArtifact(path, digest, before[2], before)

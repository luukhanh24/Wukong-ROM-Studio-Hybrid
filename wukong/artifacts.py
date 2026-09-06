"""Verified metadata for an immutable, finalized artifact within one build."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


_FINGERPRINT_BYTES = 64 * 1024


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _fingerprint(path: Path) -> bytes:
    """Return a small content token to catch same-size writes with coarse mtimes."""
    size = path.stat().st_size
    with path.open("rb") as stream:
        if size <= _FINGERPRINT_BYTES * 2:
            sample = stream.read()
        else:
            head = stream.read(_FINGERPRINT_BYTES)
            stream.seek(-_FINGERPRINT_BYTES, 2)
            sample = head + stream.read(_FINGERPRINT_BYTES)
    return hashlib.blake2b(sample, digest_size=16).digest()


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
    fingerprint: bytes

    def matches(self, path: Path) -> bool:
        return (
            self.path == path.resolve()
            and self.identity == _identity(path)
            and self.fingerprint == _fingerprint(path)
        )


def prepare_artifact(
    path: Path, previous: PreparedArtifact | None = None, *, hasher: Callable[[Path], str] = _sha256
) -> PreparedArtifact:
    path = path.resolve()
    if previous is not None and previous.matches(path):
        return previous
    before = _identity(path)
    fingerprint = _fingerprint(path)
    digest = hasher(path)
    if _identity(path) != before or _fingerprint(path) != fingerprint:
        raise RuntimeError("Artifact changed while computing its checksum")
    return PreparedArtifact(path, digest, before[2], before, fingerprint)

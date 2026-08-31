"""Cloudflare-safe multipart mirror over the existing scoped WebDAV remote."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Callable, Mapping

from .adapters import RcloneStorageAdapter
from .models import ArtifactRecord


DEFAULT_PART_SIZE = 64 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RcloneSplitStorageAdapter:
    """Store a large ZIP as resumable, individually bounded WebDAV parts."""

    def __init__(self, storage: RcloneStorageAdapter, *, part_size: int = DEFAULT_PART_SIZE) -> None:
        if part_size <= 0 or part_size > 95 * 1024 * 1024:
            raise ValueError("DC Cloud multipart size must be between 1 and 95 MiB")
        self.storage = storage
        self.part_size = part_size

    def mirror_artifact(
        self,
        artifact: Path,
        *,
        relative_path: str,
        staging_key: str,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
    ) -> ArtifactRecord:
        del staging_key  # Direct final parts are required because this WebDAV rejects MOVE.
        artifact = artifact.resolve()
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized or ".." in PurePosixPath(normalized).parts:
            raise ValueError("Mirror path is empty or contains path traversal")
        digest = _sha256_file(artifact)
        size = artifact.stat().st_size
        folder = normalized + ".parts"
        folder_uri = self.storage.remote_uri(folder)
        manifest_uri = self.storage.remote_uri(f"{folder}/manifest.json")
        try:
            existing = json.loads(self.storage.run_command(self.storage._args("cat", manifest_uri)))
            if (
                existing.get("format") == "wukong-raw-split-v1"
                and str(existing.get("sha256") or "").casefold() == digest.casefold()
                and int(existing.get("sizeBytes", -1)) == size
                and int(existing.get("partSizeBytes", -1)) == self.part_size
            ):
                return ArtifactRecord(artifact.name, folder_uri, digest, size)
        except Exception:
            pass

        self.storage.run_command(self.storage._args("mkdir", folder_uri))
        parts: list[dict[str, object]] = []
        completed = 0
        with TemporaryDirectory(prefix="wukong-dccloud-split-") as root:
            root_path = Path(root)
            with artifact.open("rb") as source:
                index = 1
                while True:
                    body = source.read(self.part_size)
                    if not body:
                        break
                    part_name = f"{artifact.name}.{index:03d}"
                    part_path = root_path / part_name
                    part_path.write_bytes(body)
                    part_digest = hashlib.sha256(body).hexdigest()
                    remote_uri = self.storage.remote_uri(f"{folder}/{part_name}")
                    remote_size = -1
                    try:
                        stat = self.storage.run_command(self.storage._args("lsjson", remote_uri, "--stat"))
                        remote_size = int(json.loads(stat).get("Size", -1))
                    except Exception:
                        pass
                    if remote_size != len(body):
                        def on_part(event: Mapping[str, object]) -> None:
                            if progress_callback is None:
                                return
                            progress_callback(
                                {
                                    "provider": "dccloud",
                                    "bytesTransferred": completed + int(event.get("bytesTransferred", 0) or 0),
                                    "totalBytes": size,
                                }
                            )

                        self.storage.copy_file(
                            part_path,
                            f"{folder}/{part_name}",
                            progress_callback=on_part if progress_callback is not None else None,
                        )
                        stat = self.storage.run_command(self.storage._args("lsjson", remote_uri, "--stat"))
                        if int(json.loads(stat).get("Size", -1)) != len(body):
                            raise RuntimeError("DC Cloud multipart stat mismatch")
                    parts.append({"name": part_name, "sha256": part_digest, "sizeBytes": len(body)})
                    completed += len(body)
                    if progress_callback is not None:
                        progress_callback(
                            {"provider": "dccloud", "bytesTransferred": completed, "totalBytes": size}
                        )
                    index += 1

            part_list = root_path / "parts.txt"
            part_list.write_text("\n".join(str(part["name"]) for part in parts) + "\n", encoding="utf-8")
            readme = root_path / "README.txt"
            readme.write_text(
                "Wukong ROM multipart mirror\n\n"
                "Download every numbered part plus parts.txt into one folder.\n"
                "Windows: run reassemble.ps1\n"
                "Linux/macOS: run bash reassemble.sh\n"
                f"Expected output: {artifact.name}\n"
                f"SHA-256: {digest}\n",
                encoding="utf-8",
            )
            powershell = root_path / "reassemble.ps1"
            powershell.write_text(
                "$ErrorActionPreference='Stop'\n"
                f"$output=[System.IO.File]::Create('{artifact.name.replace("'", "''")}')\n"
                "try { Get-Content ./parts.txt | ForEach-Object { $input=[System.IO.File]::OpenRead($_); try { $input.CopyTo($output) } finally { $input.Dispose() } } } finally { $output.Dispose() }\n"
                f"$actual=(Get-FileHash -Algorithm SHA256 '{artifact.name.replace("'", "''")}').Hash.ToLowerInvariant()\n"
                f"if ($actual -ne '{digest}') {{ throw 'SHA-256 mismatch' }}\n",
                encoding="utf-8",
            )
            shell = root_path / "reassemble.sh"
            shell.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                f": > {json.dumps(artifact.name)}\n"
                f"while IFS= read -r part; do cat -- \"$part\" >> {json.dumps(artifact.name)}; done < parts.txt\n"
                f"printf '%s  %s\\n' {json.dumps(digest)} {json.dumps(artifact.name)} | sha256sum -c -\n",
                encoding="utf-8",
            )
            checksum = root_path / (artifact.name + ".sha256")
            checksum.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
            for helper in (part_list, readme, powershell, shell, checksum):
                self.storage.copy_file(helper, f"{folder}/{helper.name}")

            manifest = root_path / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "format": "wukong-raw-split-v1",
                        "name": artifact.name,
                        "sha256": digest,
                        "sizeBytes": size,
                        "partSizeBytes": self.part_size,
                        "parts": parts,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            # Manifest is the completion marker and must always be uploaded last.
            self.storage.copy_file(manifest, f"{folder}/manifest.json")
        return ArtifactRecord(artifact.name, folder_uri, digest, size)

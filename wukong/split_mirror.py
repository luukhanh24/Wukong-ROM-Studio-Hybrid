"""Cloudflare-safe multipart mirror over the existing scoped WebDAV remote."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Callable, Mapping

from .adapters import RcloneStorageAdapter, sha256_file
from .models import ArtifactRecord


DEFAULT_PART_SIZE = 64 * 1024 * 1024


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
        artifact = artifact.resolve()
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized or ".." in PurePosixPath(normalized).parts:
            raise ValueError("Mirror path is empty or contains path traversal")
        staging_key = staging_key.replace("\\", "/").strip("/")
        if not staging_key or ".." in PurePosixPath(staging_key).parts:
            raise ValueError("Mirror staging key is empty or contains path traversal")
        digest = sha256_file(artifact)
        size = artifact.stat().st_size
        folder = normalized + ".parts"
        staging_folder = f"_staging/{staging_key}/{artifact.name}.parts"
        manifest_path = f"{folder}/manifest.json"
        folder_uri = self.storage.remote_uri(folder)
        parts: list[dict[str, object]] = []
        completed = 0
        with TemporaryDirectory(prefix="wukong-dccloud-split-") as root:
            root_path = Path(root)
            manifest_invalidated = False

            def remote_matches(relative: str, expected_size: int, expected_digest: str) -> bool:
                if self.storage.stat_size(relative) != expected_size:
                    return False
                downloaded = root_path / ("verify-" + Path(relative).name)
                downloaded.unlink(missing_ok=True)
                try:
                    self.storage.download_file(relative, downloaded)
                    return (
                        downloaded.stat().st_size == expected_size
                        and sha256_file(downloaded).casefold() == expected_digest.casefold()
                    )
                except Exception:
                    return False
                finally:
                    downloaded.unlink(missing_ok=True)

            def manifest_layout_matches(candidate_parts: object) -> bool:
                if not isinstance(candidate_parts, list):
                    return False
                expected_count = (size + self.part_size - 1) // self.part_size
                if len(candidate_parts) != expected_count:
                    return False
                remaining = size
                for index, part in enumerate(candidate_parts, start=1):
                    expected_size = min(self.part_size, remaining)
                    expected_name = f"{artifact.name}.{index:03d}"
                    if (
                        not isinstance(part, dict)
                        or part.get("name") != expected_name
                        or part.get("sizeBytes") != expected_size
                        or not isinstance(part.get("sha256"), str)
                        or len(str(part["sha256"])) != 64
                        or any(character not in "0123456789abcdefABCDEF" for character in str(part["sha256"]))
                    ):
                        return False
                    remaining -= expected_size
                return remaining == 0

            def invalidate_manifest() -> None:
                nonlocal manifest_invalidated
                if manifest_invalidated:
                    return
                incomplete = root_path / "manifest.incomplete.json"
                incomplete.write_text(
                    json.dumps(
                        {
                            "format": "wukong-raw-split-v1",
                            "status": "incomplete",
                            "name": artifact.name,
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                staging_incomplete = f"{staging_folder}/manifest.incomplete.json"
                self.storage.copy_file(incomplete, staging_incomplete)
                self.storage.copy_remote(staging_incomplete, manifest_path)
                manifest_invalidated = True

            try:
                existing_text = self.storage.read_text(manifest_path)
                existing = json.loads(existing_text)
                existing_parts = existing.get("parts")
                if (
                    existing.get("format") == "wukong-raw-split-v1"
                    and str(existing.get("sha256") or "").casefold() == digest.casefold()
                    and int(existing.get("sizeBytes", -1)) == size
                    and int(existing.get("partSizeBytes", -1)) == self.part_size
                    and manifest_layout_matches(existing_parts)
                    and all(
                        remote_matches(
                            f"{folder}/{part['name']}",
                            int(part["sizeBytes"]),
                            str(part["sha256"]),
                        )
                        for part in existing_parts  # type: ignore[union-attr]
                    )
                ):
                    return ArtifactRecord(artifact.name, folder_uri, digest, size)
            except Exception:
                pass

            self.storage.make_dir(staging_folder)
            self.storage.make_dir(folder)
            with artifact.open("rb") as source:
                index = 1
                while True:
                    body = source.read(self.part_size)
                    if not body:
                        break
                    part_name = f"{artifact.name}.{index:03d}"
                    part_path = root_path / part_name
                    part_path.write_bytes(body)
                    part_digest = sha256_file(part_path)
                    final_part = f"{folder}/{part_name}"
                    staging_part = f"{staging_folder}/{part_name}"
                    if not remote_matches(final_part, len(body), part_digest):
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

                        if not remote_matches(staging_part, len(body), part_digest):
                            self.storage.copy_file(
                                part_path,
                                staging_part,
                                progress_callback=on_part if progress_callback is not None else None,
                            )
                        invalidate_manifest()
                        self.storage.copy_remote(staging_part, final_part)
                        if not remote_matches(final_part, len(body), part_digest):
                            raise RuntimeError("DC Cloud multipart checksum mismatch")
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
                staging_helper = f"{staging_folder}/{helper.name}"
                self.storage.copy_file(helper, staging_helper)
                invalidate_manifest()
                self.storage.copy_remote(staging_helper, f"{folder}/{helper.name}")

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
            staging_manifest = f"{staging_folder}/manifest.json"
            self.storage.copy_file(manifest, staging_manifest)
            invalidate_manifest()
            self.storage.copy_remote(staging_manifest, f"{folder}/manifest.json")
            self.storage.remove_tree(staging_folder)
        return ArtifactRecord(artifact.name, folder_uri, digest, size)

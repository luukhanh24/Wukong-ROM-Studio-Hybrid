"""Repair DC Cloud mirrors from a canonical Google Drive job manifest."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from wukong.adapters import RcloneStorageAdapter, SourceIntegrityError, sha256_file
from wukong.artifact_mirror import ArtifactMirrorPublisher, DCloudMirrorConfig, attach_mirror
from wukong.models import ArtifactRecord, JobManifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair DC Cloud mirrors for one job")
    parser.add_argument("job_id")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args()
    config = DCloudMirrorConfig.from_env(config_path=args.config)
    if not config.enabled:
        raise SystemExit("DC Cloud mirror is disabled")
    primary = RcloneStorageAdapter(config_path=args.config)
    manifest_uri = primary.remote_uri(f"jobs/{args.job_id}/manifest.json")
    with tempfile.TemporaryDirectory(prefix="wukong-mirror-repair-") as root:
        directory = Path(root)
        manifest_path = directory / "manifest.json"
        primary.run_command(primary._args("copyto", manifest_uri, str(manifest_path), "--retries", "3"))
        manifest = JobManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        publisher = ArtifactMirrorPublisher(config)
        repaired: list[ArtifactRecord] = []
        failed = False
        for artifact in manifest.artifacts:
            if Path(artifact.name).suffix.casefold() != ".zip":
                repaired.append(artifact)
                continue
            if Path(artifact.name).name != artifact.name:
                raise ValueError("Artifact name contains a path separator")
            local = directory / artifact.name
            primary.run_command(primary._args("copyto", artifact.uri, str(local), "--retries", "3"))
            if not local.is_file() or local.stat().st_size != artifact.size_bytes:
                raise SourceIntegrityError(f"Primary artifact size mismatch: {artifact.name}")
            if sha256_file(local).casefold() != artifact.sha256.casefold():
                raise SourceIntegrityError(f"Primary artifact checksum mismatch: {artifact.name}")
            prefix = f"{primary.remote}:WukongROM/"
            relative = artifact.uri[len(prefix):] if artifact.uri.startswith(prefix) else ""
            if not relative:
                raise ValueError("Artifact URI is not inside WukongROM")
            mirror_root = config.root.strip("/")
            final_relative = relative
            if not final_relative.casefold().startswith(mirror_root.casefold() + "/"):
                final_relative = f"{mirror_root}/{final_relative}"
            mirror = publisher.publish(
                local,
                job_id=args.job_id,
                device="repair",
                build="repair",
                relative_path=final_relative,
            )
            failed = failed or mirror.status == "failed"
            repaired.append(attach_mirror(artifact, mirror))
        updated = JobManifest(
            job_id=manifest.job_id,
            owner=manifest.owner,
            recipe_digest=manifest.recipe_digest,
            status=manifest.status,
            stage=manifest.stage,
            progress=manifest.progress,
            runner=manifest.runner,
            external_run_id=manifest.external_run_id,
            checkpoint=manifest.checkpoint,
            checkpoint_at=manifest.checkpoint_at,
            rom_metadata=manifest.rom_metadata,
            artifacts=repaired,
            error=manifest.error,
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
            finished_at=manifest.finished_at,
        )
        manifest_path.write_text(json.dumps(updated.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        primary.copy_file(manifest_path, f"jobs/{args.job_id}/manifest.json")
        if args.manifest_output:
            args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
            args.manifest_output.write_text(
                manifest_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        print(
            json.dumps(
                {
                    "jobId": args.job_id,
                    "mirrors": [
                        {
                            "artifact": artifact.name,
                            "provider": mirror.provider,
                            "status": mirror.status,
                            "errorCode": mirror.error_code,
                        }
                        for artifact in repaired
                        for mirror in artifact.mirrors
                    ],
                },
                sort_keys=True,
            )
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

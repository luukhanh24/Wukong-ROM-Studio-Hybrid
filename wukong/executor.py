from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Any, Callable

from .adapters import RcloneStorageAdapter, SourceIntegrityError, sha256_file, source_adapter_for
from .cloud_sync import CloudJobSync
from .content_packs import ContentPackManager, validate_content_index
from .models import ArtifactRecord, BuildRecipe, JobManifest, JobStatus
from .orchestrator import JobStore, OrchestrationError
from studio_paths import CONTENT_ROOT, SCRIPT_ROOT, WORKSPACE_ROOT


LegacyBuild = Callable[[str, dict[str, Any], Path, Callable[[dict[str, Any]], None]], dict[str, Any]]

# Checkpoint only after stages that materially advance the reusable workspace.
# Read-only/preflight stages such as inspect_rom would upload the same multi-GB
# tree again and can exhaust cloud API quotas without improving resumability.
CHECKPOINT_STAGES = {
    "extract_payload",
    "unpack_partitions",
    "sync_configs",
    "repack_partitions",
    "repack_super",
    "patch_vbmeta",
    "patch_vendor_boot",
}


def run_legacy_build(
    job_id: str,
    legacy_spec: dict[str, Any],
    workspace: Path,
    callback: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    from studio_core import BuildSpec, execute_build, prepare_workspace, read_rom_metadata

    spec = BuildSpec.from_dict(legacy_spec)
    metadata = read_rom_metadata(spec.romPath)
    prepare_workspace(
        workspace,
        job_id,
        str(metadata["version_name"]),
        resume=bool(spec.resumeFromJobId),
        rom_sha256=spec.romSha256,
        spec_fingerprint=spec.specFingerprint,
    )
    return execute_build(job_id, spec, workspace, callback)


class LocalJobExecutor:
    def __init__(
        self,
        *,
        store: JobStore,
        workspace_root: Path,
        storage_factory: Callable[[str], RcloneStorageAdapter] | None = None,
        legacy_build: LegacyBuild = run_legacy_build,
        rclone_config: Path | None = None,
        build_workspace_root: Path | None = None,
        content_root: Path | None = None,
        content_index: Path | None = None,
    ) -> None:
        self.store = store
        self.workspace_root = workspace_root.resolve()
        self.storage_factory = storage_factory or (
            lambda remote: RcloneStorageAdapter(remote=remote, config_path=rclone_config)
        )
        self.legacy_build = legacy_build
        self.rclone_config = rclone_config
        self.build_workspace_root = (build_workspace_root or WORKSPACE_ROOT).resolve()
        self.content_root = (content_root or CONTENT_ROOT).resolve()
        self.content_index = (
            content_index or SCRIPT_ROOT / "content-packs" / "index.json"
        ).resolve()

    def execute(self, job_id: str) -> JobManifest:
        manifest = self.store.get(job_id)
        recipe = self.store.recipe(job_id)
        if not manifest or not recipe:
            raise OrchestrationError("Job not found")
        if manifest.status not in {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.CANCELLED}:
            raise OrchestrationError(f"Job cannot execute from status {manifest.status.value}")
        root = self.workspace_root / job_id
        source_name = recipe.source.uri.replace("\\", "/").rsplit("/", 1)[-1].split("?", 1)[0]
        if ":" in source_name:
            source_name = source_name.rsplit(":", 1)[-1]
        source_name = "".join(character for character in source_name if character.isalnum() or character in "._-")
        source_target = root / "input" / (source_name or "rom.zip")
        if not source_target.suffix:
            source_target = source_target.with_suffix(".zip")
        try:
            self.store.update(job_id, status=JobStatus.PREFLIGHT, stage="preflight", progress=0.0, error=None)
            self.store.append_event(job_id, "state", status=JobStatus.PREFLIGHT.value, stage="preflight")
            self.store.update(job_id, status=JobStatus.DOWNLOADING, stage="download", progress=0.0)
            adapter = source_adapter_for(recipe.source.kind, config_path=self.rclone_config)
            source = adapter.materialize(recipe.source.uri, source_target, recipe.source.sha256)
            self.store.append_event(
                job_id,
                "source",
                path=str(source.path),
                sha256=source.sha256,
                sizeBytes=source.size_bytes,
            )
            storage = self.storage_factory(recipe.storage.remote)
            if recipe.task == "source_mirror":
                self.store.update(job_id, status=JobStatus.UPLOADING, stage="upload", progress=0.8)
                record = storage.store_source(source.path, device=recipe.device, digest=source.sha256)
                return self._succeed(job_id, [record])
            if recipe.task == "artifact_publish":
                self.store.update(job_id, status=JobStatus.UPLOADING, stage="upload", progress=0.8)
                record = storage.publish_artifact(source.path, device=recipe.device, build="published")
                return self._succeed(job_id, [record])

            self._ensure_content_packs(recipe)
            self.store.update(job_id, status=JobStatus.RUNNING, stage="build", progress=0.1)
            from studio_core import (
                BuildSpec,
                build_spec_fingerprint,
                read_rom_metadata,
                workspace_for_version,
            )

            metadata = read_rom_metadata(source.path)
            build_workspace = workspace_for_version(
                str(metadata.get("version_name") or source.path.stem),
                fallback=source.path.stem,
                root=self.build_workspace_root,
            )
            legacy_spec = recipe.to_legacy_spec(local_rom_path=str(source.path))
            legacy_spec["romSha256"] = source.sha256
            if manifest.checkpoint:
                if manifest.checkpoint.startswith("local:"):
                    checkpoint_path = Path(manifest.checkpoint[6:]).resolve()
                    if checkpoint_path != build_workspace:
                        raise OrchestrationError("Resume checkpoint does not match the ROM workspace")
                else:
                    if build_workspace.exists():
                        import shutil

                        shutil.rmtree(build_workspace)
                    storage.restore_tree(manifest.checkpoint, build_workspace)
                marker_path = build_workspace / ".wkstudio-workspace.json"
                if not marker_path.is_file():
                    raise OrchestrationError("Resume checkpoint is missing its workspace marker")
                import json

                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                legacy_spec["specFingerprint"] = marker.get("specFingerprint")
                legacy_spec["resumeFromJobId"] = str(marker.get("jobId") or job_id)
                legacy_spec["resumePreset"] = recipe.build.preset
                legacy_spec["preset"] = "resume"
            else:
                legacy_spec["specFingerprint"] = build_spec_fingerprint(BuildSpec.from_dict(legacy_spec))

            def on_event(event: dict[str, Any]) -> None:
                current = self.store.get(job_id)
                if current and current.status == JobStatus.CANCELLED:
                    raise OrchestrationError("Job was cancelled")
                event_type = str(event.get("type") or "build")
                stage = str(event.get("step") or event.get("stage") or "build")
                progress = event.get("progress")
                changes: dict[str, object] = {"stage": stage}
                if isinstance(progress, (int, float)):
                    changes["progress"] = max(0.0, min(float(progress) / 100, 0.79))
                self.store.update(job_id, **changes)
                self.store.append_event(job_id, event_type, **event)
                self._push_cloud_progress(job_id, storage)
                if event.get("status") == "success" and stage in CHECKPOINT_STAGES:
                    try:
                        if os.environ.get("GITHUB_ACTIONS", "").casefold() == "true":
                            checkpoint = storage.sync_tree(
                                build_workspace,
                                f"checkpoints/{job_id}/{stage}",
                            )
                        else:
                            checkpoint = f"local:{build_workspace}"
                        from .models import utc_now

                        self.store.update(job_id, checkpoint=checkpoint, checkpoint_at=utc_now())
                        self.store.append_event(job_id, "checkpoint", checkpoint=checkpoint, stage=stage)
                        self._push_cloud_progress(job_id, storage)
                    except Exception as exc:
                        self.store.append_event(
                            job_id,
                            "warning",
                            warning=f"Checkpoint upload failed after {stage}: {exc}",
                        )
                        self._push_cloud_progress(job_id, storage)

            result = self.legacy_build(
                job_id,
                legacy_spec,
                build_workspace,
                on_event,
            )
            current = self.store.get(job_id)
            if current and current.status == JobStatus.CANCELLED:
                return current
            output_values = result.get("outputZips") or ([result.get("outputZip")] if result.get("outputZip") else [])
            outputs = [Path(str(value)).resolve() for value in output_values if value]
            if not outputs:
                raise OrchestrationError("Build completed without an artifact")
            records: list[ArtifactRecord] = []
            self.store.update(job_id, status=JobStatus.UPLOADING, stage="upload", progress=0.8)
            for output in outputs:
                if recipe.storage.publish_artifact:
                    records.append(
                        storage.publish_artifact(output, device=recipe.device, build=recipe.build.mod_version)
                    )
                else:
                    records.append(
                        ArtifactRecord(
                            name=output.name,
                            uri=str(output),
                            sha256=sha256_file(output),
                            size_bytes=output.stat().st_size,
                        )
                    )
            return self._succeed(job_id, records)
        except Exception as exc:
            current = self.store.get(job_id)
            if current and current.status == JobStatus.CANCELLED:
                self._push_cancelled_terminal(job_id, recipe)
                return current
            self.store.append_event(job_id, "error", error=str(exc), traceback=traceback.format_exc())
            return self.store.update(
                job_id,
                status=JobStatus.FAILED,
                error=str(exc),
                stage="failed",
            )

    def _push_cancelled_terminal(self, job_id: str, recipe: BuildRecipe) -> None:
        if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true":
            return
        try:
            CloudJobSync(self.store, self.storage_factory(recipe.storage.remote)).push(job_id)
        except Exception as exc:
            self.store.append_event(job_id, "warning", warning=f"Cancelled cloud sync failed: {exc}")

    def _ensure_content_packs(self, recipe: BuildRecipe) -> None:
        if not self.content_index.is_file():
            raise OrchestrationError(f"Content-pack index is unavailable: {self.content_index}")
        import json

        index = json.loads(self.content_index.read_text(encoding="utf-8"))
        validate_content_index(index)
        required = [f"MOD/{recipe.build.mod_version}", "copy-image/v1", "OFX/v1", "TWRP/v1"]
        manager = ContentPackManager(
            self.content_root,
            rclone_config=self.rclone_config,
        )
        for pack_id in required:
            pack = next((item for item in index["packs"] if item["id"] == pack_id), None)
            if not pack:
                raise OrchestrationError(f"Content-pack is unavailable: {pack_id}")
            target = (self.content_root / str(pack["target"])).resolve()
            try:
                manager.verify(target, pack)
            except (FileNotFoundError, SourceIntegrityError):
                if not self.rclone_config:
                    raise OrchestrationError(
                        f"Content-pack {pack_id} is missing or invalid and rclone is not configured"
                    )
                manager.install(index, pack_id)

    def _push_cloud_progress(self, job_id: str, storage: RcloneStorageAdapter) -> None:
        if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true":
            return
        try:
            CloudJobSync(self.store, storage).push(job_id)
        except Exception as exc:
            self.store.append_event(job_id, "warning", warning=f"Cloud progress sync failed: {exc}")

    def _succeed(self, job_id: str, artifacts: list[ArtifactRecord]) -> JobManifest:
        self.store.append_event(
            job_id,
            "artifacts",
            artifacts=[artifact.uri for artifact in artifacts],
        )
        manifest = self.store.update(
            job_id,
            status=JobStatus.SUCCEEDED,
            stage="complete",
            progress=1.0,
            artifacts=artifacts,
        )
        recipe = self.store.recipe(job_id)
        if recipe and os.environ.get("GITHUB_ACTIONS", "").casefold() == "true":
            try:
                CloudJobSync(self.store, self.storage_factory(recipe.storage.remote)).push(job_id)
            except Exception as exc:
                self.store.append_event(job_id, "warning", warning=f"Terminal cloud sync failed: {exc}")
        return manifest

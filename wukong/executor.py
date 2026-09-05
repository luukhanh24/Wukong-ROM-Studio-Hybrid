from __future__ import annotations

import os
import time
import traceback
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .actions_ui import GitHubActionsUI
from .artifacts import PreparedArtifact, prepare_artifact
from .adapters import RcloneStorageAdapter, SourceIntegrityError, sha256_file, source_adapter_for
from .artifact_mirror import ArtifactMirrorPublisher, DCloudMirrorConfig, attach_mirror
from .cloud_sync import CloudJobSync
from .content_packs import ContentPackManager, validate_content_index
from .models import ArtifactRecord, BuildRecipe, JobManifest, JobStatus, preset_edition_label
from .orchestrator import JobStore, OrchestrationError
from .pipeline import CHECKPOINT_PIPELINE_STEPS
from studio_paths import CONTENT_ROOT, SCRIPT_ROOT, WORKSPACE_ROOT


LegacyBuild = Callable[[str, dict[str, Any], Path, Callable[[dict[str, Any]], None]], dict[str, Any]]

# Checkpoint only after stages that materially advance the reusable workspace.
# Read-only/preflight stages such as inspect_rom would upload the same multi-GB
# tree again and can exhaust cloud API quotas without improving resumability.
CHECKPOINT_STAGES = set(CHECKPOINT_PIPELINE_STEPS)
# A hosted checkpoint uploads the whole multi-GB workspace.  Production timing
# showed that snapshots after unpack/sync/repack cost ~50 minutes while the
# work they protect takes only a few minutes.  Keep the valuable post-extract
# snapshot (it avoids re-downloading and re-extracting the ROM) and let local
# runs retain their cheap filesystem checkpoints after every reusable stage.
DEFAULT_CLOUD_CHECKPOINT_STAGES = {"extract_payload"}
# A post-extraction resume only needs the workspace identity, the successful
# stage marker, and the extracted source images consumed by ``batch_unpack``.
# Keeping this contract explicit prevents a hosted checkpoint from scanning
# and uploading later-stage trees such as ``rom-unpack`` and package caches.
CLOUD_CHECKPOINT_PATHS: dict[str, tuple[str, ...]] = {
    "extract_payload": (
        ".wkstudio-workspace.json",
        ".studio-markers/extract_payload.json",
        "source_rom",
    ),
}
CLOUD_PROGRESS_RETRY_SECONDS = 30.0
CLOUD_PROGRESS_INTERVAL_SECONDS = 90.0
CLOUD_PROGRESS_DELTA_PERCENT = 10.0
CLOUD_PUSH_WARNING_INTERVAL_SECONDS = 600.0


def artifact_upload_edition(
    recipe: BuildRecipe,
    output: Path,
    output_index: int,
    output_count: int,
) -> str:
    """Return the stable Drive folder label for one packaged edition.

    The preset key remains an internal build contract, while the configured
    edition label is the user-facing filename/Drive folder name. Both builds
    are emitted in Lite-then-Plus order, so the output index selects its label.
    """

    defaults = {"lite": "Lite", "plus": "Plus", "custom": "Custom"}
    labels = recipe.build.edition_labels
    preset = recipe.build.preset.casefold()
    if preset in {"resume", "standard"}:
        preset = "plus" if preset == "resume" else "lite"
    if preset == "both":
        preset = "lite" if output_index == 0 else "plus"
    if preset in defaults:
        return preset_edition_label(preset, labels).strip()
    name = output.name.casefold()
    for key, fallback in defaults.items():
        label = str(labels.get(key) or fallback).strip()
        marker = f"_{label.casefold()}_"
        if marker in name or name.endswith(f"_{label.casefold()}.zip"):
            return label
    if output_count > 1:
        return preset_edition_label("plus", labels).strip()
    return recipe.build.mod_version


def checkpoint_stages_for_environment() -> set[str]:
    if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true":
        return set(CHECKPOINT_STAGES)
    configured = os.environ.get("WUKONG_CLOUD_CHECKPOINT_STAGES", "").strip()
    if not configured:
        return set(DEFAULT_CLOUD_CHECKPOINT_STAGES)
    return {
        item.strip()
        for item in configured.split(",")
        if item.strip() in CHECKPOINT_STAGES
    }


def checkpoint_paths_for_stage(stage: str) -> tuple[str, ...] | None:
    """Return the minimal workspace paths needed to resume ``stage``.

    ``None`` intentionally means full-workspace behavior for stages whose
    dependency contract has not been narrowed yet.  This keeps custom
    checkpoint policies safe while the hosted extract snapshot is optimized.
    """

    return CLOUD_CHECKPOINT_PATHS.get(stage)


def sync_checkpoint_tree(
    storage: Any,
    source: Path,
    relative_path: str,
    stage: str,
) -> str:
    """Upload a stage checkpoint using its narrowed dependency contract."""

    checkpoint_paths = checkpoint_paths_for_stage(stage)
    sync_tree_subset = getattr(storage, "sync_tree_subset", None)
    if checkpoint_paths and callable(sync_tree_subset):
        return sync_tree_subset(source, relative_path, checkpoint_paths)
    return storage.sync_tree(source, relative_path)


def cloud_progress_sync_mode(
    event: Mapping[str, object],
    *,
    previous_stage: str,
    previous_progress: float | None,
    sample_counter: int,
    last_sync_at: float,
    now: float,
) -> str | None:
    """Select a bounded Drive sync that keeps Mini App progress current."""

    stage = str(event.get("step") or event.get("stage") or "build")
    status = str(event.get("status") or "")
    event_type = str(event.get("type") or "build")
    if status == "failed" or event_type in {"error", "checkpoint"}:
        return "full"
    if (status == "success" or event_type == "warning") and sample_counter % 2 == 1:
        return "full"
    if stage != previous_stage:
        return "manifest"
    progress = event_progress(event)
    interval_elapsed = now - last_sync_at >= CLOUD_PROGRESS_INTERVAL_SECONDS
    progress_changed = previous_progress is None or (
        isinstance(progress, (int, float))
        and abs(float(progress) - previous_progress) >= CLOUD_PROGRESS_DELTA_PERCENT
    )
    if isinstance(progress, (int, float)) and interval_elapsed and progress_changed:
            return "manifest"
    return None


def event_progress(event: Mapping[str, object]) -> float | None:
    progress = event.get("progress")
    if not isinstance(progress, (int, float)):
        details = event.get("details")
        if isinstance(details, Mapping):
            progress = details.get("progress")
    return float(progress) if isinstance(progress, (int, float)) else None


def source_target_for(recipe: BuildRecipe, root: Path) -> Path:
    source_name = recipe.source.uri.replace("\\", "/").rsplit("/", 1)[-1].split("?", 1)[0]
    if ":" in source_name:
        source_name = source_name.rsplit(":", 1)[-1]
    source_name = "".join(
        character for character in source_name if character.isalnum() or character in "._-"
    )
    target = root / "input" / (source_name or "rom.zip")
    if recipe.task == "build" and target.suffix.casefold() != ".zip":
        target = target.with_suffix(".zip")
    elif not target.suffix:
        target = target.with_suffix(".zip")
    return target


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
        actions_ui: GitHubActionsUI | None = None,
        mirror_publisher: ArtifactMirrorPublisher | None = None,
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
        self.actions_ui = actions_ui or GitHubActionsUI()
        if mirror_publisher is not None:
            self.mirror_publisher = mirror_publisher
        else:
            mirror_config = DCloudMirrorConfig.from_env(config_path=rclone_config)
            # The WebDAV device is scoped to My Files/WukongROM, unlike the
            # primary Drive remote.  Keep the mirror path relative to that
            # scoped root so WUKONG_DCCLOUD_ROOT=ROM maps to the shared
            # WukongROM/ROM folder rather than WukongROM/WukongROM/ROM.
            mirror_storage_factory = (
                self.storage_factory
                if storage_factory is not None
                else lambda remote: RcloneStorageAdapter(
                    remote=remote,
                    root="",
                    config_path=rclone_config,
                )
            )
            self.mirror_publisher = ArtifactMirrorPublisher(
                mirror_config,
                storage_factory=mirror_storage_factory,
            )
        self._cloud_push_warning_at: dict[str, float] = {}

    def execute(self, job_id: str) -> JobManifest:
        manifest = self.store.get(job_id)
        recipe = self.store.recipe(job_id)
        if not manifest or not recipe:
            raise OrchestrationError("Job not found")
        if manifest.status not in {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.CANCELLED}:
            raise OrchestrationError(f"Job cannot execute from status {manifest.status.value}")
        root = self.workspace_root / job_id
        source_target = source_target_for(recipe, root)
        try:
            self.store.update(job_id, status=JobStatus.PREFLIGHT, stage="preflight", progress=0.0, error=None)
            self.store.append_event(job_id, "state", status=JobStatus.PREFLIGHT.value, stage="preflight")
            self.store.update(job_id, status=JobStatus.DOWNLOADING, stage="download", progress=0.0)
            self.actions_ui.begin("download")
            storage = self.storage_factory(recipe.storage.remote)
            self._push_cloud_manifest(job_id, storage)
            adapter = source_adapter_for(recipe.source.kind, config_path=self.rclone_config)
            download_started = time.monotonic()
            source = adapter.materialize(recipe.source.uri, source_target, recipe.source.sha256)
            self.store.append_event(job_id, "metric", stage="materialize_source", durationSeconds=round(time.monotonic() - download_started, 3), bytesProcessed=source.size_bytes)
            if recipe.source.size_bytes is not None and source.size_bytes != recipe.source.size_bytes:
                source.path.unlink(missing_ok=True)
                raise SourceIntegrityError(
                    f"ROM size mismatch: expected {recipe.source.size_bytes}, got {source.size_bytes}"
                )
            self.store.append_event(
                job_id,
                "source",
                path=str(source.path),
                sha256=source.sha256,
                sizeBytes=source.size_bytes,
            )
            if recipe.task == "build":
                try:
                    from .source_probe import inspect_local_rom_metadata

                    local_metadata = inspect_local_rom_metadata(source.path)
                    if local_metadata:
                        manifest = self.store.update(
                            job_id,
                            rom_metadata={**manifest.rom_metadata, **local_metadata},
                        )
                        self.store.append_event(
                            job_id,
                            "source_metadata",
                            fields=sorted(local_metadata),
                        )
                except (
                    OSError,
                    RuntimeError,
                    ValueError,
                    zipfile.BadZipFile,
                    zipfile.LargeZipFile,
                ) as exc:
                    self.store.append_event(
                        job_id,
                        "warning",
                        warning=f"Local ROM metadata inspection was unavailable: {exc}",
                    )
            if recipe.task == "source_mirror":
                self.store.update(job_id, status=JobStatus.UPLOADING, stage="upload", progress=0.8)
                self._push_cloud_progress(job_id, storage)
                self.actions_ui.begin("upload")
                record = storage.store_source(source.path, device=recipe.device, digest=source.sha256)
                return self._succeed(job_id, [record])
            if recipe.task == "artifact_publish":
                self.store.update(job_id, status=JobStatus.UPLOADING, stage="upload", progress=0.8)
                self._push_cloud_progress(job_id, storage)
                self.actions_ui.begin("upload")
                record = self._publish_artifact_with_mirror(
                    job_id,
                    source.path,
                    recipe.device,
                    "published",
                    None,
                    lambda: storage.publish_artifact(
                        source.path,
                        device=recipe.device,
                        build="published",
                    ),
                )
                return self._succeed(job_id, [record])

            self._ensure_content_packs(recipe)
            recipe = self._reconcile_recipe_mods(job_id, recipe)
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
            resume_ready = False
            if manifest.checkpoint:
                resume_ready = self._try_restore_checkpoint(
                    job_id,
                    manifest.checkpoint,
                    build_workspace,
                    storage,
                )
                if resume_ready:
                    marker_path = build_workspace / ".wkstudio-workspace.json"
                    import json

                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    legacy_spec["specFingerprint"] = marker.get("specFingerprint")
                    legacy_spec["resumeFromJobId"] = str(marker.get("jobId") or job_id)
                    legacy_spec["resumePreset"] = recipe.build.preset
                    legacy_spec["preset"] = "resume"
                else:
                    legacy_spec["specFingerprint"] = build_spec_fingerprint(BuildSpec.from_dict(legacy_spec))
            else:
                legacy_spec["specFingerprint"] = build_spec_fingerprint(BuildSpec.from_dict(legacy_spec))

            checkpoint_upload_enabled = True
            checkpoint_stages = checkpoint_stages_for_environment()
            # On Actions, throttle cloud progress pushes: every stage event hits Drive
            # and easily exhausts API quota during long builds.
            cloud_progress_last_sync_at = 0.0
            cloud_progress_value: float | None = None
            cloud_progress_sample_counter = 0
            cloud_progress_stage = ""
            cloud_progress_retry_at = 0.0

            def on_event(event: dict[str, Any]) -> None:
                nonlocal checkpoint_upload_enabled, cloud_progress_last_sync_at
                nonlocal cloud_progress_retry_at, cloud_progress_sample_counter
                nonlocal cloud_progress_stage, cloud_progress_value
                current = self.store.get(job_id)
                if current and current.status == JobStatus.CANCELLED:
                    raise OrchestrationError("Job was cancelled")
                event_type = str(event.get("type") or "build")
                stage = str(event.get("step") or event.get("stage") or "build")
                progress = event_progress(event)
                changes: dict[str, object] = {"stage": stage}
                if progress is not None:
                    changes["progress"] = max(0.0, min(progress / 100, 0.79))
                self.store.update(job_id, **changes)
                self.store.append_event(job_id, event_type, **event)
                self.actions_ui.event(event)
                status = str(event.get("status") or "")
                terminalish = status in {"success", "failed"} or event_type in {
                    "error",
                    "warning",
                    "checkpoint",
                }
                if terminalish:
                    cloud_progress_sample_counter += 1
                now = time.monotonic()
                sync_mode = cloud_progress_sync_mode(
                    event,
                    previous_stage=cloud_progress_stage,
                    previous_progress=cloud_progress_value,
                    sample_counter=cloud_progress_sample_counter,
                    last_sync_at=cloud_progress_last_sync_at,
                    now=now,
                )
                if sync_mode and (sync_mode == "full" or now >= cloud_progress_retry_at):
                    synced = (
                        self._push_cloud_manifest(job_id, storage)
                        if sync_mode == "manifest"
                        else self._push_cloud_progress(job_id, storage)
                    )
                    if synced:
                        cloud_progress_stage = stage
                        progress_value = event_progress(event)
                        if progress_value is not None:
                            cloud_progress_value = progress_value
                        cloud_progress_last_sync_at = now
                        cloud_progress_retry_at = 0.0
                    else:
                        cloud_progress_retry_at = now + CLOUD_PROGRESS_RETRY_SECONDS
                if (
                    event.get("status") == "success"
                    and stage in checkpoint_stages
                    and checkpoint_upload_enabled
                ):
                    try:
                        if os.environ.get("GITHUB_ACTIONS", "").casefold() == "true":
                            if os.environ.get("WUKONG_DISABLE_CLOUD_CHECKPOINTS", "").strip().casefold() in {
                                "1",
                                "true",
                                "yes",
                                "on",
                            }:
                                raise RuntimeError("Cloud checkpoints disabled by WUKONG_DISABLE_CLOUD_CHECKPOINTS")
                            relative_checkpoint = f"checkpoints/{job_id}/{stage}"
                            checkpoint_started = time.monotonic()
                            checkpoint = sync_checkpoint_tree(
                                storage,
                                build_workspace,
                                relative_checkpoint,
                                stage,
                            )
                        else:
                            checkpoint = f"local:{build_workspace}"
                        from .models import utc_now

                        if os.environ.get("GITHUB_ACTIONS", "").casefold() == "true":
                            self.store.append_event(job_id, "metric", stage="checkpoint", sourceStage=stage, durationSeconds=round(time.monotonic() - checkpoint_started, 3))
                        self.store.update(job_id, checkpoint=checkpoint, checkpoint_at=utc_now())
                        self.store.append_event(job_id, "checkpoint", checkpoint=checkpoint, stage=stage)
                        self._push_cloud_progress(job_id, storage)
                    except Exception as exc:
                        checkpoint_upload_enabled = False
                        self.store.append_event(
                            job_id,
                            "warning",
                            warning=(
                                f"Checkpoint upload failed after {stage}; "
                                f"remaining checkpoints are disabled for this run: {exc}"
                            ),
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
                self.actions_ui.close_group()
                self.actions_ui.write_summary(current, recipe)
                self._push_cancelled_terminal(job_id, recipe)
                return current
            output_values = result.get("outputZips") or ([result.get("outputZip")] if result.get("outputZip") else [])
            outputs = [Path(str(value)).resolve() for value in output_values if value]
            if not outputs:
                raise OrchestrationError("Build completed without an artifact")
            records: list[ArtifactRecord] = []
            self.store.update(job_id, status=JobStatus.UPLOADING, stage="upload", progress=0.8)
            self._push_cloud_progress(job_id, storage)
            self.actions_ui.begin("upload")
            last_upload_push = 0.0
            last_upload_event = 0.0
            for output_index, output in enumerate(outputs):
                checksum_started = time.monotonic()
                prepared = prepare_artifact(output, hasher=sha256_file)
                self.store.append_event(job_id, "metric", stage="checksum", durationSeconds=round(time.monotonic() - checksum_started, 3), bytesProcessed=prepared.size_bytes, cacheHit=False)
                upload_started = time.monotonic()
                if recipe.storage.publish_artifact:
                    def report_upload(values: Mapping[str, object], *, current: Path = output) -> None:
                        nonlocal last_upload_event, last_upload_push
                        percent = float(values.get("percent") or 0.0)
                        now = time.monotonic()
                        if now - last_upload_event < 5.0 and percent < 100.0:
                            return
                        last_upload_event = now
                        overall = (output_index + percent / 100.0) / max(1, len(outputs))
                        self.store.update(job_id, stage="upload", progress=0.8 + overall * 0.19)
                        self.store.append_event(
                            job_id,
                            "upload_progress",
                            stage="upload",
                            fileName=current.name,
                            fileIndex=output_index + 1,
                            fileCount=len(outputs),
                            **dict(values),
                        )
                        if now - last_upload_push >= 5.0:
                            last_upload_push = now
                            self._push_cloud_progress(job_id, storage)

                    artifact_build = (
                        artifact_upload_edition(recipe, output, output_index, len(outputs))
                        if recipe.storage.artifact_root
                        else recipe.build.mod_version
                    )
                    record = self._publish_artifact_with_mirror(
                        job_id,
                        output,
                        recipe.device,
                        artifact_build,
                        recipe.storage.artifact_root,
                        lambda: (
                            storage.publish_artifact(
                                output,
                                device=recipe.device,
                                build=artifact_build,
                                relative_root=recipe.storage.artifact_root,
                                progress_callback=report_upload,
                                prepared=prepared,
                            )
                            if isinstance(storage, RcloneStorageAdapter)
                            else storage.publish_artifact(
                                output,
                                device=recipe.device,
                                build=recipe.build.mod_version,
                            )
                        ),
                        prepared=prepared,
                    )
                    self.store.append_event(job_id, "metric", stage="publish", durationSeconds=round(time.monotonic() - upload_started, 3), bytesProcessed=prepared.size_bytes)
                    records.append(record)
                    self.store.append_event(
                        job_id,
                        "upload_progress",
                        stage="upload",
                        fileName=output.name,
                        fileIndex=output_index + 1,
                        fileCount=len(outputs),
                        bytes=record.size_bytes,
                        totalBytes=record.size_bytes,
                        speedBytesPerSecond=0.0,
                        etaSeconds=0.0,
                        percent=100.0,
                    )
                else:
                    records.append(
                        ArtifactRecord(
                            name=output.name,
                            uri=str(output),
                            sha256=prepared.sha256,
                            size_bytes=prepared.size_bytes,
                        )
                    )
            return self._succeed(job_id, records)
        except Exception as exc:
            current = self.store.get(job_id)
            if current and current.status == JobStatus.CANCELLED:
                self.actions_ui.close_group()
                self.actions_ui.write_summary(current, recipe)
                self._push_cancelled_terminal(job_id, recipe)
                return current
            self.actions_ui.close_group()
            self.store.append_event(job_id, "error", error=str(exc), traceback=traceback.format_exc())
            failed = self.store.update(
                job_id,
                status=JobStatus.FAILED,
                error=str(exc),
                stage="failed",
            )
            self.actions_ui.write_summary(failed, recipe)
            return failed

    def _publish_artifact_with_mirror(
        self,
        job_id: str,
        artifact: Path,
        device: str,
        build: str,
        relative_root: str | None,
        publish_primary: Callable[[], ArtifactRecord],
        prepared: PreparedArtifact | None = None,
    ) -> ArtifactRecord:
        prepared = prepare_artifact(artifact, prepared, hasher=sha256_file)
        local_record = ArtifactRecord(
            name=artifact.name,
            uri=str(artifact),
            sha256=prepared.sha256,
            size_bytes=prepared.size_bytes,
        )
        mirrored_record = self._mirror_artifact(
            job_id,
            local_record,
            artifact,
            device,
            build,
            relative_root,
            prepared=prepared,
        )
        try:
            primary_record = publish_primary()
        except Exception as exc:
            available_mirror = next(
                (mirror for mirror in mirrored_record.mirrors if mirror.status == "available"),
                None,
            )
            if available_mirror is None:
                raise
            self.store.append_event(
                job_id,
                "primary_upload_failed",
                provider="gdrive",
                warning="Google Drive upload failed; the DC Cloud artifact remains available.",
                errorType=type(exc).__name__,
            )
            return ArtifactRecord(
                name=mirrored_record.name,
                uri=available_mirror.uri,
                sha256=mirrored_record.sha256,
                size_bytes=mirrored_record.size_bytes,
                # The mirror record only carries a folder share URL.  Treating
                # it as the artifact URL made Drive-failure notifications point
                # users at the wrong resource.  The DC Cloud file URL is
                # resolved just-in-time by the Mini App/control plane.
                public_url=None,
                mirrors=mirrored_record.mirrors,
            )
        # The terminal callback must be emitted as soon as the primary Drive
        # upload completes.  A failed mirror is persisted in the manifest and
        # repaired asynchronously by the control-plane outbox; retrying here
        # would keep the build (and its Telegram notification) blocked on a
        # second multi-gigabyte upload.
        return ArtifactRecord(
            name=primary_record.name,
            uri=primary_record.uri,
            sha256=primary_record.sha256,
            size_bytes=primary_record.size_bytes,
            public_url=primary_record.public_url,
            mirrors=mirrored_record.mirrors,
        )

    def _mirror_artifact(
        self,
        job_id: str,
        record: ArtifactRecord,
        artifact: Path,
        device: str,
        build: str,
        relative_root: str | None,
        prepared: PreparedArtifact | None = None,
    ) -> ArtifactRecord:
        # The secondary store is intentionally limited to distributable ROM
        # ZIPs; sources, checkpoints and arbitrary publish-task files stay on
        # the existing Drive path only.
        if artifact.suffix.casefold() != ".zip" or not self.mirror_publisher.config.enabled:
            return record

        def report_mirror(values: Mapping[str, object]) -> None:
            self.store.append_event(
                job_id,
                "upload_progress",
                provider="dccloud",
                stage="mirror_upload",
                fileName=artifact.name,
                **dict(values),
            )

        mirror = self.mirror_publisher.publish(
            artifact,
            job_id=job_id,
            device=device,
            build=build,
            relative_root=relative_root,
            progress_callback=report_mirror,
            **({"prepared": prepared} if isinstance(self.mirror_publisher, ArtifactMirrorPublisher) else {}),
        )
        if mirror.status == "failed":
            self.store.append_event(
                job_id,
                "mirror_upload_failed",
                provider="dccloud",
                warning="DC Cloud mirror upload failed; primary artifact upload will continue.",
                errorCode=mirror.error_code or "upload_failed",
            )
        elif mirror.status == "available":
            self.store.append_event(
                job_id,
                "mirror_available",
                provider="dccloud",
                fileName=artifact.name,
                browseUrl=mirror.browse_url,
            )
        return attach_mirror(record, mirror)

    def _push_cancelled_terminal(self, job_id: str, recipe: BuildRecipe) -> None:
        if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true":
            return
        try:
            CloudJobSync(self.store, self.storage_factory(recipe.storage.remote)).push(job_id)
        except Exception as exc:
            self.store.append_event(job_id, "warning", warning=f"Cancelled cloud sync failed: {exc}")

    def _ensure_content_packs(self, recipe: BuildRecipe) -> None:
        if not self.content_index.is_file():
            raise OrchestrationError(
                f"Content-pack index is unavailable: {self.content_index}. "
                "Run content_pack_tool.py index/upload or clone a tree that includes content-packs/index.json."
            )
        import json

        index = json.loads(self.content_index.read_text(encoding="utf-8"))
        validate_content_index(index)
        required = [
            f"MOD/{recipe.build.mod_version}",
            "STARK/common",
            "Flash_script/common",
            "copy-image/v1",
            "OFX/v1",
            "TWRP/v1",
        ]
        manager = ContentPackManager(
            self.content_root,
            rclone_config=self.rclone_config,
        )
        for pack_id in required:
            pack = next((item for item in index["packs"] if item["id"] == pack_id), None)
            if not pack:
                raise OrchestrationError(
                    f"Content-pack is unavailable: {pack_id}. "
                    f"Add it to content-packs/index.json and upload with content_pack_tool.py."
                )
            target = (self.content_root / str(pack["target"])).resolve()
            try:
                manager.verify(target, pack)
            except (FileNotFoundError, SourceIntegrityError):
                if not self.rclone_config:
                    raise OrchestrationError(
                        f"Content-pack {pack_id} is missing or invalid under {target} "
                        "and rclone is not configured (set WUKONG_RCLONE_CONFIG)."
                    )
                try:
                    manager.install(index, pack_id)
                except Exception as exc:
                    raise OrchestrationError(
                        f"Failed to install content-pack {pack_id}: {exc}"
                    ) from exc

    def _reconcile_recipe_mods(self, job_id: str, recipe: BuildRecipe) -> BuildRecipe:
        if recipe.task != "build":
            return recipe
        from tools.validate_recipe_content import apply_resolved_mods, resolve_recipe_mods

        try:
            resolved = resolve_recipe_mods(recipe, self.content_root)
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        dropped = [str(item) for item in (resolved.get("dropped") or [])]
        if dropped:
            self.store.append_event(
                job_id,
                "warning",
                warning=(
                    "Dropped unavailable MODs from recipe "
                    f"({recipe.build.mod_version}): {', '.join(dropped)}"
                ),
            )
        if resolved.get("rewritten") and not resolved.get("mods"):
            raise OrchestrationError(
                f"No ready MODs remain in content-pack MOD/{recipe.build.mod_version}. "
                "Install/upload a complete pack before building."
            )
        updated = apply_resolved_mods(recipe, resolved)
        if updated.digest != recipe.digest:
            self.store.replace_recipe(job_id, updated)
            # Keep manifest recipe_digest aligned with the executed MOD set.
            try:
                self.store.update(job_id, recipe_digest=updated.digest)
            except OrchestrationError:
                pass
            recipe = updated
            self.store.append_event(
                job_id,
                "state",
                status="running",
                stage="mod_reconcile",
                mods=list(updated.build.mods),
            )
        return recipe

    def _try_restore_checkpoint(
        self,
        job_id: str,
        checkpoint: str,
        build_workspace: Path,
        storage: RcloneStorageAdapter,
    ) -> bool:
        import shutil

        try:
            if checkpoint.startswith("local:"):
                checkpoint_path = Path(checkpoint[6:]).resolve()
                if checkpoint_path != build_workspace:
                    raise OrchestrationError(
                        f"Resume checkpoint path {checkpoint_path} does not match workspace {build_workspace}"
                    )
                if not (build_workspace / ".wkstudio-workspace.json").is_file():
                    raise OrchestrationError("Local resume checkpoint is missing its workspace marker")
                return True
            if build_workspace.exists():
                shutil.rmtree(build_workspace)
            storage.restore_tree(checkpoint, build_workspace)
            if not (build_workspace / ".wkstudio-workspace.json").is_file():
                raise OrchestrationError("Resume checkpoint is missing its workspace marker")
            return True
        except Exception as exc:
            if build_workspace.exists():
                shutil.rmtree(build_workspace, ignore_errors=True)
            self.store.update(job_id, checkpoint=None, checkpoint_at=None)
            self.store.append_event(
                job_id,
                "warning",
                warning=(
                    f"Checkpoint restore failed; continuing with a clean workspace: {exc}"
                ),
            )
            return False

    def _push_cloud_manifest(self, job_id: str, storage: RcloneStorageAdapter) -> bool:
        return self._push_cloud_state(job_id, storage, manifest_only=True)

    def _push_cloud_progress(self, job_id: str, storage: RcloneStorageAdapter) -> bool:
        return self._push_cloud_state(job_id, storage, manifest_only=False)

    def _push_cloud_state(
        self,
        job_id: str,
        storage: RcloneStorageAdapter,
        *,
        manifest_only: bool,
    ) -> bool:
        if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true":
            return True
        try:
            sync = CloudJobSync(self.store, storage)
            if manifest_only:
                sync.push_manifest(job_id)
            else:
                sync.push(job_id)
            if job_id in self._cloud_push_warning_at:
                self._cloud_push_warning_at.pop(job_id, None)
                self.store.append_event(job_id, "cloud_sync_recovered", stage="cloud_sync")
            return True
        except Exception as exc:
            now = time.monotonic()
            last_warning = self._cloud_push_warning_at.get(job_id)
            if last_warning is None or now - last_warning >= CLOUD_PUSH_WARNING_INTERVAL_SECONDS:
                self._cloud_push_warning_at[job_id] = now
                self.store.append_event(
                    job_id,
                    "warning",
                    warning=f"Cloud progress sync failed: {exc}",
                )
            return False

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
        self.actions_ui.close_group()
        self.actions_ui.begin("complete")
        self.actions_ui.close_group()
        recipe = self.store.recipe(job_id)
        if recipe and os.environ.get("GITHUB_ACTIONS", "").casefold() == "true":
            try:
                CloudJobSync(self.store, self.storage_factory(recipe.storage.remote)).push(job_id)
            except Exception as exc:
                self.store.append_event(job_id, "warning", warning=f"Terminal cloud sync failed: {exc}")
        if recipe:
            self.actions_ui.write_summary(manifest, recipe)
        return manifest

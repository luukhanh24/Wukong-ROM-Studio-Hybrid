from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol

from .models import BuildRecipe, Identity, JobManifest, JobStatus, utc_now
from .routing import RunnerDecision, RunnerInventory, RunnerRouter


TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class OrchestrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobEvent:
    sequence: int
    job_id: str
    timestamp: str
    type: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "jobId": self.job_id,
            "timestamp": self.timestamp,
            "type": self.type,
            **self.payload,
        }


class JobStore(Protocol):
    def create(self, manifest: JobManifest, recipe: BuildRecipe) -> JobManifest: ...
    def get(self, job_id: str) -> JobManifest | None: ...
    def recipe(self, job_id: str) -> BuildRecipe | None: ...
    def update(self, job_id: str, **changes: object) -> JobManifest: ...
    def replace_recipe(self, job_id: str, recipe: BuildRecipe) -> BuildRecipe: ...
    def append_event(self, job_id: str, event_type: str, **payload: object) -> JobEvent: ...
    def events(self, job_id: str, after: int = 0) -> list[JobEvent]: ...
    def list(self) -> list[JobManifest]: ...


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobManifest] = {}
        self._recipes: dict[str, BuildRecipe] = {}
        self._events: dict[str, list[JobEvent]] = {}
        self._lock = threading.RLock()

    def create(self, manifest: JobManifest, recipe: BuildRecipe) -> JobManifest:
        with self._lock:
            if manifest.job_id in self._jobs:
                raise OrchestrationError(f"Job already exists: {manifest.job_id}")
            self._jobs[manifest.job_id] = copy.deepcopy(manifest)
            self._recipes[manifest.job_id] = recipe
            self._events[manifest.job_id] = []
            return copy.deepcopy(manifest)

    def get(self, job_id: str) -> JobManifest | None:
        with self._lock:
            manifest = self._jobs.get(job_id)
            return copy.deepcopy(manifest) if manifest else None

    def recipe(self, job_id: str) -> BuildRecipe | None:
        with self._lock:
            return self._recipes.get(job_id)

    def update(self, job_id: str, **changes: object) -> JobManifest:
        with self._lock:
            manifest = self._jobs.get(job_id)
            if not manifest:
                raise OrchestrationError("Job not found")
            for key, value in changes.items():
                if not hasattr(manifest, key):
                    raise OrchestrationError(f"Unknown job field: {key}")
                setattr(manifest, key, value)
            manifest.updated_at = utc_now()
            if manifest.status in TERMINAL_STATUSES and not manifest.finished_at:
                manifest.finished_at = manifest.updated_at
            return copy.deepcopy(manifest)

    def replace_recipe(self, job_id: str, recipe: BuildRecipe) -> BuildRecipe:
        with self._lock:
            if job_id not in self._jobs:
                raise OrchestrationError("Job not found")
            self._recipes[job_id] = recipe
            return recipe

    def append_event(self, job_id: str, event_type: str, **payload: object) -> JobEvent:
        with self._lock:
            if job_id not in self._jobs:
                raise OrchestrationError("Job not found")
            entries = self._events.setdefault(job_id, [])
            event = JobEvent(len(entries) + 1, job_id, utc_now(), event_type, payload)
            entries.append(event)
            return event

    def events(self, job_id: str, after: int = 0) -> list[JobEvent]:
        with self._lock:
            if job_id not in self._jobs:
                raise OrchestrationError("Job not found")
            return [copy.deepcopy(event) for event in self._events[job_id] if event.sequence > after]

    def list(self) -> list[JobManifest]:
        with self._lock:
            return sorted(
                (copy.deepcopy(manifest) for manifest in self._jobs.values()),
                key=lambda manifest: manifest.created_at,
                reverse=True,
            )


class FileJobStore(InMemoryJobStore):
    def __init__(self, root: Path, *, on_change: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.root = root.resolve()
        self.on_change = on_change
        self.root.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        for directory in self.root.iterdir():
            manifest_path = directory / "manifest.json"
            recipe_path = directory / "recipe.json"
            if not directory.is_dir() or not manifest_path.is_file() or not recipe_path.is_file():
                continue
            try:
                manifest = JobManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
                recipe = BuildRecipe.from_dict(json.loads(recipe_path.read_text(encoding="utf-8")))
                events_path = directory / "events.jsonl"
                events: list[JobEvent] = []
                if events_path.is_file():
                    for line in events_path.read_text(encoding="utf-8").splitlines():
                        item = json.loads(line)
                        known = {"sequence", "jobId", "timestamp", "type"}
                        events.append(
                            JobEvent(
                                sequence=int(item["sequence"]),
                                job_id=str(item["jobId"]),
                                timestamp=str(item["timestamp"]),
                                type=str(item["type"]),
                                payload={key: value for key, value in item.items() if key not in known},
                            )
                        )
                self._jobs[manifest.job_id] = manifest
                self._recipes[manifest.job_id] = recipe
                self._events[manifest.job_id] = events
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue

    def _persist(self, job_id: str) -> None:
        directory = self.root / job_id
        directory.mkdir(parents=True, exist_ok=True)
        manifest = self._jobs[job_id]
        recipe = self._recipes[job_id]
        events = self._events[job_id]
        self._write_text_atomic(directory / "manifest.json",
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        self._write_text_atomic(directory / "recipe.json", recipe.canonical_json + "\n")
        self._write_text_atomic(directory / "events.jsonl",
            "".join(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for event in events),
        )
        if self.on_change:
            self.on_change()

    @staticmethod
    def _write_text_atomic(path: Path, content: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def create(self, manifest: JobManifest, recipe: BuildRecipe) -> JobManifest:
        with self._lock:
            result = super().create(manifest, recipe)
            self._persist(manifest.job_id)
            return result

    def update(self, job_id: str, **changes: object) -> JobManifest:
        with self._lock:
            result = super().update(job_id, **changes)
            self._persist(job_id)
            return result

    def replace_recipe(self, job_id: str, recipe: BuildRecipe) -> BuildRecipe:
        with self._lock:
            result = super().replace_recipe(job_id, recipe)
            self._persist(job_id)
            return result

    def append_event(self, job_id: str, event_type: str, **payload: object) -> JobEvent:
        with self._lock:
            result = super().append_event(job_id, event_type, **payload)
            self._persist(job_id)
            return result


InventoryProvider = Callable[[], RunnerInventory]
AccessValidator = Callable[[BuildRecipe, Identity], None]


class HybridOrchestrator:
    def __init__(
        self,
        *,
        store: JobStore,
        workspace_root: Path,
        router: RunnerRouter | None = None,
        inventory_provider: InventoryProvider | None = None,
        access_validator: AccessValidator | None = None,
        submission_reserver: Callable[[Identity, str], Mapping[str, object]] | None = None,
        submission_compensator: Callable[[Identity, str, str, bool], object] | None = None,
    ) -> None:
        self.store = store
        self.workspace_root = workspace_root.resolve()
        self.router = router or RunnerRouter()
        self.inventory_provider = inventory_provider or (lambda: RunnerInventory(False))
        self.access_validator = access_validator
        self.submission_reserver = submission_reserver
        self.submission_compensator = submission_compensator

    def validate(self, recipe: BuildRecipe) -> RunnerDecision:
        return self.router.choose(
            target=recipe.execution.target,
            estimated_workspace_bytes=recipe.estimated_workspace_bytes,
            inventory=self.inventory_provider(),
        )

    def submit(
        self,
        recipe: BuildRecipe,
        identity: Identity,
        *,
        job_id: str | None = None,
        reservation_already_made: bool = False,
    ) -> JobManifest:
        job_id = job_id or uuid.uuid4().hex
        manifest = self.prepare_submission(recipe, identity, job_id=job_id)
        decision_runner = manifest.runner or ""
        job_id = manifest.job_id
        reserved = False
        if self.submission_reserver and not reservation_already_made:
            reservation = self.submission_reserver(identity, job_id)
            existing_job_id = str(reservation.get("jobId") or job_id)
            if reservation.get("existing"):
                existing = self.store.get(existing_job_id)
                if existing is not None:
                    return existing
                raise OrchestrationError("Reserved job is not available")
            reserved = True
        try:
            self.store.create(manifest, recipe)
            self.store.append_event(job_id, "submitted", runner=decision_runner, channel=identity.channel)
        except Exception as exc:
            if reserved and self.submission_compensator:
                self.submission_compensator(identity, job_id, str(exc), False)
            raise
        return self.store.get(job_id) or manifest

    def prepare_submission(
        self,
        recipe: BuildRecipe,
        identity: Identity,
        *,
        job_id: str,
    ) -> JobManifest:
        self.validate_access(recipe, identity)
        decision = self.validate(recipe)
        if not job_id.isascii() or not job_id.replace("-", "").isalnum() or len(job_id) > 64:
            raise OrchestrationError("Job ID is invalid")
        return JobManifest(
            job_id=job_id,
            owner=identity,
            recipe_digest=recipe.digest,
            runner=decision.runner,
            rom_metadata=dict(recipe.source.metadata),
        )

    def compensate_submission(
        self,
        identity: Identity,
        job_id: str,
        reason: str,
        *,
        retain_job: bool,
    ) -> object:
        if not self.submission_compensator:
            return False
        return self.submission_compensator(identity, job_id, reason, retain_job)

    def validate_access(self, recipe: BuildRecipe, identity: Identity) -> None:
        if self.access_validator:
            self.access_validator(recipe, identity)

    def inspect(self, job_id: str, identity: Identity) -> JobManifest:
        return self._owned(job_id, identity)

    def list(self, identity: Identity) -> list[JobManifest]:
        return [manifest for manifest in self.store.list() if self._can_access(manifest, identity)]

    def events(self, job_id: str, identity: Identity, *, after: int = 0) -> list[JobEvent]:
        self._owned(job_id, identity)
        return self.store.events(job_id, after)

    def cancel(self, job_id: str, identity: Identity) -> JobManifest:
        current = self._owned(job_id, identity)
        if current.status in TERMINAL_STATUSES:
            return current
        updated = self.store.update(job_id, status=JobStatus.CANCELLED, error="Cancelled by user")
        self.store.append_event(job_id, "cancelled", actor=identity.subject)
        return updated

    def resume(self, job_id: str, identity: Identity) -> JobManifest:
        previous = self._owned(job_id, identity)
        if previous.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise OrchestrationError("Only failed or cancelled jobs can be resumed")
        if not previous.checkpoint:
            raise OrchestrationError("Job has no resumable checkpoint")
        if previous.checkpoint_at:
            checkpoint_time = datetime.fromisoformat(previous.checkpoint_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - checkpoint_time > timedelta(days=7):
                raise OrchestrationError("Job checkpoint has expired after 7 days")
        recipe = self.store.recipe(job_id)
        if not recipe:
            raise OrchestrationError("Job recipe is unavailable")
        resumed = self.submit(recipe, previous.owner)
        resumed = self.store.update(
            resumed.job_id,
            checkpoint=previous.checkpoint,
            checkpoint_at=previous.checkpoint_at,
        )
        self.store.append_event(resumed.job_id, "resumed", previousJobId=job_id)
        return resumed

    @staticmethod
    def _can_access(manifest: JobManifest, identity: Identity) -> bool:
        return identity.role == "admin" or (
            manifest.owner.channel == identity.channel and manifest.owner.subject == identity.subject
        )

    def _owned(self, job_id: str, identity: Identity) -> JobManifest:
        manifest = self.store.get(job_id)
        if not manifest or not self._can_access(manifest, identity):
            raise OrchestrationError("Job not found")
        return manifest

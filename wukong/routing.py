from __future__ import annotations

from dataclasses import dataclass


GIB = 1024**3
HOSTED_WORKSPACE_LIMIT = 10 * GIB
SELF_HOSTED_MIN_DISK = 150 * GIB
SELF_HOSTED_MIN_MEMORY = 16 * GIB
SELF_HOSTED_MIN_CPUS = 8
SELF_HOSTED_LABELS = ("self-hosted", "linux", "x64", "wukong-rom")


class RunnerUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunnerInventory:
    self_hosted_online: bool
    free_disk_bytes: int = 0
    memory_bytes: int = 0
    logical_cpus: int = 0


@dataclass(frozen=True)
class RunnerDecision:
    kind: str
    runner: str
    labels: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "runner": self.runner,
            "labels": list(self.labels),
            "reason": self.reason,
        }


class RunnerRouter:
    def choose(
        self,
        *,
        target: str,
        estimated_workspace_bytes: int,
        inventory: RunnerInventory,
    ) -> RunnerDecision:
        if target == "local-windows":
            return RunnerDecision("local", "windows", ("windows",), "Local Windows selected")
        if target == "github-hosted":
            # Direct workflow entry still uses auto routing so a recipe cannot
            # force hosted execution beyond the safety limit.
            if estimated_workspace_bytes > HOSTED_WORKSPACE_LIMIT:
                return self._self_hosted(inventory)
            return self._hosted()
        if target == "self-hosted-linux":
            return self._self_hosted(inventory)
        if target != "github-auto":
            raise ValueError(f"Unsupported execution target: {target}")
        if estimated_workspace_bytes <= HOSTED_WORKSPACE_LIMIT:
            return self._hosted()
        return self._self_hosted(inventory)

    @staticmethod
    def _hosted() -> RunnerDecision:
        return RunnerDecision(
            "github-hosted",
            "ubuntu-24.04",
            ("ubuntu-24.04",),
            "Estimated workspace fits the hosted runner safety limit",
        )

    @staticmethod
    def _self_hosted(inventory: RunnerInventory) -> RunnerDecision:
        if not inventory.self_hosted_online:
            raise RunnerUnavailableError("Required Wukong self-hosted Linux runner is offline")
        missing: list[str] = []
        if inventory.free_disk_bytes < SELF_HOSTED_MIN_DISK:
            missing.append("150 GiB free disk")
        if inventory.memory_bytes < SELF_HOSTED_MIN_MEMORY:
            missing.append("16 GiB memory")
        if inventory.logical_cpus < SELF_HOSTED_MIN_CPUS:
            missing.append("8 logical CPUs")
        if missing:
            raise RunnerUnavailableError("Self-hosted runner does not meet: " + ", ".join(missing))
        return RunnerDecision(
            "self-hosted",
            "wukong-rom",
            SELF_HOSTED_LABELS,
            "Large workspace requires the qualified self-hosted Linux runner",
        )

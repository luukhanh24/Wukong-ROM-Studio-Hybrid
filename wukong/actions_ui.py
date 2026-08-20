from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .models import BuildRecipe, JobManifest


STAGE_TITLES: Mapping[str, str] = {
    "preflight": "01 · Kiểm tra recipe / Recipe preflight",
    "route": "02 · Chọn runner / Route runner",
    "workspace": "03 · Chuẩn bị dung lượng / Prepare workspace",
    "content": "04 · Tải content-pack / Fetch private content",
    "download": "05 · Resolve & tải ROM / Resolve source download",
    "inspect_rom": "06 · Kiểm tra ROM / Inspect source ROM",
    "extract_payload": "07 · Tách payload / Extract payload",
    "unpack_partitions": "08 · Giải nén partition / Unpack partitions",
    "debloat": "09 · Gỡ ứng dụng thừa / Remove bloatware",
    "apply_mod": "10 · Áp dụng MOD / Apply MODs",
    "sync_configs": "11 · Đồng bộ metadata / Sync fs_config & SELinux",
    "repack_partitions": "12 · Đóng gói partition / Repack partitions",
    "repack_super": "13 · Tạo super.img / Build super image",
    "patch_vbmeta": "14 · Vá vbmeta / Patch vbmeta",
    "patch_vendor_boot": "15 · Vá vendor_boot / Patch vendor_boot",
    "package_zip": "16 · Đóng gói ZIP / Package flashable ZIP",
    "notify_telegram": "17 · Báo Telegram / Send notification",
    "upload": "18 · Upload Drive / Publish artifact",
    "complete": "19 · Checksum & link / Publish result",
}


def _command_text(value: object) -> str:
    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


class GitHubActionsUI:
    """Emit GitHub-native stage groups and a durable run summary.

    This adapter is intentionally presentation-only. Job state remains owned by
    the orchestrator and the same executor is used outside GitHub Actions.
    """

    def __init__(self, *, enabled: bool | None = None, summary_path: Path | None = None) -> None:
        self.enabled = (
            os.environ.get("GITHUB_ACTIONS", "").casefold() == "true"
            if enabled is None
            else enabled
        )
        raw_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
        self.summary_path = summary_path or (Path(raw_summary) if raw_summary else None)
        self._active_stage: str | None = None

    def begin(self, stage: str) -> None:
        if not self.enabled or stage == self._active_stage:
            return
        self.close_group()
        title = STAGE_TITLES.get(stage, stage.replace("_", " ").title())
        print(f"::group::{title}", flush=True)
        print(f"::notice title={_command_text(title)}::Đang thực hiện / In progress", flush=True)
        self._active_stage = stage

    def event(self, event: Mapping[str, Any]) -> None:
        if not self.enabled or str(event.get("type") or "") != "step":
            return
        stage = str(event.get("step") or "build")
        status = str(event.get("status") or "")
        if status == "running":
            self.begin(stage)
            message = event.get("message")
            if message:
                print(f"[Wukong] {message}", flush=True)
            return
        title = STAGE_TITLES.get(stage, stage)
        if status == "success":
            details = event.get("details") if isinstance(event.get("details"), Mapping) else {}
            duration = details.get("durationSeconds")
            suffix = f" · {duration}s" if duration is not None else ""
            print(f"::notice title={_command_text(title)}::Hoàn thành / Completed{suffix}", flush=True)
            self.close_group()
        elif status == "failed":
            message = event.get("message") or "Stage failed"
            print(f"::error title={_command_text(title)}::{_command_text(message)}", flush=True)
            self.close_group()

    def close_group(self) -> None:
        if self.enabled and self._active_stage is not None:
            print("::endgroup::", flush=True)
        self._active_stage = None

    def write_summary(self, manifest: JobManifest, recipe: BuildRecipe) -> None:
        if not self.enabled or self.summary_path is None:
            return
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        mods = list(recipe.build.mods) if recipe.task == "build" else []
        lines = [
            "## Wukong ROM Studio · Kết quả build / Build result",
            "",
            "| Mục / Field | Giá trị / Value |",
            "|---|---|",
            f"| Job | `{manifest.job_id}` |",
            f"| Trạng thái / Status | **{manifest.status.value}** |",
            f"| Thiết bị / Device | `{recipe.device}` |",
            f"| Tác vụ / Task | `{recipe.task}` |",
            f"| Runner | `{manifest.runner or recipe.execution.target}` |",
            f"| Recipe SHA-256 | `{manifest.recipe_digest}` |",
        ]
        if recipe.task == "build":
            lines.extend(
                [
                    f"| Nền MOD / MOD pack | `{recipe.build.mod_version}` |",
                    f"| Preset | `{recipe.build.preset}` |",
                    f"| MOD đã chọn / Selected | {len(mods)} |",
                ]
            )
        lines.extend(["", "### Artifact", ""])
        if manifest.artifacts:
            lines.extend(
                [
                    "| File | Kích thước / Size | SHA-256 | Link |",
                    "|---|---:|---|---|",
                ]
            )
            for artifact in manifest.artifacts:
                link = artifact.public_url or artifact.uri
                safe_link = link if str(link).startswith(("https://", "http://")) else "private"
                linked = f"[Mở / Open]({safe_link})" if safe_link != "private" else "Private"
                lines.append(
                    f"| `{artifact.name}` | {artifact.size_bytes:,} B | `{artifact.sha256}` | {linked} |"
                )
        else:
            lines.append("Chưa có artifact / No artifact was produced.")
        if manifest.error:
            lines.extend(["", "### Lỗi / Error", "", f"> {manifest.error.replace(chr(10), ' ')}"])
        with self.summary_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")

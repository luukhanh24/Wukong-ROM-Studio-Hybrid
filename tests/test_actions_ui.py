from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wukong.actions_ui import GitHubActionsUI, STAGE_TITLES
from wukong.models import ArtifactRecord, BuildRecipe, Identity, JobManifest, JobStatus


ROOT = Path(__file__).resolve().parents[1]


class GitHubActionsUITests(unittest.TestCase):
    def test_pipeline_events_emit_bilingual_groups_and_completion_notice(self) -> None:
        reporter = GitHubActionsUI(enabled=True)
        output = io.StringIO()

        with redirect_stdout(output):
            reporter.event({"type": "step", "step": "extract_payload", "status": "running"})
            reporter.event(
                {
                    "type": "step",
                    "step": "extract_payload",
                    "status": "success",
                    "details": {"durationSeconds": 12.5},
                }
            )

        rendered = output.getvalue()
        self.assertIn(f"::group::{STAGE_TITLES['extract_payload']}", rendered)
        self.assertIn("Hoàn thành / Completed · 12.5s", rendered)
        self.assertIn("::endgroup::", rendered)

    def test_terminal_summary_contains_recipe_and_artifact_integrity(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "schemaVersion": 1,
                "task": "source_mirror",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.test/rom.zip"},
                "execution": {"target": "github-auto"},
            }
        )
        manifest = JobManifest(
            job_id="job-1",
            owner=Identity("actions", "1", "user"),
            recipe_digest=recipe.digest,
            status=JobStatus.SUCCEEDED,
            runner="github-hosted",
            artifacts=[ArtifactRecord("rom.zip", "drive:path", "a" * 64, 123)],
        )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "summary.md")
            GitHubActionsUI(enabled=True, summary_path=path).write_summary(manifest, recipe)
            summary = path.read_text(encoding="utf-8")

        self.assertIn("Wukong ROM Studio", summary)
        self.assertIn("PKG110", summary)
        self.assertIn("github-hosted", summary)
        self.assertIn("a" * 64, summary)
        self.assertIn("123 B", summary)

    def test_workflow_exposes_numbered_jobs_and_step_summary(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "wukong-build.yml").read_text(
            encoding="utf-8"
        )
        action = (ROOT / ".github" / "actions" / "run-hybrid" / "action.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("01–02 · Kiểm tra recipe & chọn runner", workflow)
        self.assertIn("03–19 · Build trên GitHub Hosted", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("E · Pipeline 05–19", action)

    def test_plain_progress_messages_are_not_command_escaped(self) -> None:
        reporter = GitHubActionsUI(enabled=True)
        output = io.StringIO()

        with redirect_stdout(output):
            reporter.event(
                {
                    "type": "step",
                    "step": "package_zip",
                    "status": "running",
                    "message": "ZIP 42%",
                }
            )
            reporter.close_group()

        self.assertIn("ZIP 42%", output.getvalue())
        self.assertNotIn("ZIP 42%25", output.getvalue())


if __name__ == "__main__":
    unittest.main()

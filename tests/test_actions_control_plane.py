from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import mock

from tools import actions_control_plane


class ActionsControlPlaneTests(unittest.TestCase):
    def test_bootstrap_signs_request_and_preserves_github_bearer(self) -> None:
        with (
            TemporaryDirectory() as directory,
            mock.patch.object(
                actions_control_plane,
                "_request_json",
                return_value={"recipe": {"schemaVersion": 1}},
            ) as request_json,
        ):
            root = Path(directory)
            actions_control_plane.bootstrap(
                "https://worker.example",
                job_id="bootstrap-job",
                run_id=42,
                github_token="g" * 40,
                secret="s" * 32,
                output=root / "bootstrap.json",
                recipe_output=root / "recipe.json",
            )

            headers = request_json.call_args.kwargs["headers"]
            self.assertEqual(headers["Authorization"], f"Bearer {'g' * 40}")
            self.assertIn("X-Wukong-Timestamp", headers)
            self.assertIn("X-Wukong-Signature", headers)

    def test_upload_progress_is_batched_for_at_least_five_seconds(self) -> None:
        manifests = [
            {"status": "running", "stage": "uploading", "progress": progress}
            for progress in (0.0, 0.1, 0.2, 0.3)
        ] + [{"status": "succeeded", "stage": "complete", "progress": 1.0}]
        events = [
            [],
            [{"sequence": 1, "type": "upload_progress", "progress": 0.1}],
            [
                {"sequence": 1, "type": "upload_progress", "progress": 0.1},
                {"sequence": 2, "type": "upload_progress", "progress": 0.2},
            ],
            [
                {"sequence": 1, "type": "upload_progress", "progress": 0.1},
                {"sequence": 2, "type": "upload_progress", "progress": 0.2},
                {"sequence": 3, "type": "upload_progress", "progress": 0.3},
            ],
            [
                {"sequence": 1, "type": "upload_progress", "progress": 0.1},
                {"sequence": 2, "type": "upload_progress", "progress": 0.2},
                {"sequence": 3, "type": "upload_progress", "progress": 0.3},
            ],
        ]
        monotonic = [0.0, 0.0, 0.0, 2.0, 2.0, 4.0, 4.0, 6.0, 6.0, 8.0]

        with (
            mock.patch.object(actions_control_plane, "_read_json", side_effect=manifests),
            mock.patch.object(actions_control_plane, "_read_events", side_effect=events),
            mock.patch.object(actions_control_plane, "_post_signed") as post,
            mock.patch.object(actions_control_plane.time, "monotonic", side_effect=monotonic),
            mock.patch.object(actions_control_plane.time, "sleep"),
        ):
            actions_control_plane.monitor_progress(
                "https://worker.example",
                job_id="job-upload",
                run_id=42,
                secret="s" * 32,
                jobs_root=Path("jobs"),
            )

        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].args[2]
        second_payload = post.call_args_list[1].args[2]
        self.assertEqual(first_payload["events"], [])
        self.assertEqual(
            [event["sequence"] for event in second_payload["events"]],
            [3, 4, 5],
        )
        self.assertEqual(second_payload["progress"], 0.3)


if __name__ == "__main__":
    unittest.main()

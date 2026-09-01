from __future__ import annotations

import unittest
import urllib.error
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import mock

from tools import actions_control_plane


class ActionsControlPlaneTests(unittest.TestCase):
    def test_requests_use_an_explicit_cloudflare_compatible_user_agent(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        response.__enter__.return_value.status = 200
        with mock.patch.object(
            actions_control_plane.urllib.request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            result = actions_control_plane._request_json(
                "https://worker.example/internal/actions/bootstrap",
                {"jobId": "user-agent-probe", "runId": 42},
                headers={},
                attempts=1,
            )

        request = urlopen.call_args.args[0]
        self.assertEqual("wukong-actions-control-plane/1.0", request.get_header("User-agent"))
        self.assertEqual({"ok": True}, result)

    def test_http_error_includes_bounded_control_plane_json(self) -> None:
        error = urllib.error.HTTPError(
            "https://worker.example/internal/actions/bootstrap",
            403,
            "Forbidden",
            {},
            BytesIO(b'{"error":"GitHub run verification failed (403)"}'),
        )
        with (
            mock.patch.object(
                actions_control_plane.urllib.request,
                "urlopen",
                side_effect=error,
            ),
            self.assertRaisesRegex(
                RuntimeError,
                r"HTTP 403: .*GitHub run verification failed",
            ),
        ):
            actions_control_plane._request_json(
                "https://worker.example/internal/actions/bootstrap",
                {"jobId": "diagnostic", "runId": 42},
                headers={},
                attempts=1,
            )

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

    def test_mirror_repair_callback_posts_repaired_manifest(self) -> None:
        manifest = {
            "job_id": "repair-job",
            "artifacts": [{
                "name": "rom.zip",
                "mirrors": [{"provider": "dccloud", "status": "available"}],
            }],
        }
        with (
            TemporaryDirectory() as directory,
            mock.patch.object(actions_control_plane, "_read_json", return_value=manifest),
            mock.patch.object(actions_control_plane, "_post_signed", return_value={"ok": True}) as post,
        ):
            result = actions_control_plane.mirror_repair_callback(
                "https://worker.example",
                job_id="repair-job",
                run_id=77,
                secret="s" * 32,
                manifest_path=Path(directory) / "manifest.json",
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(post.call_args.args[0], "https://worker.example")
        self.assertEqual(post.call_args.args[1], "/internal/actions/mirror-repair")
        self.assertEqual(post.call_args.args[2]["jobId"], "repair-job")
        self.assertEqual(post.call_args.args[2]["runId"], 77)
        self.assertEqual(post.call_args.args[2]["manifest"], manifest)


if __name__ == "__main__":
    unittest.main()

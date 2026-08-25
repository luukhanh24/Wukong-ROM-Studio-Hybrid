from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock

from wukong.actions_progress import ActionsProgressReporter
from wukong.models import Identity, JobManifest, JobStatus


class ActionsProgressReporterTests(unittest.TestCase):
    def test_reporter_signs_monotonic_progress_and_throttles_same_stage(self) -> None:
        post = Mock()
        post.return_value.raise_for_status.return_value = None
        moments = iter((100.0, 101.0, 116.0))
        reporter = ActionsProgressReporter(
            endpoint="https://wukong-api.run.app/internal/actions/progress",
            secret="callback-secret-" + "x" * 24,
            run_id=555,
            minimum_interval=15,
            post=post,
            monotonic=lambda: next(moments),
            wall_time=lambda: 1_777_000_000,
        )
        manifest = JobManifest(
            job_id="job-progress",
            owner=Identity("actions", "1", "user"),
            recipe_digest="a" * 64,
            status=JobStatus.RUNNING,
            stage="extract",
            progress=0.25,
        )

        self.assertTrue(reporter.publish(manifest))
        self.assertFalse(reporter.publish(manifest))
        manifest.progress = 0.5
        self.assertTrue(reporter.publish(manifest))

        self.assertEqual(2, post.call_count)
        first = post.call_args_list[0]
        first_body = first.kwargs["data"]
        first_payload = json.loads(first_body)
        self.assertEqual(1, first_payload["sequence"])
        self.assertEqual(0.25, first_payload["progress"])
        timestamp = first.kwargs["headers"]["X-Wukong-Timestamp"]
        key = hmac.new(
            b"WukongActionsCallback\0",
            reporter.secret.encode(),
            hashlib.sha256,
        ).digest()
        expected = hmac.new(
            key,
            timestamp.encode("ascii") + b"." + first_body,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(expected, first.kwargs["headers"]["X-Wukong-Signature"])


if __name__ == "__main__":
    unittest.main()

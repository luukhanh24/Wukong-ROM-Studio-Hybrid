from __future__ import annotations

import json
import unittest

from wukong.cloud_tasks import CloudTaskDispatcher, CloudTasksOIDCVerifier


class _FakeCloudTasksClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    @staticmethod
    def queue_path(project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def create_task(self, *, request: dict[str, object]) -> object:
        self.requests.append(request)
        return object()


class CloudTasksTests(unittest.TestCase):
    def test_dispatcher_uses_stable_task_names_oidc_and_private_endpoints(self) -> None:
        client = _FakeCloudTasksClient()
        dispatcher = CloudTaskDispatcher(
            project="wukong-project",
            location="asia-southeast1",
            base_url="https://wukong-api.run.app",
            service_account_email="wukong-tasks@wukong-project.iam.gserviceaccount.com",
            audience="https://wukong-api.run.app",
            client=client,
        )

        dispatcher.enqueue_telegram_update(123, {"update_id": 123, "message": {}})
        dispatcher.enqueue_job_dispatch("job-abc")

        telegram_request, dispatch_request = client.requests
        telegram_task = telegram_request["task"]
        dispatch_task = dispatch_request["task"]
        self.assertTrue(str(telegram_task["name"]).endswith("/tasks/telegram-123"))
        self.assertTrue(str(dispatch_task["name"]).endswith("/tasks/job-job-abc"))
        self.assertEqual(
            "https://wukong-api.run.app/internal/tasks/telegram-update",
            telegram_task["http_request"]["url"],
        )
        self.assertEqual(
            "wukong-tasks@wukong-project.iam.gserviceaccount.com",
            telegram_task["http_request"]["oidc_token"]["service_account_email"],
        )
        self.assertEqual(
            {"updateId": 123, "update": {"update_id": 123, "message": {}}},
            json.loads(telegram_task["http_request"]["body"]),
        )

    def test_oidc_verifier_restricts_audience_and_service_account(self) -> None:
        verifier_calls: list[tuple[str, str]] = []

        def verify(token: str, audience: str) -> dict[str, object]:
            verifier_calls.append((token, audience))
            return {
                "aud": audience,
                "email": "wukong-tasks@wukong-project.iam.gserviceaccount.com",
                "email_verified": True,
            }

        verifier = CloudTasksOIDCVerifier(
            audience="https://wukong-api.run.app",
            service_account_email="wukong-tasks@wukong-project.iam.gserviceaccount.com",
            verify=verify,
        )

        self.assertTrue(verifier("Bearer signed-token"))
        self.assertFalse(verifier("Basic signed-token"))
        self.assertEqual(
            [("signed-token", "https://wukong-api.run.app")],
            verifier_calls,
        )


if __name__ == "__main__":
    unittest.main()

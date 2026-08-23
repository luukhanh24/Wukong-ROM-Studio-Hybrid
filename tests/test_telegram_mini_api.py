from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from wukong.models import ArtifactRecord, BuildRecipe, Identity, JobStatus
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore
from wukong.routing import RunnerInventory
from wukong.telegram import TelegramAccessStore
from wukong.telegram_mini_api import (
    TelegramInitDataError,
    TelegramJobNotifier,
    TelegramMiniAppAPI,
    validate_telegram_init_data,
)

TOKEN = "123456789:test-token"
CALLBACK_SECRET = "github-token-" + "x" * 32
ORIGIN = "https://luukhanh24.github.io"


def signed_init_data(user_id: int, *, auth_date: int | None = None, token: str = TOKEN) -> str:
    values = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "fixture-query",
        "user": json.dumps({"id": user_id, "first_name": "Fixture"}, separators=(",", ":")),
    }
    data_check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


class TelegramMiniAppAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.access = TelegramAccessStore(self.root / "access.json", admin_ids={1})
        self.access.approve(42, actor=self.access.identity(1))
        self.access.approve(43, actor=self.access.identity(1))
        self.store = InMemoryJobStore()
        self.orchestrator = HybridOrchestrator(
            store=self.store,
            workspace_root=self.root / "jobs",
            inventory_provider=lambda: RunnerInventory(False),
            access_validator=lambda _recipe, _identity: None,
        )
        self.runtime = Mock(spec=[
            "start",
            "refresh",
            "reconcile_actions_callback",
            "verify_actions_bearer",
            "cancel_external",
            "resume",
            "notify_terminal",
        ])
        self.runtime.refresh.side_effect = lambda manifest: manifest
        self.probe = Mock(return_value={
            "provider": "daniel-springer",
            "filename": "PKG110.zip",
            "resolvedHost": "downloads.example",
            "sizeBytes": 8718572190,
            "productName": "PKG110",
            "device": "OP5D2BL1",
            "version": "PKG110_16.0.10.500(CN01)",
            "androidVersion": "16",
            "securityPatch": "2026-08-01",
            "buildDate": "2026-08-11 09:38:18",
            "otaType": "AB",
            "contentType": "application/zip",
            "lastModified": "Tue, 11 Aug 2026 09:38:18 GMT",
            "md5": "a28632dc4e3e2c8b51cc6e938c87b6fb",
            "deepInspected": True,
            "warning": None,
        })
        self.api = TelegramMiniAppAPI(
            bot_token=TOKEN,
            allowed_origin=f"{ORIGIN}/Wukong-ROM-Studio-Hybrid/",
            access=self.access,
            orchestrator=self.orchestrator,
            runtime=self.runtime,
            catalog_provider=lambda: {"devices": []},
            diagnostics_provider=lambda: {"ready": True},
            source_probe_provider=self.probe,
            cache_provider=lambda: {"entryCount": 3, "totalBytes": 1024},
            cache_clearer=lambda: {"entryCount": 0, "totalBytes": 0},
            actions_callback_secret=CALLBACK_SECRET,
        )
        self.client = self.api.app.test_client()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def headers(self, user_id: int = 42, origin: str = ORIGIN) -> dict[str, str]:
        return {"Origin": origin, "Authorization": f"tma {signed_init_data(user_id)}"}

    def recipe(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "task": "build",
            "device": "PKG110",
            "source": {
                "kind": "https",
                "uri": "https://downloads.example/rom.zip",
                "metadata": {"productName": "FAKE"},
            },
            "execution": {"target": "github-auto"},
            "build": {
                "preset": "plus",
                "modVersion": "ColorOS_16.0.10",
                "mods": [],
                "notifyTelegram": True,
            },
        }

    def test_validates_signature_and_expiry(self) -> None:
        result = validate_telegram_init_data(signed_init_data(42), TOKEN)
        self.assertEqual(42, result["user"]["id"])
        with self.assertRaises(TelegramInitDataError):
            validate_telegram_init_data(signed_init_data(42, token="wrong"), TOKEN)
        with self.assertRaisesRegex(TelegramInitDataError, "expired"):
            validate_telegram_init_data(
                signed_init_data(42, auth_date=int(time.time()) - 7200), TOKEN
            )

    def test_strict_cors_and_allowlist(self) -> None:
        denied_origin = self.client.get("/v1/jobs", headers=self.headers(origin="https://evil.example"))
        denied_user = self.client.get("/v1/jobs", headers={
            "Origin": ORIGIN,
            "Authorization": f"tma {signed_init_data(99)}",
        })
        allowed = self.client.get("/v1/jobs", headers=self.headers())

        self.assertEqual(403, denied_origin.status_code)
        self.assertNotIn("Access-Control-Allow-Origin", denied_origin.headers)
        self.assertEqual(403, denied_user.status_code)
        self.assertEqual(200, allowed.status_code)
        self.assertEqual(ORIGIN, allowed.headers["Access-Control-Allow-Origin"])
        self.assertEqual(200, self.client.get("/healthz").status_code)

    def test_source_preview_allows_origin_without_identity_but_jobs_stay_private(self) -> None:
        preview = self.client.post(
            "/v1/sources/probe",
            headers={"Origin": ORIGIN},
            json={"uri": "https://downloads.example/rom.zip"},
        )
        jobs = self.client.get("/v1/jobs", headers={"Origin": ORIGIN})

        self.assertEqual(200, preview.status_code)
        self.assertEqual("PKG110", preview.json["productName"])
        self.assertEqual(401, jobs.status_code)

    def test_webhook_requires_secret_and_dispatches_authenticated_update(self) -> None:
        handler = Mock()
        api = TelegramMiniAppAPI(
            bot_token=TOKEN,
            allowed_origin=f"{ORIGIN}/Wukong-ROM-Studio-Hybrid/",
            access=self.access,
            orchestrator=self.orchestrator,
            runtime=self.runtime,
            catalog_provider=lambda: {"devices": []},
            diagnostics_provider=lambda: {"ready": True},
            source_probe_provider=self.probe,
            telegram_update_handler=handler,
            telegram_webhook_secret="secret-token",
        )
        client = api.app.test_client()

        denied = client.post("/telegram/webhook", json={"update_id": 1})
        accepted = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
            json={"update_id": 1},
        )

        self.assertEqual(403, denied.status_code)
        self.assertEqual(204, accepted.status_code)
        handler.assert_called_once_with({"update_id": 1})

    def test_actions_callback_requires_fresh_hmac_and_refreshes_existing_job(self) -> None:
        probe = self.client.post(
            "/v1/sources/probe",
            headers=self.headers(),
            json={"uri": "https://downloads.example/rom.zip"},
        )
        self.assertEqual(200, probe.status_code)
        created = self.client.post("/v1/jobs", headers=self.headers(), json=self.recipe())
        job_id = created.json["job_id"]
        body = json.dumps({"jobId": job_id}, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        key = hmac.new(
            b"WukongActionsCallback\0",
            CALLBACK_SECRET.encode(),
            hashlib.sha256,
        ).digest()
        signature = hmac.new(
            key,
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()

        denied = self.client.post("/internal/actions/callback", data=body)
        stale = self.client.post(
            "/internal/actions/callback",
            headers={
                "Content-Type": "application/json",
                "X-Wukong-Timestamp": str(int(timestamp) - 600),
                "X-Wukong-Signature": signature,
            },
            data=body,
        )
        accepted = self.client.post(
            "/internal/actions/callback",
            headers={
                "Content-Type": "application/json",
                "X-Wukong-Timestamp": timestamp,
                "X-Wukong-Signature": signature,
            },
            data=body,
        )

        self.assertEqual(403, denied.status_code)
        self.assertEqual(403, stale.status_code)
        self.assertEqual(200, accepted.status_code)
        self.runtime.refresh.assert_called_with(self.store.get(job_id))
        self.runtime.notify_terminal.assert_called_once()

    def test_pre_executor_callback_reconciles_failure_without_waiting_for_drive(self) -> None:
        created = self.client.post("/v1/jobs", headers=self.headers(), json=self.recipe())
        job_id = created.json["job_id"]
        self.runtime.reset_mock()
        self.runtime.reconcile_actions_callback.return_value = self.store.update(
            job_id,
            status=JobStatus.FAILED,
            stage="github-actions-failed",
            external_run_id=321,
            error="route failed",
        )
        body = json.dumps(
            {
                "jobId": job_id,
                "runId": 321,
                "workflowResult": "failure",
                "preExecutorFailure": True,
            },
            separators=(",", ":"),
        ).encode()
        timestamp = str(int(time.time()))
        key = hmac.new(
            b"WukongActionsCallback\0",
            CALLBACK_SECRET.encode(),
            hashlib.sha256,
        ).digest()
        signature = hmac.new(
            key,
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()

        accepted = self.client.post(
            "/internal/actions/callback",
            headers={
                "Content-Type": "application/json",
                "X-Wukong-Timestamp": timestamp,
                "X-Wukong-Signature": signature,
            },
            data=body,
        )

        self.assertEqual(200, accepted.status_code)
        self.assertEqual("failed", accepted.json["status"])
        self.runtime.refresh.assert_not_called()
        self.runtime.reconcile_actions_callback.assert_called_once_with(
            self.store.get(job_id),
            run_id=321,
            conclusion="failure",
        )

    def test_actions_callback_accepts_runner_bearer_verified_via_github(self) -> None:
        created = self.client.post("/v1/jobs", headers=self.headers(), json=self.recipe())
        job_id = created.json["job_id"]
        token = "g" * 40
        self.runtime.verify_actions_bearer.return_value = "success"
        self.runtime.reconcile_actions_callback.side_effect = lambda manifest, **_: manifest
        body = json.dumps(
            {
                "jobId": job_id,
                "runId": 555,
                "workflowResult": "success",
                "preExecutorFailure": False,
            },
            separators=(",", ":"),
        ).encode()

        short = self.client.post(
            "/internal/actions/callback",
            headers={"Content-Type": "application/json", "Authorization": "Bearer short"},
            data=body,
        )
        accepted = self.client.post(
            "/internal/actions/callback",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            data=body,
        )

        self.assertEqual(403, short.status_code)
        self.assertEqual(200, accepted.status_code)
        self.runtime.verify_actions_bearer.assert_called_once_with(token, 555)
        self.runtime.refresh.assert_called_once_with(self.store.get(job_id))
        self.runtime.notify_terminal.assert_called_once()

    def test_actions_callback_rejects_runner_token_github_does_not_confirm(self) -> None:
        created = self.client.post("/v1/jobs", headers=self.headers(), json=self.recipe())
        job_id = created.json["job_id"]
        self.runtime.reset_mock()
        self.runtime.verify_actions_bearer.side_effect = PermissionError(
            "Actions callback authentication failed"
        )
        body = json.dumps(
            {
                "jobId": job_id,
                "runId": 555,
                "workflowResult": "success",
                "preExecutorFailure": False,
            },
            separators=(",", ":"),
        ).encode()

        denied = self.client.post(
            "/internal/actions/callback",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {'g' * 40}"},
            data=body,
        )

        self.assertEqual(403, denied.status_code)
        self.runtime.refresh.assert_not_called()
        self.runtime.reconcile_actions_callback.assert_not_called()
        self.runtime.notify_terminal.assert_not_called()

    def test_health_waits_for_transport_readiness_and_identifies_release(self) -> None:
        ready = False
        api = TelegramMiniAppAPI(
            bot_token=TOKEN,
            allowed_origin=f"{ORIGIN}/Wukong-ROM-Studio-Hybrid/",
            access=self.access,
            orchestrator=self.orchestrator,
            runtime=self.runtime,
            catalog_provider=lambda: {"devices": []},
            diagnostics_provider=lambda: {"ready": True},
            source_probe_provider=self.probe,
            readiness_provider=lambda: ready,
        )
        client = api.app.test_client()

        with patch.dict("os.environ", {"WUKONG_RELEASE_SHA": "c" * 40}):
            starting = client.get("/healthz")
            ready = True
            healthy = client.get("/healthz")

        self.assertEqual(503, starting.status_code)
        self.assertEqual("starting", starting.json["status"])
        self.assertEqual(200, healthy.status_code)
        self.assertEqual("c" * 40, healthy.json["release"])

    def test_probe_create_list_detail_events_and_ownership(self) -> None:
        probe = self.client.post(
            "/v1/sources/probe",
            headers=self.headers(),
            json={"uri": "https://downloads.example/rom.zip"},
        )
        created = self.client.post("/v1/jobs", headers=self.headers(), json=self.recipe())

        self.assertEqual(200, probe.status_code)
        self.assertNotIn("metadata", probe.json)
        for key in (
            "provider", "filename", "resolvedHost", "sizeBytes", "productName", "device",
            "version", "androidVersion", "securityPatch", "buildDate", "otaType", "contentType",
            "lastModified", "md5", "deepInspected", "warning",
        ):
            self.assertIn(key, probe.json)
        self.assertEqual(201, created.status_code)
        job_id = created.json["job_id"]
        stored = self.store.recipe(job_id)
        self.assertEqual("PKG110", stored.source.metadata["productName"])
        self.assertEqual("16", stored.source.metadata["androidVersion"])
        self.assertEqual(8718572190, stored.source.size_bytes)
        self.runtime.start.assert_called_once()

        listed = self.client.get("/v1/jobs", headers=self.headers())
        detail = self.client.get(f"/v1/jobs/{job_id}", headers=self.headers())
        events = self.client.get(f"/v1/jobs/{job_id}/events", headers=self.headers())
        denied = self.client.get(f"/v1/jobs/{job_id}", headers=self.headers(43))

        self.assertEqual(1, len(listed.json["jobs"]))
        self.assertNotIn("owner", detail.json)
        self.assertEqual("PKG110_16.0.10.500(CN01)", detail.json["recipe"]["source"]["metadata"]["version"])
        self.assertEqual("submitted", events.json["events"][0]["type"])
        self.assertEqual(404, denied.status_code)

    def test_cache_clear_preserves_admin_boundary(self) -> None:
        inspected = self.client.get("/v1/cache", headers=self.headers())
        denied = self.client.post("/v1/cache/clear", headers=self.headers())
        cleared = self.client.post("/v1/cache/clear", headers=self.headers(1))

        self.assertEqual(3, inspected.json["entryCount"])
        self.assertEqual(403, denied.status_code)
        self.assertEqual(0, cleared.json["entryCount"])

    def test_probe_concurrency_is_bounded(self) -> None:
        self.assertTrue(self.api._probe_slots.acquire(blocking=False))
        self.assertTrue(self.api._probe_slots.acquire(blocking=False))
        try:
            response = self.client.post(
                "/v1/sources/probe",
                headers=self.headers(),
                json={"uri": "https://downloads.example/rom.zip"},
            )
        finally:
            self.api._probe_slots.release()
            self.api._probe_slots.release()

        self.assertEqual(429, response.status_code)


class TelegramJobNotifierTests(unittest.TestCase):
    def test_runtime_notifies_once_after_public_artifact_exists(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = InMemoryJobStore()
        orchestrator = HybridOrchestrator(store=store, workspace_root=root / "jobs")
        recipe = BuildRecipe.from_dict({
            "task": "build",
            "device": "PKG110",
            "source": {
                "kind": "https",
                "uri": "https://downloads.example/rom.zip",
                "metadata": {
                    "productName": "PKG110",
                    "version": "PKG110_16.0.10.500(CN01)",
                    "androidVersion": "16",
                    "securityPatch": "2026-08-01",
                    "buildDate": "2026-08-11 09:38:18",
                },
            },
            "build": {"notifyTelegram": True, "modVersion": "ColorOS_16.0.10"},
        })
        job = orchestrator.submit(recipe, Identity("telegram", "42", "user"))
        manifest = store.update(
            job.job_id,
            status=JobStatus.SUCCEEDED,
            artifacts=[ArtifactRecord(
                "Wukong.zip",
                "drive:artifact.zip",
                "a" * 64,
                1024,
                "https://drive.google.com/download/fixture",
            )],
        )
        post = Mock()
        post.return_value.raise_for_status.return_value = None
        notifier = TelegramJobNotifier(TOKEN, http_post=post)
        from wukong.runtime import HybridRuntime

        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
            terminal_notifier=notifier,
        )
        runtime.notify_terminal(manifest)
        runtime.notify_terminal(manifest)

        post.assert_called_once()
        text = post.call_args.kwargs["json"]["text"]
        self.assertIn("PKG110_16.0.10.500(CN01)", text)
        self.assertIn("Android: 16", text)
        self.assertIn("https://drive.google.com/download/fixture", text)
        self.assertEqual(1, len([
            event for event in store.events(job.job_id)
            if event.type == "telegram_terminal_notified"
        ]))


if __name__ == "__main__":
    unittest.main()

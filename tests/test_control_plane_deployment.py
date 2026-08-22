from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tools.control_plane_preflight import (
    ControlPlaneConfigurationError,
    load_configuration,
    run_preflight,
)
from tools.render_control_plane_env import render_environment


class ControlPlaneDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.rclone = self.root / "rclone.conf"
        self.rclone.write_text("[wukong-gdrive]\ntype = drive\n", encoding="utf-8")
        if os.name != "nt":
            self.rclone.chmod(0o600)
        self.values = {
            "WUKONG_MINI_API_DOMAIN": "mini-api.example.com",
            "WUKONG_RELEASE_SHA": "a" * 40,
            "WUKONG_TELEGRAM_BOT_TOKEN": "1234567:" + "a" * 32,
            "WUKONG_TELEGRAM_ADMIN_IDS": "1,42",
            "WUKONG_TELEGRAM_TRANSPORT": "webhook",
            "WUKONG_TELEGRAM_WEBHOOK_SECRET": "s" * 48,
            "WUKONG_TELEGRAM_WEB_APP_URL": "https://example.github.io/Wukong/",
            "WUKONG_TELEGRAM_MINI_APP_API_URL": "https://mini-api.example.com",
            "WUKONG_GITHUB_REPOSITORY": "owner/repository",
            "WUKONG_GITHUB_TOKEN": "github-token-" + "x" * 32,
            "WUKONG_RCLONE_REMOTE": "wukong-gdrive",
            "WUKONG_RCLONE_CONFIG": str(self.rclone),
        }

    def test_configuration_requires_matching_https_origin_and_webhook_secret(self) -> None:
        configured = load_configuration(self.values)
        self.assertEqual("mini-api.example.com", configured.domain)
        self.assertEqual(("1", "42"), configured.admin_ids)
        self.assertEqual("webhook", configured.telegram_transport)

        invalid = dict(self.values, WUKONG_TELEGRAM_MINI_APP_API_URL="https://other.example.com")
        with self.assertRaisesRegex(ControlPlaneConfigurationError, "must use"):
            load_configuration(invalid)
        invalid = dict(self.values, WUKONG_TELEGRAM_WEBHOOK_SECRET="short")
        with self.assertRaisesRegex(ControlPlaneConfigurationError, "32-256"):
            load_configuration(invalid)

    def test_offline_preflight_validates_rclone_remote_without_exposing_secrets(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "wukong-gdrive:\n", "")

        result = run_preflight(environ=self.values, run_command=fake_run)

        self.assertEqual("ready", result["configuration"])
        self.assertEqual("ready", result["rcloneConfiguration"])
        self.assertEqual("rclone", calls[0][0])
        self.assertNotIn(self.values["WUKONG_TELEGRAM_BOT_TOKEN"], str(result))

    def test_online_preflight_checks_telegram_github_and_drive(self) -> None:
        responses = []
        telegram = Mock(status_code=200)
        telegram.json.return_value = {"ok": True}
        github = Mock(status_code=200)
        responses.extend([telegram, github])

        def fake_get(*_args, **_kwargs):
            return responses.pop(0)

        def fake_run(command, **_kwargs):
            output = "wukong-gdrive:\n" if command[1] == "listremotes" else ""
            return subprocess.CompletedProcess(command, 0, output, "")

        result = run_preflight(
            online=True,
            environ=self.values,
            run_command=fake_run,
            http_get=fake_get,
        )

        self.assertEqual("ready", result["telegram"])
        self.assertEqual("ready", result["githubActions"])
        self.assertEqual("ready", result["googleDrive"])

    def test_environment_renderer_quotes_values_and_sets_webhook_transport(self) -> None:
        rendered = render_environment(
            self.values,
            domain="mini-api.example.com",
            release_sha="b" * 40,
        )

        self.assertIn('WUKONG_RELEASE_SHA="' + "b" * 40 + '"', rendered)
        self.assertIn('WUKONG_TELEGRAM_TRANSPORT="webhook"', rendered)
        self.assertIn('WUKONG_TELEGRAM_MINI_APP_API_URL="https://mini-api.example.com"', rendered)
        self.assertNotIn("RCLONE_CONFIG_B64", rendered)

    def test_deployment_contract_has_verified_ssh_health_rollback_and_secret_excludes(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github/workflows/control-plane-production.yml").read_text(
            encoding="utf-8"
        )
        ci = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        remote = (Path(__file__).parents[1] / "deploy/control-plane/deploy_remote.sh").read_text(
            encoding="utf-8"
        )
        dockerignore = (Path(__file__).parents[1] / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn("StrictHostKeyChecking=yes", workflow)
        self.assertIn("WUKONG_VPS_KNOWN_HOSTS", workflow)
        self.assertIn("control_plane_preflight --online", remote)
        self.assertIn("rollback", remote)
        self.assertIn("release", workflow)
        self.assertIn("condition: service_started", (Path(__file__).parents[1] / "deploy/control-plane/compose.yml").read_text(encoding="utf-8"))
        self.assertIn("control-plane-container", ci)
        self.assertIn("os.getuid() == 10001", ci)
        self.assertIn("**/.env", dockerignore)
        self.assertIn("**/secrets", dockerignore)

    def test_render_free_blueprint_uses_docker_generated_tls_and_ephemeral_state_backup(self) -> None:
        root = Path(__file__).parents[1]
        blueprint = (root / "render.yaml").read_text(encoding="utf-8")
        entrypoint = (root / "deploy/control-plane/entrypoint.sh").read_text(encoding="utf-8")
        binder = (root / ".github/workflows/bind-render-control-plane.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("runtime: docker", blueprint)
        self.assertIn("plan: free", blueprint)
        self.assertIn("healthCheckPath: /healthz", blueprint)
        self.assertNotIn("maxShutdownDelaySeconds", blueprint)
        self.assertIn("WUKONG_CONTROL_PLANE_STATE_BACKUP_ENABLED", blueprint)
        self.assertIn("WUKONG_CONTROL_PLANE_STATE_RESTORE_ATTEMPTS", blueprint)
        self.assertIn("WUKONG_CONTROL_PLANE_STATE_RESTORE_RETRY_SECONDS", blueprint)
        self.assertIn("WUKONG_CONTROL_PLANE_BACKGROUND_WATCHERS", blueprint)
        self.assertIn("WUKONG_CONTROL_PLANE_ONLINE_PREFLIGHT", blueprint)
        self.assertIn("WUKONG_RCLONE_CONFIG_CONTENT_B64", blueprint)
        self.assertNotIn("github_pat_", blueprint)
        self.assertIn("RENDER_EXTERNAL_URL", entrypoint)
        self.assertIn('WUKONG_TELEGRAM_MINI_APP_API_PORT', entrypoint)
        self.assertIn("WukongTelegramWebhook", entrypoint)
        self.assertIn("control_plane_preflight --online", entrypoint)
        self.assertNotIn("WUKONG_TELEGRAM_WEBHOOK_SECRET\n        generateValue", blueprint)
        self.assertIn("api_url", binder)
        self.assertIn("/healthz", binder)
        self.assertIn("WUKONG_TELEGRAM_MINI_APP_API_URL", binder)


if __name__ == "__main__":
    unittest.main()

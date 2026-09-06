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
from tools.build_vercel_mini_app import (
    PRODUCTION_API_ORIGIN,
    build_site,
    configured_api_origin,
)


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

    def test_deployment_contract_uses_private_render_hook_vercel_and_secret_excludes(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github/workflows/control-plane-production.yml").read_text(
            encoding="utf-8"
        )
        ci = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        vercel_workflow = (Path(__file__).parents[1] / ".github/workflows/telegram-mini-app-pages.yml").read_text(encoding="utf-8")
        dockerignore = (Path(__file__).parents[1] / ".dockerignore").read_text(encoding="utf-8")
        dockerfile = (Path(__file__).parents[1] / "deploy/control-plane/Dockerfile").read_text(
            encoding="utf-8"
        )
        control_plane_requirements = (
            Path(__file__).parents[1] / "deploy/control-plane/requirements.txt"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn("RENDER_DEPLOY_HOOK_URL", workflow)
        self.assertIn("api.render.com/deploy/", workflow)
        self.assertIn("ref=${GITHUB_SHA}", workflow)
        self.assertIn("for _ in {1..120}", workflow)
        self.assertIn("/healthz", workflow)
        self.assertIn("telegram-mini-app-pages.yml", workflow)
        self.assertNotIn("WUKONG_VPS_SSH_KEY", workflow)
        self.assertIn("VERCEL_TOKEN", vercel_workflow)
        self.assertIn("vercel deploy --yes --prod --archive=tgz", vercel_workflow)
        self.assertIn("workflow_dispatch:", vercel_workflow)
        self.assertNotIn("git-integration", vercel_workflow)
        self.assertIn("Git Integration auto-deploy is disabled", vercel_workflow)
        self.assertNotIn("on:\n  push:", vercel_workflow)
        self.assertNotIn("vercel build --prod", vercel_workflow)
        self.assertNotIn("deploy-pages", vercel_workflow)
        self.assertIn("condition: service_started", (Path(__file__).parents[1] / "deploy/control-plane/compose.yml").read_text(encoding="utf-8"))
        self.assertIn("control-plane-container", ci)
        self.assertIn("os.getuid() == 10001", ci)
        self.assertIn("**/.env", dockerignore)
        self.assertIn("**/secrets", dockerignore)
        self.assertIn("WUKONG_RCLONE_RELEASE=1.75.0", dockerfile)
        self.assertIn(
            "aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa",
            dockerfile,
        )
        self.assertIn("sha256sum --check --strict", dockerfile)
        self.assertNotIn("ca-certificates gosu rclone", dockerfile)
        self.assertIn("psycopg[binary]", control_plane_requirements)
        self.assertIn("deploy/control-plane/requirements.txt", dockerfile)

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
        self.assertRegex(blueprint, r"(?s)- key: DATABASE_URL\s+sync: false")
        self.assertRegex(
            blueprint,
            r"(?s)- key: WUKONG_GITHUB_REPOSITORY\s+sync: false",
        )
        self.assertIn("https://wukong-rom-studio.vercel.app/", blueprint)
        self.assertIn("WUKONG_CONTROL_PLANE_REQUIRE_POSTGRES", blueprint)
        self.assertNotIn("xuankhanh24", blueprint.casefold())
        self.assertNotIn("github_pat_", blueprint)
        self.assertIn("RENDER_EXTERNAL_URL", entrypoint)
        self.assertIn('WUKONG_TELEGRAM_MINI_APP_API_PORT', entrypoint)
        self.assertIn("WukongTelegramWebhook", entrypoint)
        self.assertIn("control_plane_preflight --online", entrypoint)
        self.assertNotIn("WUKONG_TELEGRAM_WEBHOOK_SECRET\n        generateValue", blueprint)
        self.assertIn("api_url", binder)
        self.assertIn("/healthz", binder)
        self.assertIn("WUKONG_TELEGRAM_MINI_APP_API_URL", binder)

    def test_cloudflare_production_deploy_is_gated_before_any_mutation(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github/workflows/cloudflare-control-plane.yml"
        ).read_text(encoding="utf-8")
        vercel_workflow = (
            Path(__file__).parents[1] / ".github/workflows/telegram-mini-app-pages.yml"
        ).read_text(encoding="utf-8")

        gate = workflow.index(
            "Require verified read-only migration before production deployment"
        )
        self.assertLess(gate, workflow.index("Upload Worker secrets"))
        self.assertLess(gate, workflow.index("- name: Apply D1 migrations"))
        self.assertLess(gate, workflow.index("- name: Deploy exact release"))
        self.assertIn("if: (inputs.target || 'staging') == 'production'", workflow)
        self.assertNotIn("Require verified read-only migration before cutover", workflow)
        self.assertLess(
            workflow.index("- name: Deploy exact release"),
            workflow.index("- name: Deploy Vercel bundle after production health"),
        )
        self.assertIn("Verify matching Vercel source transport after frontend promotion", workflow)
        self.assertIn('npm test --prefix telegram_mini_app', workflow)
        self.assertIn('tests.test_mini_app_upgrade', workflow)
        self.assertIn('--ref "$GITHUB_REF_NAME"', workflow)
        self.assertIn('--field release_sha="$WUKONG_RELEASE_SHA"', workflow)
        self.assertIn('inputs.release_sha || github.sha', vercel_workflow)

        legacy_render = (
            Path(__file__).parents[1] / ".github/workflows/control-plane-production.yml"
        ).read_text(encoding="utf-8")
        render_binding = (
            Path(__file__).parents[1] / ".github/workflows/bind-render-control-plane.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('--field release_sha="$GITHUB_SHA"', legacy_render)
        self.assertIn('--field release_sha="$GITHUB_SHA"', render_binding)

    def test_vercel_static_bundle_contains_no_personal_github_identity(self) -> None:
        output = self.root / "vercel-static"

        build_site(
            Path(__file__).parents[1],
            output,
            api_url="https://wukong-mini-api.onrender.com",
            release="privacy-test",
        )

        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in output.iterdir()
            if path.is_file()
        ).casefold()
        vercel = (Path(__file__).parents[1] / "vercel.json").read_text(encoding="utf-8")
        workflow = (
            Path(__file__).parents[1] / ".github/workflows/telegram-mini-app-pages.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("https://wukong-mini-api.onrender.com", combined)
        self.assertNotIn("__wukong_telegram_mini_app_api_url__", combined)
        self.assertNotIn("xuankhanh24", combined)
        self.assertIn("GITHUB_REPOSITORY_OWNER", workflow)
        self.assertIn("legacy_github_owner", workflow)
        self.assertIn("legacy_cloudflare_handle", workflow)
        self.assertNotIn("github.com", combined)
        self.assertNotIn("github.io", combined)
        self.assertIn("./assets/app-", combined)
        self.assertTrue((output / "asset-manifest.json").exists())
        self.assertEqual(
            (
                Path(__file__).parents[1]
                / "telegram_mini_app"
                / "WukongStudio.svg"
            ).read_text(encoding="utf-8"),
            (output / "WukongStudio.svg").read_text(encoding="utf-8"),
        )
        self.assertIn('"outputDirectory": ".vercel-static"', vercel)
        self.assertIn("X-Robots-Tag", vercel)

    def test_vercel_git_integration_defaults_to_cloudflare_worker(self) -> None:
        self.assertEqual(PRODUCTION_API_ORIGIN, configured_api_origin({}))
        self.assertTrue(PRODUCTION_API_ORIGIN.endswith(".workers.dev"))
        self.assertNotIn("onrender.com", PRODUCTION_API_ORIGIN)


if __name__ == "__main__":
    unittest.main()

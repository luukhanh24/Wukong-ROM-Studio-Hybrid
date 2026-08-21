from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from wukong.models import BuildRecipe, Identity, JobStatus, RecipeValidationError
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore
from wukong.routing import RunnerInventory
from wukong.runtime import HybridRuntime
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import (
    BotResponse,
    TelegramBotController,
    TelegramLongPollingDaemon,
    TelegramUIStateStore,
)
from telegram_bot_daemon import (
    _configured_admin_ids,
    build_control_plane_catalog,
    build_telegram_catalog,
)


class TelegramBotUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.access = TelegramAccessStore(self.root / "access.json", admin_ids={1})
        self.access.approve(42, actor=self.access.identity(1))
        self.store = InMemoryJobStore()
        self.orchestrator = HybridOrchestrator(
            store=self.store,
            workspace_root=self.root / "jobs",
            inventory_provider=lambda: RunnerInventory(
                True,
                free_disk_bytes=200 * 1024**3,
                memory_bytes=32 * 1024**3,
                logical_cpus=16,
            ),
            access_validator=lambda _recipe, _identity: None,
        )
        self.controller = TelegramBotController(
            access=self.access,
            orchestrator=self.orchestrator,
            catalog_provider=lambda: {
                "devices": [
                    {"product_name": "PKG110", "name": "OnePlus Ace 6"},
                    {"product_name": "CPH2725", "name": "OnePlus 13R"},
                ],
                "modVersions": ["ColorOS_16.0.8"],
                "availableGitHubModVersions": ["ColorOS_16.0.8"],
                "modsByVersion": {
                    "ColorOS_16.0.8": [
                        {"name": "Fix_Metis", "ready": True},
                        {"name": "WK_Installer", "ready": True},
                        {"name": "Camera_mod", "ready": True},
                    ]
                },
                "presetDefaultsByVersion": {
                    "ColorOS_16.0.8": {
                        "lite": ["Fix_Metis", "WK_Installer"],
                        "both": ["Fix_Metis", "WK_Installer", "Camera_mod"],
                    }
                },
            },
            diagnostics_provider=lambda: {"runner": "ready"},
            cloud_provider=lambda category: {
                "available": True,
                "category": category,
                "entries": [
                    {
                        "path": "PKG110/aabb/stock.zip",
                        "name": "stock.zip",
                        "sizeBytes": 123,
                    }
                ],
            },
            source_probe_provider=lambda _uri: {
                "provider": "oplus",
                "filename": "PKG110.zip",
                "sizeBytes": 8645349608,
                "device": "OP5D2BL1",
                "version": "PKG110_16.0.8.300(CN01)",
                "securityPatch": "2026-06-01",
                "otaType": "AB",
                "deepInspected": True,
            },
            ui_state=TelegramUIStateStore(self.root / "telegram-ui-state.json"),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_start_returns_vietnamese_menu_with_buttons(self) -> None:
        response = self.controller.handle_ui(42, "/start")

        self.assertIsInstance(response, BotResponse)
        self.assertIn("Tạo bản build", response.text)
        labels = [
            button["text"]
            for row in response.reply_markup["inline_keyboard"]
            for button in row
        ]
        self.assertIn("Tạo bản build", labels)
        self.assertIn("Công việc của tôi", labels)
        self.assertIn("English", labels)

    def test_main_menu_exposes_configured_telegram_mini_app(self) -> None:
        self.controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"

        response = self.controller.handle_ui(42, "/start")

        buttons = [button for row in response.reply_markup["inline_keyboard"] for button in row]
        app_button = next(button for button in buttons if "Mini App" in button["text"])
        self.assertEqual("v1:app", app_button["callback_data"])

        launcher = self.controller.handle_callback(42, app_button["callback_data"])
        keyboard_button = launcher.reply_markup["keyboard"][0][0]
        self.assertEqual(
            keyboard_button["web_app"]["url"],
            "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/",
        )

    def test_app_command_uses_reply_keyboard_transport_required_by_send_data(self) -> None:
        self.controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"

        response = self.controller.handle_ui(42, "/app")

        self.assertIn("keyboard", response.reply_markup)
        self.assertNotIn("inline_keyboard", response.reply_markup)
        self.assertTrue(response.reply_markup["one_time_keyboard"])

    def test_mini_app_submits_recipe_under_authenticated_telegram_identity(self) -> None:
        response = self.controller.handle_web_app_data(42, json.dumps({
            "version": 1,
            "action": "submit_recipe",
            "recipe": {
                "schemaVersion": 1,
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                "execution": {"target": "github-auto"},
                "build": {
                    "preset": "plus",
                    "modVersion": "ColorOS_16.0.8",
                    "mods": ["Camera_mod"],
                    "package": True,
                },
            },
        }))

        self.assertIn("Job", response.text)
        jobs = self.orchestrator.list(Identity("telegram", "42", "user"))
        self.assertEqual(1, len(jobs))
        self.assertEqual(jobs[0].owner.subject, "42")

    def test_mini_app_can_probe_unresolved_oplus_source(self) -> None:
        response = self.controller.handle_web_app_data(42, json.dumps({
            "version": 1,
            "action": "probe_source",
            "uri": "https://component-ota-cn.allawntech.com/downloadCheck?c=abc",
        }))

        self.assertIn("Đã nhận diện ROM", response.text)
        self.assertIn("PKG110_16.0.8.300(CN01)", response.text)
        self.assertNotIn("Signature", response.text)

    def test_mini_app_quick_actions_reuse_chat_capabilities(self) -> None:
        jobs = self.controller.handle_web_app_data(42, '{"version":1,"action":"jobs"}')
        diagnostics = self.controller.handle_web_app_data(
            42, '{"version":1,"action":"diagnostics"}'
        )

        self.assertIn("chưa có job", jobs.text.casefold())
        self.assertIn("Chẩn đoán", diagnostics.text)

    def test_mini_app_cache_actions_preserve_admin_boundary(self) -> None:
        self.controller.cache_provider = lambda: {"entryCount": 3, "totalBytes": 2048}
        self.controller.cache_clearer = lambda: {"entryCount": 0, "totalBytes": 0}

        inspected = self.controller.handle_web_app_data(42, '{"version":1,"action":"cache"}')
        denied = self.controller.handle_web_app_data(42, '{"version":1,"action":"cache_clear"}')
        cleared = self.controller.handle_web_app_data(1, '{"version":1,"action":"cache_clear"}')

        self.assertIn("entryCount", inspected.text)
        self.assertIn("Admin", denied.text)
        self.assertIn("entryCount", cleared.text)

    def test_language_callback_is_persisted_per_user(self) -> None:
        response = self.controller.handle_callback(42, "v1:lang:en")
        self.assertIn("New build", response.text)

        restarted = TelegramUIStateStore(self.root / "telegram-ui-state.json")
        self.assertEqual("en", restarted.language("42"))
        self.assertIn("My jobs", self.controller.handle_ui(42, "/start").text)

    def test_build_wizard_creates_recipe_without_json(self) -> None:
        self.controller.handle_callback(42, "v1:new")
        self.controller.handle_callback(42, "v1:task:build")
        self.controller.handle_callback(42, "v1:run:github")
        prompt = self.controller.handle_callback(42, "v1:src:url")
        self.assertIn("URL", prompt.text)

        devices = self.controller.handle_ui(42, "https://example.com/rom.zip")
        self.assertIn("PKG110", devices.text)
        self.controller.handle_callback(42, "v1:dev:0")
        self.controller.handle_callback(42, "v1:mv:0")
        mods = self.controller.handle_callback(42, "v1:pre:lite")
        self.assertIn("Fix_Metis", mods.text)
        confirmation = self.controller.handle_callback(42, "v1:mods_done")
        self.assertIn("PKG110", confirmation.text)
        self.assertIn("GitHub", confirmation.text)

        submitted = self.controller.handle_callback(42, "v1:confirm")
        self.assertIn("đã được tạo", submitted.text.casefold())
        jobs = self.orchestrator.list(Identity("telegram", "42", "user"))
        self.assertEqual(1, len(jobs))
        recipe = self.store.recipe(jobs[0].job_id)
        self.assertEqual("https", recipe.source.kind)
        self.assertEqual("github-auto", recipe.execution.target)
        self.assertEqual("PKG110", recipe.device)
        self.assertEqual("ColorOS_16.0.8", recipe.build.mod_version)
        self.assertEqual(("Fix_Metis", "WK_Installer"), recipe.build.mods)

    def test_telegram_wizard_exposes_only_always_available_cloud_runner(self) -> None:
        self.controller.handle_callback(42, "v1:new")
        picker = self.controller.handle_callback(42, "v1:task:build")
        callbacks = [
            button["callback_data"]
            for row in picker.reply_markup["inline_keyboard"]
            for button in row
        ]

        self.assertIn("v1:run:github", callbacks)
        self.assertNotIn("v1:run:local", callbacks)

    def test_wizard_exposes_artifact_publish_task(self) -> None:
        response = self.controller.handle_callback(42, "v1:new")
        callbacks = [
            button["callback_data"]
            for row in response.reply_markup["inline_keyboard"]
            for button in row
        ]
        self.assertIn("v1:task:publish", callbacks)

    def test_github_build_falls_back_to_hosted_when_self_hosted_is_offline(self) -> None:
        self.controller.ui_state.set_session(42, {
            "step": "confirm",
            "task": "build",
            "device": "PKG110",
            "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
            "execution": "github-auto",
            "preset": "lite",
            "mod_version": "ColorOS_16.0.8",
            "selected_mods": ["Fix_Metis"],
        })
        self.controller.orchestrator.inventory_provider = lambda: RunnerInventory(False)

        response = self.controller.handle_callback(42, "v1:confirm")

        # Large estimates used to hard-fail without a self-hosted runner. Hybrid
        # now queues on maximized ubuntu-24.04 so Telegram builds stay usable.
        self.assertIn("ubuntu-24.04", response.text)
        self.assertIn("queued", response.text.casefold())
        self.assertNotIn("Required Wukong self-hosted Linux runner is offline", response.text)

    def test_mod_picker_supports_toggle_select_all_and_pagination(self) -> None:
        many_mods = [
            {"name": f"Mod_{index:02d}", "ready": True}
            for index in range(19)
        ]
        self.controller.catalog_provider = lambda: {
            "devices": [{"product_name": "PKG110", "name": "OnePlus Ace 6"}],
            "modVersions": ["ColorOS_16.0.9"],
            "availableGitHubModVersions": ["ColorOS_16.0.9"],
            "modsByVersion": {"ColorOS_16.0.9": many_mods},
            "presetDefaultsByVersion": {"ColorOS_16.0.9": {"lite": [], "both": []}},
        }
        self.controller.handle_callback(42, "v1:new")
        self.controller.handle_callback(42, "v1:task:build")
        self.controller.handle_callback(42, "v1:run:github")
        self.controller.handle_callback(42, "v1:src:url")
        self.controller.handle_ui(42, "https://example.com/rom.zip")
        self.controller.handle_callback(42, "v1:dev:0")
        self.controller.handle_callback(42, "v1:mv:0")

        first_page = self.controller.handle_callback(42, "v1:pre:lite")
        self.assertIn("1/3", first_page.text)
        self.assertIn("Mod_00", first_page.text)
        self.assertNotIn("Mod_08", first_page.text)
        toggled = self.controller.handle_callback(42, "v1:mod:0")
        self.assertIn("1/19 MOD", toggled.text)
        second_page = self.controller.handle_callback(42, "v1:mods:1")
        self.assertIn("2/3", second_page.text)
        selected = self.controller.handle_callback(42, "v1:mods_all:1")
        self.assertIn("19 MOD", selected.text)
        confirmation = self.controller.handle_callback(42, "v1:mods_done")
        self.assertIn("19", confirmation.text)

        self.controller.handle_callback(42, "v1:confirm")
        recipe = self.store.recipe(self.orchestrator.list(Identity("telegram", "42", "user"))[0].job_id)
        self.assertEqual(19, len(recipe.build.mods))

    def test_both_preset_cannot_confirm_with_empty_mod_selection(self) -> None:
        self.controller.ui_state.set_session(42, {
            "step": "mods",
            "preset": "both",
            "mod_options": ["Fix_Metis"],
            "selected_mods": [],
        })

        response = self.controller.handle_callback(42, "v1:mods_done")

        self.assertIn("Lite và Plus", response.text)
        self.assertEqual("mods", self.controller.ui_state.session(42)["step"])

    def test_github_wizard_lists_only_versions_with_uploaded_content_pack(self) -> None:
        self.controller.catalog_provider = lambda: {
            "devices": [{"product_name": "PKG110", "name": "OnePlus Ace 6"}],
            "modVersions": ["ColorOS_16.0.8", "ColorOS_16.0.9"],
            "availableGitHubModVersions": ["ColorOS_16.0.8"],
            "modsByVersion": {},
        }
        self.controller.ui_state.set_session(42, {
            "step": "mod_version",
            "execution": "github-auto",
        })

        response = self.controller._mod_version_picker(42, "vi")

        self.assertIn("ColorOS_16.0.8", response.reply_markup["inline_keyboard"][0][0]["text"])
        labels = [button["text"] for row in response.reply_markup["inline_keyboard"] for button in row]
        self.assertNotIn("ColorOS_16.0.9", labels)

    def test_cloud_library_source_can_be_selected_with_buttons(self) -> None:
        self.controller.handle_callback(42, "v1:new")
        self.controller.handle_callback(42, "v1:task:build")
        self.controller.handle_callback(42, "v1:run:github")
        library = self.controller.handle_callback(42, "v1:src:library")
        self.assertIn("stock.zip", library.text)

        devices = self.controller.handle_callback(42, "v1:lib:0")
        self.assertIn("thiết bị", devices.text.casefold())
        session = self.controller.ui_state.session("42")
        self.assertEqual(
            "wukong-gdrive:WukongROM/sources/PKG110/aabb/stock.zip",
            session["source"]["uri"],
        )

    def test_configured_cloud_remote_is_used_by_wizard(self) -> None:
        self.controller.storage_remote = "custom-drive"
        self.controller.handle_callback(42, "v1:new")
        self.controller.handle_callback(42, "v1:task:mirror")
        self.controller.handle_callback(42, "v1:run:github")
        self.controller.handle_callback(42, "v1:src:library")
        self.controller.handle_callback(42, "v1:lib:0")
        self.controller.handle_callback(42, "v1:dev:0")
        submitted = self.controller.handle_callback(42, "v1:confirm")

        self.assertIn("đã được tạo", submitted.text.casefold())
        recipe = self.store.recipe(self.orchestrator.list(Identity("telegram", "42", "user"))[0].job_id)
        self.assertEqual("custom-drive", recipe.storage.remote)
        self.assertTrue(recipe.source.uri.startswith("custom-drive:"))

    def test_ota_query_url_is_accepted_but_hidden_from_confirmation(self) -> None:
        self.controller.handle_callback(42, "v1:new")
        self.controller.handle_callback(42, "v1:task:mirror")
        self.controller.handle_callback(42, "v1:run:github")
        self.controller.handle_callback(42, "v1:src:url")
        self.controller.handle_ui(42, "https://example.com/downloadCheck?c=abc&p=def&s=123")
        confirmation = self.controller.handle_callback(42, "v1:dev:0")
        self.assertNotIn("abc", confirmation.text)
        self.assertIn("?…", confirmation.text)

    def test_credential_query_url_is_rejected_and_never_persisted(self) -> None:
        self.controller.handle_callback(42, "v1:new")
        self.controller.handle_callback(42, "v1:task:mirror")
        self.controller.handle_callback(42, "v1:run:github")
        self.controller.handle_callback(42, "v1:src:url")
        rejected = self.controller.handle_ui(42, "https://example.com/rom.zip?token=very-secret")

        self.assertIn("credential", rejected.text)
        persisted = (self.root / "telegram-ui-state.json").read_text(encoding="utf-8")
        self.assertNotIn("very-secret", persisted)
        with self.assertRaisesRegex(RecipeValidationError, "credential"):
            BuildRecipe.from_dict(
                {
                    "task": "source_mirror",
                    "device": "PKG110",
                    "source": {"kind": "https", "uri": "https://example.com/rom.zip?token=very-secret"},
                }
            )

    def test_stale_wizard_callback_recovers_without_mutating_new_session(self) -> None:
        self.controller.handle_callback(42, "v1:new")
        stale = self.controller.handle_callback(42, "v1:run:github")

        self.assertIn("hết hạn", stale.text.casefold())
        self.assertEqual("task", self.controller.ui_state.session("42")["step"])

    def test_job_progress_and_callbacks_fit_telegram_limits(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "task": "source_mirror",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "execution": {"target": "github-auto"},
            }
        )
        job_id = "a" * 64
        self.orchestrator.submit(recipe, Identity("telegram", "42", "user"), job_id=job_id)
        self.store.update(job_id, status=JobStatus.UPLOADING, progress=0.8)

        detail = self.controller.handle_callback(42, f"v1:job:{job_id}")
        self.assertIn("80%", detail.text)
        callbacks = [
            button["callback_data"]
            for row in detail.reply_markup["inline_keyboard"]
            for button in row
        ]
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in callbacks))

    def test_job_callback_enforces_ownership_and_recovers_to_menu(self) -> None:
        other_identity = Identity("telegram", "99", "user")
        recipe = BuildRecipe.from_dict(
            {
                "task": "source_mirror",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://example.com/rom.zip"},
                "execution": {"target": "github-auto"},
            }
        )
        other = self.orchestrator.submit(recipe, other_identity)

        denied = self.controller.handle_callback(42, f"v1:job:{other.job_id}")
        self.assertIn("không thể", denied.text.casefold())
        self.assertIn("inline_keyboard", denied.reply_markup)

        stale = self.controller.handle_callback(42, "broken-callback")
        self.assertIn("hết hạn", stale.text.casefold())


class TelegramDaemonUITests(unittest.TestCase):
    def test_admin_ids_fall_back_to_the_configured_private_chat(self) -> None:
        with patch.dict(
            "telegram_bot_daemon.os.environ",
            {"WUKONG_TELEGRAM_CHAT_ID": "1678823419"},
            clear=True,
        ):
            self.assertEqual({"1678823419"}, _configured_admin_ids())

        with patch.dict(
            "telegram_bot_daemon.os.environ",
            {
                "WUKONG_TELEGRAM_CHAT_ID": "1678823419",
                "WUKONG_TELEGRAM_ADMIN_IDS": "42, 43",
            },
            clear=True,
        ):
            self.assertEqual({"42", "43"}, _configured_admin_ids())

    def test_reuses_one_http_session_for_telegram_requests(self) -> None:
        controller = Mock()
        controller.command_sets.return_value = {"vi": [], "en": []}
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success

        with patch("wukong.telegram_bot.requests.Session", return_value=http) as session:
            daemon = TelegramLongPollingDaemon("test-token", controller)
            daemon.register_commands()

        session.assert_called_once_with()
        self.assertEqual(2, http.post.call_count)

    def test_catalog_uses_installed_mod_root_and_only_uploaded_github_versions(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "Content")
            (content / "MOD" / "ColorOS_16.0.9" / "Camera_mod" / "system").mkdir(parents=True)
            (content / "MOD" / "RealmeUI_16.0.9" / "Gapps" / "product").mkdir(parents=True)
            index_path = Path(root, "index.json")
            index_path.write_text(json.dumps({
                "schemaVersion": 1,
                "packs": [
                    {
                        "id": "MOD/ColorOS_16.0.9",
                        "target": "MOD/ColorOS_16.0.9",
                        "remote": "drive:MOD/ColorOS_16.0.9",
                        "sizeBytes": 0,
                        "files": [],
                        "archive": {
                            "uri": "drive:MOD/ColorOS_16.0.9.tar.zst",
                            "sha256": "a" * 64,
                            "md5": "b" * 32,
                            "sizeBytes": 1,
                        },
                    },
                    {
                        "id": "MOD/RealmeUI_16.0.9",
                        "target": "MOD/RealmeUI_16.0.9",
                        "remote": "drive:MOD/RealmeUI_16.0.9",
                        "sizeBytes": 0,
                        "files": [],
                    },
                ],
            }), encoding="utf-8")

            catalog = build_telegram_catalog(content, index_path)

        self.assertEqual(
            ["ColorOS_16.0.9", "RealmeUI_16.0.9"],
            catalog["modVersions"],
        )
        self.assertEqual(["ColorOS_16.0.9"], catalog["availableGitHubModVersions"])
        self.assertIn(
            "Camera_mod",
            [item["name"] for item in catalog["modsByVersion"]["ColorOS_16.0.9"]],
        )

    def test_control_plane_catalog_does_not_require_installed_private_mods(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            index = path / "index.json"
            index.write_text(json.dumps({
                "schemaVersion": 1,
                "packs": [{
                    "id": "MOD/ColorOS_16.0.10",
                    "target": "MOD/ColorOS_16.0.10",
                    "remote": "drive:MOD/ColorOS_16.0.10",
                    "sizeBytes": 1,
                    "archive": {
                        "uri": "drive:MOD/ColorOS_16.0.10.tar.zst",
                        "sha256": "a" * 64,
                        "md5": "b" * 32,
                        "sizeBytes": 1,
                    },
                    "files": [{"path": "WK_Manager/system/app.apk", "sha256": "c" * 64, "sizeBytes": 1}],
                }],
            }), encoding="utf-8")

            with patch("telegram_bot_daemon.DATA_ROOT", path):
                catalog = build_control_plane_catalog(index)

        self.assertIn("ColorOS_16.0.10", catalog["modVersions"])
        self.assertIn("WK_Manager", catalog["modsByVersion"]["ColorOS_16.0.10"])

        access = TelegramAccessStore(path / "access.json", admin_ids={42})
        store = InMemoryJobStore()
        controller = TelegramBotController(
            access=access,
            orchestrator=HybridOrchestrator(store=store, workspace_root=path / "jobs"),
            catalog_provider=lambda: catalog,
            diagnostics_provider=lambda: {},
            ui_state=TelegramUIStateStore(path / "ui.json"),
        )
        devices = controller._devices()
        self.assertTrue(any(product == "PKG110" for product, _name in devices))
        controller.ui_state.set_session(42, {
            "step": "mods",
            "mod_version": "ColorOS_16.0.10",
            "preset": "plus",
        })
        picker = controller._start_mod_picker(
            42,
            "vi",
            controller.ui_state.session(42),
        )
        self.assertIn("WK_Manager", picker.text)

    def test_runtime_uses_the_same_content_root_as_the_bot_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            content = path / "installed-content"
            content.mkdir()
            index = path / "index.json"
            index.write_text('{"schemaVersion":1,"packs":[]}', encoding="utf-8")
            store = InMemoryJobStore()
            runtime = HybridRuntime(
                orchestrator=HybridOrchestrator(store=store, workspace_root=path / "orchestrator"),
                store=store,
                workspace_root=path / "jobs",
                data_root=path / "data",
                content_root=content,
                content_index=index,
            )

            with patch("wukong.runtime.LocalJobExecutor") as executor:
                runtime._execute_local("job-id")

        self.assertEqual(content.resolve(), executor.call_args.kwargs["content_root"])
        self.assertEqual(index.resolve(), executor.call_args.kwargs["content_index"])

    def test_runtime_uses_gh_cli_auth_when_dedicated_token_is_missing(self) -> None:
        with patch.dict(os.environ, {
            "WUKONG_GITHUB_TOKEN": "",
            "GH_TOKEN": "",
            "GITHUB_TOKEN": "",
        }, clear=False), patch("wukong.runtime.shutil.which", return_value="gh"), patch(
            "wukong.runtime.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "token-from-keyring\n"

            token = HybridRuntime._github_token()

        self.assertEqual("token-from-keyring", token)
        self.assertEqual(["gh", "auth", "token"], run.call_args.args[0])

    def test_dispatched_job_stays_queued_when_run_lookup_temporarily_fails(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = InMemoryJobStore()
        orchestrator = HybridOrchestrator(
            store=store,
            workspace_root=root / "jobs",
            inventory_provider=lambda: RunnerInventory(False),
            access_validator=lambda _recipe, _identity: None,
        )
        source = "https://downloads.example/rom.zip"
        recipe = BuildRecipe.from_dict({
            "schemaVersion": 1,
            "task": "build",
            "device": "PKG110",
            "source": {"kind": "https", "uri": source},
            "execution": {"target": "github-auto"},
            "storage": {"remote": "wukong-gdrive"},
        })
        job = orchestrator.submit(recipe, Identity("telegram", "42", "user"))
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        runtime.rclone_config = root / "rclone.conf"
        runtime.rclone_config.write_text("[wukong-gdrive]\n", encoding="utf-8")
        storage = Mock()
        storage.copy_file.return_value = "wukong-gdrive:WukongROM/recipes/job.json"
        github = Mock()
        github.find_run.side_effect = RuntimeError("temporary socket exhaustion")
        cloud_sync = Mock()

        with patch.dict(os.environ, {
            "WUKONG_GITHUB_TOKEN": "test-token",
            "WUKONG_GITHUB_REPOSITORY": "owner/repository",
        }, clear=False), patch("wukong.runtime.RcloneStorageAdapter", return_value=storage), patch(
            "wukong.runtime.GitHubActionsAdapter", return_value=github
        ), patch("wukong.runtime.CloudJobSync", return_value=cloud_sync), patch(
            "wukong.runtime.threading.Thread"
        ) as thread:
            runtime._dispatch_github(job.job_id)

        refreshed = store.get(job.job_id)
        self.assertIsNotNone(refreshed)
        self.assertEqual(JobStatus.QUEUED, refreshed.status)
        self.assertEqual("github-actions", refreshed.stage)
        self.assertIsNone(refreshed.external_run_id)
        github.dispatch.assert_called_once()
        thread.return_value.start.assert_called_once()
        warnings = [event for event in store.events(job.job_id) if event.type == "warning"]
        self.assertEqual(1, len(warnings))
        self.assertIn("run ID is not available yet", str(warnings[0].payload.get("warning")))

    def test_runtime_resumes_cloud_watcher_after_daemon_restart(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = InMemoryJobStore()
        orchestrator = HybridOrchestrator(
            store=store,
            workspace_root=root / "jobs",
            inventory_provider=lambda: RunnerInventory(False),
            access_validator=lambda _recipe, _identity: None,
        )
        recipe = BuildRecipe.from_dict({
            "schemaVersion": 1,
            "task": "build",
            "device": "PKG110",
            "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
            "execution": {"target": "github-auto"},
            "storage": {"remote": "wukong-gdrive"},
        })
        job = orchestrator.submit(recipe, Identity("telegram", "42", "user"))
        store.update(job.job_id, status=JobStatus.RUNNING, stage="unpack_partitions")
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        runtime.rclone_config = root / "rclone.conf"
        runtime.rclone_config.write_text("[wukong-gdrive]\n", encoding="utf-8")

        with patch("wukong.runtime.RcloneStorageAdapter") as storage, patch(
            "wukong.runtime.threading.Thread"
        ) as thread:
            resumed = runtime.resume_cloud_watchers()

        self.assertEqual(1, resumed)
        storage.assert_called_once_with(
            remote="wukong-gdrive", config_path=runtime.rclone_config
        )
        self.assertEqual(job.job_id, thread.call_args.kwargs["args"][0])
        thread.return_value.start.assert_called_once()

    def test_runtime_does_not_resume_stale_cloud_watcher(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = InMemoryJobStore()
        orchestrator = HybridOrchestrator(
            store=store,
            workspace_root=root / "jobs",
            inventory_provider=lambda: RunnerInventory(False),
            access_validator=lambda _recipe, _identity: None,
        )
        recipe = BuildRecipe.from_dict({
            "schemaVersion": 1,
            "task": "build",
            "device": "PKG110",
            "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
            "execution": {"target": "github-auto"},
        })
        job = orchestrator.submit(recipe, Identity("telegram", "42", "user"))
        stale = datetime.now(timezone.utc) - timedelta(hours=13)
        store.update(job.job_id, status=JobStatus.RUNNING, created_at=stale.isoformat())
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        runtime.rclone_config = root / "rclone.conf"

        with patch("wukong.runtime.threading.Thread") as thread:
            resumed = runtime.resume_cloud_watchers()

        self.assertEqual(0, resumed)
        thread.assert_not_called()

    def test_free_control_plane_disables_background_drive_watchers(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = InMemoryJobStore()
        orchestrator = HybridOrchestrator(
            store=store,
            workspace_root=root / "jobs",
            inventory_provider=lambda: RunnerInventory(False),
            access_validator=lambda _recipe, _identity: None,
        )
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        runtime.rclone_config = root / "rclone.conf"

        with patch.dict(
            os.environ,
            {"WUKONG_CONTROL_PLANE_BACKGROUND_WATCHERS": "false"},
        ):
            runtime = HybridRuntime(
                orchestrator=orchestrator,
                store=store,
                workspace_root=root / "runtime",
                data_root=root / "data",
            )

        self.assertFalse(runtime.cloud_watchers_enabled)
        self.assertEqual(0, runtime.resume_cloud_watchers())

    def test_registers_commands_and_handles_callback_queries(self) -> None:
        controller = Mock()
        controller.command_sets.return_value = {
            "vi": [{"command": "start", "description": "Mở menu"}],
            "en": [{"command": "start", "description": "Open menu"}],
        }
        controller.handle_callback.return_value = BotResponse(
            "Đã đổi", {"inline_keyboard": [[{"text": "Menu", "callback_data": "v1:menu"}]]}
        )
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.register_commands()
        daemon.process_update(
            {
                "update_id": 7,
                "callback_query": {
                    "id": "callback-1",
                    "from": {"id": 42},
                    "message": {"message_id": 99, "chat": {"id": 100}},
                    "data": "v1:lang:en",
                },
            }
        )

        endpoints = [call.args[0] for call in http.post.call_args_list]
        self.assertTrue(any(value.endswith("/setMyCommands") for value in endpoints))
        self.assertTrue(any(value.endswith("/answerCallbackQuery") for value in endpoints))
        self.assertTrue(any(value.endswith("/editMessageText") for value in endpoints))

    def test_configures_https_webhook_with_secret_and_single_connection(self) -> None:
        controller = Mock()
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"ok": True}
        http = Mock()
        http.post.return_value = success
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.configure_webhook("https://mini-api.example.com/", "stable-secret")

        endpoint = http.post.call_args.args[0]
        payload = http.post.call_args.kwargs["json"]
        self.assertTrue(endpoint.endswith("/setWebhook"))
        self.assertEqual("https://mini-api.example.com/telegram/webhook", payload["url"])
        self.assertEqual("stable-secret", payload["secret_token"])
        self.assertEqual(1, payload["max_connections"])

    def test_processes_telegram_web_app_data(self) -> None:
        controller = Mock()
        controller.handle_web_app_data.return_value = BotResponse("Created")
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.process_update({
            "message": {
                "from": {"id": 42},
                "chat": {"id": 100},
                "web_app_data": {"data": '{"version":1,"action":"jobs"}'},
            }
        })

        controller.handle_web_app_data.assert_called_once_with(
            42, '{"version":1,"action":"jobs"}'
        )
        self.assertTrue(http.post.call_args.args[0].endswith("/sendMessage"))

    def test_source_probe_does_not_block_long_polling_loop(self) -> None:
        started = threading.Event()
        release = threading.Event()
        controller = Mock()

        def probe(_user_id, _raw_data):
            started.set()
            release.wait(2)
            return BotResponse("Detected")

        controller.handle_web_app_data.side_effect = probe
        http = Mock()
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.post.return_value.raise_for_status.return_value = None
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
        update = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": 100},
                "web_app_data": {"data": '{"version":1,"action":"probe_source","uri":"https://example.com/rom.zip"}'},
            }
        }

        before = time.monotonic()
        with patch("wukong.telegram_bot.requests.Session", return_value=session):
            daemon.process_update(update)
            elapsed = time.monotonic() - before
            self.assertTrue(started.wait(1))
            self.assertLess(elapsed, 0.2)
            release.set()
            for _ in range(50):
                if session.post.called:
                    break
                time.sleep(0.01)

        self.assertTrue(session.post.called)

    def test_reply_keyboard_callback_is_sent_as_a_new_message(self) -> None:
        controller = Mock()
        controller.handle_callback.return_value = BotResponse(
            "Open app",
            {"keyboard": [[{"text": "Open", "web_app": {"url": "https://example.com"}}]]},
        )
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.process_update({
            "callback_query": {
                "id": "callback-app",
                "from": {"id": 42},
                "message": {"message_id": 99, "chat": {"id": 100}},
                "data": "v1:app",
            }
        })

        endpoints = [call.args[0] for call in http.post.call_args_list]
        self.assertTrue(any(value.endswith("/sendMessage") for value in endpoints))
        self.assertFalse(any(value.endswith("/editMessageText") for value in endpoints))

    def test_callback_edit_failure_falls_back_to_new_message(self) -> None:
        controller = Mock()
        controller.handle_callback.return_value = BotResponse(
            "Recovered", {"inline_keyboard": [[{"text": "Menu", "callback_data": "v1:menu"}]]}
        )
        success = Mock()
        success.raise_for_status.return_value = None
        failed = Mock()
        failed.raise_for_status.side_effect = requests.RequestException("not editable")

        def fake_post(endpoint, **_kwargs):
            return failed if endpoint.endswith("/editMessageText") else success

        http = Mock()
        http.post.side_effect = fake_post
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
        daemon.process_update(
            {
                "callback_query": {
                    "id": "callback-1",
                    "from": {"id": 42},
                    "message": {"message_id": 99, "chat": {"id": 100}},
                    "data": "v1:menu",
                }
            }
        )

        endpoints = [call.args[0] for call in http.post.call_args_list]
        self.assertTrue(any(value.endswith("/sendMessage") for value in endpoints))


if __name__ == "__main__":
    unittest.main()

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
from urllib.parse import parse_qs, urlsplit

import requests

from wukong.models import ArtifactRecord, BuildRecipe, Identity, JobStatus, RecipeValidationError
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
from wukong.telegram_mini_api import TelegramMiniAppSessionStore, validate_telegram_launch_token
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
        self.sessions = TelegramMiniAppSessionStore()
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
                "modReleaseVersions": {"ColorOS_16.0.8": "Stable 4"},
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
            session_store=self.sessions,
            web_app_url=" ",
            allow_chat_build=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_start_routes_new_builds_to_the_mini_app(self) -> None:
        self.controller.web_app_url = "https://wukong-rom-studio.vercel.app/"

        response = self.controller.handle_ui(42, "/start")

        self.assertIsInstance(response, BotResponse)
        self.assertIn("Mini App", response.text)
        buttons = [
            button
            for row in response.reply_markup["inline_keyboard"]
            for button in row
        ]
        labels = [button["text"] for button in buttons]
        self.assertNotIn("Tạo bản build", labels)
        self.assertFalse(any(button.get("callback_data") == "v1:new" for button in buttons))
        self.assertEqual(
            "https://wukong-rom-studio.vercel.app/",
            next(button for button in buttons if "web_app" in button)["web_app"]["url"],
        )
        self.assertIn("Công việc của tôi", labels)
        self.assertIn("English", labels)

    def test_pending_start_records_profile_and_asks_user_to_wait(self) -> None:
        daemon = TelegramLongPollingDaemon("123:test", self.controller)
        daemon._observe_sender({
            "id": 77,
            "first_name": "Pending",
            "last_name": "User",
            "username": "pending_user",
            "language_code": "vi",
        })

        response = self.controller.handle_ui(77, "/start")
        profile = self.access.profile(77)

        self.assertIsNotNone(profile)
        self.assertEqual("Pending User", profile["displayName"])
        self.assertEqual("pending_user", profile["username"])
        self.assertIn("chờ quản trị viên duyệt", response.text.casefold())
        self.assertNotIn("gửi telegram user id", response.text.casefold())

    def test_account_command_shows_build_allowance_and_usage(self) -> None:
        response = self.controller.handle_ui(42, "/account")

        self.assertIn("Lượt build còn lại: 1", response.text)
        self.assertIn("Tổng job: 0", response.text)
        self.assertIn("Lượt build đã dùng: 0", response.text)

    def test_new_command_opens_the_mini_app_instead_of_the_chat_wizard(self) -> None:
        self.controller.web_app_url = "https://wukong-rom-studio.vercel.app/"

        response = self.controller.handle_ui(42, "/new")

        self.assertIn("Mini App", response.text)
        self.assertEqual(
            self.controller.web_app_url,
            response.reply_markup["inline_keyboard"][0][0]["web_app"]["url"],
        )
        self.assertFalse(self.controller.ui_state.session(42))

    def test_bot_command_menu_does_not_advertise_chat_build(self) -> None:
        self.controller.web_app_url = "https://wukong-rom-studio.vercel.app/"

        commands = self.controller.command_sets()

        self.assertNotIn("new", [item["command"] for item in commands["vi"]])
        self.assertNotIn("new", [item["command"] for item in commands["en"]])

    def test_submit_command_does_not_create_a_chat_build_when_mini_app_is_configured(self) -> None:
        self.controller.web_app_url = "https://wukong-rom-studio.vercel.app/"
        recipe = {
            "task": "build",
            "device": "PKG110",
            "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
            "execution": {"target": "github-auto"},
        }

        response = self.controller.handle_ui(42, f"/submit {json.dumps(recipe)}")

        self.assertIn("Mini App", response.text)
        self.assertEqual(
            self.controller.web_app_url,
            response.reply_markup["inline_keyboard"][0][0]["web_app"]["url"],
        )
        self.assertEqual([], self.orchestrator.list(Identity("telegram", "42", "user")))

    def test_chat_build_is_disabled_by_default_without_a_mini_app_url(self) -> None:
        self.controller.web_app_url = ""
        self.controller.allow_chat_build = False

        response = self.controller.handle_ui(42, "/new")

        self.assertIn("URL Mini App chưa được cấu hình", response.text)
        self.assertFalse(self.controller.ui_state.session(42))

    def test_disabled_chat_build_discards_persisted_wizard_callbacks(self) -> None:
        self.controller.web_app_url = "https://wukong-rom-studio.vercel.app/"
        self.controller.allow_chat_build = False
        self.controller.ui_state.set_session(42, {"step": "confirm", "task": "build"})

        response = self.controller.handle_callback(42, "v1:confirm")

        self.assertIn("Mini App", response.text)
        self.assertFalse(self.controller.ui_state.session(42))
        self.assertEqual([], self.orchestrator.list(Identity("telegram", "42", "user")))

    def test_main_menu_exposes_configured_telegram_mini_app(self) -> None:
        self.controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"

        response = self.controller.handle_ui(42, "/start")

        buttons = [button for row in response.reply_markup["inline_keyboard"] for button in row]
        app_button = next(button for button in buttons if "Mini App" in button["text"])
        self.assertEqual(
            app_button["web_app"]["url"],
            "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/",
        )
        self.assertNotIn("callback_data", app_button)

    def test_app_command_uses_inline_web_app_transport_required_for_init_data(self) -> None:
        self.controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"

        response = self.controller.handle_ui(42, "/app")

        self.assertIn("inline_keyboard", response.reply_markup)
        self.assertNotIn("keyboard", response.reply_markup)
        app_button = response.reply_markup["inline_keyboard"][0][0]
        self.assertEqual(self.controller.web_app_url, app_button["web_app"]["url"])

    def test_pair_start_confirms_static_mini_app_session(self) -> None:
        self.controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"
        pairing = self.sessions.begin("WK_build_bot")

        response = self.controller.handle_ui(42, f"/start pair_{pairing['pairId']}")

        self.assertIn("Đã xác nhận tài khoản", response.text)
        token = self.sessions.launch_token(pairing["pairId"], pairing["pairSecret"], "test-token")
        self.assertEqual(42, validate_telegram_launch_token(token, "test-token"))

    def test_plain_rom_url_is_saved_for_the_mini_app_paste_fallback(self) -> None:
        uri = "https://component-ota-cn.allawntech.com/downloadCheck?c=fixture&p=signed"

        response = self.controller.handle_ui(42, uri)

        self.assertIn("Đã lưu link ROM", response.text)
        self.assertEqual(uri, self.sessions.source_draft(42))

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

    def test_text_job_commands_hide_internal_github_identity(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                "execution": {"target": "github-auto"},
            }
        )
        identity = Identity("telegram", "42", "user")
        job = self.orchestrator.submit(recipe, identity)
        internal_url = (
            "https://github.com/luukhanh24/"
            "Wukong-ROM-Studio-Hybrid/actions/runs/123"
        )
        self.store.update(job.job_id, external_run_id=123, error=f"Failed: {internal_url}")
        self.store.append_event(
            job.job_id,
            "github_run",
            runId=123,
            repository="luukhanh24/Wukong-ROM-Studio-Hybrid",
            url=internal_url,
        )

        output = "\n".join(
            [
                self.controller.handle(42, "/jobs"),
                self.controller.handle(42, f"/job {job.job_id}"),
                self.controller.handle(42, f"/events {job.job_id}"),
            ]
        ).casefold()

        self.assertNotIn("luukhanh24", output)
        self.assertNotIn("github.com", output)
        self.assertNotIn("external_run_id", output)
        self.assertNotIn('"runid"', output)

    def test_artifact_command_uses_each_original_cloud_url(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                "execution": {"target": "github-auto"},
            }
        )
        job = self.orchestrator.submit(recipe, Identity("telegram", "42", "user"))
        self.store.update(
            job.job_id,
            status=JobStatus.SUCCEEDED,
            artifacts=[
                ArtifactRecord(
                    "Wukong_Lite.zip",
                    "drive:lite.zip",
                    "a" * 64,
                    1024,
                    "https://drive.google.com/open?id=lite",
                ),
                ArtifactRecord(
                    "Wukong_Plus.zip",
                    "drive:plus.zip",
                    "b" * 64,
                    2048,
                    "https://drive.google.com/open?id=plus",
                ),
            ],
        )

        output = self.controller.handle(42, f"/artifacts {job.job_id}")

        self.assertIn("https://drive.google.com/open?id=lite", output)
        self.assertIn("https://drive.google.com/open?id=plus", output)
        self.assertNotIn("onrender.com", output)

    def test_artifact_without_cloud_url_does_not_borrow_another_artifact_link(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "task": "build",
                "device": "PKG110",
                "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                "execution": {"target": "github-auto"},
            }
        )
        job = self.orchestrator.submit(recipe, Identity("telegram", "42", "user"))
        self.store.update(
            job.job_id,
            status=JobStatus.SUCCEEDED,
            artifacts=[
                ArtifactRecord(
                    "Wukong_Lite.zip",
                    "drive:lite.zip",
                    "a" * 64,
                    1024,
                    "https://drive.google.com/open?id=lite",
                ),
                ArtifactRecord("Wukong_Plus.zip", "drive:plus.zip", "b" * 64, 2048),
            ],
        )
        self.controller.artifact_download_url_provider = (
            lambda _manifest: "https://drive.google.com/open?id=lite"
        )

        output = self.controller.handle(42, f"/artifacts {job.job_id}")

        self.assertEqual(1, output.count("https://drive.google.com/open?id=lite"))

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
        self.assertIn("Open the Mini App", response.text)

        restarted = TelegramUIStateStore(self.root / "telegram-ui-state.json")
        self.assertEqual("en", restarted.language("42"))
        menu = self.controller.handle_ui(42, "/start")
        labels = [
            button["text"]
            for row in menu.reply_markup["inline_keyboard"]
            for button in row
        ]
        self.assertIn("My jobs", labels)

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
        self.assertEqual("Stable 4", recipe.build.mod_release_version)
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
            self.assertEqual({"42", "43", "1678823419"}, _configured_admin_ids())

        with patch.dict("telegram_bot_daemon.os.environ", {}, clear=True):
            self.assertEqual({"1678823419"}, _configured_admin_ids())

    def test_reuses_one_http_session_for_telegram_requests(self) -> None:
        controller = Mock()
        controller.command_sets.return_value = {"vi": [], "en": []}
        controller.web_app_url = ""
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success

        with patch("wukong.telegram_bot.requests.Session", return_value=http) as session:
            daemon = TelegramLongPollingDaemon("test-token", controller)
            daemon.register_commands()

        session.assert_called_once_with()
        self.assertEqual(2, http.post.call_count)

    def test_register_commands_configures_authenticated_mini_app_menu_button(self) -> None:
        controller = Mock()
        controller.command_sets.return_value = {"vi": [], "en": []}
        controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.register_commands()

        menu_call = next(
            call for call in http.post.call_args_list if call.args[0].endswith("/setChatMenuButton")
        )
        self.assertEqual(
            {
                "menu_button": {
                    "type": "web_app",
                    "text": "Wukong Studio",
                    "web_app": {"url": controller.web_app_url},
                }
            },
            menu_call.kwargs["json"],
        )

    def test_register_commands_refreshes_existing_private_chat_menus(self) -> None:
        controller = Mock()
        controller.command_sets.return_value = {"vi": [], "en": []}
        controller.web_app_url = "https://wukong-rom-studio.vercel.app/"
        controller.access.subjects.return_value = ("42", "43")
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"ok": True, "result": True}
        cleanup_sent = Mock()
        cleanup_sent.raise_for_status.return_value = None
        cleanup_sent.json.return_value = {"ok": True, "result": {"message_id": 99}}
        http = Mock()

        def fake_post(endpoint, **kwargs):
            if (
                endpoint.endswith("/sendMessage")
                and kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
            ):
                return cleanup_sent
            return success

        http.post.side_effect = fake_post
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.register_commands()

        menu_calls = [
            call.kwargs["json"]
            for call in http.post.call_args_list
            if call.args[0].endswith("/setChatMenuButton")
        ]
        self.assertEqual(3, len(menu_calls))
        self.assertNotIn("chat_id", menu_calls[0])
        self.assertEqual(["42", "43"], [payload["chat_id"] for payload in menu_calls[1:]])
        for payload in menu_calls[1:]:
            url = payload["menu_button"]["web_app"]["url"]
            self.assertEqual("wukong-rom-studio.vercel.app", urlsplit(url).hostname)
            self.assertIn("wkLaunch", parse_qs(urlsplit(url).query))
        cleanup_calls = [
            call.kwargs["json"]
            for call in http.post.call_args_list
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
        ]
        self.assertEqual(["42", "43"], [str(payload["chat_id"]) for payload in cleanup_calls])
        self.assertEqual(
            2,
            len([
                call
                for call in http.post.call_args_list
                if call.args[0].endswith("/deleteMessage")
            ]),
        )

    def test_start_personalizes_mini_app_button_and_chat_menu(self) -> None:
        controller = Mock()
        controller.web_app_url = "https://luukhanh24.github.io/Wukong-ROM-Studio-Hybrid/"
        controller.handle_ui.return_value = BotResponse(
            "Open app",
            {"inline_keyboard": [[{
                "text": "Open",
                "web_app": {"url": controller.web_app_url},
            }]]},
        )
        success = Mock()
        success.raise_for_status.return_value = None
        http = Mock()
        http.post.return_value = success
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)

        daemon.process_update({
            "message": {
                "from": {"id": 42},
                "chat": {"id": 42},
                "text": "/start",
            }
        })

        calls = [call for call in http.post.call_args_list if call.args[0].endswith(("/sendMessage", "/setChatMenuButton"))]
        sent = next(
            call.kwargs["json"]
            for call in calls
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("reply_markup") != {"remove_keyboard": True}
        )
        menu = next(call.kwargs["json"] for call in calls if call.args[0].endswith("/setChatMenuButton"))
        button_url = sent["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"]
        menu_url = menu["menu_button"]["web_app"]["url"]
        self.assertEqual(42, menu["chat_id"])
        self.assertEqual(button_url, menu_url)
        launch_token = parse_qs(urlsplit(button_url).query)["wkLaunch"][0]
        self.assertEqual(42, validate_telegram_launch_token(launch_token, "test-token"))

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

    def test_actions_bearer_accepts_final_callback_while_run_is_in_progress(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = InMemoryJobStore()
        orchestrator = HybridOrchestrator(store=store, workspace_root=root / "jobs")
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        github = Mock()
        github.run_state.return_value = {
            "status": "in_progress",
            "conclusion": None,
            "url": "https://github.example/actions/runs/321",
        }

        with patch.dict(
            os.environ,
            {"WUKONG_GITHUB_REPOSITORY": "owner/repository"},
            clear=False,
        ), patch("wukong.runtime.GitHubActionsAdapter", return_value=github):
            conclusion = runtime.verify_actions_bearer(
                "github-actions-token-1234567890",
                321,
                "success",
            )

        self.assertEqual("success", conclusion)
        github.run_state.assert_called_once_with(321)

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

    def test_refresh_reconciles_pre_executor_github_failure(self) -> None:
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
        store.update(job.job_id, status=JobStatus.QUEUED, stage="github-actions")
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        runtime.rclone_config = root / "rclone.conf"
        runtime.rclone_config.write_text("[wukong-gdrive]\n", encoding="utf-8")
        storage = Mock()
        sync = Mock()
        sync.pull.return_value = store.get(job.job_id)
        github = Mock()
        github.find_run.return_value = 32550269975
        github.run_state.return_value = {
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.example/actions/runs/32550269975",
        }

        with patch.dict(os.environ, {
            "WUKONG_GITHUB_TOKEN": "test-token",
            "WUKONG_GITHUB_REPOSITORY": "owner/repository",
        }, clear=False), patch("wukong.runtime.RcloneStorageAdapter", return_value=storage), patch(
            "wukong.runtime.CloudJobSync", return_value=sync
        ), patch("wukong.runtime.GitHubActionsAdapter", return_value=github):
            refreshed = runtime.refresh(store.get(job.job_id))

        self.assertEqual(JobStatus.FAILED, refreshed.status)
        self.assertEqual("github-actions-failed", refreshed.stage)
        self.assertEqual(32550269975, refreshed.external_run_id)
        self.assertIn("GitHub Actions failed", refreshed.error)
        sync.push.assert_called_once_with(job.job_id)

    def test_refresh_marks_active_github_run_running_without_blocking_on_drive(self) -> None:
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
        store.update(
            job.job_id,
            status=JobStatus.QUEUED,
            stage="github-actions",
            external_run_id=123,
        )
        runtime = HybridRuntime(
            orchestrator=orchestrator,
            store=store,
            workspace_root=root / "runtime",
            data_root=root / "data",
        )
        runtime.rclone_config = root / "rclone.conf"
        runtime.rclone_config.write_text("[wukong-gdrive]\n", encoding="utf-8")
        runtime.cloud_watchers_enabled = False
        sync = Mock()
        github = Mock()
        github.run_state.return_value = {
            "status": "in_progress",
            "conclusion": None,
            "url": "https://github.example/actions/runs/123",
        }

        with patch.dict(os.environ, {
            "WUKONG_GITHUB_TOKEN": "test-token",
            "WUKONG_GITHUB_REPOSITORY": "owner/repository",
        }, clear=False), patch("wukong.runtime.CloudJobSync", return_value=sync), patch(
            "wukong.runtime.GitHubActionsAdapter", return_value=github
        ), patch("wukong.runtime.threading.Thread") as thread:
            refreshed = runtime.refresh(store.get(job.job_id))

        sync.pull.assert_not_called()
        thread.return_value.start.assert_called_once()
        self.assertEqual(JobStatus.RUNNING, refreshed.status)
        self.assertEqual("github-actions-running", refreshed.stage)
        self.assertGreater(refreshed.progress, 0)

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
        callback_index = next(
            index
            for index, endpoint in enumerate(endpoints)
            if endpoint.endswith("/answerCallbackQuery")
        )
        cleanup_index = next(
            index
            for index, call in enumerate(http.post.call_args_list)
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
        )
        self.assertLess(callback_index, cleanup_index)

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
        controller.handle_web_app_data.return_value = BotResponse(
            "Created",
            {
                "keyboard": [[{"text": "Legacy"}]],
                "resize_keyboard": True,
                "selective": True,
                "input_field_placeholder": "Choose an action",
            },
        )
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
        cleanup = next(
            call.kwargs["json"]
            for call in http.post.call_args_list
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
        )
        self.assertEqual(100, cleanup["chat_id"])
        response = next(
            call.kwargs["json"]
            for call in http.post.call_args_list
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("text") == "Created"
        )
        self.assertNotIn("reply_markup", response)

    def test_source_probe_does_not_block_long_polling_loop(self) -> None:
        started = threading.Event()
        release = threading.Event()
        controller = Mock()

        def probe(_user_id, _raw_data):
            started.set()
            release.wait(2)
            return BotResponse(
                "Detected",
                {
                    "keyboard": [[{"text": "Legacy"}]],
                    "selective": True,
                    "input_field_placeholder": "Choose an action",
                },
            )

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
        self.assertNotIn("reply_markup", session.post.call_args.kwargs["json"])

    def test_reply_keyboard_callback_is_removed_instead_of_recreated(self) -> None:
        controller = Mock()
        controller.web_app_url = ""
        controller.handle_callback.return_value = BotResponse(
            "Open app",
            {
                "keyboard": [[{"text": "Open", "web_app": {"url": "https://example.com"}}]],
                "resize_keyboard": True,
                "selective": True,
                "input_field_placeholder": "Open Wukong Studio",
            },
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
                "message": {"message_id": 99, "chat": {"id": 42}},
                "data": "v1:app",
            }
        })

        edited = next(
            call.kwargs["json"]
            for call in http.post.call_args_list
            if call.args[0].endswith("/editMessageText")
        )
        self.assertNotIn("reply_markup", edited)
        cleanup = next(
            call.kwargs["json"]
            for call in http.post.call_args_list
            if call.args[0].endswith("/sendMessage")
        )
        self.assertEqual({"remove_keyboard": True}, cleanup["reply_markup"])

    def test_reply_keyboard_cleanup_retries_delete_without_sending_another_helper(self) -> None:
        controller = Mock()
        controller.web_app_url = ""
        controller.handle_ui.return_value = BotResponse("Ready")
        cleanup_sent = Mock()
        cleanup_sent.raise_for_status.return_value = None
        cleanup_sent.json.return_value = {"ok": True, "result": {"message_id": 77}}
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"ok": True, "result": True}
        delete_failed = Mock()
        delete_failed.status_code = 429
        delete_failed.json.return_value = {
            "ok": False,
            "description": "Too Many Requests: retry after 1",
        }
        delete_failed.raise_for_status.side_effect = requests.HTTPError(
            "rate limited",
            response=delete_failed,
        )
        delete_attempts = 0

        def fake_post(endpoint, **kwargs):
            nonlocal delete_attempts
            if endpoint.endswith("/deleteMessage"):
                delete_attempts += 1
                return delete_failed if delete_attempts == 1 else success
            if (
                endpoint.endswith("/sendMessage")
                and kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
            ):
                return cleanup_sent
            return success

        http = Mock()
        http.post.side_effect = fake_post
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
        update = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": -100123},
                "text": "/start",
            }
        }

        daemon.process_update(update)
        daemon.process_update(update)

        cleanup_calls = [
            call
            for call in http.post.call_args_list
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
        ]
        delete_calls = [
            call
            for call in http.post.call_args_list
            if call.args[0].endswith("/deleteMessage")
        ]
        self.assertEqual(1, len(cleanup_calls))
        self.assertEqual(2, len(delete_calls))
        self.assertEqual({"chat_id": -100123, "message_id": 77}, delete_calls[-1].kwargs["json"])
        self.assertNotIn("-100123", daemon._reply_keyboard_cleanup_messages)
        self.assertIn("-100123", daemon._reply_keyboard_removed_chats)

    def test_reply_keyboard_cleanup_retries_in_background_without_another_update(self) -> None:
        controller = Mock()
        controller.web_app_url = ""
        controller.handle_ui.return_value = BotResponse("Ready")
        cleanup_sent = Mock()
        cleanup_sent.raise_for_status.return_value = None
        cleanup_sent.json.return_value = {"ok": True, "result": {"message_id": 77}}
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"ok": True, "result": True}
        delete_failed = Mock()
        delete_failed.raise_for_status.side_effect = requests.RequestException("temporary")
        delete_attempts = 0

        def fake_post(endpoint, **kwargs):
            nonlocal delete_attempts
            if endpoint.endswith("/deleteMessage"):
                delete_attempts += 1
                return delete_failed if delete_attempts == 1 else success
            if (
                endpoint.endswith("/sendMessage")
                and kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
            ):
                return cleanup_sent
            return success

        http = Mock()
        http.post.side_effect = fake_post
        timer = Mock()
        with patch("wukong.telegram_bot.threading.Timer", return_value=timer) as timer_factory:
            daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
            daemon.process_update({
                "message": {
                    "from": {"id": 42},
                    "chat": {"id": 42},
                    "text": "/start",
                }
            })

            timer.start.assert_called_once_with()
            retry = timer_factory.call_args.args[1]
            retry(*timer_factory.call_args.kwargs["args"])

        self.assertEqual(2, delete_attempts)
        self.assertNotIn("42", daemon._reply_keyboard_cleanup_messages)
        self.assertIn("42", daemon._reply_keyboard_removed_chats)

    def test_reply_keyboard_cleanup_retry_exhaustion_does_not_cache_false_success(self) -> None:
        controller = Mock()
        controller.web_app_url = ""
        controller.handle_ui.return_value = BotResponse("Ready")
        failed = Mock()
        failed.raise_for_status.side_effect = requests.RequestException("offline")
        success = Mock()
        success.raise_for_status.return_value = None

        def fake_post(endpoint, **kwargs):
            if (
                endpoint.endswith("/sendMessage")
                and kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
            ):
                return failed
            return success

        http = Mock()
        http.post.side_effect = fake_post
        timers = [Mock() for _ in range(5)]
        with patch("wukong.telegram_bot.threading.Timer", side_effect=timers) as timer_factory:
            daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
            daemon.process_update({
                "message": {
                    "from": {"id": 42},
                    "chat": {"id": 42},
                    "text": "/start",
                }
            })
            for _ in range(5):
                timer_call = timer_factory.call_args
                retry = timer_call.args[1]
                retry(*timer_call.kwargs["args"])

        self.assertEqual(5, timer_factory.call_count)
        self.assertNotIn("42", daemon._reply_keyboard_removed_chats)
        self.assertNotIn("42", daemon._reply_keyboard_cleanup_timers)
        self.assertNotIn("42", daemon._reply_keyboard_cleanup_attempts)

    def test_reply_keyboard_cleanup_does_not_cache_semantic_telegram_failure(self) -> None:
        controller = Mock()
        controller.web_app_url = ""
        controller.handle_ui.return_value = BotResponse("Ready")
        rejected = Mock()
        rejected.raise_for_status.return_value = None
        rejected.status_code = 200
        rejected.json.return_value = {
            "ok": False,
            "description": "Bad Request: chat not found",
        }
        success = Mock()
        success.raise_for_status.return_value = None

        def fake_post(endpoint, **kwargs):
            if (
                endpoint.endswith("/sendMessage")
                and kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
            ):
                return rejected
            return success

        http = Mock()
        http.post.side_effect = fake_post
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
        update = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": 42},
                "text": "/start",
            }
        }

        daemon.process_update(update)
        daemon.process_update(update)

        cleanup_calls = [
            call
            for call in http.post.call_args_list
            if call.args[0].endswith("/sendMessage")
            and call.kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
        ]
        self.assertEqual(2, len(cleanup_calls))
        self.assertNotIn("42", daemon._reply_keyboard_removed_chats)

    def test_reply_keyboard_cleanup_treats_missing_helper_as_already_deleted(self) -> None:
        controller = Mock()
        controller.web_app_url = ""
        controller.handle_ui.return_value = BotResponse("Ready")
        cleanup_sent = Mock()
        cleanup_sent.raise_for_status.return_value = None
        cleanup_sent.json.return_value = {"ok": True, "result": {"message_id": 77}}
        missing = Mock()
        missing.status_code = 400
        missing.json.return_value = {
            "ok": False,
            "description": "Bad Request: message to delete not found",
        }
        missing.raise_for_status.side_effect = requests.HTTPError(
            "not found",
            response=missing,
        )
        success = Mock()
        success.raise_for_status.return_value = None

        def fake_post(endpoint, **kwargs):
            if endpoint.endswith("/deleteMessage"):
                return missing
            if (
                endpoint.endswith("/sendMessage")
                and kwargs["json"].get("reply_markup") == {"remove_keyboard": True}
            ):
                return cleanup_sent
            return success

        http = Mock()
        http.post.side_effect = fake_post
        daemon = TelegramLongPollingDaemon("test-token", controller, http=http)
        update = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": 42},
                "text": "/start",
            }
        }

        daemon.process_update(update)
        daemon.process_update(update)

        self.assertEqual(
            1,
            len([
                call
                for call in http.post.call_args_list
                if call.args[0].endswith("/deleteMessage")
            ]),
        )
        self.assertNotIn("42", daemon._reply_keyboard_cleanup_messages)
        self.assertIn("42", daemon._reply_keyboard_removed_chats)

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

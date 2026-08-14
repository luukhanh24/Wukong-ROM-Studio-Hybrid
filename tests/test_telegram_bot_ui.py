from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from wukong.models import BuildRecipe, Identity, JobStatus, RecipeValidationError
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore
from wukong.routing import RunnerInventory
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import (
    BotResponse,
    TelegramBotController,
    TelegramLongPollingDaemon,
    TelegramUIStateStore,
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
                "mods": {"ColorOS_16.0.8": []},
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
        confirmation = self.controller.handle_callback(42, "v1:pre:lite")
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
    def test_registers_commands_and_handles_callback_queries(self) -> None:
        controller = Mock()
        controller.command_sets.return_value = {
            "vi": [{"command": "start", "description": "Mở menu"}],
            "en": [{"command": "start", "description": "Open menu"}],
        }
        controller.handle_callback.return_value = BotResponse(
            "Đã đổi", {"inline_keyboard": [[{"text": "Menu", "callback_data": "v1:menu"}]]}
        )
        daemon = TelegramLongPollingDaemon("test-token", controller)
        success = Mock()
        success.raise_for_status.return_value = None

        with patch("wukong.telegram_bot.requests.post", return_value=success) as post:
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

        endpoints = [call.args[0] for call in post.call_args_list]
        self.assertTrue(any(value.endswith("/setMyCommands") for value in endpoints))
        self.assertTrue(any(value.endswith("/answerCallbackQuery") for value in endpoints))
        self.assertTrue(any(value.endswith("/editMessageText") for value in endpoints))

    def test_callback_edit_failure_falls_back_to_new_message(self) -> None:
        controller = Mock()
        controller.handle_callback.return_value = BotResponse(
            "Recovered", {"inline_keyboard": [[{"text": "Menu", "callback_data": "v1:menu"}]]}
        )
        daemon = TelegramLongPollingDaemon("test-token", controller)
        success = Mock()
        success.raise_for_status.return_value = None
        failed = Mock()
        failed.raise_for_status.side_effect = requests.RequestException("not editable")

        def fake_post(endpoint, **_kwargs):
            return failed if endpoint.endswith("/editMessageText") else success

        with patch("wukong.telegram_bot.requests.post", side_effect=fake_post) as post:
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

        endpoints = [call.args[0] for call in post.call_args_list]
        self.assertTrue(any(value.endswith("/sendMessage") for value in endpoints))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit

from wukong.render_binding import RenderBinding, RenderBindingError, RenderOriginBinder


class RenderOriginBinderTests(unittest.TestCase):
    def binding(self) -> RenderBinding:
        return RenderBinding(
            repository="owner/repository",
            token="github-token-" + "x" * 32,
            api_url="https://wukong-mini-api.onrender.com",
            release_sha="a" * 40,
            mini_app_url="https://app.example.com/",
        )

    def test_binding_accepts_configured_vercel_origin_without_personal_hostname(self) -> None:
        binding = RenderBinding(
            repository="owner/repository",
            token="github-token-" + "x" * 32,
            api_url="https://wukong-mini-api.onrender.com",
            release_sha="a" * 40,
            mini_app_url="https://wukong-rom-studio.vercel.app/",
        )

        self.assertEqual("wukong-rom-studio.vercel.app", urlsplit(binding.mini_app_url).hostname)

    def test_creates_missing_variable_and_dispatches_pages(self) -> None:
        http = Mock()
        http.get.return_value = Mock(status_code=404)
        http.post.side_effect = [Mock(status_code=201), Mock(status_code=204)]

        RenderOriginBinder(self.binding(), http=http).bind_once()

        self.assertIn("/actions/variables", http.post.call_args_list[0].args[0])
        self.assertEqual(
            "https://wukong-mini-api.onrender.com",
            http.post.call_args_list[0].kwargs["json"]["value"],
        )
        self.assertIn("telegram-mini-app-pages.yml/dispatches", http.post.call_args_list[1].args[0])
        self.assertEqual(
            {"ref": "main", "inputs": {"release_sha": self.binding().release_sha}},
            http.post.call_args_list[1].kwargs["json"],
        )

    def test_updates_changed_variable_before_dispatch(self) -> None:
        http = Mock()
        current = Mock(status_code=200)
        current.json.return_value = {"value": "https://old.onrender.com"}
        http.get.return_value = current
        http.patch.return_value = Mock(status_code=204)
        http.post.return_value = Mock(status_code=204)

        RenderOriginBinder(self.binding(), http=http).bind_once()

        http.patch.assert_called_once()
        http.post.assert_called_once()

    def test_unchanged_variable_still_republishes_pages(self) -> None:
        http = Mock()
        current = Mock(status_code=200)
        current.json.return_value = {"value": self.binding().api_url}
        stale_page = Mock(status_code=200, text="old release")
        http.get.side_effect = [current, stale_page]
        http.post.return_value = Mock(status_code=204)

        RenderOriginBinder(self.binding(), http=http).bind_once()

        http.patch.assert_not_called()
        http.post.assert_called_once()

    def test_current_published_page_avoids_duplicate_actions_dispatch(self) -> None:
        http = Mock()
        current = Mock(status_code=200)
        current.json.return_value = {"value": self.binding().api_url}
        page = Mock(
            status_code=200,
            text=(
                self.binding().api_url
                + f'<meta name="wukong-release" content="{self.binding().release_sha}">'
            ),
        )
        http.get.side_effect = [current, page]

        RenderOriginBinder(self.binding(), http=http).bind_once()

        http.patch.assert_not_called()
        http.post.assert_not_called()

    def test_rejects_non_render_origin_and_reports_github_failure(self) -> None:
        with self.assertRaises(ValueError):
            RenderBinding(
                repository="owner/repository",
                token="x" * 32,
                api_url="https://example.com",
                release_sha="a" * 40,
                mini_app_url="https://app.example.com/",
            )
        http = Mock()
        http.get.return_value = Mock(status_code=403)
        with self.assertRaises(RenderBindingError):
            RenderOriginBinder(self.binding(), http=http).bind_once()


if __name__ == "__main__":
    unittest.main()

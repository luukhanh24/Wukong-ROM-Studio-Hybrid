from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.export_mini_app_catalog import export_catalog


ROOT = Path(__file__).resolve().parents[1]


class TelegramMiniAppTests(unittest.TestCase):
    def test_catalog_export_contains_only_ready_github_packs_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            index = base / "index.json"
            devices = base / "devices.json"
            output = base / "site" / "catalog.json"
            index.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "packs": [
                            {
                                "id": "MOD/ColorOS_16.0.9",
                                "target": "MOD/ColorOS_16.0.9",
                                "remote": "drive:MOD/ColorOS_16.0.9",
                                "sizeBytes": 2,
                                "archive": {
                                    "uri": "drive:MOD/ColorOS_16.0.9.tar.zst",
                                    "sha256": "a" * 64,
                                    "md5": "b" * 32,
                                    "sizeBytes": 1,
                                },
                                "files": [
                                    {"path": "Gapps/system/app.apk", "sha256": "c" * 64, "sizeBytes": 1},
                                    {"path": "WK_Manager/system/app.apk", "sha256": "d" * 64, "sizeBytes": 1},
                                ],
                            },
                            {
                                "id": "MOD/not-uploaded",
                                "target": "MOD/not-uploaded",
                                "remote": "drive:MOD/not-uploaded",
                                "sizeBytes": 0,
                                "files": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            devices.write_text(
                '[{"product_name":"PKG110","name":"OnePlus Ace 5"}]',
                encoding="utf-8",
            )

            payload = export_catalog(index, devices, output)

            exported = output.read_text(encoding="utf-8")

        self.assertEqual(["ColorOS_16.0.9"], payload["modVersions"])
        self.assertEqual(["Gapps", "WK_Manager"], payload["modsByVersion"]["ColorOS_16.0.9"])
        self.assertEqual(["Gapps", "WK_Manager"], payload["presetDefaultsByVersion"]["ColorOS_16.0.9"]["both"])
        self.assertIn("sync_configs", [item["id"] for item in payload["pipelineSteps"]])
        self.assertNotIn("sync_metadata", [item["id"] for item in payload["pipelineSteps"]])
        self.assertEqual("PKG110", payload["devices"][0]["product"])
        self.assertTrue(exported.endswith("\n"))

    def test_static_app_exposes_bilingual_build_and_job_contract(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        for element_id in (
            "recipe-form",
            "source-uri",
            "device",
            "execution",
            "mod-version",
            "mod-list",
            "job-id",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("Telegram.WebApp", script)
        self.assertIn('send("submit_recipe"', script)
        self.assertIn("4096", script)
        self.assertIn("catalog.json", script)
        self.assertIn("const translations", script)
        self.assertIn("source_mirror", script)

        exporter = (ROOT / "tools" / "export_mini_app_catalog.py").read_text(encoding="utf-8")
        self.assertNotIn("from studio_core import", exporter)

    def test_mini_app_maps_windows_operating_surfaces_without_saas_chrome(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "telegram_mini_app" / "styles.css").read_text(encoding="utf-8")
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        for surface in ("build", "jobs", "cloud", "catalog", "system"):
            self.assertIn(f'id="{surface}"', html)
            self.assertIn(f'data-nav="{surface}"', html)
        for control in (
            "catalog-search",
            "catalog-version",
            "device-list",
            "catalog-mod-list",
            "default-preset",
            "pipeline-count",
            "mod-search",
            "telegram-auth-state",
        ):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('data-action="cache"', html)
        self.assertIn('data-action="cache_clear"', html)
        self.assertIn("renderCatalog", script)
        self.assertIn('.contents-rail [data-nav]', script)
        self.assertIn("incompleteLabel", script)
        self.assertIn("chooseDeviceHint", script)
        self.assertNotIn("backdrop-filter", styles)
        self.assertNotIn("linear-gradient", styles)
        self.assertIn('"Sora"', styles)
        self.assertIn('"IBM Plex Mono"', styles)
        self.assertIn("--aqua:", styles)
        self.assertIn("--coral:", styles)
        self.assertIn("--shadow-md:", styles)

    def test_smart_source_recognizes_unresolved_ota_without_exposing_signed_url(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        for element_id in ("source-state", "source-facts", "probe-source", "source-provider"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("downloadcheck", script.casefold())
        self.assertIn('send("probe_source"', script)
        self.assertNotIn("resolvedUrl", html + script)
        self.assertNotIn("Signature=signed", html + script)


if __name__ == "__main__":
    unittest.main()

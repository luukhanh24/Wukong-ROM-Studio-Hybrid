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
                            {
                                "id": "STARK/common",
                                "target": "STARK",
                                "remote": "drive:STARK/common",
                                "sizeBytes": 1,
                                "archive": {
                                    "uri": "drive:STARK/common.tar.zst",
                                    "sha256": "e" * 64,
                                    "md5": "f" * 32,
                                    "sizeBytes": 1,
                                },
                                "files": [
                                    {"path": "WK_Installer/system_ext/app.apk", "sha256": "1" * 64, "sizeBytes": 1},
                                ],
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
        self.assertEqual(["Gapps", "WK_Installer", "WK_Manager"], payload["modsByVersion"]["ColorOS_16.0.9"])
        self.assertEqual(["Gapps", "WK_Installer", "WK_Manager"], payload["presetDefaultsByVersion"]["ColorOS_16.0.9"]["both"])
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
            "active-job",
            "job-history",
            "job-history-count",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("Telegram.WebApp", script)
        self.assertIn('apiRequest("/v1/jobs"', script)
        self.assertIn("submitRecipe", script)
        self.assertNotIn('send("submit_recipe"', script)
        self.assertIn("telegramTransportAvailable", script)
        self.assertIn('TelegramApp.platform !== "unknown"', script)
        self.assertNotIn("!TelegramApp.initData", script)
        self.assertIn("keyboardConnected", script)
        self.assertIn("4096", script)
        self.assertIn("sameStringList(paths, state.catalog.defaultDebloatPaths)", script)
        self.assertIn("catalog.json", script)
        self.assertIn("const translations", script)
        self.assertIn("source_mirror", script)
        self.assertIn("loadJobs", script)
        self.assertIn("scheduleJobsPoll", script)
        self.assertIn("renderArtifacts", script)

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
            "cloud-results",
        ):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('data-action="cache"', html)
        self.assertIn('data-action="cache_clear"', html)
        self.assertIn("renderCatalog", script)
        self.assertIn('.contents-rail [data-nav]', script)
        self.assertIn("incompleteLabel", script)
        self.assertIn("chooseDeviceHint", script)
        self.assertIn('class="runtime-strip"', html)
        self.assertIn('class="readiness-checklist"', html)
        self.assertIn("modCategory", script)
        self.assertIn("setDeliveryState", script)
        self.assertIn('apiRequest("/v1/cache"', script)
        self.assertIn('apiRequest("/v1/cache/clear"', script)
        self.assertIn("pipelineRunning", script)
        self.assertIn("runtimeReady", script)
        self.assertIn('className = "mod-group"', script)
        self.assertNotIn('class="mobile-dispatch"', html)
        self.assertNotIn("backdrop-filter", styles)
        self.assertNotIn("linear-gradient", styles)
        self.assertIn('"IBM Plex Sans"', styles)
        self.assertIn('"JetBrains Mono"', styles)
        self.assertIn("--accent:", styles)
        self.assertIn("--success:", styles)
        self.assertIn("--radius-sm: 4px", styles)

    def test_smart_source_recognizes_unresolved_ota_without_exposing_signed_url(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        for element_id in (
            "source-state",
            "source-facts",
            "probe-source",
            "source-provider",
            "source-product-detected",
            "source-android-version",
            "source-security-patch",
            "source-build-date",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("downloadcheck", script.casefold())
        self.assertIn("probeSourceInPlace", script)
        self.assertIn("probeSourceViaBackend", script)
        self.assertIn('name="wukong-mini-api-endpoint"', html)
        self.assertIn("__WUKONG_TELEGRAM_MINI_APP_API_URL__", html)
        self.assertNotIn("fetch(uri", script)
        self.assertNotIn('send("probe_source"', script)
        self.assertNotIn("resolvedUrl", html + script)
        self.assertNotIn("Signature=signed", html + script)
        self.assertIn("matchCatalogDevice", script)
        self.assertIn("result?.productName", script)
        self.assertIn("selectModPackForVersion", script)

    def test_smart_source_uses_server_probe_instead_of_cross_origin_browser_fetch(self) -> None:
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        self.assertIn("probeSourceViaBackend", script)
        self.assertNotIn("fetch(uri", script)

    def test_default_debloat_list_is_embedded_for_recipe_parity(self) -> None:
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")
        config = json.loads((ROOT / "config" / "debloat.json").read_text(encoding="utf-8"))

        self.assertIn("defaultDebloatPaths", script)
        for path in (
            r"my_stock\priv-app\CodeBook",
            r"my_stock\app\AIWriter",
            r"my_stock\app\ColorDirectService",
            r"my_stock\app\AIMemory",
        ):
            self.assertIn(path, config["default"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from tools.export_mini_app_catalog import export_catalog


ROOT = Path(__file__).resolve().parents[1]

OPLUS_TEST_URI = (
    "https://component-ota-cn.allawntech.com/downloadCheck?"
    "c=fixture-component&p=fixture-product&d=fixture-device&g=fixture-group&"
    "id=fixture-build&taste=0&supportDLTaste=0&mode=1&tr=auto&s=fixture-signature"
)

OPLUS_TEST_METADATA = {
    "provider": "oplus",
    "filename": "c42d35ce2a9d460fa61db8a45c9b4db6.zip",
    "resolvedHost": "gauss-compotaauto-c-cn.allawnfs.com",
    "sizeBytes": 8680370027,
    "contentType": "application/zip",
    "lastModified": "Wed, 08 Jul 2026 10:28:55 GMT",
    "md5": "6fb0095cc9c07dbdb74074c87cbb643f",
    "productName": "PKG110",
    "device": "OP5D2BL1",
    "version": "PKG110_16.0.9.400(CN01)",
    "androidVersion": "16",
    "securityPatch": "2026-07-01",
    "buildDate": "2026-07-06 08:51:35",
    "otaType": "AB",
    "deepInspected": True,
    "warning": None,
}


def _chrome_path() -> str | None:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((str(path) for path in candidates if path and Path(path).is_file()), None)


class _MiniAppFixtureHandler(BaseHTTPRequestHandler):
    api_enabled = True

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            origin = f"http://127.0.0.1:{self.server.server_port}" if self.api_enabled else ""
            html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
            html = html.replace("__WUKONG_TELEGRAM_MINI_APP_API_URL__", origin)
            html = html.replace("https://telegram.org/js/telegram-web-app.js", "/telegram-web-app.js")
            self._send(html.encode(), "text/html; charset=utf-8")
            return
        if path == "/telegram-web-app.js":
            source = f"""
window.Telegram = {{ WebApp: {{ initData: 'fixture-init-data', platform: 'android', ready() {{}}, expand() {{}}, isVersionAtLeast() {{ return false; }}, HapticFeedback: {{ notificationOccurred() {{}} }} }} }};
window.addEventListener('load', () => {{
  const fill = () => {{
    const input = document.querySelector('#source-uri');
    const catalogReady = document.querySelector('#device option[value="PKG110"]');
    if (!input || !catalogReady) {{ setTimeout(fill, 50); return; }}
    input.value = {json.dumps(OPLUS_TEST_URI)};
    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  }};
  setTimeout(fill, 50);
}});
"""
            self._send(source.encode(), "application/javascript; charset=utf-8")
            return
        if path == "/styles.css":
            styles = (ROOT / "telegram_mini_app" / "styles.css").read_text(encoding="utf-8")
            styles = styles.replace(styles.splitlines()[0], "")
            self._send(styles.encode(), "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send(
                (ROOT / "telegram_mini_app" / "app.js").read_bytes(),
                "application/javascript; charset=utf-8",
            )
            return
        if path == "/catalog.json":
            catalog = {
                "schemaVersion": 1,
                "devices": [{"product": "PKG110", "name": "OnePlus Ace 5"}],
                "modVersions": ["ColorOS_16.0.9"],
                "modsByVersion": {"ColorOS_16.0.9": ["Gapps", "WK_Manager"]},
                "presetDefaultsByVersion": {
                    "ColorOS_16.0.9": {"lite": [], "plus": ["Gapps"], "both": ["Gapps", "WK_Manager"], "custom": []}
                },
                "pipelineSteps": [],
                "defaultDebloatPaths": [],
            }
            self._send(json.dumps(catalog).encode(), "application/json")
            return
        if path == "/v1/jobs":
            self._send(b'{"jobs":[]}', "application/json")
            return
        self._send(b"not found", "text/plain", 404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if urlsplit(self.path).path == "/v1/sources/probe" and self.api_enabled:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if payload.get("uri") != OPLUS_TEST_URI:
                self._send(b'{"error":"unexpected fixture URI"}', "application/json", 400)
                return
            self._send(json.dumps(OPLUS_TEST_METADATA).encode(), "application/json")
            return
        self._send(b'{"error":"not found"}', "application/json", 404)


def _render_mini_app_in_chrome(*, api_enabled: bool) -> tuple[str, int]:
    chrome = _chrome_path()
    if not chrome:
        raise unittest.SkipTest("Chrome/Chromium is unavailable")
    handler = type("MiniAppFixtureHandler", (_MiniAppFixtureHandler,), {"api_enabled": api_enabled})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as profile:
            screenshot = Path(profile) / "mini-app-mobile.png"
            result = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--window-size=390,1400",
                    "--virtual-time-budget=8000",
                    f"--user-data-dir={profile}",
                    f"--screenshot={screenshot}",
                    "--dump-dom",
                    f"http://127.0.0.1:{server.server_port}/",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
            return result.stdout.decode("utf-8", errors="replace"), screenshot.stat().st_size
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


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
        self.assertNotIn("TelegramApp.sendData(", script)
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
        self.assertIn("activeEventsJobId", script)
        self.assertIn("events?after=${after}", script)

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
        styles = (ROOT / "telegram_mini_app" / "styles.css").read_text(encoding="utf-8")

        for element_id in (
            "source-state",
            "source-facts",
            "source-facts-head",
            "source-metadata-count",
            "copy-source-metadata",
            "probe-source",
            "source-provider",
            "source-product-detected",
            "source-device-detected",
            "source-android-version",
            "source-security-patch",
            "source-build-date",
            "source-ota-type",
            "source-content-type",
            "source-md5",
            "source-last-modified",
            "source-deep-inspection",
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
        self.assertIn("error?.status !== 429", script)
        self.assertIn("const uriChanged = state.sourceInputUri !== currentUri", script)
        self.assertIn("sourceProbeRequestId", script)
        self.assertIn("sourceProbeController?.abort()", script)
        self.assertIn("metadataCompleteness", script)
        self.assertIn("copySourceMetadata", script)
        self.assertIn("apiUnavailableMessage", script)
        self.assertIn("checklistApiPending", script)
        self.assertIn("state.sourceProbeUri === currentUri", script)
        self.assertNotIn("confirmSource", script)
        source_fact_rule = styles.split(".source-facts dd", 1)[1].split("}", 1)[0]
        self.assertIn("overflow-wrap: anywhere", source_fact_rule)
        self.assertIn("white-space: normal", source_fact_rule)
        self.assertNotIn("text-overflow: ellipsis", source_fact_rule)

    def test_real_oplus_fixture_renders_full_metadata_and_selects_device_on_mobile(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(api_enabled=True)

        for value in (
            "PKG110",
            "OP5D2BL1",
            "PKG110_16.0.9.400(CN01)",
            "2026-07-01",
            "2026-07-06 08:51:35",
            "8.680.370.027 bytes",
            "c42d35ce2a9d460fa61db8a45c9b4db6.zip",
            "gauss-compotaauto-c-cn.allawnfs.com",
            "6fb0095cc9c07dbdb74074c87cbb643f",
            "14/14 thông số",
        ):
            self.assertIn(value, dom)
        self.assertIn('<strong id="launch-summary">PKG110 / PLUS / GitHub Auto</strong>', dom)
        self.assertIn('<li id="check-device" class="complete">', dom)
        self.assertIn('<li id="check-source" class="complete">', dom)
        self.assertIn('<li id="check-api" class="complete">', dom)
        self.assertRegex(dom, r'id="source-facts"(?![^>]* hidden)')
        submit_tag = dom.split('id="submit-recipe"', 1)[1].split(">", 1)[0]
        self.assertNotIn("disabled", submit_tag)
        self.assertGreater(screenshot_size, 10_000)

    def test_mobile_preview_explains_missing_api_instead_of_claiming_preflight_ready(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(api_enabled=False)

        self.assertIn("API CHƯA KẾT NỐI", dom)
        self.assertIn("Không thể đọc metadata sâu hoặc tạo job", dom)
        self.assertIn('id="submit-recipe" type="submit" disabled=""', dom)
        self.assertNotIn("SẴN SÀNG KIỂM TRA", dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_smart_source_uses_server_probe_instead_of_cross_origin_browser_fetch(self) -> None:
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        self.assertIn("probeSourceViaBackend", script)
        self.assertNotIn("fetch(uri", script)

    def test_pages_publish_is_not_skipped_when_api_is_not_configured(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "telegram-mini-app-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("if: ${{ vars.WUKONG_TELEGRAM_MINI_APP_API_URL != '' }}", workflow)
        self.assertIn('[[ -n "${MINI_APP_API_URL}"', workflow)
        self.assertIn("api_url=\"${MINI_APP_API_URL%/}\"", workflow)

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

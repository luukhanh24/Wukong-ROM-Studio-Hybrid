from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

from tools.export_mini_app_catalog import export_catalog
from wukong.mod_release_versions import default_mod_release_version


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
    telegram_authenticated = True
    click_paste = False
    source_uri = OPLUS_TEST_URI
    clipboard_fallback = False
    clipboard_gesture_only = False
    pairing_recovery = False
    server_draft_fallback = False
    probe_signed_expired = False
    source_metadata = OPLUS_TEST_METADATA
    catalog_mod_versions = ("ColorOS_16.0.9",)
    catalog_mods_by_version = None

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
            session = (
                "initData: 'fixture-init-data', "
                if self.telegram_authenticated
                else "initData: '', "
            )
            clipboard_value = "null" if (self.clipboard_fallback or self.clipboard_gesture_only or self.server_draft_fallback) else json.dumps(self.source_uri)
            gesture_guard = "window.__wukongPasteGesture === true" if self.clipboard_gesture_only else "true"
            exec_fallback = f"""
document.execCommand = (command) => {{
  if (command !== 'paste') return false;
  if (!({gesture_guard})) return false;
  const input = document.querySelector('#source-uri');
  if (!input) return false;
  input.value = {json.dumps(self.source_uri)};
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return true;
}};
""" if (self.clipboard_fallback or self.clipboard_gesture_only) else ""
            navigator_fallback = """
Object.defineProperty(navigator, 'clipboard', { value: {
  readText() { return Promise.reject(new DOMException('blocked', 'NotAllowedError')); }
}});
""" if (self.clipboard_gesture_only or self.server_draft_fallback) else ""
            source = f"""
window.Telegram = {{ WebApp: {{ {session}platform: 'android', ready() {{}}, expand() {{}}, isVersionAtLeast() {{ return false; }}, openTelegramLink() {{}}, readTextFromClipboard(callback) {{ callback({clipboard_value}); }}, HapticFeedback: {{ notificationOccurred() {{}} }} }} }};
{exec_fallback}
{navigator_fallback}
window.addEventListener('load', () => {{
  const fill = () => {{
    const input = document.querySelector('#source-uri');
    const catalogReady = document.querySelector('#device option[value="PKG110"]');
    if (!input || !catalogReady) {{ setTimeout(fill, 50); return; }}
    if ({str(self.click_paste).lower()}) {{
      window.__wukongPasteGesture = true;
      document.querySelector('#paste-source')?.click();
      window.__wukongPasteGesture = false;
    }}
    else {{ input.value = {json.dumps(self.source_uri)}; input.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
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
            mod_versions = list(self.catalog_mod_versions)
            mods_by_version = self.catalog_mods_by_version or {
                version: ["Gapps", "WK_Manager"] for version in mod_versions
            }
            catalog = {
                "schemaVersion": 1,
                "devices": [{"product": "PKG110", "name": "OnePlus Ace 5"}],
                "modVersions": mod_versions,
                "modReleaseVersions": {
                    version: default_mod_release_version(version)
                    for version in mod_versions
                },
                "modsByVersion": mods_by_version,
                "presetDefaultsByVersion": {
                    version: {"lite": [], "plus": ["Gapps"], "both": ["Gapps", "WK_Manager"], "custom": []}
                    for version in mod_versions
                },
                "pipelineSteps": [],
                "defaultDebloatPaths": [],
            }
            self._send(json.dumps(catalog).encode(), "application/json")
            return
        if path == "/v1/jobs":
            self._send(b'{"jobs":[]}', "application/json")
            return
        if path == "/v1/drafts/source" and self.server_draft_fallback:
            self._send(json.dumps({"uri": self.source_uri}).encode(), "application/json")
            return
        self._send(b"not found", "text/plain", 404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        if path == "/v1/session/pair" and self.pairing_recovery:
            self._send(json.dumps({
                "pairId": "fixture-pair",
                "pairSecret": "fixture-secret",
                "botLink": "https://t.me/WK_build_bot?start=pair_fixture-pair",
                "expiresIn": 300,
            }).encode(), "application/json", 201)
            return
        if path == "/v1/session/pair/status" and self.pairing_recovery:
            self._send(json.dumps({
                "status": "confirmed",
                "launchToken": f"v1.42.1.9999999999.{'a' * 64}",
            }).encode(), "application/json")
            return
        if path == "/v1/sources/probe" and self.api_enabled:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if payload.get("uri") != OPLUS_TEST_URI:
                self._send(b'{"error":"unexpected fixture URI"}', "application/json", 400)
                return
            if self.probe_signed_expired:
                self._send(
                    b'{"error":"signed URL expired","code":"source_signed_url_expired"}',
                    "application/json",
                    400,
                )
                return
            self._send(json.dumps(self.source_metadata).encode(), "application/json")
            return
        self._send(b'{"error":"not found"}', "application/json", 404)


def _render_mini_app_in_chrome(
    *,
    api_enabled: bool,
    telegram_authenticated: bool = True,
    click_paste: bool = False,
    source_uri: str = OPLUS_TEST_URI,
    clipboard_fallback: bool = False,
    clipboard_gesture_only: bool = False,
    telegram_hash_authenticated: bool = False,
    signed_launch_authenticated: bool = False,
    pairing_recovery: bool = False,
    server_draft_fallback: bool = False,
    probe_signed_expired: bool = False,
    source_metadata: dict[str, object] | None = None,
    catalog_mod_versions: tuple[str, ...] = ("ColorOS_16.0.9",),
    catalog_mods_by_version: dict[str, list[str]] | None = None,
    initial_view: str = "",
) -> tuple[str, int]:
    chrome = _chrome_path()
    if not chrome:
        raise unittest.SkipTest("Chrome/Chromium is unavailable")
    handler = type(
        "MiniAppFixtureHandler",
        (_MiniAppFixtureHandler,),
        {
            "api_enabled": api_enabled,
            "telegram_authenticated": telegram_authenticated,
            "click_paste": click_paste,
            "source_uri": source_uri,
            "clipboard_fallback": clipboard_fallback,
            "clipboard_gesture_only": clipboard_gesture_only,
            "pairing_recovery": pairing_recovery,
            "server_draft_fallback": server_draft_fallback,
            "probe_signed_expired": probe_signed_expired,
            "source_metadata": source_metadata or OPLUS_TEST_METADATA,
            "catalog_mod_versions": catalog_mod_versions,
            "catalog_mods_by_version": catalog_mods_by_version,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as profile:
            screenshot = Path(profile) / "mini-app-mobile.png"
            launch_url = f"http://127.0.0.1:{server.server_port}/"
            if signed_launch_authenticated:
                launch_url += f"?wkLaunch=v1.42.1.9999999999.{('a' * 64)}"
            if telegram_hash_authenticated:
                init_data = (
                    'query_id=fixture-query&'
                    'user={"id":42,"first_name":"Fixture"}&'
                    'auth_date=1787472000&hash=fixture-hash'
                )
                launch_url += f"#tgWebAppData={quote(init_data, safe='')}"
            elif initial_view:
                launch_url += f"#{initial_view}"
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
                    launch_url,
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
        self.assertEqual("V5.0", payload["modReleaseVersions"]["ColorOS_16.0.9"])
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
        self.assertNotIn("source_mirror", script)
        self.assertNotIn("artifact_publish", script)
        self.assertIn("loadJobs", script)
        self.assertIn("scheduleJobsPoll", script)
        self.assertIn("renderArtifacts", script)
        self.assertIn("upload_progress", script)
        self.assertIn("speedBytesPerSecond", script)
        self.assertIn("event-group", script)
        self.assertIn("activeEventsJobId", script)
        self.assertIn("events?after=${after}", script)
        self.assertIn("const unique = new Map()", script)
        self.assertNotIn("githubRunLink", script)
        self.assertNotIn("external_run_id", script)
        self.assertNotIn("luukhanh24", script)
        self.assertNotIn("github.com", script)

        exporter = (ROOT / "tools" / "export_mini_app_catalog.py").read_text(encoding="utf-8")
        self.assertIn("modReleaseVersions", exporter)

    def test_mini_app_maps_windows_operating_surfaces_without_saas_chrome(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "telegram_mini_app" / "styles.css").read_text(encoding="utf-8")
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        for surface in ("build", "jobs", "system"):
            self.assertIn(f'id="{surface}"', html)
            self.assertIn(f'data-nav="{surface}"', html)
        self.assertNotIn('id="catalog"', html)
        for control in (
            "default-preset",
            "pipeline-count",
            "mod-search",
            "telegram-auth-state",
            "mod-release-version-input",
        ):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('data-action="cache"', html)
        self.assertIn('data-action="cache_clear"', html)
        self.assertNotIn("renderCatalog", script)
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
        self.assertIn("backdrop-filter", styles)
        self.assertIn("liquid-lens", styles)
        bottom_nav = re.search(r'<nav class="bottom-nav".*?</nav>', html, re.DOTALL)
        self.assertIsNotNone(bottom_nav)
        bottom_nav_html = bottom_nav.group(0)
        self.assertEqual(["build", "jobs", "system"], re.findall(r'data-nav="([^"]+)"', bottom_nav_html))
        self.assertEqual(3, bottom_nav_html.count('class="nav-icon"'))
        self.assertNotRegex(bottom_nav_html, r"<b>\d{2}</b>")
        self.assertNotIn(".bottom-nav button.active::before", styles)
        self.assertIn("updateDispatchFab", script)
        self.assertIn('class="sr-only" data-i18n="finishSource"', html)
        self.assertIn("prefersReducedMotion", script)
        self.assertIn('"IBM Plex Sans"', styles)
        self.assertIn('"JetBrains Mono"', styles)
        self.assertIn("--accent:", styles)
        self.assertIn("--success:", styles)
        self.assertIn("--radius-sm: 4px", styles)
        self.assertIn("repeat(3,minmax(0,1fr))", styles)
        self.assertIn(".source-input-field, .source-input-head { min-width: 0; }", styles)

    def test_build_surface_keeps_only_build_jobs_and_system_actions(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "telegram_mini_app" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("Build từ Telegram.", html)
        self.assertNotIn("Build from Telegram.", script)
        self.assertNotIn('id="source-sha256"', html)
        self.assertNotIn("source_mirror", script)
        self.assertNotIn("artifact_publish", script)
        self.assertIn('id="mod-release-version"', html)
        self.assertIn('id="mod-release-version-input" maxlength="64"', html)
        self.assertIn("build.modReleaseVersion", script)
        self.assertIn("event-group", script)

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
        self.assertIn("110000", script)
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
        self.assertIn('<strong id="launch-summary">PKG110 · V5.0 / PLUS / GitHub Auto</strong>', dom)
        self.assertIn('<li id="check-device" class="complete">', dom)
        self.assertIn('<li id="check-source" class="complete">', dom)
        self.assertIn('<li id="check-api" class="complete">', dom)
        self.assertRegex(dom, r'id="source-facts"(?![^>]* hidden)')
        submit_tag = dom.split('id="submit-recipe"', 1)[1].split(">", 1)[0]
        self.assertNotIn("disabled", submit_tag)
        self.assertGreater(screenshot_size, 10_000)

    def test_probe_selects_the_mod_pack_matching_the_detected_rom_version(self) -> None:
        metadata = {
            **OPLUS_TEST_METADATA,
            "version": "PKG110_16.0.10.500(CN01)",
            "securityPatch": "2026-08-01",
            "buildDate": "2026-08-11 09:38:18",
        }

        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            source_metadata=metadata,
            catalog_mod_versions=("ColorOS_16.0.9", "ColorOS_16.0.10"),
            catalog_mods_by_version={
                "ColorOS_16.0.9": ["Gapps", "Legacy_marker"],
                "ColorOS_16.0.10": ["Gapps", "Hasselblad_filter"],
            },
        )

        mod_list = dom.split('id="mod-list"', 1)[1].split('<details class="advanced">', 1)[0]
        self.assertIn("Hasselblad_filter", mod_list)
        self.assertNotIn("Legacy_marker", mod_list)
        self.assertIn("PKG110_16.0.10.500(CN01)", dom)

    def test_paste_button_reads_clipboard_and_starts_source_analysis(self) -> None:
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, click_paste=True)

        self.assertIn('id="paste-source"', dom)
        self.assertIn(OPLUS_TEST_URI.split("?", 1)[0], dom.replace("&amp;", "&"))
        self.assertIn("14/14 thông số", dom)

    def test_paste_button_falls_back_when_clipboard_apis_are_blocked(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            click_paste=True,
            clipboard_fallback=True,
        )

        self.assertIn(OPLUS_TEST_URI.split("?", 1)[0], dom.replace("&amp;", "&"))
        self.assertIn("14/14 thông số", dom)
        self.assertNotIn("Không đọc được clipboard", dom)

    def test_paste_fallback_runs_inside_the_original_user_gesture(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            click_paste=True,
            clipboard_gesture_only=True,
        )

        self.assertIn(OPLUS_TEST_URI.split("?", 1)[0], dom.replace("&amp;", "&"))
        self.assertIn("14/14 thông số", dom)
        self.assertNotIn("Ô link đã được chọn", dom)

    def test_paste_button_retrieves_the_private_link_saved_by_the_bot(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            click_paste=True,
            server_draft_fallback=True,
        )

        self.assertIn(OPLUS_TEST_URI.split("?", 1)[0], dom.replace("&amp;", "&"))
        self.assertIn("14/14 thông số", dom)

    def test_mobile_preview_explains_missing_api_instead_of_claiming_preflight_ready(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(api_enabled=False)

        self.assertIn("API CHƯA KẾT NỐI", dom)
        self.assertIn("Không thể đọc metadata sâu hoặc tạo job", dom)
        self.assertIn('id="submit-recipe" type="submit" disabled=""', dom)
        self.assertNotIn("SẴN SÀNG KIỂM TRA", dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_expired_signed_source_explains_how_to_refresh_the_link(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            probe_signed_expired=True,
        )

        self.assertIn("Link tải ký trực tiếp đã hết hạn hoặc không còn đủ thời gian cho build cloud", dom)
        self.assertIn("OPlus downloadCheck", dom)

    def test_live_signed_source_with_dispatch_margin_allows_cloud_build(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            source_metadata={
                **OPLUS_TEST_METADATA,
                "cloudBuildReady": True,
                "signedUrlExpiresAt": 1_787_500_917,
            },
        )

        self.assertIn("14/14 thông số", dom)
        self.assertIn('<li id="check-source" class="complete">', dom)
        submit_match = re.search(r'<button[^>]*id="submit-recipe"[^>]*>', dom)
        self.assertIsNotNone(submit_match)
        self.assertNotIn("disabled", submit_match.group(0))

    def test_unauthenticated_preview_keeps_link_and_offers_bot_jump(self) -> None:
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, telegram_authenticated=False)

        self.assertNotIn("CẦN PHIÊN TELEGRAM", dom)
        self.assertIn("14/14 thông số", dom)
        self.assertIn(OPLUS_TEST_URI.split("?")[0], dom.replace("&amp;", "&"))
        submit_match = re.search(r'<button[^>]*id="submit-recipe"[^>]*>', dom)
        self.assertIsNotNone(submit_match)
        self.assertIn("disabled", submit_match.group(0))

    def test_hash_init_data_survives_initial_navigation_and_enables_jobs(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            telegram_authenticated=False,
            telegram_hash_authenticated=True,
        )

        self.assertIn("14/14 thông số", dom)
        self.assertIn('<li id="check-api" class="complete">', dom)
        self.assertIn("phiên hợp lệ", dom)
        submit_match = re.search(r'<button[^>]*id="submit-recipe"[^>]*>', dom)
        self.assertIsNotNone(submit_match)
        self.assertNotIn("disabled", submit_match.group(0))

    def test_signed_bot_launch_enables_api_when_telegram_omits_init_data(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            telegram_authenticated=False,
            signed_launch_authenticated=True,
        )

        self.assertIn("14/14 thông số", dom)
        self.assertIn('<li id="check-api" class="complete">', dom)
        self.assertIn("phiên dự phòng", dom)
        submit_match = re.search(r'<button[^>]*id="submit-recipe"[^>]*>', dom)
        self.assertIsNotNone(submit_match)
        self.assertNotIn("disabled", submit_match.group(0))

    def test_static_launch_can_pair_with_bot_and_enable_api(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            telegram_authenticated=False,
            pairing_recovery=True,
        )

        self.assertIn('id="connect-telegram"', dom)
        self.assertIn('<li id="check-api" class="complete">', dom)
        self.assertIn("phiên dự phòng", dom)

    def test_jobs_distinguishes_missing_telegram_session_from_missing_api(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            telegram_authenticated=False,
            initial_view="jobs",
        )

        self.assertIn("Phiên Telegram chưa được kết nối", dom)
        self.assertIn('id="connect-telegram"', dom)
        self.assertNotIn("Mini App API chưa được cấu hình", dom)

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

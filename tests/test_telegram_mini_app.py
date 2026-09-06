from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

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


def _partial_metadata_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "META-INF/com/android/metadata",
            "\n".join((
                "oplus-product-name=PKG110",
                "pre-device=OP5D2BL1",
                "oplus-version-name=PKG110_16.0.9.400(CN01)",
                "post-sdk-level=36",
                "post-security-patch-level=2026-07-01",
                "post-timestamp=1783327895",
                "ota-type=AB",
            )),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr(
            "payload_properties.txt",
            "FILE_HASH=fixture",
            compress_type=zipfile.ZIP_BZIP2,
        )
    output.seek(0)
    return output.read()


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



def _style_source():
    root = ROOT / "telegram_mini_app"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted((root / "styles").glob("*.css")))


def _app_source():
    root = ROOT / "telegram_mini_app"
    return "\n".join(path.read_text(encoding="utf-8") for path in [root / "app.js", *sorted((root / "modules").glob("*.js")), *sorted((root / "lib").glob("*.js"))])

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
    probe_zip_payload = None
    catalog_mod_versions = ("ColorOS_16.0.9",)
    catalog_mods_by_version = None
    jobs_fixture = False
    upload_progress_fixture = False
    legacy_sync_contract = False
    click_job_log = False
    click_mod_toggle = False
    click_other_job = False
    artifact_fixture = False
    click_artifact_actions = False
    click_profile = False
    click_theme_dark = False
    system_theme_change = False
    click_cache_flow = False
    click_admin_user = False
    admin_job_scenario = False
    click_admin_action = False
    exercise_batch_controls = False
    exercise_custom_release = False
    exercise_custom_recipe = False
    submitted_recipe = None
    preset_labels = {"lite": "Lite", "plus": "Plus", "custom": "Custom"}
    exercise_dock_header = False
    cache_clear_requests = 0
    admin_user = False
    pending_user = False
    library_scenario = ""
    maintenance_enabled = False

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
        if path == "/probe-range" and self.probe_zip_payload is not None:
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
            if not match:
                self._send(b'{"error":"range required"}', "application/json", 416)
                return
            start, end = map(int, match.groups())
            payload = self.probe_zip_payload[start : end + 1]
            self.send_response(206)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(self.probe_zip_payload)}")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
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
            artifact_clipboard = """
Object.defineProperty(navigator, 'clipboard', { value: {
  readText() { return Promise.resolve(''); },
  writeText(value) { document.body.dataset.copiedArtifact = value; return Promise.resolve(); }
}});
""" if self.click_artifact_actions else ""
            source = f"""
window.__telegramEvents = {{}};
window.Telegram = {{ WebApp: {{ {session}platform: 'android', colorScheme: 'light', ready() {{}}, expand() {{}}, isVersionAtLeast() {{ return false; }}, onEvent(name, callback) {{ window.__telegramEvents[name] = callback; }}, offEvent(name, callback) {{ if (window.__telegramEvents[name] === callback) delete window.__telegramEvents[name]; }}, setHeaderColor(value) {{ document.body.dataset.telegramHeaderColor = value; }}, setBackgroundColor(value) {{ document.body.dataset.telegramBackgroundColor = value; }}, openTelegramLink() {{}}, openLink(url) {{ document.body.dataset.openedArtifact = url; }}, readTextFromClipboard(callback) {{ callback({clipboard_value}); }}, HapticFeedback: {{ notificationOccurred() {{}}, impactOccurred() {{}}, selectionChanged() {{ document.body.dataset.hapticSelections = String(Number(document.body.dataset.hapticSelections || 0) + 1); }} }} }} }};
{exec_fallback}
window.addEventListener('DOMContentLoaded', () => {{
  if (!{json.dumps(self.library_scenario)}) return;
  Object.defineProperty(navigator, 'clipboard', {{ configurable: true, value: {{ writeText: async (text) => {{ document.body.dataset.romCopied = text; }} }} }});
  if ({json.dumps(self.library_scenario)} === 'timeout') {{
    const nativeTimeout = window.setTimeout.bind(window);
    window.setTimeout = (callback, delay, ...args) => nativeTimeout(callback, delay === 70000 ? 20 : delay, ...args);
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, options) => String(input).endsWith('/v1/sources/resolve')
      ? new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
      : nativeFetch(input, options);
  }}
  const exerciseLibrary = () => {{
    if (document.body.classList.contains('access-checking')) {{ setTimeout(exerciseLibrary, 50); return; }}
    document.querySelector('[data-nav="catalog"]').click();
    document.body.dataset.libraryTitle = document.querySelector('#catalog-title').textContent;
    document.body.dataset.romInLibrary = String(document.querySelector('#catalog').contains(document.querySelector('#rom-catalog-panel')));
    document.querySelector('#library-technical-tab').click();
    document.body.dataset.technicalVisible = String(!document.querySelector('#library-technical').hidden);
    document.querySelector('#library-rom-tab').click();
    const chooseDevice = () => {{
    const choice = document.querySelector('[data-rom-device="OP 13"]');
    if (!choice) {{ setTimeout(chooseDevice, 50); return; }}
    document.querySelector('#rom-device-picker').open = true;
    const search = document.querySelector('#rom-device-search');
    search.value = 'OnePlus Pad 2';
    search.dispatchEvent(new Event('input', {{ bubbles: true }}));
    document.body.dataset.naturalDeviceMatch = String(Boolean(document.querySelector('[data-rom-device="OP PAD2"]')));
    search.value = 'cph2653';
    search.dispatchEvent(new Event('input', {{ bubbles: true }}));
    document.body.dataset.filteredDevices = String(document.querySelectorAll('[data-rom-device]').length);
    document.querySelector('[data-rom-device="OP 13"]').click();
    document.body.dataset.deviceLabel = document.querySelector('#rom-device-label').textContent;
    document.body.dataset.deviceRegions = [...document.querySelector('#rom-region-filter').options].map(o => o.value).join(',');
    document.querySelector('#search-rom-catalog').click();
    const checkResult = () => {{
      const result = document.querySelector('[data-rom-action="analyze"]');
      if (!result) {{ setTimeout(checkResult, 50); return; }}
      document.body.dataset.romResults = String(document.querySelectorAll('.rom-release').length);
      const versions = document.querySelector('#rom-version-filter');
      document.body.dataset.romVersionCount = String(versions.options.length);
      versions.value = 'rom-old';
      versions.dispatchEvent(new Event('change'));
      document.body.dataset.oldVersionSelected = String(document.querySelector('.rom-release-version').textContent.includes('16.0.9'));
      versions.value = 'rom-fixture';
      versions.dispatchEvent(new Event('change'));
      if ({json.dumps(self.library_scenario)} === 'timeout') {{
        document.querySelector('[data-rom-action="resolve"]').click();
        const checkTimeout = () => {{
          if (!document.querySelector('.rom-resolve-error')) {{ setTimeout(checkTimeout, 50); return; }}
          document.body.dataset.resolveTimeoutRecovered = String(!document.querySelector('[data-rom-action="resolve"]').disabled);
        }};
        checkTimeout();
      }}
      if ({json.dumps(self.library_scenario)} === 'select') {{
        document.querySelector('[data-rom-action="copy"]').click();
        document.querySelector('[data-rom-action="resolve"]').click();
        const finishSelection = () => {{
        const resolved = document.querySelector('.rom-resolved-url');
        if (!resolved) {{ setTimeout(finishSelection, 50); return; }}
        document.body.dataset.resolvedRomLink = resolved.value;
        document.querySelector('[data-rom-action="analyze"]').click();
        document.body.dataset.selectedSource = document.querySelector('#source-uri').value;
        document.body.dataset.selectedView = document.querySelector('main>.view.active').id;
        }};
        finishSelection();
      }}
    }};
    checkResult();
    }};
    chooseDevice();
  }};
  setTimeout(exerciseLibrary, 400);
}});
{navigator_fallback}
{artifact_clipboard}
window.addEventListener('load', () => {{
  if ({str(self.system_theme_change).lower()}) {{
    const changeTelegramTheme = () => {{
      const handler = window.__telegramEvents.themeChanged;
      if (!handler) {{ setTimeout(changeTelegramTheme, 50); return; }}
      window.Telegram.WebApp.colorScheme = 'dark';
      handler();
      document.body.dataset.systemThemeAfterTelegramChange = document.documentElement.dataset.colorScheme || '';
      document.body.dataset.selectedThemeMode = document.documentElement.dataset.theme || '';
    }};
    setTimeout(changeTelegramTheme, 250);
  }}
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
  if ({str(self.click_job_log).lower()}) {{
    const openLog = () => {{
      const button = document.querySelector('.job-log-toggle');
      if (!button) {{ setTimeout(openLog, 50); return; }}
      button.click();
    }};
    setTimeout(openLog, 100);
  }}
  if ({str(self.click_artifact_actions).lower()}) {{
    const useArtifactActions = () => {{
      const open = document.querySelector('.artifact-open');
      const copy = document.querySelector('.artifact-copy');
      if (!open || !copy) {{ setTimeout(useArtifactActions, 50); return; }}
      open.click();
      copy.click();
    }};
    setTimeout(useArtifactActions, 100);
  }}
  if ({str(self.click_mod_toggle).lower()}) {{
    const customizeMod = () => {{
      const input = document.querySelector('#mod-list input[type="checkbox"]');
      const preset = document.querySelector('#preset');
      if (!input || !preset) {{ setTimeout(customizeMod, 50); return; }}
      input.click();
      document.body.dataset.presetAfterMod = preset.value;
    }};
    setTimeout(customizeMod, 100);
  }}
  if ({str(self.click_other_job).lower()}) {{
    let jobSelectionStarted = false;
    let syncRequestsAfterSelection = 0;
    const fetchBeforeJobSelection = window.fetch.bind(window);
    window.fetch = async (...args) => {{
      if (jobSelectionStarted && String(args[0]).includes('/v1/sync')) syncRequestsAfterSelection += 1;
      return fetchBeforeJobSelection(...args);
    }};
    const selectArchivedJob = () => {{
      const tab = document.querySelector('[data-job-filter="succeeded"]');
      if (!tab) {{ setTimeout(selectArchivedJob, 50); return; }}
      if (tab.getAttribute('aria-selected') !== 'true') tab.click();
      const card = document.querySelector('.job-history-card');
      if (!card || !card.textContent.includes('ARCHIVED_16.0.8.300(CN01)')) {{ setTimeout(selectArchivedJob, 50); return; }}
      jobSelectionStarted = true;
      card.click();
      setTimeout(() => {{ document.body.dataset.jobDetailSyncCalls = String(syncRequestsAfterSelection); }}, 500);
    }};
    setTimeout(selectArchivedJob, 300);
  }}
  if ({str(self.click_profile).lower()}) {{
    const openProfile = () => {{
      const button = document.querySelector('#dock-profile');
      if (!button || button.hidden) {{ setTimeout(openProfile, 50); return; }}
      button.click();
      document.body.dataset.profileOpened = String(document.querySelector('#profile')?.classList.contains('active') === true);
      document.body.dataset.activeProfileTab = document.querySelector('.bottom-nav [aria-current="page"]')?.dataset.nav || '';
      document.body.dataset.profileLensSuppressed = String(document.querySelector('.bottom-nav')?.classList.contains('profile-active') === true);
      document.body.dataset.profileHaloActive = String(button.classList.contains('active') === true);
    }};
    setTimeout(openProfile, 250);
  }}
  if ({str(self.click_theme_dark).lower()}) {{
    const selectDark = () => {{
      const button = document.querySelector('[data-theme-value="dark"]');
      if (!button) {{ setTimeout(selectDark, 50); return; }}
      button.scrollIntoView({{ block: 'center' }});
      button.click();
      document.body.dataset.selectedTheme = document.documentElement.dataset.colorScheme || '';
    }};
    setTimeout(selectDark, 250);
  }}
  if ({str(self.click_cache_flow).lower()}) {{
    const exerciseCache = () => {{
      const trigger = document.querySelector('[data-action="cache_clear"]');
      const dialog = document.querySelector('#cache-clear-dialog');
      if (!trigger || !dialog) {{ setTimeout(exerciseCache, 50); return; }}
      trigger.click();
      document.body.dataset.cacheDialogOpened = String(dialog.open === true);
      dialog.querySelector('[value="cancel"]')?.click();
      document.body.dataset.cacheCancelled = String(dialog.open === false);
      setTimeout(() => {{
        trigger.click();
        setTimeout(() => {{
          document.querySelector('#cache-clear-confirm')?.click();
          setTimeout(async () => {{
            const result = await fetch('/test/cache-count').then((response) => response.json());
            document.body.dataset.cacheRequestCount = String(result.count);
          }}, 800);
        }}, 80);
      }}, 80);
    }};
    setTimeout(exerciseCache, 300);
  }}
  if ({str(self.click_admin_user).lower()}) {{
    const openAdminProfile = () => {{
      const button = document.querySelector('.user-open');
      if (!button) {{ setTimeout(openAdminProfile, 50); return; }}
      button.click();
      setTimeout(() => {{
        const page = document.querySelector('#admin-user-page');
        document.body.dataset.adminUserPageOpen = String(page?.hidden === false && document.querySelector('#system')?.classList.contains('admin-user-open'));
        document.body.dataset.adminUserDialogPresent = String(Boolean(document.querySelector('#user-detail-dialog')));
      }}, 500);
    }};
    setTimeout(openAdminProfile, 500);
  }}
  if ({str(self.admin_job_scenario).lower()}) {{
    const inspectUserJob = () => {{
      const button = document.querySelector('[data-open-user-job]');
      if (!button) {{ setTimeout(inspectUserJob, 50); return; }}
      const originalFetch = window.fetch.bind(window);
      let delayNextPoll = true;
      window.fetch = async (...args) => {{
        const url = String(args[0]);
        const response = await originalFetch(...args);
        if (url.includes('/v1/sync') && !url.includes('archived-job') && delayNextPoll) {{
          delayNextPoll = false;
          await new Promise(resolve => setTimeout(resolve, 700));
        }}
        return response;
      }};
      document.querySelector('#refresh-jobs').click();
      const originalJob = localStorage.getItem('wukong-active-job');
      button.click();
      setTimeout(() => {{
        let sameJobCalls = 0;
        const priorFetch = window.fetch.bind(window);
        window.fetch = async (...args) => {{
          const isSync = String(args[0]).includes('/v1/sync');
          const number = isSync ? ++sameJobCalls : 0;
          const response = await priorFetch(...args);
          if (!isSync) return response;
          const data = await response.json();
          data.activeJob.stage = number === 1 ? 'old-stage' : 'new-stage';
          data.activeJob.recipe.build.debloatPaths = Array.from({{length:100}}, (_, i) => `my_stock/app/Test${{i}}`);
          await new Promise(resolve => setTimeout(resolve, number === 1 ? 450 : 30));
          return new Response(JSON.stringify(data), {{status:200, headers:{{'Content-Type':'application/json'}}}});
        }};
        document.querySelector('#refresh-admin-job')?.click();
        setTimeout(() => document.querySelector('#refresh-admin-job')?.click(), 40);
        setTimeout(() => {{
          document.body.dataset.inspectedJob = document.querySelector('#admin-job-detail')?.dataset.jobId || '';
          document.body.dataset.inspectedEvents = document.querySelector('#admin-job-detail .job-events')?.textContent || '';
          document.body.dataset.inspectedOwner = document.querySelector('#admin-job-detail .job-creator')?.textContent || '';
          document.body.dataset.inspectedView = document.body.dataset.view;
          document.body.dataset.adminSelectionUnchanged = String(localStorage.getItem('wukong-active-job') === originalJob);
          const reader = document.querySelector('#admin-job-detail .job-config');
          if (!reader) return;
          reader.open = true;
          const pre = reader.querySelector('pre');
          pre.focus(); pre.scrollTop = 200;
          const selection = getSelection(); const range = document.createRange();
          range.setStart(pre.firstChild, 5); range.setEnd(pre.firstChild, 20);
          selection.removeAllRanges(); selection.addRange(range);
          const selectedText = selection.toString();
          document.querySelector('#refresh-admin-job').click();
          setTimeout(() => {{
            document.body.dataset.parametersPreserved = String(document.querySelector('#admin-job-detail .job-config pre') === pre && pre.scrollTop === 200 && document.activeElement === pre && selection.toString() === selectedText);
            reader.open = false;
            document.body.dataset.inspectedStage = document.querySelector('#admin-job-detail .job-progress strong')?.textContent || '';
            const logButton = document.querySelector('#admin-job-detail .job-log-toggle');
            logButton.focus();
            let statusMutations = 0;
            const statusObserver = new MutationObserver(() => statusMutations++);
            statusObserver.observe(document.querySelector('#admin-job-connection'), {{childList:true, characterData:true, subtree:true}});
            document.querySelector('#refresh-admin-job').click();
            setTimeout(() => {{
              statusObserver.disconnect();
              document.body.dataset.adminJobStatusQuiet = String(statusMutations === 0);
              document.body.dataset.adminJobFocusPreserved = String(document.activeElement?.dataset.jobFocus === 'log-toggle');
              const successfulFetch = window.fetch.bind(window);
              window.fetch = async (...args) => String(args[0]).includes('jobId=archived-job')
                ? new Response(JSON.stringify({{error:'Fixture offline'}}), {{status:503, headers:{{'Content-Type':'application/json'}}}})
                : successfulFetch(...args);
              let errorStatusMutations = 0;
              const errorStatusObserver = new MutationObserver(() => errorStatusMutations++);
              errorStatusObserver.observe(document.querySelector('#admin-job-connection'), {{childList:true, characterData:true,subtree:true}});
              document.querySelector('#refresh-admin-job').click();
              setTimeout(() => {{
                document.querySelector('#refresh-admin-job').click();
                setTimeout(() => {{
                  errorStatusObserver.disconnect();
                  document.body.dataset.adminJobErrorStatusQuiet = String(errorStatusMutations === 1);
                  window.fetch = successfulFetch;
                  document.querySelector('#admin-job-back').click();
                  document.body.dataset.userHistoryRestored = String(document.querySelector('#admin-user-page').hidden === false && !document.querySelector('#system').classList.contains('admin-job-open') && document.activeElement === button);
                  setTimeout(() => {{
                    document.body.dataset.closedJobStayedClosed = String(document.querySelector('#admin-job-page').hidden && localStorage.getItem('wukong-active-job') === originalJob);
                    button.click();
                  }}, 100);
                }}, 2000);
              }}, 100);
            }}, 200);
          }}, 200);
        }}, 700);
      }}, 1100);
    }};
    setTimeout(inspectUserJob, 1100);
  }}
  if ({str(self.click_admin_action).lower()}) {{
    const openAdminAction = () => {{
      const button = document.querySelector('.user-detail-actions button:nth-child(2)');
      if (!button) {{ setTimeout(openAdminAction, 50); return; }}
      button.click();
      setTimeout(() => {{
        const dialog = document.querySelector('#admin-action-dialog');
        document.body.dataset.adminActionDialogOpen = String(dialog?.open === true);
        document.body.dataset.adminActionValueVisible = String(document.querySelector('#admin-action-value-field')?.hidden === false);
        const confirmStyle = getComputedStyle(document.querySelector('#admin-action-confirm'));
        document.body.dataset.adminActionConfirmColor = confirmStyle.color;
        document.body.dataset.adminActionConfirmBackground = confirmStyle.backgroundColor;
      }}, 100);
    }};
    setTimeout(openAdminAction, 1200);
  }}
  if ({str(self.admin_user).lower()}) {{
    const captureBatchLaunchStyle = () => {{
      const button = document.querySelector('#open-batch-build');
      if (!button || button.hidden) {{ setTimeout(captureBatchLaunchStyle, 50); return; }}
      const style = getComputedStyle(button);
      document.body.dataset.batchLaunchColor = style.color;
      document.body.dataset.batchLaunchBackground = style.backgroundColor;
    }};
    setTimeout(captureBatchLaunchStyle, 700);
  }}
  if ({str(self.exercise_batch_controls).lower()}) {{
    const exerciseBatchControls = () => {{
      const open = document.querySelector('#open-batch-build');
      const selectDevices = document.querySelector('#batch-select-all-devices');
      const clearDevices = document.querySelector('#batch-clear-devices');
      const selectMods = document.querySelector('#batch-select-all-mods');
      const clearMods = document.querySelector('#batch-clear-mods');
      if (!open || !selectDevices || !clearDevices || !selectMods || !clearMods) {{ setTimeout(exerciseBatchControls, 50); return; }}
      open.click();
      selectDevices.click();
      document.body.dataset.batchDevicesSelected = String(document.querySelectorAll('#batch-devices input:checked').length);
      clearDevices.click();
      document.body.dataset.batchDevicesCleared = String(document.querySelectorAll('#batch-devices input:checked').length);
      selectMods.click();
      document.body.dataset.batchModsSelected = String(document.querySelectorAll('#batch-mod-versions input:checked').length);
      clearMods.click();
      document.body.dataset.batchModsCleared = String(document.querySelectorAll('#batch-mod-versions input:checked').length);
      document.body.dataset.batchReleaseInputAbsent = String(!document.querySelector('#batch-release-version'));
    }};
    setTimeout(exerciseBatchControls, 700);
  }}
  if ({str(self.exercise_custom_release).lower()}) {{
    const exercisePresetLabels = () => {{
      const nav = document.querySelector('[data-nav="catalog"]');
      const tab = document.querySelector('#library-technical-tab');
      const lite = document.querySelector('#admin-preset-label-lite');
      const plus = document.querySelector('#admin-preset-label-plus');
      const custom = document.querySelector('#admin-preset-label-custom');
      const save = document.querySelector('#save-admin-preset-labels');
      if (!nav || !tab || !lite || !plus || !custom || !save) {{ setTimeout(exercisePresetLabels, 50); return; }}
      nav.click();
      tab.click();
      if (save.closest('[hidden]')) {{ setTimeout(exercisePresetLabels, 50); return; }}
      lite.value = 'Essential'; plus.value = 'Complete'; custom.value = 'Studio';
      save.click();
      setTimeout(() => {{
        document.body.dataset.presetLabelsEditorVisible = String(!save.closest('[hidden]'));
        document.body.dataset.presetLabelsSaved = String(document.querySelector('#preset option[value="lite"]')?.textContent === 'Essential');
        document.body.dataset.presetLabelCustom = document.querySelector('#preset option[value="custom"]')?.textContent || '';
        document.body.dataset.releaseTitleAfterPresetRename = document.querySelector('#release-version-title')?.textContent || '';
      }}, 250);
    }};
    setTimeout(exercisePresetLabels, 700);
  }}
  if ({str(self.exercise_custom_recipe).lower()}) {{
    const exerciseCustomRecipe = () => {{
      const form = document.querySelector('#recipe-form');
      const submit = document.querySelector('#submit-recipe');
      const source = document.querySelector('#source-uri');
      const device = document.querySelector('#device');
      const releaseInput = document.querySelector('#mod-release-version-input');
      const saveRelease = document.querySelector('#save-mod-release-version');
      const customLabelEditor = document.querySelector('#custom-preset-label-editor');
      const customLabelInput = document.querySelector('#custom-preset-label-input');
      const applyCustomLabel = document.querySelector('#apply-custom-preset-label');
      if (!form || !submit || !source || !device || !releaseInput || !saveRelease || !customLabelEditor || !customLabelInput || !applyCustomLabel || document.body.classList.contains('access-checking')) {{ setTimeout(exerciseCustomRecipe, 50); return; }}
      document.querySelector('#preset').value = 'custom';
      document.querySelector('#preset').dispatchEvent(new Event('change', {{ bubbles: true }}));
      document.body.dataset.customLabelEditorVisible = String(!customLabelEditor.hidden);
      customLabelInput.value = 'Limited';
      applyCustomLabel.click();
      releaseInput.value = 'KhanhDZ Custom';
      saveRelease.click();
      source.value = {json.dumps(OPLUS_TEST_URI)};
      source.dispatchEvent(new Event('input', {{ bubbles: true }}));
      device.value = 'PKG110';
      submit.disabled = false;
      form.requestSubmit();
      const readRecipe = () => fetch('/test/submitted-recipe').then(response => response.json()).then(payload => {{
        const build = payload.recipe?.build || {{}};
        if (!build.modVersion) {{ setTimeout(readRecipe, 50); return; }}
        document.body.dataset.customModRecipe = build.modVersion;
        document.body.dataset.customPresetLabelRecipe = JSON.stringify(build.editionLabels || {{}});
        document.body.dataset.customReleaseRecipe = build.modReleaseVersion || '';
      }}).catch(() => setTimeout(readRecipe, 50));
      setTimeout(readRecipe, 100);
    }};
    setTimeout(exerciseCustomRecipe, 700);
  }}
  if ({str(self.exercise_dock_header).lower()}) {{
    const exerciseDockHeader = () => {{
      const greeting = document.querySelector('#greeting-message');
      const jobs = document.querySelector('.bottom-nav [data-nav="jobs"]');
      if (!greeting || !jobs || jobs.hidden) {{ setTimeout(exerciseDockHeader, 50); return; }}
      document.body.dataset.greetingInitial = greeting.textContent;
      setTimeout(() => {{
        document.documentElement.scrollTop = 120;
        document.body.scrollTop = 120;
        window.dispatchEvent(new Event('scroll'));
        setTimeout(() => {{
          document.body.dataset.mastheadProgress = document.documentElement.style.getPropertyValue('--masthead-scroll');
          jobs.click();
        }}, 250);
      }}, 1800);
      setTimeout(() => {{
        document.body.dataset.activeDockTab = document.querySelector('.bottom-nav [aria-current="page"]')?.dataset.nav || '';
        document.body.dataset.greetingRotated = String(greeting.textContent !== document.body.dataset.greetingInitial);
        document.body.dataset.brokenAssets = String([...document.images].filter((image) => image.complete && image.naturalWidth === 0).length);
      }}, 6500);
    }};
    setTimeout(exerciseDockHeader, 350);
  }}
  setTimeout(() => {{
    document.body.dataset.viewportWidth = String(document.documentElement.clientWidth);
    document.body.dataset.documentWidth = String(document.documentElement.scrollWidth);
  }}, 1200);
}});
"""
            self._send(source.encode(), "application/javascript; charset=utf-8")
            return
        if path == "/fixture-avatar.svg":
            self._send(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
                    '<defs><radialGradient id="a"><stop stop-color="#56d6ff"/>'
                    '<stop offset=".46" stop-color="#3159d9"/><stop offset="1" stop-color="#120b35"/></radialGradient></defs>'
                    '<rect width="200" height="200" fill="url(#a)"/><circle cx="100" cy="100" r="48" fill="none" '
                    'stroke="#ff8bd2" stroke-width="13"/><circle cx="116" cy="82" r="26" fill="#fff" opacity=".72"/></svg>'
                ).encode(),
                "image/svg+xml",
            )
            return
        if path == "/WukongStudio.svg":
            self._send(
                (ROOT / "telegram_mini_app" / "WukongStudio.svg").read_bytes(),
                "image/svg+xml",
            )
            return
        if path == "/styles.css":
            styles = (ROOT / "telegram_mini_app" / "styles.css").read_text(encoding="utf-8")
            self._send(styles.encode(), "text/css; charset=utf-8")
            return
        if path.startswith(("/lib/", "/modules/", "/styles/", "/assets/")):
            asset = (ROOT / "telegram_mini_app" / path.lstrip("/")).resolve()
            if asset.is_relative_to(ROOT / "telegram_mini_app") and asset.is_file():
                content_type = "application/javascript" if asset.suffix == ".js" else "text/css" if asset.suffix == ".css" else "font/woff2" if asset.suffix == ".woff2" else "image/svg+xml"
                self._send(asset.read_bytes(), content_type)
                return
        if path == "/app.js":
            self._send(
                (ROOT / "telegram_mini_app" / "app.js").read_bytes(),
                "application/javascript; charset=utf-8",
            )
            return
        if path == "/fflate.js":
            self._send(
                (ROOT / "telegram_mini_app" / "fflate.js").read_bytes(),
                "application/javascript; charset=utf-8",
            )
            return
        if path.startswith("/assets/"):
            asset = ROOT / "telegram_mini_app" / path.lstrip("/")
            if asset.is_file():
                self._send(asset.read_bytes(), "image/svg+xml")
                return
        if path == "/catalog.json":
            mod_versions = list(self.catalog_mod_versions)
            mods_by_version = self.catalog_mods_by_version or {
                version: ["Gapps", "WK_Manager"] for version in mod_versions
            }
            catalog = {
                "schemaVersion": 1,
                "presetLabels": dict(type(self).preset_labels),
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
            jobs = [self._fixture_job()] if self.jobs_fixture else []
            if self.jobs_fixture and self.click_other_job:
                jobs.append(self._fixture_archived_job())
            self._send(json.dumps({"jobs": jobs}).encode(), "application/json")
            return
        if path == "/test/submitted-recipe":
            self._send(json.dumps({"recipe": type(self).submitted_recipe}).encode(), "application/json")
            return
        if path == "/v1/sync":
            jobs = [self._fixture_job()] if self.jobs_fixture else []
            if self.jobs_fixture and self.click_other_job:
                jobs.append(self._fixture_archived_job())
            if self.jobs_fixture and self.legacy_sync_contract:
                for index in range(25):
                    archived = self._fixture_archived_job()
                    archived["job_id"] = f"archived-job-{index:02d}"
                    jobs.append(archived)
            all_jobs = list(jobs)
            query = parse_qs(urlsplit(self.path).query)
            selected = str((query.get("jobId") or [""])[0])
            after = int(str((query.get("after") or ["0"])[0]) or "0")
            status_filter = str((query.get("status") or [""])[0])
            if status_filter == "active" and not self.legacy_sync_contract:
                jobs = [job for job in jobs if job.get("status") not in {"succeeded", "failed", "cancelled"}]
            elif status_filter == "succeeded" and not self.legacy_sync_contract:
                jobs = [job for job in jobs if job.get("status") == "succeeded"]
            elif status_filter == "failed" and not self.legacy_sync_contract:
                jobs = [job for job in jobs if job.get("status") in {"failed", "cancelled"}]
            if selected == "archived-job" and self.jobs_fixture and (self.click_other_job or self.admin_job_scenario):
                active_job = self._fixture_archived_job()
                if self.admin_job_scenario:
                    active_job["createdBy"] = {"telegramId": "88", "displayName": "New User", "username": "new_user"}
                events = [
                    {"sequence": 1, "jobId": "archived-job", "timestamp": "2026-08-24T01:00:00Z", "type": "submitted"},
                    {"sequence": 2, "jobId": "archived-job", "timestamp": "2026-08-24T01:04:00Z", "type": "step", "step": "package", "status": "success"},
                ]
            elif self.jobs_fixture:
                active_job = self._fixture_job()
                events = [
                    {"sequence": 1, "jobId": "fixture-job", "timestamp": "2026-08-25T01:00:00Z", "type": "submitted", "runner": "github-hosted"},
                    {"sequence": 2, "jobId": "fixture-job", "timestamp": "2026-08-25T01:01:00Z", "type": "plan", "steps": ["inspect_rom", "debloat", "apply_mod"]},
                    {"sequence": 3, "jobId": "fixture-job", "timestamp": "2026-08-25T01:02:00Z", "type": "step", "step": "inspect_rom", "status": "success", "details": {"durationSeconds": 4.2, "phase": "Plus"}},
                    {"sequence": 4, "jobId": "fixture-job", "timestamp": "2026-08-25T01:03:00Z", "type": "step", "step": "debloat", "status": "running", "message": "Đang quét 42 đường dẫn hệ thống", "details": {"removedCount": 17, "notFoundCount": 2, "phase": "Plus"}},
                ]
                if self.upload_progress_fixture:
                    events.extend([
                        {"sequence": 5, "jobId": "fixture-job", "timestamp": "2026-08-25T01:04:00Z", "type": "upload_progress", "provider": "dccloud", "stage": "mirror_upload", "fileName": "fixture-rom.zip", "fileIndex": 1, "fileCount": 1, "bytesTransferred": 2 * 1024**2, "totalBytes": 8 * 1024**2, "speedBytesPerSecond": 2 * 1024**2, "etaSeconds": 3, "percent": 25},
                        {"sequence": 6, "jobId": "fixture-job", "timestamp": "2026-08-25T01:04:05Z", "type": "upload_progress", "provider": "dccloud", "stage": "mirror_upload", "fileName": "fixture-rom.zip", "fileIndex": 1, "fileCount": 1, "bytesTransferred": 4 * 1024**2, "totalBytes": 8 * 1024**2, "speedBytesPerSecond": 2 * 1024**2, "etaSeconds": 2, "percent": 50},
                        {"sequence": 7, "jobId": "fixture-job", "timestamp": "2026-08-25T01:04:10Z", "type": "upload_progress", "provider": "dccloud", "stage": "mirror_upload", "fileName": "fixture-rom.zip", "fileIndex": 1, "fileCount": 1, "bytesTransferred": 6 * 1024**2, "totalBytes": 8 * 1024**2, "speedBytesPerSecond": 2 * 1024**2, "etaSeconds": 1, "percent": 75},
                        {"sequence": 8, "jobId": "fixture-job", "timestamp": "2026-08-25T01:04:15Z", "type": "upload_progress", "provider": "dccloud", "stage": "mirror_upload", "fileName": "fixture-rom.zip", "fileIndex": 1, "fileCount": 1, "bytesTransferred": 8 * 1024**2, "totalBytes": 8 * 1024**2, "speedBytesPerSecond": 2 * 1024**2, "etaSeconds": 0, "percent": 100},
                    ])
            else:
                active_job = None
                events = []
            payload = {
                "user": self._fixture_user(),
                "jobs": jobs,
                "activeJob": active_job,
                "events": [event for event in events if int(event["sequence"]) > after],
            }
            if not self.legacy_sync_contract:
                payload.update({
                    "page": 1,
                    "pageSize": 20,
                    "total": len(jobs),
                    "totalPages": 1,
                    "statusCounts": {
                        "active": sum(job.get("status") not in {"succeeded", "failed", "cancelled"} for job in all_jobs),
                        "succeeded": sum(job.get("status") == "succeeded" for job in all_jobs),
                        "failed": sum(job.get("status") in {"failed", "cancelled"} for job in all_jobs),
                    },
                })
            self._send(json.dumps(payload).encode(), "application/json")
            return
        if path == "/v1/me":
            self._send(json.dumps({"user": self._fixture_user(), "maintenance": {"enabled": self.maintenance_enabled, "message": "Đang nâng cấp Studio."}}).encode(), "application/json")
            return
        if path == "/v1/preset-labels" and self.api_enabled:
            self._send(json.dumps({"presetLabels": dict(type(self).preset_labels), "editable": self.admin_user}).encode(), "application/json")
            return
        if path == "/v1/rom-catalog":
            self._send(json.dumps({"releases": [{"id": "rom-fixture", "device": "OnePlus 13", "model": "CPH2653", "region": "EU", "version": "CPH2653_16.0.10.501(EX01)", "securityPatch": "2026-08-01", "sizeBytes": 8304912951, "sourceUrl": OPLUS_TEST_URI}, {"id": "rom-old", "device": "OnePlus 13", "region": "EU", "version": "CPH2653_16.0.9.500(EX01)", "sourceUrl": "https://cdn.example/old.zip"}]}).encode(), "application/json")
            return
        if path == "/v1/rom-catalog/devices":
            self._send(json.dumps({"devices": [
                {"id": "OP 13", "label": "OnePlus 13", "brand": "OnePlus", "regions": [{"code": "CN", "models": ["PJZ110"]}, {"code": "EU", "models": ["CPH2653"]}]},
                {"id": "OPPO FIND X8", "label": "OPPO Find X8", "brand": "OPPO", "regions": [{"code": "CN", "models": ["PKB110"]}]},
                {"id": "OP PAD2", "label": "OnePlus PAD2", "brand": "OnePlus", "regions": [{"code": "EU", "models": ["fixture-pad"]}]},
            ]}).encode(), "application/json")
            return
        if path == "/test/cache-count":
            self._send(json.dumps({"count": type(self).cache_clear_requests}).encode(), "application/json")
            return
        if path == "/v1/admin/users" and self.admin_user:
            user = {
                **self._fixture_user(), "telegramId": "88", "username": "new_user",
                "displayName": "New User", "role": "user",
                "currentActivity": {
                    "type": "build", "status": "running", "stage": "debloat",
                    "progress": .42, "jobId": "archived-job", "deviceName": "OnePlus Ace 5",
                    "productCode": "PKG110", "preset": "custom",
                    "modVersion": "ColorOS_16.0.8", "releaseVersion": "V4.0",
                    "startedAt": "2026-08-27T01:00:00Z", "updatedAt": "2026-08-27T01:04:00Z",
                },
            }
            user["currentActivities"] = [user["currentActivity"], {
                "type": "rom_search", "status": "completed", "device": "OP 13",
                "region": "EU", "latest": False, "resultCount": 2,
                "results": [{"version": "CPH2653_16.0.10.500(EX01)"}],
                "startedAt": "2026-08-27T01:02:00Z", "updatedAt": "2026-08-27T01:03:00Z",
            }]
            self._send(json.dumps({
                "users": [user, {
                    **self._fixture_user(), "telegramId": "89", "username": "rom_user",
                    "displayName": "ROM User", "role": "user",
                    "currentActivity": {
                        "type": "rom_search", "status": "searching",
                        "device": "OP 13", "region": "EU", "latest": True,
                        "startedAt": "2026-08-27T01:05:00Z", "updatedAt": "2026-08-27T01:05:00Z",
                    },
                }],
                "total": 7,
                "statusCounts": {"approved": 4, "pending": 1, "revoked": 2},
            }).encode(), "application/json")
            return
        if path == "/v1/admin/users/88/jobs" and self.admin_user:
            jobs = [{**self._fixture_archived_job(), "createdBy": {
                "telegramId": "88", "displayName": "New User", "username": "new_user"
            }}] if self.admin_job_scenario else []
            status_filter = str((parse_qs(urlsplit(self.path).query).get("status") or [""])[0])
            if status_filter == "active": jobs = [job for job in jobs if job["status"] not in {"succeeded", "failed", "cancelled"}]
            elif status_filter == "succeeded": jobs = [job for job in jobs if job["status"] == "succeeded"]
            elif status_filter == "failed": jobs = [job for job in jobs if job["status"] in {"failed", "cancelled"}]
            self._send(json.dumps({
                "jobs": jobs,
                "page": 1,
                "pageSize": 20,
                "total": len(jobs),
                "totalPages": max(1, (len(jobs) + 19) // 20),
                "statusCounts": {
                    "active": 0,
                    "succeeded": 1 if self.admin_job_scenario else 0,
                    "failed": 0,
                },
            }).encode(), "application/json")
            return
        if path == "/v1/admin/users/88" and self.admin_user:
            user = {
                **self._fixture_user(), "telegramId": "88", "username": "new_user",
                "displayName": "New User", "role": "user",
                "currentActivity": {
                    "type": "build", "status": "running", "stage": "debloat",
                    "progress": .42, "jobId": "archived-job", "deviceName": "OnePlus Ace 5",
                    "productCode": "PKG110", "preset": "custom",
                    "modVersion": "ColorOS_16.0.8", "releaseVersion": "V4.0",
                    "startedAt": "2026-08-27T01:00:00Z", "updatedAt": "2026-08-27T01:04:00Z",
                },
            }
            user["currentActivities"] = [user["currentActivity"], {
                "type": "rom_search", "status": "completed", "device": "OP 13",
                "region": "EU", "latest": False, "resultCount": 2,
                "results": [{"version": "CPH2653_16.0.10.500(EX01)"}],
                "startedAt": "2026-08-27T01:02:00Z", "updatedAt": "2026-08-27T01:03:00Z",
            }]
            jobs = [{**self._fixture_archived_job(), "createdBy": user}] if self.admin_job_scenario else []
            self._send(json.dumps({"user": user, "jobs": jobs, "events": [
                {
                    "type": "rom_search_completed", "createdAt": "2026-08-27T00:58:00Z",
                    "details": {
                        "device": "OP 13", "region": "EU", "latest": True,
                        "resultCount": 2, "durationMs": 1840,
                        "results": [
                            {"model": "CPH2653", "version": "CPH2653_16.0.10.500(EX01)"},
                            {"model": "CPH2653", "version": "CPH2653_16.0.9.500(EX01)"},
                        ],
                    },
                },
                {"type": "approved", "createdAt": "2026-08-25T01:00:00Z", "actorTelegramId": "42", "reason": "fixture"},
            ]}).encode(), "application/json")
            return
        if path == "/v1/jobs/fixture-job" and self.jobs_fixture:
            self._send(json.dumps(self._fixture_job()).encode(), "application/json")
            return
        if path == "/v1/jobs/fixture-job/events" and self.jobs_fixture:
            events = [
                {"sequence": 1, "jobId": "fixture-job", "timestamp": "2026-08-25T01:00:00Z", "type": "submitted", "runner": "github-hosted"},
                {"sequence": 2, "jobId": "fixture-job", "timestamp": "2026-08-25T01:01:00Z", "type": "plan", "steps": ["inspect_rom", "debloat", "apply_mod"]},
                {"sequence": 3, "jobId": "fixture-job", "timestamp": "2026-08-25T01:02:00Z", "type": "step", "step": "inspect_rom", "status": "success", "details": {"durationSeconds": 4.2, "phase": "Plus"}},
                {"sequence": 4, "jobId": "fixture-job", "timestamp": "2026-08-25T01:03:00Z", "type": "step", "step": "debloat", "status": "running", "message": "Đang quét 42 đường dẫn hệ thống", "details": {"removedCount": 17, "notFoundCount": 2, "phase": "Plus"}},
            ]
            self._send(json.dumps({"events": events}).encode(), "application/json")
            return
        if path == "/v1/jobs/archived-job" and self.jobs_fixture and self.click_other_job:
            self._send(json.dumps(self._fixture_archived_job()).encode(), "application/json")
            return
        if path == "/v1/jobs/archived-job/events" and self.jobs_fixture and self.click_other_job:
            self._send(json.dumps({"events": [
                {"sequence": 1, "jobId": "archived-job", "timestamp": "2026-08-24T01:00:00Z", "type": "submitted"},
                {"sequence": 2, "jobId": "archived-job", "timestamp": "2026-08-24T01:04:00Z", "type": "step", "step": "package", "status": "success"},
            ]}).encode(), "application/json")
            return
        if path == "/v1/drafts/source" and self.server_draft_fallback:
            self._send(json.dumps({"uri": self.source_uri}).encode(), "application/json")
            return
        self._send(b"not found", "text/plain", 404)

    @classmethod
    def _fixture_job(cls) -> dict[str, object]:
        artifacts = (
            [
                {
                    "name": "Wukong_Lite_V6.0_PKG110.zip",
                    "size_bytes": 7 * 1024**3,
                    "sha256": "a" * 64,
                    "downloadAvailable": True,
                    "publicUrl": "https://drive.google.com/open?id=fixture-artifact",
                },
                {
                    "name": "Wukong_Plus_V6.0_PKG110.zip",
                    "size_bytes": 8 * 1024**3,
                    "sha256": "b" * 64,
                    "downloadAvailable": True,
                    "publicUrl": "https://drive.google.com/open?id=fixture-artifact-plus",
                },
            ]
            if cls.artifact_fixture
            else []
        )
        return {
            "job_id": "fixture-job",
            "status": "succeeded" if cls.artifact_fixture else "running",
            "stage": "complete" if cls.artifact_fixture else "debloat",
            "progress": 1 if cls.artifact_fixture else 0.42,
            "runner": "github-hosted", "created_at": "2026-08-25T01:00:00Z",
            "rom_metadata": {
                "productName": "PKG110",
                "device": "OP5D2BL1",
                "version": "PKG110_16.0.10.500(CN01)",
                "androidVersion": "16",
                "securityPatch": "2026-08-01",
                "buildDate": "2026-08-11 09:38:18",
            },
            "recipe": {
                "device": "PKG110", "source": {"sizeBytes": 8680370027, "metadata": {"productName": "PKG110", "version": "stale", "androidVersion": "15"}},
                "build": {"preset": "both", "modVersion": "ColorOS_16.0.10", "modReleaseVersion": "V6.0", "mods": ["Gapps", "WK_Manager"]},
            },
            "artifacts": artifacts,
        }

    @classmethod
    def _fixture_user(cls) -> dict[str, object]:
        return {
            "telegramId": "42", "username": "fixture", "displayName": "Fixture User",
            "photoUrl": "/fixture-avatar.svg",
            "accessStatus": "pending" if cls.pending_user else "approved", "role": "admin" if cls.admin_user else "user", "buildCredits": 3,
            "unlimited": cls.admin_user, "miniAppOpenCount": 2, "jobCount": 1,
            "lifetimeGranted": 5, "lifetimeUsed": 2, "language": "vi", "platform": "android", "appVersion": "1.0",
            "firstSeenAt": "2026-08-24T01:00:00Z", "lastSeenAt": "2026-08-25T01:00:00Z",
        }

    @classmethod
    def _fixture_archived_job(cls) -> dict[str, object]:
        return {
            "job_id": "archived-job",
            "status": "succeeded",
            "stage": "complete",
            "progress": 1,
            "runner": "github-hosted",
            "created_at": "2026-08-24T01:00:00Z",
            "recipe": {
                "device": "PKG110",
                "source": {
                    "sizeBytes": 8680370027,
                    "metadata": {
                        "productName": "PKG110",
                        "version": "ARCHIVED_16.0.8.300(CN01)",
                        "androidVersion": "16",
                    },
                },
                "build": {
                    "preset": "custom",
                    "modVersion": "ColorOS_16.0.8",
                    "modReleaseVersion": "V4.0",
                    "mods": ["WK_Manager"],
                },
            },
            "artifacts": [],
        }

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        if path == "/v1/jobs" and self.api_enabled:
            length = int(self.headers.get("Content-Length", "0"))
            type(self).submitted_recipe = json.loads(self.rfile.read(length) or b"{}")
            self._send(json.dumps({"job_id": "submitted-custom-job", "status": "queued", "stage": "queued", "progress": 0}).encode(), "application/json", 201)
            return
        if path == "/v1/sources/resolve":
            self._send(json.dumps({"resolvedUrl": "https://cdn.allawnfs.com/rom.zip?Signature=fixture", "signedUrlExpiresAt": 9999999999}).encode(), "application/json")
            return
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
        if path == "/v1/session/open" and self.api_enabled:
            self._send(json.dumps({"user": self._fixture_user(), "maintenance": {"enabled": self.maintenance_enabled, "message": "Đang nâng cấp Studio."}}).encode(), "application/json")
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
            source_metadata = dict(self.source_metadata)
            if self.probe_zip_payload is not None:
                source_metadata.update({
                    "filename": "fixture.zip",
                    "sizeBytes": len(self.probe_zip_payload),
                    "productName": None,
                    "device": None,
                    "version": None,
                    "androidVersion": None,
                    "securityPatch": None,
                    "buildDate": None,
                    "otaType": None,
                    "deepInspected": False,
                    "rangeSession": {
                        "url": f"http://127.0.0.1:{self.server.server_port}/probe-range",
                    },
                })
            self._send(json.dumps(source_metadata).encode(), "application/json")
            return
        if path == "/v1/cache/clear" and self.api_enabled and self.admin_user:
            type(self).cache_clear_requests += 1
            self._send(json.dumps({"entryCount": type(self).cache_clear_requests, "totalBytes": 0}).encode(), "application/json")
            return
        self._send(b'{"error":"not found"}', "application/json", 404)

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        if path == "/v1/preset-labels" and self.api_enabled and self.admin_user:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            type(self).preset_labels = dict(payload.get("presetLabels") or {})
            self._send(json.dumps({"presetLabels": dict(type(self).preset_labels)}).encode(), "application/json")
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
    probe_zip_payload: bytes | None = None,
    catalog_mod_versions: tuple[str, ...] = ("ColorOS_16.0.9",),
    catalog_mods_by_version: dict[str, list[str]] | None = None,
    initial_view: str = "",
    jobs_fixture: bool = False,
    upload_progress_fixture: bool = False,
    legacy_sync_contract: bool = False,
    click_job_log: bool = False,
    click_mod_toggle: bool = False,
    click_other_job: bool = False,
    artifact_fixture: bool = False,
    click_artifact_actions: bool = False,
    click_profile: bool = False,
    click_theme_dark: bool = False,
    system_theme_change: bool = False,
    click_cache_flow: bool = False,
    click_admin_user: bool = False,
    admin_job_scenario: bool = False,
    click_admin_action: bool = False,
    exercise_batch_controls: bool = False,
    exercise_custom_release: bool = False,
    exercise_custom_recipe: bool = False,
    exercise_dock_header: bool = False,
    admin_user: bool = False,
    pending_user: bool = False,
    library_scenario: str = "",
    maintenance_enabled: bool = False,
    screenshot_output: Path | None = None,
    window_width: int = 390,
    window_height: int = 1400,
    page_action=None,
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
            "probe_zip_payload": probe_zip_payload,
            "catalog_mod_versions": catalog_mod_versions,
            "catalog_mods_by_version": catalog_mods_by_version,
            "jobs_fixture": jobs_fixture,
            "upload_progress_fixture": upload_progress_fixture,
            "legacy_sync_contract": legacy_sync_contract,
            "click_job_log": click_job_log,
            "click_mod_toggle": click_mod_toggle,
            "click_other_job": click_other_job,
            "artifact_fixture": artifact_fixture,
            "click_artifact_actions": click_artifact_actions,
            "click_profile": click_profile,
            "click_theme_dark": click_theme_dark,
            "system_theme_change": system_theme_change,
            "click_cache_flow": click_cache_flow,
            "click_admin_user": click_admin_user,
            "admin_job_scenario": admin_job_scenario,
            "click_admin_action": click_admin_action,
            "exercise_batch_controls": exercise_batch_controls,
            "exercise_custom_release": exercise_custom_release,
            "exercise_custom_recipe": exercise_custom_recipe,
            "preset_labels": {"lite": "Lite", "plus": "Plus", "custom": "Custom"},
            "exercise_dock_header": exercise_dock_header,
            "cache_clear_requests": 0,
            "admin_user": admin_user,
            "pending_user": pending_user,
            "library_scenario": library_scenario,
            "maintenance_enabled": maintenance_enabled,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from playwright.sync_api import sync_playwright
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=chrome)
            try:
                page = browser.new_page(viewport={"width": window_width, "height": window_height}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(launch_url, wait_until="networkidle")
                wait_ms = 7000 if exercise_dock_header else 6000 if admin_job_scenario else 2200
                page.wait_for_timeout(wait_ms)
                if page_action:
                    page_action(page)
                assert page.evaluate("innerWidth") == window_width, "Browser viewport must match the test case"
                page.evaluate("""() => {
                    document.body.dataset.viewportWidth = String(innerWidth);
                    document.body.dataset.documentWidth = String(document.documentElement.scrollWidth);
                }""")
                screenshot = page.screenshot(path=str(screenshot_output) if screenshot_output else None)
                assert not errors, errors
                return page.content(), len(screenshot)
            finally:
                browser.close()
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
                                "sizeBytes": 4,
                                "archive": {
                                    "uri": "drive:MOD/ColorOS_16.0.9.tar.zst",
                                    "sha256": "a" * 64,
                                    "md5": "b" * 32,
                                    "sizeBytes": 1,
                                },
                                "files": [
                                    {"path": "Gapps/my_product/app.apk", "sha256": "c" * 64, "sizeBytes": 1},
                                    {"path": "GlobalSearch/my_stock/app.apk", "sha256": "2" * 64, "sizeBytes": 1},
                                    {"path": "Unsafe/vendor/app.apk", "sha256": "3" * 64, "sizeBytes": 1},
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
        self.assertEqual(
            ["Gapps", "GlobalSearch", "WK_Installer", "WK_Manager"],
            payload["modsByVersion"]["ColorOS_16.0.9"],
        )
        self.assertEqual(
            ["Gapps", "GlobalSearch", "WK_Installer", "WK_Manager"],
            payload["presetDefaultsByVersion"]["ColorOS_16.0.9"]["both"],
        )
        self.assertIn("sync_configs", [item["id"] for item in payload["pipelineSteps"]])
        self.assertNotIn("sync_metadata", [item["id"] for item in payload["pipelineSteps"]])
        self.assertEqual("PKG110", payload["devices"][0]["product"])
        self.assertTrue(exported.endswith("\n"))

    def test_static_app_exposes_bilingual_build_and_job_contract(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = _app_source()

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
            "job-history-tabs",
            "job-history-filters",
            "job-history-search",
            "job-history-preset",
            "job-history-mod",
            "job-history-from",
            "job-history-to",
            "job-history-pagination",
            "job-page-buttons",
            "debloat-editor",
            "save-debloat-paths",
            "cancel-debloat-paths",
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
        self.assertIn("state.debloatPaths", script)
        self.assertIn("resetJobDraft", script)
        self.assertIn('apiRequest("/v1/drafts/source", { method: "DELETE" })', script)
        self.assertNotIn('id="workspace-estimate"', html)
        self.assertIn("catalog.json", script)
        self.assertIn("const translations", script)
        self.assertNotIn("source_mirror", script)
        self.assertNotIn("artifact_publish", script)
        self.assertIn("loadJobs", script)
        self.assertIn("scheduleJobsPoll", script)
        self.assertIn("loadMoreAudit", script)
        self.assertIn(
            "/events?cursor=${encodeURIComponent(auditCursor)}&limit=100",
            script,
        )
        self.assertIn("renderArtifacts", script)
        self.assertIn("dcCloudMirrorRepairing", script)
        self.assertIn("function jobNeedsMirrorPoll", script)
        self.assertIn("jobShouldPoll(selectedJob)", script)
        self.assertIn("upload_progress", script)
        self.assertIn("speedBytesPerSecond", script)
        self.assertIn("event-group", script)
        self.assertIn("activeEventsJobId", script)
        self.assertIn("jobDetailRequestId", script)
        self.assertIn("function jobHistoryParams", script)
        self.assertIn("/v1/sync?${params.toString()}", script)
        self.assertIn("const selectedJobId = state.activeJobId", script)
        self.assertIn("loadJobDetail(selectedJobId)", script)
        self.assertIn("function renderPageButtons", script)
        self.assertIn("setTimeout(reloadJobHistory, 300)", script)
        self.assertIn("const unique = new Map()", script)
        self.assertNotIn("githubRunLink", script)
        self.assertNotIn("external_run_id", script)
        self.assertNotIn("xuankhanh24", script)
        self.assertNotIn("github.com", script)

        exporter = (ROOT / "tools" / "export_mini_app_catalog.py").read_text(encoding="utf-8")
        self.assertIn("modReleaseVersions", exporter)

    def test_mini_app_maps_windows_operating_surfaces_without_saas_chrome(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = _style_source()
        script = _app_source()

        for surface in ("build", "jobs", "catalog", "system"):
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
            "mod-release-version-input",
            "custom-preset-label-input",
            "apply-custom-preset-label",
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
        self.assertIn("backdrop-filter", styles)
        self.assertIn("liquid-lens", styles)
        bottom_nav = re.search(r'<nav class="bottom-nav".*?</nav>', html, re.DOTALL)
        self.assertIsNotNone(bottom_nav)
        bottom_nav_html = bottom_nav.group(0)
        self.assertEqual(["build", "jobs", "profile", "catalog", "system"], re.findall(r'data-nav="([^"]+)"', bottom_nav_html))
        self.assertEqual(4, bottom_nav_html.count('class="nav-icon"'))
        self.assertNotRegex(bottom_nav_html, r"<b>\d{2}</b>")
        self.assertNotIn(".bottom-nav button.active::before", styles)
        self.assertIn("updateDispatchFab", script)
        self.assertIn('data-i18n="fabBuild">Build', html)
        self.assertIn("bindLiquidBottomTabs", script)
        self.assertIn("--liquid-press", styles)
        self.assertIn("chromatic", (ROOT / "DESIGN.md").read_text(encoding="utf-8"))
        self.assertIn("prefersReducedMotion", script)
        self.assertIn('"Geist Sans"', styles)
        self.assertIn('"Geist Mono"', styles)
        self.assertIn("--accent:", styles)
        self.assertIn("--success:", styles)
        self.assertIn("--radius-sm: 8px", styles)
        self.assertIn("repeat(var(--dock-slot-count),minmax(0,1fr))", styles)
        self.assertIn(".source-input-field, .source-input-head { min-width: 0; }", styles)

    def test_mini_app_exposes_branded_liquid_profile_theme_and_cache_safety(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = _style_source()
        script = _app_source()

        bottom_nav = re.search(r'<nav class="bottom-nav".*?</nav>', html, re.DOTALL)
        self.assertIsNotNone(bottom_nav)
        dock = bottom_nav.group(0)
        self.assertEqual(["0", "1", "2", "3", "4"], re.findall(r'data-slot="([^"]+)"', dock))
        self.assertIn('id="dock-profile"', dock)
        self.assertIn('data-nav="profile"', dock)
        self.assertNotIn('id="header-profile"', html)
        self.assertIn('src="./WukongStudio.svg"', html)
        self.assertEqual(
            (ROOT / "desktop" / "WukongStudio.App" / "Assets" / "WukongStudio.svg").read_text(encoding="utf-8"),
            (ROOT / "telegram_mini_app" / "WukongStudio.svg").read_text(encoding="utf-8"),
        )
        self.assertIn('class="view profile-view" id="profile"', html)
        self.assertNotIn('id="profile-dialog"', html)
        self.assertIn('id="cache-clear-dialog"', html)
        self.assertIn('id="theme-selector"', html)
        self.assertIn('data-theme-value="system"', html)
        self.assertIn('data-theme-value="light"', html)
        self.assertIn('data-theme-value="dark"', html)
        self.assertEqual(
            re.findall(r'href="(\./assets/[^"]+)"', html),
            ["./assets/fonts/geist-sans-variable.woff2"],
        )
        self.assertNotIn("ROM STUDIO / HYBRID", html)
        self.assertIn("wukong-theme", script)
        self.assertIn("renderProfileView", script)
        self.assertIn("openCacheClearDialog", script)
        self.assertIn("miniAppOpenCount", script)
        self.assertIn('!["miniAppOpenCount", "photoUrl"].includes(key)', script)
        self.assertIn("greetingTimer", script)
        self.assertIn("updateMastheadScroll", script)
        self.assertIn("HapticFeedback?.selectionChanged", script)
        self.assertIn("Chỉ quản trị viên", html)
        self.assertIn(
            "activateTelegramApp();\n    bindTelegramThemeEvents();\n    applyTheme(state.theme);",
            script,
        )
        self.assertIn("--dock-slot-count:5", styles)
        self.assertIn(".profile-scene-backdrop", styles)
        self.assertIn("backdrop-filter:blur(10px)", styles)
        self.assertIn('data-color-scheme="dark"', styles)
        self.assertIn('id="greeting-mark"', html)
        self.assertNotIn('id="greeting-emoji"', html)
        self.assertIn('class="language-button"', html)
        self.assertNotIn(".wordmark > span { display:none; }", styles)
        self.assertIn(".bottom-nav.profile-active:not(.profile-dragging) .liquid-lens", styles)
        self.assertIn(".bottom-nav .dock-profile.active::before", styles)
        self.assertIn("updateGreetingOverflow", script)
        self.assertIn('window.addEventListener("resize"', script)
        self.assertIn("--avatar-image", script)
        self.assertIn("profile-dragging", script)
        self.assertIn("easeOutQuint", script)
        self.assertNotIn("velocity = velocity * .72", script)
        self.assertNotIn('emoji: "🚀"', script)
        self.assertIn(':root[data-color-scheme="dark"] .masthead', styles)
        self.assertIn(':root[data-color-scheme="dark"] .bottom-nav', styles)

    def test_admin_system_surface_renders_user_access_and_quota_ledger(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="system",
            admin_user=True,
        )

        self.assertIn('id="user-admin"', dom)
        self.assertNotRegex(dom, r'id="user-admin"[^>]* hidden')
        self.assertIn("Người dùng &amp; lượt build", dom)
        self.assertIn('id="user-total-count">7</strong>', dom)
        self.assertIn('id="user-approved-count">4</strong>', dom)
        self.assertIn('id="user-pending-count">1</strong>', dom)
        self.assertIn('id="user-revoked-count">2</strong>', dom)
        self.assertIn("Đã cấp quyền", dom)
        self.assertIn("Chờ cấp quyền", dom)
        self.assertNotRegex(dom, r'id="admin-maintenance"[^>]* hidden')
        self.assertIn("New User", dom)
        self.assertIn("@new_user", dom)
        self.assertIn('id="greeting-carousel"', dom)
        self.assertIn("Không giới hạn", dom)
        self.assertIn("Không giới hạn lượt còn lại", dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_maintenance_gate_and_admin_control_are_wired_to_the_public_api(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = _style_source()
        script = _app_source()

        self.assertIn('id="maintenance-gate"', html)
        self.assertIn('id="maintenance-toggle"', html)
        self.assertIn('id="maintenance-message-input"', html)
        self.assertIn('body.maintenance-limited', styles)
        self.assertIn('apiRequest("/v1/system/maintenance"', script)
        self.assertIn('state.maintenance = payload.maintenance', script)

    def test_rom_catalog_selection_uses_the_existing_source_probe_flow(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = _app_source()

        self.assertIn('id="open-rom-catalog"', html)
        self.assertIn('id="rom-catalog-results"', html)
        self.assertIn('apiRequest(`/v1/rom-catalog?', script)
        self.assertIn('source.value = release.sourceUrl;', script)
        self.assertIn("scheduleSourceProbe();", script)

    def test_library_search_selects_rom_and_returns_to_studio(self) -> None:
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, library_scenario="select")
        self.assertIn('data-library-title="Thư viện"', dom)
        self.assertIn('data-rom-in-library="true"', dom)
        self.assertIn('data-technical-visible="true"', dom)
        self.assertIn('data-rom-results="1"', dom)
        self.assertNotIn('id="rom-model-filter"', dom)
        self.assertIn('data-rom-version-count="2"', dom)
        self.assertIn('data-old-version-selected="true"', dom)
        self.assertIn('data-resolved-rom-link="https://cdn.allawnfs.com/rom.zip?Signature=fixture"', dom)
        self.assertIn('data-rom-copied="https://component-ota-cn.allawntech.com/downloadCheck?', dom)
        self.assertIn('data-filtered-devices="1"', dom)
        self.assertIn('data-natural-device-match="true"', dom)
        self.assertIn('data-device-label="OnePlus 13"', dom)
        self.assertIn('data-device-regions=",CN,EU"', dom)
        self.assertIn('data-selected-view="build"', dom)
        self.assertIn('data-selected-source="https://component-ota-cn.allawntech.com/downloadCheck?', dom)
        self.assertRegex(dom, r'id="source-product-detected"[^>]*>PKG110')

    def test_user_sees_maintenance_gate_but_admin_keeps_workspace(self) -> None:
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, maintenance_enabled=True)
        self.assertRegex(dom, r'<body class="[^"]*maintenance-limited')
        self.assertNotRegex(dom, r'id="maintenance-gate"[^>]*hidden')
        self.assertIn('Đang nâng cấp Studio.', dom)
        admin, _ = _render_mini_app_in_chrome(api_enabled=True, maintenance_enabled=True, admin_user=True)
        self.assertNotRegex(admin, r'<body class="[^"]*maintenance-limited')
        self.assertRegex(admin, r'id="maintenance-gate"[^>]*hidden')

    def test_rom_resolve_timeout_is_retryable(self) -> None:
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, library_scenario="timeout")
        self.assertIn('data-resolve-timeout-recovered="true"', dom)

    def test_admin_user_opens_as_a_system_page_in_dark_mode(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = _style_source()
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="system",
            admin_user=True,
            click_admin_user=True,
            click_theme_dark=True,
        )

        self.assertIn('id="admin-user-page"', html)
        self.assertNotIn('id="user-detail-dialog"', html)
        self.assertIn('data-admin-user-page-open="true"', dom)
        self.assertIn('data-admin-user-dialog-present="false"', dom)
        self.assertRegex(dom, r'<section class="[^"]*admin-user-open[^"]*" id="system"')
        self.assertIn("New User", dom)
        self.assertIn(':root[data-color-scheme="dark"] .user-dialog', styles)
        self.assertIn(':root[data-color-scheme="dark"] .confirm-dialog', styles)
        script = _app_source()
        self.assertNotIn("window.prompt", script)
        self.assertNotIn("window.confirm", script)
        self.assertGreater(screenshot_size, 10_000)

    def test_admin_sensitive_action_uses_themed_dialog(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="system",
            admin_user=True,
            click_admin_user=True,
            click_admin_action=True,
            click_theme_dark=True,
        )

        self.assertIn('data-admin-action-dialog-open="true"', dom)
        self.assertIn('data-admin-action-value-visible="true"', dom)
        self.assertRegex(dom, r'id="admin-action-dialog"[^>]* open')
        self.assertIn("Trừ lượt", dom)

    def test_light_mode_admin_primary_actions_keep_readable_contrast(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="system",
            admin_user=True,
            click_admin_user=True,
            click_admin_action=True,
        )

        self.assertIn('data-batch-launch-color="rgb(255, 255, 255)"', dom)
        self.assertIn('data-batch-launch-background="rgb(49, 95, 158)"', dom)
        self.assertIn('data-admin-action-confirm-color="rgb(255, 255, 255)"', dom)
        self.assertIn('data-admin-action-confirm-background="rgb(49, 95, 158)"', dom)

    def test_mobile_surface_is_distilled_and_maintenance_is_admin_only(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        styles = _style_source()
        script = _app_source()
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, initial_view="system")

        self.assertNotIn('data-i18n="buildIntro"', html)
        self.assertNotIn('data-i18n="jobsIntro"', html)
        self.assertNotIn('data-i18n="catalogIntro"', html)
        self.assertNotIn('data-i18n="systemIntro"', html)
        self.assertNotIn('class="process-key"', html)
        self.assertIn('id="admin-maintenance" hidden', html)
        self.assertRegex(dom, r'id="admin-maintenance"[^>]* hidden')
        self.assertIn('data-i18n="fabBuild">Build', html)
        self.assertIn('mods.className = "job-mod-grid"', script)
        self.assertNotIn('input.focus({ preventScroll: true });\n  toast(t("sourceCleared"))', script)
        self.assertIn('.bottom-nav .liquid-surface::before { display:none; }', styles)
        self.assertIn('class="dock-shell"', html)
        self.assertIn('dock-shell-clip', html)
        self.assertIn('id="dock-shell-path"', html)
        self.assertIn('class="dock-rim"', html)
        self.assertIn("updateDockShellPath", script)
        self.assertIn('background:var(--dock-glass-bg)', styles)
        self.assertIn('backdrop-filter:blur(10px) saturate(1.5) contrast(1.08)', styles)
        self.assertIn('--dock-foreground: #171b22', styles)
        self.assertIn('--dock-foreground: #f5f7fb', styles)
        self.assertIn('bottom:calc(132px + env(safe-area-inset-bottom))', styles)
        self.assertIn('.bottom-nav button:not(.dock-profile) { top:7px; height:56px; min-height:56px;', styles)
        self.assertIn("const bodyTop = 32;", script)
        self.assertIn("const capRadius = Math.min(42", script)
        self.assertIn("const capCenterY = 45;", script)
        self.assertIn("const capShoulder = capRadius + 10;", script)
        self.assertIn("const sideRadius = (bodyBottom - bodyTop) / 2;", script)
        self.assertIn("`A ${sideRadius} ${sideRadius} 0 0 1", script)
        self.assertIn('.profile-highlight { text-align:center; }', styles)
        self.assertIn('$("#admin-maintenance").hidden = true;', script)
        self.assertIn("payload.statusCounts", script)
        self.assertNotIn("Promise.allSettled", script)
        self.assertNotIn('data-i18n="secretBoundary"', html)

    def test_profile_sheet_excludes_open_count_and_theme_can_be_overridden(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            click_profile=True,
            click_theme_dark=True,
        )

        self.assertIn('data-profile-opened="true"', dom)
        self.assertIn('data-selected-theme="dark"', dom)
        self.assertIn('data-active-profile-tab="profile"', dom)
        self.assertIn('data-profile-lens-suppressed="true"', dom)
        self.assertIn('data-profile-halo-active="true"', dom)
        profile = re.search(r'<section class="view profile-view active" id="profile".*?</section>\s*</main>', dom, re.DOTALL)
        self.assertIsNotNone(profile)
        self.assertIn("Fixture User", profile.group(0))
        self.assertNotIn("2 lần mở", profile.group(0))
        self.assertNotIn("miniAppOpenCount", profile.group(0))
        self.assertGreater(screenshot_size, 10_000)

    def test_system_theme_tracks_telegram_theme_changes_on_mobile(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            system_theme_change=True,
        )

        self.assertIn('data-selected-theme-mode="system"', dom)
        self.assertIn('data-system-theme-after-telegram-change="dark"', dom)
        self.assertRegex(dom, r'<html[^>]*data-theme="system"[^>]*data-color-scheme="dark"')
        self.assertRegex(dom, r'<body[^>]*data-telegram-header-color="#1d2025"')

    def test_cache_clear_requires_dialog_confirmation_and_submits_once(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="system",
            admin_user=True,
            click_cache_flow=True,
        )

        self.assertIn('data-cache-dialog-opened="true"', dom)
        self.assertIn('data-cache-cancelled="true"', dom)
        self.assertIn('data-cache-request-count="1"', dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_dock_header_greeting_haptics_and_assets_work_together(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            exercise_dock_header=True,
        )
        script = _app_source()

        self.assertIn('data-active-dock-tab="jobs"', dom)
        self.assertIn('data-masthead-progress="', dom)
        self.assertIn('root.setProperty("--masthead-scroll", progress.toFixed(3))', script)
        self.assertIn(
            'window.addEventListener("scroll", updateMastheadScroll, { passive: true })',
            script,
        )
        self.assertIn('data-greeting-initial="', dom)
        self.assertIn("state.greetingTimer = window.setInterval", script)
        self.assertIn("}, 6000);", script)
        self.assertIn('data-haptic-selections="1"', dom)
        self.assertIn('data-broken-assets="0"', dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_build_surface_keeps_build_workflow_separate_from_catalog_and_system(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = _app_source()

        self.assertNotIn("Build từ Telegram.", html)
        self.assertNotIn("Build from Telegram.", script)
        self.assertNotIn('id="source-sha256"', html)
        self.assertNotIn("source_mirror", script)
        self.assertNotIn("artifact_publish", script)
        self.assertIn('id="mod-release-version"', html)
        self.assertIn('id="mod-release-version-input" maxlength="64"', html)
        self.assertNotIn('id="custom-mod-version-editor"', html)
        self.assertNotIn('id="custom-mod-version-input"', html)
        self.assertIn('id="catalog-preset-admin"', html)
        self.assertIn('id="admin-preset-label-lite" maxlength="64"', html)
        self.assertIn('id="admin-preset-label-plus" maxlength="64"', html)
        self.assertIn('id="admin-preset-label-custom" maxlength="64"', html)
        self.assertIn('apiRequest("/v1/preset-labels"', script)
        self.assertIn('modVersion: selectedModVersion()', script)
        self.assertIn("build.modReleaseVersion", script)
        self.assertIn("event-group", script)
        self.assertIn("viewFullLog", script)
        self.assertIn("eventDetailEntries", script)
        self.assertIn("events.slice(-8)", script)

    def test_jobs_full_log_expands_named_steps_and_structured_details(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            click_job_log=True,
        )

        self.assertIn('class="job-events expanded"', dom)
        self.assertIn('class="job-mod-grid"', dom)
        self.assertRegex(dom, r'class="job-mod-grid"[^>]*>.*?<span>Gapps</span>.*?<span>WK_Manager</span>')
        self.assertIn("Toàn bộ nhật ký build", dom)
        self.assertIn("Gỡ ứng dụng thừa · Đang thực hiện", dom)
        self.assertIn("Đang quét 42 đường dẫn hệ thống", dom)
        self.assertIn("removed Count", dom)
        self.assertIn("17", dom)
        self.assertIn("Thu gọn nhật ký", dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_artifacts_use_direct_cloud_links_with_open_and_copy_actions(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            artifact_fixture=True,
            click_artifact_actions=True,
        )

        self.assertIn("Mở trên Google Drive", dom)
        self.assertIn("Sao chép link tải", dom)
        self.assertIn("Google Drive", dom)
        self.assertIn(
            'data-opened-artifact="https://drive.google.com/open?id=fixture-artifact"',
            dom,
        )
        self.assertIn(
            'data-copied-artifact="https://drive.google.com/open?id=fixture-artifact"',
            dom,
        )
        self.assertNotIn("/v1/jobs/fixture-job/download", dom)
        self.assertNotIn("onrender.com", dom)
        script = _app_source()
        self.assertIn('if (!copied) throw new Error("Clipboard copy failed")', script)
        self.assertGreater(screenshot_size, 10_000)

    def test_live_upload_log_compacts_repeated_updates_into_a_progress_card(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            upload_progress_fixture=True,
        )

        self.assertEqual(1, dom.count('class="event-upload-card"'))
        self.assertIn('data-progress-percent="100"', dom)
        self.assertIn("8.00 MiB", dom)
        self.assertIn("2.00 MiB/s", dom)
        self.assertIn("DC Cloud", dom)
        self.assertIn("4 lần cập nhật đã gộp", dom)
        self.assertIn("5 thẻ / 8 cập nhật", dom)
        self.assertGreater(screenshot_size, 10_000)

        expanded, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            upload_progress_fixture=True,
            click_job_log=True,
        )
        self.assertNotIn('class="event-upload-card"', expanded)
        self.assertGreaterEqual(expanded.count('class="event-upload_progress"'), 4)

    def test_completed_job_uses_terminal_metadata_and_lists_each_artifact_size(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            artifact_fixture=True,
        )

        for value in (
            "<small>Tên thiết bị</small><strong>OnePlus Ace 5</strong>",
            "<small>Mã sản phẩm</small><strong>PKG110</strong>",
            "<small>Mã thiết bị</small><strong>OP5D2BL1</strong>",
            "PKG110_16.0.10.500(CN01)",
            "2026-08-01",
            "2026-08-11 09:38:18",
            "<strong>Wukong_Lite_V6.0_PKG110.zip</strong><span>7.00 GiB</span>",
            "<strong>Wukong_Plus_V6.0_PKG110.zip</strong><span>8.00 GiB</span>",
            "Dung lượng ROM nguồn",
        ):
            self.assertIn(value, dom)
        self.assertNotIn('class="job-facts job-edition-facts"', dom)
        self.assertNotIn("<small>Lite</small>", dom)
        self.assertNotIn("<small>Plus</small>", dom)
        self.assertLess(
            dom.index('<section class="job-artifacts">'),
            dom.index('<div class="job-controls">'),
        )
        self.assertLess(
            dom.index('<div class="job-controls">'),
            dom.index('<section class="job-events">'),
        )
        self.assertNotIn("<small>Upload gần nhất</small>", dom)
        self.assertNotIn("<h2>stale</h2>", dom)

    def test_smart_source_recognizes_unresolved_ota_without_exposing_signed_url(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = _app_source()
        styles = _style_source()

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
        # Explicit Library Resolve may reveal a temporary link; automatic Smart Source must not.
        probe_start = script.index("async function probeSourceViaBackend")
        probe_end = script.index("const ZIP_METADATA_SUFFIXES", probe_start)
        self.assertNotIn("resolvedUrl", script[probe_start:probe_end])
        self.assertNotIn("Signature=signed", html + script)
        self.assertNotIn("OPlus chưa resolve và Drive", html + script)
        self.assertNotIn("unresolved OPlus links and Drive", html + script)
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
        self.assertIn('<strong id="launch-summary">PKG110 · V5.0 / Plus / GitHub Auto</strong>', dom)
        self.assertIn('<li id="check-device" class="complete">', dom)
        self.assertIn('<li id="check-source" class="complete">', dom)
        self.assertIn('<li id="check-api" class="complete">', dom)
        self.assertRegex(dom, r'id="source-facts"(?![^>]* hidden)')
        submit_tag = dom.split('id="submit-recipe"', 1)[1].split(">", 1)[0]
        self.assertNotIn("disabled", submit_tag)
        self.assertGreater(screenshot_size, 10_000)

    def test_optional_rom_headers_do_not_mark_core_metadata_as_incomplete(self) -> None:
        metadata = {
            **OPLUS_TEST_METADATA,
            "md5": None,
            "lastModified": None,
        }

        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            source_metadata=metadata,
        )

        self.assertIn("12/14 thông số", dom)
        self.assertRegex(dom, r'class="[^"]*analyzed[^"]*" id="source-state"')
        self.assertRegex(dom, r'<dd id="source-md5" data-empty="true"[^>]*>—</dd>')
        self.assertRegex(dom, r'<dd id="source-last-modified" data-empty="true"[^>]*>—</dd>')

    def test_one_unreadable_metadata_file_does_not_discard_valid_rom_fields(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            source_metadata={
                **OPLUS_TEST_METADATA,
                "md5": None,
                "lastModified": None,
            },
            probe_zip_payload=_partial_metadata_zip(),
        )

        for value in (
            "PKG110",
            "OP5D2BL1",
            "PKG110_16.0.9.400(CN01)",
            "2026-07-01",
            "12/14 thông số",
            "Đã đọc metadata trong ZIP",
        ):
            self.assertIn(value, dom)
        self.assertRegex(dom, r'class="[^"]*analyzed[^"]*" id="source-state"')

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

        self.assertIn('class="access-limited"', dom)
        self.assertIn("Kết nối tài khoản để tiếp tục", dom)
        self.assertIn('id="refresh-access"', dom)
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

        self.assertIn('class="access-limited"', dom)
        self.assertIn("Kết nối tài khoản để tiếp tục", dom)
        self.assertNotIn("14/14 thông số", dom)

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

        self.assertIn("Kết nối tài khoản để tiếp tục", dom)
        self.assertIn('id="refresh-access"', dom)
        self.assertNotIn("Mini App API chưa được cấu hình", dom)

    def test_pending_user_only_sees_account_and_approval_waiting_gate(self) -> None:
        dom, _ = _render_mini_app_in_chrome(api_enabled=True, pending_user=True)

        self.assertIn('class="access-limited"', dom)
        self.assertIn("Chờ quản trị viên cấp quyền", dom)
        self.assertIn("Fixture User", dom)
        self.assertIn("@fixture", dom)
        self.assertIn('<dd id="access-id">42</dd>', dom)
        self.assertIn('class="profile-avatar profile-avatar-large"', dom)
        self.assertNotIn("2 lần mở", dom)

    def test_smart_source_uses_server_probe_instead_of_cross_origin_browser_fetch(self) -> None:
        script = _app_source()

        self.assertIn("probeSourceViaBackend", script)
        self.assertNotIn("fetch(uri", script)

    def test_vercel_publish_binds_the_api_without_github_pages(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "telegram-mini-app-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("WUKONG_TELEGRAM_MINI_APP_API_URL", workflow)
        self.assertIn("VERCEL_TOKEN", workflow)
        self.assertIn("args=(vercel deploy . --yes --force --archive=tgz)", workflow)
        self.assertIn("args+=(--prod)", workflow)
        self.assertNotIn("vercel build --prod", workflow)
        self.assertIn("https://wukong-rom-studio.vercel.app", workflow)
        self.assertNotIn("deploy-pages", workflow)

    def test_default_debloat_list_is_embedded_for_recipe_parity(self) -> None:
        script = _app_source()
        config = json.loads((ROOT / "config" / "debloat.json").read_text(encoding="utf-8"))

        self.assertIn("defaultDebloatPaths", script)
        self.assertEqual(38, len(config["default"]))
        partitions = {path.split("\\", 1)[0] for path in config["default"]}
        self.assertEqual({"my_product", "my_stock"}, partitions)
        self.assertIn(r"my_product\app\BaiduInput_U_Product", config["default"])
        self.assertIn(r"my_stock\del-app\OPBreathMode", config["default"])
        self.assertIn(r"my_stock\app\AIMemory", config["default"])
        self.assertNotIn(r"my_product\app\OplusCamera", config["default"])

    def test_job_history_is_partitioned_into_counted_status_tabs(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
        )

        self.assertIn('id="job-history-tabs"', dom)
        self.assertIn('data-job-filter="active"', dom)
        self.assertIn('data-job-filter="succeeded"', dom)
        self.assertIn('data-job-filter="failed"', dom)
        self.assertRegex(
            dom,
            r'(?s)data-job-filter="active"[^>]*>.*?<b id="job-count-active">1</b>',
        )
        self.assertGreater(screenshot_size, 10_000)

    def test_legacy_sync_response_does_not_render_every_status_in_active_tab(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            legacy_sync_contract=True,
        )

        self.assertEqual(1, dom.count('class="job-history-card selected"'))
        self.assertNotIn("ARCHIVED_16.0.8.300(CN01)", dom)

    def test_manual_mod_selection_switches_the_recipe_to_custom(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            click_mod_toggle=True,
        )

        self.assertIn('data-preset-after-mod="custom"', dom)

    def test_admin_can_rename_preset_labels_permanently(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            admin_user=True,
            initial_view="catalog",
            exercise_custom_release=True,
        )

        self.assertIn('data-preset-labels-editor-visible="true"', dom)
        self.assertIn('data-preset-labels-saved="true"', dom)
        self.assertIn('data-preset-label-custom="Studio"', dom)
        self.assertIn('data-release-title-after-preset-rename="Phiên bản phát hành"', dom)
        self.assertNotIn('id="custom-mod-version-editor"', dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_custom_mod_and_base_release_versions_are_submitted_separately(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            exercise_custom_recipe=True,
            catalog_mod_versions=("ColorOS_16.0.9", "ColorOS_16.0.10"),
        )

        self.assertIn('data-custom-mod-recipe="ColorOS_16.0.9"', dom)
        self.assertIn('data-custom-release-recipe="KhanhDZ Custom"', dom)
        self.assertIn('data-custom-label-editor-visible="true"', dom)
        self.assertIn('&quot;custom&quot;:&quot;Limited&quot;', dom)

    def test_selected_archived_job_log_is_not_replaced_by_running_job_poll(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="jobs",
            jobs_fixture=True,
            click_other_job=True,
        )

        self.assertIn("ARCHIVED_16.0.8.300(CN01)", dom)
        self.assertIn('class="job-history-card selected"', dom)
        self.assertIn("ColorOS_16.0.8", dom)
        self.assertIn('data-job-detail-sync-calls="1"', dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_admin_opens_user_job_on_separate_page_without_changing_own_job(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True, admin_user=True, initial_view="system",
            jobs_fixture=True, click_admin_user=True, admin_job_scenario=True,
        )
        self.assertIn('data-inspected-job="archived-job"', dom)
        self.assertIn('data-inspected-view="system"', dom)
        self.assertIn('data-admin-selection-unchanged="true"', dom)
        self.assertIn('data-user-history-restored="true"', dom)
        self.assertIn('data-closed-job-stayed-closed="true"', dom)
        self.assertIn('data-inspected-stage="new-stage"', dom)
        self.assertIn('data-parameters-preserved="true"', dom)
        self.assertIn('data-admin-job-focus-preserved="true"', dom)
        self.assertIn('data-admin-job-status-quiet="true"', dom)
        self.assertIn('data-admin-job-error-status-quiet="true"', dom)
        self.assertRegex(dom, r'data-inspected-owner="[^"]*New User')
        events = re.search(r'data-inspected-events="([^"]*)"', dom)
        self.assertIsNotNone(events)
        self.assertNotIn("42 đường dẫn", events.group(1))
        self.assertIn('class="job-config"', dom)

    def test_admin_user_cards_and_detail_show_live_build_and_rom_search_activity(self) -> None:
        dom, screenshot_size = _render_mini_app_in_chrome(
            api_enabled=True, admin_user=True, initial_view="system",
            jobs_fixture=True, click_admin_user=True,
        )
        self.assertIn("Đang build ROM", dom)
        self.assertIn("Đang tìm ROM nguồn", dom)
        self.assertIn("Đã tìm thấy 2 bản ROM", dom)
        self.assertIn("OnePlus Ace 5", dom)
        self.assertIn("PKG110", dom)
        self.assertIn("Custom · ColorOS_16.0.8", dom)
        self.assertIn("V4.0", dom)
        self.assertIn("Hoàn tất tìm ROM nguồn", dom)
        self.assertIn("Kết quả ROM: 2", dom)
        self.assertIn("CPH2653_16.0.10.500(EX01)", dom)
        self.assertIn("OP 13 · EU", dom)
        self.assertGreater(screenshot_size, 10_000)

    def test_mobile_operating_surfaces_do_not_overflow_horizontally(self) -> None:
        for route, flags in (
            ("", {"click_mod_toggle": True}),
            ("jobs", {"jobs_fixture": True, "click_other_job": True}),
            ("system", {
                "admin_user": True, "jobs_fixture": True, "click_admin_user": True,
                "admin_job_scenario": True,
            }),
        ):
            with self.subTest(route=route or "studio"):
                dom, _ = _render_mini_app_in_chrome(
                    api_enabled=True,
                    initial_view=route,
                    **flags,
                )
                viewport = re.search(r'data-viewport-width="(\d+)"', dom)
                document = re.search(r'data-document-width="(\d+)"', dom)
                self.assertIsNotNone(viewport)
                self.assertIsNotNone(document)
                self.assertEqual(viewport.group(1), document.group(1))


    def test_admin_batch_build_and_persistent_release_surfaces_are_separate_and_wired(self) -> None:
        html = (ROOT / "telegram_mini_app" / "index.html").read_text(encoding="utf-8")
        script = _app_source()
        styles = _style_source()
        self.assertIn('id="catalog-release-admin" hidden', html)
        self.assertIn('id="save-admin-release"', html)
        self.assertIn('id="open-batch-build"', html)
        self.assertIn('id="admin-batch-page" hidden', html)
        self.assertIn('id="batch-devices"', html)
        self.assertIn('id="batch-mod-versions"', html)
        self.assertIn('apiRequest("/v1/mod-release-versions",', script)
        self.assertIn('apiRequest("/v1/admin/batch-builds",', script)
        self.assertIn('classList.add("admin-batch-open")', script)
        self.assertIn('requestScopes.cancel("batch")', script)
        self.assertIn('#system.admin-batch-open > :not(.admin-batch-page)', styles)

    def test_admin_batch_can_select_and_clear_every_device_and_mod_without_release_input(self) -> None:
        dom, _ = _render_mini_app_in_chrome(
            api_enabled=True,
            initial_view="system",
            admin_user=True,
            catalog_mod_versions=("ColorOS_16.0.8", "ColorOS_16.0.9"),
            exercise_batch_controls=True,
        )

        self.assertRegex(dom, r'data-batch-devices-selected="[1-9]\d*"')
        self.assertIn('data-batch-devices-cleared="0"', dom)
        self.assertIn('data-batch-mods-selected="2"', dom)
        self.assertIn('data-batch-mods-cleared="0"', dom)
        self.assertIn('data-batch-release-input-absent="true"', dom)


if __name__ == "__main__":
    unittest.main()

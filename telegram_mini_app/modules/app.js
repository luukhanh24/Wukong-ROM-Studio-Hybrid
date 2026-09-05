import { runtime, state } from "./state.js";
import { activateTelegramApp, ensureAutomaticTelegramConnection, renderSessionDiagnostics, startMiniApp } from "./shell.js";
import { applyTheme, bindTelegramThemeEvents } from "./dock.js";
import { restoreSourceDraft, updateSourceDetection } from "./source-rom.js";
import { restorePendingSubmission, updateTelegramState } from "./build.js";
import { scheduleSourceProbe } from "./catalog.js";
import { initializeApprovedWorkspace, loadSession, miniApiAvailable, renderAccessGate } from "./session.js";

if (runtime.TelegramApp) {
  activateTelegramApp();
  startMiniApp();
} else {
  // The official bridge failed to load before boot (blocked CDN, flaky
  // network inside the Telegram webview). Render the UI anyway, then inject
  // the bridge once more so a real session can still attach late.
  startMiniApp();
  const bridge = document.createElement("script");
  bridge.src = "https://telegram.org/js/telegram-web-app.js";
  bridge.async = true;
  bridge.addEventListener("load", () => {
    runtime.TelegramApp = (window.Telegram && window.Telegram.WebApp) || null;
    if (!runtime.TelegramApp) { renderSessionDiagnostics(); return; }
    activateTelegramApp();
    bindTelegramThemeEvents();
    applyTheme(state.theme);
    restoreSourceDraft();
  restorePendingSubmission();
    updateTelegramState();
    updateSourceDetection();
    scheduleSourceProbe();
    renderSessionDiagnostics();
    ensureAutomaticTelegramConnection();
    if (miniApiAvailable()) {
      loadSession({ countOpen: false }).then(() => initializeApprovedWorkspace()).catch(() => {});
    } else renderAccessGate();
  });
  bridge.addEventListener("error", renderSessionDiagnostics);
  document.head.append(bridge);
}

import { $, $$, miniApiEndpoint, parseInitDataFromHash, requestJson, requestScopes, runtime, state, t, telegramBotUsername, validSignedLaunchToken, workspacePollingAllowed } from "./state.js";
import { ensureAutomaticTelegramConnection, renderSessionDiagnostics, toast } from "./shell.js";
import { restorePendingSubmission, updateSummary, updateTelegramState } from "./build.js";
import { formatBytes, updateSourceDetection } from "./source-rom.js";
import { loadAdminJobDetail, loadJobs, setJobsConnection } from "./jobs.js";
import { openCacheClearDialog, loadAdminUsers, loadLatestBatch, refreshAdminUserActivity, renderAdminPresetLabels, renderAdminReleaseEditor, renderMaintenanceAdmin } from "./admin.js";
import { navigate, renderGreeting, scheduleGreeting } from "./dock.js";
import { loadCatalog, refreshLiveReleaseVersions } from "./catalog.js";
import { closeAdminUserPage, profileAvatar, renderProfileTrigger, renderProfileView } from "./profile.js";

function setSignedTelegramLaunchToken(token) {
  if (!validSignedLaunchToken(token)) return false;
  runtime.signedTelegramLaunchToken = String(token);
  try {
    sessionStorage.setItem("wukong-signed-launch", runtime.signedTelegramLaunchToken);
    localStorage.setItem("wukong-signed-launch", runtime.signedTelegramLaunchToken);
  } catch (_) {}
  return true;
}

function activeSignedLaunchToken() {
  if (validSignedLaunchToken(runtime.signedTelegramLaunchToken)) return runtime.signedTelegramLaunchToken;
  runtime.signedTelegramLaunchToken = "";
  try {
    sessionStorage.removeItem("wukong-signed-launch");
    localStorage.removeItem("wukong-signed-launch");
  } catch (_) {}
  return "";
}

function effectiveInitData() {
  const direct = String(runtime.TelegramApp?.initData || "");
  if (direct) {
    runtime.cachedTelegramInitData = direct;
    return direct;
  }
  if (runtime.cachedTelegramInitData) return runtime.cachedTelegramInitData;
  runtime.cachedTelegramInitData = parseInitDataFromHash();
  return runtime.cachedTelegramInitData;
}

function effectiveInitDataUnsafe() {
  const direct = runtime.TelegramApp?.initDataUnsafe;
  if (direct && typeof direct === "object") return direct;
  // Fallback: parse hash ourselves so start_param still works even if bridge missed it
  try {
    const data = effectiveInitData();
    if (!data) return {};
    const usp = new URLSearchParams(data);
    const userRaw = usp.get("user");
    let user = null;
    try { user = userRaw ? JSON.parse(userRaw) : null; } catch (_) {}
    return {
      query_id: usp.get("query_id") || "",
      user,
      auth_date: usp.get("auth_date") || "",
      hash: usp.get("hash") || "",
      start_param: usp.get("start_param") || "",
    };
  } catch (_) { return {}; }
}

function miniApiAvailable() {
  return Boolean(miniApiEndpoint && (effectiveInitData() || activeSignedLaunchToken()));
}

function privateApiAvailable() {
  return miniApiAvailable() && state.me?.accessStatus === "approved"
    && (!state.maintenance?.enabled || state.me?.role === "admin");
}

function getMiniSessionId() {
  if (state.miniSessionId) return state.miniSessionId;
  try {
    state.miniSessionId = sessionStorage.getItem("wukong-mini-session-id") || "";
    if (!state.miniSessionId) {
      state.miniSessionId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      sessionStorage.setItem("wukong-mini-session-id", state.miniSessionId);
    }
  } catch (_) { state.miniSessionId = `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
  return state.miniSessionId;
}

function miniApiState() {
  if (!miniApiEndpoint) return "unconfigured";
  if (!effectiveInitData() && !activeSignedLaunchToken()) return "unauthenticated";
  return "ready";
}

function miniApiUnavailableMessageKey() {
  return miniApiState() === "unconfigured" ? "apiRequired" : "telegramOnly";
}

async function apiRequest(path, options = {}) {
  if (!miniApiEndpoint) throw new Error(t("apiRequired"));
  const initData = effectiveInitData();
  const launchToken = activeSignedLaunchToken();
  if (!initData && !launchToken) throw new Error(t("telegramOnly"));
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", initData ? `tma ${initData}` : `wla ${launchToken}`);
  headers.set("X-Wukong-Session-Id", getMiniSessionId());
  headers.set("X-Wukong-Client-Version", "2026.08.25");
  headers.set("X-Telegram-Platform", String(runtime.TelegramApp?.platform || "web"));
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  try {
    return (await requestJson(`${miniApiEndpoint}${path}`, { ...options, headers, cache: "no-store" })).payload;
  } catch (error) {
    if (error.payload?.code === "maintenance_mode" && error.payload.maintenance) {
      state.maintenance = error.payload.maintenance;
      renderAccessGate();
    }
    if (error.code === "build_concurrency_limit") error.message = t("buildConcurrencyLimit");
    else if (error.code === "request_timeout") error.message = t("requestTimedOut");
    else if (error.connectionFailed) error.message = t("requestFailed");
    throw error;
  }
}

async function publicApiRequest(path, options = {}) {
  if (!miniApiEndpoint) throw new Error(t("apiRequired"));
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return requestJson(`${miniApiEndpoint}${path}`, { ...options, headers, cache: "no-store" });
}

function telegramTransportAvailable() {
  return typeof runtime.TelegramApp?.sendData === "function" && Boolean(runtime.TelegramApp.platform) && runtime.TelegramApp.platform !== "unknown";
}

function presentMissingApi() {
  const status = miniApiState();
  const node = $("#source-state");
  node.classList.remove("probing", "analyzed", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  node.classList.add("probe-unavailable");
  const unconfigured = status === "unconfigured";
  const insideTelegram = Boolean(runtime.TelegramApp?.platform && runtime.TelegramApp.platform !== "unknown");
  $("#source-kicker").textContent = t(unconfigured ? "apiUnavailableKicker" : "apiAuthKicker");
  $("#source-state-message").textContent = t(unconfigured ? "apiUnavailableMessage" : "apiAuthMessage");
  const button = $("#probe-source");
  button.textContent = t(unconfigured ? "apiUnavailableButton" : "apiAuthButton");
  if (unconfigured) {
    button.disabled = true;
    delete button.dataset.openBot;
    delete button.dataset.closeApp;
    return;
  }
  // Always offer a way out: inside Telegram just close and reopen from the
  // menu button so initData is attached; outside Telegram jump to the bot.
  if (insideTelegram) {
    button.disabled = false;
    button.dataset.connectTelegram = "1";
    delete button.dataset.openBot;
    delete button.dataset.closeApp;
  } else if (telegramBotUsername) {
    button.disabled = false;
    button.dataset.openBot = "1";
    delete button.dataset.closeApp;
  } else {
    button.disabled = true;
    delete button.dataset.openBot;
    delete button.dataset.closeApp;
  }
}

function telegramBotLink() {
  return `https://t.me/${telegramBotUsername}`;
}

function openTelegramBot() {
  const link = telegramBotLink();
  try {
    if (runtime.TelegramApp?.openTelegramLink) { runtime.TelegramApp.openTelegramLink(link); return; }
  } catch (_) {}
  window.open(link, "_blank", "noopener");
}

function storedPairing() {
  try { return JSON.parse(sessionStorage.getItem("wukong-telegram-pairing") || "null"); }
  catch (_) { return null; }
}

async function pollTelegramPairing(pairing) {
  clearTimeout(state.pairingPollTimer);
  if (!workspacePollingAllowed() || !pairing?.pairId || !pairing?.pairSecret || miniApiAvailable()) return;
  const signal = requestScopes.start("pairing");
  const { payload, status } = await publicApiRequest("/v1/session/pair/status", {
    method: "POST",
    signal, body: JSON.stringify({ pairId: pairing.pairId, pairSecret: pairing.pairSecret })
  });
  if (signal.aborted || !workspacePollingAllowed()) return;
  if (status === 200 && setSignedTelegramLaunchToken(payload.launchToken)) {
    try { sessionStorage.removeItem("wukong-telegram-pairing"); } catch (_) {}
    state.pairingInFlight = false;
    state.pairingPollAttempt = 0;
    renderSessionDiagnostics();
    updateTelegramState();
    updateSummary();
    updateSourceDetection();
    loadSession().then(() => {
      initializeApprovedWorkspace();
    }).catch(() => {});
    toast(t("pairingReady"));
    return;
  }
  const recoveryText = $("#session-recovery p");
  if (recoveryText) recoveryText.textContent = t("pairingWaiting");
  const pairingBackoff = [3000, 5000, 8000, 10000];
  const delay = pairingBackoff[Math.min(state.pairingPollAttempt, pairingBackoff.length - 1)];
  state.pairingPollAttempt += 1;
  state.pairingPollTimer = setTimeout(() => {
    pollTelegramPairing(pairing).catch((error) => {
      if (error.name === "AbortError" || !workspacePollingAllowed()) return;
      state.pairingInFlight = false;
      updateSummary();
      toast(t("pairingFailed"), true);
    });
  }, delay);
}

async function connectTelegramSession() {
  if (state.pairingInFlight || miniApiAvailable()) return;
  state.pairingInFlight = true;
  state.pairingPollAttempt = 0;
  updateSummary();
  const recoveryText = $("#session-recovery p");
  if (recoveryText) recoveryText.textContent = t("pairingOpening");
  try {
    const { payload: pairing } = await publicApiRequest("/v1/session/pair", { method: "POST" });
    sessionStorage.setItem("wukong-telegram-pairing", JSON.stringify(pairing));
    try {
      if (runtime.TelegramApp?.openTelegramLink) runtime.TelegramApp.openTelegramLink(pairing.botLink);
      else window.open(pairing.botLink, "_blank", "noopener");
    } catch (_) { window.open(pairing.botLink, "_blank", "noopener"); }
    await pollTelegramPairing(pairing);
  } catch (error) {
    if (error.name === "AbortError" || !workspacePollingAllowed()) return;
    state.pairingInFlight = false;
    updateSummary();
    toast(error.message || t("pairingFailed"), true);
  }
}

function closeTelegramApp() {
  try { runtime.TelegramApp?.close(); } catch (_) {}
  // Fallback for browsers/testing: just navigate away from the stale entry.
  setTimeout(() => { try { window.close(); } catch (_) {} }, 120);
}

function pauseWorkspacePolling() {
  clearTimeout(workspaceReconnectTimer);
  workspaceReconnectTimer = null;
  for (const name of ["adminUsersPollTimer", "adminUserPollTimer", "jobsPollTimer", "maintenancePollTimer", "batchPollTimer", "pairingPollTimer"]) {
    clearTimeout(state[name]); state[name] = null;
  }
  clearTimeout(state.adminJobView?.timer);
  if (state.adminJobView) state.adminJobView.timer = null;
  requestScopes.cancelAll();
  ++state.jobHistoryRequestId; ++state.jobDetailRequestId;
  state.jobsLoading = false;
  state.jobHistoryLoading = false;
  state.pairingInFlight = false;
  clearInterval(state.greetingTimer);
  cancelAnimationFrame(state.liquidAnimationFrame);
}

function resumeWorkspacePolling() {
  if (!workspacePollingAllowed() || !privateApiAvailable()) return;
  if (state.adminJobView) loadAdminJobDetail();
  else {
    if (document.body.dataset.view === "jobs") loadJobs({ force: true }).catch(() => {});
    if (state.selectedAdminUserId) refreshAdminUserActivity();
    else if (document.body.dataset.view === "system" && state.me?.role === "admin") loadAdminUsers().catch(() => {});
  }
  if (document.body.dataset.view === "system" && !$("#admin-batch-page").hidden) loadLatestBatch().catch(() => {});
}

function reconnectWorkspace() {
  if (!workspacePollingAllowed()) return;
  scheduleGreeting();
  ensureAutomaticTelegramConnection();
  loadSession({ countOpen: false }).then(() => initializeApprovedWorkspace({ refresh: true })).catch(() => setJobsConnection("jobsOffline", true));
}

let workspaceReconnectTimer = null;

function scheduleWorkspaceReconnect() {
  if (!workspacePollingAllowed()) return;
  clearTimeout(workspaceReconnectTimer);
  workspaceReconnectTimer = setTimeout(() => {
    workspaceReconnectTimer = null;
    reconnectWorkspace();
  }, 0);
}

function initializeApprovedWorkspace({ refresh = false } = {}) {
  if (state.me?.accessStatus !== "approved") return;
  if (state.maintenance?.enabled && state.me?.role !== "admin") {
    renderAccessGate();
    return;
  }
  document.body.classList.remove("access-checking", "access-limited", "maintenance-limited");
  $("#access-gate").hidden = true;
  $("#maintenance-gate").hidden = true;
  if (state.workspaceLoaded) {
    if (refresh && !document.hidden) resumeWorkspacePolling();
    return;
  }
  state.workspaceLoaded = true;
  navigate(location.hash.slice(1) || "build", false);
  loadCatalog().finally(() => requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" })));
  refreshLiveReleaseVersions().catch(() => {});
  loadJobs({ force: true }).catch(() => {});
}

function renderAccessGate() {
  const profile = state.me;
  const gate = $("#access-gate");
  if (!gate) return;
  const maintenanceGate = $("#maintenance-gate");
  const maintenanceLimited = Boolean(state.maintenance?.enabled && profile?.role !== "admin");
  if (maintenanceLimited) {
    document.body.classList.remove("access-checking", "access-limited");
    document.body.classList.add("maintenance-limited");
    gate.hidden = true;
    maintenanceGate.hidden = false;
    $("#maintenance-gate-message").textContent = state.maintenance.message || t("maintenanceGateTitle");
    clearTimeout(state.jobsPollTimer);
    clearTimeout(state.sourceProbeTimer);
    state.sourceProbeController?.abort();
    $$("dialog[open]").forEach((dialog) => dialog.close());
    clearTimeout(state.maintenancePollTimer);
    if (workspacePollingAllowed()) state.maintenancePollTimer = setTimeout(() => {
      loadSession({ countOpen: false }).catch(() => renderAccessGate());
    }, 30000);
    return;
  }
  const wasLimited = document.body.classList.contains("maintenance-limited");
  clearTimeout(state.maintenancePollTimer);
  document.body.classList.remove("maintenance-limited");
  maintenanceGate.hidden = true;
  const approved = profile?.accessStatus === "approved";
  if (approved) {
    initializeApprovedWorkspace();
    if (wasLimited && state.workspaceLoaded) loadJobs().catch(() => {});
    return;
  }
  document.body.classList.remove("access-checking");
  document.body.classList.add("access-limited");
  gate.hidden = false;
  const status = profile?.accessStatus === "revoked" ? "Revoked" : profile ? "Pending" : "Connect";
  $("#access-kicker").textContent = t(`access${status}Kicker`);
  $("#access-title").textContent = t(`access${status}Title`);
  $("#access-message").textContent = t(`access${status}Message`);
  const facts = $("#access-profile");
  facts.hidden = !profile;
  if (profile) {
    $("#access-name").textContent = profile.displayName || "—";
    $("#access-username").textContent = profile.username ? `@${profile.username}` : "—";
    $("#access-id").textContent = profile.telegramId || "—";
    $("#access-meta").textContent = [
      profile.language ? profile.language.toUpperCase() : "",
      profile.platform || "",
      profile.appVersion ? `v${profile.appVersion}` : ""
    ].filter(Boolean).join(" · ") || "—";
    $("#access-avatar").replaceWith(profileAvatar(profile, "profile-avatar-large"));
    const avatar = $(".access-card .profile-avatar");
    if (avatar) avatar.id = "access-avatar";
  }
}

function renderAccount() {
  const profile = state.me;
  renderProfileTrigger($("#dock-profile"), profile);
  renderProfileTrigger($("#header-profile"), profile);
  renderProfileView();
  renderGreeting();
  scheduleGreeting();
  $("#user-admin").hidden = true;
  $("#admin-maintenance").hidden = true;
  $("#admin-batch-launch").hidden = true;
  $("#catalog-release-admin").hidden = true;
  $("#catalog-preset-admin").hidden = true;
  if (!profile || profile.role !== "admin") closeAdminUserPage({ restoreFocus: false, scroll: false });
  if (!profile) return;
  const runtimeAllowance = $("#runtime-build-allowance");
  if (runtimeAllowance) {
    const values = {
      used: Number(profile.lifetimeUsed || 0),
      jobs: Number(profile.jobCount || 0)
    };
    runtimeAllowance.textContent = profile.unlimited
      ? t("allowanceUnlimitedSummary", values)
      : t("allowanceSummary", {
          ...values,
          remaining: String(Number(profile.buildCredits || 0))
        });
  }
  const admin = profile.role === "admin";
  $("#user-admin").hidden = !admin;
  $("#admin-maintenance").hidden = !admin;
  $("#admin-batch-launch").hidden = !admin;
  renderAdminReleaseEditor();
  renderAdminPresetLabels();
  renderMaintenanceAdmin();
  renderAccessGate();
}

async function loadSession({ countOpen = true } = {}) {
  if (!miniApiAvailable()) return null;
  const payload = await apiRequest(countOpen ? "/v1/session/open" : "/v1/me", {
    method: countOpen ? "POST" : "GET"
  });
  const previousSubject = state.me?.telegramId;
  if (previousSubject && previousSubject !== payload.user?.telegramId) {
    pauseWorkspacePolling(); state.jobs = []; state.activeEvents = []; state.activeJobId = "";
    state.workspaceLoaded = false;
    localStorage.removeItem("wukong-submit-request"); localStorage.removeItem("wukong-active-job");
  }
  state.me = payload.user || null;
  restorePendingSubmission();
  state.maintenance = payload.maintenance || state.maintenance;
  renderAccount();
  updateSummary();
  if (state.me?.role === "admin" && document.body.dataset.view === "system") loadAdminUsers().catch(() => {});
  return state.me;
}

export { setSignedTelegramLaunchToken, activeSignedLaunchToken, effectiveInitData, effectiveInitDataUnsafe, miniApiAvailable, privateApiAvailable, getMiniSessionId, miniApiState, miniApiUnavailableMessageKey, apiRequest, publicApiRequest, telegramTransportAvailable, presentMissingApi, telegramBotLink, openTelegramBot, storedPairing, pollTelegramPairing, connectTelegramSession, closeTelegramApp, pauseWorkspacePolling, resumeWorkspacePolling, reconnectWorkspace, scheduleWorkspaceReconnect, initializeApprovedWorkspace, renderAccessGate, renderAccount, loadSession };

async function runQuickAction(action) {
  if (action === "diagnostics") {
    const payload = await apiRequest("/v1/diagnostics");
    const healthy = Boolean(payload.system || payload.runner || payload.cache);
    $("#telegram-health")?.classList.toggle("ok", healthy);
    toast(healthy ? t("jobsConnected") : t("requestFailed"), !healthy);
    return;
  }
  if (action === "cache") {
    const payload = await apiRequest("/v1/cache");
    toast(`${payload.entryCount ?? 0} cache · ${formatBytes(payload.totalBytes)}`);
    return;
  }
  if (action === "cache_clear") {
    openCacheClearDialog();
    return;
  }
  throw new Error(t("requestFailed"));
}

export { runQuickAction };

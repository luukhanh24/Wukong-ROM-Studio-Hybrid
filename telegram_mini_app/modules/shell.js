import { bindViewport } from "./viewport.js";
import { $, $$, miniApiEndpoint, runtime, state, t, themeMedia } from "./state.js";
import { applyCustomPresetLabelForJob, closeDebloatEditor, filterMods, openDebloatEditor, renderCatalog, renderCustomPresetLabelEditor, renderDebloatSummary, renderMods, renderPipelineSteps, restorePendingSubmission, saveDebloatPaths, saveReleaseVersion, setDeliveryState, setMods, submitRecipe, updatePipelineCount, updateSummary, updateTelegramState } from "./build.js";
import { closeAdminJobPage, loadAdminJobDetail, loadJobs, renderJobHistory, renderSelectedJob, setJobsConnection } from "./jobs.js";
import { runQuickAction, activeSignedLaunchToken, apiRequest, closeTelegramApp, connectTelegramSession, effectiveInitData, initializeApprovedWorkspace, loadSession, miniApiAvailable, openTelegramBot, pauseWorkspacePolling, pollTelegramPairing, reconnectWorkspace, scheduleWorkspaceReconnect, renderAccessGate, renderAccount, storedPairing } from "./session.js";
import { loadRomDevices, renderRomCatalogResults, renderRomDevices, renderRomVersions, resetRomResolved, searchRomCatalog, selectLibraryTab } from "./rom-catalog.js";
import { closeBatchBuildPage, loadAdminUsers, loadBatch, openBatchBuildPage, performCacheClear, renderAdminUsers, savePermanentPresetLabels, savePermanentReleaseVersion, setBatchSelections, startBatchBuild, updateBatchSummary, updateMaintenance } from "./admin.js";
import { clearSource, copySourceMetadata, pasteSourceFromClipboard, probeSourceInPlace, restoreSourceDraft, updateSourceDetection } from "./source-rom.js";
import { applyTheme, bindLiquidBottomTabs, bindTelegramThemeEvents, handleSystemThemeChange, navigate, prefersReducedMotion, scheduleGreeting, updateDispatchFab, updateDockShellPath, updateGreetingOverflow, updateMastheadScroll } from "./dock.js";
import { scheduleSourceProbe } from "./catalog.js";
import { closeAdminUserPage } from "./profile.js";

function applyLanguage() {
  document.documentElement.lang = state.language;
  $$('[data-i18n-placeholder]').forEach((node) => { node.placeholder = t(node.dataset.i18nPlaceholder); });
  $$('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  $$("[data-i18n-aria]").forEach((node) => node.setAttribute("aria-label", t(node.dataset.i18nAria)));
  $("#language").textContent = state.language === "vi" ? "VI / EN" : "EN / VI";
  const devicePlaceholder = $("#device option[value='']");
  if (devicePlaceholder) devicePlaceholder.textContent = t("chooseDevice");
  renderMods(false);
  renderPipelineSteps(false);
  renderCatalog();
  renderJobHistory();
  renderSelectedJob();
  renderSessionDiagnostics();
  renderAccount();
  renderRomVersions();
  renderRomCatalogResults();
  renderRomDevices();
  renderAdminUsers();
  renderDebloatSummary();
  updateSummary();
  updateTelegramState();
  updateSourceDetection();
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", error);
  node.classList.add("visible");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => node.classList.remove("visible"), 3600);
  if (runtime.TelegramApp?.HapticFeedback) runtime.TelegramApp.HapticFeedback.notificationOccurred(error ? "error" : "success");
}

function options(select, entries, preferred) {
  select.replaceChildren(...entries.map(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value; option.textContent = label; return option;
  }));
  if (preferred && entries.some((entry) => entry.value === preferred)) select.value = preferred;
}

function bindEvents() {
  $("#confirm-submit")?.addEventListener("click", () => submitRecipe().catch(error => toast(error.message, true)));
  $("#language").addEventListener("click", () => { state.language = state.language === "vi" ? "en" : "vi"; localStorage.setItem("wukong-language", state.language); applyLanguage(); });
  $$('[data-nav]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.nav)));
  bindLiquidBottomTabs();
  $("#cache-clear-confirm")?.addEventListener("click", () => performCacheClear());
  $$("[data-theme-value]").forEach((button) => button.addEventListener("click", () => applyTheme(button.dataset.themeValue, true)));
  themeMedia?.addEventListener?.("change", handleSystemThemeChange);
  bindTelegramThemeEvents();
  window.addEventListener("scroll", updateMastheadScroll, { passive: true });
  let greetingResizeFrame = 0;
  window.addEventListener("resize", () => {
    cancelAnimationFrame(greetingResizeFrame);
    greetingResizeFrame = requestAnimationFrame(() => {
      updateGreetingOverflow();
      updateDockShellPath();
    });
  }, { passive: true });
  document.fonts?.ready?.then(updateGreetingOverflow).catch(() => {});
  $$('[data-action]').forEach((button) => button.addEventListener("click", () => {
    runQuickAction(button.dataset.action).catch((error) => toast(error.message, true));
  }));
  $("#recipe-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter || event.currentTarget.querySelector('[type="submit"]');
    if (button) button.disabled = true;
    try { await submitRecipe(); } catch (error) { toast(error.message, true); }
    finally { if (button) button.disabled = false; }
  });
  $("#source-uri").addEventListener("input", () => { updateSourceDetection(); scheduleSourceProbe(); });
  $("#source-uri").addEventListener("paste", () => queueMicrotask(() => { updateSourceDetection(); scheduleSourceProbe(); }));
  $("#open-rom-catalog").addEventListener("click", () => {
    selectLibraryTab("rom");
    navigate("catalog");
    $("#rom-device-picker summary").focus();
  });
  $("#rom-catalog-form").addEventListener("submit", (event) => {
    event.preventDefault();
    searchRomCatalog();
  });
  $("#rom-device-search").addEventListener("input", renderRomDevices);
  $("#rom-region-filter").addEventListener("change", () => { resetRomResolved(); renderRomVersions(false); renderRomCatalogResults(); });
  $("#rom-version-filter").addEventListener("change", () => { resetRomResolved(); renderRomCatalogResults(); });
  $("#rom-device-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); $("[data-rom-device]")?.focus(); }
  });
  $("#rom-devices-retry").addEventListener("click", loadRomDevices);
  $("#rom-device-picker").addEventListener("toggle", () => {
    if ($("#rom-device-picker").open) loadRomDevices();
  });
  $("#rom-device-picker").addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    $("#rom-device-picker").open = false;
    $("#rom-device-picker summary").focus();
  });
  $$('[data-library-tab]').forEach((button) => {
    button.addEventListener("click", () => selectLibraryTab(button.dataset.libraryTab));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const name = event.key === "Home" ? "rom" : event.key === "End" ? "technical"
        : button.dataset.libraryTab === "rom" ? "technical" : "rom";
      selectLibraryTab(name, true);
    });
  });
  $("#paste-source").addEventListener("click", () => pasteSourceFromClipboard().catch((error) => toast(error.message, true)));
  $("#connect-telegram").addEventListener("click", () => connectTelegramSession());
  $("#refresh-access").addEventListener("click", () => {
    if (!miniApiAvailable()) { connectTelegramSession(); return; }
    loadSession({ countOpen: false }).catch((error) => toast(error.message, true));
  });
  $("#refresh-maintenance").addEventListener("click", () => {
    loadSession({ countOpen: false }).catch((error) => toast(error.message, true));
  });
  $("#maintenance-toggle").addEventListener("click", () => {
    updateMaintenance().catch((error) => toast(error.message, true));
  });
  $("#maintenance-message-input").addEventListener("input", () => { state.maintenanceMessageDirty = true; });
  $("#clear-source").addEventListener("click", clearSource);
  $("#probe-source").addEventListener("click", () => {
    clearTimeout(state.sourceProbeTimer);
    const probeButton = $("#probe-source");
    if (probeButton.dataset.connectTelegram) { connectTelegramSession(); return; }
    if (probeButton.dataset.closeApp) { closeTelegramApp(); return; }
    if (probeButton.dataset.openBot) { openTelegramBot(); return; }
    probeSourceInPlace().catch((error) => toast(error.message, true));
  });
  $("#select-defaults").addEventListener("click", () => setMods("defaults"));
  $("#select-all").addEventListener("click", () => setMods("all"));
  $("#clear-mods").addEventListener("click", () => setMods("none"));
  $("#mod-version").addEventListener("change", () => renderMods());
  $("#save-mod-release-version").addEventListener("click", () => saveReleaseVersion().catch((error) => toast(error.message, true)));
  $("#apply-custom-preset-label").addEventListener("click", () => {
    try { applyCustomPresetLabelForJob(); }
    catch (error) { toast(error.message, true); }
  });
  $("#preset").addEventListener("change", () => renderMods());
  $("#execution").addEventListener("change", updateSummary);
  $("#device").addEventListener("change", updateSummary);
  $("#mod-list").addEventListener("change", (event) => {
    if (event.target.matches('input[type="checkbox"]')) {
      $("#preset").value = "custom";
      renderCustomPresetLabelEditor();
    }
    updateSummary();
  });
  $("#mod-search").addEventListener("input", filterMods);
  $("#catalog-search").addEventListener("input", renderCatalog);
  $("#catalog-version").addEventListener("change", renderCatalog);
  $("#admin-release-pack").addEventListener("change", () => { $("#admin-release-label").value = state.catalog.modReleaseVersions[$("#admin-release-pack").value] || $("#admin-release-pack").value; });
  $("#save-admin-release").addEventListener("click", () => savePermanentReleaseVersion().catch(error => toast(error.message, true)));
  $("#save-admin-preset-labels").addEventListener("click", () => savePermanentPresetLabels().catch(error => toast(error.message, true)));
  $("#open-batch-build").addEventListener("click", openBatchBuildPage);
  $("#admin-batch-back").addEventListener("click", closeBatchBuildPage);
  $("#start-batch-build").addEventListener("click", () => startBatchBuild().catch(error => toast(error.message, true)));
  $("#refresh-batch").addEventListener("click", () => loadBatch().catch(error => toast(error.message, true)));
  $("#batch-devices").addEventListener("change", updateBatchSummary);
  $("#batch-mod-versions").addEventListener("change", updateBatchSummary);
  $("#batch-select-all-devices").addEventListener("click", () => setBatchSelections("#batch-devices", true));
  $("#batch-clear-devices").addEventListener("click", () => setBatchSelections("#batch-devices", false));
  $("#batch-select-all-mods").addEventListener("click", () => setBatchSelections("#batch-mod-versions", true));
  $("#batch-clear-mods").addEventListener("click", () => setBatchSelections("#batch-mod-versions", false));
  $("#batch-lite").addEventListener("change", updateBatchSummary);
  $("#batch-plus").addEventListener("change", updateBatchSummary);
  $("#steps").addEventListener("change", updatePipelineCount);
  $("#edit-debloat-paths").addEventListener("click", openDebloatEditor);
  $("#save-debloat-paths").addEventListener("click", saveDebloatPaths);
  $("#cancel-debloat-paths").addEventListener("click", closeDebloatEditor);
  $$(".switches input").forEach((input) => input.addEventListener("change", () => {
    state.delivery[input.id] = input.checked ? "pending" : "skipped";
    updateSummary();
  }));
  $("#default-preset").value = state.defaultPreset;
  $("#preset").value = state.defaultPreset;
  $("#default-preset").addEventListener("change", (event) => {
    state.defaultPreset = event.target.value;
    localStorage.setItem("wukong-default-preset", state.defaultPreset);
    $("#preset").value = state.defaultPreset;
    renderMods();
  });
  $("#refresh-jobs").addEventListener("click", () => loadJobs({ force: true }).catch((error) => toast(error.message, true)));
  $$("[data-job-filter]").forEach((button) => button.addEventListener("click", () => {
    state.jobHistoryFilter = button.dataset.jobFilter;
    state.jobHistoryPage = 1;
    loadJobs({ force: true }).catch((error) => toast(error.message, true));
  }));
  const reloadJobHistory = () => {
    state.jobHistoryPage = 1;
    loadJobs({ force: true }).catch((error) => toast(error.message, true));
  };
  let jobHistorySearchTimer;
  $("#job-history-search")?.addEventListener("input", () => {
    clearTimeout(jobHistorySearchTimer);
    jobHistorySearchTimer = setTimeout(reloadJobHistory, 300);
  });
  for (const id of ["job-history-preset", "job-history-mod", "job-history-from", "job-history-to"]) {
    $("#" + id)?.addEventListener("change", reloadJobHistory);
  }
  $("#job-history-filters")?.addEventListener("reset", () => setTimeout(reloadJobHistory, 0));
  let userSearchTimer;
  $("#user-search").addEventListener("input", () => { clearTimeout(userSearchTimer); userSearchTimer = setTimeout(() => loadAdminUsers({ reset: true }).catch(() => {}), 250); });
  $("#user-status").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-quota-filter").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-activity-filter").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-sort").addEventListener("change", () => loadAdminUsers({ reset: true }).catch(() => {}));
  $("#user-prev").addEventListener("click", () => { state.adminUsersOffset = Math.max(0, state.adminUsersOffset - 25); loadAdminUsers().catch(() => {}); });
  $("#user-next").addEventListener("click", () => { state.adminUsersOffset += 25; loadAdminUsers().catch(() => {}); });
  $("#add-user").addEventListener("click", () => $("#user-create-dialog").showModal());
  $("#admin-user-back").addEventListener("click", () => closeAdminUserPage());
  $("#admin-job-back").addEventListener("click", () => closeAdminJobPage());
  $("#refresh-admin-job").addEventListener("click", () => loadAdminJobDetail());
  $("#user-create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await apiRequest("/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({
          telegramId: $("#new-user-id").value.trim(),
          username: $("#new-user-username").value.trim(),
          displayName: $("#new-user-display-name").value.trim()
        })
      });
      $("#user-create-form").reset(); $("#user-create-dialog").close(); toast(t("userCreated"));
      await loadAdminUsers({ reset: true });
    } catch (error) { toast(error.message, true); }
  });
  document.addEventListener("visibilitychange", () => document.hidden ? pauseWorkspacePolling() : scheduleWorkspaceReconnect());
  window.addEventListener("offline", () => { pauseWorkspacePolling(); setJobsConnection("jobsOffline", true); });
  window.addEventListener("online", scheduleWorkspaceReconnect);
  $("#copy-source-metadata").addEventListener("click", () => copySourceMetadata().catch((error) => toast(error.message, true)));
  const docket = $(".dispatch-docket");
  const fab = $("#dispatch-fab");
  if (docket && fab && "IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      state.docketInView = entry.isIntersecting;
      updateDispatchFab();
    }, { threshold: .18 }).observe(docket);
    fab.addEventListener("click", () => docket.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" }));
  }
}

function renderSessionDiagnostics() {
  const node = $("#session-diag");
  if (!node) return;
  if (activeSignedLaunchToken()) { node.textContent = t("sessionDiagLaunchToken"); return; }
  if (!runtime.TelegramApp && !effectiveInitData()) { node.textContent = t("sessionDiagNoLib"); return; }
  const rawDirect = String(runtime.TelegramApp?.initData || "");
  const fallback = !rawDirect ? effectiveInitData() : "";
  const chars = String(effectiveInitData() || "").length;
  if (!chars) { node.textContent = t("sessionDiagNoData"); return; }
  const via = fallback ? " (từ hash)" : "";
  node.textContent = t("sessionDiagOk", { platform: (runtime.TelegramApp?.platform || "?") + via, chars });
}

function activateTelegramApp() {
  bindViewport(runtime.TelegramApp);
  try {
    runtime.TelegramApp.ready(); runtime.TelegramApp.expand();
    if (runtime.TelegramApp.isVersionAtLeast?.("7.7")) runtime.TelegramApp.disableVerticalSwipes?.();
    if (runtime.TelegramApp.isVersionAtLeast?.("6.1")) {
      runtime.TelegramApp.setHeaderColor?.("secondary_bg_color");
      runtime.TelegramApp.setBackgroundColor?.("secondary_bg_color");
    }
  } catch (_) {}
}

function ensureAutomaticTelegramConnection() {
  const insideTelegram = Boolean(runtime.TelegramApp?.platform && runtime.TelegramApp.platform !== "unknown");
  if (miniApiAvailable() || !miniApiEndpoint || !insideTelegram || state.pairingInFlight) return;
  const pairing = storedPairing();
  if (pairing) {
    state.pairingInFlight = true;
    updateSummary();
    pollTelegramPairing(pairing).catch(() => {
      state.pairingInFlight = false;
      updateSummary();
      toast(t("pairingFailed"), true);
    });
    return;
  }
  connectTelegramSession();
}

function startMiniApp() {
  bindViewport(runtime.TelegramApp);
  applyTheme(state.theme);
  bindEvents();
  updateMastheadScroll();
  scheduleGreeting();
  restoreSourceDraft();
  restorePendingSubmission();
  window.WukongMiniApp = Object.freeze({ setDeliveryState });
  applyLanguage();
  history.scrollRestoration = "manual";
  renderSessionDiagnostics();
  ensureAutomaticTelegramConnection();
  if (miniApiAvailable()) {
    loadSession().then(() => {
      initializeApprovedWorkspace();
    }).catch((error) => toast(error.message, true));
  } else renderAccessGate();
}

export { applyLanguage, toast, options, bindEvents, renderSessionDiagnostics, activateTelegramApp, ensureAutomaticTelegramConnection, startMiniApp };

import { $, $$, miniApiEndpoint, pipelineLabels, state, t } from "./state.js";
import { renderAdminPresetLabels, renderAdminReleaseEditor } from "./admin.js";
import { activeSignedLaunchToken, apiRequest, effectiveInitData, loadSession, miniApiAvailable, miniApiUnavailableMessageKey, telegramTransportAvailable } from "./session.js";
import { classifySource } from "./source-rom.js";
import { options, toast } from "./shell.js";
import { navigate } from "./dock.js";
import { loadJobs } from "./jobs.js";

function selectedMods() {
  return $$("#mod-list input:checked").map((input) => input.value);
}

function defaultMods() {
  const version = selectedModVersion();
  const preset = $("#preset").value;
  return state.catalog?.presetDefaultsByVersion?.[version]?.[preset] || [];
}

function modCategory(name) {
  const value = name.toLocaleLowerCase();
  if (/gapps|google|play[_ -]?store|youtube|chrome|maps/.test(value)) return "google";
  if (/camera|cam|photo|gallery|image|video/.test(value)) return "camera";
  if (/security|secure|selinux|root|magisk|permission|safetynet|integrity/.test(value)) return "security";
  if (/system[_ -]?ui|launcher|theme|font|icon|wallpaper|aod|status|control[_ -]?center/.test(value)) return "interface";
  if (/wk|manager|framework|service|core|kernel|module|tools?/.test(value)) return "core";
  return "other";
}

function modCategoryLabel(category) {
  return t({
    google: "modGroupGoogle",
    camera: "modGroupCamera",
    interface: "modGroupInterface",
    security: "modGroupSecurity",
    core: "modGroupCore",
    other: "modGroupOther"
  }[category]);
}

function selectionMark() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M3.5 8.2 6.5 11l6-6.5");
  svg.append(path);
  return svg;
}

function renderMods(reset = true) {
  const list = $("#mod-list");
  if (!list || !state.catalog) return;
  const current = new Set(reset ? defaultMods() : selectedMods());
  const names = state.catalog.modsByVersion[selectedModVersion()] || [];
  renderReleaseVersion();
  renderCustomPresetLabelEditor();
  list.replaceChildren();
  if (!names.length) {
    const empty = document.createElement("div"); empty.className = "mod-empty"; empty.textContent = t("noMods"); list.append(empty);
  }
  const groups = new Map();
  names.forEach((name) => {
    const category = modCategory(name);
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(name);
  });
  ["google", "camera", "interface", "security", "core", "other"].forEach((category) => {
    const groupNames = groups.get(category);
    if (!groupNames?.length) return;
    const section = document.createElement("section"); section.className = "mod-group"; section.dataset.category = category;
    const header = document.createElement("header");
    const title = document.createElement("h3"); title.textContent = modCategoryLabel(category);
    const count = document.createElement("span"); count.textContent = String(groupNames.length);
    const items = document.createElement("div"); items.className = "mod-group-items";
    header.append(title, count); section.append(header, items);
    groupNames.forEach((name) => {
      const label = document.createElement("label");
      const input = document.createElement("input"); input.type = "checkbox"; input.value = name; input.checked = current.has(name);
      const span = document.createElement("span"); span.title = name;
      const text = document.createElement("b"); text.textContent = name;
      span.append(selectionMark(), text); label.append(input, span); items.append(label);
    });
    list.append(section);
  });
  updateSummary();
}

function renderPipelineSteps(reset = true) {
  const container = $("#steps");
  const current = new Set(reset ? [] : $$("#steps input:checked").map((input) => input.value));
  container.replaceChildren(...(state.catalog?.pipelineSteps || []).map((step) => {
    const label = document.createElement("label");
    const input = document.createElement("input"); input.type = "checkbox"; input.value = step.id; input.checked = reset ? Boolean(step.default) : current.has(step.id);
    const span = document.createElement("span"); span.textContent = pipelineLabels[state.language][step.id] || step.label;
    label.append(input, span); return label;
  }));
  updatePipelineCount();
}

function renderCatalog() {
  if (!state.catalog || !$("#device-list")) return;
  const query = ($("#catalog-search")?.value || "").trim().toLocaleLowerCase();
  const version = $("#catalog-version")?.value || state.catalog.modVersions[0];
  const devices = state.catalog.devices.filter((item) => `${item.product} ${item.name}`.toLocaleLowerCase().includes(query));
  const mods = (state.catalog.modsByVersion[version] || []).filter((name) => name.toLocaleLowerCase().includes(query));
  $("#device-list").replaceChildren(...devices.map((item) => {
    const row = document.createElement("div"); row.className = "device-row";
    const code = document.createElement("b"); code.textContent = item.product;
    const name = document.createElement("span"); name.textContent = item.name;
    const copy = document.createElement("span"); copy.className = "device-copy"; copy.append(code, name);
    row.append(copy); return row;
  }));
  $("#catalog-mod-list").replaceChildren(...mods.map((name) => {
    const item = document.createElement("span"); item.textContent = name; return item;
  }));
  if (!devices.length && !mods.length) {
    const empty = document.createElement("span"); empty.className = "catalog-empty"; empty.textContent = t("noCatalogMatches");
    $("#catalog-mod-list").append(empty);
  }
  $("#device-count").textContent = String(devices.length);
  $("#catalog-mod-count").textContent = String(mods.length);
  const totalMods = Object.values(state.catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
  $("#catalog-total").textContent = t("catalogSummary", { devices: state.catalog.devices.length, mods: totalMods });
  renderAdminReleaseEditor();
  renderAdminPresetLabels();
}

function filterMods() {
  const query = ($("#mod-search")?.value || "").trim().toLocaleLowerCase();
  $$("#mod-list label").forEach((label) => {
    label.hidden = Boolean(query) && !label.textContent.toLocaleLowerCase().includes(query);
  });
  $$("#mod-list .mod-group").forEach((group) => {
    group.hidden = ![...group.querySelectorAll("label")].some((label) => !label.hidden);
  });
}

function updateTelegramState() {
  const authenticated = Boolean(effectiveInitData() || activeSignedLaunchToken());
  const keyboardConnected = telegramTransportAvailable();
  const sessionAvailable = authenticated || keyboardConnected;
  const connected = miniApiAvailable();
  const connection = $("#telegram-state");
  const connectionText = connection?.querySelector("span");
  if (connectionText) {
    const stateKey = connected ? "connected" : sessionAvailable ? "apiSessionOnly" : "previewMode";
    connectionText.dataset.i18n = stateKey;
    connectionText.textContent = t(stateKey);
  }
  connection?.classList.toggle("preview", !connected);
  $("#telegram-health")?.classList.toggle("ok", connected);
  const authText = $("#telegram-auth-state");
  if (authText) {
    const stateKey = connected ? "authenticated" : sessionAvailable ? "apiUnavailableMessage" : "authenticatedPreview";
    authText.dataset.i18n = stateKey;
    authText.textContent = t(stateKey);
  }
}

function updatePipelineCount() {
  const all = $$("#steps input");
  const selected = all.filter((input) => input.checked).length;
  if ($("#pipeline-count")) $("#pipeline-count").textContent = `${selected}/${all.length}`;
}

function setMods(mode) {
  const defaults = new Set(defaultMods());
  $$("#mod-list input").forEach((input) => { input.checked = mode === "all" || (mode === "defaults" && defaults.has(input.value)); });
  if (mode !== "defaults") $("#preset").value = "custom";
  renderCustomPresetLabelEditor();
  updateSummary();
}

function runnerLabel(value) {
  return t(value === "github-hosted" ? "runnerHosted" : value === "self-hosted-linux" ? "runnerSelf" : "runnerAuto");
}

function updateDeliveryStates() {
  $$(".switches input").forEach((input) => {
    const status = input.checked ? state.delivery[input.id] || "pending" : "skipped";
    const label = input.closest("label");
    if (label) label.dataset.state = status;
    const stateText = input.closest("label")?.querySelector("em");
    const key = { pending: "pipelinePending", running: "pipelineRunning", complete: "pipelineComplete", failed: "pipelineFailed", skipped: "pipelineSkipped" }[status];
    if (stateText) stateText.textContent = t(key || "pipelinePending");
  });
}

function setDeliveryState(stage, status) {
  if (!Object.hasOwn(state.delivery, stage) || !["pending", "running", "complete", "failed"].includes(status)) return false;
  state.delivery[stage] = status;
  updateDeliveryStates();
  return true;
}

function updateChecklistItem(id, done, completeKey, pendingKey) {
  const item = document.getElementById(id);
  if (!item) return;
  item.classList.toggle("complete", done);
  const detail = item.querySelector("small");
  if (detail) detail.textContent = t(done ? completeKey : pendingKey);
}

function updateSummary() {
  const selectionSummary = $("#config-summary");
  if (selectionSummary) selectionSummary.textContent = t("selectionSummary", { mods: selectedMods().length, steps: $$("#steps input:checked").length });
  const selectedDevice = $("#device")?.value || "";
  const device = selectedDevice || "—";
  const preset = $("#preset")?.value || "plus";
  const runner = runnerLabel($("#execution")?.value || "github-auto");
  const release = selectedReleaseVersion();
  $("#route-label").textContent = runner;
  const summary = `${device} · ${release} / ${presetLabel(preset)} / ${runner}`;
  $("#launch-summary").textContent = summary;
  if ($("#mobile-launch-summary")) $("#mobile-launch-summary").textContent = summary;
  $("#mod-count").textContent = `${selectedMods().length} ${t("selected")}`;
  const currentUri = $("#source-uri")?.value?.trim() || "";
  const sourceDetection = classifySource(currentUri);
  const sourceReady = Boolean(sourceDetection?.valid);
  const apiReady = miniApiAvailable();
  const quotaReady = Boolean(
    state.me?.accessStatus === "approved"
    && (state.me?.unlimited || Number(state.me?.buildCredits || 0) > 0)
  );
  const sourceVerified = sourceDetection?.kind === "rclone"
    ? sourceReady
    : sourceReady && state.sourceProbeUri === currentUri && ["analyzed", "partial"].includes(state.sourceProbe?.status);
  const sourceNeedsRefresh = sourceReady && state.sourceProbeUri === currentUri && state.sourceProbe?.status === "preview-only";
  const runnerReady = Boolean($("#execution")?.value);
  const ready = sourceVerified && Boolean(selectedDevice) && runnerReady && apiReady && quotaReady;
  const completedChecks = [sourceVerified, Boolean(selectedDevice), runnerReady, apiReady && quotaReady].filter(Boolean).length;
  const docket = $(".dispatch-docket");
  docket?.classList.toggle("incomplete", !ready);
  const runtimeState = $("#runtime-pipeline-state");
  const runtimeDot = $("#runtime-pipeline-dot");
  if (runtimeState) runtimeState.textContent = t(ready ? "runtimeReady" : "runtimeWaiting");
  runtimeDot?.classList.toggle("waiting", !ready);
  runtimeDot?.classList.toggle("online", ready);
  if ($("#readiness-label")) $("#readiness-label").textContent = t(ready ? "readyLabel" : "incompleteLabel");
  if ($("#readiness-count")) $("#readiness-count").textContent = t("readinessProgress", { done: completedChecks });
  if ($("#launch-warning")) {
    const warningKey = ready ? "fallbackWarning" : !apiReady ? "apiRequiredHint" : !quotaReady ? "quotaRequiredHint" : sourceNeedsRefresh ? "probeSignedPreviewOnly" : sourceReady && !sourceVerified ? "sourceProbePendingHint" : sourceReady ? "chooseDeviceHint" : "completeSourceHint";
    $("#launch-warning").textContent = t(warningKey);
  }
  const recovery = $("#session-recovery");
  if (recovery) recovery.hidden = apiReady || !miniApiEndpoint;
  const connect = $("#connect-telegram");
  if (connect) {
    connect.disabled = state.pairingInFlight;
    connect.textContent = state.pairingInFlight ? t("pairingWaiting") : t("pairingButton");
  }
  updateChecklistItem("check-source", sourceVerified, "checklistSourceVerified", sourceNeedsRefresh ? "checklistSourceRefreshRequired" : sourceReady ? "checklistSourceProbePending" : "checklistSourcePending");
  updateChecklistItem("check-device", Boolean(selectedDevice), "checklistDeviceDone", "checklistDevicePending");
  updateChecklistItem("check-runner", runnerReady, "checklistRunnerDone", "checklistRunnerDone");
  updateChecklistItem("check-api", apiReady && quotaReady, "checklistApiDone", miniApiEndpoint ? "checklistApiAuthPending" : "checklistApiPending");
  if ($("#submit-recipe")) $("#submit-recipe").disabled = !ready;
  updateDeliveryStates();
  $$('[data-i18n="launch"], [data-i18n="finishSource"]').forEach((node) => {
    node.dataset.i18n = ready ? "launch" : "finishSource";
    node.textContent = t(ready ? "launch" : "finishSource");
  });
  $("#dispatch-fab")?.setAttribute("aria-label", t("fabBuild"));
}

function positiveInteger(input, errorKey) {
  const raw = input.value.trim();
  if (!raw) return undefined;
  if (!/^\d+$/.test(raw) || Number(raw) <= 0 || !Number.isSafeInteger(Number(raw))) throw new Error(t(errorKey));
  return Number(raw);
}

function sourceSpec() {
  const uri = $("#source-uri").value.trim();
  const detection = classifySource(uri);
  if (!detection?.valid) throw new Error(t("invalidUrl"));
  const source = { kind: detection.kind, uri };
  const size = positiveInteger($("#source-size"), "invalidSize");
  if (size) source.sizeBytes = size;
  return source;
}

function selectedReleaseVersion() {
  const version = selectedBaseModVersion();
  return String(
    state.releaseVersionOverrides[version]
    || state.catalog?.modReleaseVersions?.[version]
    || version
    || "—"
  );
}

function selectedBaseModVersion() {
  return $("#mod-version")?.value || "";
}

function selectedModVersion() {
  return selectedBaseModVersion();
}

function currentEditionLabels() {
  const labels = { ...state.presetLabels };
  if (state.customPresetLabelOverride) labels.custom = state.customPresetLabelOverride;
  return labels;
}

function presetLabel(key, labels = undefined) {
  let normalized = String(key || "").toLowerCase();
  if (normalized === "resume") normalized = "plus";
  if (normalized === "standard") normalized = "lite";
  const map = labels && typeof labels === "object" ? labels : currentEditionLabels();
  if (normalized === "both") return `${map.lite || "Lite"} + ${map.plus || "Plus"}`;
  return map[normalized] || ({ lite: "Lite", plus: "Plus", custom: "Custom" }[normalized] || normalized);
}

function presetEntries() {
  return [
    { value: "lite", label: presetLabel("lite") },
    { value: "plus", label: presetLabel("plus") },
    { value: "both", label: presetLabel("both") },
    { value: "custom", label: presetLabel("custom") }
  ];
}

function renderPresetLabels() {
  const selected = $("#preset")?.value || "plus";
  const defaultSelected = $("#default-preset")?.value || state.defaultPreset;
  const entries = presetEntries();
  if ($("#preset")) options($("#preset"), entries, selected);
  if ($("#default-preset")) options($("#default-preset"), entries, defaultSelected);
  renderAdminPresetLabels();
  renderCustomPresetLabelEditor();
}

function renderCustomPresetLabelEditor() {
  const editor = $("#custom-preset-label-editor");
  const input = $("#custom-preset-label-input");
  if (!editor || !input) return;
  const visible = $("#preset")?.value === "custom";
  editor.hidden = !visible;
  if (visible && document.activeElement !== input) {
    input.value = state.customPresetLabelOverride || state.presetLabels.custom || "Custom";
  }
}

function applyCustomPresetLabelForJob() {
  if ($("#preset")?.value !== "custom") return;
  const label = $("#custom-preset-label-input").value.trim();
  if (!isSafePresetLabel(label)) throw new Error(t("invalidPresetLabel"));
  state.customPresetLabelOverride = label;
  renderPresetLabels();
  updateSummary();
  toast(t("customPresetJobSaved"));
}

function isSafePresetLabel(value) {
  return Boolean(value)
    && value.length <= 64
    && !/[\\/\x00-\x1f<>:\"|?*]/.test(value)
    && !/[ .]$/.test(value)
    && !/^\.+$/.test(value);
}

function renderReleaseVersion() {
  const label = selectedReleaseVersion();
  const display = $("#mod-release-version");
  const title = $("#release-version-title");
  const hint = $("#release-version-hint");
  const input = $("#mod-release-version-input");
  if (display) display.textContent = label;
  if (title) title.textContent = t("releaseVersion");
  if (hint) hint.textContent = t("releaseVersionHint");
  if (input) {
    input.value = label === "—" ? "" : label;
    input.placeholder = t("releaseVersionPlaceholder");
    input.setAttribute("aria-label", t("releaseVersion"));
  }
}

async function saveReleaseVersion() {
  const version = selectedBaseModVersion();
  const label = $("#mod-release-version-input").value.trim();
  if (!isSafePresetLabel(label)) throw new Error(t("invalidReleaseVersion"));
  const defaultLabel = String(state.catalog?.modReleaseVersions?.[version] || version);
  if (label === defaultLabel) delete state.releaseVersionOverrides[version];
  else state.releaseVersionOverrides[version] = label;
  renderReleaseVersion();
  updateSummary();
  toast(t("releaseVersionSaved"));
}

function sameStringList(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

function normalizedDebloatPaths(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderDebloatSummary() {
  const count = $("#debloat-path-count");
  const status = $("#debloat-path-state");
  if (count) count.textContent = t("debloatPathCount", { count: state.debloatPaths.length });
  if (status) status.textContent = t(state.debloatPathsCustomized ? "debloatCustomState" : "debloatDefaultState");
}

function openDebloatEditor() {
  const editor = $("#debloat-editor");
  const input = $("#debloat-paths");
  if (!editor || !input) return;
  input.value = state.debloatPaths.join("\n");
  editor.hidden = false;
  $("#edit-debloat-paths").hidden = true;
  requestAnimationFrame(() => input.focus({ preventScroll: true }));
}

function closeDebloatEditor() {
  const editor = $("#debloat-editor");
  if (editor) editor.hidden = true;
  $("#edit-debloat-paths").hidden = false;
}

function saveDebloatPaths() {
  state.debloatPaths = normalizedDebloatPaths($("#debloat-paths").value);
  state.debloatPathsCustomized = !sameStringList(
    state.debloatPaths,
    state.catalog?.defaultDebloatPaths || []
  );
  closeDebloatEditor();
  renderDebloatSummary();
  toast(t("debloatSaved"));
}

function resetJobDraft() {
  const source = $("#source-uri");
  if (source) {
    source.value = "";
    source.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const size = $("#source-size");
  if (size) size.value = "";
  state.customPresetLabelOverride = "";
  state.releaseVersionOverrides = {};
  state.debloatPaths = [...(state.catalog?.defaultDebloatPaths || [])];
  state.debloatPathsCustomized = false;
  closeDebloatEditor();
  renderDebloatSummary();
  renderReleaseVersion();
  renderPresetLabels();
  try { localStorage.removeItem("wukong-recipe-draft"); } catch (_) {}
}

function buildRecipe() {
  if (!$("#device").value) throw new Error(t("deviceRequired"));
  const recipe = {
    schemaVersion: 1, task: "build", device: $("#device").value, source: sourceSpec(),
    execution: { target: $("#execution").value },
    storage: { remote: "wukong-gdrive", publishArtifact: $("#publish").checked }
  };
  recipe.build = {
      preset: $("#preset").value, modVersion: selectedModVersion(), mods: selectedMods(), editionLabels: currentEditionLabels(),
      modReleaseVersion: selectedReleaseVersion(),
      enabledSteps: $$("#steps input:checked").map((input) => input.value),
      package: $("#package").checked, notifyTelegram: $("#notify").checked
    };
    // The shared default list is intentionally visible/editable in the Mini App.
    // Omitting an unchanged list is lossless: every runner resolves a missing
    // debloatPaths field from the same versioned config/debloat.json catalog.
    if (!sameStringList(state.debloatPaths, state.catalog.defaultDebloatPaths)) {
      recipe.build.debloatPaths = [...state.debloatPaths];
    }
  return recipe;
}

function restorePendingSubmission() {
  let pending = null;
  try { pending = JSON.parse(localStorage.getItem("wukong-submit-request") || "null"); } catch (_) {}
  const subject = String(state.me?.telegramId || "");
  state.submitUncertain = Boolean(subject && pending?.subject === subject && pending.recipe && pending.key);
  if (subject && pending && pending.subject !== subject) localStorage.removeItem("wukong-submit-request");
  renderSubmitRecovery();
}

function renderSubmitRecovery() {
  const recovery = $("#submit-recovery");
  if (!recovery) return;
  recovery.hidden = !state.submitUncertain;
  recovery.querySelector("p").textContent = t("confirmingJob");
}

async function submitRecipe() {
  if (!miniApiAvailable()) throw new Error(t(miniApiUnavailableMessageKey()));
  restorePendingSubmission();
  let savedRequest = null;
  try { savedRequest = JSON.parse(localStorage.getItem("wukong-submit-request") || "null"); } catch (_) {}
  const recipe = state.submitUncertain && savedRequest?.recipe ? JSON.parse(savedRequest.recipe) : buildRecipe();
  const canonical = JSON.stringify(recipe);
  let pending = null;
  try { pending = JSON.parse(localStorage.getItem("wukong-submit-request") || "null"); } catch (_) {}
  if (!pending || pending.recipe !== canonical || !pending.key) {
    pending = { subject: String(state.me?.telegramId || ""), recipe: canonical, key: crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` };
    localStorage.setItem("wukong-submit-request", JSON.stringify(pending));
  }
  let job;
  try {
    job = await apiRequest("/v1/jobs", { method: "POST", headers: { "Idempotency-Key": pending.key }, body: canonical });
    localStorage.removeItem("wukong-submit-request");
    state.submitUncertain = false; renderSubmitRecovery();
  } catch (error) {
    if (!error.connectionFailed && !error.uncertain && error.status < 500) {
      localStorage.removeItem("wukong-submit-request"); state.submitUncertain = false; renderSubmitRecovery();
    }
    else {
      state.submitUncertain = true;
      error.message = t("confirmingJob");
      renderSubmitRecovery();
    }
    throw error;
  }
  state.activeJobId = job.job_id || job.jobId;
  localStorage.setItem("wukong-active-job", state.activeJobId);
  // Reflect the confirmed job before ancillary cleanup. A profile refresh or
  // draft deletion failure must never hide a successful submission.
  state.submitUncertain = false;
  renderSubmitRecovery();
  toast(t("buildCreated"));
  navigate("jobs");
  await loadJobs({ force: true }).catch(() => {});
  resetJobDraft();
  await apiRequest("/v1/drafts/source", { method: "DELETE" }).catch(() => {});
  await loadSession({ countOpen: false }).catch(() => {});
}

export { selectedMods, defaultMods, modCategory, modCategoryLabel, selectionMark, renderMods, renderPipelineSteps, renderCatalog, filterMods, updateTelegramState, updatePipelineCount, setMods, runnerLabel, updateDeliveryStates, setDeliveryState, updateChecklistItem, updateSummary, positiveInteger, sourceSpec, selectedReleaseVersion, selectedBaseModVersion, selectedModVersion, currentEditionLabels, presetLabel, presetEntries, renderPresetLabels, renderCustomPresetLabelEditor, applyCustomPresetLabelForJob, isSafePresetLabel, renderReleaseVersion, saveReleaseVersion, sameStringList, normalizedDebloatPaths, renderDebloatSummary, openDebloatEditor, closeDebloatEditor, saveDebloatPaths, resetJobDraft, buildRecipe, restorePendingSubmission, renderSubmitRecovery, submitRecipe };

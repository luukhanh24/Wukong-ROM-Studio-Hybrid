import { $, miniApiEndpoint, state, t } from "./state.js";
import { probeSourceInPlace, updateSourceDetection } from "./source-rom.js";
import { options, toast } from "./shell.js";
import { renderCatalog, renderDebloatSummary, renderMods, renderPipelineSteps, renderPresetLabels, renderReleaseVersion, updateSummary } from "./build.js";
import { apiRequest, privateApiAvailable } from "./session.js";
import { renderSelectedJob } from "./jobs.js";
import { renderBatchChoices, updateBatchSummary } from "./admin.js";

function scheduleSourceProbe() {
  clearTimeout(state.sourceProbeTimer);
  const uri = $("#source-uri").value.trim();
  if (!miniApiEndpoint || !/^https?:\/\//i.test(uri) || !state.sourceDetection?.valid) return;
  if (state.sourceProbeUri === uri && state.sourceProbe?.result) return;
  state.sourceProbeTimer = setTimeout(() => probeSourceInPlace().catch(() => {}), 450);
}

async function loadCatalog() {
  try {
    const response = await fetch("./catalog.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const catalog = await response.json();
    if (catalog.schemaVersion !== 1 || !Array.isArray(catalog.devices) || !Array.isArray(catalog.modVersions)) throw new Error("Invalid catalog");
    state.catalog = catalog;
    state.catalog.modReleaseVersions ||= {};
    state.presetLabels = { lite: "Lite", plus: "Plus", custom: "Custom", ...(catalog.presetLabels || {}) };
    state.debloatPaths = Array.isArray(catalog.defaultDebloatPaths) ? [...catalog.defaultDebloatPaths] : [];
    state.debloatPathsCustomized = false;
    options($("#device"), [{ value: "", label: t("chooseDevice") }, ...catalog.devices.map((item) => ({ value: item.product, label: `${item.product} — ${item.name}` }))]);
    options($("#mod-version"), catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    options($("#catalog-version"), catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })), catalog.modVersions.includes("ColorOS_16.0.9") ? "ColorOS_16.0.9" : catalog.modVersions.at(-1));
    renderPresetLabels();
    if (privateApiAvailable()) await Promise.all([refreshLiveReleaseVersions(), refreshLivePresetLabels()]);
    const count = Object.values(catalog.modsByVersion).reduce((total, names) => total + names.length, 0);
    $("#catalog-status").textContent = t("catalogReady", { mods: count, versions: catalog.modVersions.length });
    $("#catalog-status").closest("div").querySelector("i").classList.add("ok");
    renderPipelineSteps();
    renderMods();
    renderDebloatSummary();
    renderCatalog();
    updateSourceDetection();
    renderSelectedJob();
  } catch (error) {
    $("#catalog-status").textContent = t("catalogFailed");
    toast(t("catalogFailed"), true);
  }
}

async function refreshLiveReleaseVersions() {
  if (!state.catalog || !privateApiAvailable()) return;
  try {
    const selected = $("#mod-version").value;
    const live = await apiRequest("/v1/mod-release-versions");
    state.catalog.modReleaseVersions = { ...state.catalog.modReleaseVersions, ...(live.modReleaseVersions || {}) };
    options(
      $("#mod-version"),
      state.catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })),
      selected,
    );
    const catalogSelected = $("#catalog-version").value || selected;
    options(
      $("#catalog-version"),
      state.catalog.modVersions.map((value) => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })),
      catalogSelected,
    );
    renderReleaseVersion();
    renderCatalog();
  } catch (_) { /* static labels remain usable while the authenticated API reconnects */ }
}

async function refreshLivePresetLabels() {
  if (!state.catalog || !privateApiAvailable()) return;
  try {
    const live = await apiRequest("/v1/preset-labels");
    state.presetLabels = { ...state.presetLabels, ...(live.presetLabels || {}) };
    renderPresetLabels();
    renderBatchChoices();
    updateBatchSummary();
    updateSummary();
  } catch (_) { /* static labels remain usable while the authenticated API reconnects */ }
}

export { scheduleSourceProbe, loadCatalog, refreshLiveReleaseVersions, refreshLivePresetLabels };

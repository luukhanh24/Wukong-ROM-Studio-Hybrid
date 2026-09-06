import { $, completenessSourceFactIds, miniApiEndpoint, requiredSourceFactIds, runtime, sourceFactDefinitions, state, t } from "./state.js";
import { toast } from "./shell.js";
import { apiRequest, effectiveInitData, effectiveInitDataUnsafe, miniApiAvailable, presentMissingApi } from "./session.js";
import { scheduleSourceProbe } from "./catalog.js";
import { renderMods, updateSummary } from "./build.js";
async function inspectProbeZipMetadata(...args) {
  const module = await import("./zip-metadata.js");
  return module.inspectProbeZipMetadata(...args);
}

function classifySource(rawValue) {
  const value = rawValue.trim();
  if (!value) return null;
  if (/^[A-Za-z]:[\\/]/.test(value) || /^\\\\/.test(value)) return { valid: false };
  const rclone = /^([A-Za-z0-9][A-Za-z0-9_.-]*):(?!\/\/)(.+)$/.exec(value);
  if (rclone && !rclone[1].includes("\\")) {
    return { valid: true, kind: "rclone", provider: t("providerDrive"), type: t("sourceDriveType"), marker: "DRV" };
  }
  let url;
  try { url = new URL(value); } catch { return { valid: false }; }
  if (!/^https?:$/.test(url.protocol)) return { valid: false };
  const host = url.hostname.toLowerCase();
  const path = url.pathname.toLowerCase();
  let provider = t("providerDirect");
  let type = t("sourceDirect");
  let marker = "HTTP";
  if (host.includes("allawn") || host.includes("oppo") || host.includes("coloros") || path.endsWith("/downloadcheck")) {
    provider = "OPlus OTA"; type = path.endsWith("/downloadcheck") ? t("sourceResolver") : t("sourceDirect"); marker = "OTA";
  } else if (host === "roms.danielspringer.at") {
    provider = "Daniel Springer"; type = url.searchParams.has("build") ? t("sourcePage") : t("sourceDirect"); marker = "OTA";
  } else if (host.includes("drive.google.com")) {
    provider = "Google Drive"; type = t("sourceDriveType"); marker = "DRV";
  }
  let decoded = "";
  try { decoded = decodeURIComponent(url.pathname); } catch { decoded = url.pathname; }
  const device = state.catalog?.devices?.find((item) => decoded.toLowerCase().includes(String(item.product).toLowerCase()))?.product || "";
  const version = decoded.match(/(?:^|[_-])(\d{1,2}(?:\.\d+){1,3}(?:\([^)]*\))?)(?:[_./-]|$)/)?.[1] || "";
  return { valid: true, kind: url.protocol === "https:" ? "https" : "http", provider, type, marker, device, version };
}

function setSourceFact(id, value) {
  const node = $(`#${id}`);
  if (!node) return;
  const text = String(value || "").trim();
  node.textContent = text || "—";
  node.dataset.empty = text && text !== "—" ? "false" : "true";
  node.title = text && text !== "—" ? text : "";
}

function updateMetadataCompleteness() {
  const completed = (ids) => ids.filter((id) => {
    const value = $(`#${id}`)?.textContent?.trim();
    return value && value !== "—" && value !== "···";
  }).length;
  const complete = completed(completenessSourceFactIds);
  const total = completenessSourceFactIds.length;
  const requiredComplete = completed(requiredSourceFactIds);
  $("#source-metadata-count").textContent = t("metadataCompleteness", { complete, total });
  return {
    complete,
    total,
    requiredComplete,
    requiredTotal: requiredSourceFactIds.length
  };
}

function resetSourceFacts(detection, uri) {
  sourceFactDefinitions.forEach(([id]) => setSourceFact(id, ""));
  if (!detection?.valid) { updateMetadataCompleteness(); return; }
  setSourceFact("source-provider", detection.provider);
  setSourceFact("source-product-detected", detection.device);
  setSourceFact("source-version-detected", detection.version);
  setSourceFact("source-host", detection.kind === "rclone" ? "Google Drive" : new URL(uri).hostname);
  updateMetadataCompleteness();
}

function sourceMetadataText() {
  return sourceFactDefinitions.map(([id, key]) => `${t(key)}: ${$(`#${id}`)?.textContent?.trim() || "—"}`).join("\n");
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch (_) { /* Try the WebView-compatible copy path. */ }
  }
  {
    const input = document.createElement("textarea"); input.value = text;
    input.style.position = "fixed"; input.style.opacity = "0"; input.style.pointerEvents = "none";
    document.body.append(input); input.select();
    const copied = document.execCommand("copy");
    input.remove();
    if (!copied) throw new Error("Clipboard copy failed");
  }
}

async function copySourceMetadata() {
  await copyText(sourceMetadataText());
  toast(t("metadataCopied"));
}

function readTelegramClipboard() {
  if (typeof runtime.TelegramApp?.readTextFromClipboard !== "function") return Promise.resolve({ text: "", readable: false });
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve({ text: typeof value === "string" ? value : "", readable: typeof value === "string" });
    };
    const timeout = setTimeout(() => finish(null), 1200);
    try { runtime.TelegramApp.readTextFromClipboard(finish); } catch (_) { finish(null); }
  });
}

async function readClipboardText() {
  const input = $("#source-uri");
  input.focus({ preventScroll: true });
  // Some Android WebViews only honor the legacy paste command while the
  // original trusted click is still active. Try it synchronously before any
  // Promise/await can consume that transient user activation.
  try {
    const accepted = document.execCommand?.("paste") === true;
    const text = input.value.trim();
    if (accepted && text) return { text, readable: true };
  } catch (_) {}
  if (navigator.clipboard?.readText) {
    try {
      const result = await Promise.race([
        navigator.clipboard.readText().then((text) => ({ text, readable: true })),
        new Promise((resolve) => setTimeout(() => resolve({ text: "", readable: false }), 500)),
      ]);
      if (result.readable) return result;
    } catch (_) {}
  }
  const telegram = await readTelegramClipboard();
  if (telegram.readable) return telegram;
  return { text: "", readable: false };
}

async function pasteSourceFromClipboard() {
  const clipboard = await readClipboardText();
  let value = String(clipboard.text || "").trim();
  let fromDraft = false;
  if (!value && miniApiAvailable()) {
    try {
      const draft = await apiRequest("/v1/drafts/source");
      value = String(draft.uri || "").trim();
      fromDraft = Boolean(value);
    } catch (_) {}
  }
  const input = $("#source-uri");
  if (!value) {
    input.focus({ preventScroll: true });
    input.select();
    toast(t(clipboard.readable ? "clipboardEmpty" : "clipboardManual"));
    return;
  }
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.focus({ preventScroll: true });
  toast(t(fromDraft ? "draftPasted" : "linkPasted"));
}

function clearSource() {
  const input = $("#source-uri");
  input.value = "";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  toast(t("sourceCleared"));
}

function restoreSourceDraft() {
  // One-time cleanup of the legacy draft that used to persist signed links.
  try { localStorage.removeItem("wukong-source-draft"); } catch (_) {}
  try { localStorage.removeItem("wukong-recipe-draft"); } catch (_) {}
  // Clear a fragment-only paste (e.g. "6a8a..." pasted without https://) that
  // was left in the textarea by autofill or a previous session.
  const input = $("#source-uri");
  if (!input) return;
  const current = input.value.trim();
  if (current && !/^https?:\/\//i.test(current)) input.value = "";
  if (input.value.trim()) return;
  let startParam = "";
  try { startParam = decodeURIComponent(String(effectiveInitDataUnsafe()?.start_param || "")); } catch (_) { startParam = String(effectiveInitDataUnsafe()?.start_param || ""); }
  if (!startParam || !/^https?:\/\//i.test(startParam)) return;
  input.value = startParam;
  updateSourceDetection();
  scheduleSourceProbe();
}

function updateSourceDetection() {
  const node = $("#source-state");
  if (!node) return;
  const currentUri = $("#source-uri").value.trim();
  const detection = classifySource(currentUri);
  const uriChanged = state.sourceInputUri !== currentUri;
  if (uriChanged) {
    state.sourceInputUri = currentUri;
    state.sourceProbeRequestId += 1;
    state.sourceProbeController?.abort();
    state.sourceProbeController = null;
    $("#source-size").value = "";
    state.sourceProbeUri = "";
    if (state.sourceAutoDevice && $("#device").value === state.sourceAutoDevice) {
      $("#device").value = "";
      updateSummary();
    }
    state.sourceAutoDevice = null;
    state.sourceProbe = null;
  }
  state.sourceDetection = detection;
  updateSummary();
  node.classList.toggle("detected", Boolean(detection?.valid));
  node.classList.toggle("invalid", Boolean(detection && !detection.valid));
  node.classList.remove("probing", "analyzed", "preview-only", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  const marker = node.querySelector(".source-state-mark span");
  const facts = $("#source-facts");
  const factsHead = $("#source-facts-head");
  const probe = $("#probe-source");
  probe.disabled = false;
  probe.textContent = t("analyzeSource");
  if (!detection) {
    marker.textContent = "URL";
    $("#source-kicker").textContent = t("sourceIdleKicker");
    $("#source-state-title").textContent = t("sourceIdleTitle");
    $("#source-state-message").textContent = t("sourceIdleMessage");
    resetSourceFacts(null, "");
    facts.hidden = true; factsHead.hidden = true; probe.hidden = true; return;
  }
  if (!detection.valid) {
    marker.textContent = "?";
    $("#source-kicker").textContent = t("sourceInvalidKicker");
    $("#source-state-title").textContent = t("sourceInvalidTitle");
    $("#source-state-message").textContent = t("sourceInvalidMessage");
    resetSourceFacts(null, "");
    facts.hidden = true; factsHead.hidden = true; probe.hidden = true; return;
  }
  marker.textContent = detection.marker;
  $("#source-kicker").textContent = t("sourceDetectedKicker");
  $("#source-state-title").textContent = `${detection.provider} · ${detection.type}`;
  $("#source-state-message").textContent = t("deepProbeHint");
  resetSourceFacts(detection, currentUri);
  facts.hidden = false; factsHead.hidden = false;
  probe.hidden = detection.marker === "DRV";
  if (detection.device && [...$("#device").options].some((option) => option.value === detection.device)) {
    $("#device").value = detection.device;
    state.sourceAutoDevice = detection.device;
    updateSummary();
  }
  if (!$("#device").value) {
    $(".source-manual").open = true;
  }
  if (state.sourceProbeUri === currentUri && state.sourceProbe?.result) {
    const completeness = applyProbeResult(state.sourceProbe.result, currentUri, { announce: false });
    const previewOnly = state.sourceProbe.status === "preview-only";
    const coreComplete = completeness.requiredComplete === completeness.requiredTotal;
    setProbePresentation(previewOnly ? "preview-only" : coreComplete ? "analyzed" : "probe-limited", previewOnly ? "probeSignedPreviewOnly" : coreComplete ? "probeSuccess" : "probePartial");
    return;
  }
  if (!probe.hidden && !miniApiEndpoint) presentMissingApi();
}

function setProbePresentation(status, messageKey) {
  const node = $("#source-state");
  node.classList.remove("probing", "analyzed", "preview-only", "probe-deferred", "probe-limited", "probe-failed", "probe-unavailable", "backend-offline");
  node.classList.add(status);
  const kickerKey = status === "analyzed" ? "probeReadyKicker" : status === "preview-only" ? "probeLimitedKicker" : status === "probe-failed" ? "probeFailedKicker" : status === "probe-deferred" ? "probeDeferredKicker" : status === "probe-limited" ? "probeLimitedKicker" : "sourceDetectedKicker";
  $("#source-kicker").textContent = t(kickerKey);
  $("#source-state-message").textContent = t(messageKey);
}

async function probeSourceViaBackend(uri, signal) {
  const options = {
    method: "POST",
    body: JSON.stringify({ uri }),
    timeoutMs: 110000,
    signal
  };
  if (effectiveInitData()) return apiRequest("/v1/sources/probe", options);
  const headers = new Headers({ "Content-Type": "application/json" });
  let response;
  try {
    response = await fetch(`${miniApiEndpoint}/v1/sources/probe`, { ...options, headers, cache: "no-store" });
  } catch (cause) {
    if (cause?.name === "AbortError") throw cause;
    const error = new Error(t("requestFailed"));
    error.connectionFailed = true;
    throw error;
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.code = payload.code || "";
    error.status = response.status;
    error.sourceRejected = response.status >= 400 && response.status < 500;
    throw error;
  }
  return payload;
}

function normalizeDevice(value) {
  return String(value || "").toLocaleUpperCase().replace(/[^A-Z0-9]/g, "");
}

function matchCatalogDevice(result, detected, inferred, filename) {
  const versionProduct = String(result?.version || "").split("_", 1)[0];
  const candidates = [result?.productName, versionProduct, filename, result?.device, detected?.device, inferred?.device]
    .map(normalizeDevice).filter(Boolean);
  return state.catalog?.devices?.find((item) => {
    const product = normalizeDevice(item.product);
    return candidates.some((candidate) => candidate === product || candidate.startsWith(product) || candidate.includes(product));
  })?.product || "";
}

function selectModPackForVersion(version) {
  const match = String(version || "").match(/_(\d+\.\d+\.\d+)/);
  if (!match) return;
  const preferred = `ColorOS_${match[1]}`;
  if (state.catalog?.modVersions?.includes(preferred) && $("#mod-version").value !== preferred) {
    $("#mod-version").value = preferred;
    renderMods();
  }
}

function formatBytes(value) {
  let size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size.toFixed(index ? 2 : 0)} ${units[index]}`;
}

function applyProbeResult(result, uri, { announce = true } = {}) {
  const detected = state.sourceDetection;
  const url = new URL(uri);
  const rawFilename = url.pathname.split("/").filter(Boolean).at(-1) || "";
  const localFilename = /\.(?:zip|ozip|bin)$/i.test(rawFilename) ? decodeURIComponent(rawFilename) : "—";
  const filename = result?.filename || localFilename;
  const host = result?.resolvedHost || result?.host || url.hostname;
  const inferred = filename !== "—" ? classifySource(`https://${host}/${encodeURIComponent(filename)}`) : null;
  const device = matchCatalogDevice(result, detected, inferred, filename);
  const product = result?.productName || String(result?.version || "").split("_", 1)[0] || device;
  const version = result?.version || detected.version || inferred?.version || "";
  const size = Number(result?.sizeBytes || 0);
  setSourceFact("source-provider", result?.provider || detected.provider);
  setSourceFact("source-host", host);
  setSourceFact("source-filename", filename);
  setSourceFact("source-product-detected", product);
  setSourceFact("source-device-detected", result?.device);
  setSourceFact("source-version-detected", version);
  setSourceFact("source-android-version", result?.androidVersion);
  setSourceFact("source-security-patch", result?.securityPatch);
  setSourceFact("source-build-date", result?.buildDate);
  setSourceFact("source-size-detected", size > 0 ? `${formatBytes(size)} · ${size.toLocaleString(state.language === "vi" ? "vi-VN" : "en-US")} bytes` : "");
  setSourceFact("source-ota-type", result?.otaType);
  setSourceFact("source-content-type", result?.contentType);
  setSourceFact("source-md5", result?.md5);
  setSourceFact("source-last-modified", result?.lastModified);
  setSourceFact("source-deep-inspection", result?.deepInspected ? t("deepInspected") : t("headersOnly"));
  if (Number.isSafeInteger(size) && size > 0) $("#source-size").value = String(size);
  if (device && [...$("#device").options].some((option) => option.value === device)) {
    $("#device").value = device;
    state.sourceAutoDevice = device;
    if (announce) toast(t("autoSelected", { device }));
  }
  selectModPackForVersion(version);
  state.sourceProbeUri = uri;
  const completeness = updateMetadataCompleteness();
  state.sourceProbe = { status: result?.cloudBuildReady === false ? "preview-only" : completeness.requiredComplete === completeness.requiredTotal ? "analyzed" : "partial", result };
  updateSummary();
  return completeness;
}

async function probeSourceInPlace() {
  const button = $("#probe-source");
  const uri = $("#source-uri").value.trim();
  if (!state.sourceDetection?.valid || !/^https?:\/\//i.test(uri)) throw new Error(t("invalidUrl"));
  if (!miniApiEndpoint) { presentMissingApi(); return; }
  state.sourceProbeController?.abort();
  const controller = new AbortController();
  state.sourceProbeController = controller;
  const requestId = ++state.sourceProbeRequestId;
  let timedOut = false;
  // Free control-plane hosts can require close to a minute to wake from an
  // idle cold start before the remote ZIP probe itself begins.
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 110000);
  button.disabled = true;
  button.textContent = t("probeAnalyzing");
  setProbePresentation("probing", "probeAnalyzing");
  try {
    let result = await probeSourceViaBackend(uri, controller.signal);
    try {
      result = await inspectProbeZipMetadata(result, controller.signal);
    } catch (inspectionError) {
      if (inspectionError?.name === "AbortError") throw inspectionError;
      result = {
        ...result,
        deepInspected: false,
        warning: inspectionError?.message || "ROM ZIP metadata is unavailable"
      };
    }
    if (requestId !== state.sourceProbeRequestId || uri !== $("#source-uri").value.trim()) return;
    const completeness = applyProbeResult(result, uri);
    const previewOnly = state.sourceProbe.status === "preview-only";
    const coreComplete = completeness.requiredComplete === completeness.requiredTotal;
    setProbePresentation(previewOnly ? "preview-only" : coreComplete ? "analyzed" : "probe-limited", previewOnly ? "probeSignedPreviewOnly" : coreComplete ? "probeSuccess" : "probePartial");
  } catch (error) {
    if (requestId !== state.sourceProbeRequestId || uri !== $("#source-uri").value.trim()) return;
    if (error?.name === "AbortError" && !timedOut) return;
    const sourceFailed = error?.sourceRejected && error?.status !== 429;
    const apiOffline = timedOut || error?.connectionFailed || navigator.onLine === false;
    const status = sourceFailed ? "probe-failed" : apiOffline ? "backend-offline" : "probe-deferred";
    const message = sourceFailed ? "probeFailed" : apiOffline ? "apiOfflineMessage" : "probeDeferred";
    state.sourceProbe = { status: sourceFailed ? "failed" : apiOffline ? "offline" : "deferred" };
    setProbePresentation(status, message);
    if (error?.code === "source_signed_url_expired") {
      $("#source-state-message").textContent = t("probeSignedExpired");
    }
    if (apiOffline) $("#source-kicker").textContent = t("apiOfflineKicker");
    toast(error?.code === "source_signed_url_expired" ? t("probeSignedExpired") : sourceFailed ? t("probeFailed") : apiOffline ? t("apiOfflineMessage") : t("probeDeferred"), true);
  } finally {
    clearTimeout(timeout);
    if (requestId === state.sourceProbeRequestId) {
      state.sourceProbeController = null;
      button.disabled = false;
      button.textContent = t("analyzeSource");
    }
  }
}

export { classifySource, setSourceFact, updateMetadataCompleteness, resetSourceFacts, sourceMetadataText, copyText, copySourceMetadata, readTelegramClipboard, readClipboardText, pasteSourceFromClipboard, clearSource, restoreSourceDraft, updateSourceDetection, setProbePresentation, probeSourceViaBackend, normalizeDevice, matchCatalogDevice, selectModPackForVersion, formatBytes, applyProbeResult, probeSourceInPlace };

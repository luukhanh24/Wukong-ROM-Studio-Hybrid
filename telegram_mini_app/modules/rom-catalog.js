import { $, $$, publicRomCatalogEndpoint, romDeviceBrands, romDeviceWords, state, t } from "./state.js";
import { apiRequest, privateApiAvailable } from "./session.js";
import { copyText, formatBytes } from "./source-rom.js";
import { navigate } from "./dock.js";
import { toast } from "./shell.js";

function normalizeRomDevice(device, queryKey = "device") {
  if (!device || typeof device !== "object") return null;
  const id = String(device.id ?? "").trim().slice(0, 128);
  const label = String(device.label ?? "").trim().slice(0, 256);
  const brand = String(device.brand ?? "").trim();
  if (!id || !label || !romDeviceBrands.has(brand.toLocaleLowerCase())) return null;
  const regions = (Array.isArray(device.regions) ? device.regions : [])
    .map((region) => {
      if (!region || typeof region !== "object") return null;
      const code = String(region.code ?? "").trim().toUpperCase().slice(0, 32);
      if (!code) return null;
      const models = [...new Set((Array.isArray(region.models) ? region.models : [])
        .map((model) => String(model ?? "").trim().slice(0, 128)).filter(Boolean))];
      return { code, models };
    }).filter(Boolean);
  return { id, label, brand, queryKey: queryKey === "model" ? "model" : "device", regions };
}

function romReleaseRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];
  for (const key of ["data", "releases", "results"]) {
    if (Array.isArray(payload[key])) return payload[key];
  }
  return [];
}

function romDevicesFromReleases(rows) {
  const devices = new Map();
  rows.forEach((row) => {
    if (!row || typeof row !== "object") return;
    const id = String(row.device ?? "").trim().slice(0, 128);
    if (!id || !/^(OP\s|OnePlus\s|OPPO\s|Realme\s)/i.test(id)) return;
    const key = id.toLocaleUpperCase();
    if (!devices.has(key)) {
      const label = id.split(/\s+/).map((word) => romDeviceWords[word.toLocaleUpperCase()] || word).join(" ");
      const brand = /^(OnePlus|OPPO|Realme)\b/i.exec(label)?.[1] || "Other";
      if (!romDeviceBrands.has(brand.toLocaleLowerCase())) return;
      devices.set(key, { id, label, brand, regions: new Map() });
    }
    const device = devices.get(key);
    const code = String(row.region ?? "").trim().toUpperCase().slice(0, 32);
    const model = String(row.model ?? "").trim().slice(0, 128);
    if (!code) return;
    if (!device.regions.has(code)) device.regions.set(code, new Set());
    if (model) device.regions.get(code).add(model);
  });
  return [...devices.values()]
    .sort((a, b) => a.brand.localeCompare(b.brand) || a.label.localeCompare(b.label, "en", { numeric: true }))
    .map((device) => ({ ...device, regions: [...device.regions.entries()]
      .sort(([a], [b]) => a.localeCompare(b)).map(([code, models]) => ({ code, models: [...models].sort() })) }));
}

function localRomDevices() {
  const devices = Array.isArray(state.catalog?.devices) ? state.catalog.devices : [];
  return devices.map((item) => {
    const product = String(item?.product ?? "").trim();
    const name = String(item?.name ?? "").trim();
    if (!product || !name) return null;
    const brand = /^OPPO\b/i.test(name) ? "OPPO" : /^Realme\b/i.test(name) ? "Realme" : "OnePlus";
    return normalizeRomDevice({ id: product, label: `${name} · ${product}`, brand }, "model");
  }).filter(Boolean);
}

async function fetchPublicRomCatalog(params) {
  const publicParams = new URLSearchParams(params);
  if (publicParams.get("latest") === "0") publicParams.delete("latest");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch(`${publicRomCatalogEndpoint}?${publicParams}`, {
      headers: { Accept: "application/json" }, cache: "no-store", signal: controller.signal
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    return {
      releases: romReleaseRows(payload).map((release) => ({
        id: String(release?.id ?? "").trim(), device: String(release?.device ?? "").trim(),
        region: String(release?.region ?? "").trim().toUpperCase(), model: String(release?.model ?? "").trim(),
        version: String(release?.version ?? "").trim(), otaVersion: String(release?.ota_version ?? "").trim(),
        buildTimestamp: String(release?.build_timestamp ?? "").trim(), securityPatch: String(release?.security_patch ?? "").trim(),
        md5: String(release?.md5 ?? "").trim(), sizeBytes: Number.isFinite(Number(release?.size)) ? Number(release.size) : null,
        publishedAt: String(release?.published ?? "").trim(), versionCode: String(release?.version_code ?? "").trim(),
        sourceUrl: String(release?.source_url ?? "").trim(), changelogUrl: String(release?.changelog_url ?? "").trim(),
        latest: release?.is_latest === true || release?.is_latest === 1 || release?.is_latest === "1"
      })).filter((release) => release.id && release.sourceUrl),
      truncated: false
    };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchPublicRomDevices() {
  const params = new URLSearchParams({ latest: "1" });
  const response = await fetchPublicRomCatalog(params);
  const devices = romDevicesFromReleases(response.releases);
  if (!devices.length) throw new Error("Public device catalog is empty");
  return devices;
}

function renderRomDevices() {
  const selected = state.romDevices.find((device) => device.id === $("#rom-device-filter").value);
  $("#rom-device-label").textContent = selected?.label || t("romDeviceChoose");
  const status = state.romDevicesStatus;
  $("#rom-devices-retry").hidden = status !== "error";
  const target = $("#rom-device-options");
  target.setAttribute("aria-busy", String(status === "loading"));
  target.replaceChildren();
  if (status !== "ready") {
    $("#rom-device-status").textContent = t(status === "error" ? "romDevicesError" : "romDevicesLoading");
    return;
  }
  const searchKey = (value) => String(value).toLocaleLowerCase().replace(/[\s_-]+/g, "");
  const query = searchKey($("#rom-device-search").value);
  const devices = state.romDevices.filter((device) => [device.id, device.label,
    ...(Array.isArray(device.regions) ? device.regions : []).flatMap((region) => region.models || [])]
    .some((value) => searchKey(value).includes(query)));
  const statusKey = state.romDevicesSource === "public" ? "romDevicesPublic"
    : state.romDevicesSource === "local" ? "romDevicesLocal" : "romDevicesCount";
  $("#rom-device-status").textContent = devices.length
    ? t(statusKey, { count: query ? devices.length : state.romDevices.length })
    : t("romDevicesEmpty");
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "rom-device-clear";
  clear.textContent = t("romDeviceClear");
  clear.addEventListener("click", () => chooseRomDevice(null));
  target.append(clear);
  const groups = new Map();
  devices.forEach((device) => {
    if (!groups.has(device.brand)) groups.set(device.brand, []);
    groups.get(device.brand).push(device);
  });
  groups.forEach((items, brand) => {
    const heading = document.createElement("h3");
    heading.textContent = `${brand} · ${items.length}`;
    target.append(heading);
    items.forEach((device) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.romDevice = device.id;
      button.setAttribute("aria-pressed", String(selected?.id === device.id));
      const label = document.createElement("span");
      label.textContent = device.label;
      const regions = document.createElement("small");
      regions.textContent = (Array.isArray(device.regions) ? device.regions : []).map((region) => region.code).join(" · ");
      button.append(label, regions);
      button.addEventListener("click", () => chooseRomDevice(device));
      target.append(button);
    });
  });
}

async function loadRomDevices() {
  if (["loading", "ready"].includes(state.romDevicesStatus)) return;
  state.romDevicesStatus = "loading";
  state.romDevicesError = "";
  renderRomDevices();
  try {
    // The Worker remains the preferred source because it records the search
    // activity and applies the same normalization as the rest of the API.
    // A catalog read is also safe to recover from the public, read-only OTA
    // endpoint when the private edge route is temporarily unavailable.
    if (!privateApiAvailable()) throw new Error(t("telegramOnly"));
    const payload = await apiRequest("/v1/rom-catalog/devices");
    if (!Array.isArray(payload.devices)) throw new Error("Invalid device catalog");
    const devices = payload.devices.map((device) => normalizeRomDevice(device)).filter(Boolean);
    if (!devices.length) throw new Error("Empty device catalog");
    state.romDevices = devices;
    state.romDevicesSource = "remote";
    state.romDevicesStatus = "ready";
  } catch (apiError) {
    state.romDevicesError = apiError?.message || t("romDevicesError");
    try {
      state.romDevices = await fetchPublicRomDevices();
      state.romDevicesSource = "public";
      state.romDevicesStatus = "ready";
    } catch (publicError) {
      const local = localRomDevices();
      if (local.length) {
        state.romDevices = local;
        state.romDevicesSource = "local";
        state.romDevicesStatus = "ready";
      } else {
        state.romDevicesStatus = "error";
      }
      state.romDevicesError = publicError?.message || state.romDevicesError;
    }
  }
  renderRomDevices();
}

function chooseRomDevice(device) {
  $("#rom-device-filter").value = device?.id || "";
  const region = $("#rom-region-filter");
  const codes = device && Array.isArray(device.regions) && device.regions.length
    ? device.regions.map((entry) => entry.code) : ["CN", "EU", "GLO", "IN", "NA"];
  region.replaceChildren(new Option(t("romAllRegions"), ""), ...codes.map((code) => new Option(code, code)));
  region.options[0].dataset.i18n = "romAllRegions";
  $("#rom-device-picker").open = false;
  $("#rom-device-picker summary").focus();
  $("#rom-device-search").value = "";
  state.romCatalogRequestId += 1;
  state.romCatalogStatus = "idle";
  state.romCatalogReleases = [];
  resetRomResolved();
  renderRomVersions(false);
  $("#search-rom-catalog").disabled = false;
  renderRomDevices();
  renderRomCatalogResults();
  if (device) searchRomCatalog();
}

function resetRomResolved() {
  state.romResolveController?.abort();
  state.romResolveController = null;
  state.romResolved = null;
}

function filteredRomReleases() {
  const region = $("#rom-region-filter").value;
  return state.romCatalogReleases.filter((release) => !region || release.region === region);
}

function renderRomVersions(preserve = true) {
  const select = $("#rom-version-filter");
  const previous = preserve ? select.value : "";
  const releases = state.romCatalogStatus === "ready" ? filteredRomReleases() : [];
  select.replaceChildren(...releases.map((release) => new Option(`${release.version || release.otaVersion} · ${release.region}`, release.id)));
  select.disabled = !releases.length;
  if (!releases.length) select.add(new Option(t(state.romCatalogStatus === "loading" ? "romCatalogLoading" : state.romCatalogStatus === "ready" ? "romCatalogEmpty" : "romChooseDeviceFirst"), ""));
  else if (releases.some((release) => release.id === previous)) select.value = previous;
}

async function resolveRomRelease(release) {
  if (state.romResolved?.status === "loading") return;
  const controller = new AbortController();
  state.romResolveController = controller;
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 70_000);
  state.romResolved = { id: release.id, status: "loading" };
  renderRomCatalogResults();
  try {
    const payload = await apiRequest("/v1/sources/resolve", {
      method: "POST", body: JSON.stringify({ uri: release.sourceUrl }), signal: controller.signal, timeoutMs: 70000
    });
    if (controller.signal.aborted || $("#rom-version-filter").value !== release.id) return;
    const url = new URL(payload.resolvedUrl);
    if (!["https:", "http:"].includes(url.protocol)) throw new Error("Invalid resolved link");
    state.romResolved = { id: release.id, status: "ready", url: url.toString(), expiresAt: payload.signedUrlExpiresAt };
  } catch (error) {
    if ((controller.signal.aborted && !timedOut) || $("#rom-version-filter").value !== release.id) return;
    state.romResolved = { id: release.id, status: "error" };
  } finally {
    clearTimeout(timeout);
    if (state.romResolveController === controller) {
      state.romResolveController = null;
      renderRomCatalogResults();
    }
  }
}

function renderRomCatalogResults() {
  const target = $("#rom-catalog-results");
  if (!target) return;
  const status = state.romCatalogStatus;
  target.setAttribute("aria-busy", String(status === "loading"));
  $("#rom-catalog-status").textContent = status === "ready"
    ? t("romCatalogCount", { count: filteredRomReleases().length })
    : status === "loading" ? t("romCatalogLoading") : "";
  if (status !== "ready") {
    const empty = document.createElement("div");
    empty.className = "rom-catalog-empty";
    const title = document.createElement("strong");
    title.textContent = t(status === "loading" ? "romCatalogLoading" : status === "error" ? "romCatalogRetry" : "romCatalogIdle");
    empty.append(title);
    if (status === "idle") {
      const hint = document.createElement("p");
      hint.textContent = t("romCatalogIdleHint");
      empty.append(hint);
    }
    target.replaceChildren(empty);
    return;
  }
  if (!filteredRomReleases().length) {
    const empty = document.createElement("p");
    empty.className = "rom-catalog-empty";
    empty.textContent = t("romCatalogEmpty");
    target.replaceChildren(empty);
    return;
  }
  target.replaceChildren(...filteredRomReleases().filter((release) => release.id === $("#rom-version-filter").value).map((release) => {
    const row = document.createElement("article");
    row.className = "rom-release";
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = [release.device || release.model || "ROM", release.region].filter(Boolean).join(" · ");
    const version = document.createElement("p");
    version.className = "rom-release-version";
    version.textContent = release.version || release.otaVersion || "—";
    const meta = document.createElement("small");
    meta.textContent = [
      release.model,
      release.securityPatch ? `${t("securityPatch")}: ${release.securityPatch}` : "",
      Number(release.sizeBytes) > 0 ? formatBytes(release.sizeBytes) : ""
    ].filter(Boolean).join(" · ");
    copy.append(title, version, meta);
    const use = document.createElement("button");
    use.type = "button";
    use.dataset.romAction = "analyze";
    use.textContent = t("useRom");
    use.addEventListener("click", () => {
      const source = $("#source-uri");
      source.value = release.sourceUrl;
      source.dispatchEvent(new Event("input", { bubbles: true }));
      navigate("build");
      source.focus({ preventScroll: true });
      toast(t("romSelected"));
    });
    const actions = document.createElement("div");
    actions.className = "rom-release-actions";
    const copyLink = document.createElement("button");
    copyLink.type = "button";
    copyLink.dataset.romAction = "copy";
    copyLink.textContent = t("romCopyLink");
    copyLink.addEventListener("click", () => copyText(release.sourceUrl).then(() => toast(t("romLinkCopied"))).catch(() => toast(t("clipboardDenied"), true)));
    const resolve = document.createElement("button");
    resolve.type = "button";
    resolve.dataset.romAction = "resolve";
    const resolved = state.romResolved?.id === release.id ? state.romResolved : null;
    resolve.disabled = resolved?.status === "loading";
    resolve.textContent = t(resolve.disabled ? "romResolving" : "romResolve");
    resolve.addEventListener("click", () => resolveRomRelease(release));
    actions.append(copyLink, resolve, use);
    row.append(copy, actions);
    if (resolved?.status === "error") {
      const error = document.createElement("p");
      error.className = "rom-resolve-error";
      error.setAttribute("role", "alert");
      error.textContent = t("romResolveFailed");
      row.append(error);
    }
    if (resolved?.status === "ready") {
      const result = document.createElement("div");
      result.className = "rom-resolved-result";
      const label = document.createElement("label");
      label.textContent = t("romResolvedLabel");
      const link = document.createElement("textarea");
      link.className = "rom-resolved-url";
      link.readOnly = true;
      link.rows = 2;
      link.value = resolved.url;
      label.append(link);
      const hint = document.createElement("p");
      hint.textContent = t("romResolvedHint");
      const resolvedCopy = document.createElement("button");
      resolvedCopy.type = "button";
      resolvedCopy.dataset.romAction = "copy-resolved";
      resolvedCopy.textContent = t("romResolvedCopy");
      resolvedCopy.addEventListener("click", () => copyText(resolved.url).then(() => toast(t("romResolvedCopied"))).catch(() => { link.focus(); link.select(); toast(t("clipboardDenied"), true); }));
      result.append(label, hint, resolvedCopy);
      row.append(result);
    }
    return row;
  }));
  if (state.romCatalogTruncated) {
    const note = document.createElement("p");
    note.textContent = t("romVersionsTruncated");
    target.append(note);
  }
}

async function searchRomCatalog() {
  if (state.romCatalogStatus === "loading") return;
  const button = $("#search-rom-catalog");
  const params = new URLSearchParams({ latest: "0" });
  const filters = {
    device: $("#rom-device-filter").value.trim(),
    region: $("#rom-region-filter").value.trim()
  };
  if (!filters.device) {
    toast(t("romFilterRequired"), true);
    $("#rom-device-picker").open = true;
    $("#rom-device-search").focus();
    return;
  }
  const selectedDevice = state.romDevices.find((device) => device.id === filters.device);
  Object.entries(filters).forEach(([key, value]) => {
    if (!value) return;
    params.set(key === "device" && selectedDevice?.queryKey === "model" ? "model" : key, value);
  });
  button.disabled = true;
  const requestId = ++state.romCatalogRequestId;
  resetRomResolved();
  state.romCatalogStatus = "loading";
  renderRomVersions(false);
  renderRomCatalogResults();
  try {
    let payload;
    try {
      payload = await apiRequest(`/v1/rom-catalog?${params.toString()}`);
    } catch (apiError) {
      try {
        payload = await fetchPublicRomCatalog(params);
      } catch (_) {
        throw apiError;
      }
    }
    if (requestId !== state.romCatalogRequestId) return;
    state.romCatalogReleases = Array.isArray(payload.releases) ? payload.releases : [];
    state.romCatalogStatus = "ready";
    state.romCatalogTruncated = payload.truncated === true;
    renderRomVersions(false);
    renderRomCatalogResults();
  } catch (error) {
    if (requestId !== state.romCatalogRequestId) return;
    state.romCatalogReleases = [];
    state.romCatalogStatus = "error";
    renderRomVersions(false);
    renderRomCatalogResults();
  } finally {
    if (requestId === state.romCatalogRequestId) button.disabled = false;
  }
}

function selectLibraryTab(name, focus = false) {
  const rom = name === "rom";
  $("#rom-catalog-panel").hidden = !rom;
  $("#library-technical").hidden = rom;
  $$('[data-library-tab]').forEach((button) => {
    const selected = button.dataset.libraryTab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    if (selected && focus) button.focus();
  });
}

export { normalizeRomDevice, romReleaseRows, romDevicesFromReleases, localRomDevices, fetchPublicRomCatalog, fetchPublicRomDevices, renderRomDevices, loadRomDevices, chooseRomDevice, resetRomResolved, filteredRomReleases, renderRomVersions, resolveRomRelease, renderRomCatalogResults, searchRomCatalog, selectLibraryTab };

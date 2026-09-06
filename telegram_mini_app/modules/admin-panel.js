import { $, $$, requestScopes, runtime, state, t, workspacePollingAllowed } from "./state.js";
import { options, toast } from "./shell.js";
import { isSafePresetLabel, presetLabel, renderPresetLabels } from "./build.js";
import { apiRequest } from "./session.js";
import { refreshLiveReleaseVersions } from "./catalog.js";
import { appendJobHistoryFilters, formatDate, jobDeviceLabel, jobEditionBadge, jobMetadata, jobModBadge, jobProgress, legacyJobHistoryPage, openAdminJobPage, readableEventStage, readableEventType, renderPageButtons, statusLabel } from "./jobs.js";
import { accessLabel, detailFact, profileAvatar, renderCurrentActivitySummary } from "./profile.js";
import { prefersReducedMotion } from "./dock.js";
import { formatBytes } from "./source-rom.js";

function renderAdminReleaseEditor() {
  const root = $("#catalog-release-admin");
  if (!root || !state.catalog) return;
  const admin = state.me?.role === "admin";
  root.hidden = !admin;
  if (!admin) return;
  const pack = $("#admin-release-pack");
  const selected = pack.value || $("#catalog-version").value || state.catalog.modVersions[0];
  options(pack, state.catalog.modVersions.map(value => ({ value, label: `${value} · ${state.catalog.modReleaseVersions[value] || value}` })), selected);
  $("#admin-release-label").value = state.catalog.modReleaseVersions[pack.value] || pack.value;
}

async function savePermanentReleaseVersion() {
  if (state.me?.role !== "admin") return;
  const pack = $("#admin-release-pack").value;
  const label = $("#admin-release-label").value.trim();
  if (!isSafePresetLabel(label)) throw new Error(t("invalidReleaseVersion"));
  const payload = await apiRequest("/v1/mod-release-versions", {
    method: "PUT", body: JSON.stringify({ modReleaseVersions: { [pack]: label } })
  });
  state.catalog.modReleaseVersions = { ...state.catalog.modReleaseVersions, ...(payload.modReleaseVersions || {}) };
  await refreshLiveReleaseVersions();
  renderAdminReleaseEditor();
  toast(`Đã lưu ${pack} thành ${label} cho mọi job sau.`);
}

function batchSelections(selector) { return $$(`${selector} input:checked`).map(input => input.value); }

function setBatchSelections(selector, checked) {
  $$(`${selector} input[type="checkbox"]`).forEach(input => { input.checked = checked; });
  updateBatchSummary();
}

function updateBatchSummary() {
  const modVersions = batchSelections("#batch-mod-versions");
  const count = batchSelections("#batch-devices").length * modVersions.length;
  const editions = [$("#batch-lite").checked ? presetLabel("lite") : "", $("#batch-plus").checked ? presetLabel("plus") : ""].filter(Boolean).join(" + ");
  const releases = [...new Set(modVersions.map(value => state.catalog?.modReleaseVersions?.[value]).filter(Boolean))].join(" + ");
  $("#batch-summary").textContent = `${count} cấu hình${editions ? ` · ${editions}` : ""}${releases ? ` · ${releases}` : ""}`;
}

function renderBatchChoices() {
  if (!state.catalog) return;
  $("#batch-devices").replaceChildren(...state.catalog.devices.map(item => {
    const label = document.createElement("label"); const input = document.createElement("input"); input.type = "checkbox"; input.value = item.product;
    const copy = document.createElement("span"); const name = document.createElement("b"); name.textContent = item.name; const code = document.createElement("small"); code.textContent = item.product;
    copy.append(name, code); label.append(input, copy); return label;
  }));
  $("#batch-mod-versions").replaceChildren(...state.catalog.modVersions.map(value => {
    const label = document.createElement("label"); const input = document.createElement("input"); input.type = "checkbox"; input.value = value;
    const copy = document.createElement("span"); const name = document.createElement("b"); name.textContent = value; const release = document.createElement("small"); release.textContent = state.catalog.modReleaseVersions[value] || value;
    copy.append(name, release); label.append(input, copy); return label;
  }));
  const liteLabel = $("#batch-lite")?.closest("label")?.querySelector("span");
  const plusLabel = $("#batch-plus")?.closest("label")?.querySelector("span");
  if (liteLabel) liteLabel.textContent = presetLabel("lite");
  if (plusLabel) plusLabel.textContent = presetLabel("plus");
  updateBatchSummary();
}

function openBatchBuildPage() {
  if (state.me?.role !== "admin") return;
  renderBatchChoices();
  $("#system").classList.add("admin-batch-open"); $("#admin-batch-page").hidden = false;
  window.scrollTo({ top: 0, behavior: "instant" }); $("#admin-batch-back").focus({ preventScroll: true });
  loadLatestBatch().catch(() => {});
}

function closeBatchBuildPage() {
  clearTimeout(state.batchPollTimer); state.batchPollTimer = null;
  requestScopes.cancel("batch");
  $("#system").classList.remove("admin-batch-open"); $("#admin-batch-page").hidden = true;
}

function batchReleaseSummary(payload) {
  return payload.releaseVersion
    || [...new Set(Object.values(payload.releaseVersions || {}).filter(Boolean))].join(" + ")
    || "Theo nền MOD";
}

function renderBatch(payload) {
  $("#batch-status").textContent = `${batchReleaseSummary(payload)} · ${payload.status} · ${(payload.items || []).length} cấu hình`;
  $("#batch-items").replaceChildren(...(payload.items || []).map(item => {
    const row = document.createElement("article"); const head = document.createElement("div"); const title = document.createElement("strong"); title.textContent = `${item.device} · ${item.modVersion}${item.releaseVersion ? ` · ${item.releaseVersion}` : ""}`;
    const status = document.createElement("span"); status.textContent = `${item.status}${item.stage ? ` · ${item.stage}` : ""} · ${Math.round(Number(item.progress || 0) * 100)}%`; head.append(title, status);
    const detail = document.createElement("small"); detail.textContent = item.error || item.sourceVersion || "Đang chờ tìm ROM nguồn"; row.append(head, detail);
    if (Array.isArray(item.jobEvents) && item.jobEvents.length) {
      const log = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = `Log job · ${item.jobEvents.length} sự kiện`;
      const lines = document.createElement("div"); lines.className = "batch-job-log";
      lines.append(...item.jobEvents.slice().reverse().map(event => {
        const line = document.createElement("p"); const time = document.createElement("time"); time.textContent = formatDate(event.timestamp);
        const copy = document.createElement("span"); copy.textContent = event.message || event.error || event.warning || `${readableEventType(event.type)}${event.stage ? ` · ${readableEventStage(event.stage)}` : ""}`;
        line.append(time, copy); return line;
      }));
      log.append(summary, lines); row.append(log);
    }
    return row;
  }));
  $("#batch-events").replaceChildren(...(payload.events || []).slice().reverse().map(item => {
    const row = document.createElement("article"); const time = document.createElement("time"); time.textContent = formatDate(item.createdAt); const message = document.createElement("span"); message.textContent = item.message || item.eventType; row.append(time, message); return row;
  }));
  if (["succeeded", "partial", "failed", "cancelled"].includes(payload.status)) {
    localStorage.removeItem("wukong-batch-request");
    localStorage.removeItem("wukong-active-batch");
    state.activeBatchId = "";
  }
}

async function loadBatch() {
  if (!workspacePollingAllowed() || !state.activeBatchId || state.me?.role !== "admin" || $("#admin-batch-page").hidden) return;
  clearTimeout(state.batchPollTimer);
  const signal = requestScopes.start("batch");
  let finished = false;
  try {
    const payload = await apiRequest(`/v1/admin/batch-builds/${encodeURIComponent(state.activeBatchId)}`, { signal });
    if (signal.aborted) return;
    renderBatch(payload);
    finished = ["succeeded", "partial", "failed", "cancelled"].includes(payload.status);
  } finally {
    if (!signal.aborted && workspacePollingAllowed() && !finished) {
      state.batchPollTimer = setTimeout(() => loadBatch().catch(() => {}), 10000);
    }
  }
}

async function loadLatestBatch() {
  if (!workspacePollingAllowed()) return;
  if (state.activeBatchId) return loadBatch();
  const payload = await apiRequest("/v1/admin/batch-builds");
  const latest = Array.isArray(payload.batches) ? payload.batches[0] : null;
  if (!latest?.batchId) return;
  state.activeBatchId = latest.batchId;
  return loadBatch();
}

async function startBatchBuild() {
  const devices = batchSelections("#batch-devices"), modVersions = batchSelections("#batch-mod-versions");
  const editions = [$("#batch-lite").checked ? "lite" : "", $("#batch-plus").checked ? "plus" : ""].filter(Boolean);
  if (!devices.length || !modVersions.length || !editions.length) throw new Error(`Hãy chọn ít nhất một thiết bị, một nền MOD và một bản ${presetLabel("lite")}/${presetLabel("plus")}.`);
  const button = $("#start-batch-build"); button.disabled = true;
  try {
    const body = JSON.stringify({ devices, modVersions, editions });
    let pending = null;
    try { pending = JSON.parse(localStorage.getItem("wukong-batch-request") || "null"); } catch (_) {}
    if (!pending || pending.subject !== String(state.me?.telegramId || "") || pending.body !== body || !pending.key) {
      pending = { subject: String(state.me?.telegramId || ""), body, key: crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` };
      localStorage.setItem("wukong-batch-request", JSON.stringify(pending));
    }
    const payload = await apiRequest("/v1/admin/batch-builds", { method: "POST", headers: { "Idempotency-Key": pending.key }, body });
    state.activeBatchId = payload.batchId;
    localStorage.setItem("wukong-active-batch", state.activeBatchId);
    pending.batchId = payload.batchId;
    localStorage.setItem("wukong-batch-request", JSON.stringify(pending));
    $("#batch-status").textContent = `${batchReleaseSummary(payload)} · ${payload.status} · ${payload.itemCount} cấu hình`;
    toast(`Đã tạo ${payload.itemCount} cấu hình batch build.`);
    loadBatch().catch(error => toast(`Batch đã được tạo; chưa tải được tiến độ: ${error.message}`, true));
  } finally { button.disabled = false; }
}

function renderMaintenanceAdmin() {
  const maintenance = state.maintenance || { enabled: false, message: "" };
  const enabled = Boolean(maintenance.enabled);
  const input = $("#maintenance-message-input");
  const toggle = $("#maintenance-toggle");
  const badge = $("#maintenance-state-badge");
  if (input && !state.maintenanceMessageDirty) {
    input.value = maintenance.message || "Hệ thống đang được bảo trì. Vui lòng quay lại sau.";
  }
  if (toggle) {
    toggle.classList.toggle("enabled", enabled);
    toggle.querySelector("span").textContent = t(enabled ? "disableMaintenance" : "enableMaintenance");
  }
  if (badge) {
    badge.classList.toggle("enabled", enabled);
    badge.textContent = enabled ? "BẢO TRÌ" : "ĐANG MỞ";
  }
  const status = $("#maintenance-admin-status");
  if (status) status.textContent = t(enabled ? "maintenanceClosedStatus" : "maintenanceOpenStatus");
}

async function updateMaintenance() {
  if (state.me?.role !== "admin") return;
  const button = $("#maintenance-toggle");
  const enabled = !Boolean(state.maintenance?.enabled);
  const message = $("#maintenance-message-input").value.trim();
  if (!message) {
    toast(t("maintenanceMessage"), true);
    return;
  }
  button.disabled = true;
  try {
    const payload = await apiRequest("/v1/system/maintenance", {
      method: "PUT",
      body: JSON.stringify({ enabled, message })
    });
    state.maintenance = payload.maintenance;
    state.maintenanceMessageDirty = false;
    renderMaintenanceAdmin();
    toast(t(enabled ? "maintenanceEnabledToast" : "maintenanceDisabledToast"));
  } finally {
    button.disabled = false;
  }
}

function renderAdminUsers() {
  const body = $("#user-table-body");
  if (!body) return;
  if (!state.adminUsers.length) {
    const empty = document.createElement("p"); empty.className = "user-empty"; empty.textContent = t("noUsers");
    body.replaceChildren(empty);
  } else body.replaceChildren(...state.adminUsers.map((user) => {
    const row = document.createElement("div"); row.className = "user-row"; row.setAttribute("role", "row");
    const identity = document.createElement("span"); identity.className = "user-identity";
    identity.append(profileAvatar(user, "profile-avatar-small"));
    const identityCopy = document.createElement("span");
    const name = document.createElement("strong"); name.textContent = user.displayName || (user.username ? `@${user.username}` : user.telegramId);
    const id = document.createElement("small"); id.textContent = `${user.telegramId}${user.username ? ` · @${user.username}` : ""}`;
    identityCopy.append(name, id); identity.append(identityCopy);
    const activity = renderCurrentActivitySummary(user, true);
    const quota = document.createElement("span"); quota.className = "user-quota";
    quota.textContent = user.unlimited ? t("unlimited") : `${user.buildCredits || 0} · ${t("jobsCount", { count: user.jobCount || 0 })}`;
    const status = document.createElement("span"); status.className = `access-badge ${user.accessStatus}`; status.textContent = accessLabel(user.accessStatus);
    const open = document.createElement("button"); open.type = "button"; open.className = "user-open"; open.dataset.userId = String(user.telegramId); open.textContent = "›"; open.setAttribute("aria-label", `${t("displayName")}: ${name.textContent}`);
    open.addEventListener("click", () => openAdminUser(user.telegramId).catch((error) => toast(error.message, true)));
    row.append(identity, activity, quota, status, open);
    return row;
  }));
  const start = state.adminUsersTotal ? state.adminUsersOffset + 1 : 0;
  const end = Math.min(state.adminUsersOffset + state.adminUsers.length, state.adminUsersTotal);
  $("#user-page-summary").textContent = `${start}–${end} / ${state.adminUsersTotal}`;
  const counts = state.adminUserStatusCounts;
  $("#user-total-count").textContent = String(counts.approved + counts.pending + counts.revoked);
  $("#user-approved-count").textContent = String(counts.approved);
  $("#user-pending-count").textContent = String(counts.pending);
  $("#user-revoked-count").textContent = String(counts.revoked);
  $("#user-prev").disabled = state.adminUsersOffset <= 0;
  $("#user-next").disabled = end >= state.adminUsersTotal;
}

async function loadAdminUsers({ reset = false } = {}) {
  if (state.me?.role !== "admin" || !workspacePollingAllowed() || document.body.dataset.view !== "system") return;
  const signal = requestScopes.start("adminUsers");
  clearTimeout(state.adminUsersPollTimer);
  if (reset) state.adminUsersOffset = 0;
  state.adminUsersLoading = true;
  try {
    const query = encodeURIComponent($("#user-search")?.value?.trim() || "");
    const status = encodeURIComponent($("#user-status")?.value || "");
    const quota = encodeURIComponent($("#user-quota-filter")?.value || "");
    const activity = encodeURIComponent($("#user-activity-filter")?.value || "");
    const sort = encodeURIComponent($("#user-sort")?.value || "lastSeenAt");
    const payload = await apiRequest(`/v1/admin/users?query=${query}&status=${status}&quota=${quota}&activity=${activity}&sort=${sort}&offset=${state.adminUsersOffset}&limit=25`, { signal });
    if (signal.aborted) return;
    state.adminUsers = Array.isArray(payload.users) ? payload.users : [];
    state.adminUsersTotal = Number(payload.total || 0);
    const statusCounts = payload.statusCounts || {};
    state.adminUserStatusCounts = {
      approved: Number(statusCounts.approved || 0),
      pending: Number(statusCounts.pending || 0),
      revoked: Number(statusCounts.revoked || 0)
    };
    renderAdminUsers();
  } finally {
    if (!requestScopes.isCurrent("adminUsers", signal)) return;
    state.adminUsersLoading = false;
    clearTimeout(state.adminUsersPollTimer);
    if (workspacePollingAllowed() && state.me?.role === "admin" && document.body.dataset.view === "system") {
      state.adminUsersPollTimer = setTimeout(() => loadAdminUsers().catch(() => {}), 10000);
    }
  }
}

function adminAuditArticle(event) {
  const article = document.createElement("article");
  article.dataset.adminEventId = String(event.eventId || `${event.type || "event"}:${event.createdAt || ""}`);
  const name = document.createElement("strong"); name.textContent = event.type;
  const detail = document.createElement("small");
  detail.textContent = `${formatDate(event.createdAt)}${event.actorTelegramId ? ` · ${event.actorTelegramId}` : ""}${event.reason ? ` · ${event.reason}` : ""}`;
  article.append(name, detail);
  if (String(event.type || "").startsWith("rom_search_")) {
    article.classList.add("rom-search-audit");
    const details = event.details || {};
    name.textContent = t(event.type === "rom_search_started"
      ? "romSearchStartedLog"
      : event.type === "rom_search_completed"
        ? "romSearchCompletedLog"
        : "romSearchFailedLog");
    const filters = document.createElement("p");
    filters.textContent = `${t("romSearchFilters")}: ${[details.device || details.model, details.region, details.latest ? t("romLatestOnly") : t("romAllVersions")].filter(Boolean).join(" · ")}`;
    article.append(filters);
    if (Number.isFinite(Number(details.durationMs))) {
      const duration = document.createElement("small");
      duration.textContent = `${t("romSearchDuration")}: ${(Number(details.durationMs) / 1000).toFixed(2)}s`;
      article.append(duration);
    }
    const results = Array.isArray(details.results) ? details.results : [];
    if (event.type === "rom_search_completed") {
      const resultTitle = document.createElement("b");
      resultTitle.textContent = `${t("romSearchResults")}: ${Number(details.resultCount || results.length)}`;
      const list = document.createElement("ul");
      results.forEach((result) => {
        const item = document.createElement("li");
        item.textContent = [result.model, result.version, result.region].filter(Boolean).join(" · ");
        list.append(item);
      });
      article.append(resultTitle, list);
    }
    if (details.error) {
      const error = document.createElement("p"); error.className = "error"; error.textContent = String(details.error); article.append(error);
    }
  }
  return article;
}

function scheduleAdminUserActivityPoll() {
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  if (!workspacePollingAllowed() || document.body.dataset.view !== "system" || state.me?.role !== "admin" || !state.selectedAdminUserId || state.adminJobView) return;
  state.adminUserPollTimer = setTimeout(refreshAdminUserActivity, 10000);
}

async function refreshAdminUserActivity() {
  const telegramId = state.selectedAdminUserId;
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  if (!telegramId || !workspacePollingAllowed() || document.body.dataset.view !== "system" || state.adminJobView) return;
  const signal = requestScopes.start("adminActivity");
  try {
    const collected = [];
    let latestUser = null;
    let nextCursor = { ...state.adminUserEventCursor };
    for (let page = 0; page < 4; page += 1) {
      const query = new URLSearchParams({
        afterCreatedAt: nextCursor.createdAt,
        afterEventId: nextCursor.eventId
      });
      const payload = await apiRequest(`/v1/admin/users/${encodeURIComponent(telegramId)}/activity?${query}`, { signal });
      if (signal.aborted || state.selectedAdminUserId !== telegramId || state.adminJobView) return;
      latestUser = payload.user;
      const events = Array.isArray(payload.events) ? payload.events : [];
      collected.push(...events);
      const consumed = events.at(-1);
      if (consumed?.createdAt) {
        nextCursor = {
          createdAt: String(consumed.createdAt),
          eventId: String(consumed.eventId || "")
        };
      }
      if (!payload.hasMore || !consumed) break;
    }
    if (!latestUser) return;
    const activity = renderCurrentActivitySummary(latestUser);
    activity.id = "admin-user-current-activity";
    $("#admin-user-current-activity")?.replaceWith(activity);
    const audit = $("#admin-user-audit-log");
    if (audit) {
      const existing = new Set([...audit.children].map((node) => node.dataset.adminEventId));
      const incoming = [...collected].reverse()
        .filter((event) => !existing.has(String(event.eventId || `${event.type || "event"}:${event.createdAt || ""}`)))
        .map(adminAuditArticle);
      if (incoming.length) audit.prepend(...incoming);
    }
    state.adminUserEventCursor = nextCursor;
  } catch (_) {
    // Keep the current snapshot and retry without interrupting the admin.
  } finally {
    if (!signal.aborted && workspacePollingAllowed() && document.body.dataset.view === "system" && state.selectedAdminUserId === telegramId) scheduleAdminUserActivityPoll();
  }
}

function requestAdminAction(user, action) {
  if (action === "credit-add") return Promise.resolve({ reason: "admin grant" });
  const dialog = $("#admin-action-dialog");
  const form = $("#admin-action-form");
  const valueField = $("#admin-action-value-field");
  const valueInput = $("#admin-action-value");
  const reasonField = $("#admin-action-reason-field");
  const reasonInput = $("#admin-action-reason");
  const error = $("#admin-action-error");
  const confirm = $("#admin-action-confirm");
  const needsValue = ["credit-subtract", "credit-set"].includes(action);
  const needsReason = action === "revoke" || action === "credit-subtract" || (action === "unlimited" && user.unlimited);
  const allowsReason = needsReason || action === "approve" || action === "credit-set";
  $("#admin-action-title").textContent = t({
    approve: "approveUser", revoke: "revokeUser", "credit-subtract": "subtractCredit",
    "credit-set": "setCredit", unlimited: "toggleUnlimited"
  }[action]);
  $("#admin-action-message").textContent = t("adminActionMessage");
  valueField.hidden = !needsValue;
  reasonField.hidden = !allowsReason;
  valueInput.value = action === "credit-set" ? String(user.buildCredits || 0) : "1";
  reasonInput.value = action === "approve" ? "approved by admin" : "";
  error.hidden = true;
  confirm.classList.toggle("danger-confirm", action === "revoke");
  confirm.classList.toggle("primary", action !== "revoke");
  dialog.showModal();
  requestAnimationFrame(() => (needsValue ? valueInput : allowsReason ? reasonInput : confirm).focus());
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      form.onsubmit = null;
      resolve(value);
    };
    form.onsubmit = (event) => {
      event.preventDefault();
      if (event.submitter?.value === "cancel") { dialog.close("cancel"); return; }
      const rawValue = valueInput.value.trim();
      const valueValid = !needsValue || /^\d+$/.test(rawValue)
        && (action === "credit-set" || Number(rawValue) > 0);
      if (!valueValid) {
        error.textContent = t("actionValueInvalid");
        error.hidden = false;
        valueInput.focus();
        return;
      }
      const value = needsValue ? Number(rawValue) : undefined;
      const reasonRequired = needsReason || action === "credit-set" && value < Number(user.buildCredits || 0);
      const reason = reasonInput.value.trim();
      if (reasonRequired && !reason) {
        error.textContent = t("actionReasonRequired");
        error.hidden = false;
        reasonInput.focus();
        return;
      }
      dialog.close("confirm");
      finish({ value, reason });
    };
    dialog.addEventListener("close", () => finish(null), { once: true });
  });
}

async function runAdminUserAction(user, action) {
  const input = await requestAdminAction(user, action);
  if (!input) return;
  let path = action; let body = {};
  if (action === "approve" || action === "revoke") body.reason = input.reason;
  if (action === "credit-add") { path = "allowance"; body = { operation: "add", value: 1, reason: input.reason }; }
  if (action === "credit-subtract") { path = "allowance"; body = { operation: "add", value: -input.value, reason: input.reason }; }
  if (action === "credit-set") {
    path = "allowance";
    body = { operation: "set", value: input.value, reason: input.reason || "admin allocation" };
  }
  if (action === "unlimited") {
    path = "allowance";
    const next = !user.unlimited;
    body = { operation: "unlimited", unlimited: next, reason: input.reason || "admin enabled unlimited" };
  }
  await apiRequest(`/v1/admin/users/${encodeURIComponent(user.telegramId)}/${path}`, { method: "POST", body: JSON.stringify(body) });
  toast(t("userUpdated"));
  await loadAdminUsers({ reset: false });
  await openAdminUser(user.telegramId);
}

async function openAdminUser(telegramId) {
  const signal = requestScopes.start("adminUser");
  requestScopes.cancel("adminActivity");
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  if (!$("#system")?.classList.contains("admin-user-open")) state.adminUserReturnScrollY = window.scrollY;
  const payload = await apiRequest(`/v1/admin/users/${encodeURIComponent(telegramId)}`, { signal });
  if (signal.aborted) return;
  const user = payload.user; const events = Array.isArray(payload.events) ? payload.events : [];
  const initialJobsPage = await apiRequest("/v1/admin/users/" + encodeURIComponent(telegramId) + "/jobs?page=1", { signal });
  if (signal.aborted) return;
  state.selectedAdminUserId = user.telegramId;
  state.adminUserEventCursor = events[0]?.createdAt
    ? { createdAt: String(events[0].createdAt), eventId: String(events[0].eventId || "") }
    : { createdAt: "1970-01-01T00:00:00.000Z", eventId: "" };
  const root = $("#user-detail-content");
  const header = document.createElement("header");
  header.className = "admin-user-hero";
  const titleBox = document.createElement("div"); titleBox.className = "user-detail-title"; titleBox.append(profileAvatar(user));
  const titleCopy = document.createElement("span"); const kicker = document.createElement("small"); kicker.textContent = `TELEGRAM ${user.telegramId}`; const title = document.createElement("h1"); title.id = "admin-user-page-title"; title.textContent = user.displayName || (user.username ? `@${user.username}` : user.telegramId); titleCopy.append(kicker, title); titleBox.append(titleCopy);
  const status = document.createElement("span"); status.className = `access-badge ${user.accessStatus}`; status.textContent = accessLabel(user.accessStatus); header.append(titleBox, status);
  const activityTitle = document.createElement("h3"); activityTitle.textContent = t("currentUserActivity");
  const currentActivity = renderCurrentActivitySummary(user);
  currentActivity.id = "admin-user-current-activity";
  const grid = document.createElement("div"); grid.className = "user-detail-grid";
  grid.append(
    detailFact(t("accessStatus"), accessLabel(user.accessStatus)), detailFact(t("allowance"), user.unlimited ? t("unlimited") : String(user.buildCredits || 0)),
    detailFact(t("firstAccess"), formatDate(user.firstSeenAt)), detailFact(t("lastAccess"), formatDate(user.lastSeenAt)),
    detailFact(t("activity"), `${t("openCount", { count: user.miniAppOpenCount || 0 })} · ${t("jobsCount", { count: user.jobCount || 0 })}`), detailFact(t("lastJob"), `${user.lastJobId || "—"} · ${user.lastJobStatus || "—"}`),
    detailFact("Username", user.username ? `@${user.username}` : "—"), detailFact(t("role"), user.role || "user"),
    detailFact(t("lifetime"), t("lifetimeSummary", { granted: user.lifetimeGranted || 0, used: user.lifetimeUsed || 0 })), detailFact(t("client"), [user.language, user.platform, user.appVersion].filter(Boolean).join(" · ")),
    detailFact(t("approvedAt"), formatDate(user.approvedAt)), detailFact(t("revokedAt"), formatDate(user.revokedAt)),
    detailFact(t("accessActor"), user.accessActor || "—"), detailFact(t("accessReason"), user.accessReason || "—")
  );
  const actions = document.createElement("div"); actions.className = "user-detail-actions";
  const definitions = user.accessStatus === "approved"
    ? [["credit-add", t("addCredit")], ["credit-subtract", t("subtractCredit")], ["credit-set", t("setCredit")], ["unlimited", t("toggleUnlimited")], ["revoke", t("revokeUser"), "danger"]]
    : [["approve", t("approveUser")]];
  definitions.forEach(([action, label, className]) => { const button = document.createElement("button"); button.type = "button"; button.textContent = label; if (className) button.className = className; button.disabled = Boolean(user.configuredAdmin); button.addEventListener("click", () => runAdminUserAction(user, action).catch((error) => toast(error.message, true))); actions.append(button); });
  const auditTitle = document.createElement("h3"); auditTitle.textContent = t("auditTitle");
  const audit = document.createElement("div"); audit.id = "admin-user-audit-log"; audit.className = "user-audit";
  audit.replaceChildren(...events.map(adminAuditArticle));
  let auditCursor = String(payload.eventsNextCursor || "");
  const loadMoreAudit = document.createElement("button");
  loadMoreAudit.type = "button";
  loadMoreAudit.className = "secondary";
  loadMoreAudit.textContent = t("loadMoreAudit");
  loadMoreAudit.hidden = !payload.eventsHasMore;
  loadMoreAudit.addEventListener("click", async () => {
    loadMoreAudit.disabled = true;
    try {
      const page = await apiRequest(`/v1/admin/users/${encodeURIComponent(user.telegramId)}/events?cursor=${encodeURIComponent(auditCursor)}&limit=100`);
      const nextEvents = Array.isArray(page.events) ? page.events : [];
      audit.append(...nextEvents.map(adminAuditArticle));
      auditCursor = String(page.nextCursor || "");
      loadMoreAudit.hidden = !page.hasMore;
    } catch (error) {
      toast(error.message, true);
    } finally {
      loadMoreAudit.disabled = false;
    }
  });
  const jobsTitle = document.createElement("h3"); jobsTitle.textContent = t("jobHistory");
  const jobTabs = document.createElement("div"); jobTabs.className = "job-history-tabs admin-job-history-tabs"; jobTabs.setAttribute("role", "tablist"); jobTabs.setAttribute("aria-label", t("jobHistory"));
  const adminJobState = {
    filter: Number(initialJobsPage?.statusCounts?.active || 0) > 0
      ? "active"
      : Number(initialJobsPage?.statusCounts?.succeeded || 0) > 0 ? "succeeded" : "failed",
    page: 1,
    pageSize: 20,
    total: 0,
    totalPages: 1,
    requestId: 0
  };
  const jobTabButtons = {};
  for (const [key, labelKey] of [["active", "jobTabActive"], ["succeeded", "jobTabSucceeded"], ["failed", "jobTabFailed"]]) {
    const button = document.createElement("button"); button.type = "button"; button.setAttribute("role", "tab");
    const label = document.createElement("span"); label.textContent = t(labelKey);
    const count = document.createElement("b"); count.textContent = "0"; button.append(label, count);
    button.addEventListener("click", () => { adminJobState.filter = key; adminJobState.page = 1; loadAdminJobs().catch((error) => toast(error.message, true)); });
    jobTabs.append(button); jobTabButtons[key] = { button, count };
  }
  const jobFilters = document.createElement("form"); jobFilters.className = "job-history-filters admin-job-history-filters";
  const adminJobSearch = document.createElement("input"); adminJobSearch.type = "search"; adminJobSearch.maxLength = 128; adminJobSearch.autocomplete = "off"; adminJobSearch.dataset.i18nPlaceholder = "jobSearchPlaceholder"; adminJobSearch.placeholder = t("jobSearchPlaceholder");
  const adminJobPreset = document.createElement("select");
  [["", "allJobs"], ["lite", "lite"], ["plus", "plus"], ["both", "both"], ["custom", "custom"]].forEach(([value, label]) => { const option = document.createElement("option"); option.value = value; option.textContent = label === "allJobs" ? t(label) : label === "both" ? "Lite + Plus" : label[0].toUpperCase() + label.slice(1); adminJobPreset.append(option); });
  const adminJobMod = document.createElement("input"); adminJobMod.type = "search"; adminJobMod.maxLength = 128; adminJobMod.dataset.i18nPlaceholder = "jobModPlaceholder"; adminJobMod.placeholder = t("jobModPlaceholder");
  const adminJobFrom = document.createElement("input"); adminJobFrom.type = "date";
  const adminJobTo = document.createElement("input"); adminJobTo.type = "date";
  const adminJobDatalist = document.createElement("datalist");
  if (state.catalog?.modVersions) adminJobDatalist.append(...state.catalog.modVersions.map((value) => { const option = document.createElement("option"); option.value = value; return option; }));
  adminJobDatalist.id = "admin-job-mod-options"; adminJobMod.setAttribute("list", adminJobDatalist.id);
  const adminJobField = (labelKey, control, wide = false) => { const label = document.createElement("label"); label.className = wide ? "field job-history-search" : "field"; const text = document.createElement("span"); text.dataset.i18n = labelKey; text.textContent = t(labelKey); label.append(text, control); return label; };
  jobFilters.append(adminJobField("jobSearch", adminJobSearch, true), adminJobField("jobPresetFilter", adminJobPreset), adminJobField("jobModFilter", adminJobMod), adminJobField("jobDateFrom", adminJobFrom), adminJobField("jobDateTo", adminJobTo));
  const clearAdminJobFilters = document.createElement("button"); clearAdminJobFilters.type = "reset"; clearAdminJobFilters.className = "secondary compact"; clearAdminJobFilters.textContent = t("clearJobFilters"); jobFilters.append(clearAdminJobFilters, adminJobDatalist);
  const jobHistory = document.createElement("div"); jobHistory.className = "user-audit";
  const jobPagination = document.createElement("div"); jobPagination.className = "job-history-pagination admin-job-history-pagination";
  const jobPageSummary = document.createElement("span"); const jobPageButtons = document.createElement("nav"); jobPageButtons.className = "job-page-buttons"; jobPageButtons.setAttribute("aria-label", t("jobHistory"));
  jobPagination.append(jobPageSummary, jobPageButtons);
  const historyEntry = (job) => {
    const article = document.createElement("article"); article.className = "user-job-entry";
    const copy = document.createElement("div");
    const deviceLabel = jobDeviceLabel(job);
    const name = document.createElement("strong"); name.textContent = jobMetadata(job).version || deviceLabel || job.recipe?.device || job.job_id || job.jobId;
    const detailParts = [deviceLabel, job.recipe?.build?.modVersion, job.recipe?.build?.modReleaseVersion].filter(Boolean);
    if (detailParts.length) {
      const deviceLine = document.createElement("small"); deviceLine.className = "user-job-device";
      deviceLine.textContent = detailParts.join(" · ");
      copy.append(deviceLine);
    }
    const detail = document.createElement("small"); detail.textContent = `${statusLabel(job.status)} · ${jobProgress(job)}% · ${job.stage || "—"}\n${formatDate(job.created_at || job.createdAt)} · ${job.job_id || job.jobId}`;
    copy.append(name, detail);
    const open = document.createElement("button"); open.type = "button"; open.className = "secondary";
    open.dataset.openUserJob = job.job_id || job.jobId; open.textContent = t("openUserJob");
    open.addEventListener("click", (event) => openAdminJobPage({
      ...job,
      createdBy: job.createdBy || user,
      __returnFocus: event.currentTarget
    }));
    const editionBadge = jobEditionBadge(job);
    const modBadge = jobModBadge(job);
    article.append(copy, ...(editionBadge ? [editionBadge] : []), ...(modBadge ? [modBadge] : []), open);
    return article;
  };
  const renderAdminJobs = (page) => {
    if (!page.page) {
      page = legacyJobHistoryPage(Array.isArray(page.jobs) ? page.jobs : [], {
        filter: adminJobState.filter,
        page: adminJobState.page,
        search: adminJobSearch,
        preset: adminJobPreset,
        mod: adminJobMod,
        from: adminJobFrom,
        to: adminJobTo
      });
    }
    adminJobState.page = Number(page.page || adminJobState.page);
    adminJobState.pageSize = Number(page.pageSize || 20);
    adminJobState.total = Number(page.total || 0);
    adminJobState.totalPages = Number(page.totalPages || 1);
    for (const key of ["active", "succeeded", "failed"]) {
      jobTabButtons[key].count.textContent = String(page.statusCounts?.[key] || 0);
      const selected = key === adminJobState.filter;
      jobTabButtons[key].button.classList.toggle("active", selected);
      jobTabButtons[key].button.setAttribute("aria-selected", String(selected));
    }
    jobHistory.replaceChildren(...(page.jobs || []).map(historyEntry));
    if (!page.jobs?.length) { const empty = document.createElement("p"); empty.className = "job-filter-empty"; empty.textContent = t("jobFilterEmpty"); jobHistory.append(empty); }
    const first = adminJobState.total ? (adminJobState.page - 1) * adminJobState.pageSize + 1 : 0;
    const last = adminJobState.total ? Math.min(adminJobState.page * adminJobState.pageSize, adminJobState.total) : 0;
    jobPageSummary.textContent = t("jobPageSummary", { from: first, to: last, total: adminJobState.total });
    jobPagination.hidden = adminJobState.total === 0;
    renderPageButtons(jobPageButtons, adminJobState.page, adminJobState.totalPages, (pageNumber) => { adminJobState.page = pageNumber; loadAdminJobs().catch((error) => toast(error.message, true)); });
  };
  const loadAdminJobs = async () => {
    const requestId = ++adminJobState.requestId;
    const params = new URLSearchParams({ page: String(adminJobState.page), status: adminJobState.filter });
    appendJobHistoryFilters(params, {
      search: adminJobSearch,
      preset: adminJobPreset,
      mod: adminJobMod,
      from: adminJobFrom,
      to: adminJobTo
    });
    jobPagination.hidden = false; jobPageSummary.textContent = t("jobHistoryLoading");
    const page = await apiRequest("/v1/admin/users/" + encodeURIComponent(user.telegramId) + "/jobs?" + params.toString());
    if (requestId !== adminJobState.requestId) return;
    renderAdminJobs(page);
  };
  let adminJobSearchTimer;
  adminJobSearch.addEventListener("input", () => { clearTimeout(adminJobSearchTimer); adminJobSearchTimer = setTimeout(() => { adminJobState.page = 1; loadAdminJobs().catch((error) => toast(error.message, true)); }, 300); });
  [adminJobPreset, adminJobMod, adminJobFrom, adminJobTo].forEach((control) => control.addEventListener("change", () => { adminJobState.page = 1; loadAdminJobs().catch((error) => toast(error.message, true)); }));
  jobFilters.addEventListener("reset", () => setTimeout(() => { adminJobState.page = 1; loadAdminJobs().catch((error) => toast(error.message, true)); }, 0));
  root.replaceChildren(header, activityTitle, currentActivity, grid, actions, jobsTitle, jobTabs, jobFilters, jobHistory, jobPagination, auditTitle, audit, loadMoreAudit);
  $("#admin-user-page").hidden = false;
  $("#system").classList.add("admin-user-open");
  window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  requestAnimationFrame(() => $("#admin-user-back").focus());
  loadAdminJobs().catch((error) => toast(error.message, true));
  scheduleAdminUserActivityPoll();
}

function renderAdminPresetLabels() {
  const root = $("#catalog-preset-admin");
  if (!root) return;
  const admin = state.me?.role === "admin";
  root.hidden = !admin;
  if (!admin) return;
  for (const key of ["lite", "plus", "custom"]) {
    const input = $(`#admin-preset-label-${key}`);
    if (input && document.activeElement !== input) input.value = state.presetLabels[key] || presetLabel(key);
  }
}

async function savePermanentPresetLabels() {
  if (state.me?.role !== "admin") return;
  const values = {};
  for (const key of ["lite", "plus", "custom"]) {
    const value = $(`#admin-preset-label-${key}`).value.trim();
    if (!isSafePresetLabel(value)) throw new Error(t("invalidPresetLabel"));
    values[key] = value;
  }
  const payload = await apiRequest("/v1/preset-labels", { method: "PUT", body: JSON.stringify({ presetLabels: values }) });
  state.presetLabels = { ...state.presetLabels, ...(payload.presetLabels || {}) };
  renderPresetLabels();
  renderBatchChoices();
  toast(t("presetLabelsSaved"));
}


function openCacheClearDialog() {
  if (state.cacheClearPending) return;
  const dialog = $("#cache-clear-dialog");
  if (dialog && !dialog.open) dialog.showModal();
  runtime.TelegramApp?.HapticFeedback?.impactOccurred?.("medium");
}

async function performCacheClear() {
  if (state.cacheClearPending) return;
  const button = $("#cache-clear-confirm");
  state.cacheClearPending = true;
  if (button) {
    button.disabled = true;
    button.textContent = t("cacheClearing");
  }
  try {
    const payload = await apiRequest("/v1/cache/clear", { method: "POST" });
    $("#cache-clear-dialog")?.close();
    toast(t("cacheCleared", { count: payload.entryCount ?? 0 }));
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.cacheClearPending = false;
    if (button) {
      button.disabled = false;
      button.textContent = t("confirmClearCache");
    }
  }
}

export { renderAdminReleaseEditor, savePermanentReleaseVersion, batchSelections, setBatchSelections, updateBatchSummary, renderBatchChoices, openBatchBuildPage, closeBatchBuildPage, batchReleaseSummary, renderBatch, loadBatch, loadLatestBatch, startBatchBuild, renderMaintenanceAdmin, updateMaintenance, renderAdminUsers, loadAdminUsers, adminAuditArticle, scheduleAdminUserActivityPoll, refreshAdminUserActivity, requestAdminAction, runAdminUserAction, openAdminUser, renderAdminPresetLabels, savePermanentPresetLabels, openCacheClearDialog, performCacheClear };

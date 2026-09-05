import { $, $$, eventCursor, eventStageLabels, eventTypeLabels, mergeEvents, miniApiEndpoint, pipelineLabels, requestScopes, runtime, state, t, terminalJobStatuses } from "./state.js";
import { copyText, formatBytes } from "./source-rom.js";
import { presetLabel } from "./build.js";
import { apiRequest, miniApiUnavailableMessageKey, privateApiAvailable, renderAccount } from "./session.js";
import { toast } from "./shell.js";
import { openAdminUser, refreshAdminUserActivity } from "./admin.js";
import { navigate, prefersReducedMotion } from "./dock.js";
import { profileAvatar } from "./profile.js";

function renderSelectedJob() {
  if (state.adminJobView) renderActiveJob(state.adminJobView.job, state.adminJobView.events, state.adminJobView);
  const activeJob = state.jobs.find((job) => (job.job_id || job.jobId) === state.activeJobId);
  if (!activeJob) return;
  const activeId = activeJob.job_id || activeJob.jobId;
  renderActiveJob(activeJob, state.activeEventsJobId === activeId ? state.activeEvents : []);
}

function jobNeedsMirrorPoll(job) {
  if (!job || !terminalJobStatuses.has(String(job.status || "").toLowerCase())) return false;
  return (Array.isArray(job.artifacts) ? job.artifacts : []).some((artifact) =>
    (Array.isArray(artifact?.mirrors) ? artifact.mirrors : []).some((mirror) =>
      String(mirror?.provider || "").toLowerCase() === "dccloud"
      && String(mirror?.status || "").toLowerCase() === "repairing"
    )
  );
}

function jobShouldPoll(job) {
  return Boolean(job && (!terminalJobStatuses.has(String(job.status || "").toLowerCase()) || jobNeedsMirrorPoll(job)));
}

function readableEventType(value) {
  const key = String(value || "event");
  return eventTypeLabels[state.language]?.[key] || key.replaceAll("_", " ");
}

function readableEventStage(value) {
  const key = String(value || "");
  return eventStageLabels[state.language]?.[key] || eventTypeLabels[state.language]?.[key] || key.replaceAll("_", " ");
}

function readableStep(value) {
  const key = String(value || "");
  return pipelineLabels[state.language]?.[key] || key.replaceAll("_", " ") || t("events");
}

function readableStepStatus(value) {
  return t({ running: "eventRunning", success: "eventSucceeded", succeeded: "eventSucceeded", failed: "eventFailed" }[String(value || "").toLowerCase()] || "eventRunning");
}

function uploadProgressSnapshot(event) {
  const numberValue = (...keys) => {
    for (const key of keys) {
      const raw = event?.[key];
      if (raw === null || raw === undefined || raw === "") continue;
      const value = Number(raw);
      if (Number.isFinite(value)) return value;
    }
    return 0;
  };
  const bytes = Math.max(0, numberValue("bytes", "bytesTransferred"));
  const totalBytes = Math.max(0, numberValue("totalBytes", "sizeBytes"));
  const calculatedPercent = totalBytes > 0 ? (bytes / totalBytes) * 100 : 0;
  const rawPercent = numberValue("percent");
  const percent = Math.max(0, Math.min(100, Math.round(rawPercent || calculatedPercent)));
  let speedBytesPerSecond = Math.max(0, numberValue("speedBytesPerSecond", "speed"));
  const etaCandidate = ["etaSeconds", "eta"]
    .map((key) => event?.[key])
    .filter((raw) => raw !== null && raw !== undefined && raw !== "")
    .map((raw) => Number(raw))
    .find((value) => Number.isFinite(value));
  let etaSeconds = etaCandidate === undefined ? null : Math.max(0, etaCandidate);
  const firstBytes = Number(event?._uploadFirstBytes);
  const firstAt = Date.parse(String(event?._uploadFirstTimestamp || ""));
  const currentAt = Date.parse(String(event?.timestamp || ""));
  if (speedBytesPerSecond <= 0 && Number.isFinite(firstBytes) && firstBytes >= 0 && Number.isFinite(firstAt) && Number.isFinite(currentAt) && currentAt > firstAt) {
    speedBytesPerSecond = Math.max(0, (bytes - firstBytes) / ((currentAt - firstAt) / 1000));
  }
  if (etaSeconds === null && speedBytesPerSecond > 0 && totalBytes > bytes) {
    etaSeconds = (totalBytes - bytes) / speedBytesPerSecond;
  }
  return { bytes, totalBytes, percent, speedBytesPerSecond, etaSeconds };
}

function uploadProgressKey(event) {
  return [event?.fileIndex || "", event?.fileName || "", event?.provider || ""].join("|");
}

function compactLiveEvents(events) {
  const compacted = [];
  const uploadGroups = new Map();
  for (const event of Array.isArray(events) ? events : []) {
    if (event?.type !== "upload_progress") {
      compacted.push(event);
      continue;
    }
    const key = uploadProgressKey(event);
    const previous = uploadGroups.get(key);
    if (previous) {
      const previousIndex = compacted.indexOf(previous);
      const merged = {
        ...event,
        _uploadUpdateCount: Number(previous._uploadUpdateCount || 1) + 1,
        _uploadFirstTimestamp: previous._uploadFirstTimestamp || previous.timestamp,
        _uploadFirstBytes: Number.isFinite(Number(previous._uploadFirstBytes)) ? Number(previous._uploadFirstBytes) : uploadProgressSnapshot(previous).bytes,
      };
      if (previousIndex >= 0) compacted.splice(previousIndex, 1);
      compacted.push(merged);
      uploadGroups.set(key, merged);
    } else {
      const first = { ...event, _uploadUpdateCount: 1, _uploadFirstTimestamp: event.timestamp, _uploadFirstBytes: uploadProgressSnapshot(event).bytes };
      compacted.push(first);
      uploadGroups.set(key, first);
    }
  }
  return compacted;
}

function eventTitle(event) {
  if (event.type === "step" && event.step) return `${readableStep(event.step)} · ${readableStepStatus(event.status)}`;
  if (event.type === "plan") return `${readableEventType(event.type)} · ${(event.steps || []).length} ${t("eventSteps")}`;
  return readableEventType(event.type || event.status);
}

function formatEventValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join(" · ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function eventDetailEntries(event) {
  const entries = [];
  const skip = new Set(["sequence", "jobId", "timestamp", "type", "traceback", "message", "error", "warning", "step", "stage", "status"]);
  Object.entries(event || {}).forEach(([key, value]) => {
    if (key.startsWith("_")) return;
    if (skip.has(key)) return;
    if (key === "details" && value && typeof value === "object" && !Array.isArray(value)) {
      Object.entries(value).forEach(([detailKey, detailValue]) => entries.push([detailKey, formatEventValue(detailValue)]));
    } else entries.push([key, formatEventValue(value)]);
  });
  return entries;
}

function renderUploadProgressCard(event) {
  const snapshot = uploadProgressSnapshot(event);
  const card = document.createElement("div");
  card.className = "event-upload-card";
  card.dataset.progressPercent = String(snapshot.percent);
  const header = document.createElement("div"); header.className = "event-upload-header";
  const fileInfo = document.createElement("div"); fileInfo.className = "event-upload-file";
  const file = document.createElement("strong"); file.textContent = event.fileName || t("artifact");
  fileInfo.append(file);
  const provider = String(event.provider || "").trim().toLowerCase();
  if (provider) {
    const providerLabel = document.createElement("small"); providerLabel.textContent = provider === "dccloud" ? "DC Cloud" : provider;
    fileInfo.append(providerLabel);
  }
  const percent = document.createElement("b"); percent.textContent = `${snapshot.percent}%`;
  header.append(fileInfo, percent);
  const track = document.createElement("div"); track.className = "event-upload-track";
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-valuemin", "0"); track.setAttribute("aria-valuemax", "100"); track.setAttribute("aria-valuenow", String(snapshot.percent));
  const fill = document.createElement("i"); fill.style.width = `${snapshot.percent}%`; fill.setAttribute("aria-hidden", "true");
  track.append(fill);
  const metrics = document.createElement("div"); metrics.className = "event-upload-metrics";
  const metric = (label, value) => {
    const node = document.createElement("span");
    const caption = document.createElement("small"); caption.textContent = label;
    const content = document.createElement("b"); content.textContent = value;
    node.append(caption, content); return node;
  };
  metrics.append(
    metric(t("uploadTransferred"), `${formatBytes(snapshot.bytes)} / ${formatBytes(snapshot.totalBytes)}`),
    metric(t("uploadSpeed"), snapshot.speedBytesPerSecond > 0 ? `${formatBytes(snapshot.speedBytesPerSecond)}/s` : "—"),
    metric(t("uploadEta"), snapshot.percent >= 100 ? t("uploadComplete") : Number.isFinite(snapshot.etaSeconds) && snapshot.etaSeconds > 0 ? `${Math.round(snapshot.etaSeconds)}s` : "—")
  );
  const updates = Number(event._uploadUpdateCount || 1);
  if (updates > 1) {
    const note = document.createElement("small"); note.className = "event-upload-note";
    note.textContent = t("uploadUpdates", { count: updates }); card.append(note);
  }
  card.prepend(header, track, metrics);
  return card;
}

function statusLabel(status) {
  return t({
    queued: "stageQueued", preflight: "stagePreflight", downloading: "stageDownloading",
    running: "stageRunning", uploading: "stageUploading", succeeded: "pipelineComplete",
    failed: "pipelineFailed", cancelled: "cancel"
  }[status] || status);
}

function jobMetadata(job) {
  return {
    ...(job?.recipe?.source?.metadata || {}),
    ...(job?.rom_metadata || job?.romMetadata || {})
  };
}

function jobDeviceLabel(job) {
  const product = String(job?.recipe?.device || "").trim();
  if (!product) return "";
  const name = catalogDeviceName(product);
  return name && name !== product ? `${name} (${product})` : name || product;
}

function jobEditionBadge(job) {
  const preset = String(job?.recipe?.build?.preset || "").trim().toLowerCase();
  if (!preset) return null;
  const label = presetLabel(preset, job?.recipe?.build?.editionLabels || job?.recipe?.build?.edition_labels || state.presetLabels);
  if (!label) return null;
  const badge = document.createElement("span");
  badge.className = "job-edition-badge";
  badge.textContent = label;
  return badge;
}

function jobHistoryDayLabel(job) {
  const value = job?.created_at || job?.createdAt;
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "";
  const startOfDay = (input) => { const day = new Date(input); day.setHours(0, 0, 0, 0); return day.getTime(); };
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86_400_000);
  if (days === 0) return t("jobHistoryToday");
  if (days === 1) return t("jobHistoryYesterday");
  const options = { day: "numeric", month: "short" };
  if (date.getFullYear() !== new Date().getFullYear()) options.year = "numeric";
  return new Intl.DateTimeFormat(state.language === "vi" ? "vi-VN" : "en-US", options).format(date);
}

function catalogDeviceName(product) {
  const normalized = String(product || "").trim().toLocaleUpperCase();
  if (!normalized) return "";
  return state.catalog?.devices?.find(
    (item) => String(item?.product || "").trim().toLocaleUpperCase() === normalized
  )?.name || "";
}

function jobProgress(job) {
  const value = Math.max(0, Math.min(1, Number(job?.progress || 0)));
  return Math.round(value * 100);
}

function jobModBadge(job) {
  const build = job?.recipe?.build || {};
  const parts = [build.modVersion, build.modReleaseVersion, build.mods?.length ? `${build.mods.length} MOD` : ""]
    .map((part) => String(part || "").trim())
    .filter(Boolean);
  if (!parts.length) return null;
  const badge = document.createElement("span");
  badge.className = "job-mod-badge";
  badge.textContent = parts.join(" · ");
  return badge;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(state.language === "vi" ? "vi-VN" : "en-GB", {
    dateStyle: "medium", timeStyle: "short"
  }).format(date);
}

function formatElapsed(job) {
  const start = new Date(job.created_at || job.createdAt || 0).getTime();
  const end = new Date(job.finished_at || job.finishedAt || Date.now()).getTime();
  if (!start || Number.isNaN(start) || Number.isNaN(end)) return "—";
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

function jobFact(label, value) {
  const node = document.createElement("div");
  const name = document.createElement("small"); name.textContent = label;
  const content = document.createElement("strong"); content.textContent = value || "—";
  node.append(name, content);
  return node;
}

function artifactCloudUrl(artifact) {
  const candidate = String(artifact?.publicUrl || artifact?.public_url || "").trim();
  try {
    if (
      !candidate
      || candidate.includes("\\")
      || /\s|[\u0000-\u001f\u007f]/u.test(candidate)
      || /%(?![0-9a-f]{2})/iu.test(candidate)
    ) return "";
    const parsed = new URL(candidate);
    const hostname = parsed.hostname.toLowerCase();
    let miniApiOrigin = "";
    try { miniApiOrigin = new URL(miniApiEndpoint).origin; } catch (_) {}
    if (
      parsed.protocol !== "https:"
      || !hostname
      || hostname === "wukong-mini-api.onrender.com"
      || (miniApiOrigin && parsed.origin === miniApiOrigin)
    ) return "";
    return parsed.href;
  } catch (_) {
    return "";
  }
}

function artifactMirrorUrl(mirror) {
  return artifactCloudUrl({ publicUrl: mirror?.browseUrl || mirror?.browse_url });
}

async function repairDcCloudMirror(jobId, button) {
  if (!jobId || !button) return;
  button.disabled = true;
  try {
    await apiRequest(`/v1/jobs/${encodeURIComponent(jobId)}/mirror-repair`, { method: "POST" });
    toast(t("dcCloudRepairQueued"));
    await loadJobs({ force: true });
  } catch (error) {
    toast(error?.message || t("dcCloudRepairFailed"), true);
  } finally {
    button.disabled = false;
  }
}

async function dcCloudDownloadUrl(jobId, artifactIndex) {
  if (!jobId || !Number.isInteger(artifactIndex)) return "";
  const payload = await apiRequest(
    `/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${artifactIndex}/dccloud-download`
  );
  const url = artifactCloudUrl({ publicUrl: payload?.downloadUrl });
  if (!url) throw new Error(t("artifactLinkUnavailable"));
  return url;
}

async function downloadDcCloudMirror(jobId, artifactIndex, button) {
  if (!jobId || !Number.isInteger(artifactIndex) || !button) return;
  button.disabled = true;
  try {
    openArtifactUrl(await dcCloudDownloadUrl(jobId, artifactIndex));
  } catch (error) {
    toast(error?.message || t("artifactLinkUnavailable"), true);
  } finally {
    button.disabled = false;
  }
}

async function copyDcCloudMirrorLink(jobId, artifactIndex, button) {
  if (!jobId || !Number.isInteger(artifactIndex) || !button) return;
  button.disabled = true;
  try {
    await copyText(await dcCloudDownloadUrl(jobId, artifactIndex));
    toast(t("artifactLinkCopied"));
  } catch (error) {
    toast(error?.message || t("clipboardDenied"), true);
  } finally {
    button.disabled = false;
  }
}

function artifactProvider(url) {
  const hostname = new URL(url).hostname.toLowerCase();
  if (hostname === "drive.google.com" || hostname.endsWith(".googleusercontent.com")) return "Google Drive";
  if (hostname === "1drv.ms" || hostname.endsWith(".onedrive.live.com")) return "OneDrive";
  if (hostname === "dropbox.com" || hostname.endsWith(".dropboxusercontent.com")) return "Dropbox";
  if (hostname === "mega.nz" || hostname.endsWith(".mega.nz")) return "MEGA";
  return hostname.replace(/^www\./, "");
}

function openArtifactUrl(url) {
  if (runtime.TelegramApp?.openLink) runtime.TelegramApp.openLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

function renderArtifacts(job) {
  const section = document.createElement("section"); section.className = "job-artifacts";
  const title = document.createElement("h3"); title.textContent = t("artifactsReady"); section.append(title);
  const artifacts = Array.isArray(job.artifacts) ? job.artifacts : [];
  if (!artifacts.length) {
    const empty = document.createElement("p"); empty.textContent = t("noArtifacts"); section.append(empty); return section;
  }
  artifacts.forEach((artifact, index) => {
    const card = document.createElement("article");
    const header = document.createElement("div");
    const name = document.createElement("strong"); name.textContent = artifact.name || "Artifact";
    const size = document.createElement("span"); size.textContent = formatBytes(artifact.size_bytes ?? artifact.sizeBytes);
    header.append(name, size);
    const sha = document.createElement("code"); sha.textContent = `SHA-256 ${artifact.sha256 || "—"}`;
    const cloudUrl = artifactCloudUrl(artifact);
    if (cloudUrl) {
      const providerName = artifactProvider(cloudUrl);
      const provider = document.createElement("small");
      provider.className = "artifact-provider";
      provider.textContent = providerName;
      const actions = document.createElement("div");
      actions.className = "job-artifact-actions";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "artifact-open";
      open.dataset.jobFocus = `artifact-open-${index}`;
      open.textContent = t("openArtifactCloud", { provider: providerName });
      open.setAttribute("aria-label", `${open.textContent}: ${artifact.name || "Artifact"}`);
      open.addEventListener("click", () => openArtifactUrl(cloudUrl));
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "artifact-copy";
      copy.dataset.jobFocus = `artifact-copy-${index}`;
      copy.textContent = t("copyArtifactLink");
      copy.setAttribute("aria-label", `${copy.textContent}: ${artifact.name || "Artifact"}`);
      copy.addEventListener("click", () => {
        copyText(cloudUrl)
          .then(() => toast(t("artifactLinkCopied")))
          .catch(() => toast(t("clipboardDenied"), true));
      });
      actions.append(open, copy);
      card.append(header, sha, provider, actions);
    } else {
      const uri = document.createElement("code"); uri.textContent = t("artifactLinkUnavailable");
      card.append(header, sha, uri);
    }
    const mirrors = Array.isArray(artifact.mirrors) ? artifact.mirrors : [];
    mirrors.filter((mirror) => String(mirror?.provider || "").toLowerCase() === "dccloud").forEach((mirror) => {
      const mirrorStatus = String(mirror?.status || "pending").toLowerCase();
      const mirrorLabel = document.createElement("small");
      mirrorLabel.className = "artifact-provider";
      mirrorLabel.textContent = mirrorStatus === "available"
        ? t("dcCloudMirror")
        : mirrorStatus === "repairing"
          ? t("dcCloudMirrorRepairing")
          : mirrorStatus === "failed"
            ? t("dcCloudMirrorFailed")
            : t("dcCloudMirrorPending");
      card.append(mirrorLabel);
      if (mirrorStatus === "available") {
        const mirrorActions = document.createElement("div");
        mirrorActions.className = "job-artifact-actions";
        const downloadMirror = document.createElement("button");
        downloadMirror.type = "button";
        downloadMirror.className = "artifact-open";
        downloadMirror.textContent = t("downloadArtifactCloud", { provider: "DC Cloud" });
        downloadMirror.setAttribute("aria-label", `${downloadMirror.textContent}: ${artifact.name || "Artifact"}`);
        downloadMirror.addEventListener("click", () => downloadDcCloudMirror(job.job_id || job.jobId, index, downloadMirror));
        const copyMirror = document.createElement("button");
        copyMirror.type = "button";
        copyMirror.className = "artifact-copy";
        copyMirror.textContent = t("copyArtifactLink");
        copyMirror.setAttribute("aria-label", `${copyMirror.textContent}: ${artifact.name || "Artifact"}`);
        copyMirror.addEventListener("click", () => copyDcCloudMirrorLink(job.job_id || job.jobId, index, copyMirror));
        mirrorActions.append(downloadMirror, copyMirror);
        card.append(mirrorActions);
      }
      if (
        terminalJobStatuses.has(job.status)
        && mirrorStatus !== "available"
        && mirrorStatus !== "repairing"
        && (job.job_id || job.jobId)
      ) {
        const repair = document.createElement("button");
        repair.type = "button";
        repair.className = "secondary artifact-repair";
        repair.textContent = t("dcCloudRepair");
        repair.title = t("dcCloudRepairHint");
        repair.addEventListener("click", () => repairDcCloudMirror(job.job_id || job.jobId, repair));
        card.append(repair);
      }
    });
    section.append(card);
  });
  return section;
}

function renderEvents(events, expanded = false) {
  const section = document.createElement("section"); section.className = "job-events";
  if (expanded) section.classList.add("expanded");
  const rawPreviewEvents = events.slice(-8);
  const visibleEvents = expanded ? events : compactLiveEvents(rawPreviewEvents);
  const heading = document.createElement("div"); heading.className = "job-events-heading";
  const title = document.createElement("h3"); title.textContent = expanded ? t("fullLogTitle") : t("eventTimeline");
  const count = document.createElement("span"); count.textContent = t("eventsPreview", { visible: expanded ? events.length : visibleEvents.length, total: events.length });
  heading.append(title, count); section.append(heading);
  const list = document.createElement("ol");
  if (!events.length) {
    const empty = document.createElement("li"); empty.textContent = t("noEvents"); list.append(empty);
  } else {
    let currentGroup = "";
    visibleEvents.forEach((event) => {
      const group = event.step ? readableStep(event.step) : readableEventStage(event.stage || event.status || event.type || t("events"));
      if (group !== currentGroup) {
        currentGroup = group;
        const divider = document.createElement("li"); divider.className = "event-group";
        divider.textContent = group; list.append(divider);
      }
      const item = document.createElement("li"); item.className = `event-${String(event.type || event.status || "info").replace(/[^a-z0-9_-]/gi, "")}`;
      const marker = document.createElement("span"); marker.className = "event-marker";
      const markerDot = document.createElement("i");
      const markerSequence = document.createElement("b"); markerSequence.textContent = String(event.sequence || "•").padStart(2, "0");
      marker.append(markerDot, markerSequence);
      const content = document.createElement("div"); content.className = "event-copy";
      const titleRow = document.createElement("div"); titleRow.className = "event-title-row";
      const eventTitleNode = document.createElement("strong"); eventTitleNode.textContent = eventTitle(event);
      const eventTime = document.createElement("time"); eventTime.dateTime = String(event.timestamp || ""); eventTime.textContent = formatDate(event.timestamp);
      titleRow.append(eventTitleNode, eventTime);
      const detail = document.createElement("p");
      const details = eventDetailEntries(event);
      const visible = event.message || event.error || event.warning || (event.type === "step" ? details.slice(0, 3).map(([key, value]) => `${key}: ${value}`).join(" · ") : "") || event.stage || event.status;
      if (event.type === "upload_progress" && !expanded) {
        detail.hidden = true;
        content.append(titleRow, renderUploadProgressCard(event));
      } else {
        detail.textContent = String(visible || readableEventStage(event.stage || event.status || event.type || ""));
        if (!detail.textContent) detail.hidden = true;
        content.append(titleRow, detail);
      }
      if (expanded && details.length) {
        const data = document.createElement("dl"); data.className = "event-data";
        details.forEach(([key, value]) => {
          const row = document.createElement("div");
          const term = document.createElement("dt"); term.textContent = key.replaceAll(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ");
          const description = document.createElement("dd"); description.textContent = value;
          row.append(term, description); data.append(row);
        });
        content.append(data);
      }
      item.append(marker, content); list.append(item);
    });
  }
  section.append(list); return section;
}

function jobAction(label, action, job, danger = false) {
  const button = document.createElement("button"); button.type = "button"; button.textContent = label;
  button.dataset.jobFocus = `job-action-${action}`;
  if (danger) button.classList.add("danger");
  button.addEventListener("click", () => runJobAction(action, job.job_id || job.jobId).catch((error) => toast(error.message, true)));
  return button;
}

function openAdminJobPage(job) {
  if (state.me?.role !== "admin" || !state.selectedAdminUserId) return;
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  closeAdminJobPage({ restoreFocus: false, scroll: false, refreshUser: false });
  clearTimeout(state.jobsPollTimer);
  ++state.jobDetailRequestId;
  const view = {
    jobId: job.job_id || job.jobId, job, events: [], requestId: 0, timer: null,
    returnFocus: job.__returnFocus || document.activeElement,
    returnScrollY: window.scrollY, expandedConfigJobId: "", expandedLogJobId: "",
    jobEventsHasMore: false, unchangedPolls: 0, signature: ""
  };
  state.adminJobView = view;
  $("#system").classList.add("admin-job-open");
  $("#admin-job-page").hidden = false;
  renderActiveJob(job, [], view);
  const status = $("#admin-job-connection");
  status.classList.remove("error");
  if (status.textContent !== t("userJobLoading")) status.textContent = t("userJobLoading");
  window.scrollTo({ top: 0, behavior: "instant" });
  $("#admin-job-back").focus({ preventScroll: true });
  loadAdminJobDetail();
}

function closeAdminJobPage({ restoreFocus = true, scroll = true, refreshUser = true } = {}) {
  requestScopes.cancel("adminJob");
  const view = state.adminJobView;
  if (!view) return;
  clearTimeout(view.timer);
  state.adminJobView = null;
  $("#system").classList.remove("admin-job-open");
  $("#admin-job-page").hidden = true;
  $("#admin-job-detail").replaceChildren();
  if (scroll) window.scrollTo({ top: view.returnScrollY, behavior: "instant" });
  if (restoreFocus) {
    const opener = view.returnFocus?.isConnected && view.returnFocus.matches?.("[data-open-user-job]")
      ? view.returnFocus
      : $$("[data-open-user-job]").find(button => button.dataset.openUserJob === view.jobId);
    opener?.focus({ preventScroll: true });
  }
  scheduleJobsPoll(true);
  if (refreshUser && state.selectedAdminUserId && !document.hidden) {
    refreshAdminUserActivity();
  }
}

async function loadAdminJobDetail() {
  const view = state.adminJobView;
  if (!view || document.hidden || state.me?.role !== "admin") return;
  clearTimeout(view.timer);
  const requestId = ++view.requestId;
  const after = view.events.reduce((max, event) => Math.max(max, Number(event.sequence || 0)), 0);
  const status = $("#admin-job-connection");
  try {
    const signal = requestScopes.start("adminJob");
    const payload = view.historicalLogPage && view.events.length
      ? { activeJob: await apiRequest(`/v1/jobs/${encodeURIComponent(view.jobId)}`, { signal }), events: [], eventsHasMore: view.jobEventsHasMore }
      : await apiRequest(`/v1/sync?includeHistory=0&jobId=${encodeURIComponent(view.jobId)}&after=${after}`, { signal });
    if (state.adminJobView !== view || requestId !== view.requestId) return;
    const job = payload.activeJob;
    if (!job || (job.job_id || job.jobId) !== view.jobId) {
      throw new Error(t("jobUnavailable"));
    }
    const incoming = Array.isArray(payload.events) ? payload.events : [];
    if (!view.historicalLogPage || !view.events.length) view.events = mergeEvents(view.events, incoming);
    view.job = job;
    view.jobEventsHasMore = payload.eventsHasMore ?? incoming.length >= 500;
    const signature = JSON.stringify([job.status, job.stage, job.progress, job.updated_at || job.updatedAt, view.events.length]);
    view.unchangedPolls = signature === view.signature ? view.unchangedPolls + 1 : 0;
    view.signature = signature;
    renderActiveJob(job, view.events, view);
    if (status.textContent !== t("userJobSynced")) status.textContent = t("userJobSynced");
    status.classList.remove("error");
  } catch (error) {
    if (state.adminJobView !== view || requestId !== view.requestId) return;
    const message = error.connectionFailed ? t("jobsOffline") : error.message;
    if (status.textContent !== message) status.textContent = message;
    status.classList.add("error");
  } finally {
    if (state.adminJobView === view && requestId === view.requestId && !document.hidden) {
      const delay = !jobShouldPoll(view.job) || view.unchangedPolls >= 6 ? 30000 : view.unchangedPolls >= 3 ? 15000 : 10000;
      view.timer = setTimeout(loadAdminJobDetail, delay);
    }
  }
}

function openJob(job) {
  const jobId = job.job_id || job.jobId;
  state.activeJobId = jobId;
  localStorage.setItem("wukong-active-job", state.activeJobId);
  ++state.jobDetailRequestId;
  state.activeEvents = [];
  state.historicalLogPage = false;
  state.activeEventsJobId = "";
  state.jobEventsHasMore = false;
  state.jobHistoryFilter = job.status === "succeeded" ? "succeeded" : terminalJobStatuses.has(job.status) ? "failed" : "active";
  renderActiveJob(job, []); renderJobHistory();
  scheduleJobsPoll(jobShouldPoll(job), true);
  loadJobDetail(jobId).catch((error) => { if (error.name !== "AbortError") toast(error.message, true); });
}

function renderJobParameters(job, root, reader) {
  const id = job.job_id || job.jobId;
  const previous = root.querySelector(":scope > .job-config");
  const details = previous?.dataset.jobId === id ? previous : document.createElement("details");
  details.className = "job-config"; details.dataset.jobId = id;
  details.open = reader.expandedConfigJobId === id;
  if (!details.children.length) {
    details.append(document.createElement("summary"), document.createElement("p"), document.createElement("button"));
    details.addEventListener("toggle", () => { if (details.isConnected) reader.expandedConfigJobId = details.open ? id : ""; });
  }
  details.querySelector("summary").textContent = t("jobParameters");
  details.querySelector("p").textContent = t("jobParametersHint");
  const copy = details.querySelector("button"); copy.type = "button"; copy.className = "secondary"; copy.textContent = t("copyJobParameters");
  copy.onclick = () => copyText(JSON.stringify(job, null, 2)).then(() => toast(t("jobParametersCopied"))).catch(() => toast(t("clipboardDenied"), true));
  const { recipe, ...runtime } = job;
  for (const [key, value] of [["jobRecipeData", recipe || {}], ["jobRuntimeData", runtime]]) {
    let data = details.querySelector(`[data-parameters="${key}"]`);
    if (!data) {
      data = document.createElement("pre"); data.tabIndex = 0; data.dataset.parameters = key;
      details.append(document.createElement("h4"), data);
    }
    data.previousElementSibling.textContent = t(key);
    const text = JSON.stringify(value, null, 2);
    if (data.textContent !== text) {
      const { scrollTop, scrollLeft } = data;
      data.textContent = text;
      data.scrollTop = scrollTop; data.scrollLeft = scrollLeft;
    }
  }
  return details;
}

function renderActiveJob(job, events, inspection = null) {
  const root = inspection ? $("#admin-job-detail") : $("#active-job");
  const reader = inspection || state;
  if (!root) return;
  const focusedJobControl = root.contains(document.activeElement)
    ? document.activeElement.closest("[data-job-focus]")
    : null;
  const focusedJobControlKey = focusedJobControl?.dataset.jobFocus || "";
  if (!job) { root.hidden = true; root.replaceChildren(); delete root.dataset.jobId; return; }
  root.hidden = false;
  root.dataset.jobId = job.job_id || job.jobId;
  const metadata = jobMetadata(job);
  const header = document.createElement("header");
  const title = document.createElement("div");
  const kicker = document.createElement("small");
  kicker.textContent = t(terminalJobStatuses.has(job.status) ? "historicalJob" : "activeJob");
  const heading = document.createElement("h2"); heading.textContent = metadata.version || `${job.recipe?.device || "ROM"} · ${String(job.job_id || job.jobId).slice(0, 12)}`;
  title.append(kicker, heading);
  const badge = document.createElement("span"); badge.className = `job-status ${job.status}`; badge.textContent = statusLabel(job.status);
  header.append(title, badge);
  const creator = document.createElement("div"); creator.className = "job-creator";
  if (state.me?.role === "admin" && job.createdBy) {
    const user = job.createdBy;
    const text = document.createElement("div"); text.className = "job-creator-copy";
    const label = document.createElement("small"); label.textContent = t("jobCreator");
    const name = document.createElement("strong"); name.textContent = user.displayName || user.username || user.telegramId;
    const identity = document.createElement("span"); identity.textContent = [user.username ? `@${user.username}` : "", `ID ${user.telegramId}`].filter(Boolean).join(" · ");
    text.append(label, name, identity);
    const open = document.createElement("button"); open.type = "button"; open.className = "secondary"; open.textContent = t("viewJobUser");
    open.addEventListener("click", () => { navigate("system"); openAdminUser(user.telegramId).catch(error => toast(error.message, true)); });
    creator.append(profileAvatar(user), text);
    if (!inspection) creator.append(open);
  } else creator.hidden = true;
  const progress = document.createElement("div"); progress.className = "job-progress";
  const progressCopy = document.createElement("div");
  const stage = document.createElement("strong"); stage.textContent = job.stage || statusLabel(job.status);
  const percentage = document.createElement("b"); percentage.textContent = `${jobProgress(job)}%`;
  progressCopy.append(stage, percentage);
  const track = document.createElement("div"); const fill = document.createElement("i"); fill.style.width = `${jobProgress(job)}%`; track.append(fill);
  progress.append(progressCopy, track);
  const build = job.recipe?.build || {};
  const context = document.createElement("section"); context.className = "job-context";
  const contextTitle = document.createElement("div");
  const contextLabel = document.createElement("strong"); contextLabel.textContent = t("jobContext");
  const mods = document.createElement("div"); mods.className = "job-mod-grid";
  const selectedJobMods = build.mods || [];
  if (selectedJobMods.length) mods.append(...selectedJobMods.map((name) => {
    const chip = document.createElement("span"); chip.textContent = name; return chip;
  }));
  else { const empty = document.createElement("small"); empty.textContent = t("noModsSelected"); mods.append(empty); }
  contextTitle.append(contextLabel, mods);
  const contextCopy = document.createElement("div"); contextCopy.className = "job-release-context";
  const pack = document.createElement("small"); pack.textContent = build.modVersion || "—";
  const release = document.createElement("b"); release.textContent = build.modReleaseVersion || "—";
  const count = document.createElement("span"); count.textContent = `${(build.mods || []).length} ${t("selected")}`;
  contextCopy.append(pack, release, count);
  context.append(contextTitle, contextCopy);
  const upload = [...events].reverse().find((event) => event.type === "upload_progress");
  const uploadSnapshot = upload ? uploadProgressSnapshot(upload) : null;
  const uploadDetail = upload
    ? `${upload.fileName || "—"} · ${uploadSnapshot.percent}% · ${formatBytes(uploadSnapshot.bytes)} / ${formatBytes(uploadSnapshot.totalBytes)} · ${formatBytes(uploadSnapshot.speedBytesPerSecond)}/s${Number.isFinite(uploadSnapshot.etaSeconds) ? ` · ETA ${Math.max(0, Math.round(uploadSnapshot.etaSeconds))}s` : ""}`
    : "";
  const facts = document.createElement("div"); facts.className = "job-facts";
  const product = metadata.productName || job.recipe?.device;
  const factNodes = [
    jobFact("Job ID", job.job_id || job.jobId),
    jobFact(t("jobCreatedAt"), formatDate(job.created_at || job.createdAt)),
    jobFact(t("jobUpdatedAt"), formatDate(job.updated_at || job.updatedAt)),
    jobFact(t("deviceName"), catalogDeviceName(product)),
    jobFact(t("productCode"), product),
    jobFact(t("detectedDevice"), metadata.device),
    jobFact(t("androidVersion"), metadata.androidVersion),
    jobFact(t("securityPatch"), metadata.securityPatch),
    jobFact(t("buildDate"), metadata.buildDate),
    jobFact(t("runner"), job.runner),
    jobFact(t("elapsed"), formatElapsed(job)),
    jobFact(t("modConfiguration"), `${build.preset ? presetLabel(build.preset, build.editionLabels || build.edition_labels) : "—"} / ${build.modVersion || "—"}`),
    jobFact(t("releaseVersion"), build.modReleaseVersion),
    jobFact(t("sourceSizeDetected"), formatBytes(job.recipe?.source?.sizeBytes))
  ];
  if (!terminalJobStatuses.has(job.status)) {
    factNodes.push(jobFact(t(job.status === "uploading" ? "uploadingNow" : "uploadSummary"), uploadDetail));
  }
  facts.append(...factNodes);
  const artifacts = renderArtifacts(job);
  const actions = document.createElement("div"); actions.className = "job-controls";
  const jobId = job.job_id || job.jobId;
  const logExpanded = reader.expandedLogJobId === jobId;
  const logButton = document.createElement("button"); logButton.type = "button"; logButton.className = "job-log-toggle";
  logButton.dataset.jobFocus = "log-toggle";
  logButton.textContent = t(logExpanded ? "hideFullLog" : "viewFullLog");
  logButton.setAttribute("aria-expanded", String(logExpanded));
  logButton.addEventListener("click", () => {
    reader.expandedLogJobId = logExpanded ? "" : jobId;
    renderActiveJob(job, events, inspection);
    if (!logExpanded) requestAnimationFrame(() => root.querySelector(".job-events")?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" }));
  });
  actions.append(logButton);
  if (reader.jobEventsHasMore) {
    const more = document.createElement("button"); more.type = "button"; more.textContent = t("loadMoreJobEvents");
    more.dataset.jobFocus = "load-more-events";
    more.addEventListener("click", () => { more.disabled = true; loadLogPage(jobId, events, "next", inspection).catch(error => toast(error.message, true)).finally(() => { more.disabled = false; }); });
    actions.append(more);
  }
  if (Number(events[0]?.sequence) > 1) {
    const previous = document.createElement("button"); previous.type = "button";
    previous.textContent = t("previousEvents"); previous.dataset.jobFocus = "previous-events";
    previous.addEventListener("click", () => loadLogPage(jobId, events, "previous", inspection).catch(error => toast(error.message, true)));
    actions.append(previous);
  }
  if (!inspection && !terminalJobStatuses.has(job.status)) actions.append(jobAction(t("cancel"), "cancel", job, true));
  if (!inspection && ["failed", "cancelled"].includes(job.status) && job.checkpoint) actions.append(jobAction(t("resume"), "resume", job));
  const config = state.me?.role === "admin" ? renderJobParameters(job, root, reader) : null;
  const technical = document.createElement("details"); technical.className = "job-technical";
  technical.open = root.querySelector(".job-technical")?.open || false;
  const technicalTitle = document.createElement("summary"); technicalTitle.textContent = t("metadataDetails");
  technical.append(technicalTitle, context, facts);
  const updated = document.createElement("small"); updated.className = "job-sync-time";
  updated.textContent = `${t("latestUpdate")}: ${formatDate(job.updated_at || job.updatedAt)}`;
  progress.append(updated);
  const before = [header, creator, progress, technical];
  const previousLog = root.querySelector(".job-events");
  const previousTop = previousLog?.scrollTop || 0;
  const atBottom = previousLog ? previousLog.scrollHeight - previousTop - previousLog.clientHeight < 36 : true;
  const nextLog = renderEvents(events, logExpanded);
  const log = previousLog?.isEqualNode(nextLog) ? previousLog : nextLog;
  const children = [...before, ...(config ? [config] : []), artifacts, actions, log];
  for (let index = 0; index < children.length; index += 1) {
    const child = children[index], current = root.children[index];
    // Retain equal presentation nodes and the attached parameter reader.
    if (current === child || (index < before.length && current?.isEqualNode(child))) continue;
    if (current) root.insertBefore(child, current); else root.append(child);
    if (current && !children.includes(current)) current.remove();
  }
  while (root.children.length > children.length) root.lastElementChild.remove();
  if (log !== previousLog) log.scrollTop = atBottom && !reader.historicalLogPage ? log.scrollHeight : previousTop;
  if (focusedJobControlKey) {
    root.querySelector(`[data-job-focus="${focusedJobControlKey}"]`)?.focus({ preventScroll: true });
  }
}

function historyDateBoundary(value, end = false) {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  if (end) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

function appendJobHistoryFilters(params, { search, preset, mod, from, to } = {}) {
  const valueOf = (control) => typeof control === "string" ? control : control?.value || "";
  const searchValue = valueOf(search).trim();
  const presetValue = valueOf(preset);
  const modValue = valueOf(mod).trim();
  const fromValue = historyDateBoundary(valueOf(from));
  const toValue = historyDateBoundary(valueOf(to), true);
  if (searchValue) params.set("q", searchValue);
  if (presetValue) params.set("preset", presetValue);
  if (modValue) params.set("modVersion", modValue);
  if (fromValue) params.set("createdFrom", fromValue);
  if (toValue) params.set("createdTo", toValue);
}

function jobHistoryParams({ includePage = true, jobId = "", after = "" } = {}) {
  const params = new URLSearchParams();
  if (includePage) params.set("page", String(state.jobHistoryPage));
  if (state.jobHistoryFilter) params.set("status", state.jobHistoryFilter);
  appendJobHistoryFilters(params, {
    search: $("#job-history-search"),
    preset: $("#job-history-preset"),
    mod: $("#job-history-mod"),
    from: $("#job-history-from"),
    to: $("#job-history-to")
  });
  if (jobId) params.set("jobId", jobId);
  if (after) params.set("after", after);
  return params;
}

function historyHasFilters() {
  return Boolean(
    $("#job-history-search")?.value.trim()
    || $("#job-history-preset")?.value
    || $("#job-history-mod")?.value.trim()
    || $("#job-history-from")?.value
    || $("#job-history-to")?.value
  );
}

function legacyJobHistoryPage(jobs, { filter, page, search, preset, mod, from, to }) {
  const valueOf = (control) => typeof control === "string" ? control : control?.value || "";
  const query = valueOf(search).trim().toLocaleLowerCase();
  const presetValue = valueOf(preset).trim().toLocaleLowerCase();
  const modValue = valueOf(mod).trim().toLocaleLowerCase();
  const createdFrom = historyDateBoundary(valueOf(from));
  const createdTo = historyDateBoundary(valueOf(to), true);
  const matchingFilters = jobs.filter((job) => {
    const build = job.recipe?.build || {};
    const metadata = jobMetadata(job);
    const creator = job.createdBy || {};
    const searchable = [
      job.job_id || job.jobId,
      jobDeviceLabel(job),
      job.recipe?.device,
      build.modVersion,
      build.modReleaseVersion,
      metadata.version,
      creator.displayName,
      creator.username,
      creator.telegramId
    ].filter(Boolean).join(" ").toLocaleLowerCase();
    const createdAt = new Date(job.created_at || job.createdAt || 0).getTime();
    return (!query || searchable.includes(query))
      && (!presetValue || String(build.preset || "").toLocaleLowerCase() === presetValue)
      && (!modValue || String(build.modVersion || "").toLocaleLowerCase() === modValue)
      && (!createdFrom || createdAt >= Date.parse(createdFrom))
      && (!createdTo || createdAt < Date.parse(createdTo));
  });
  const statusCounts = {
    active: matchingFilters.filter((job) => !terminalJobStatuses.has(job.status)).length,
    succeeded: matchingFilters.filter((job) => job.status === "succeeded").length,
    failed: matchingFilters.filter((job) => ["failed", "cancelled"].includes(job.status)).length
  };
  const matchingStatus = matchingFilters.filter((job) => filter === "active"
    ? !terminalJobStatuses.has(job.status)
    : filter === "succeeded" ? job.status === "succeeded" : ["failed", "cancelled"].includes(job.status));
  const pageSize = 20;
  const totalPages = Math.max(1, Math.ceil(matchingStatus.length / pageSize));
  const safePage = Math.min(Math.max(1, Number(page) || 1), totalPages);
  return {
    jobs: matchingStatus.slice((safePage - 1) * pageSize, safePage * pageSize),
    page: safePage,
    pageSize,
    total: matchingStatus.length,
    totalPages,
    statusCounts
  };
}

function renderPageButtons(root, page, totalPages, onPage) {
  root.replaceChildren();
  if (totalPages <= 1) return;
  const addButton = (label, target, disabled = false, current = false) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = current ? "active" : "";
    button.textContent = label;
    button.disabled = disabled;
    if (current) button.setAttribute("aria-current", "page");
    if (!current && !disabled) button.addEventListener("click", () => onPage(target));
    if (current) button.setAttribute("aria-label", t("jobPage", { page: target }));
    root.append(button);
  };
  addButton(t("jobPrevious"), page - 1, page <= 1);
  const numbers = [];
  if (totalPages <= 10) {
    for (let value = 1; value <= totalPages; value += 1) numbers.push(value);
  } else {
    const start = Math.max(2, Math.min(page - 3, totalPages - 7));
    numbers.push(1);
    if (start > 2) numbers.push("…");
    for (let value = start; value < start + 6; value += 1) numbers.push(value);
    if (start + 6 < totalPages) numbers.push("…");
    numbers.push(totalPages);
  }
  numbers.forEach((value) => {
    if (value === "…") {
      const ellipsis = document.createElement("span");
      ellipsis.className = "job-page-ellipsis";
      ellipsis.textContent = value;
      root.append(ellipsis);
    } else addButton(String(value), value, false, value === page);
  });
  addButton(t("jobNext"), page + 1, page >= totalPages);
}

function renderJobHistoryPagination() {
  const pagination = $("#job-history-pagination");
  if (!pagination) return;
  const total = state.jobHistoryTotal;
  const totalPages = state.jobHistoryTotalPages;
  pagination.hidden = total === 0 && !historyHasFilters();
  const first = total ? (state.jobHistoryPage - 1) * state.jobHistoryPageSize + 1 : 0;
  const last = total ? Math.min(state.jobHistoryPage * state.jobHistoryPageSize, total) : 0;
  $("#job-history-page-summary").textContent = t("jobPageSummary", { from: first, to: last, total });
  renderPageButtons($("#job-page-buttons"), state.jobHistoryPage, totalPages, (page) => {
    state.jobHistoryPage = page;
    loadJobs({ force: true }).catch((error) => toast(error.message, true));
  });
}

function applyJobHistoryPayload(payload) {
  const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
  if (payload.page) {
    state.jobHistoryPage = Number(payload.page);
    state.jobHistoryPageSize = Number(payload.pageSize || state.jobHistoryPageSize);
    state.jobHistoryTotal = Number(payload.total || 0);
    state.jobHistoryTotalPages = Number(payload.totalPages || 1);
    state.jobHistoryStatusCounts = payload.statusCounts || state.jobHistoryStatusCounts;
    return;
  }
  const page = legacyJobHistoryPage(jobs, {
    filter: state.jobHistoryFilter,
    page: state.jobHistoryPage,
    search: $("#job-history-search"),
    preset: $("#job-history-preset"),
    mod: $("#job-history-mod"),
    from: $("#job-history-from"),
    to: $("#job-history-to")
  });
  state.jobs = page.jobs;
  state.jobHistoryPage = page.page;
  state.jobHistoryPageSize = page.pageSize;
  state.jobHistoryTotal = page.total;
  state.jobHistoryTotalPages = page.totalPages;
  state.jobHistoryStatusCounts = page.statusCounts;
}

function renderJobHistory() {
  const history = $("#job-history");
  const jobs = state.jobs;
  const signature = JSON.stringify([jobs, state.language, state.activeJobId, state.jobHistoryPage,
    state.jobHistoryFilter, state.jobHistoryTotal, state.jobHistoryStatusCounts, historyHasFilters()]);
  if (history.dataset.signature === signature && (!state.jobHistoryLoading || jobs.length)) return;
  if (!state.jobHistoryLoading) history.dataset.signature = signature;
  const modOptions = $("#job-mod-options");
  if (modOptions && state.catalog?.modVersions) {
    modOptions.replaceChildren(...state.catalog.modVersions.map((value) => {
      const option = document.createElement("option");
      option.value = value;
      return option;
    }));
  }
  $$("[data-job-filter]").forEach((button) => {
    const selected = button.dataset.jobFilter === state.jobHistoryFilter;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  for (const key of ["active", "succeeded", "failed"]) {
    const count = $(`#job-count-${key}`);
    if (count) count.textContent = String(state.jobHistoryStatusCounts[key] || 0);
  }
  if (state.jobHistoryLoading && !state.jobs.length) {
    history.hidden = false;
    $("#job-empty").hidden = true;
    const loading = document.createElement("p");
    loading.className = "job-filter-empty";
    loading.setAttribute("role", "status");
    loading.textContent = t("jobHistoryLoading");
    history.replaceChildren(loading);
    $("#job-history-pagination").hidden = true;
    return;
  }
  $("#job-history-count").textContent = String(state.jobHistoryTotal);
  const statusTotal = Object.values(state.jobHistoryStatusCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  const noJobs = state.jobHistoryTotal === 0 && !historyHasFilters() && statusTotal === 0;
  $("#job-empty").hidden = !noJobs;
  history.hidden = noJobs;
  const shownJobs = jobs;
  const fragments = [];
  let lastDay = "";
  for (const job of shownJobs) {
    const metadata = jobMetadata(job);
    const deviceLabel = jobDeviceLabel(job);
    const dayLabel = jobHistoryDayLabel(job);
    if (dayLabel && dayLabel !== lastDay) {
      const divider = document.createElement("div");
      divider.className = "job-history-divider";
      divider.setAttribute("role", "separator");
      divider.innerHTML = `<span></span><small></small><span></span>`;
      divider.querySelector("small").textContent = dayLabel;
      fragments.push(divider);
      lastDay = dayLabel;
    }
    const card = document.createElement("button"); card.type = "button"; card.className = "job-history-card";
    if ((job.job_id || job.jobId) === state.activeJobId) card.classList.add("selected");
    const header = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = metadata.version || job.recipe?.device || "ROM build";
    const status = document.createElement("span"); status.className = `job-status ${job.status}`; status.textContent = statusLabel(job.status);
    header.append(title, status);
    const build = job.recipe?.build || {};
    const details = document.createElement("p");
    const detailParts = [deviceLabel || job.recipe?.device || "—", build.modVersion || "—", build.modReleaseVersion || "—", `${jobProgress(job)}%`];
    details.textContent = detailParts.join(" · ");
    const footer = document.createElement("small"); footer.textContent = `${String(job.job_id || job.jobId).slice(0, 12)} · ${formatDate(job.created_at || job.createdAt)}`;
    card.append(header, details, footer);
    const badges = document.createElement("div"); badges.className = "job-card-badges";
    const editionBadge = jobEditionBadge(job);
    const modBadge = jobModBadge(job);
    if (editionBadge || modBadge) badges.append(...(editionBadge ? [editionBadge] : []), ...(modBadge ? [modBadge] : []));
    if (badges.children.length) card.append(badges);
    if (state.me?.role === "admin" && job.createdBy) {
      const creator = document.createElement("p"); creator.className = "job-history-creator";
      creator.textContent = `${job.createdBy.displayName || job.createdBy.username || job.createdBy.telegramId} · ID ${job.createdBy.telegramId}`;
      card.append(creator);
    }
    card.addEventListener("click", () => {
      openJob(job);
    });
    fragments.push(card);
  }
  if (!fragments.length && !noJobs) {
    const empty = document.createElement("p");
    empty.className = "job-filter-empty";
    empty.textContent = t("jobFilterEmpty");
    history.replaceChildren(empty);
  } else history.replaceChildren(...fragments);
  renderJobHistoryPagination();
}

function setJobsConnection(key, error = false) {
  const node = $("#jobs-connection"); if (!node) return;
  node.classList.toggle("error", error); node.classList.toggle("online", !error);
  node.querySelector("span").textContent = t(key) + (state.lastSyncedAt ? ` · ${t("syncSnapshot", { time: formatDate(state.lastSyncedAt) })}` : "");
}

async function loadLogPage(jobId, events, direction, inspection = null) {
  const parameter = direction === "previous" ? `before=${Number(events[0]?.sequence || 1)}` : `after=${eventCursor(events)}`;
  const payload = await apiRequest(`/v1/sync?includeHistory=0&jobId=${encodeURIComponent(jobId)}&${parameter}`, { signal: requestScopes.start(inspection ? "adminJob" : "jobDetail") });
  if (inspection ? state.adminJobView !== inspection : state.activeJobId !== jobId) return;
  const page = mergeEvents([], payload.events || []);
  (inspection || state).historicalLogPage = direction === "previous" || Boolean(payload.eventsHasMore);
  if (inspection) { inspection.events = page; inspection.jobEventsHasMore = payload.eventsHasMore; }
  else { state.activeEvents = page; state.activeEventsJobId = jobId; state.jobEventsHasMore = payload.eventsHasMore; }
  renderActiveJob(payload.activeJob, page, inspection);
}

async function loadJobDetail(jobId) {
  if (!jobId) return;
  requestScopes.cancel("jobs");
  const requestId = ++state.jobDetailRequestId;
  const sameJob = state.activeEventsJobId === jobId;
  const after = sameJob
    ? state.activeEvents.reduce((maximum, event) => Math.max(maximum, Number(event.sequence || 0)), 0)
    : 0;
  const encodedJobId = encodeURIComponent(jobId);
  const signal = requestScopes.start("jobDetail");
  const eventPayload = state.historicalLogPage && sameJob
    ? { activeJob: await apiRequest(`/v1/jobs/${encodedJobId}`, { signal }), events: [], eventsHasMore: state.jobEventsHasMore }
    : await apiRequest(`/v1/sync?includeHistory=0&jobId=${encodedJobId}&after=${after}`, { signal });
  const job = eventPayload.activeJob;
  if (requestId !== state.jobDetailRequestId || state.activeJobId !== jobId) return;
  if (!job || (job.job_id || job.jobId) !== jobId) throw new Error(t("jobUnavailable"));
  const incoming = Array.isArray(eventPayload?.events) ? eventPayload.events : [];
  state.jobEventsHasMore = eventPayload.eventsHasMore ?? incoming.length >= 500;
  state.activeEvents = mergeEvents(sameJob ? state.activeEvents : [], incoming);
  state.activeEventsJobId = jobId;
  const index = state.jobs.findIndex((item) => (item.job_id || item.jobId) === jobId);
  if (index >= 0 && job) state.jobs[index] = job;
  renderActiveJob(job, state.activeEvents); renderJobHistory();
}

function scheduleJobsPoll(active, changed = false) {
  clearTimeout(state.jobsPollTimer);
  if (document.hidden || !privateApiAvailable() || state.adminJobView) return;
  if (changed) state.jobsUnchangedPolls = 0;
  else state.jobsUnchangedPolls += 1;
  const delay = !active
    ? 30000
    : state.jobsUnchangedPolls >= 6
      ? 30000
      : state.jobsUnchangedPolls >= 3
        ? 15000
        : 10000;
  state.jobsPollTimer = setTimeout(() => {
    const selectedJobId = state.activeJobId;
    if (document.body.dataset.view === "jobs" && selectedJobId) {
      loadJobDetail(selectedJobId)
        .then(() => {
          state.lastSyncedAt = new Date().toISOString();
    setJobsConnection("jobsConnected");
          const selectedJob = state.jobs.find((job) => (job.job_id || job.jobId) === selectedJobId);
          scheduleJobsPoll(jobShouldPoll(selectedJob), false);
        })
        .catch(() => {
          setJobsConnection("jobsOffline", true);
          scheduleJobsPoll(true, false);
        });
      return;
    }
    loadJobs().catch(() => {});
  }, delay);
}

async function loadJobs({ force = false } = {}) {
  if (document.hidden) return;
  if (state.adminJobView) return;
  if (state.jobsLoading && !force) return;
  requestScopes.cancel("jobDetail");
  if (!privateApiAvailable()) { setJobsConnection(state.me ? "quotaRequiredHint" : miniApiUnavailableMessageKey(), true); return; }
  state.jobsLoading = true;
  state.jobHistoryLoading = true;
  $("#job-history")?.setAttribute("aria-busy", "true");
  renderJobHistory();
  const historyRequestId = ++state.jobHistoryRequestId;
  try {
    const requestedId = state.activeJobId;
    const selectionVersion = ++state.jobDetailRequestId;
    const sameJob = state.activeEventsJobId === requestedId;
    const after = sameJob
      ? state.activeEvents.reduce((maximum, event) => Math.max(maximum, Number(event.sequence || 0)), 0)
      : 0;
    const params = jobHistoryParams({ jobId: requestedId, after });
    const payload = await apiRequest(`/v1/sync?${params.toString()}`, { signal: requestScopes.start("jobs") });
    if (historyRequestId !== state.jobHistoryRequestId || selectionVersion !== state.jobDetailRequestId || requestedId !== state.activeJobId) return;
    state.maintenance = payload.maintenance || state.maintenance;
    renderAccount();
    state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
    applyJobHistoryPayload(payload);
    state.jobHistoryLoading = false;
    if (!requestedId && state.jobHistoryFilter === "active" && state.jobHistoryTotal === 0) {
      const fallbackFilter = state.jobHistoryStatusCounts.succeeded > 0 ? "succeeded" : state.jobHistoryStatusCounts.failed > 0 ? "failed" : "";
      if (fallbackFilter) {
        state.jobHistoryFilter = fallbackFilter;
        state.jobHistoryPage = 1;
        return loadJobs({ force: true });
      }
    }
    const selectedFromServer = payload.activeJob
      && (payload.activeJob.job_id || payload.activeJob.jobId) === state.activeJobId;
    const running = (payload.activeJob && !terminalJobStatuses.has(payload.activeJob.status))
      ? payload.activeJob
      : state.jobs.find((job) => !terminalJobStatuses.has(job.status));
    const selectedExists = Boolean(selectedFromServer)
      || state.jobs.some((job) => (job.job_id || job.jobId) === state.activeJobId);
    if (requestedId && !selectedExists) throw new Error(t("jobUnavailable"));
    if (!selectedExists) state.activeJobId = (running?.job_id || running?.jobId) || state.jobs[0]?.job_id || state.jobs[0]?.jobId || "";
    if (state.activeJobId) localStorage.setItem("wukong-active-job", state.activeJobId);
    else localStorage.removeItem("wukong-active-job");
    const activeJob = payload.activeJob
      && (payload.activeJob.job_id || payload.activeJob.jobId) === state.activeJobId
      ? payload.activeJob
      : state.jobs.find((job) => (job.job_id || job.jobId) === state.activeJobId) || null;
    const eventsSameJob = state.activeEventsJobId === state.activeJobId;
    const responseId = payload.activeJob?.job_id || payload.activeJob?.jobId;
    const incoming = responseId === state.activeJobId && Array.isArray(payload.events) ? payload.events : [];
    if (!state.historicalLogPage || !eventsSameJob) {
      state.jobEventsHasMore = payload.eventsHasMore ?? incoming.length >= 500;
      state.activeEvents = mergeEvents(eventsSameJob ? state.activeEvents : [], incoming);
    }
    state.activeEventsJobId = state.activeJobId;
    const nextSignature = JSON.stringify({
      jobs: state.jobs.map((job) => [
        job.job_id || job.jobId,
        job.status,
        job.stage,
        job.progress,
        job.updated_at || job.updatedAt,
        (Array.isArray(job.artifacts) ? job.artifacts : []).map((artifact) =>
          (Array.isArray(artifact?.mirrors) ? artifact.mirrors : [])
            .filter((mirror) => String(mirror?.provider || "").toLowerCase() === "dccloud")
            .map((mirror) => String(mirror?.status || "").toLowerCase())
        )
      ]),
      active: state.activeJobId,
      sequence: state.activeEvents.reduce(
        (maximum, event) => Math.max(maximum, Number(event.sequence || 0)),
        0
      )
    });
    const changed = nextSignature !== state.jobsSyncSignature;
    state.jobsSyncSignature = nextSignature;
    if (changed) { renderJobHistory(); renderActiveJob(activeJob, state.activeEvents); }
    state.lastSyncedAt = payload.serverTime || new Date().toISOString();
    setJobsConnection("jobsConnected");
    scheduleJobsPoll(jobShouldPoll(activeJob || running), changed);
  } catch (error) {
    if (error.name === "AbortError" || historyRequestId !== state.jobHistoryRequestId) return;
    setJobsConnection("jobsOffline", true); scheduleJobsPoll(true, false); throw error;
  } finally {
    if (historyRequestId === state.jobHistoryRequestId) {
      state.jobsLoading = false;
      state.jobHistoryLoading = false;
      $("#job-history")?.setAttribute("aria-busy", "false");
      renderJobHistory();
    }
  }
}

async function runJobAction(action, jobId) {
  const job = await apiRequest(`/v1/jobs/${encodeURIComponent(jobId)}/${action}`, { method: "POST" });
  state.activeJobId = job.job_id || job.jobId; localStorage.setItem("wukong-active-job", state.activeJobId);
  await loadJobs({ force: true });
}

export { renderSelectedJob, jobNeedsMirrorPoll, jobShouldPoll, readableEventType, readableEventStage, readableStep, readableStepStatus, uploadProgressSnapshot, uploadProgressKey, compactLiveEvents, eventTitle, formatEventValue, eventDetailEntries, renderUploadProgressCard, statusLabel, jobMetadata, jobDeviceLabel, jobEditionBadge, jobHistoryDayLabel, catalogDeviceName, jobProgress, jobModBadge, formatDate, formatElapsed, jobFact, artifactCloudUrl, artifactMirrorUrl, repairDcCloudMirror, dcCloudDownloadUrl, downloadDcCloudMirror, copyDcCloudMirrorLink, artifactProvider, openArtifactUrl, renderArtifacts, renderEvents, jobAction, openAdminJobPage, closeAdminJobPage, loadAdminJobDetail, openJob, renderJobParameters, renderActiveJob, historyDateBoundary, appendJobHistoryFilters, jobHistoryParams, historyHasFilters, legacyJobHistoryPage, renderPageButtons, renderJobHistoryPagination, applyJobHistoryPayload, renderJobHistory, setJobsConnection, loadLogPage, loadJobDetail, scheduleJobsPoll, loadJobs, runJobAction };

import { $, $$, requestScopes, state, t } from "./state.js";
import { catalogDeviceName, closeAdminJobPage, formatDate, openAdminJobPage } from "./jobs.js";
import { presetLabel } from "./build.js";
import { prefersReducedMotion } from "./dock.js";

function profileInitials(profile) {
  const label = String(profile?.displayName || profile?.username || profile?.telegramId || "WK").trim();
  const parts = label.split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)[0]}` : label.slice(0, 2)).toUpperCase();
}

function profileAvatar(profile, className = "") {
  const root = document.createElement("div");
  root.className = `profile-avatar ${className}`.trim();
  const fallback = document.createElement("span");
  fallback.textContent = profileInitials(profile);
  root.append(fallback);
  if (profile?.photoUrl) {
    const image = document.createElement("img");
    image.src = profile.photoUrl;
    image.alt = "";
    image.referrerPolicy = "no-referrer";
    image.addEventListener("error", () => image.remove(), { once: true });
    root.prepend(image);
  }
  const hue = [...String(profile?.telegramId || "wukong")].reduce((total, char) => total + char.charCodeAt(0), 0) % 360;
  root.style.setProperty("--avatar-hue", String(hue));
  return root;
}

function renderProfileTrigger(button, profile) {
  if (!button) return;
  button.hidden = !profile;
  if (!profile) return;
  const avatar = profileAvatar(profile);
  button.replaceChildren(...avatar.childNodes);
  button.style.setProperty("--avatar-hue", avatar.style.getPropertyValue("--avatar-hue"));
  if (profile.photoUrl) button.style.setProperty("--avatar-image", `url(${JSON.stringify(String(profile.photoUrl))})`);
  else button.style.removeProperty("--avatar-image");
  button.setAttribute("aria-label", t("openProfile"));
}

function profileValue(key, profile) {
  const values = {
    telegramId: profile.telegramId,
    username: profile.username ? `@${profile.username}` : "—",
    displayName: profile.displayName || "—",
    accessStatus: accessLabel(profile.accessStatus),
    role: t(profile.role === "admin" ? "roleAdmin" : "roleUser"),
    buildCredits: profile.unlimited ? t("unlimited") : String(profile.buildCredits || 0),
    unlimited: profile.unlimited ? t("yes") : t("no"),
    lifetimeGranted: String(profile.lifetimeGranted || 0),
    lifetimeUsed: String(profile.lifetimeUsed || 0),
    jobCount: String(profile.jobCount || 0),
    firstSeenAt: formatDate(profile.firstSeenAt),
    lastSeenAt: formatDate(profile.lastSeenAt),
    lastJobId: profile.lastJobId || "—",
    lastJobStatus: profile.lastJobStatus || "—",
    language: String(profile.language || "—").toUpperCase(),
    platform: profile.platform || "—",
    appVersion: profile.appVersion || "—",
    approvedAt: formatDate(profile.approvedAt),
    revokedAt: formatDate(profile.revokedAt),
    accessActor: profile.accessActor || "—",
    accessReason: profile.accessReason || "—",
    configuredAdmin: profile.configuredAdmin ? t("configuredAdminYes") : t("configuredAdminNo")
  };
  return values[key] ?? "—";
}

function profileLabel(key) {
  const labels = {
    telegramId: "Telegram ID", username: "Username", displayName: t("displayName"),
    accessStatus: t("profileStatus"), role: t("role"), buildCredits: t("allowance"),
    unlimited: t("unlimitedLabel"), lifetimeGranted: t("lifetimeGrantedLabel"), lifetimeUsed: t("lifetimeUsedLabel"),
    jobCount: t("jobCount"), firstSeenAt: t("firstAccess"), lastSeenAt: t("lastAccess"),
    lastJobId: t("lastJob"), lastJobStatus: t("lastJobStatusLabel"), language: t("languageLabel"),
    platform: t("platformLabel"), appVersion: t("appVersionLabel"), approvedAt: t("approvedAt"),
    revokedAt: t("revokedAt"), accessActor: t("accessActor"), accessReason: t("accessReason"),
    configuredAdmin: t("profileConfiguredAdmin")
  };
  return labels[key] || key;
}

function profileFact(key, profile) {
  const fact = document.createElement("div");
  fact.className = "profile-fact";
  const label = document.createElement("small");
  label.textContent = profileLabel(key);
  const value = document.createElement("strong");
  value.textContent = profileValue(key, profile);
  fact.append(label, value);
  return fact;
}

function profileGroup(titleKey, keys, profile) {
  const section = document.createElement("section");
  section.className = "profile-fact-group";
  const title = document.createElement("h2");
  title.textContent = t(titleKey);
  const facts = document.createElement("div");
  facts.className = "profile-fact-list";
  facts.append(...keys.map((key) => profileFact(key, profile)));
  section.append(title, facts);
  return section;
}

function profileHighlight(label, value, tone) {
  const node = document.createElement("div");
  node.className = `profile-highlight ${tone}`;
  const small = document.createElement("small");
  small.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  node.append(small, strong);
  return node;
}

function renderProfileView() {
  const profile = state.me;
  if (!profile) return;
  const avatarRoot = $("#profile-view-avatar");
  const avatar = profileAvatar(profile, "profile-avatar-hero");
  avatar.id = "profile-view-avatar";
  avatarRoot?.replaceWith(avatar);
  $("#profile-view-name").textContent = profile.displayName || profile.username || profile.telegramId;
  $("#profile-view-handle").textContent = profile.username ? `@${profile.username} · ${profile.telegramId}` : profile.telegramId;
  const scene = $("#profile-scene");
  scene?.style.setProperty("--profile-image", profile.photoUrl ? `url("${String(profile.photoUrl).replaceAll('"', '\\"')}")` : "none");
  scene?.style.setProperty("--avatar-hue", avatar.style.getPropertyValue("--avatar-hue"));

  const badgeRoot = $("#profile-view-badges");
  const access = document.createElement("span");
  access.className = `profile-badge ${profile.accessStatus || "pending"}`;
  access.textContent = accessLabel(profile.accessStatus);
  const role = document.createElement("span");
  role.className = "profile-badge";
  role.textContent = t(profile.role === "admin" ? "roleAdmin" : "roleUser");
  badgeRoot?.replaceChildren(access, role);

  $("#profile-highlights")?.replaceChildren(
    profileHighlight(t("profileBuilds"), profile.unlimited ? "∞" : String(profile.buildCredits || 0), "builds"),
    profileHighlight(t("profileJobs"), String(profile.jobCount || 0), "jobs"),
    profileHighlight(t("profileAccess"), accessLabel(profile.accessStatus), "access")
  );

  const groups = [
    ["profileIdentityGroup", ["telegramId", "username", "displayName", "role"]],
    ["profileAccessGroup", ["accessStatus", "buildCredits", "unlimited", "lifetimeGranted", "lifetimeUsed", "configuredAdmin"]],
    ["profileActivityGroup", ["jobCount", "firstSeenAt", "lastSeenAt", "lastJobId", "lastJobStatus", "approvedAt", "revokedAt"]],
    ["profileClientGroup", ["language", "platform", "appVersion", "accessActor", "accessReason"]]
  ];
  const grouped = new Set(groups.flatMap(([, keys]) => keys));
  const extra = Object.keys(profile).filter((key) => !grouped.has(key) && !["miniAppOpenCount", "photoUrl"].includes(key));
  const nodes = groups
    .map(([title, keys]) => profileGroup(title, keys.filter((key) => key in profile), profile))
    .filter((group) => group.querySelector(".profile-fact"));
  if (extra.length) nodes.push(profileGroup("profileMoreGroup", extra, profile));
  $("#profile-detail-grid")?.replaceChildren(...nodes);
}

function accessLabel(status) { return t(["pending", "approved", "revoked"].includes(status) ? status : "pending"); }

function currentActivityTitle(activity) {
  if (activity?.type === "build") return t("userBuildingRom");
  if (activity?.status === "searching") return t("userSearchingRom");
  if (activity?.status === "completed") return t("userRomSearchCompleted", { count: Number(activity.resultCount || 0) });
  return t("userRomSearchFailed");
}

function currentActivityLines(activity) {
  if (!activity) return [];
  if (activity.type === "build") {
    const device = activity.deviceName || catalogDeviceName(activity.productCode) || activity.productCode;
    return [
      [device, activity.productCode].filter(Boolean).join(" · "),
      [activity.preset ? presetLabel(activity.preset, activity.editionLabels) : "", activity.modVersion].filter(Boolean).join(" · "),
      [activity.releaseVersion, `${Math.round(Number(activity.progress || 0) * 100)}%`, activity.stage].filter(Boolean).join(" · ")
    ].filter(Boolean);
  }
  const firstResult = Array.isArray(activity.results) ? activity.results[0] || {} : {};
  return [
    [activity.device || activity.model, activity.region].filter(Boolean).join(" · "),
    activity.latest ? t("romLatestOnly") : t("romAllVersions"),
    activity.status === "completed" ? firstResult.version || activity.version || "" : ""
  ].filter(Boolean);
}

function renderCurrentActivitySummary(user, compact = false) {
  const activities = Array.isArray(user.currentActivities) && user.currentActivities.length
    ? user.currentActivities
    : user.currentActivity ? [user.currentActivity] : [];
  const group = document.createElement(compact ? "span" : "section");
  group.className = "user-current-activities";
  if (!activities.length) {
    const section = document.createElement("span");
    section.className = "user-current-activity idle";
    const title = document.createElement("strong"); title.textContent = compact ? t("openCount", { count: user.miniAppOpenCount || 0 }) : t("noCurrentUserActivity");
    const detail = document.createElement("small"); detail.textContent = compact ? `${t("lastAccess")}: ${formatDate(user.lastSeenAt)}` : "";
    section.append(title, detail);
    group.append(section);
    return group;
  }
  activities.forEach((activity) => {
    const section = document.createElement("span");
  section.className = `user-current-activity ${activity?.type || "idle"} ${activity?.status || ""}`;
    const title = document.createElement("strong"); title.textContent = currentActivityTitle(activity);
    const status = document.createElement("i"); status.setAttribute("aria-hidden", "true");
    const heading = document.createElement("span"); heading.append(status, title);
    section.append(heading);
    currentActivityLines(activity).slice(0, 3).forEach((value) => {
      const line = document.createElement("small"); line.textContent = value; section.append(line);
    });
    if (!compact && activity.type === "build" && activity.jobId) {
      const open = document.createElement("button"); open.type = "button"; open.className = "secondary";
      open.textContent = t("openUserJob");
      open.addEventListener("click", () => openAdminJobPage({
        job_id: activity.jobId,
        status: activity.status,
        stage: activity.stage,
        progress: activity.progress,
        createdBy: user,
        recipe: {
          device: activity.productCode,
          build: {
            preset: activity.preset,
            modVersion: activity.modVersion,
            modReleaseVersion: activity.releaseVersion,
            editionLabels: activity.editionLabels || {}
          }
        }
      }));
      section.append(open);
    }
    group.append(section);
  });
  return group;
}

function detailFact(label, value) {
  const box = document.createElement("div"); const small = document.createElement("small"); const strong = document.createElement("strong");
  small.textContent = label; strong.textContent = value || "—"; box.append(small, strong); return box;
}

function closeAdminUserPage({ restoreFocus = true, scroll = true } = {}) {
  requestScopes.cancel("adminUser");
  requestScopes.cancel("adminActivity");
  closeAdminJobPage({ restoreFocus: false, scroll: false, refreshUser: false });
  clearTimeout(state.adminUserPollTimer);
  state.adminUserPollTimer = null;
  const system = $("#system");
  const page = $("#admin-user-page");
  if (!system || !page) return;
  const telegramId = state.selectedAdminUserId;
  system.classList.remove("admin-user-open");
  page.hidden = true;
  state.selectedAdminUserId = "";
  state.adminUserEventCursor = { createdAt: "1970-01-01T00:00:00.000Z", eventId: "" };
  if (scroll) window.scrollTo({ top: state.adminUserReturnScrollY, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  if (restoreFocus && telegramId) {
    requestAnimationFrame(() => $$(".user-open").find((button) => button.dataset.userId === String(telegramId))?.focus());
  }
}

export { profileInitials, profileAvatar, renderProfileTrigger, profileValue, profileLabel, profileFact, profileGroup, profileHighlight, renderProfileView, accessLabel, currentActivityTitle, currentActivityLines, renderCurrentActivitySummary, detailFact, closeAdminUserPage };

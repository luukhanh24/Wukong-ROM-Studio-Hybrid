import type { AuthenticatedRequest } from "./auth";
import type { TelegramProfile } from "./state";
import { catalogPayload } from "./catalog";
import { presetEditionLabel } from "./artifact-metadata";

type JsonObject = Record<string, unknown>;
type ActivityActor = AuthenticatedRequest | {
  subject: string;
  displayName?: string;
  username?: string;
};

export interface CurrentUserActivity extends JsonObject {
  type: "build" | "rom_search";
  status: string;
  startedAt: string;
  updatedAt: string;
}

export interface RomSearchTrace {
  searchId: string;
  subject: string;
  startedAt: string;
  query: JsonObject;
}

export interface ActivityProfileExtension {
  currentActivity: CurrentUserActivity | null;
  currentActivities: CurrentUserActivity[];
}

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function parseObject(value: unknown): JsonObject {
  try {
    return object(JSON.parse(String(value ?? "{}")));
  } catch {
    return {};
  }
}

function html(value: unknown, fallback = "—", limit = 240): string {
  return (String(value ?? "").trim() || fallback).slice(0, limit)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function adminSubjects(env: Env, actorSubject: string): string[] {
  return [...new Set(env.WUKONG_TELEGRAM_ADMIN_IDS
    .split(",")
    .map((value) => value.trim())
    .filter((value) => /^[1-9][0-9]*$/.test(value) && value !== actorSubject))];
}

function adminNotificationStatements(
  env: Env,
  actorSubject: string,
  dedupePrefix: string,
  payload: JsonObject,
  now: string
): D1PreparedStatement[] {
  return adminSubjects(env, actorSubject).map((adminSubject) => env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
     (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    `${dedupePrefix}:${adminSubject}`,
    adminSubject,
    JSON.stringify(payload),
    now,
    now
  ));
}

function actorLines(actor: ActivityActor): string[] {
  const profile = "profile" in actor ? actor.profile : actor;
  return [
    `User  <b>${html(profile.displayName || profile.username || actor.subject)}</b>`,
    `Telegram  <code>${html(actor.subject, "—", 32)}</code>${profile.username ? ` · @${html(profile.username, "—", 64)}` : ""}`
  ];
}

const DEVICE_NAMES = (() => {
  const catalogDevices = catalogPayload().devices;
  const devices: unknown[] = Array.isArray(catalogDevices)
    ? catalogDevices as unknown[]
    : [];
  const names = new Map<string, string>();
  devices.forEach((value) => {
    const device = object(value);
    const product = String(device.product ?? "").trim().toUpperCase();
    const name = String(device.name ?? "").trim();
    if (product && name) names.set(product, name);
  });
  return names;
})();

function friendlyDeviceName(productCode: unknown, fallback: unknown): string {
  const product = String(productCode ?? "").trim().toUpperCase();
  return DEVICE_NAMES.get(product) ?? String(fallback ?? "").trim();
}

export function buildStartedAdminStatements(
  env: Env,
  actor: ActivityActor,
  jobId: string,
  recipe: JsonObject,
  now: string,
  resumedFromJobId = "",
  requiredDispatchedRunId?: number
): D1PreparedStatement[] {
  const source = object(recipe.source);
  const metadata = object(source.metadata);
  const build = object(recipe.build);
  const lines = [
    "<b>Wukong ROM Studio · Hoạt động user</b>",
    `<b>${resumedFromJobId ? "Tiếp tục build ROM" : "Bắt đầu build ROM"}</b>`,
    "",
    ...actorLines(actor),
    "",
    "<b>Thông tin build</b>",
    `Job  <code>${html(jobId, "—", 64)}</code>`,
    `Tên thiết bị  <code>${html(friendlyDeviceName(recipe.device, metadata.device ?? metadata.deviceName))}</code>`,
    `Mã sản phẩm  <code>${html(recipe.device)}</code>`,
    `Bản build  <code>${html(presetEditionLabel(build.preset, build.editionLabels ?? build.edition_labels))}</code>`,
    `MOD pack  <code>${html(build.modVersion ?? build.mod_version)}</code>`,
    `Phát hành  <code>${html(build.modReleaseVersion ?? build.mod_release_version)}</code>`,
    `Phiên bản ROM  <code>${html(metadata.version)}</code>`,
    resumedFromJobId ? `Tiếp tục từ  <code>${html(resumedFromJobId, "—", 64)}</code>` : ""
  ].filter(Boolean);
  const payload: JsonObject = {
    text: lines.join("\n"),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    ...(env.WUKONG_TELEGRAM_WEB_APP_URL.startsWith("https://") ? {
      reply_markup: { inline_keyboard: [[{
        text: "Mở Wukong Mini App",
        web_app: { url: env.WUKONG_TELEGRAM_WEB_APP_URL }
      }]] }
    } : {})
  };
  if (requiredDispatchedRunId === undefined) {
    return adminNotificationStatements(
      env,
      actor.subject,
      `admin-activity:build:${jobId}`,
      payload,
      now
    );
  }
  return adminSubjects(env, actor.subject).map((adminSubject) => env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
     (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
     SELECT ?, ?, ?, ?, ?, ?
     WHERE EXISTS (
       SELECT 1 FROM wukong_jobs
       WHERE job_id = ? AND status = 'dispatched' AND github_run_id = ?
     )`
  ).bind(
    crypto.randomUUID(),
    `admin-activity:build:${jobId}:${adminSubject}`,
    adminSubject,
    JSON.stringify(payload),
    now,
    now,
    jobId,
    requiredDispatchedRunId
  ));
}

function romSearchQuery(request: Request): JsonObject {
  const search = new URL(request.url).searchParams;
  const value = (name: string, limit = 128) => (search.get(name) ?? "").trim().slice(0, limit);
  return {
    device: value("device"),
    model: value("model"),
    region: value("region", 64).toUpperCase(),
    latest: value("latest", 1) !== "0",
    since: value("since", 64)
  };
}

function romSearchDetails(trace: RomSearchTrace, extra: JsonObject = {}): JsonObject {
  return {
    searchId: trace.searchId,
    startedAt: trace.startedAt,
    ...trace.query,
    ...extra
  };
}

async function activityKey(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest).slice(0, 16)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function createRomSearchTrace(
  auth: AuthenticatedRequest,
  request: Request
): Promise<RomSearchTrace> {
  const query = romSearchQuery(request);
  const cooldownBucket = Math.floor(Date.now() / 30_000);
  return {
    searchId: `rom-search-${await activityKey(`${auth.subject}:${cooldownBucket}:${JSON.stringify(query)}`)}`,
    subject: auth.subject,
    startedAt: new Date().toISOString(),
    query
  };
}

export async function recordRomSearchStart(
  env: Env,
  auth: AuthenticatedRequest,
  trace: RomSearchTrace
): Promise<void> {
  const lines = [
    "<b>Wukong ROM Studio · Hoạt động user</b>",
    "<b>Đang tìm ROM nguồn</b>",
    "",
    ...actorLines(auth),
    "",
    "<b>Bộ lọc</b>",
    trace.query.device ? `Thiết bị  <code>${html(trace.query.device)}</code>` : "",
    trace.query.model ? `Mã model  <code>${html(trace.query.model)}</code>` : "",
    trace.query.region ? `Khu vực  <code>${html(trace.query.region)}</code>` : "",
    `Phiên bản  <code>${trace.query.latest ? "Mới nhất" : "Toàn bộ lịch sử"}</code>`
  ].filter(Boolean);
  await env.DB.batch([
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_telegram_user_events
       (event_id, subject, event_type, details_json, created_at)
       VALUES (?, ?, 'rom_search_started', ?, ?)`
    ).bind(
      trace.searchId,
      auth.subject,
      JSON.stringify(romSearchDetails(trace)),
      trace.startedAt
    ),
    ...adminNotificationStatements(
      env,
      auth.subject,
      `admin-activity:rom-search:${trace.searchId}`,
      {
        text: lines.join("\n"),
        parse_mode: "HTML",
        disable_web_page_preview: true
      },
      trace.startedAt
    )
  ]);
}

function releaseSummary(value: unknown): JsonObject | null {
  const release = object(value);
  if (!Object.keys(release).length) return null;
  return {
    device: String(release.device ?? "").slice(0, 128),
    model: String(release.model ?? "").slice(0, 128),
    region: String(release.region ?? "").slice(0, 64),
    version: String(release.version ?? release.otaVersion ?? "").slice(0, 256),
    securityPatch: String(release.securityPatch ?? "").slice(0, 64),
    sizeBytes: Number.isFinite(Number(release.sizeBytes)) ? Number(release.sizeBytes) : null
  };
}

export async function completeRomSearch(
  env: Env,
  trace: RomSearchTrace,
  result: JsonObject
): Promise<void> {
  const finishedAt = new Date().toISOString();
  const releases = Array.isArray(result.releases) ? result.releases : [];
  const details = romSearchDetails(trace, {
    resultCount: releases.length,
    truncated: result.truncated === true,
    durationMs: Math.max(0, Date.parse(finishedAt) - Date.parse(trace.startedAt)),
    results: releases.slice(0, 8).map(releaseSummary).filter(Boolean)
  });
  await env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_telegram_user_events
     (event_id, subject, event_type, details_json, created_at)
     VALUES (?, ?, 'rom_search_completed', ?, ?)`
  ).bind(`${trace.searchId}:completed`, trace.subject, JSON.stringify(details), finishedAt).run();
}

export async function failRomSearch(
  env: Env,
  trace: RomSearchTrace,
  error: unknown
): Promise<void> {
  const finishedAt = new Date().toISOString();
  const status = Number(object(error).status ?? 0);
  const details = romSearchDetails(trace, {
    durationMs: Math.max(0, Date.parse(finishedAt) - Date.parse(trace.startedAt)),
    errorCode: status >= 400 && status < 500 ? "invalid_filters" : "source_unavailable",
    error: status >= 400 && status < 500
      ? "Bộ lọc tìm ROM không hợp lệ."
      : "Nguồn dữ liệu ROM tạm thời không khả dụng."
  });
  await env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_telegram_user_events
     (event_id, subject, event_type, details_json, created_at)
     VALUES (?, ?, 'rom_search_failed', ?, ?)`
  ).bind(`${trace.searchId}:failed`, trace.subject, JSON.stringify(details), finishedAt).run();
}

function buildActivity(row: Record<string, unknown>): CurrentUserActivity {
  const recipe = parseObject(row.recipe_json);
  const source = object(recipe.source);
  const metadata = object(source.metadata);
  const build = object(recipe.build);
  return {
    type: "build",
    status: String(row.status ?? ""),
    stage: String(row.stage ?? ""),
    progress: Math.max(0, Math.min(1, Number(row.progress ?? 0))),
    jobId: String(row.job_id ?? ""),
    deviceName: friendlyDeviceName(recipe.device, metadata.deviceName ?? metadata.device),
    detectedDevice: String(metadata.device ?? ""),
    productCode: String(recipe.device ?? ""),
    romVersion: String(metadata.version ?? ""),
    preset: String(build.preset ?? ""),
    editionLabels: object(build.editionLabels ?? build.edition_labels),
    modVersion: String(build.modVersion ?? build.mod_version ?? ""),
    releaseVersion: String(build.modReleaseVersion ?? build.mod_release_version ?? ""),
    startedAt: String(row.created_at ?? ""),
    updatedAt: String(row.updated_at ?? row.created_at ?? "")
  };
}

function romActivity(row: Record<string, unknown>): CurrentUserActivity {
  const details = parseObject(row.details_json);
  const eventType = String(row.event_type ?? "");
  return {
    type: "rom_search",
    status: eventType === "rom_search_started"
      ? "searching"
      : eventType === "rom_search_completed"
        ? "completed"
        : "failed",
    ...details,
    startedAt: eventType === "rom_search_started"
      ? String(row.created_at ?? "")
      : String(details.startedAt ?? row.created_at ?? ""),
    updatedAt: String(row.created_at ?? "")
  };
}

export async function attachCurrentActivities<T extends TelegramProfile>(
  env: Env,
  profiles: T[]
): Promise<Array<T & ActivityProfileExtension>> {
  if (!profiles.length) return [];
  const subjects = profiles.map((profile) => profile.telegramId);
  const placeholders = subjects.map(() => "?").join(",");
  const builds = await env.DB.prepare(
    `WITH ranked_builds AS (
       SELECT job_id, owner_subject, recipe_json, status, stage, progress, created_at, updated_at,
              ROW_NUMBER() OVER (PARTITION BY owner_subject ORDER BY created_at DESC, job_id DESC) AS row_number
       FROM wukong_jobs
       WHERE owner_channel = 'telegram' AND owner_subject IN (${placeholders})
         AND status NOT IN ('succeeded', 'failed', 'cancelled')
     )
     SELECT job_id, owner_subject, recipe_json, status, stage, progress, created_at, updated_at
     FROM ranked_builds WHERE row_number = 1`
  ).bind(...subjects).all<Record<string, unknown>>();
  const bySubject = new Map<string, CurrentUserActivity[]>();
  for (const row of builds.results) {
    const subject = String(row.owner_subject ?? "");
    bySubject.set(subject, [buildActivity(row)]);
  }
  const cutoff = new Date(Date.now() - 15 * 60 * 1000).toISOString();
  for (let start = 0; start < subjects.length; start += 99) {
    const chunk = subjects.slice(start, start + 99);
    const chunkPlaceholders = chunk.map(() => "?").join(",");
    const searches = await env.DB.prepare(
      `WITH ranked_searches AS (
         SELECT subject, event_type, details_json, created_at,
                ROW_NUMBER() OVER (PARTITION BY subject ORDER BY created_at DESC, event_id DESC) AS row_number
         FROM wukong_telegram_user_events
         WHERE subject IN (${chunkPlaceholders})
           AND event_type IN ('rom_search_started', 'rom_search_completed', 'rom_search_failed')
           AND created_at >= ?
       )
       SELECT subject, event_type, details_json, created_at
       FROM ranked_searches WHERE row_number = 1`
    ).bind(...chunk, cutoff).all<Record<string, unknown>>();
    for (const row of searches.results) {
      const subject = String(row.subject ?? "");
      const activities = bySubject.get(subject) ?? [];
      activities.push(romActivity(row));
      bySubject.set(subject, activities);
    }
  }
  return profiles.map((profile) => ({
    ...profile,
    currentActivity: bySubject.get(profile.telegramId)?.[0] ?? null,
    currentActivities: bySubject.get(profile.telegramId) ?? []
  }));
}

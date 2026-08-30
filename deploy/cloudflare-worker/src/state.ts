import { attachCurrentActivities, type ActivityProfileExtension } from "./activity";

export interface TelegramProfile {
  telegramId: string;
  username: string;
  displayName: string;
  photoUrl: string;
  accessStatus: "pending" | "approved" | "revoked";
  role: "admin" | "user";
  firstSeenAt: string;
  lastSeenAt: string;
  miniAppOpenCount: number;
  jobCount: number;
  buildCredits: number;
  unlimited: boolean;
  lifetimeGranted: number;
  lifetimeUsed: number;
  lastJobId: string;
  lastJobStatus: string;
  approvedAt: string;
  revokedAt: string;
  accessActor: string;
  accessReason: string;
  language: string;
  platform: string;
  appVersion: string;
  configuredAdmin: boolean;
}

const PROFILE_COLUMNS = `
  subject, username, display_name, photo_url, access_status, role,
  first_seen_at, last_seen_at, mini_app_open_count, job_count,
  build_credits, unlimited, lifetime_granted, lifetime_used,
  last_job_id, last_job_status, approved_at, revoked_at,
  access_actor, access_reason, language, platform, app_version,
  configured_admin
`;

function text(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

function integer(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isSafeInteger(parsed) ? parsed : 0;
}

export function profilePayload(row: Record<string, unknown> | null): TelegramProfile | null {
  if (!row) return null;
  return {
    telegramId: text(row.subject),
    username: text(row.username),
    displayName: text(row.display_name),
    photoUrl: text(row.photo_url),
    accessStatus: text(row.access_status) as TelegramProfile["accessStatus"],
    role: text(row.role) as TelegramProfile["role"],
    firstSeenAt: text(row.first_seen_at),
    lastSeenAt: text(row.last_seen_at),
    miniAppOpenCount: integer(row.mini_app_open_count),
    jobCount: integer(row.job_count),
    buildCredits: integer(row.build_credits),
    unlimited: Boolean(row.unlimited),
    lifetimeGranted: integer(row.lifetime_granted),
    lifetimeUsed: integer(row.lifetime_used),
    lastJobId: text(row.last_job_id),
    lastJobStatus: text(row.last_job_status),
    approvedAt: text(row.approved_at),
    revokedAt: text(row.revoked_at),
    accessActor: text(row.access_actor),
    accessReason: text(row.access_reason),
    language: text(row.language),
    platform: text(row.platform),
    appVersion: text(row.app_version),
    configuredAdmin: Boolean(row.configured_admin)
  };
}

function requireTelegramSubject(value: unknown): string {
  const subject = String(value ?? "").trim();
  if (!/^[1-9][0-9]*$/.test(subject)) throw new Error("Telegram user ID is required");
  return subject;
}

function eventStatement(
  env: Env,
  subject: string,
  eventType: string,
  now: string,
  options: {
    actor?: string;
    reason?: string;
    details?: Record<string, unknown>;
  } = {}
): D1PreparedStatement {
  return env.DB.prepare(
    `INSERT INTO wukong_telegram_user_events
     (event_id, subject, event_type, actor_subject, reason, details_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    subject,
    eventType,
    options.actor ?? "",
    (options.reason ?? "").slice(0, 1024),
    JSON.stringify(options.details ?? {}),
    now
  );
}

function notificationStatement(
  env: Env,
  subject: string,
  dedupeKey: string,
  textValue: string,
  now: string
): D1PreparedStatement {
  return env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
     (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    dedupeKey,
    subject,
    JSON.stringify({
      text: textValue,
      parse_mode: "HTML",
      disable_web_page_preview: true
    }),
    now,
    now
  );
}

function html(value: unknown): string {
  return text(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function accessRequestMessage(subject: string, displayName: string, username: string): string {
  const name = html(displayName || username || `Telegram User ${subject}`);
  const handle = username ? `@${html(username)}` : "—";
  return [
    "<b>🔐 YÊU CẦU CẤP QUYỀN MỚI</b>",
    "<i>Wukong ROM Studio</i>",
    "",
    `<b>${name}</b>`,
    `<i>Username</i>  ${handle}`,
    `<i>Telegram ID</i>  <code>${subject}</code>`,
    "",
    `<i>Hành động</i>  Gửi <code>/approve ${subject}</code> để cấp 1 lượt build.`
  ].join("\n");
}

export function configuredAdmins(env: Env): string[] {
  return env.WUKONG_TELEGRAM_ADMIN_IDS
    .split(",")
    .map((value) => value.trim())
    .filter((value) => /^[1-9][0-9]*$/.test(value));
}

export async function ensureConfiguredAdmins(env: Env): Promise<void> {
  const now = new Date().toISOString();
  for (const subject of configuredAdmins(env)) {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_telegram_users
          (subject, access_status, role, first_seen_at, last_seen_at, unlimited, configured_admin)
         VALUES (?, 'approved', 'admin', ?, ?, 1, 1)
         ON CONFLICT (subject) DO UPDATE SET
           access_status = 'approved',
           role = 'admin',
           build_credits = 0,
           unlimited = 1,
           configured_admin = 1`
      ).bind(subject, now, now),
      env.DB.prepare(
        `INSERT INTO wukong_telegram_access (subject, role)
         VALUES (?, 'admin')
         ON CONFLICT (subject) DO UPDATE SET role = 'admin'`
      ).bind(subject)
    ]);
  }
}

export async function profile(env: Env, subject: string): Promise<TelegramProfile | null> {
  const row = await env.DB.prepare(
    `SELECT ${PROFILE_COLUMNS} FROM wukong_telegram_users WHERE subject = ?`
  ).bind(subject).first<Record<string, unknown>>();
  return profilePayload(row);
}

function safePhotoUrl(value: unknown): string {
  const candidate = text(value).trim();
  if (!candidate || candidate.length > 2048) return "";
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password) return "";
    return candidate;
  } catch {
    return "";
  }
}

export interface ObservedTelegramUser {
  id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  language_code?: string;
  photo_url?: string;
}

export async function observeUser(
  env: Env,
  user: ObservedTelegramUser,
  request: Request
): Promise<TelegramProfile> {
  const subject = String(user.id);
  const now = new Date().toISOString();
  const existing = await profile(env, subject);
  const displayName = [user.first_name, user.last_name]
    .map((value) => text(value).trim())
    .filter(Boolean)
    .join(" ")
    .slice(0, 256);
  const username = text(user.username).trim().slice(0, 256);
  const photoUrl = safePhotoUrl(user.photo_url);
  const language = text(user.language_code).trim().slice(0, 16);
  const platform = text(request.headers.get("X-Telegram-Platform")).trim().slice(0, 64);
  const appVersion = text(request.headers.get("X-Wukong-Client-Version")).trim().slice(0, 64);
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO wukong_telegram_users (subject, first_seen_at, last_seen_at)
       VALUES (?, ?, ?) ON CONFLICT (subject) DO NOTHING`
    ).bind(subject, now, now),
    env.DB.prepare(
      `UPDATE wukong_telegram_users SET
         last_seen_at = ?,
         username = CASE WHEN ? <> '' THEN ? ELSE username END,
         display_name = CASE WHEN ? <> '' THEN ? ELSE display_name END,
         photo_url = CASE WHEN ? <> '' THEN ? ELSE photo_url END,
         language = CASE WHEN ? <> '' THEN ? ELSE language END,
         platform = CASE WHEN ? <> '' THEN ? ELSE platform END,
         app_version = CASE WHEN ? <> '' THEN ? ELSE app_version END
       WHERE subject = ?`
    ).bind(
      now,
      username, username,
      displayName, displayName,
      photoUrl, photoUrl,
      language, language,
      platform, platform,
      appVersion, appVersion,
      subject
    )
  ]);
  if (!existing) {
    const message = accessRequestMessage(subject, displayName, username);
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_telegram_user_events
         (event_id, subject, event_type, created_at)
         VALUES (?, ?, 'first_seen', ?)`
      ).bind(crypto.randomUUID(), subject, now),
      ...configuredAdmins(env).map((adminSubject) => notificationStatement(
        env,
        adminSubject,
        `access-request:${subject}:${adminSubject}`,
        message,
        now
      ))
    ]);
  }
  return (await profile(env, subject))!;
}

export async function openSession(
  env: Env,
  subject: string,
  sessionId: string
): Promise<TelegramProfile> {
  const normalized = sessionId.trim();
  if (!normalized || normalized.length > 128) {
    throw new Error("Mini App session ID is required");
  }
  const now = new Date().toISOString();
  const inserted = await env.DB.prepare(
    `INSERT INTO wukong_telegram_sessions (subject, session_id, opened_at)
     VALUES (?, ?, ?) ON CONFLICT (subject, session_id) DO NOTHING`
  ).bind(subject, normalized, now).run();
  if ((inserted.meta.changes ?? 0) > 0) {
    await env.DB.batch([
      env.DB.prepare(
        `UPDATE wukong_telegram_users
         SET mini_app_open_count = mini_app_open_count + 1, last_seen_at = ?
         WHERE subject = ?`
      ).bind(now, subject),
      env.DB.prepare(
        `INSERT INTO wukong_telegram_user_events
         (event_id, subject, event_type, details_json, created_at)
         VALUES (?, ?, 'mini_app_open', ?, ?)`
      ).bind(crypto.randomUUID(), subject, JSON.stringify({ sessionId: normalized }), now)
    ]);
  }
  return (await profile(env, subject))!;
}

export async function createUser(
  env: Env,
  value: unknown,
  actorSubject: string,
  username = "",
  displayName = ""
): Promise<TelegramProfile> {
  const subject = requireTelegramSubject(value);
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO wukong_telegram_users
       (subject, username, display_name, first_seen_at, last_seen_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT (subject) DO UPDATE SET
         username = CASE WHEN excluded.username <> '' THEN excluded.username ELSE username END,
         display_name = CASE WHEN excluded.display_name <> '' THEN excluded.display_name ELSE display_name END`
    ).bind(subject, username.trim().slice(0, 256), displayName.trim().slice(0, 256), now, now),
    eventStatement(env, subject, "created_by_admin", now, { actor: actorSubject })
  ]);
  return (await profile(env, subject))!;
}

export async function approveUser(
  env: Env,
  value: unknown,
  actorSubject: string,
  reason = ""
): Promise<TelegramProfile> {
  const subject = requireTelegramSubject(value);
  if (configuredAdmins(env).includes(subject)) {
    await ensureConfiguredAdmins(env);
    return (await profile(env, subject))!;
  }
  const current = await profile(env, subject);
  if (current?.accessStatus === "approved") return current;
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO wukong_telegram_users
       (subject, access_status, role, first_seen_at, last_seen_at, build_credits,
        lifetime_granted, approved_at, access_actor, access_reason)
       VALUES (?, 'approved', 'user', ?, ?, 1, 1, ?, ?, ?)
       ON CONFLICT (subject) DO UPDATE SET
         access_status = 'approved', role = 'user', build_credits = 1,
         unlimited = 0, lifetime_granted = lifetime_granted + 1,
         approved_at = excluded.approved_at, revoked_at = '',
         access_actor = excluded.access_actor, access_reason = excluded.access_reason`
    ).bind(subject, now, now, now, actorSubject, reason.slice(0, 1024)),
    env.DB.prepare(
      `INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user')
       ON CONFLICT (subject) DO UPDATE SET role = 'user'`
    ).bind(subject),
    eventStatement(env, subject, "approved", now, {
      actor: actorSubject,
      reason,
      details: { credits: 1 }
    }),
    notificationStatement(
      env,
      subject,
      `access-approved:${subject}:${now}`,
      "✅ <b>Tài khoản đã được duyệt</b>\n\nBạn có <b>1 lượt build</b>. Hãy mở Wukong ROM Studio để bắt đầu.",
      now
    )
  ]);
  return (await profile(env, subject))!;
}

export async function revokeUser(
  env: Env,
  value: unknown,
  actorSubject: string,
  reason: string
): Promise<TelegramProfile> {
  const subject = requireTelegramSubject(value);
  const normalizedReason = reason.trim();
  if (!normalizedReason) throw new Error("A reason is required to revoke access");
  if (configuredAdmins(env).includes(subject)) {
    throw new Error("Configured Telegram admins cannot be revoked from the allowlist");
  }
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO wukong_telegram_users (subject, first_seen_at, last_seen_at)
       VALUES (?, ?, ?) ON CONFLICT (subject) DO NOTHING`
    ).bind(subject, now, now),
    env.DB.prepare("DELETE FROM wukong_telegram_access WHERE subject = ?").bind(subject),
    env.DB.prepare(
      `UPDATE wukong_telegram_users SET access_status = 'revoked',
       build_credits = 0, unlimited = 0, revoked_at = ?,
       access_actor = ?, access_reason = ? WHERE subject = ?`
    ).bind(now, actorSubject, normalizedReason.slice(0, 1024), subject),
    eventStatement(env, subject, "revoked", now, {
      actor: actorSubject,
      reason: normalizedReason
    }),
    notificationStatement(
      env,
      subject,
      `access-revoked:${subject}:${now}`,
      `⛔ <b>Quyền truy cập đã bị thu hồi</b>\n\nLý do: ${escapeTelegramHtml(normalizedReason)}`,
      now
    )
  ]);
  return (await profile(env, subject))!;
}

function escapeTelegramHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

export async function updateAllowance(
  env: Env,
  value: unknown,
  actorSubject: string,
  payload: Record<string, unknown>
): Promise<TelegramProfile> {
  const subject = requireTelegramSubject(value);
  if (configuredAdmins(env).includes(subject)) {
    throw new Error("Configured Telegram admins are always unlimited");
  }
  const current = await profile(env, subject);
  if (!current || current.accessStatus !== "approved") {
    throw new Error("Telegram account is not approved");
  }
  const operation = String(payload.operation ?? "").trim().toLowerCase();
  let after = current.buildCredits;
  let unlimited = current.unlimited;
  if (operation === "add") {
    const amount = Number(payload.value);
    if (!Number.isSafeInteger(amount)) throw new Error("Build credit value must be an integer");
    after += amount;
  } else if (operation === "set") {
    const amount = Number(payload.value);
    if (!Number.isSafeInteger(amount)) throw new Error("Build credit value must be an integer");
    after = amount;
  } else if (operation === "unlimited") {
    if (typeof payload.unlimited !== "boolean") throw new Error("Unlimited value must be a boolean");
    unlimited = payload.unlimited;
  } else {
    throw new Error("Unsupported allowance operation");
  }
  if (after < 0) throw new Error("Build credits cannot be negative");
  const reason = String(payload.reason ?? "").trim();
  if ((after < current.buildCredits || (current.unlimited && !unlimited)) && !reason) {
    throw new Error("A reason is required to reduce access");
  }
  const delta = after - current.buildCredits;
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE wukong_telegram_users SET build_credits = ?, unlimited = ?,
       lifetime_granted = lifetime_granted + ? WHERE subject = ?`
    ).bind(after, unlimited ? 1 : 0, Math.max(0, delta), subject),
    env.DB.prepare(
      `INSERT INTO wukong_telegram_quota_ledger
       (ledger_id, subject, entry_type, delta, balance_after, actor_subject, reason, created_at)
       VALUES (?, ?, 'admin_adjustment', ?, ?, ?, ?, ?)`
    ).bind(
      crypto.randomUUID(), subject, delta, after, actorSubject, reason.slice(0, 1024), now
    ),
    eventStatement(env, subject, "allowance_changed", now, {
      actor: actorSubject,
      reason,
      details: { operation, delta, balance: after, unlimited }
    }),
    notificationStatement(
      env,
      subject,
      `allowance:${subject}:${now}`,
      `🎟 <b>Hạn mức build đã thay đổi</b>\n\nCòn lại: <b>${unlimited ? "không giới hạn" : `${after} lượt`}</b>.`,
      now
    )
  ]);
  return (await profile(env, subject))!;
}

const SORT_COLUMNS: Record<string, string> = {
  lastSeenAt: "last_seen_at",
  firstSeenAt: "first_seen_at",
  jobCount: "job_count",
  buildCredits: "build_credits"
};

export function encodeAuditCursor(event: Record<string, unknown>): string {
  const payload = JSON.stringify([
    String(event.createdAt ?? ""),
    String(event.eventId ?? "")
  ]);
  const bytes = new TextEncoder().encode(payload);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export function decodeAuditCursor(
  value: string
): { createdAt: string; eventId: string } | null {
  const normalized = value.trim();
  if (!normalized) return null;
  try {
    const base64 = normalized.replaceAll("-", "+").replaceAll("_", "/")
      + "=".repeat((4 - normalized.length % 4) % 4);
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const decoded = JSON.parse(new TextDecoder().decode(bytes));
    if (
      !Array.isArray(decoded) ||
      decoded.length !== 2 ||
      !decoded.every((item) => typeof item === "string" && item.length > 0)
    ) {
      throw new Error("invalid payload");
    }
    return { createdAt: decoded[0], eventId: decoded[1] };
  } catch {
    throw new Error("Audit cursor is invalid");
  }
}

export async function listUsers(
  env: Env,
  search: URLSearchParams
): Promise<{
  users: Array<TelegramProfile & ActivityProfileExtension>;
  total: number;
  limit: number;
  offset: number;
  statusCounts: Record<"approved" | "pending" | "revoked", number>;
}> {
  const query = (search.get("query") ?? "").trim().slice(0, 256);
  const status = (search.get("status") ?? "").trim().toLowerCase();
  const quota = (search.get("quota") ?? "").trim().toLowerCase();
  const activity = (search.get("activity") ?? "").trim().toLowerCase();
  const limit = Math.max(1, Math.min(Number(search.get("limit") ?? 50) || 50, 100));
  const offset = Math.max(0, Number(search.get("offset") ?? 0) || 0);
  const sort = SORT_COLUMNS[search.get("sort") ?? "lastSeenAt"] ?? "last_seen_at";
  const direction = (search.get("direction") ?? "desc").toLowerCase() === "asc" ? "ASC" : "DESC";
  const where: string[] = [];
  const bindings: unknown[] = [];
  if (query) {
    where.push("(subject LIKE ? OR username LIKE ? OR display_name LIKE ?)");
    const pattern = `%${query}%`;
    bindings.push(pattern, pattern, pattern);
  }
  if (["pending", "approved", "revoked"].includes(status)) {
    where.push("access_status = ?");
    bindings.push(status);
  }
  if (quota === "available") where.push("(unlimited = 1 OR build_credits > 0)");
  if (quota === "exhausted") where.push("unlimited = 0 AND build_credits = 0");
  if (quota === "unlimited") where.push("unlimited = 1");
  if (activity === "active") where.push("mini_app_open_count > 0");
  if (activity === "never") where.push("mini_app_open_count = 0");
  if (activity === "jobs") where.push("job_count > 0");
  const clause = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const count = await env.DB.prepare(
    `SELECT COUNT(*) AS count FROM wukong_telegram_users ${clause}`
  ).bind(...bindings).first<{ count: number }>();
  const page = await env.DB.prepare(
    `SELECT ${PROFILE_COLUMNS} FROM wukong_telegram_users ${clause}
     ORDER BY ${sort} ${direction}, subject ASC LIMIT ? OFFSET ?`
  ).bind(...bindings, limit, offset).all<Record<string, unknown>>();
  const statusRows = await env.DB.prepare(
    `SELECT access_status, COUNT(*) AS count
     FROM wukong_telegram_users
     GROUP BY access_status`
  ).all<{ access_status: string; count: number }>();
  const statusCounts = { approved: 0, pending: 0, revoked: 0 };
  for (const row of statusRows.results) {
    const key = String(row.access_status) as keyof typeof statusCounts;
    if (key in statusCounts) statusCounts[key] = Number(row.count ?? 0);
  }
  const profiles = page.results
    .map(profilePayload)
    .filter((value): value is TelegramProfile => Boolean(value));
  return {
    users: await attachCurrentActivities(env, profiles),
    total: Number(count?.count ?? 0),
    limit,
    offset,
    statusCounts
  };
}

export async function profileWithActivity(
  env: Env,
  subject: string
): Promise<(TelegramProfile & ActivityProfileExtension) | null> {
  const value = await profile(env, subject);
  if (!value) return null;
  return (await attachCurrentActivities(env, [value]))[0] ?? null;
}

function userEventPayload(row: Record<string, unknown>, subject: string): Record<string, unknown> {
  let details = {};
  try { details = JSON.parse(String(row.details_json ?? "{}")); } catch { details = {}; }
  return {
    eventId: row.event_id,
    telegramId: subject,
    type: row.event_type,
    actorTelegramId: row.actor_subject,
    reason: row.reason,
    details,
    createdAt: row.created_at
  };
}

export async function userEvents(
  env: Env,
  subjectValue: unknown,
  limit = 100,
  before?: { createdAt: string; eventId: string }
): Promise<Array<Record<string, unknown>>> {
  const subject = requireTelegramSubject(subjectValue);
  const cursorClause = before
    ? " AND (created_at < ? OR (created_at = ? AND event_id < ?))"
    : "";
  const bindings: unknown[] = [subject];
  if (before) bindings.push(before.createdAt, before.createdAt, before.eventId);
  bindings.push(Math.max(1, Math.min(limit, 101)));
  const result = await env.DB.prepare(
    `SELECT event_id, event_type, actor_subject, reason, details_json, created_at
     FROM wukong_telegram_user_events WHERE subject = ?${cursorClause}
     ORDER BY created_at DESC, event_id DESC LIMIT ?`
  ).bind(...bindings).all<Record<string, unknown>>();
  return result.results.map((row) => userEventPayload(row, subject));
}

export async function userEventsSince(
  env: Env,
  subjectValue: unknown,
  createdAt: string,
  eventId: string,
  limit = 50
): Promise<Array<Record<string, unknown>>> {
  const subject = requireTelegramSubject(subjectValue);
  const result = await env.DB.prepare(
    `SELECT event_id, event_type, actor_subject, reason, details_json, created_at
     FROM wukong_telegram_user_events
     WHERE subject = ?
       AND (created_at > ? OR (created_at = ? AND event_id > ?))
     ORDER BY created_at ASC, event_id ASC LIMIT ?`
  ).bind(
    subject,
    createdAt,
    createdAt,
    eventId,
    Math.max(1, Math.min(limit, 51))
  ).all<Record<string, unknown>>();
  return result.results.map((row) => userEventPayload(row, subject));
}

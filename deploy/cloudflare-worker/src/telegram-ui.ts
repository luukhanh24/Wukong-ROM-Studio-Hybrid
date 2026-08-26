import type { AuthenticatedRequest } from "./auth";
import { catalogPayload } from "./catalog";
import { cloudLibrary } from "./drive";
import { clearActionsCaches, listActionsCaches } from "./github";
import {
  artifactDownloadUrl,
  cancelJob,
  inspectJob,
  jobEvents,
  listJobs,
  publicJob,
  resumeJob,
  type JobRow
} from "./jobs";
import {
  approveUser,
  listUsers,
  revokeUser,
  type TelegramProfile
} from "./state";

type JsonObject = Record<string, unknown>;
export interface TelegramUiResponse {
  text: string;
  reply_markup?: JsonObject;
}

function escape(value: unknown, limit = 512): string {
  return String(value ?? "—").slice(0, limit)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function inline(rows: JsonObject[][]): JsonObject {
  return { inline_keyboard: rows };
}

function appButton(env: Env, language: string): JsonObject {
  return {
    text: language === "en" ? "Open Wukong Mini App" : "Mở Wukong Mini App",
    web_app: { url: env.WUKONG_TELEGRAM_WEB_APP_URL }
  };
}

async function languageFor(env: Env, subject: string, fallback = "vi"): Promise<string> {
  const row = await env.DB.prepare(
    "SELECT language FROM wukong_telegram_ui_state WHERE subject = ?"
  ).bind(subject).first<{ language: string }>();
  return row?.language === "en" || row?.language === "vi"
    ? row.language
    : fallback.toLowerCase().startsWith("en")
      ? "en"
      : "vi";
}

async function saveLanguage(env: Env, subject: string, language: string): Promise<void> {
  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO wukong_telegram_ui_state (subject, language, updated_at)
     VALUES (?, ?, ?)
     ON CONFLICT (subject) DO UPDATE SET language = excluded.language, updated_at = excluded.updated_at`
  ).bind(subject, language, now).run();
}

function menu(env: Env, language: string): TelegramUiResponse {
  const en = language === "en";
  return {
    text: en
      ? "✨ <b>Wukong ROM Studio</b>\n\nChoose a feature below. ROM configuration and new builds open in the Mini App."
      : "✨ <b>Wukong ROM Studio</b>\n\nChọn chức năng bên dưới. Cấu hình ROM và tạo build mới được thực hiện trong Mini App.",
    reply_markup: inline([
      [appButton(env, language)],
      [
        { text: en ? "📦 Jobs" : "📦 Job", callback_data: "v1:jobs" },
        { text: en ? "👤 Account" : "👤 Tài khoản", callback_data: "v1:account" }
      ],
      [{ text: en ? "☁️ Cloud library" : "☁️ Thư viện cloud", callback_data: "v1:cloud" }],
      [
        { text: en ? "🩺 Diagnostics" : "🩺 Chẩn đoán", callback_data: "v1:diag" },
        { text: en ? "🇻🇳 Tiếng Việt" : "🇬🇧 English", callback_data: `v1:lang:${en ? "vi" : "en"}` }
      ]
    ])
  };
}

function accountMessage(user: TelegramProfile, language: string): TelegramUiResponse {
  const en = language === "en";
  const status = en
    ? { pending: "Pending", approved: "Approved", revoked: "Revoked" }[user.accessStatus]
    : { pending: "Chờ duyệt", approved: "Đã duyệt", revoked: "Đã thu hồi" }[user.accessStatus];
  const allowance = user.unlimited ? (en ? "Unlimited" : "Không giới hạn") : String(user.buildCredits);
  return {
    text: [
      en ? "<b>Telegram account</b>" : "<b>Tài khoản Telegram</b>",
      "",
      `${en ? "Name" : "Tên"}  <b>${escape(user.displayName)}</b>`,
      `Telegram ID  <code>${escape(user.telegramId)}</code>`,
      `Username  ${user.username ? `@${escape(user.username)}` : "—"}`,
      `${en ? "Access" : "Quyền truy cập"}  <b>${status}</b>`,
      `${en ? "Build allowance" : "Lượt build"}  <b>${allowance}</b>`,
      `${en ? "Completed/created jobs" : "Số lượt đã build"}  <b>${user.jobCount}</b>`,
      `${en ? "Credits used" : "Lượt đã dùng"}  <b>${user.lifetimeUsed}</b>`
    ].join("\n")
  };
}

function helpMessage(role: string, language: string): TelegramUiResponse {
  const en = language === "en";
  const base = en
    ? [
      "<b>Wukong bot commands</b>",
      "/app, /new, /submit — open Mini App",
      "/jobs — recent jobs",
      "/job &lt;id&gt; — job details",
      "/events &lt;id&gt; — recent events",
      "/artifacts &lt;id&gt; — direct cloud artifact",
      "/cancel &lt;id&gt; — cancel an active job",
      "/resume &lt;id&gt; — resume a resumable job",
      "/cloud [sources|artifacts] — cloud library",
      "/account — account and Build allowance",
      "/diagnostics, /catalog, /cache, /language"
    ]
    : [
      "<b>Lệnh Wukong bot</b>",
      "/app, /new, /submit — mở Mini App",
      "/jobs — các job gần đây",
      "/job &lt;id&gt; — chi tiết job",
      "/events &lt;id&gt; — sự kiện gần nhất",
      "/artifacts &lt;id&gt; — artifact cloud trực tiếp",
      "/cancel &lt;id&gt; — hủy job đang chạy",
      "/resume &lt;id&gt; — chạy tiếp job có checkpoint",
      "/cloud [sources|artifacts] — thư viện cloud",
      "/account — tài khoản và lượt build",
      "/diagnostics, /catalog, /cache, /language"
    ];
  if (role === "admin") {
    base.push(
      en
        ? "/users, /approve &lt;id&gt;, /revoke &lt;id&gt; &lt;reason&gt;, /cache_clear"
        : "/users, /approve &lt;id&gt;, /revoke &lt;id&gt; &lt;lý do&gt;, /cache_clear"
    );
  }
  return { text: base.join("\n") };
}

function authFor(user: TelegramProfile): AuthenticatedRequest {
  return { subject: user.telegramId, role: user.role, profile: user };
}

function jobId(value: JsonObject): string {
  return String(value.job_id ?? value.jobId ?? "");
}

function jobSummary(value: JsonObject, language: string): string {
  const id = jobId(value);
  const progress = Math.round(Number(value.progress ?? 0) * 100);
  return [
    `<b>${language === "en" ? "Job" : "Job"} ${escape(id, 64)}</b>`,
    `${language === "en" ? "Status" : "Trạng thái"}  <b>${escape(value.status)}</b>`,
    `${language === "en" ? "Stage" : "Giai đoạn"}  <code>${escape(value.stage)}</code>`,
    `${language === "en" ? "Progress" : "Tiến độ"}  <b>${progress}%</b>`
  ].join("\n");
}

async function jobsMenu(env: Env, user: TelegramProfile, language: string): Promise<TelegramUiResponse> {
  const jobs = (await listJobs(env, authFor(user))).slice(0, 12);
  if (!jobs.length) {
    return {
      text: language === "en" ? "No build jobs yet." : "Chưa có job build.",
      reply_markup: inline([[appButton(env, language)], [{ text: "‹ Menu", callback_data: "v1:menu" }]])
    };
  }
  return {
    text: language === "en" ? "<b>Recent jobs</b>" : "<b>Job gần đây</b>",
    reply_markup: inline([
      ...jobs.map((value) => [{
        text: `${String(value.status ?? "—")} · ${jobId(value).slice(0, 12)}`,
        callback_data: `v1:job:${jobId(value)}`
      }]),
      [{ text: "‹ Menu", callback_data: "v1:menu" }]
    ])
  };
}

async function resolveJob(env: Env, user: TelegramProfile, reference: string): Promise<JobRow> {
  const exact = reference.trim();
  if (/^[A-Za-z0-9-]{1,64}$/.test(exact)) {
    try {
      return await inspectJob(env, authFor(user), exact);
    } catch {
      // Fall through to a unique prefix lookup for the compact Telegram UI.
    }
  }
  const ownership = user.role === "admin" ? "" : "AND owner_channel = 'telegram' AND owner_subject = ?";
  const statement = env.DB.prepare(
    `SELECT * FROM wukong_jobs WHERE job_id LIKE ? ${ownership}
     ORDER BY created_at DESC LIMIT 2`
  );
  const rows = user.role === "admin"
    ? await statement.bind(`${exact}%`).all<JobRow>()
    : await statement.bind(`${exact}%`, user.telegramId).all<JobRow>();
  if (rows.results.length !== 1) throw new Error("Job not found");
  return rows.results[0]!;
}

function jobKeyboard(env: Env, row: JobRow, language: string, hasArtifact: boolean): JsonObject {
  const id = row.job_id;
  const rows: JsonObject[][] = [[
    { text: language === "en" ? "Refresh" : "Làm mới", callback_data: `v1:job:${id}` },
    { text: language === "en" ? "Events" : "Sự kiện", callback_data: `v1:events:${id}` }
  ]];
  if (hasArtifact) rows.push([{ text: "Artifact", callback_data: `v1:artifact:${id}` }]);
  if (!["succeeded", "failed", "cancelled"].includes(row.status)) {
    rows.push([{ text: language === "en" ? "Cancel" : "Hủy", callback_data: `v1:cancel:${id}` }]);
  }
  if (["failed", "cancelled"].includes(row.status)) {
    rows.push([{ text: language === "en" ? "Resume" : "Tiếp tục", callback_data: `v1:resume:${id}` }]);
  }
  rows.push([{ text: "‹ Jobs", callback_data: "v1:jobs" }, appButton(env, language)]);
  return inline(rows);
}

async function jobAction(
  env: Env,
  user: TelegramProfile,
  language: string,
  action: string,
  reference: string
): Promise<TelegramUiResponse> {
  const row = await resolveJob(env, user, reference);
  const auth = authFor(user);
  if (action === "cancel") await cancelJob(env, auth, row.job_id);
  if (action === "resume") {
    const resumed = await resumeJob(env, auth, row.job_id, `telegram:${crypto.randomUUID()}`);
    const resumedId = jobId(resumed.job);
    const resumedRow = await resolveJob(env, user, resumedId);
    return {
      text: jobSummary(publicJob(resumedRow, env), language),
      reply_markup: jobKeyboard(env, resumedRow, language, Boolean(artifactDownloadUrl(resumedRow, env)))
    };
  }
  const refreshed = await resolveJob(env, user, row.job_id);
  if (action === "events") {
    const events = (await jobEvents(env, auth, row.job_id, 0)).slice(-10);
    return {
      text: [
        `<b>${language === "en" ? "Recent events" : "Sự kiện gần đây"} · ${escape(row.job_id, 64)}</b>`,
        "",
        ...(events.length
          ? events.map((event) => `${event.sequence}. ${escape(event.type)} · ${escape(event.stage ?? event.status ?? "")}`)
          : ["—"])
      ].join("\n"),
      reply_markup: jobKeyboard(env, refreshed, language, Boolean(artifactDownloadUrl(refreshed, env)))
    };
  }
  if (action === "artifact") {
    const url = artifactDownloadUrl(refreshed, env);
    return {
      text: url
        ? `<b>Artifact</b>\n\nJob  <code>${escape(row.job_id, 64)}</code>\nLink Drive/cloud trực tiếp đã sẵn sàng.`
        : language === "en" ? "Artifact is not available yet." : "Job chưa có artifact.",
      reply_markup: inline([
        ...(url ? [[{ text: language === "en" ? "Download artifact" : "Tải artifact", url }]] : []),
        [{ text: "‹ Job", callback_data: `v1:job:${row.job_id}` }]
      ])
    };
  }
  return {
    text: jobSummary(publicJob(refreshed, env), language),
    reply_markup: jobKeyboard(env, refreshed, language, Boolean(artifactDownloadUrl(refreshed, env)))
  };
}

async function cloudMenu(env: Env, language: string, category = "sources"): Promise<TelegramUiResponse> {
  const payload = await cloudLibrary(env, category);
  const entries = Array.isArray(payload.entries) ? payload.entries.slice(0, 20) : [];
  return {
    text: [
      language === "en" ? `<b>Cloud library · ${category}</b>` : `<b>Thư viện cloud · ${category}</b>`,
      "",
      ...(entries.length
        ? entries.map((entry) => `• ${escape((entry as JsonObject).name ?? (entry as JsonObject).path)}`)
        : [language === "en" ? "No files found." : "Chưa có tệp."])
    ].join("\n"),
    reply_markup: inline([[appButton(env, language)], [{ text: "‹ Menu", callback_data: "v1:menu" }]])
  };
}

async function diagnostics(env: Env, language: string): Promise<TelegramUiResponse> {
  return {
    text: [
      language === "en" ? "<b>System diagnostics</b>" : "<b>Chẩn đoán hệ thống</b>",
      "",
      "Control plane  <b>ready</b>",
      "State backend  <code>D1</code>",
      `Runner  <code>GitHub Actions · ${escape(env.WUKONG_GITHUB_REPOSITORY)}</code>`,
      `Cloud  <code>${env.WUKONG_GOOGLE_DRIVE_FOLDER_ID ? "Google Drive" : "chưa cấu hình"}</code>`,
      `Release  <code>${escape(env.WUKONG_RELEASE_SHA, 40)}</code>`
    ].join("\n")
  };
}

export async function telegramUi(
  env: Env,
  user: TelegramProfile,
  input: { text?: string; callbackData?: string; fallbackLanguage?: string }
): Promise<TelegramUiResponse> {
  let language = await languageFor(env, user.telegramId, input.fallbackLanguage);
  const callback = input.callbackData ?? "";
  if (callback.startsWith("v1:lang:")) {
    language = callback.endsWith(":en") ? "en" : "vi";
    await saveLanguage(env, user.telegramId, language);
    return menu(env, language);
  }
  if (user.accessStatus !== "approved") {
    return {
      text: language === "en"
        ? "⏳ <b>Wukong ROM Studio</b>\n\nYour account is waiting for administrator approval."
        : "⏳ <b>Wukong ROM Studio</b>\n\nTài khoản đang chờ quản trị viên cấp quyền."
    };
  }
  const commandText = String(input.text ?? "").trim();
  const [rawCommand = "", ...parts] = commandText.split(/\s+/);
  const command = rawCommand.split("@", 1)[0]!.toLowerCase();
  const argument = parts.join(" ").trim();
  const action = callback.startsWith("v1:") ? callback.slice(3) : "";
  try {
    if (action === "menu" || (!action && ["", "/start", "/menu"].includes(command))) {
      return menu(env, language);
    }
    const legacyBuildAction = /^(new|task|run|src|source|device|preset|modver|mod|toggle|confirm|build)(?::|$)/.test(action);
    if (["/app", "/new", "/submit"].includes(command) || action === "app" || legacyBuildAction) {
      return {
        text: language === "en"
          ? "Open the Mini App to configure ROM metadata, MODs, release label, and start a build."
          : "Mở Mini App để cấu hình ROM, MOD, phiên bản phát hành và bắt đầu build.",
        reply_markup: inline([[appButton(env, language)], [{ text: "‹ Menu", callback_data: "v1:menu" }]])
      };
    }
    if (command === "/language") {
      language = language === "en" ? "vi" : "en";
      await saveLanguage(env, user.telegramId, language);
      return menu(env, language);
    }
    if (["/account", "/me"].includes(command) || action === "account") return accountMessage(user, language);
    if (command === "/help") return helpMessage(user.role, language);
    if (command === "/jobs" || action === "jobs") return jobsMenu(env, user, language);
    const callbackJob = action.match(/^(job|events|artifact|cancel|resume):(.+)$/);
    if (callbackJob) return jobAction(env, user, language, callbackJob[1]!, callbackJob[2]!);
    if (["/job", "/events", "/artifacts", "/cancel", "/resume"].includes(command)) {
      if (!argument) return { text: `Cú pháp: ${command} <job_id>` };
      return jobAction(env, user, language, command === "/artifacts" ? "artifact" : command.slice(1), argument);
    }
    if (command === "/cloud" || action === "cloud") return cloudMenu(env, language, argument || "sources");
    if (command === "/diagnostics" || action === "diag") return diagnostics(env, language);
    if (command === "/catalog") {
      const catalog = catalogPayload();
      return {
        text: `<b>Catalog</b>\n\nDevices  <b>${Array.isArray(catalog.devices) ? catalog.devices.length : 0}</b>\nMOD versions  <b>${Array.isArray(catalog.modVersions) ? catalog.modVersions.length : 0}</b>`
      };
    }
    if (command === "/cache") {
      const cache = await listActionsCaches(env);
      return { text: `<b>GitHub Actions cache</b>\n\nEntries  <b>${escape(cache.entryCount)}</b>\nSize  <code>${escape(cache.totalBytes)} B</code>` };
    }
    if (command === "/cache_clear") {
      if (user.role !== "admin") throw new Error("Admin access is required");
      const result = await clearActionsCaches(env);
      return { text: `✅ Cache cleared\n<code>${escape(JSON.stringify(result), 1200)}</code>` };
    }
    if (command === "/users") {
      if (user.role !== "admin") throw new Error("Admin access is required");
      const result = await listUsers(env, new URLSearchParams({ limit: "20" }));
      const users = Array.isArray(result.users) ? result.users : [];
      return {
        text: [
          "<b>Telegram users</b>",
          "",
          ...users.map((value) => {
            const item = value as TelegramProfile;
            return `• <code>${escape(item.telegramId)}</code> · ${escape(item.displayName)} · ${escape(item.accessStatus)} · ${item.jobCount} jobs`;
          })
        ].join("\n")
      };
    }
    if (command === "/approve") {
      if (user.role !== "admin") throw new Error("Admin access is required");
      const approved = await approveUser(env, argument, user.telegramId);
      return { text: `✅ Đã duyệt <code>${escape(approved.telegramId)}</code> · ${escape(approved.displayName)}` };
    }
    if (command === "/revoke") {
      if (user.role !== "admin") throw new Error("Admin access is required");
      const [subject = "", ...reasonParts] = parts;
      if (!subject || !reasonParts.join(" ").trim()) return { text: "Cú pháp: /revoke <telegram_id> <lý do>" };
      const revoked = await revokeUser(env, subject, user.telegramId, reasonParts.join(" "));
      return { text: `⛔ Đã thu hồi <code>${escape(revoked.telegramId)}</code>` };
    }
    return helpMessage(user.role, language);
  } catch (error) {
    return {
      text: `${language === "en" ? "Could not complete the action" : "Không thể thực hiện"}: ${escape(error instanceof Error ? error.message : error, 800)}`,
      reply_markup: inline([[{ text: "‹ Menu", callback_data: "v1:menu" }]])
    };
  }
}

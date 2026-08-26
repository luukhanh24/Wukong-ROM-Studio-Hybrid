import { confirmPairing, rememberSourceDraft } from "./sessions";
import { observeUser, profile } from "./state";
import { recoverPreBootstrapJobs } from "./recovery";

type JsonObject = Record<string, unknown>;

export class TelegramHttpError extends Error {
  constructor(message: string, readonly status = 400) {
    super(message);
  }
}

function html(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function telegramUser(value: unknown): {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  photo_url?: string;
} | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const user = value as JsonObject;
  const id = Number(user.id);
  if (!Number.isSafeInteger(id) || id <= 0) return null;
  return {
    id,
    ...(typeof user.first_name === "string" ? { first_name: user.first_name } : {}),
    ...(typeof user.last_name === "string" ? { last_name: user.last_name } : {}),
    ...(typeof user.username === "string" ? { username: user.username } : {}),
    ...(typeof user.language_code === "string" ? { language_code: user.language_code } : {}),
    ...(typeof user.photo_url === "string" ? { photo_url: user.photo_url } : {})
  };
}

function webAppKeyboard(env: Env): JsonObject {
  return {
    inline_keyboard: [[{
      text: "Mở Wukong ROM Studio",
      web_app: { url: env.WUKONG_TELEGRAM_WEB_APP_URL }
    }]]
  };
}

function waitingMessage(displayName: string): string {
  return [
    "⏳ <b>Wukong ROM Studio</b>",
    "",
    `Xin chào <b>${html(displayName || "bạn")}</b>.`,
    "Yêu cầu truy cập của bạn đã được ghi nhận.",
    "",
    "Trạng thái: <b>Chờ quản trị viên cấp quyền</b>",
    "Bạn sẽ nhận thông báo ngay khi tài khoản được duyệt."
  ].join("\n");
}

function readyMessage(
  displayName: string,
  buildCredits: number,
  unlimited: boolean,
  jobCount: number
): string {
  return [
    "✨ <b>Wukong ROM Studio</b>",
    "",
    `Xin chào <b>${html(displayName || "bạn")}</b>. Control plane đã sẵn sàng.`,
    "",
    `🎟 Lượt build: <b>${unlimited ? "Không giới hạn" : buildCredits}</b>`,
    `📦 Số lượt đã build: <b>${jobCount}</b>`,
    "",
    "Mở Studio để cấu hình ROM, theo dõi tiến trình và lấy link Drive/cloud trực tiếp."
  ].join("\n");
}

async function enqueueMessage(
  env: Env,
  chatId: string,
  dedupeKey: string,
  payload: JsonObject
): Promise<void> {
  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
     (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), dedupeKey, chatId, JSON.stringify(payload), now, now).run();
}

export async function drainTelegramOutbox(env: Env, limit = 10): Promise<void> {
  const now = new Date().toISOString();
  const leaseExpiresAt = new Date(Date.now() + 2 * 60 * 1000).toISOString();
  const result = await env.DB.prepare(
    `SELECT notification_id, chat_id, method, payload_json, attempts
     FROM wukong_telegram_notification_outbox
     WHERE available_at <= ? AND state IN ('pending', 'failed', 'sending')
     ORDER BY created_at ASC LIMIT ?`
  ).bind(now, Math.max(1, Math.min(limit, 50))).all<Record<string, unknown>>();
  for (const row of result.results) {
    const notificationId = String(row.notification_id);
    const claimed = await env.DB.prepare(
      `UPDATE wukong_telegram_notification_outbox
       SET state = 'sending', attempts = attempts + 1, available_at = ?
       WHERE notification_id = ?
         AND available_at <= ?
         AND state IN ('pending', 'failed', 'sending')`
    ).bind(leaseExpiresAt, notificationId, now).run();
    if ((claimed.meta.changes ?? 0) !== 1) continue;
    let payload: JsonObject;
    try {
      payload = JSON.parse(String(row.payload_json)) as JsonObject;
    } catch {
      payload = {};
    }
    try {
      const method = String(row.method || "sendMessage");
      const response = await fetch(
        `https://api.telegram.org/bot${env.WUKONG_TELEGRAM_BOT_TOKEN}/${method}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: String(row.chat_id), ...payload })
        }
      );
      const resultPayload = await response.json().catch(() => ({})) as JsonObject;
      if (!response.ok || resultPayload.ok === false) {
        throw new Error(String(resultPayload.description ?? `Telegram HTTP ${response.status}`));
      }
      await env.DB.prepare(
        `UPDATE wukong_telegram_notification_outbox
         SET state = 'sent', sent_at = ?, last_error = ''
         WHERE notification_id = ?`
      ).bind(new Date().toISOString(), notificationId).run();
    } catch (error) {
      const attempts = Number(row.attempts ?? 0) + 1;
      const delaySeconds = Math.min(3600, 2 ** Math.min(attempts, 10));
      await env.DB.prepare(
        `UPDATE wukong_telegram_notification_outbox
         SET state = 'failed', available_at = ?, last_error = ?
         WHERE notification_id = ?`
      ).bind(
        new Date(Date.now() + delaySeconds * 1000).toISOString(),
        (error instanceof Error ? error.message : String(error)).slice(0, 1024),
        notificationId
      ).run();
    }
  }
}

export async function handleTelegramWebhook(
  request: Request,
  env: Env
): Promise<void> {
  const supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token") ?? "";
  if (!env.WUKONG_TELEGRAM_WEBHOOK_SECRET || supplied !== env.WUKONG_TELEGRAM_WEBHOOK_SECRET) {
    throw new TelegramHttpError("Telegram webhook authentication failed", 403);
  }
  const payload = await request.json() as JsonObject;
  const updateId = Number(payload.update_id);
  if (!Number.isSafeInteger(updateId)) {
    throw new TelegramHttpError("Telegram update must be an object", 400);
  }
  const now = new Date().toISOString();
  const accepted = await env.DB.prepare(
    `INSERT INTO wukong_telegram_update_inbox
     (update_id, payload_json, state, received_at)
     VALUES (?, ?, 'processing', ?) ON CONFLICT (update_id) DO NOTHING`
  ).bind(updateId, JSON.stringify(payload), now).run();
  if ((accepted.meta.changes ?? 0) !== 1) return;
  try {
    const message = payload.message && typeof payload.message === "object"
      ? payload.message as JsonObject
      : null;
    const user = telegramUser(message?.from);
    const chat = message?.chat && typeof message.chat === "object"
      ? message.chat as JsonObject
      : {};
    const chatId = String(chat.id ?? user?.id ?? "");
    if (message && user && chatId) {
      const observed = await observeUser(
        env,
        user,
        new Request("https://telegram.invalid", {
          headers: { "X-Telegram-Platform": "telegram-bot" }
        })
      );
      const text = String(message.text ?? "").trim();
      const pairMatch = text.match(/^\/start(?:@\w+)?\s+pair_([0-9a-f]{24})$/i);
      const paired = pairMatch
        ? await confirmPairing(env, pairMatch[1]!, String(user.id))
        : false;
      const current = (await profile(env, String(user.id))) ?? observed;
      const displayName = current.displayName || user.first_name || "";
      let responseText: string;
      let replyMarkup: JsonObject | undefined;
      if (current.accessStatus !== "approved") {
        responseText = paired
          ? `${waitingMessage(displayName)}\n\n🔗 Phiên Mini App đã được kết nối.`
          : waitingMessage(displayName);
      } else {
        const remembered = /^https?:\/\//i.test(text)
          ? await rememberSourceDraft(env, String(user.id), text)
          : false;
        responseText = remembered
          ? "🔗 <b>Đã lưu link ROM cho job hiện tại</b>\n\nMở Studio để phân tích metadata và hoàn tất cấu hình."
          : paired
            ? `${readyMessage(displayName, current.buildCredits, current.unlimited, current.jobCount)}\n\n🔗 Phiên Mini App đã được kết nối.`
            : readyMessage(displayName, current.buildCredits, current.unlimited, current.jobCount);
        replyMarkup = webAppKeyboard(env);
      }
      await enqueueMessage(env, chatId, `telegram-update:${updateId}`, {
        text: responseText,
        parse_mode: "HTML",
        disable_web_page_preview: true,
        ...(replyMarkup ? { reply_markup: replyMarkup } : {})
      });
      await drainTelegramOutbox(env, 1);
    }
    await env.DB.prepare(
      `UPDATE wukong_telegram_update_inbox
       SET state = 'processed', processed_at = ? WHERE update_id = ?`
    ).bind(new Date().toISOString(), updateId).run();
  } catch (error) {
    await env.DB.prepare(
      `UPDATE wukong_telegram_update_inbox
       SET state = 'failed', attempts = attempts + 1, last_error = ?
       WHERE update_id = ?`
    ).bind(
      (error instanceof Error ? error.message : String(error)).slice(0, 1024),
      updateId
    ).run();
    throw error;
  }
}

export async function maintenance(env: Env): Promise<void> {
  try {
    await recoverPreBootstrapJobs(env);
  } catch (error) {
    console.error(
      "Pre-bootstrap GitHub Actions recovery failed",
      error instanceof Error ? error.message : String(error)
    );
  }
  const nowSeconds = Math.floor(Date.now() / 1000);
  const oldIso = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM wukong_telegram_pairings WHERE expires_at < ?").bind(nowSeconds),
    env.DB.prepare("DELETE FROM wukong_source_probe_sessions WHERE expires_at < ?").bind(nowSeconds),
    env.DB.prepare("DELETE FROM wukong_source_transport_claims WHERE expires_at < ?").bind(nowSeconds),
    env.DB.prepare(
      "DELETE FROM wukong_telegram_source_drafts WHERE updated_at < ?"
    ).bind(nowSeconds - 24 * 60 * 60),
    env.DB.prepare(
      "DELETE FROM wukong_telegram_update_inbox WHERE processed_at <> '' AND processed_at < ?"
    ).bind(oldIso)
  ]);
  await drainTelegramOutbox(env, 25);
}

import { issueLaunchToken } from "./auth";
import { constantTimeHexEqual, sha256Hex } from "./crypto";

type JsonObject = Record<string, unknown>;

export class SessionHttpError extends Error {
  constructor(message: string, readonly status = 400) {
    super(message);
  }
}

function randomToken(bytesLength: number): string {
  const value = new Uint8Array(bytesLength);
  crypto.getRandomValues(value);
  return [...value].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function beginPairing(env: Env): Promise<JsonObject> {
  const username = env.WUKONG_TELEGRAM_BOT_USERNAME.trim().replace(/^@/, "");
  if (!/^[A-Za-z0-9_]{5,32}$/.test(username)) {
    throw new SessionHttpError("Telegram bot username is not configured", 503);
  }
  const pairId = randomToken(12);
  const pairSecret = randomToken(24);
  const now = Math.floor(Date.now() / 1000);
  const expiresIn = 5 * 60;
  await env.DB.prepare(
    `INSERT INTO wukong_telegram_pairings
     (pair_id, secret_hash, created_at, expires_at)
     VALUES (?, ?, ?, ?)`
  ).bind(pairId, await sha256Hex(pairSecret), now, now + expiresIn).run();
  return {
    pairId,
    pairSecret,
    botLink: `https://t.me/${username}?start=pair_${pairId}`,
    expiresIn
  };
}

export async function confirmPairing(
  env: Env,
  pairId: string,
  subject: string
): Promise<boolean> {
  if (!/^[0-9a-f]{24}$/.test(pairId) || !/^[1-9][0-9]*$/.test(subject)) return false;
  const now = Math.floor(Date.now() / 1000);
  const result = await env.DB.prepare(
    `UPDATE wukong_telegram_pairings SET user_id = ?
     WHERE pair_id = ? AND expires_at >= ?
       AND (user_id IS NULL OR user_id = '' OR user_id = ?)`
  ).bind(subject, pairId, now, subject).run();
  return (result.meta.changes ?? 0) === 1;
}

export async function pairingStatus(
  env: Env,
  value: unknown
): Promise<{ payload: JsonObject; status: number }> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new SessionHttpError("Telegram pairing request is invalid or expired", 404);
  }
  const payload = value as JsonObject;
  const pairId = String(payload.pairId ?? "").trim();
  const pairSecret = String(payload.pairSecret ?? "");
  if (!/^[0-9a-f]{24}$/.test(pairId) || !pairSecret) {
    throw new SessionHttpError("Telegram pairing request is invalid or expired", 404);
  }
  const row = await env.DB.prepare(
    `SELECT secret_hash, user_id, expires_at
     FROM wukong_telegram_pairings WHERE pair_id = ?`
  ).bind(pairId).first<{ secret_hash: string; user_id: string; expires_at: number }>();
  const suppliedHash = await sha256Hex(pairSecret);
  if (
    !row ||
    Number(row.expires_at) < Math.floor(Date.now() / 1000) ||
    !constantTimeHexEqual(suppliedHash, row.secret_hash)
  ) {
    throw new SessionHttpError("Telegram pairing request is invalid or expired", 404);
  }
  if (!row.user_id) return { payload: { status: "pending" }, status: 202 };
  return {
    payload: {
      status: "confirmed",
      launchToken: await issueLaunchToken(row.user_id, env.WUKONG_TELEGRAM_BOT_TOKEN)
    },
    status: 200
  };
}

export async function sourceDraft(env: Env, subject: string): Promise<string> {
  const minimum = Math.floor(Date.now() / 1000) - 24 * 60 * 60;
  const row = await env.DB.prepare(
    `SELECT uri FROM wukong_telegram_source_drafts
     WHERE subject = ? AND updated_at >= ?`
  ).bind(subject, minimum).first<{ uri: string }>();
  return row?.uri ?? "";
}

export async function rememberSourceDraft(
  env: Env,
  subject: string,
  uriValue: string
): Promise<boolean> {
  const uri = uriValue.trim();
  if (!uri || uri.length > 8192) return false;
  try {
    const parsed = new URL(uri);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
      return false;
    }
  } catch {
    return false;
  }
  await env.DB.prepare(
    `INSERT INTO wukong_telegram_source_drafts (subject, uri, updated_at)
     VALUES (?, ?, ?) ON CONFLICT (subject) DO UPDATE SET
       uri = excluded.uri, updated_at = excluded.updated_at`
  ).bind(subject, uri, Math.floor(Date.now() / 1000)).run();
  return true;
}

export async function clearSourceDraft(env: Env, subject: string): Promise<void> {
  await env.DB.prepare("DELETE FROM wukong_telegram_source_drafts WHERE subject = ?")
    .bind(subject)
    .run();
}

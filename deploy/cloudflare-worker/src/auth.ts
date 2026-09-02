import { bytes, constantTimeHexEqual, hmacHex, hmacSha256 } from "./crypto";
import {
  type ObservedTelegramUser,
  type TelegramProfile,
  observeUser,
  profile
} from "./state";

const TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS = 60 * 60;
// Telegram terminal messages can remain in a chat for a while.  The ticket
// only authorizes resolving the DC Cloud URI (the resulting URL is still
// short-lived), so keep it valid long enough for a user to open an older
// notification without making it permanent.
const DCCLOUD_DOWNLOAD_TICKET_MAX_AGE_SECONDS = 24 * 60 * 60;

export interface AuthenticatedRequest {
  subject: string;
  role: "admin" | "user";
  profile: TelegramProfile;
}

function authError(message: string): Error {
  return new Error(message);
}

async function validateInitData(initData: string, botToken: string): Promise<ObservedTelegramUser> {
  if (!initData || new TextEncoder().encode(initData).byteLength > 16384) {
    throw authError("Telegram Mini App authentication is missing");
  }
  const pairs = new URLSearchParams(initData);
  const values = new Map<string, string>();
  for (const [key, value] of pairs.entries()) {
    if (values.has(key)) {
      throw authError("Telegram Mini App authentication contains duplicate fields");
    }
    values.set(key, value);
  }
  const suppliedHash = (values.get("hash") ?? "").toLowerCase();
  values.delete("hash");
  if (!/^[0-9a-f]{64}$/.test(suppliedHash)) {
    throw authError("Telegram Mini App signature is invalid");
  }
  const dataCheck = [...values.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  const secret = await hmacSha256(bytes("WebAppData"), botToken);
  const expected = await hmacHex(secret, dataCheck);
  if (!constantTimeHexEqual(suppliedHash, expected)) {
    throw authError("Telegram Mini App signature is invalid");
  }
  const authDate = Number(values.get("auth_date"));
  const current = Math.floor(Date.now() / 1000);
  if (!Number.isSafeInteger(authDate)) {
    throw authError("Telegram Mini App auth_date is invalid");
  }
  if (authDate > current + 60 || current - authDate > 3600) {
    throw authError("Telegram Mini App authentication has expired");
  }
  try {
    const user = JSON.parse(values.get("user") ?? "") as ObservedTelegramUser;
    if (!user || !Number.isSafeInteger(user.id) || user.id <= 0) {
      throw new Error("invalid");
    }
    return user;
  } catch {
    throw authError("Telegram Mini App user is invalid");
  }
}

async function validateLaunchToken(token: string, botToken: string): Promise<string> {
  const parts = token.split(".");
  if (
    parts.length !== 5 ||
    parts[0] !== "v1" ||
    !parts.slice(1, 4).every((value) => /^[0-9]+$/.test(value ?? "")) ||
    !/^[0-9a-f]{64}$/i.test(parts[4] ?? "")
  ) {
    throw authError("Telegram launch signature is invalid");
  }
  const payload = parts.slice(0, 4).join(".");
  const launchKey = await hmacSha256(bytes("WukongMiniAppLaunch\0"), botToken);
  const expected = await hmacHex(launchKey, payload);
  if (!constantTimeHexEqual((parts[4] ?? "").toLowerCase(), expected)) {
    throw authError("Telegram launch signature is invalid");
  }
  const subject = Number(parts[1]);
  const issuedAt = Number(parts[2]);
  const expiresAt = Number(parts[3]);
  const current = Math.floor(Date.now() / 1000);
  if (
    !Number.isSafeInteger(subject) ||
    subject <= 0 ||
    !Number.isSafeInteger(issuedAt) ||
    !Number.isSafeInteger(expiresAt) ||
    issuedAt > current + 60 ||
    expiresAt <= issuedAt
  ) {
    throw authError("Telegram launch signature is invalid");
  }
  if (expiresAt - issuedAt > TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS || current > expiresAt) {
    throw authError("Telegram launch authentication has expired");
  }
  return String(subject);
}

export async function issueLaunchToken(
  subjectValue: string | number,
  botToken: string,
  now = Math.floor(Date.now() / 1000)
): Promise<string> {
  const subject = Number(subjectValue);
  if (!Number.isSafeInteger(subject) || subject <= 0 || !botToken) {
    throw new Error("Telegram launch user is invalid");
  }
  const issuedAt = Math.floor(now);
  const expiresAt = issuedAt + TELEGRAM_LAUNCH_TOKEN_MAX_AGE_SECONDS;
  const payload = `v1.${subject}.${issuedAt}.${expiresAt}`;
  const key = await hmacSha256(bytes("WukongMiniAppLaunch\0"), botToken);
  return `${payload}.${await hmacHex(key, payload)}`;
}

export async function validateArtifactDownloadTicket(
  jobId: string,
  ticket: string,
  botToken: string
): Promise<string> {
  const parts = ticket.split(".");
  if (
    !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(jobId) ||
    parts.length !== 4 ||
    parts[0] !== "v1" ||
    !/^[1-9][0-9]*$/.test(parts[1] ?? "") ||
    !/^[0-9]+$/.test(parts[2] ?? "") ||
    !/^[0-9a-f]{64}$/i.test(parts[3] ?? "")
  ) {
    throw authError("Artifact download ticket is invalid");
  }
  const payload = parts.slice(0, 3).join(".");
  const key = await hmacSha256(bytes("WukongMiniAppLaunch\0"), botToken);
  const expected = await hmacHex(key, `download\0${jobId}\0${payload}`);
  if (
    !constantTimeHexEqual((parts[3] ?? "").toLowerCase(), expected) ||
    Number(parts[2]) < Math.floor(Date.now() / 1000)
  ) {
    throw authError("Artifact download ticket is invalid or expired");
  }
  return parts[1]!;
}

/**
 * Issue a public, narrowly-scoped ticket for resolving one DC Cloud file.
 * The artifact index is part of the signed payload so a ticket cannot be
 * moved to another artifact in the same job.
 */
export async function issueDcCloudArtifactDownloadTicket(
  jobId: string,
  artifactIndex: number,
  botToken: string,
  now = Math.floor(Date.now() / 1000)
): Promise<string> {
  if (
    !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(jobId)
    || !Number.isSafeInteger(artifactIndex)
    || artifactIndex < 0
    || !botToken
  ) {
    throw new Error("DC Cloud artifact download ticket is invalid");
  }
  const issuedAt = Math.floor(now);
  const expiresAt = issuedAt + DCCLOUD_DOWNLOAD_TICKET_MAX_AGE_SECONDS;
  const payload = `v1.${artifactIndex}.${expiresAt}`;
  const key = await hmacSha256(bytes("WukongMiniAppLaunch\0"), botToken);
  const signature = await hmacHex(key, `dccloud-download\0${jobId}\0${payload}`);
  return `${payload}.${signature}`;
}

/** Validate a public DC Cloud ticket and return its signed artifact index. */
export async function validateDcCloudArtifactDownloadTicket(
  jobId: string,
  ticket: string,
  botToken: string
): Promise<number> {
  const parts = ticket.split(".");
  if (
    !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(jobId)
    || parts.length !== 4
    || parts[0] !== "v1"
    || !/^[0-9]+$/.test(parts[1] ?? "")
    || !/^[0-9]+$/.test(parts[2] ?? "")
    || !/^[0-9a-f]{64}$/i.test(parts[3] ?? "")
  ) {
    throw authError("DC Cloud artifact download ticket is invalid");
  }
  const artifactIndex = Number(parts[1]);
  const expiresAt = Number(parts[2]);
  if (!Number.isSafeInteger(artifactIndex) || !Number.isSafeInteger(expiresAt)) {
    throw authError("DC Cloud artifact download ticket is invalid");
  }
  const payload = parts.slice(0, 3).join(".");
  const key = await hmacSha256(bytes("WukongMiniAppLaunch\0"), botToken);
  const expected = await hmacHex(key, `dccloud-download\0${jobId}\0${payload}`);
  if (
    !constantTimeHexEqual((parts[3] ?? "").toLowerCase(), expected)
    || expiresAt < Math.floor(Date.now() / 1000)
  ) {
    throw authError("DC Cloud artifact download ticket is invalid or expired");
  }
  return artifactIndex;
}

export async function authenticate(request: Request, env: Env): Promise<AuthenticatedRequest> {
  const authorization = request.headers.get("Authorization") ?? "";
  const separator = authorization.indexOf(" ");
  if (separator <= 0) {
    throw authError("Telegram Mini App authentication is required");
  }
  const scheme = authorization.slice(0, separator).toLowerCase();
  const credential = authorization.slice(separator + 1).trim();
  let subject = "";
  let currentProfile: TelegramProfile | null = null;
  if (scheme === "tma") {
    const user = await validateInitData(credential, env.WUKONG_TELEGRAM_BOT_TOKEN);
    subject = String(user.id);
    currentProfile = await observeUser(env, user, request);
  } else if (scheme === "wla") {
    subject = await validateLaunchToken(credential, env.WUKONG_TELEGRAM_BOT_TOKEN);
    currentProfile = await profile(env, subject);
  } else {
    throw authError("Telegram Mini App authentication is required");
  }
  if (!currentProfile) {
    throw authError("Telegram profile is unavailable");
  }
  return {
    subject,
    role: currentProfile.role,
    profile: currentProfile
  };
}

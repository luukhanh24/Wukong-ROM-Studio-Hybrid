const encoder = new TextEncoder();

function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function hmac(key: BufferSource, value: string): Promise<ArrayBuffer> {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(value));
}

export async function signedInitData(
  userId: number,
  extra: Record<string, unknown> = {}
): Promise<string> {
  const user = JSON.stringify({
    id: userId,
    first_name: "Fixture",
    language_code: "vi",
    ...extra
  });
  const values = new URLSearchParams({
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: `fixture-${userId}`,
    user
  });
  const dataCheck = [...values.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  const secret = await hmac(encoder.encode("WebAppData"), "123456789:fixture_bot_secret_value");
  values.set("hash", hex(await hmac(secret, dataCheck)));
  return values.toString();
}

export async function tmaHeaders(
  userId: number,
  extra: Record<string, unknown> = {}
): Promise<Record<string, string>> {
  return {
    Origin: "https://wukong-rom-studio.vercel.app",
    Authorization: `tma ${await signedInitData(userId, extra)}`,
    "X-Wukong-Session-Id": `fixture-session-${userId}`,
    "X-Wukong-Client-Version": "worker-tests",
    "X-Telegram-Platform": "android"
  };
}

export async function actionsHeaders(body: string): Promise<Record<string, string>> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const key = await hmac(
    new TextEncoder().encode("WukongActionsCallback\0"),
    "fixture-actions-callback-secret-value"
  );
  return {
    "Content-Type": "application/json",
    "X-Wukong-Timestamp": timestamp,
    "X-Wukong-Signature": hex(await hmac(key, `${timestamp}.${body}`))
  };
}

const encoder = new TextEncoder();

export function bytes(value: string): Uint8Array {
  return encoder.encode(value);
}

export function hex(value: ArrayBuffer): string {
  return [...new Uint8Array(value)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function hmacSha256(key: BufferSource, value: string): Promise<ArrayBuffer> {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
  return crypto.subtle.sign("HMAC", cryptoKey, bytes(value));
}

export async function hmacHex(key: BufferSource, value: string): Promise<string> {
  return hex(await hmacSha256(key, value));
}

export function constantTimeHexEqual(left: string, right: string): boolean {
  if (!/^[0-9a-f]+$/i.test(left) || left.length !== right.length || left.length % 2 !== 0) {
    return false;
  }
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

export async function sha256Hex(value: string | ArrayBuffer): Promise<string> {
  const body = typeof value === "string" ? bytes(value) : value;
  return hex(await crypto.subtle.digest("SHA-256", body));
}

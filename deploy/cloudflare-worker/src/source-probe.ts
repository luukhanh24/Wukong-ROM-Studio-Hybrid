const MAX_REDIRECTS = 5;
const SESSION_SECONDS = 120;
const MAX_REQUESTS = 64;
const MAX_SESSION_BYTES = 16 * 1024 * 1024;
const MAX_RANGE_BYTES = 8 * 1024 * 1024;

type JsonObject = Record<string, unknown>;

export class SourceProbeHttpError extends Error {
  constructor(
    message: string,
    readonly status = 400,
    readonly code = "source_unreachable"
  ) {
    super(message);
  }
}

function parseIpv4(value: string): number[] | null {
  const parts = value.split(".");
  if (parts.length !== 4) return null;
  const octets = parts.map((part) => Number(part));
  if (octets.some((part, index) =>
    !/^(0|[1-9][0-9]{0,2})$/.test(parts[index] ?? "") ||
    !Number.isInteger(part) ||
    part < 0 ||
    part > 255
  )) return null;
  return octets;
}

export function isPrivateOrSpecialAddress(value: string): boolean {
  const normalized = value.trim().toLowerCase().replace(/^\[|\]$/g, "");
  const ipv4 = parseIpv4(normalized);
  if (ipv4) {
    const [a, b] = ipv4;
    return (
      a === 0 ||
      a === 10 ||
      a === 127 ||
      (a === 100 && b! >= 64 && b! <= 127) ||
      (a === 169 && b === 254) ||
      (a === 172 && b! >= 16 && b! <= 31) ||
      (a === 192 && b === 0) ||
      (a === 192 && b === 168) ||
      (a === 198 && (b === 18 || b === 19)) ||
      a! >= 224
    );
  }
  if (!normalized.includes(":")) return false;
  if (
    normalized === "::" ||
    normalized === "::1" ||
    normalized.startsWith("fc") ||
    normalized.startsWith("fd") ||
    /^fe[89ab]/.test(normalized) ||
    normalized.startsWith("ff") ||
    normalized.startsWith("2001:db8:")
  ) return true;
  const mapped = normalized.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  return mapped ? isPrivateOrSpecialAddress(mapped[1]!) : false;
}

function validatedUrl(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new SourceProbeHttpError("A valid ROM source URL is required");
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    (url.port && !["80", "443"].includes(url.port))
  ) {
    throw new SourceProbeHttpError("ROM source must use HTTP or HTTPS on port 80/443");
  }
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (
    !host ||
    host === "localhost" ||
    host.endsWith(".localhost") ||
    isPrivateOrSpecialAddress(host)
  ) {
    throw new SourceProbeHttpError("ROM source resolves to a private or local destination");
  }
  return url;
}

interface DnsJson {
  Status?: number;
  Answer?: Array<{ type?: number; data?: string }>;
}

async function dnsAddresses(hostname: string): Promise<string[]> {
  if (parseIpv4(hostname) || hostname.includes(":")) return [hostname];
  const query = async (type: "A" | "AAAA"): Promise<string[]> => {
    const url = new URL("https://cloudflare-dns.com/dns-query");
    url.searchParams.set("name", hostname);
    url.searchParams.set("type", type);
    const response = await fetch(url, {
      headers: { Accept: "application/dns-json" },
      redirect: "manual"
    });
    if (!response.ok) throw new SourceProbeHttpError("ROM source DNS lookup failed");
    const payload = await response.json() as DnsJson;
    if (payload.Status !== 0) throw new SourceProbeHttpError("ROM source DNS lookup failed");
    return (payload.Answer ?? [])
      .filter((answer) => answer.type === 1 || answer.type === 28)
      .map((answer) => String(answer.data ?? "").trim())
      .filter(Boolean);
  };
  const addresses = (await Promise.all([query("A"), query("AAAA")])).flat();
  if (!addresses.length) throw new SourceProbeHttpError("ROM source hostname has no public address");
  return [...new Set(addresses)];
}

async function validateDestination(value: string): Promise<URL> {
  const url = validatedUrl(value);
  const addresses = await dnsAddresses(url.hostname.toLowerCase().replace(/^\[|\]$/g, ""));
  if (addresses.some(isPrivateOrSpecialAddress)) {
    throw new SourceProbeHttpError("ROM source resolves to a private or local destination");
  }
  return url;
}

async function secureFetch(
  initialUrl: string,
  init: RequestInit,
  initialDestinationValidated = false
): Promise<{ response: Response; url: URL }> {
  let url = initialDestinationValidated
    ? validatedUrl(initialUrl)
    : await validateDestination(initialUrl);
  for (let redirectCount = 0; redirectCount <= MAX_REDIRECTS; redirectCount += 1) {
    const response = await fetch(url, { ...init, redirect: "manual" });
    if (![301, 302, 303, 307, 308].includes(response.status)) {
      return { response, url };
    }
    const location = response.headers.get("Location");
    if (!location) throw new SourceProbeHttpError("ROM source redirect is missing a destination");
    if (redirectCount === MAX_REDIRECTS) {
      throw new SourceProbeHttpError("ROM source has too many redirects");
    }
    await response.body?.cancel();
    url = await validateDestination(new URL(location, url).toString());
  }
  throw new SourceProbeHttpError("ROM source has too many redirects");
}

function contentSize(response: Response): number | null {
  const range = response.headers.get("Content-Range");
  const rangeMatch = range?.match(/\/([0-9]+)$/);
  const raw = rangeMatch?.[1] ?? response.headers.get("Content-Length") ?? "";
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function filenameFrom(response: Response, url: URL): string {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded).replace(/[\\/\u0000-\u001f]/g, "_").slice(0, 255);
    } catch {
      // Fall through to the plain filename or URL path.
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]?.trim();
  const pathName = decodeURIComponent(url.pathname.split("/").pop() || "rom.zip");
  return (plain || pathName).replace(/[\\/\u0000-\u001f]/g, "_").slice(0, 255);
}

function checksumHeader(response: Response): string {
  const contentMd5 = response.headers.get("Content-MD5")?.trim();
  if (contentMd5) return contentMd5;
  const oplusMd5 = response.headers.get("X-Amz-Meta-Filemd5")?.trim();
  if (oplusMd5) return oplusMd5;
  const googleHash = response.headers.get("X-Goog-Hash") ?? "";
  return googleHash.split(",").map((value) => value.trim())
    .find((value) => value.toLowerCase().startsWith("md5="))
    ?.slice(4) ?? "";
}

function signedUrlExpiry(url: URL): number | null {
  const epoch = Number(url.searchParams.get("expires") ?? url.searchParams.get("Expires"));
  if (Number.isSafeInteger(epoch) && epoch > 0) return epoch > 10_000_000_000 ? Math.floor(epoch / 1000) : epoch;
  const date = url.searchParams.get("X-Amz-Date") ?? url.searchParams.get("X-Goog-Date");
  const seconds = Number(url.searchParams.get("X-Amz-Expires") ?? url.searchParams.get("X-Goog-Expires"));
  const match = date?.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (!match || !Number.isSafeInteger(seconds) || seconds <= 0) return null;
  const issued = Date.UTC(
    Number(match[1]), Number(match[2]) - 1, Number(match[3]),
    Number(match[4]), Number(match[5]), Number(match[6])
  ) / 1000;
  return Math.floor(issued + seconds);
}

function providerFor(hostname: string): string {
  const host = hostname.toLowerCase();
  if (host.includes("google") || host.includes("drive")) return "Google Drive";
  if (host.includes("oplus") || host.includes("allawn")) return "OPlus OTA";
  return "HTTP";
}

export async function createProbeSession(
  request: Request,
  env: Env,
  value: unknown,
  ownerSubject = ""
): Promise<JsonObject> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new SourceProbeHttpError("A valid ROM source URL is required");
  }
  const uri = String((value as JsonObject).uri ?? "").trim();
  if (!uri || uri.length > 8192) {
    throw new SourceProbeHttpError("A valid ROM source URL is required");
  }
  let result = await secureFetch(uri, {
    method: "HEAD",
    headers: {
      "Accept-Encoding": "identity",
      "User-Agent": "Wukong-ROM-Studio/1.0"
    }
  });
  const initialContentType = result.response.headers.get("Content-Type")?.toLowerCase() ?? "";
  const resolverPath = new URL(uri).pathname.toLowerCase().replace(/\/$/, "");
  if (
    [403, 405, 501].includes(result.response.status) ||
    initialContentType.includes("json") ||
    resolverPath.endsWith("/downloadcheck")
  ) {
    await result.response.body?.cancel();
    result = await secureFetch(uri, {
      method: "GET",
      headers: {
        Range: "bytes=0-0",
        "Accept-Encoding": "identity",
        "User-Agent": "Wukong-ROM-Studio/1.0"
      }
    });
  }
  if (!result.response.ok && result.response.status !== 206) {
    throw new SourceProbeHttpError(`ROM source returned HTTP ${result.response.status}`);
  }
  if (
    resolverPath.endsWith("/downloadcheck") &&
    result.response.headers.get("Content-Type")?.toLowerCase().includes("json")
  ) {
    await result.response.body?.cancel();
    throw new SourceProbeHttpError("OPlus OTA resolver did not return a ROM download");
  }
  const expiresAt = signedUrlExpiry(result.url);
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (expiresAt && expiresAt <= nowSeconds) {
    throw new SourceProbeHttpError(
      "The signed ROM download URL has expired",
      400,
      "source_signed_url_expired"
    );
  }
  const sessionId = crypto.randomUUID().replaceAll("-", "");
  const filename = filenameFrom(result.response, result.url);
  const sizeBytes = contentSize(result.response);
  const contentType = result.response.headers.get("Content-Type")?.split(";", 1)[0]?.trim() ?? "";
  const checksum = checksumHeader(result.response);
  const createdAt = nowSeconds;
  await env.DB.prepare(
    `INSERT INTO wukong_source_probe_sessions
     (session_id, owner_subject, source_url, resolved_url, resolved_host,
      filename, content_type, size_bytes, checksum_header, signed_url_expires_at,
      created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    sessionId,
    ownerSubject,
    uri,
    result.url.toString(),
    result.url.hostname,
    filename,
    contentType,
    sizeBytes,
    checksum,
    expiresAt ? new Date(expiresAt * 1000).toISOString() : "",
    createdAt,
    createdAt + SESSION_SECONDS
  ).run();
  return {
    provider: providerFor(result.url.hostname),
    filename,
    resolvedHost: result.url.hostname,
    host: result.url.hostname,
    sizeBytes,
    contentType: contentType || null,
    etag: result.response.headers.get("ETag"),
    lastModified: result.response.headers.get("Last-Modified"),
    md5: checksum || null,
    checksumHeader: checksum || null,
    productName: null,
    device: null,
    version: null,
    androidVersion: null,
    securityPatch: null,
    buildDate: null,
    otaType: null,
    deepInspected: false,
    warning: null,
    signedUrlExpiresAt: expiresAt,
    cloudBuildReady: true,
    rangeSession: {
      id: sessionId,
      url: new URL(`/v1/sources/probe/${sessionId}/range`, request.url).toString(),
      expiresIn: SESSION_SECONDS,
      maxRequests: MAX_REQUESTS,
      maxBytes: MAX_SESSION_BYTES,
      maxRangeBytes: MAX_RANGE_BYTES
    }
  };
}

function requestedRange(value: string | null): { start: number; end: number; length: number } {
  const match = value?.match(/^bytes=([0-9]+)-([0-9]+)$/);
  if (!match) throw new SourceProbeHttpError("A single explicit byte range is required", 416);
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 0 ||
    end < start ||
    end - start + 1 > MAX_RANGE_BYTES
  ) {
    throw new SourceProbeHttpError("Requested ROM range is too large", 416);
  }
  return { start, end, length: end - start + 1 };
}

async function limitedBody(response: Response, maximum: number): Promise<ArrayBuffer> {
  if (!response.body) return new ArrayBuffer(0);
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximum) {
      await reader.cancel();
      throw new SourceProbeHttpError("ROM source ignored the requested range", 502);
    }
    chunks.push(value);
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

export async function proxyProbeRange(
  request: Request,
  env: Env,
  sessionId: string
): Promise<Response> {
  if (!/^[0-9a-f]{32}$/.test(sessionId)) {
    throw new SourceProbeHttpError("ROM probe session was not found", 404);
  }
  const range = requestedRange(request.headers.get("Range"));
  const now = Math.floor(Date.now() / 1000);
  const session = await env.DB.prepare(
    `SELECT * FROM wukong_source_probe_sessions WHERE session_id = ?`
  ).bind(sessionId).first<Record<string, unknown>>();
  if (!session) throw new SourceProbeHttpError("ROM probe session was not found", 404);
  if (Number(session.expires_at) < now) {
    throw new SourceProbeHttpError("ROM probe session has expired", 410);
  }
  const knownSize = session.size_bytes == null ? null : Number(session.size_bytes);
  if (knownSize != null && range.end >= knownSize) {
    throw new SourceProbeHttpError("Requested ROM range is outside the source", 416);
  }
  const reserved = await env.DB.prepare(
    `UPDATE wukong_source_probe_sessions
     SET request_count = request_count + 1, bytes_served = bytes_served + ?
     WHERE session_id = ? AND expires_at >= ?
       AND request_count < ? AND bytes_served + ? <= ?`
  ).bind(
    range.length, sessionId, now, MAX_REQUESTS, range.length, MAX_SESSION_BYTES
  ).run();
  if ((reserved.meta.changes ?? 0) !== 1) {
    throw new SourceProbeHttpError("ROM probe session budget is exhausted", 429);
  }
  // The resolved URL was DNS-validated, redirect-by-redirect, when this
  // short-lived session was created. Reuse that result for its first hop;
  // any new redirect destination is still validated before it is fetched.
  const result = await secureFetch(String(session.resolved_url), {
    method: "GET",
    headers: {
      Range: `bytes=${range.start}-${range.end}`,
      "Accept-Encoding": "identity",
      "User-Agent": "Wukong-ROM-Studio/1.0"
    }
  }, true);
  if (result.response.status !== 206) {
    const declared = Number(result.response.headers.get("Content-Length") ?? 0);
    if (!declared || declared > range.length) {
      throw new SourceProbeHttpError("ROM source does not support safe byte ranges", 502);
    }
  }
  const body = await limitedBody(result.response, range.length);
  if (body.byteLength > range.length) {
    throw new SourceProbeHttpError("ROM source returned an oversized range", 502);
  }
  const total = knownSize ?? "*";
  return new Response(body, {
    status: 206,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": String(session.content_type || "application/octet-stream"),
      "Accept-Ranges": "bytes",
      "Content-Range": result.response.headers.get("Content-Range")
        ?? `bytes ${range.start}-${range.start + body.byteLength - 1}/${total}`,
      "Content-Length": String(body.byteLength)
    }
  });
}

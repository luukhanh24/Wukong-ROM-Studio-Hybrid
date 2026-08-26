const MAX_REDIRECTS = 5;
const SESSION_SECONDS = 120;
const MAX_REQUESTS = 64;
const MAX_SESSION_BYTES = 16 * 1024 * 1024;
const MAX_RANGE_BYTES = 8 * 1024 * 1024;
const TRANSPORT_CLAIM_SECONDS = 30;
const MAX_TRANSPORT_METADATA_BYTES = 32 * 1024;

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

function providerFor(hostname: string, originalHostname = ""): string {
  const host = hostname.toLowerCase();
  if (originalHostname.toLowerCase() === "roms.danielspringer.at") return "Daniel Springer";
  if (host.includes("google") || host.includes("drive")) return "Google Drive";
  if (host.includes("oplus") || host.includes("allawn")) return "OPlus OTA";
  return "HTTP";
}

function isDanielOtaPage(url: URL): boolean {
  return (
    url.hostname.toLowerCase() === "roms.danielspringer.at" &&
    url.pathname.toLowerCase().replace(/\/$/, "") === "/index.php" &&
    url.searchParams.get("view")?.toLowerCase() === "ota" &&
    Boolean(url.searchParams.get("build")?.trim())
  );
}

function isOplusResolver(url: URL): boolean {
  return (
    /^component-ota(?:-[a-z0-9]+)?\.allawntech\.com$/i.test(url.hostname) &&
    url.pathname.toLowerCase().replace(/\/$/, "").endsWith("/downloadcheck")
  );
}

function usesVercelTransport(url: URL): boolean {
  const host = url.hostname.toLowerCase();
  return isDanielOtaPage(url) || isOplusResolver(url) || host.endsWith(".allawnfs.com");
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)]
    .map((part) => part.toString(16).padStart(2, "0"))
    .join("");
}

async function createTransportClaim(
  request: Request,
  env: Env,
  operation: "probe" | "range",
  sourceUrl: string,
  rangeHeader: string,
  maximumBytes: number
): Promise<{ claimUrl: string; token: string }> {
  const random = crypto.getRandomValues(new Uint8Array(32));
  const token = base64Url(random);
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    `INSERT INTO wukong_source_transport_claims
     (token_hash, operation, source_url, range_header, maximum_bytes,
      created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    await sha256Hex(token), operation, sourceUrl, rangeHeader,
    maximumBytes, now, now + TRANSPORT_CLAIM_SECONDS
  ).run();
  return {
    claimUrl: new URL("/internal/source-transport/claim", request.url).toString(),
    token
  };
}

async function callSourceTransport(
  request: Request,
  env: Env,
  operation: "probe" | "range",
  sourceUrl: string,
  rangeHeader: string,
  maximumBytes: number
): Promise<Response> {
  const transport = validatedUrl(env.WUKONG_SOURCE_TRANSPORT_URL);
  if (transport.protocol !== "https:") {
    throw new SourceProbeHttpError("ROM source transport is unavailable", 503);
  }
  const claim = await createTransportClaim(
    request, env, operation, sourceUrl, rangeHeader, maximumBytes
  );
  let response: Response;
  try {
    response = await fetch(transport, {
      method: "POST",
      redirect: "manual",
      headers: {
        Accept: operation === "probe" ? "application/json" : "application/octet-stream",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(claim)
    });
  } catch {
    throw new SourceProbeHttpError("ROM source transport is unavailable", 503);
  }
  if ([301, 302, 303, 307, 308].includes(response.status)) {
    await response.body?.cancel();
    throw new SourceProbeHttpError("ROM source transport returned an unexpected redirect", 502);
  }
  if (!response.ok) {
    await response.body?.cancel();
    throw new SourceProbeHttpError("ROM source transport could not reach this link", 502);
  }
  return response;
}

export async function claimSourceTransport(request: Request, env: Env): Promise<Response> {
  const authorization = request.headers.get("Authorization") ?? "";
  const token = authorization.match(/^TransportClaim ([A-Za-z0-9_-]{43})$/)?.[1] ?? "";
  if (!token) return Response.json({ error: "Source transport claim is invalid" }, { status: 401 });
  const now = Math.floor(Date.now() / 1000);
  const tokenHash = await sha256Hex(token);
  const claimed = await env.DB.prepare(
    `UPDATE wukong_source_transport_claims
     SET claimed_at = ?
     WHERE token_hash = ? AND claimed_at = 0 AND expires_at >= ?`
  ).bind(now, tokenHash, now).run();
  if ((claimed.meta.changes ?? 0) !== 1) {
    return Response.json({ error: "Source transport claim is invalid or expired" }, { status: 410 });
  }
  const row = await env.DB.prepare(
    `SELECT operation, source_url, range_header, maximum_bytes
     FROM wukong_source_transport_claims WHERE token_hash = ?`
  ).bind(tokenHash).first<Record<string, unknown>>();
  if (!row) return Response.json({ error: "Source transport claim is unavailable" }, { status: 410 });
  return Response.json({
    operation: String(row.operation),
    sourceUrl: String(row.source_url),
    range: String(row.range_header),
    maximumBytes: Number(row.maximum_bytes)
  }, { headers: { "Cache-Control": "no-store" } });
}

function initialProbeHeaders(url: URL): HeadersInit {
  const resolver = url.pathname.toLowerCase().replace(/\/$/, "").endsWith("/downloadcheck");
  return {
    Range: "bytes=0-0",
    "Accept-Encoding": "identity",
    "User-Agent": resolver ? "okhttp/3.12.12" : "Wukong-ROM-Studio/1.0",
    ...(resolver ? {
      Accept: "*/*",
      "Cache-Control": "no-cache",
      userId: "oplus-ota|16002018"
    } : {})
  };
}

interface TransportProbeMetadata {
  resolvedUrl: string;
  filename: string;
  sizeBytes: number | null;
  contentType: string;
  checksum: string;
  etag: string | null;
  lastModified: string | null;
}

async function transportProbeMetadata(response: Response): Promise<TransportProbeMetadata> {
  const bytes = await limitedBody(response, MAX_TRANSPORT_METADATA_BYTES);
  let value: Record<string, unknown>;
  try {
    value = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
  } catch {
    throw new SourceProbeHttpError("ROM source transport returned invalid metadata", 502);
  }
  const resolvedUrl = String(value.resolvedUrl ?? "").trim();
  const url = validatedUrl(resolvedUrl);
  if (!url.hostname.toLowerCase().endsWith(".allawnfs.com")) {
    throw new SourceProbeHttpError("ROM source transport returned an unsupported destination", 502);
  }
  const rawSize = value.sizeBytes;
  const sizeBytes = rawSize == null ? null : Number(rawSize);
  if (sizeBytes != null && (!Number.isSafeInteger(sizeBytes) || sizeBytes < 0)) {
    throw new SourceProbeHttpError("ROM source transport returned invalid metadata", 502);
  }
  return {
    resolvedUrl: url.toString(),
    filename: String(value.filename ?? "rom.zip").slice(0, 255),
    sizeBytes,
    contentType: String(value.contentType ?? "").slice(0, 255),
    checksum: String(value.checksum ?? "").slice(0, 512),
    etag: value.etag == null ? null : String(value.etag).slice(0, 512),
    lastModified: value.lastModified == null ? null : String(value.lastModified).slice(0, 512)
  };
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
  const originalUrl = validatedUrl(uri);
  let resolvedUrl: URL;
  let filename: string;
  let sizeBytes: number | null;
  let contentType: string;
  let checksum: string;
  let etag: string | null;
  let lastModified: string | null;
  let transportMode: "direct" | "vercel" = "direct";
  if (usesVercelTransport(originalUrl)) {
    const transportResponse = await callSourceTransport(
      request, env, "probe", uri, "bytes=0-0", 1
    );
    const metadata = await transportProbeMetadata(transportResponse);
    resolvedUrl = validatedUrl(metadata.resolvedUrl);
    filename = metadata.filename;
    sizeBytes = metadata.sizeBytes;
    contentType = metadata.contentType;
    checksum = metadata.checksum;
    etag = metadata.etag;
    lastModified = metadata.lastModified;
    transportMode = "vercel";
  } else {
    const resolvedInput = uri;
    const probeUrl = validatedUrl(resolvedInput);
    const result = await secureFetch(resolvedInput, {
      method: "GET",
      headers: initialProbeHeaders(probeUrl)
    });
    const resolverPath = probeUrl.pathname.toLowerCase().replace(/\/$/, "");
    if (!result.response.ok && result.response.status !== 206) {
      await result.response.body?.cancel();
      throw new SourceProbeHttpError(`ROM source returned HTTP ${result.response.status}`);
    }
    if (
      resolverPath.endsWith("/downloadcheck") &&
      result.response.headers.get("Content-Type")?.toLowerCase().includes("json")
    ) {
      await result.response.body?.cancel();
      throw new SourceProbeHttpError("OPlus OTA resolver did not return a ROM download");
    }
    resolvedUrl = result.url;
    filename = filenameFrom(result.response, result.url);
    sizeBytes = contentSize(result.response);
    contentType = result.response.headers.get("Content-Type")?.split(";", 1)[0]?.trim() ?? "";
    checksum = checksumHeader(result.response);
    etag = result.response.headers.get("ETag");
    lastModified = result.response.headers.get("Last-Modified");
    await result.response.body?.cancel();
  }
  const expiresAt = signedUrlExpiry(resolvedUrl);
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (expiresAt && expiresAt <= nowSeconds) {
    throw new SourceProbeHttpError(
      "The signed ROM download URL has expired",
      400,
      "source_signed_url_expired"
    );
  }
  const sessionId = crypto.randomUUID().replaceAll("-", "");
  const createdAt = nowSeconds;
  await env.DB.prepare(
    `INSERT INTO wukong_source_probe_sessions
     (session_id, owner_subject, source_url, resolved_url, resolved_host,
      filename, content_type, size_bytes, checksum_header, signed_url_expires_at,
      created_at, expires_at, transport_mode)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    sessionId,
    ownerSubject,
    uri,
    resolvedUrl.toString(),
    resolvedUrl.hostname,
    filename,
    contentType,
    sizeBytes,
    checksum,
    expiresAt ? new Date(expiresAt * 1000).toISOString() : "",
    createdAt,
    createdAt + SESSION_SECONDS,
    transportMode
  ).run();
  return {
    provider: providerFor(resolvedUrl.hostname, originalUrl.hostname),
    filename,
    resolvedHost: resolvedUrl.hostname,
    host: resolvedUrl.hostname,
    sizeBytes,
    contentType: contentType || null,
    etag,
    lastModified,
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
  const rangeHeader = `bytes=${range.start}-${range.end}`;
  const result = String(session.transport_mode) === "vercel"
    ? {
        response: await callSourceTransport(
          request, env, "range", String(session.resolved_url), rangeHeader, range.length
        ),
        url: validatedUrl(String(session.resolved_url))
      }
    : await secureFetch(String(session.resolved_url), {
        method: "GET",
        headers: {
          Range: rangeHeader,
          "Accept-Encoding": "identity",
          "User-Agent": "Wukong-ROM-Studio/1.0"
        }
      }, true);
  if (result.response.status !== 206) {
    const declared = Number(result.response.headers.get("Content-Length") ?? 0);
    if (!declared || declared > range.length) {
      throw new SourceProbeHttpError("ROM source does not support safe byte ranges", 502);
    }
  } else {
    const contentRange = result.response.headers.get("Content-Range") ?? "";
    const match = contentRange.match(/^bytes ([0-9]+)-([0-9]+)\/(?:[0-9]+|\*)$/i);
    if (!match || Number(match[1]) !== range.start || Number(match[2]) !== range.end) {
      await result.response.body?.cancel();
      throw new SourceProbeHttpError("ROM source returned the wrong byte range", 502);
    }
  }
  const body = await limitedBody(result.response, range.length);
  if (body.byteLength !== range.length) {
    throw new SourceProbeHttpError("ROM source returned an incomplete byte range", 502);
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

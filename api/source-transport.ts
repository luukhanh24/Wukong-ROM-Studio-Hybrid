const MAX_REDIRECTS = 5;
const MAX_REQUEST_BODY = 16 * 1024;
const MAX_CLAIM_BODY = 16 * 1024;
const MAX_CATALOG_PAGE = 2 * 1024 * 1024;
const MAX_RESOLVER_BODY = 1024 * 1024;
const PRODUCTION_WORKER_ORIGINS = new Set([
  "https://wukong-control-plane.wukong-rom-studio-api.workers.dev",
  "https://wukong-control-plane-staging.wukong-rom-studio-api.workers.dev"
]);

type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type ResolveAddresses = (hostname: string) => Promise<string[]>;

interface TransportWork {
  operation: "probe" | "range" | "catalog";
  sourceUrl: string;
  range: string;
  maximumBytes: number;
}

class TransportError extends Error {
  readonly status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

function privateAddress(value: string): boolean {
  const normalized = value.toLowerCase().replace(/^\[|\]$/g, "");
  const ipv4 = normalized.split(".");
  if (ipv4.length === 4 && ipv4.every((part) => /^(0|[1-9][0-9]{0,2})$/.test(part) && Number(part) <= 255)) {
    const [a = 0, b = 0] = ipv4.map(Number);
    return a === 0 || a === 10 || a === 127 ||
      (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) || (a === 192 && (b === 0 || b === 168)) ||
      (a === 198 && (b === 18 || b === 19)) || a >= 224;
  }
  if (!normalized.includes(":")) return false;
  return normalized === "::" || normalized === "::1" || normalized.startsWith("fc") ||
    normalized.startsWith("fd") || /^fe[89ab]/.test(normalized) ||
    normalized.startsWith("ff") || normalized.startsWith("2001:db8:") ||
    normalized.startsWith("::ffff:");
}

function sourceKind(url: URL): "daniel" | "resolver" | "cdn" | "catalog" | null {
  const host = url.hostname.toLowerCase();
  const path = url.pathname.toLowerCase().replace(/\/$/, "");
  if (url.protocol === "https:" && host === "roms.danielspringer.at" && url.pathname === "/api/ota.php") return "catalog";
  if (
    host === "roms.danielspringer.at" && path === "/index.php" &&
    ((url.searchParams.get("view")?.toLowerCase() === "ota" && Boolean(url.searchParams.get("build"))) ||
      url.searchParams.get("ota_action") === "resolve_json")
  ) return "daniel";
  if (
    /^component-ota(?:-[a-z0-9]+)?\.allawntech\.com$/.test(host) &&
    path.endsWith("/downloadcheck")
  ) return "resolver";
  if (host.endsWith(".allawnfs.com")) return "cdn";
  return null;
}

function parsePublicUrl(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new TransportError("Source URL is invalid");
  }
  if (
    !["http:", "https:"].includes(url.protocol) || url.username || url.password ||
    (url.port && !["80", "443"].includes(url.port)) || !sourceKind(url)
  ) throw new TransportError("Source URL is not supported");
  if (privateAddress(url.hostname)) throw new TransportError("Source destination is not public");
  return url;
}

async function defaultResolveAddresses(hostname: string): Promise<string[]> {
  if (privateAddress(hostname) || hostname.includes(":") || /^\d+\.\d+\.\d+\.\d+$/.test(hostname)) {
    return [hostname];
  }
  const query = async (type: "A" | "AAAA"): Promise<string[]> => {
    const url = new URL("https://cloudflare-dns.com/dns-query");
    url.searchParams.set("name", hostname);
    url.searchParams.set("type", type);
    const response = await fetch(url, {
      redirect: "manual",
      headers: { Accept: "application/dns-json" }
    });
    if (!response.ok) return [];
    const payload = await response.json() as {
      Status?: number;
      Answer?: Array<{ type?: number; data?: string }>;
    };
    if (payload.Status !== 0) return [];
    return (payload.Answer ?? [])
      .filter((answer) => answer.type === 1 || answer.type === 28)
      .map((answer) => String(answer.data ?? "").trim()).filter(Boolean);
  };
  return [...new Set((await Promise.all([query("A"), query("AAAA")])).flat())];
}

async function validateDestination(value: string, resolveAddresses: ResolveAddresses): Promise<URL> {
  const url = parsePublicUrl(value);
  const addresses = await resolveAddresses(url.hostname);
  if (!addresses.length || addresses.some(privateAddress)) {
    throw new TransportError("Source destination is not public");
  }
  return url;
}

async function secureFetch(
  initial: string,
  init: RequestInit,
  fetchImpl: Fetch,
  resolveAddresses: ResolveAddresses
): Promise<{ response: Response; url: URL }> {
  let url = await validateDestination(initial, resolveAddresses);
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    const response = await fetchImpl(url, { ...init, redirect: "manual" });
    if (![301, 302, 303, 307, 308].includes(response.status)) return { response, url };
    const location = response.headers.get("Location");
    await response.body?.cancel();
    if (!location || redirects === MAX_REDIRECTS) {
      throw new TransportError("Source redirect is invalid", 502);
    }
    if (!["GET", "HEAD"].includes(String(init.method ?? "GET").toUpperCase())) {
      throw new TransportError("Source resolver returned an unexpected redirect", 502);
    }
    url = await validateDestination(new URL(location, url).toString(), resolveAddresses);
  }
  throw new TransportError("Source has too many redirects", 502);
}

async function boundedBytes(
  response: { body: ReadableStream<Uint8Array> | null },
  maximum: number
): Promise<Uint8Array> {
  if (!response.body) return new Uint8Array();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximum) {
      await reader.cancel();
      throw new TransportError("Source response is too large", 502);
    }
    chunks.push(value);
  }
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}

function decodeAttribute(tag: string, name: string): string {
  const match = tag.match(new RegExp(`${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i"));
  return (match?.[1] ?? match?.[2] ?? "")
    .replaceAll("&amp;", "&").replaceAll("&quot;", '"').replaceAll("&#39;", "'")
    .replaceAll("&lt;", "<").replaceAll("&gt;", ">");
}

function responseCookies(response: Response): string {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] };
  const values = headers.getSetCookie?.() ?? [response.headers.get("Set-Cookie") ?? ""];
  return values.map((value) => value.split(";", 1)[0]?.trim() ?? "")
    .filter((value) => /^[!#$%&'*+.^_`|~0-9A-Za-z-]+=[^;\r\n]*$/.test(value)).join("; ");
}

async function resolveDaniel(
  source: string,
  fetchImpl: Fetch,
  resolveAddresses: ResolveAddresses
): Promise<string> {
  const page = await secureFetch(source, {
    method: "GET",
    headers: {
      Accept: "text/html,application/xhtml+xml",
      "Accept-Encoding": "identity",
      "User-Agent": "Wukong-ROM-Studio/1.0"
    }
  }, fetchImpl, resolveAddresses);
  if (!page.response.ok) throw new TransportError("ROM catalog page is unavailable", 502);
  const cookies = responseCookies(page.response);
  const html = new TextDecoder("utf-8", { fatal: true }).decode(
    await boundedBytes(page.response, MAX_CATALOG_PAGE)
  );
  const tag = html.match(/<[^>]+\bid\s*=\s*["']resultBox["'][^>]*>/i)?.[0] ?? "";
  const ready = decodeAttribute(tag, "data-url").trim();
  if (ready) return (await validateDestination(ready, resolveAddresses)).toString();
  const key = decodeAttribute(tag, "data-ota-key").trim();
  const csrf = decodeAttribute(tag, "data-csrf").trim();
  if (!key || !csrf || key.length > 256 || csrf.length > 256) {
    throw new TransportError("ROM catalog resolver state is invalid", 502);
  }
  const endpoint = new URL("/index.php?view=ota&ota_action=resolve_json", page.url);
  const result = await secureFetch(endpoint.toString(), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
      Origin: "https://roms.danielspringer.at",
      Referer: page.url.toString(),
      "User-Agent": "Wukong-ROM-Studio/1.0",
      ...(cookies ? { Cookie: cookies } : {})
    },
    body: new URLSearchParams({ k: key, csrf })
  }, fetchImpl, resolveAddresses);
  const raw = await boundedBytes(result.response, MAX_RESOLVER_BODY);
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(new TextDecoder().decode(raw)) as Record<string, unknown>;
  } catch {
    throw new TransportError("ROM catalog resolver response is invalid", 502);
  }
  if (!result.response.ok || payload.ok !== true || typeof payload.url !== "string") {
    throw new TransportError("ROM catalog could not prepare the download", 502);
  }
  return (await validateDestination(payload.url, resolveAddresses)).toString();
}

function probeHeaders(url: URL): HeadersInit {
  const resolver = sourceKind(url) === "resolver";
  return {
    Range: "bytes=0-0",
    "Accept-Encoding": "identity",
    "User-Agent": resolver ? "okhttp/3.12.12" : "Wukong-ROM-Studio/1.0",
    ...(resolver ? { Accept: "*/*", "Cache-Control": "no-cache", userId: "oplus-ota|16002018" } : {})
  };
}

function sizeFrom(response: Response): number | null {
  const value = response.headers.get("Content-Range")?.match(/\/([0-9]+)$/)?.[1] ??
    response.headers.get("Content-Length") ?? "";
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function filenameFrom(response: Response, url: URL): string {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]?.trim();
  const fallback = decodeURIComponent(url.pathname.split("/").pop() || "rom.zip");
  return (plain || fallback).replace(/[\\/\u0000-\u001f]/g, "_").slice(0, 255);
}

function checksumFrom(response: Response): string {
  return response.headers.get("Content-MD5")?.trim() ||
    response.headers.get("X-Amz-Meta-Filemd5")?.trim() || "";
}

function allowedClaimOrigins(): Set<string> {
  return PRODUCTION_WORKER_ORIGINS;
}

function claimUrl(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new TransportError("Transport claim URL is invalid");
  }
  if (
    url.pathname !== "/internal/source-transport/claim" || url.search || url.hash ||
    !allowedClaimOrigins().has(url.origin)
  ) throw new TransportError("Transport claim origin is not allowed", 403);
  return url;
}

function explicitRange(value: string, maximum: number): { start: number; end: number } {
  const match = value.match(/^bytes=([0-9]+)-([0-9]+)$/);
  const start = Number(match?.[1]);
  const end = Number(match?.[2]);
  if (!match || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) ||
    start < 0 || end < start || end - start + 1 !== maximum || maximum > 8 * 1024 * 1024) {
    throw new TransportError("Transport range is invalid", 416);
  }
  return { start, end };
}

function limitedStream(body: ReadableStream<Uint8Array> | null, expected: number): ReadableStream<Uint8Array> | null {
  if (!body) return null;
  let total = 0;
  return body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      total += chunk.byteLength;
      if (total > expected) throw new TransportError("Source returned an oversized range", 502);
      controller.enqueue(chunk);
    },
    flush() {
      if (total !== expected) throw new TransportError("Source returned an incomplete range", 502);
    }
  }));
}

export function createSourceTransportHandler(dependencies: {
  fetchImpl?: Fetch;
  resolveAddresses?: ResolveAddresses;
} = {}) {
  const fetchImpl = dependencies.fetchImpl ?? fetch;
  const resolveAddresses = dependencies.resolveAddresses ?? defaultResolveAddresses;
  return async (request: Request): Promise<Response> => {
    try {
      if (request.method !== "POST") throw new TransportError("Method not allowed", 405);
      const bodyBytes = await boundedBytes(request, MAX_REQUEST_BODY);
      let input: Record<string, unknown>;
      try {
        input = JSON.parse(new TextDecoder().decode(bodyBytes)) as Record<string, unknown>;
      } catch {
        throw new TransportError("Transport request is invalid");
      }
      const url = claimUrl(String(input.claimUrl ?? ""));
      const token = String(input.token ?? "");
      if (!/^[A-Za-z0-9_-]{43}$/.test(token)) throw new TransportError("Transport token is invalid", 401);
      const claimResponse = await fetchImpl(url, {
        method: "POST",
        redirect: "manual",
        headers: { Authorization: `TransportClaim ${token}`, Accept: "application/json" }
      });
      if (!claimResponse.ok) throw new TransportError("Transport claim was rejected", 403);
      const claimBytes = await boundedBytes(claimResponse, MAX_CLAIM_BODY);
      const work = JSON.parse(new TextDecoder().decode(claimBytes)) as TransportWork;
      if (!["probe", "range", "catalog"].includes(work.operation) || !Number.isSafeInteger(work.maximumBytes)) {
        throw new TransportError("Transport claim is invalid", 403);
      }
      let source = (await validateDestination(work.sourceUrl, resolveAddresses)).toString();
      if (work.operation === "catalog") {
        const catalog = new URL(source);
        if (sourceKind(catalog) !== "catalog" || work.maximumBytes !== MAX_CATALOG_PAGE ||
          ![...catalog.searchParams.keys()].every((key) => ["device", "model", "region", "latest", "since"].includes(key)) ||
          ![...catalog.searchParams.values()].every((value) => value.length <= 128) ||
          !(catalog.searchParams.get("device") || catalog.searchParams.get("model") || catalog.search === "?latest=1")) {
          throw new TransportError("Catalog claim is invalid", 403);
        }
        const response = await fetchImpl(catalog, {
          redirect: "manual", signal: AbortSignal.timeout(15_000),
          headers: { Accept: "application/json", "User-Agent": "Wukong-ROM-Studio/1.0" }
        });
        if (!response.ok) {
          await response.body?.cancel();
          throw new TransportError("ROM catalog is unavailable", 502);
        }
        const payload = await boundedBytes(response, MAX_CATALOG_PAGE);
        return new Response(new TextDecoder().decode(payload), {
          headers: { "Content-Type": "application/json", "Cache-Control": "no-store" }
        });
      }
      if (sourceKind(new URL(source)) === "catalog") throw new TransportError("Catalog operation is required", 403);
      if (work.operation === "probe") {
        const original = new URL(source);
        if (sourceKind(original) === "daniel") {
          source = await resolveDaniel(source, fetchImpl, resolveAddresses);
        }
        const result = await secureFetch(source, {
          method: "GET",
          headers: probeHeaders(new URL(source))
        }, fetchImpl, resolveAddresses);
        if (!result.response.ok && result.response.status !== 206) {
          throw new TransportError("ROM source probe failed", 502);
        }
        if (sourceKind(new URL(source)) === "resolver" &&
          result.response.headers.get("Content-Type")?.toLowerCase().includes("json")) {
          throw new TransportError("ROM resolver did not return a download", 502);
        }
        const metadata = {
          resolvedUrl: result.url.toString(),
          filename: filenameFrom(result.response, result.url),
          sizeBytes: sizeFrom(result.response),
          contentType: result.response.headers.get("Content-Type")?.split(";", 1)[0]?.trim() ?? "",
          checksum: checksumFrom(result.response),
          etag: result.response.headers.get("ETag"),
          lastModified: result.response.headers.get("Last-Modified")
        };
        await result.response.body?.cancel();
        return Response.json(metadata, { headers: { "Cache-Control": "no-store" } });
      }
      const requested = explicitRange(work.range, work.maximumBytes);
      if (sourceKind(new URL(source)) !== "cdn") throw new TransportError("Range source is not supported", 403);
      const result = await secureFetch(source, {
        method: "GET",
        headers: {
          Range: work.range,
          "Accept-Encoding": "identity",
          "User-Agent": "Wukong-ROM-Studio/1.0"
        }
      }, fetchImpl, resolveAddresses);
      if (!result.response.ok) {
        await result.response.body?.cancel();
        throw new TransportError("ROM source range failed", 502);
      }
      const declared = Number(result.response.headers.get("Content-Length") ?? 0);
      const contentRange = result.response.headers.get("Content-Range") ?? "";
      const contentRangeMatch = contentRange.match(/^bytes ([0-9]+)-([0-9]+)\/(?:[0-9]+|\*)$/i);
      if (
        result.response.status === 206 &&
        (!contentRangeMatch || Number(contentRangeMatch[1]) !== requested.start ||
          Number(contentRangeMatch[2]) !== requested.end)
      ) {
        await result.response.body?.cancel();
        throw new TransportError("ROM source returned the wrong range", 502);
      }
      if (result.response.status !== 206 && declared !== work.maximumBytes) {
        await result.response.body?.cancel();
        throw new TransportError("ROM source does not support safe ranges", 502);
      }
      return new Response(limitedStream(result.response.body, work.maximumBytes), {
        status: 206,
        headers: {
          "Cache-Control": "no-store",
          "Content-Type": result.response.headers.get("Content-Type") ?? "application/octet-stream",
          "Content-Range": contentRange,
          "Content-Length": String(work.maximumBytes)
        }
      });
    } catch (error) {
      const status = error instanceof TransportError ? error.status : 502;
      const message = error instanceof TransportError ? error.message : "Source transport failed";
      return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
    }
  };
}

const handle = createSourceTransportHandler();

declare const process: { env: Record<string, string | undefined> };

export default {
  async fetch(request: Request): Promise<Response> {
    const response = await handle(request);
    const headers = new Headers(response.headers);
    headers.set("X-Wukong-Release", process.env.VERCEL_GIT_COMMIT_SHA ?? "development");
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers
    });
  }
};

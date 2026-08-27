const DANIEL_API = "https://roms.danielspringer.at/api/ota.php";
const QUERY_KEYS = ["device", "region", "model", "latest", "since"] as const;
const MAX_RELEASES = 200;
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

type UpstreamRelease = Record<string, unknown>;

export class RomCatalogHttpError extends Error {
  constructor(
    message: string,
    readonly status = 502
  ) {
    super(message);
  }
}

function stringValue(value: unknown, maximum = 512): string {
  return typeof value === "string" ? value.trim().slice(0, maximum) : "";
}

function numberValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function dateValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? new Date(parsed).toISOString() : "";
  }
  const numeric = numberValue(value);
  if (numeric === null) return "";
  const milliseconds = numeric < 10_000_000_000 ? numeric * 1000 : numeric;
  const date = new Date(milliseconds);
  return Number.isFinite(date.getTime()) ? date.toISOString() : "";
}

function httpUrl(value: unknown): string {
  const raw = stringValue(value, 4096);
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
}

function normalizeRelease(row: UpstreamRelease): Record<string, unknown> | null {
  if (!row || typeof row !== "object") return null;
  const sourceUrl = httpUrl(row.source_url);
  if (!sourceUrl) return null;
  return {
    id: stringValue(row.id, 128),
    device: stringValue(row.device, 128),
    region: stringValue(row.region, 64),
    model: stringValue(row.model, 128),
    version: stringValue(row.version, 256),
    otaVersion: stringValue(row.ota_version, 256),
    buildTimestamp: dateValue(row.build_timestamp),
    securityPatch: stringValue(row.security_patch, 64),
    md5: stringValue(row.md5, 128),
    sizeBytes: numberValue(row.size),
    publishedAt: dateValue(row.published),
    versionCode: stringValue(String(row.version_code ?? ""), 128),
    sourceUrl,
    changelogUrl: httpUrl(row.changelog_url),
    latest: row.is_latest === true || row.is_latest === 1 || row.is_latest === "1"
  };
}

function releaseRows(payload: unknown): UpstreamRelease[] {
  if (Array.isArray(payload)) return payload as UpstreamRelease[];
  if (!payload || typeof payload !== "object") return [];
  const record = payload as Record<string, unknown>;
  for (const key of ["data", "releases", "results"]) {
    if (Array.isArray(record[key])) return record[key] as UpstreamRelease[];
  }
  return [];
}

export async function romCatalog(request: Request): Promise<Record<string, unknown>> {
  const input = new URL(request.url);
  const upstream = new URL(DANIEL_API);
  for (const key of QUERY_KEYS) {
    const value = input.searchParams.get(key)?.trim() ?? "";
    if (!value) continue;
    if (value.length > 128) throw new RomCatalogHttpError(`${key} filter is too long`, 400);
    if (key === "latest" && !["0", "1"].includes(value)) {
      throw new RomCatalogHttpError("latest filter must be 0 or 1", 400);
    }
    upstream.searchParams.set(key, value);
  }
  if (!upstream.searchParams.has("latest")) upstream.searchParams.set("latest", "1");
  if (!upstream.searchParams.has("device") && !upstream.searchParams.has("model")) {
    throw new RomCatalogHttpError("Enter a device or model filter", 400);
  }
  const cacheKey = new Request(`https://rom-catalog-cache.wukong.invalid/v1?${upstream.searchParams}`);
  const cached = await caches.default.match(cacheKey);
  if (cached) return await cached.json() as Record<string, unknown>;

  let response: Response;
  try {
    response = await fetch(upstream, {
      redirect: "manual",
      headers: {
        Accept: "application/json",
        "User-Agent": "Wukong-ROM-Studio/1.0"
      },
      signal: AbortSignal.timeout(8_000)
    });
  } catch {
    throw new RomCatalogHttpError("ROM catalog source is temporarily unavailable", 503);
  }
  if (!response.ok) {
    throw new RomCatalogHttpError(`ROM catalog source returned HTTP ${response.status}`, 502);
  }
  const contentLength = Number(response.headers.get("Content-Length") || 0);
  if (contentLength > MAX_RESPONSE_BYTES) {
    await response.body?.cancel();
    throw new RomCatalogHttpError("ROM catalog response is too large", 502);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new RomCatalogHttpError("ROM catalog response is empty");
  const decoder = new TextDecoder();
  let text = "";
  let bytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    bytes += value.byteLength;
    if (bytes > MAX_RESPONSE_BYTES) {
      await reader.cancel();
      throw new RomCatalogHttpError("ROM catalog response is too large", 502);
    }
    text += decoder.decode(value, { stream: true });
  }
  text += decoder.decode();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new RomCatalogHttpError("ROM catalog source returned invalid JSON", 502);
  }
  const releases = releaseRows(payload)
    .slice(0, MAX_RELEASES)
    .map(normalizeRelease)
    .filter((release): release is Record<string, unknown> => release !== null);
  const result = {
    source: "daniel-springer",
    fetchedAt: new Date().toISOString(),
    releases,
    truncated: releaseRows(payload).length > MAX_RELEASES
  };
  await caches.default.put(cacheKey, Response.json(result, {
    headers: { "Cache-Control": "public, max-age=900" }
  }));
  return result;
}

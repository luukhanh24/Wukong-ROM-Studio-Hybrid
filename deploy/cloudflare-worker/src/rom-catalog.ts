import { callSourceTransport } from "./source-probe";

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

function deviceChoices(rows: UpstreamRelease[]) {
  const devices = new Map<string, { id: string; label: string; brand: string; regions: Map<string, Set<string>> }>();
  const words: Record<string, string> = { OP: "OnePlus", PRO: "Pro", ULTRA: "Ultra", ACE: "Ace", FIND: "Find", RENO: "Reno", NORD: "Nord", PAD: "Pad", OPEN: "Open", TURBO: "Turbo", LITE: "Lite", RACING: "Racing", GO: "Go", REALME: "Realme", REDMI: "Redmi", XIAOMI: "Xiaomi" };
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const id = stringValue(row.device, 128);
    if (!id) continue;
    const key = id.toUpperCase();
    if (!devices.has(key)) {
      if (devices.size >= 512) throw new RomCatalogHttpError("Device catalog is too large");
      const label = id.split(/\s+/).map((word) => words[word.toUpperCase()] || word).join(" ");
      const brand = /^(OnePlus|OPPO|Realme|Xiaomi|Redmi|POCO)\b/i.exec(label)?.[1] || "Other";
      devices.set(key, { id, label, brand, regions: new Map() });
    }
    const device = devices.get(key)!;
    const region = stringValue(row.region, 64).toUpperCase();
    const model = stringValue(row.model, 128);
    if (region) {
      if (!device.regions.has(region)) device.regions.set(region, new Set());
      if (model) device.regions.get(region)!.add(model);
    }
  }
  return [...devices.values()]
    .sort((a, b) => a.brand.localeCompare(b.brand) || a.label.localeCompare(b.label, "en", { numeric: true }))
    .map((device) => ({ ...device, regions: [...device.regions.entries()].sort(([a], [b]) => a.localeCompare(b))
      .map(([code, models]) => ({ code, models: [...models].sort() })) }));
}

export async function romCatalog(request: Request, env: Env): Promise<Record<string, unknown>> {
  const input = new URL(request.url);
  const devicesOnly = input.pathname === "/v1/rom-catalog/devices";
  const upstream = new URL(DANIEL_API);
  for (const key of QUERY_KEYS) {
    if (devicesOnly) break;
    const value = input.searchParams.get(key)?.trim() ?? "";
    if (!value) continue;
    if (value.length > 128) throw new RomCatalogHttpError(`${key} filter is too long`, 400);
    if (key === "latest" && !["0", "1"].includes(value)) {
      throw new RomCatalogHttpError("latest filter must be 0 or 1", 400);
    }
    upstream.searchParams.set(key, value);
  }
  if (!upstream.searchParams.has("latest")) upstream.searchParams.set("latest", "1");
  if (!devicesOnly && !upstream.searchParams.has("device") && !upstream.searchParams.has("model")) {
    throw new RomCatalogHttpError("Enter a device or model filter", 400);
  }
  const cacheKey = new Request(`https://rom-catalog-cache.wukong.invalid/${devicesOnly ? "devices" : "v1"}?${upstream.searchParams}`);
  const cached = await caches.default.match(cacheKey);
  if (cached) return await cached.json() as Record<string, unknown>;

  let response: Response | null = null;
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
    // The same source can be reachable from Vercel when edge TLS/DNS fails.
  }
  if (!response || response.status >= 500) {
    await response?.body?.cancel();
    response = await callSourceTransport(request, env, "catalog", upstream.toString(), "", MAX_RESPONSE_BYTES);
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
  const rows = releaseRows(payload);
  const releases = (devicesOnly ? [] : rows)
    .slice(0, MAX_RELEASES)
    .map(normalizeRelease)
    .filter((release): release is Record<string, unknown> => release !== null);
  const result = {
    source: "daniel-springer",
    fetchedAt: new Date().toISOString(),
    ...(devicesOnly ? { devices: deviceChoices(rows) } : { releases, truncated: rows.length > MAX_RELEASES })
  };
  await caches.default.put(cacheKey, Response.json(result, {
    headers: { "Cache-Control": "public, max-age=900" }
  }));
  return result;
}

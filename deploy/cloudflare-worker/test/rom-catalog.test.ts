import { SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tmaHeaders } from "./helpers";

describe("ROM discovery catalog", () => {
  it("returns a direct resolved link only for an approved private resolve request", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({
      resolvedUrl: "https://cdn.allawnfs.com/rom.zip?Signature=temporary",
      filename: "rom.zip", sizeBytes: 4096, contentType: "application/zip"
    })));
    const url = "https://worker.example/v1/sources/resolve";
    const body = JSON.stringify({ uri: "https://component-ota-cn.allawntech.com/downloadCheck?resolve=1" });
    expect((await SELF.fetch(url, { method: "POST", body, headers: await tmaHeaders(77041) })).status).toBe(403);
    const response = await SELF.fetch(url, { method: "POST", body, headers: await tmaHeaders(1678823419) });
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toMatchObject({ resolvedUrl: "https://cdn.allawnfs.com/rom.zip?Signature=temporary" });
  });
  it("lists unique devices and their regions across the entire latest catalog, with caching and approval", async () => {
    const rows = Array.from({ length: 201 }, (_, i) => ({ device: "OP 13", region: i % 2 ? "EU" : "CN", model: i % 2 ? "CPH2653" : "PJZ110" }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe("https://roms.danielspringer.at/api/ota.php?latest=1");
      return Response.json({ releases: [...rows, { device: "OPPO FIND X8", region: "CN", model: "PKB110" }, { device: "Xiaomi 15", region: "CN" }, { device: "Realme GT7", region: "CN" }] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const url = "https://worker.example/v1/rom-catalog/devices";
    expect((await SELF.fetch(url, { headers: await tmaHeaders(77040) })).status).toBe(403);
    const headers = await tmaHeaders(1678823419);
    const response = await SELF.fetch(url, { headers });
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload).toMatchObject({ devices: [
      { id: "OP 13", label: "OnePlus 13", brand: "OnePlus", regions: [{ code: "CN", models: ["PJZ110"] }, { code: "EU", models: ["CPH2653"] }] },
      { id: "OPPO FIND X8", label: "OPPO Find X8", brand: "OPPO" },
      { id: "Realme GT7", brand: "Realme" }
    ] });
    expect(await (await SELF.fetch(url, { headers })).json()).toEqual(payload);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("returns selectable historical versions newest first", async () => {
    const upstreamUrls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      upstreamUrls.push(String(input));
      return Response.json({ releases: [
        { id: "old", device: "OP ACE 5", version: "16.0.9.500", build_timestamp: 1700000000, source_url: "https://cdn.example/old.zip" },
        { id: "new", device: "OP ACE 5", version: "16.0.10.500", build_timestamp: 1800000000, source_url: "https://cdn.example/new.zip" }
      ] });
    }));
    const response = await SELF.fetch("https://worker.example/v1/rom-catalog?device=OP+ACE+5&latest=0", { headers: await tmaHeaders(1678823419) });
    // Public API accepts only latest=1; history must omit the parameter.
    expect(upstreamUrls).toEqual(["https://roms.danielspringer.at/api/ota.php?device=OP+ACE+5"]);
    expect((await response.json() as { releases: {id:string}[] }).releases.map(r => r.id)).toEqual(["new", "old"]);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("queries only the Daniel Springer API and returns normalized unresolved releases", async () => {
    let upstreamUrl = "";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      // The deployed edge runtime rejects redirect: "error" although local workerd accepts it.
      expect(init?.redirect).toBe("manual");
      const request = input instanceof Request ? input : new Request(input);
      upstreamUrl = request.url;
      return Response.json({
        count: 1,
        data: [{
          id: "dfc92b312dea4d096e2e04b8",
          device: "OP 13",
          region: "EU",
          model: "CPH2653",
          version: "CPH2653_15.0.0.850(EX01)",
          ota_version: "CPH2653_15.0.0.850(EX01)",
          build_timestamp: 1750000000,
          security_patch: "2026-07-05",
          md5: "a28632dc4e3e2c8b51cc6e938c87b6fb",
          size: 7340032000,
          published: "2026-08-20T12:00:00Z",
          version_code: "15.0.0.850",
          source_url: "https://component-ota-cn.allawntech.com/downloadCheck?c=fixture",
          changelog_url: "https://example.invalid/changelog",
          is_latest: 1
        }]
      }, {
        headers: { ETag: "\"fixture-etag\"" }
      });
    }));

    const headers = await tmaHeaders(1678823419);
    const response = await SELF.fetch(
      "https://worker.example/v1/rom-catalog?device=OP%2013&region=EU&latest=1&upstream=https://evil.example",
      { headers }
    );

    expect(response.status).toBe(200);
    expect(upstreamUrl).toBe(
      "https://roms.danielspringer.at/api/ota.php?device=OP+13&region=EU&latest=1"
    );
    await expect(response.json()).resolves.toMatchObject({
      source: "daniel-springer",
      releases: [{
        id: "dfc92b312dea4d096e2e04b8",
        device: "OP 13",
        region: "EU",
        model: "CPH2653",
        version: "CPH2653_15.0.0.850(EX01)",
        securityPatch: "2026-07-05",
        sizeBytes: 7340032000,
        sourceUrl: "https://component-ota-cn.allawntech.com/downloadCheck?c=fixture",
        latest: true
      }]
    });
  });

  it("reuses a bounded catalog snapshot and preserves real upstream date fields", async () => {
    const fetchMock = vi.fn(async () => Response.json({ releases: [{
      id: "cache-date-fixture", model: "CPH2649", device: "OP 13", region: "IN",
      build_timestamp: "2026-08-07T10:54:00Z", published: 1786939382388, version_code: 2930,
      size: null, source_url: "https://component-ota-sg.allawnos.com/downloadCheck?c=cache"
    }, null] }));
    vi.stubGlobal("fetch", fetchMock);
    const headers = await tmaHeaders(1678823419);
    const url = "https://worker.example/v1/rom-catalog?model=CPH2649";
    const first = await SELF.fetch(url, { headers });
    expect(first.status).toBe(200);
    const result = await first.json();
    expect(result).toMatchObject({ releases: [{
      buildTimestamp: "2026-08-07T10:54:00.000Z", publishedAt: "2026-08-17T04:03:02.388Z",
      versionCode: "2930", sizeBytes: null
    }] });
    const second = await SELF.fetch(url, { headers });
    expect(await second.json()).toEqual(result);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requires approval and bounded filters before contacting the catalog", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const denied = await SELF.fetch("https://worker.example/v1/rom-catalog?model=CPH2653", {
      headers: await tmaHeaders(77039)
    });
    expect(denied.status).toBe(403);
    const empty = await SELF.fetch("https://worker.example/v1/rom-catalog", {
      headers: await tmaHeaders(1678823419)
    });
    expect(empty.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects upstream redirects without following them", async () => {
    const fetchMock = vi.fn(async () => new Response(null, {
      status: 302, headers: { Location: "https://untrusted.example/catalog" }
    }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await SELF.fetch("https://worker.example/v1/rom-catalog?model=redirect-fixture", {
      headers: await tmaHeaders(1678823419)
    });
    expect(response.status).toBe(502);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses a single-use transport claim when the edge cannot negotiate source TLS", async () => {
    let claimed = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const current = new Request(input, init);
      if (new URL(current.url).hostname === "roms.danielspringer.at") return new Response(null, { status: 525 });
      expect(current.url).toBe("https://wukong-rom-studio.vercel.app/api/source-transport");
      const claim = await current.json() as { token: string; claimUrl: string };
      const headers = { Authorization: `TransportClaim ${claim.token}` };
      const response = await SELF.fetch(claim.claimUrl, { method: "POST", headers });
      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({
        operation: "catalog", sourceUrl: "https://roms.danielspringer.at/api/ota.php?model=tls-fixture&latest=1",
        maximumBytes: 2 * 1024 * 1024
      });
      expect((await SELF.fetch(claim.claimUrl, { method: "POST", headers })).status).toBe(410);
      claimed = true;
      return Response.json({ releases: [{ id: "tls", source_url: "https://cdn.example/rom.zip" }] });
    }));
    const result = await SELF.fetch("https://worker.example/v1/rom-catalog?model=tls-fixture", {
      headers: await tmaHeaders(1678823419)
    });
    expect(result.status).toBe(200);
    expect(claimed).toBe(true);
    expect(await result.json()).toMatchObject({ releases: [{ id: "tls" }] });
  });
});

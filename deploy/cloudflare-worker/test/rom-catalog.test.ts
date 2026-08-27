import { SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tmaHeaders } from "./helpers";

describe("ROM discovery catalog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("queries only the Daniel Springer API and returns normalized unresolved releases", async () => {
    let upstreamUrl = "";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
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
});

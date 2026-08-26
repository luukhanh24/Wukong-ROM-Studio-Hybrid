import { SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";

function mockDnsAndOrigin(handler: (request: Request) => Response | Promise<Response>): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    if (url.hostname === "cloudflare-dns.com") {
      return Response.json({
        Status: 0,
        Answer: [{ type: 1, data: "8.8.8.8" }]
      });
    }
    return handler(request);
  }));
}

describe("bounded ROM source Range proxy", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("creates a two-minute probe session and serves a bounded byte range", async () => {
    const bytes = new Uint8Array(1024).fill(0x50);
    mockDnsAndOrigin((request) => {
      if (request.method === "HEAD") {
        return new Response(null, {
          status: 200,
          headers: {
            "Content-Length": String(16 * 1024 * 1024),
            "Content-Type": "application/zip",
            "Content-Disposition": 'attachment; filename="PJD110_OTA.zip"',
            "Accept-Ranges": "bytes",
            "Content-MD5": "fixture-md5"
          }
        });
      }
      expect(request.headers.get("Range")).toBe("bytes=0-1023");
      return new Response(bytes, {
        status: 206,
        headers: {
          "Content-Type": "application/zip",
          "Content-Range": `bytes 0-1023/${16 * 1024 * 1024}`
        }
      });
    });

    const probe = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ uri: "https://downloads.example/PJD110_OTA.zip" })
    });
    if (probe.status !== 200) console.log("probe failure", await probe.clone().text());
    expect(probe.status).toBe(200);
    const payload = await probe.json() as Record<string, unknown>;
    expect(payload).toMatchObject({
      host: "downloads.example",
      filename: "PJD110_OTA.zip",
      sizeBytes: 16 * 1024 * 1024,
      contentType: "application/zip",
      checksumHeader: "fixture-md5",
      deepInspected: false,
      rangeSession: {
        expiresIn: 120,
        maxRequests: 64,
        maxBytes: 16 * 1024 * 1024
      }
    });
    const session = payload.rangeSession as { id: string; url: string };
    expect(session.id).toMatch(/^[0-9a-f]{32}$/);

    const range = await SELF.fetch(session.url, {
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        Range: "bytes=0-1023"
      }
    });
    expect(range.status).toBe(206);
    expect((await range.arrayBuffer()).byteLength).toBe(1024);
  });

  it("rejects private destinations and oversized ranges", async () => {
    const blocked = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ uri: "http://127.0.0.1/private.zip" })
    });
    expect(blocked.status).toBe(400);
    await expect(blocked.json()).resolves.toMatchObject({ code: "source_unreachable" });

    mockDnsAndOrigin(() => new Response(null, {
      status: 200,
      headers: { "Content-Length": "20000000", "Content-Type": "application/zip" }
    }));
    const probe = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ uri: "https://downloads.example/rom.zip" })
    });
    if (probe.status !== 200) console.log("probe failure", await probe.clone().text());
    const session = (await probe.json() as { rangeSession: { url: string } }).rangeSession;
    const oversized = await SELF.fetch(session.url, {
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        Range: `bytes=0-${8 * 1024 * 1024}`
      }
    });
    expect(oversized.status).toBe(416);
  });

  it("reuses destination validation across range requests", async () => {
    let dnsRequests = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(input, init);
      const url = new URL(request.url);
      if (url.hostname === "cloudflare-dns.com") {
        dnsRequests += 1;
        return Response.json({
          Status: 0,
          Answer: [{ type: 1, data: "8.8.8.8" }]
        });
      }
      if (request.method === "HEAD") {
        return new Response(null, {
          status: 200,
          headers: {
            "Content-Length": "4096",
            "Content-Type": "application/zip",
            "Content-Disposition": 'attachment; filename="fixture.zip"'
          }
        });
      }
      const match = request.headers.get("Range")?.match(/bytes=(\d+)-(\d+)/);
      const length = match ? Number(match[2]) - Number(match[1]) + 1 : 0;
      return new Response(new Uint8Array(length), { status: 206 });
    }));

    const probe = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ uri: "https://downloads.example/fixture.zip" })
    });
    const session = (await probe.json() as { rangeSession: { url: string } }).rangeSession;
    expect(dnsRequests).toBe(2);

    for (const range of ["bytes=0-31", "bytes=32-63", "bytes=64-95"]) {
      const response = await SELF.fetch(session.url, {
        headers: {
          Origin: "https://wukong-rom-studio.vercel.app",
          Range: range
        }
      });
      expect(response.status).toBe(206);
    }

    expect(dnsRequests).toBe(2);
  });

  it("still blocks a private destination introduced by a range redirect", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(input, init);
      const url = new URL(request.url);
      if (url.hostname === "cloudflare-dns.com") {
        const host = url.searchParams.get("name");
        return Response.json({
          Status: 0,
          Answer: [{ type: 1, data: host === "private.example" ? "127.0.0.1" : "8.8.8.8" }]
        });
      }
      if (request.method === "HEAD") {
        return new Response(null, {
          status: 200,
          headers: { "Content-Length": "4096", "Content-Type": "application/zip" }
        });
      }
      return new Response(null, {
        status: 302,
        headers: { Location: "http://private.example/internal" }
      });
    }));

    const probe = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ uri: "https://downloads.example/fixture.zip" })
    });
    const session = (await probe.json() as { rangeSession: { url: string } }).rangeSession;
    const range = await SELF.fetch(session.url, {
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        Range: "bytes=0-31"
      }
    });

    expect(range.status).toBe(400);
    await expect(range.json()).resolves.toMatchObject({ code: "source_unreachable" });
  });

  it("resolves OPlus downloadCheck when HEAD returns JSON", async () => {
    let sourceGets = 0;
    mockDnsAndOrigin((request) => {
      const url = new URL(request.url);
      if (url.pathname === "/downloadCheck" && request.method === "HEAD") {
        return new Response(null, {
          status: 200,
          headers: {
            "Content-Length": "128",
            "Content-Type": "application/json"
          }
        });
      }
      if (url.pathname === "/downloadCheck") {
        sourceGets += 1;
        return new Response(null, {
          status: 302,
          headers: { Location: "https://cdn.example/PKG110_16.0.9.zip" }
        });
      }
      return new Response(null, {
        status: 200,
        headers: {
          "Content-Length": "8192",
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="PKG110_16.0.9.zip"'
        }
      });
    });

    const probe = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        uri: "https://component-ota-cn.allawntech.com/downloadCheck?c=fixture"
      })
    });
    const payload = await probe.json() as Record<string, unknown>;

    expect(sourceGets).toBe(1);
    expect(payload.filename).toBe("PKG110_16.0.9.zip");
    expect(payload.contentType).toBe("application/zip");
  });

  it("preserves the OPlus MD5 response header", async () => {
    mockDnsAndOrigin(() => new Response(null, {
      status: 200,
      headers: {
        "Content-Length": "8192",
        "Content-Type": "application/zip",
        "Content-Disposition": 'attachment; filename="PKG110.zip"',
        "x-amz-meta-filemd5": "a28632dc4e3e2c8b51cc6e938c87b6fb"
      }
    }));

    const probe = await SELF.fetch("https://worker.example/v1/sources/probe", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ uri: "https://downloads.example/PKG110.zip" })
    });
    const payload = await probe.json() as Record<string, unknown>;

    expect(payload.md5).toBe("a28632dc4e3e2c8b51cc6e938c87b6fb");
  });
});

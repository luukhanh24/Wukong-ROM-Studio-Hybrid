import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tmaHeaders } from "./helpers";

describe("admin batch ROM builds", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rejects normal users", async () => {
    const response = await SELF.fetch("https://worker.example/v1/admin/batch-builds", {
      method: "POST",
      headers: { ...await tmaHeaders(78001), "Idempotency-Key": "denied-batch" },
      body: JSON.stringify({ devices: ["PKG110"], modVersions: ["ColorOS_16.0.9"], editions: ["lite"] })
    });
    expect(response.status).toBe(403);
  });

  it("reserves release-folder storage for server-created batch jobs", async () => {
    const response = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST", headers: { ...await tmaHeaders(1678823419), "Idempotency-Key": "forged-batch-storage" },
      body: JSON.stringify({
        schemaVersion: 1, task: "build", device: "PKG110",
        source: { kind: "https", uri: "https://downloads.example/rom.zip" },
        execution: { target: "github-auto" }, build: { preset: "lite", modVersion: "ColorOS_16.0.9" },
        storage: { publishArtifact: true, artifactRoot: "ROM/V5.1" }
      })
    });
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ code: "batch_storage_forbidden" });
  });

  it("persists an admin release label and keeps it read-only for users", async () => {
    const adminHeaders = await tmaHeaders(1678823419);
    const saved = await SELF.fetch("https://worker.example/v1/mod-release-versions", {
      method: "PUT", headers: adminHeaders,
      body: JSON.stringify({ modReleaseVersions: { "ColorOS_16.0.9": "V5.1" } })
    });
    expect(saved.status).toBe(200);
    expect((await saved.json() as any).modReleaseVersions["ColorOS_16.0.9"]).toBe("V5.1");
    const live = await (await SELF.fetch("https://worker.example/v1/mod-release-versions", { headers: adminHeaders })).json() as any;
    expect(live).toMatchObject({ editable: true, modReleaseVersions: { "ColorOS_16.0.9": "V5.1" } });
    expect((await SELF.fetch("https://worker.example/v1/mod-release-versions", {
      method: "PUT", headers: await tmaHeaders(78002), body: JSON.stringify({ modReleaseVersions: { "ColorOS_16.0.9": "V9.9" } })
    })).status).toBe(403);
  });

  it("finds a matching stock ROM, creates linked jobs and preserves the batch Drive layout", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("roms.danielspringer.at/api/ota.php?model=PKG110");
      return Response.json({ releases: [
        { id: "wrong", model: "PKG110", version: "PKG110_16.0.8.300(CN01)", source_url: "https://example.com/wrong.zip", build_timestamp: 1 },
        { id: "right", model: "PKG110", version: "PKG110_16.0.9.500(CN01)", source_url: "https://component-ota-cn.allawntech.com/downloadCheck?c=batch", build_timestamp: 2 }
      ] });
    }));
    const headers = await tmaHeaders(1678823419);
    await SELF.fetch("https://worker.example/v1/mod-release-versions", {
      method: "PUT", headers,
      body: JSON.stringify({ modReleaseVersions: { "ColorOS_16.0.9": "V5.1" } })
    });
    const body = JSON.stringify({
        devices: ["PKG110"], modVersions: ["ColorOS_16.0.9"],
        editions: ["lite", "plus"]
      });
    const created = await SELF.fetch("https://worker.example/v1/admin/batch-builds", {
      method: "POST", headers: { ...headers, "Idempotency-Key": "batch-source-match" }, body
    });
    expect(created.status).toBe(201);
    const batch = await created.json() as any;
    expect(batch).toMatchObject({ releaseVersion: "V5.1", itemCount: 1 });
    const retry = await SELF.fetch("https://worker.example/v1/admin/batch-builds", { method: "POST", headers: { ...headers, "Idempotency-Key": "batch-source-match" }, body });
    expect(retry.status).toBe(200);
    expect((await retry.json() as any).batchId).toBe(batch.batchId);

    const detail = await (await SELF.fetch(`https://worker.example/v1/admin/batch-builds/${batch.batchId}`, { headers })).json() as any;
    expect(detail.items[0]).toMatchObject({ device: "PKG110", modVersion: "ColorOS_16.0.9", status: "queued", itemStatus: "job_created" });
    expect(detail.items[0].jobId).toBeTruthy();
    expect(detail.events.map((event: any) => event.eventType)).toEqual(expect.arrayContaining(["batch_created", "source_found", "job_created"]));

    const job = await (await SELF.fetch(`https://worker.example/v1/jobs/${detail.items[0].jobId}`, { headers })).json() as any;
    expect(job.recipe.build).toMatchObject({ preset: "both", modVersion: "ColorOS_16.0.9", modReleaseVersion: "V5.1" });
    expect(job.recipe.storage).toMatchObject({ publishArtifact: true, artifactRoot: "ROM/V5.1" });
    const db = (env as unknown as Env).DB;
    await db.batch(Array.from({ length: 60 }, (_, index) => db.prepare(
      "INSERT INTO wukong_job_events (job_id,sequence,timestamp,event_type,payload_json) VALUES (?,?,?,?,?)"
    ).bind(detail.items[0].jobId, index + 10, `2026-08-28T12:${String(index).padStart(2, "0")}:00Z`, "step", JSON.stringify({ message: `event-${index + 10}` }))));
    const withLogs = await (await SELF.fetch(`https://worker.example/v1/admin/batch-builds/${batch.batchId}`, { headers })).json() as any;
    expect(withLogs.items[0].jobEvents).toHaveLength(50);
    expect(withLogs.items[0].jobEvents.at(-1).message).toBe("event-69");
  });

  it("derives each item release folder from its permanent MOD label", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ releases: [
      { id: "cos-8", model: "PKG110", version: "PKG110_16.0.8.500(CN01)", source_url: "https://component-ota-cn.allawntech.com/downloadCheck?c=cos8", build_timestamp: 1 },
      { id: "cos-9", model: "PKG110", version: "PKG110_16.0.9.500(CN01)", source_url: "https://component-ota-cn.allawntech.com/downloadCheck?c=cos9", build_timestamp: 2 }
    ] })));
    const headers = await tmaHeaders(1678823419);
    await SELF.fetch("https://worker.example/v1/mod-release-versions", {
      method: "PUT", headers,
      body: JSON.stringify({ modReleaseVersions: { "ColorOS_16.0.8": "V4.2", "ColorOS_16.0.9": "V5.1" } })
    });

    const created = await SELF.fetch("https://worker.example/v1/admin/batch-builds", {
      method: "POST", headers: { ...headers, "Idempotency-Key": "batch-derived-release-folders" },
      body: JSON.stringify({
        devices: ["PKG110"], modVersions: ["ColorOS_16.0.8", "ColorOS_16.0.9"], editions: ["lite"],
        releaseVersion: "FORGED-BY-CLIENT"
      })
    });
    expect(created.status).toBe(201);
    const batch = await created.json() as any;
    expect(batch.releaseVersions).toEqual({ "ColorOS_16.0.8": "V4.2", "ColorOS_16.0.9": "V5.1" });

    const detail = await (await SELF.fetch(`https://worker.example/v1/admin/batch-builds/${batch.batchId}`, { headers })).json() as any;
    expect(detail.items.map((item: any) => [item.modVersion, item.releaseVersion]).sort()).toEqual([
      ["ColorOS_16.0.8", "V4.2"], ["ColorOS_16.0.9", "V5.1"]
    ]);
    for (const item of detail.items) {
      const job = await (await SELF.fetch(`https://worker.example/v1/jobs/${item.jobId}`, { headers })).json() as any;
      expect(job.recipe.build.modReleaseVersion).toBe(item.releaseVersion);
      expect(job.recipe.storage.artifactRoot).toBe(`ROM/${item.releaseVersion}`);
    }
  });

  it("accepts every supported device and MOD combination selected together", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ releases: [] })));
    const headers = await tmaHeaders(1678823419);
    const catalog = await (await SELF.fetch("https://worker.example/v1/catalog", { headers })).json() as any;
    const devices = catalog.devices.map((device: any) => device.product);
    const modVersions = catalog.modVersions;
    expect(devices.length * modVersions.length).toBeGreaterThan(50);

    const response = await SELF.fetch("https://worker.example/v1/admin/batch-builds", {
      method: "POST", headers: { ...headers, "Idempotency-Key": "batch-select-everything" },
      body: JSON.stringify({ devices, modVersions, editions: ["lite", "plus"] })
    });
    const payload = await response.json() as any;
    expect(response.status, JSON.stringify(payload)).toBe(201);
    expect(payload).toMatchObject({ itemCount: devices.length * modVersions.length });
  });
});

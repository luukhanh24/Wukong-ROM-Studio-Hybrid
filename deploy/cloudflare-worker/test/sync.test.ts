import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";
import { syncJobs } from "../src/sync";

describe("bounded job synchronization", () => {
  it("omits history for detail requests, reduces payload and pages events without loss", async () => {
    const headers = await tmaHeaders(1678823419);
    await SELF.fetch("https://worker.example/v1/me", { headers });
    const db = (env as unknown as Env).DB;
    await db.batch(Array.from({ length: 110 }, (_, i) => {
      const id = `sync-fixture-${i}`;
      return db.prepare(`INSERT INTO wukong_jobs (job_id,manifest_json,recipe_json,created_at,updated_at,owner_channel,owner_subject,device,status) VALUES (?,?,?,'2026-09-01','2026-09-01','telegram','1678823419','PKG110','succeeded')`)
        .bind(id, JSON.stringify({ job_id: id }), JSON.stringify({ device: "PKG110", build: { preset: "plus", modVersion: "ColorOS_16.0.10" } }));
    }));
    const base = "https://worker.example/v1/sync?jobId=sync-fixture-0";
    const legacy = await (await SELF.fetch(base, { headers })).text();
    const compact = await (await SELF.fetch(`${base}&includeHistory=0`, { headers })).text();
    expect(compact.length).toBeLessThan(legacy.length * 0.7);
    expect(JSON.parse(compact)).not.toHaveProperty("jobs");
    expect(JSON.parse(legacy).jobs).toHaveLength(100);
    for (let offset = 0; offset < 1001; offset += 100) {
      await db.batch(Array.from({ length: Math.min(100, 1001 - offset) }, (_, i) => db.prepare(
        "INSERT INTO wukong_job_events(job_id,sequence,timestamp,event_type,payload_json) VALUES ('sync-fixture-0',?,'2026-09-01','progress','{}')"
      ).bind(offset + i + 1)));
    }
    const first = await (await SELF.fetch(`${base}&includeHistory=0`, { headers })).json() as any;
    expect(first.events).toHaveLength(500);
    expect(first).toMatchObject({ nextEventSequence: 500, eventsHasMore: true });
    const second = await (await SELF.fetch(`${base}&includeHistory=0&after=500`, { headers })).json() as any;
    expect(second.events[0].sequence).toBe(501);
    expect(second).toMatchObject({ nextEventSequence: 1000, eventsHasMore: true });
    const last = await (await SELF.fetch(`${base}&includeHistory=0&after=1000`, { headers })).json() as any;
    expect(last).toMatchObject({ nextEventSequence: 1001, eventsHasMore: false });
    const previous = await (await SELF.fetch(`${base}&includeHistory=0&before=750`, { headers })).json() as any;
    expect(previous.events).toHaveLength(500);
    expect(previous.events[0].sequence).toBe(250);
    expect(previous.events.at(-1).sequence).toBe(749);
  });

  it("does not disclose a selected job owned by another user", async () => {
    const db = (env as unknown as Env).DB;
    const now = new Date().toISOString();
    await db.prepare("INSERT OR REPLACE INTO wukong_telegram_users (subject,username,display_name,first_seen_at,last_seen_at,access_status,role,build_credits,unlimited) VALUES ('2678823419','','Other',?,?, 'approved','user',5,0)").bind(now, now).run();
    const other = await tmaHeaders(2678823419);
    const response = await SELF.fetch("https://worker.example/v1/sync?includeHistory=0&jobId=sync-fixture-0", { headers: other });
    expect(response.status).toBe(200);
    expect((await response.json() as any).activeJob).toBeNull();
  });

  it("does not turn storage failures into a successful empty detail", async () => {
    const broken = { DB: { prepare() { throw new Error("database unavailable"); } } } as unknown as Env;
    await expect(syncJobs(broken, { role: "admin", subject: "1678823419" } as any,
      new URLSearchParams("includeHistory=0&jobId=fixture"))).rejects.toThrow("database unavailable");
  });
});

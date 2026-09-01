import { env } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { drainAutomaticMirrorRepairOutbox } from "../src/mirror-repair-outbox";

describe("automatic DC Cloud mirror repair", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("dispatches each queued repair exactly once", async () => {
    const bindings = env as unknown as Env;
    const jobId = "automatic-mirror-repair";
    const now = new Date().toISOString();
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at, build_credits, lifetime_granted)
         VALUES ('44001', 'approved', 'user', ?, ?, 1, 1)
         ON CONFLICT (subject) DO UPDATE SET access_status = 'approved'`
      ).bind(now, now),
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_access (subject, role) VALUES ('44001', 'user')
         ON CONFLICT (subject) DO UPDATE SET role = 'user'`
      ),
      bindings.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at, owner_channel,
          owner_subject, device, status, stage, progress)
         VALUES (?, '{}', '{}', ?, ?, 'telegram', '44001', 'PJD110', 'succeeded', 'complete', 1)`
      ).bind(jobId, now, now),
      bindings.DB.prepare(
        `INSERT INTO wukong_mirror_repair_outbox
         (job_id, state, attempts, available_at, created_at)
         VALUES (?, 'pending', 0, ?, ?)`
      ).bind(jobId, now, now)
    ]);
    const requests: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), body: JSON.parse(String(init?.body)) });
      return new Response(null, { status: 204 });
    }));
    const dispatchEnv = new Proxy(bindings, {
      get(target, property, receiver) {
        if (property === "WUKONG_DISABLE_EXTERNAL_DISPATCH") return "";
        return Reflect.get(target, property, receiver);
      }
    });

    await drainAutomaticMirrorRepairOutbox(dispatchEnv, 5);
    await drainAutomaticMirrorRepairOutbox(dispatchEnv, 5);

    expect(requests).toEqual([{
      url: "https://api.github.com/repos/fixture-owner/fixture-repository/actions/workflows/mirror-repair.yml/dispatches",
      body: { ref: "main", inputs: { job_id: jobId } }
    }]);
    const queued = await bindings.DB.prepare(
      `SELECT state, attempts, dispatched_at, last_error
       FROM wukong_mirror_repair_outbox WHERE job_id = ?`
    ).bind(jobId).first<Record<string, unknown>>();
    expect(queued).toMatchObject({ state: "dispatched", attempts: 1, last_error: "" });
    expect(String(queued?.dispatched_at)).not.toBe("");
  });

  it("stops retrying after five failed dispatch attempts", async () => {
    const bindings = env as unknown as Env;
    const jobId = "bounded-automatic-repair";
    const now = new Date().toISOString();
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at, build_credits, lifetime_granted)
         VALUES ('44002', 'approved', 'user', ?, ?, 1, 1)
         ON CONFLICT (subject) DO UPDATE SET access_status = 'approved'`
      ).bind(now, now),
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_access (subject, role) VALUES ('44002', 'user')
         ON CONFLICT (subject) DO UPDATE SET role = 'user'`
      ),
      bindings.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at, owner_channel,
          owner_subject, device, status, stage, progress)
         VALUES (?, '{}', '{}', ?, ?, 'telegram', '44002', 'PJD110', 'succeeded', 'complete', 1)`
      ).bind(jobId, now, now),
      bindings.DB.prepare(
        `INSERT INTO wukong_mirror_repair_outbox
         (job_id, state, attempts, available_at, created_at)
         VALUES (?, 'failed', 4, ?, ?)`
      ).bind(jobId, now, now)
    ]);
    let requests = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      requests += 1;
      return new Response("temporarily unavailable", { status: 503 });
    }));
    const dispatchEnv = new Proxy(bindings, {
      get(target, property, receiver) {
        if (property === "WUKONG_DISABLE_EXTERNAL_DISPATCH") return "";
        return Reflect.get(target, property, receiver);
      }
    });

    await drainAutomaticMirrorRepairOutbox(dispatchEnv, 5);
    await bindings.DB.prepare(
      "UPDATE wukong_mirror_repair_outbox SET available_at = ? WHERE job_id = ?"
    ).bind(new Date().toISOString(), jobId).run();
    await drainAutomaticMirrorRepairOutbox(dispatchEnv, 5);

    expect(requests).toBe(1);
    const queued = await bindings.DB.prepare(
      `SELECT state, attempts, last_error
       FROM wukong_mirror_repair_outbox WHERE job_id = ?`
    ).bind(jobId).first<Record<string, unknown>>();
    expect(queued).toMatchObject({ state: "failed", attempts: 5 });
    expect(String(queued?.last_error)).toContain("503");
  });
});

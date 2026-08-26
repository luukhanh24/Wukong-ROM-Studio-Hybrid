import { env, SELF } from "cloudflare:test";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";

const recipe = {
  schemaVersion: 1,
  task: "build",
  device: "PKG110",
  source: {
    kind: "https",
    uri: "https://downloads.example/rom.zip",
    metadata: { productName: "Fixture ROM" }
  },
  execution: { target: "github-auto" },
  build: {
    preset: "plus",
    modVersion: "ColorOS_16.0.10",
    modReleaseVersion: "V6.0",
    mods: [],
    notifyTelegram: true
  },
  storage: { publishArtifact: true }
};

async function seedApprovedUser(subject: string, credits: number): Promise<void> {
  const now = new Date().toISOString();
  await (env as unknown as Env).DB.batch([
    (env as unknown as Env).DB.prepare(
      `INSERT INTO wukong_telegram_users
       (subject, access_status, role, first_seen_at, last_seen_at, build_credits, lifetime_granted)
       VALUES (?, 'approved', 'user', ?, ?, ?, ?)
       ON CONFLICT (subject) DO UPDATE SET
         access_status = 'approved', build_credits = excluded.build_credits,
         lifetime_granted = excluded.lifetime_granted`
    ).bind(subject, now, now, credits, credits),
    (env as unknown as Env).DB.prepare(
      `INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user')
       ON CONFLICT (subject) DO UPDATE SET role = 'user'`
    ).bind(subject)
  ]);
}

describe("atomic Accepted Job creation", () => {
  beforeEach(async () => {
    await seedApprovedUser("42001", 5);
  });

  afterEach(async () => {
    const bindings = env as unknown as Env;
    await bindings.DB.batch([
      bindings.DB.prepare(
        "DELETE FROM wukong_control_plane_metadata WHERE key = 'd1_migration_mode'"
      ),
      bindings.DB.prepare(
        "DELETE FROM wukong_jobs WHERE job_id LIKE 'global-cap-fixture-%'"
      )
    ]);
  });

  it("returns one Accepted Job for concurrent retries and consumes one credit", async () => {
    const headers = {
      ...(await tmaHeaders(42001)),
      "Content-Type": "application/json",
      "Idempotency-Key": "same-request"
    };
    const responses = await Promise.all(
      Array.from({ length: 50 }, () =>
        SELF.fetch("https://worker.example/v1/jobs", {
          method: "POST",
          headers,
          body: JSON.stringify(recipe)
        })
      )
    );
    const payloads = await Promise.all(responses.map((response) => response.json() as Promise<Record<string, unknown>>));
    const jobIds = new Set(payloads.map((payload) => payload.job_id));

    expect(jobIds.size).toBe(1);
    expect(responses.filter((response) => response.status === 201)).toHaveLength(1);
    expect(responses.every((response) => response.status === 200 || response.status === 201)).toBe(true);

    const me = await SELF.fetch("https://worker.example/v1/me", { headers });
    await expect(me.json()).resolves.toMatchObject({
      user: { buildCredits: 4, lifetimeUsed: 1, jobCount: 1 }
    });
    const jobs = await SELF.fetch("https://worker.example/v1/jobs", { headers });
    await expect(jobs.json()).resolves.toMatchObject({
      jobs: [{ status: "queued", recipe: { device: "PKG110" } }]
    });
  });

  it("allows concurrent jobs for the same user and device", async () => {
    await seedApprovedUser("42003", 25);
    const competingRecipe = { ...recipe, device: "PKG111" };
    const firstHeaders = {
      ...(await tmaHeaders(42003)),
      "Content-Type": "application/json",
      "Idempotency-Key": "first-build"
    };
    const secondHeaders = {
      ...firstHeaders,
      "Idempotency-Key": "second-build"
    };
    const [first, second] = await Promise.all([
      SELF.fetch("https://worker.example/v1/jobs", {
        method: "POST",
        headers: firstHeaders,
        body: JSON.stringify(competingRecipe)
      }),
      SELF.fetch("https://worker.example/v1/jobs", {
        method: "POST",
        headers: secondHeaders,
        body: JSON.stringify(competingRecipe)
      })
    ]);
    expect([first.status, second.status].sort()).toEqual([201, 201]);
    const payloads = await Promise.all([
      first.json() as Promise<{ job_id: string }>,
      second.json() as Promise<{ job_id: string }>
    ]);
    expect(payloads[0].job_id).not.toBe(payloads[1].job_id);
  });

  it("rejects the twenty-first active job across the system", async () => {
    const bindings = env as unknown as Env;
    const now = new Date().toISOString();
    await bindings.DB.prepare(
      `INSERT INTO wukong_control_plane_metadata (key, value)
       VALUES ('d1_migration_mode', 'migration')
       ON CONFLICT (key) DO UPDATE SET value = 'migration'`
    ).run();
    for (let index = 0; index < 20; index += 1) {
      const jobId = `global-cap-fixture-${index}`;
      await bindings.DB.prepare(
        `INSERT OR REPLACE INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at,
          next_event_sequence, owner_channel, owner_subject, device, status, stage, progress)
         VALUES (?, '{}', ?, ?, ?, 2, 'telegram', '1678823419',
          ?, 'running', 'fixture', 0.5)`
      ).bind(jobId, JSON.stringify(recipe), now, now, `PKG${200 + index}`).run();
    }
    await bindings.DB.prepare(
      "DELETE FROM wukong_control_plane_metadata WHERE key = 'd1_migration_mode'"
    ).run();

    const response = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers: {
        ...(await tmaHeaders(1678823419)),
        "Content-Type": "application/json",
        "Idempotency-Key": "twenty-first-active-job"
      },
      body: JSON.stringify({ ...recipe, device: "PKG999" })
    });

    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({
      code: "build_concurrency_limit"
    });
    await expect(
      bindings.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at,
          next_event_sequence, owner_channel, owner_subject, device, status, stage, progress)
         VALUES ('internal-job-at-capacity', '{}', ?, ?, ?, 2, 'internal',
          'system', 'PKG998', 'queued', 'queued', 0)`
      ).bind(JSON.stringify(recipe), now, now).run()
    ).rejects.toThrow("build_concurrency_limit");
  });

  it("does not accept a job after the Build Allowance is exhausted", async () => {
    await seedApprovedUser("42002", 0);
    const response = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers: {
        ...(await tmaHeaders(42002)),
        "Content-Type": "application/json",
        "Idempotency-Key": "no-credit"
      },
      body: JSON.stringify(recipe)
    });
    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toMatchObject({ code: "build_quota_exhausted" });
  });

  it("resumes a failed checkpoint as a new Accepted Job", async () => {
    const bindings = env as unknown as Env;
    await seedApprovedUser("42004", 5);
    const headers = {
      ...(await tmaHeaders(42004)),
      "Content-Type": "application/json",
      "Idempotency-Key": "original-checkpoint-job"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify({ ...recipe, device: "PKG112" })
    });
    expect(created.status).toBe(201);
    const previous = await created.json() as { job_id: string };
    const checkpointAt = new Date().toISOString();
    const stored = await bindings.DB.prepare(
      "SELECT manifest_json FROM wukong_jobs WHERE job_id = ?"
    ).bind(previous.job_id).first<{ manifest_json: string }>();
    const manifest = {
      ...JSON.parse(stored?.manifest_json ?? "{}"),
      status: "failed",
      stage: "failed",
      checkpoint: "wukong-gdrive:WukongROM/checkpoints/original/extract.tar",
      checkpoint_at: checkpointAt
    };
    await bindings.DB.batch([
      bindings.DB.prepare(
        `UPDATE wukong_jobs SET manifest_json = ?, status = 'failed',
         stage = 'failed', finished_at = ? WHERE job_id = ?`
      ).bind(JSON.stringify(manifest), checkpointAt, previous.job_id),
      bindings.DB.prepare("DELETE FROM wukong_build_locks WHERE job_id = ?")
        .bind(previous.job_id)
    ]);

    const resumed = await SELF.fetch(
      `https://worker.example/v1/jobs/${previous.job_id}/resume`,
      {
        method: "POST",
        headers: {
          ...headers,
          "Idempotency-Key": "resume-checkpoint-job"
        }
      }
    );
    expect(resumed.status).toBe(201);
    const resumedJob = await resumed.json() as Record<string, unknown>;
    expect(resumedJob.job_id).not.toBe(previous.job_id);
    expect(resumedJob).toMatchObject({
      status: "queued",
      checkpoint: "wukong-gdrive:WukongROM/checkpoints/original/extract.tar",
      checkpoint_at: checkpointAt,
      resumed_from_job_id: previous.job_id
    });
    const me = await SELF.fetch("https://worker.example/v1/me", { headers });
    await expect(me.json()).resolves.toMatchObject({
      user: { buildCredits: 3, lifetimeUsed: 2, jobCount: 2 }
    });
  });

  it("accepts a Python-compatible download ticket without exposing the Worker URL", async () => {
    const bindings = env as unknown as Env;
    await SELF.fetch("https://worker.example/healthz");
    const now = new Date().toISOString();
    const manifest = {
      job_id: "ticket-job",
      owner: { channel: "telegram", subject: "1678823419", role: "admin" },
      status: "succeeded",
      stage: "complete",
      progress: 1,
      artifacts: [{
        name: "Wukong-PKG110.zip",
        public_url: "https://drive.google.com/file/d/ticket-fixture/view"
      }]
    };
    await bindings.DB.prepare(
      `INSERT INTO wukong_jobs
       (job_id, manifest_json, recipe_json, created_at, updated_at,
        next_event_sequence, owner_channel, owner_subject, device, status, stage, progress)
       VALUES ('ticket-job', ?, ?, ?, ?, 2, 'telegram', '1678823419',
        'PKG110', 'succeeded', 'complete', 1)`
    ).bind(JSON.stringify(manifest), JSON.stringify(recipe), now, now).run();
    const ticket = "v1.1678823419.2000000000.248bb9708f061622a3191dc7f729edb0d4dcc0e24ad4a80d8e19d19471818150";
    const response = await SELF.fetch(
      `https://worker.example/v1/jobs/ticket-job/download?ticket=${ticket}`,
      { redirect: "manual" }
    );
    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe(
      "https://drive.google.com/file/d/ticket-fixture/view"
    );
  });
});

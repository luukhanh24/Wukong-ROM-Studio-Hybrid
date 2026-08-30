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
  it("lets admins inspect a user's job and identity while isolating other users", async () => {
    await seedApprovedUser("42991", 2);
    await seedApprovedUser("42992", 2);
    const headers = await tmaHeaders(42991, { first_name: "Job Owner", username: "job_owner" });
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST", headers: { ...headers, "Idempotency-Key": "admin-inspect" }, body: JSON.stringify(recipe)
    });
    expect(created.status).toBe(201);
    const job = await created.json() as { job_id: string };
    const url = `https://worker.example/v1/sync?jobId=${job.job_id}`;
    const adminHeaders = await tmaHeaders(1678823419);
    const admin = await (await SELF.fetch(url, { headers: adminHeaders })).json() as any;
    expect(admin.activeJob).toMatchObject({ job_id: job.job_id, createdBy: { telegramId: "42991", displayName: "Job Owner", username: "job_owner" }, recipe: { build: { modReleaseVersion: "V6.0" } } });
    expect(admin.jobs.find((j: any) => j.job_id === job.job_id).createdBy.telegramId).toBe("42991");
    expect(admin.events.length).toBeGreaterThan(0);
    const own = await (await SELF.fetch(url, { headers })).json() as any;
    expect(own.activeJob.job_id).toBe(job.job_id);
    expect(own.activeJob.createdBy).toBeUndefined();
    const other = await (await SELF.fetch(url, { headers: await tmaHeaders(42992) })).json() as any;
    expect(other.activeJob).toBeNull();
    expect(other.events).toEqual([]);
    expect(other.jobs.some((j: any) => j.job_id === job.job_id)).toBe(false);
  });
  it("redacts nested credentials and signed URLs from admin parameters", async () => {
    await seedApprovedUser("42993", 2);
    const unsafe = { ...recipe, source: { ...recipe.source, metadata: { resolvedUrl: "https://cdn.allawnfs.com/rom.zip?Signature=private-signature&Expires=123" } },
      build: { ...recipe.build, nested: { accessToken: "private-token", client_secret: "private-secret", validParameter: 37, note: "Authorization: Bearer hidden-bearer\nAuthorization: Basic hidden-basic" } } };
    const created = await SELF.fetch("https://worker.example/v1/jobs", { method: "POST", headers: { ...await tmaHeaders(42993), "Idempotency-Key": "redacted-job" }, body: JSON.stringify(unsafe) });
    const job = await created.json() as { job_id: string };
    const response = await SELF.fetch(`https://worker.example/v1/jobs/${job.job_id}`, { headers: await tmaHeaders(1678823419) });
    const text = await response.text();
    expect(text).not.toContain("private-token");
    expect(text).not.toContain("private-secret");
    expect(text).not.toContain("private-signature");
    expect(text).not.toContain("hidden-bearer");
    expect(text).not.toContain("hidden-basic");
    expect(JSON.parse(text).recipe.build.nested.validParameter).toBe(37);
  });
  it("keeps validated signed cloud artifact downloads usable", async () => {
    await seedApprovedUser("42995", 2);
    const headers = await tmaHeaders(42995);
    const created = await SELF.fetch("https://worker.example/v1/jobs", { method: "POST", headers: { ...headers, "Idempotency-Key": "signed-artifact" }, body: JSON.stringify(recipe) });
    const job = await created.json() as { job_id: string };
    const url = "https://bucket.s3.amazonaws.com/rom.zip?X-Amz-Signature=valid-download&X-Amz-Expires=3600";
    const githubUrl = `https://github.com/${(env as unknown as Env).WUKONG_GITHUB_REPOSITORY}/releases/download/v1/rom.zip`;
    await (env as unknown as Env).DB.prepare("UPDATE wukong_jobs SET manifest_json = ? WHERE job_id = ?")
      .bind(JSON.stringify({ job_id: job.job_id, artifacts: [{ name: "rom.zip", public_url: url }, { name: "github.zip", public_url: githubUrl }] }), job.job_id).run();
    const result = await (await SELF.fetch(`https://worker.example/v1/jobs/${job.job_id}`, { headers })).json() as any;
    expect(result.artifacts[0]).toMatchObject({ publicUrl: url, downloadAvailable: true });
    expect(result.artifacts[1].publicUrl).toBeUndefined();
    expect(result.artifacts[1].downloadAvailable).toBe(false);
  });
  it("pages all of a user's job history and opens jobs outside the latest100", async () => {
    await seedApprovedUser("42994", 2);
    const db = (env as unknown as Env).DB;
    await db.batch(Array.from({ length: 106 }, (_, i) => {
      const id = `history-page-${String(i).padStart(3, "0")}`;
      return db.prepare(`INSERT INTO wukong_jobs (job_id,manifest_json,recipe_json,created_at,updated_at,owner_channel,owner_subject,device,status,stage,progress) VALUES (?,?,?,'2026-01-01','2026-01-01','telegram','42994','PKG110','succeeded','complete',1)`)
        .bind(id, JSON.stringify({ job_id: id }), JSON.stringify(recipe));
    }));
    const headers = await tmaHeaders(1678823419);
    const detail = await (await SELF.fetch("https://worker.example/v1/admin/users/42994", { headers })).json() as any;
    expect(detail.jobs).toHaveLength(50);
    expect(detail.jobsHasMore).toBe(true);
    const page2 = await (await SELF.fetch(`https://worker.example/v1/admin/users/42994/jobs?cursor=${detail.jobsNextCursor}`, { headers })).json() as any;
    expect(page2.jobs).toHaveLength(50);
    const page3 = await (await SELF.fetch(`https://worker.example/v1/admin/users/42994/jobs?cursor=${page2.nextCursor}`, { headers })).json() as any;
    expect(page3.jobs).toHaveLength(6);
    expect(page3.hasMore).toBe(false);
    expect(new Set([...detail.jobs, ...page2.jobs, ...page3.jobs].map((j: any) => j.job_id)).size).toBe(106);
    const lastId = page3.jobs.at(-1).job_id;
    const sync = await (await SELF.fetch(`https://worker.example/v1/sync?jobId=${lastId}`, { headers })).json() as any;
    expect(sync.jobs.some((j: any) => j.job_id === lastId)).toBe(false);
    expect(sync.activeJob.job_id).toBe(lastId);
    expect((await SELF.fetch("https://worker.example/v1/admin/users/42994/jobs", { headers: await tmaHeaders(42994) })).status).toBe(403);
  });
  it("filters and numerically pages the complete job history", async () => {
    await seedApprovedUser("42996", 2);
    const db = (env as unknown as Env).DB;
    await db.batch(Array.from({ length: 205 }, (_, i) => {
      const id = `numeric-history-${String(i).padStart(3, "0")}`;
      const createdAt = new Date(Date.UTC(2026, 0, 1) + i * 60_000).toISOString();
      const succeeded = i % 3 !== 0;
      const filtered = i < 25;
      const rowRecipe = {
        ...recipe,
        device: filtered ? "FILTER110" : "PKG110",
        build: {
          ...recipe.build,
          preset: filtered ? "plus" : i % 2 ? "lite" : "custom",
          modVersion: filtered ? "ColorOS_Filter" : "ColorOS_16.0.10"
        }
      };
      const manifest = {
        job_id: id,
        rom_metadata: { version: filtered ? "Filter ROM" : "Regular ROM" }
      };
      return db.prepare(
        `INSERT INTO wukong_jobs
         (job_id,manifest_json,recipe_json,created_at,updated_at,owner_channel,owner_subject,device,status,stage,progress)
         VALUES (?,?,?,? ,?,'telegram','42996',?,?, 'complete',1)`
      ).bind(
        id,
        JSON.stringify(manifest),
        JSON.stringify(rowRecipe),
        createdAt,
        createdAt,
        rowRecipe.device,
        succeeded ? "succeeded" : "failed"
      );
    }));
    const headers = await tmaHeaders(42996);
    const page1 = await (await SELF.fetch("https://worker.example/v1/jobs?page=1", { headers })).json() as any;
    const page10 = await (await SELF.fetch("https://worker.example/v1/jobs?page=10", { headers })).json() as any;
    const lastPage = await (await SELF.fetch("https://worker.example/v1/jobs?page=999", { headers })).json() as any;
    expect(page1).toMatchObject({ page: 1, pageSize: 20, total: 205, totalPages: 11 });
    expect(page1.jobs).toHaveLength(20);
    expect(page10.jobs).toHaveLength(20);
    expect(page1.jobs[0].job_id).toBe("numeric-history-204");
    expect(page1.jobs.at(-1).job_id).toBe("numeric-history-185");
    expect(page10.jobs[0].job_id).toBe("numeric-history-024");
    expect(lastPage).toMatchObject({ page: 11, totalPages: 11 });
    expect(lastPage.jobs).toHaveLength(5);
    expect(lastPage.jobs.at(-1).job_id).toBe("numeric-history-000");
    const pages = await Promise.all(Array.from({ length: 11 }, (_, index) =>
      SELF.fetch(`https://worker.example/v1/jobs?page=${index + 1}`, { headers }).then((response) => response.json())
    )) as any[];
    const allIds = pages.flatMap((page) => page.jobs.map((job: any) => job.job_id));
    expect(allIds).toHaveLength(205);
    expect(new Set(allIds).size).toBe(205);
    expect(page1.statusCounts).toEqual({ active: 0, succeeded: 136, failed: 69 });

    const filtered = await (await SELF.fetch(
      "https://worker.example/v1/jobs?page=1&q=filter&status=succeeded&preset=plus&modVersion=ColorOS_Filter&createdFrom=2026-01-01T00:00:00.000Z&createdTo=2026-01-01T00:30:00.000Z",
      { headers }
    )).json() as any;
    expect(filtered).toMatchObject({ page: 1, total: 16, totalPages: 1 });
    expect(filtered.jobs.every((job: any) => job.recipe.device === "FILTER110")).toBe(true);
    expect((await SELF.fetch("https://worker.example/v1/jobs?page=bad", { headers })).status).toBe(400);
    expect((await SELF.fetch("https://worker.example/v1/sync?page=bad", { headers })).status).toBe(400);
  });
  it("pages an admin user's history while preserving the cursor contract and validation", async () => {
    await seedApprovedUser("42997", 2);
    const db = (env as unknown as Env).DB;
    await db.prepare(
      `INSERT INTO wukong_jobs
       (job_id,manifest_json,recipe_json,created_at,updated_at,owner_channel,owner_subject,device,status,stage,progress)
       VALUES ('admin-page-job', ?, ?, '2026-02-01T00:00:00.000Z', '2026-02-01T00:00:00.000Z', 'telegram', '42997', 'PKG110', 'succeeded', 'complete', 1)`
    ).bind(JSON.stringify({ job_id: "admin-page-job" }), JSON.stringify(recipe)).run();
    const adminHeaders = await tmaHeaders(1678823419);
    const page = await (await SELF.fetch(
      "https://worker.example/v1/admin/users/42997/jobs?page=1&status=succeeded&modVersion=ColorOS_16.0.10",
      { headers: adminHeaders }
    )).json() as any;
    expect(page).toMatchObject({ page: 1, pageSize: 20, total: 1, totalPages: 1 });
    expect(page.jobs[0]).toMatchObject({ job_id: "admin-page-job", createdBy: { telegramId: "42997" } });
    expect((await SELF.fetch("https://worker.example/v1/admin/users/42997/jobs?page=bad", { headers: adminHeaders })).status).toBe(400);
    expect((await SELF.fetch("https://worker.example/v1/admin/users/42997/jobs?page=1&status=unknown", { headers: adminHeaders })).status).toBe(400);
    expect((await SELF.fetch("https://worker.example/v1/admin/users/42997/jobs?page=1", { headers: await tmaHeaders(42997) })).status).toBe(403);
  });
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

  it("never exposes repository identity or GitHub run links in public jobs and events", async () => {
    const bindings = env as unknown as Env;
    const subject = "42005";
    await seedApprovedUser(subject, 5);
    const headers = {
      ...(await tmaHeaders(Number(subject))),
      "Content-Type": "application/json",
      "Idempotency-Key": "repository-redaction"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify(recipe)
    });
    const job = await created.json() as { job_id: string };
    const privateRepository = bindings.WUKONG_GITHUB_REPOSITORY;
    await bindings.DB.batch([
      bindings.DB.prepare(
        `UPDATE wukong_jobs SET manifest_json = json_set(
           manifest_json,
           '$.error', ?,
           '$.repository', ?,
           '$.external_run_id', 8123
         ) WHERE job_id = ?`
      ).bind(
        `Build failed: https://github.com/${privateRepository}/actions/runs/8123`,
        privateRepository,
        job.job_id
      ),
      bindings.DB.prepare(
        `INSERT INTO wukong_job_events
         (job_id, sequence, timestamp, event_type, payload_json)
         VALUES (?, 2, ?, 'warning', ?)`
      ).bind(
        job.job_id,
        new Date().toISOString(),
        JSON.stringify({
          repository: privateRepository,
          githubOwner: privateRepository.split("/", 1)[0],
          runId: 8123,
          warning: `GitHub owner: ${privateRepository.split("/", 1)[0]}; Cloud sync failed in ${privateRepository}`
        })
      )
    ]);

    const [jobResponse, eventsResponse] = await Promise.all([
      SELF.fetch(`https://worker.example/v1/jobs/${job.job_id}`, { headers }),
      SELF.fetch(`https://worker.example/v1/jobs/${job.job_id}/events`, { headers })
    ]);
    const publicPayload = JSON.stringify({
      job: await jobResponse.json(),
      events: await eventsResponse.json()
    });
    expect(publicPayload).not.toContain(privateRepository);
    expect(publicPayload).not.toContain("github.com");
    expect(publicPayload).not.toContain("8123");
    expect(publicPayload).toContain("[internal");
  });
});

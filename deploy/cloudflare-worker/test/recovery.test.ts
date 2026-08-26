import { env } from "cloudflare:test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { recoverPreBootstrapJobs } from "../src/recovery";

const JOB_ID = "startup-recovery-job";
const SUBJECT = "55001";

async function seedPreBootstrapJob(attempts: number): Promise<void> {
  const bindings = env as unknown as Env;
  await bindings.DB.batch([
    bindings.DB.prepare(
      "DELETE FROM wukong_telegram_notification_outbox WHERE dedupe_key = ?"
    ).bind(`job-terminal:${JOB_ID}`),
    bindings.DB.prepare(
      "DELETE FROM wukong_telegram_user_events WHERE event_id = ?"
    ).bind(`build-compensated:${JOB_ID}`),
    bindings.DB.prepare(
      "DELETE FROM wukong_telegram_quota_ledger WHERE job_id = ?"
    ).bind(JOB_ID),
    bindings.DB.prepare("DELETE FROM wukong_jobs WHERE job_id = ?").bind(JOB_ID)
  ]);
  const createdAt = new Date(Date.now() - 15 * 60 * 1000).toISOString();
  const manifest = {
    schema_version: 1,
    job_id: JOB_ID,
    owner: { channel: "telegram", subject: SUBJECT, role: "user" },
    status: "queued",
    stage: "queued",
    progress: 0,
    artifacts: [],
    error: null
  };
  const recipe = {
    schemaVersion: 1,
    task: "build",
    device: "PKG110",
    source: { kind: "danielspringer", uri: "https://roms.danielspringer.at/index.php?view=ota&build=fixture" },
    execution: { target: "github-auto" },
    build: { preset: "plus", modVersion: "ColorOS_16.0.10" }
  };
  await bindings.DB.batch([
    bindings.DB.prepare(
      `INSERT INTO wukong_telegram_users
       (subject, access_status, role, first_seen_at, last_seen_at,
        build_credits, lifetime_granted, lifetime_used, job_count, last_job_id, last_job_status)
       VALUES (?, 'approved', 'user', ?, ?, 1, 1, 0, 1, ?, 'queued')
       ON CONFLICT (subject) DO UPDATE SET
         access_status = 'approved', build_credits = 1, lifetime_granted = 1,
         lifetime_used = 0, job_count = 1, last_job_id = excluded.last_job_id,
         last_job_status = 'queued'`
    ).bind(SUBJECT, createdAt, createdAt, JOB_ID),
    bindings.DB.prepare(
      `INSERT OR REPLACE INTO wukong_jobs
       (job_id, manifest_json, recipe_json, created_at, updated_at,
        next_event_sequence, owner_channel, owner_subject, device, status,
        stage, progress, dispatch_attempts, dispatch_last_attempt_at)
       VALUES (?, ?, ?, ?, ?, 2, 'telegram', ?, 'PKG110', 'queued',
               'queued', 0, ?, ?)`
    ).bind(
      JOB_ID,
      JSON.stringify(manifest),
      JSON.stringify(recipe),
      createdAt,
      createdAt,
      SUBJECT,
      attempts,
      createdAt
    ),
    bindings.DB.prepare(
      `UPDATE wukong_telegram_users
       SET build_credits = 0, lifetime_used = 1
       WHERE subject = ?`
    ).bind(SUBJECT),
    bindings.DB.prepare(
      `INSERT OR REPLACE INTO wukong_build_locks
       (lock_key, job_id, subject, device, created_at)
       VALUES ('user:55001', ?, ?, 'PKG110', ?)`
    ).bind(JOB_ID, SUBJECT, createdAt),
    bindings.DB.prepare(
      `INSERT OR REPLACE INTO wukong_build_locks
       (lock_key, job_id, subject, device, created_at)
       VALUES ('device:pkg110', ?, ?, 'PKG110', ?)`
    ).bind(JOB_ID, SUBJECT, createdAt),
    bindings.DB.prepare(
      `INSERT OR REPLACE INTO wukong_telegram_quota_ledger
       (ledger_id, subject, entry_type, delta, balance_after, job_id,
        idempotency_key, consumed, created_at)
       VALUES ('consume-startup-recovery', ?, 'consume', -1, 0, ?,
               '55001:startup-recovery', 1, ?)`
    ).bind(SUBJECT, JOB_ID, createdAt)
  ]);
}

function mockStartupFailure(): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/actions/workflows/") && (init?.method ?? "GET") === "GET") {
      return Response.json({
        workflow_runs: [{
          id: 99101,
          event: "workflow_dispatch",
          display_title: `${JOB_ID} · Wukong Hybrid`,
          path: ".github/workflows/wukong-build.yml",
          status: "completed",
          conclusion: "startup_failure",
          created_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          updated_at: new Date(Date.now() - 5 * 60 * 1000).toISOString()
        }]
      });
    }
    if (url.endsWith("/actions/runs/99101/rerun") && init?.method === "POST") {
      return new Response(null, { status: 201 });
    }
    throw new Error(`Unexpected GitHub request: ${init?.method ?? "GET"} ${url}`);
  }));
}

function mockBootstrapRace(): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/actions/workflows/") && (init?.method ?? "GET") === "GET") {
      await (env as unknown as Env).DB.prepare(
        `UPDATE wukong_jobs
         SET status = 'dispatched', stage = 'github-actions', github_run_id = 99101
         WHERE job_id = ?`
      ).bind(JOB_ID).run();
      return Response.json({
        workflow_runs: [{
          id: 99101,
          event: "workflow_dispatch",
          display_title: `${JOB_ID} · Wukong Hybrid`,
          path: ".github/workflows/wukong-build.yml",
          status: "completed",
          conclusion: "startup_failure",
          created_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          updated_at: new Date(Date.now() - 5 * 60 * 1000).toISOString()
        }]
      });
    }
    throw new Error(`Unexpected GitHub request: ${init?.method ?? "GET"} ${url}`);
  }));
}

describe("pre-bootstrap GitHub Actions recovery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T15:30:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reruns a startup failure without releasing the accepted job", async () => {
    await seedPreBootstrapJob(1);
    mockStartupFailure();

    await recoverPreBootstrapJobs(env as unknown as Env);

    const bindings = env as unknown as Env;
    const job = await bindings.DB.prepare(
      `SELECT status, stage, github_run_id, dispatch_attempts
       FROM wukong_jobs WHERE job_id = ?`
    ).bind(JOB_ID).first<Record<string, unknown>>();
    expect(job).toMatchObject({
      status: "dispatched",
      stage: "github-actions-queued",
      github_run_id: 99101,
      dispatch_attempts: 2
    });
    const locks = await bindings.DB.prepare(
      "SELECT COUNT(*) AS count FROM wukong_build_locks WHERE job_id = ?"
    ).bind(JOB_ID).first<{ count: number }>();
    expect(Number(locks?.count)).toBe(2);
  });

  it("fails, compensates and notifies exactly once after retries are exhausted", async () => {
    await seedPreBootstrapJob(3);
    mockStartupFailure();

    await recoverPreBootstrapJobs(env as unknown as Env);
    await recoverPreBootstrapJobs(env as unknown as Env);

    const bindings = env as unknown as Env;
    const job = await bindings.DB.prepare(
      "SELECT status, stage, manifest_json FROM wukong_jobs WHERE job_id = ?"
    ).bind(JOB_ID).first<Record<string, unknown>>();
    expect(job).toMatchObject({ status: "failed", stage: "startup_failed" });
    expect(JSON.parse(String(job?.manifest_json))).toMatchObject({
      error: { code: "github_actions_startup_failed" }
    });
    const user = await bindings.DB.prepare(
      "SELECT build_credits, lifetime_used, last_job_status FROM wukong_telegram_users WHERE subject = ?"
    ).bind(SUBJECT).first<Record<string, unknown>>();
    expect(user).toMatchObject({ build_credits: 1, lifetime_used: 0, last_job_status: "failed" });
    const locks = await bindings.DB.prepare(
      "SELECT COUNT(*) AS count FROM wukong_build_locks WHERE job_id = ?"
    ).bind(JOB_ID).first<{ count: number }>();
    expect(Number(locks?.count)).toBe(0);
    const compensation = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_telegram_quota_ledger
       WHERE job_id = ? AND entry_type = 'compensate'`
    ).bind(JOB_ID).first<{ count: number }>();
    expect(Number(compensation?.count)).toBe(1);
    const notifications = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_telegram_notification_outbox
       WHERE dedupe_key = ?`
    ).bind(`job-terminal:${JOB_ID}`).first<{ count: number }>();
    expect(Number(notifications?.count)).toBe(1);
  });

  it("does not finalize a job that bootstraps while recovery is listing runs", async () => {
    await seedPreBootstrapJob(3);
    mockBootstrapRace();

    await recoverPreBootstrapJobs(env as unknown as Env);

    const bindings = env as unknown as Env;
    const job = await bindings.DB.prepare(
      "SELECT status, stage FROM wukong_jobs WHERE job_id = ?"
    ).bind(JOB_ID).first<Record<string, unknown>>();
    expect(job).toMatchObject({ status: "dispatched", stage: "github-actions" });
    const user = await bindings.DB.prepare(
      "SELECT build_credits, lifetime_used FROM wukong_telegram_users WHERE subject = ?"
    ).bind(SUBJECT).first<Record<string, unknown>>();
    expect(user).toMatchObject({ build_credits: 0, lifetime_used: 1 });
    const locks = await bindings.DB.prepare(
      "SELECT COUNT(*) AS count FROM wukong_build_locks WHERE job_id = ?"
    ).bind(JOB_ID).first<{ count: number }>();
    expect(Number(locks?.count)).toBe(2);
    const notifications = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_telegram_notification_outbox
       WHERE dedupe_key = ?`
    ).bind(`job-terminal:${JOB_ID}`).first<{ count: number }>();
    expect(Number(notifications?.count)).toBe(0);
  });
});

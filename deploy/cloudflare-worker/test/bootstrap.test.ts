import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { actionsHeaders, tmaHeaders } from "./helpers";

describe("GitHub Actions bootstrap", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("verifies the GitHub run before returning the private recipe", async () => {
    const headers = {
      ...(await tmaHeaders(1678823419)),
      "Content-Type": "application/json",
      "Idempotency-Key": "bootstrap-job"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify({
        schemaVersion: 1,
        task: "build",
        device: "PKG110",
        source: { kind: "https", uri: "https://downloads.example/private-rom.zip" },
        execution: { target: "github-auto" },
        build: { preset: "plus", modVersion: "ColorOS_16.0.10", mods: [] }
      })
    });
    const job = await created.json() as { job_id: string };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(
        "https://api.github.com/repos/luukhanh24/Wukong-ROM-Studio-Hybrid/actions/runs/7123"
      );
      expect(new Headers(init?.headers).get("Authorization")).toBe(
        `Bearer ${(env as unknown as Env).WUKONG_GITHUB_TOKEN}`
      );
      return Response.json({
        id: 7123,
        event: "workflow_dispatch",
        display_title: `${job.job_id} · Wukong Hybrid`,
        path: ".github/workflows/wukong-build.yml",
        repository: { full_name: "luukhanh24/Wukong-ROM-Studio-Hybrid" }
      });
    }));

    const body = JSON.stringify({ jobId: job.job_id, runId: 7123 });
    const response = await SELF.fetch("https://worker.example/internal/actions/bootstrap", {
      method: "POST",
      headers: {
        ...(await actionsHeaders(body)),
        Authorization: `Bearer ${"g".repeat(40)}`,
      },
      body
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      jobId: job.job_id,
      runId: 7123,
      repository: "luukhanh24/Wukong-ROM-Studio-Hybrid",
      recipe: {
        source: { uri: "https://downloads.example/private-rom.zip" }
      }
    });
  });

  it("rejects bootstrap requests without the Actions callback signature", async () => {
    const response = await SELF.fetch("https://worker.example/internal/actions/bootstrap", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${"g".repeat(40)}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ jobId: "unsigned-bootstrap", runId: 7122 })
    });
    expect(response.status).toBe(403);
  });

  it("returns a bounded GitHub verification error without exposing credentials", async () => {
    const bindings = env as unknown as Env;
    const now = new Date().toISOString();
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at,
          build_credits, lifetime_granted)
         VALUES ('45002', 'approved', 'user', ?, ?, 1, 1)`
      ).bind(now, now),
      bindings.DB.prepare(
        "INSERT INTO wukong_telegram_access (subject, role) VALUES ('45002', 'user')"
      )
    ]);
    const headers = {
      ...(await tmaHeaders(45002)),
      "Content-Type": "application/json",
      "Idempotency-Key": "bootstrap-github-error"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify({
        schemaVersion: 1,
        task: "build",
        device: "PKG112",
        source: { kind: "https", uri: "https://downloads.example/private-rom.zip" },
        execution: { target: "github-auto" },
        build: { preset: "plus", modVersion: "ColorOS_16.0.10", mods: [] }
      })
    });
    const job = await created.json() as { job_id: string };
    vi.stubGlobal("fetch", vi.fn(() => Response.json(
      { message: "Resource not accessible by integration", secret: "must-not-leak" },
      { status: 403 }
    )));
    const body = JSON.stringify({ jobId: job.job_id, runId: 7125 });
    const response = await SELF.fetch("https://worker.example/internal/actions/bootstrap", {
      method: "POST",
      headers: {
        ...(await actionsHeaders(body)),
        Authorization: `Bearer ${"g".repeat(40)}`
      },
      body
    });
    const payload = await response.json() as { error: string };
    expect(response.status).toBe(403);
    expect(payload.error).toContain("Resource not accessible by integration");
    expect(payload.error).not.toContain("must-not-leak");
  });

  it("does not bootstrap a job that was cancelled before its run appeared", async () => {
    const bindings = env as unknown as Env;
    const now = new Date().toISOString();
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at,
          build_credits, lifetime_granted)
         VALUES ('45001', 'approved', 'user', ?, ?, 1, 1)`
      ).bind(now, now),
      bindings.DB.prepare(
        "INSERT INTO wukong_telegram_access (subject, role) VALUES ('45001', 'user')"
      )
    ]);
    const headers = {
      ...(await tmaHeaders(45001)),
      "Content-Type": "application/json",
      "Idempotency-Key": "cancel-before-bootstrap"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify({
        schemaVersion: 1,
        task: "build",
        device: "PKG111",
        source: { kind: "https", uri: "https://downloads.example/private-rom.zip" },
        execution: { target: "github-auto" },
        build: { preset: "plus", modVersion: "ColorOS_16.0.10", mods: [] }
      })
    });
    const job = await created.json() as { job_id: string };
    const cancelled = await SELF.fetch(
      `https://worker.example/v1/jobs/${job.job_id}/cancel`,
      { method: "POST", headers }
    );
    expect(cancelled.status).toBe(200);
    vi.stubGlobal("fetch", vi.fn(() => {
      throw new Error("A terminal job must be rejected before GitHub verification");
    }));

    const body = JSON.stringify({ jobId: job.job_id, runId: 7124 });
    const response = await SELF.fetch(
      "https://worker.example/internal/actions/bootstrap",
      {
        method: "POST",
        headers: {
          ...(await actionsHeaders(body)),
          Authorization: `Bearer ${"g".repeat(40)}`,
        },
        body
      }
    );
    expect(response.status).toBe(409);
  });

  it("rejects bootstrap when recovery finalizes the job during GitHub verification", async () => {
    const bindings = env as unknown as Env;
    const now = new Date().toISOString();
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at,
          build_credits, lifetime_granted)
         VALUES ('45003', 'approved', 'user', ?, ?, 1, 1)`
      ).bind(now, now),
      bindings.DB.prepare(
        "INSERT INTO wukong_telegram_access (subject, role) VALUES ('45003', 'user')"
      )
    ]);
    const headers = {
      ...(await tmaHeaders(45003)),
      "Content-Type": "application/json",
      "Idempotency-Key": "bootstrap-recovery-race"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify({
        schemaVersion: 1,
        task: "build",
        device: "PKG113",
        source: { kind: "https", uri: "https://downloads.example/private-rom.zip" },
        execution: { target: "github-auto" },
        build: { preset: "plus", modVersion: "ColorOS_16.0.10", mods: [] }
      })
    });
    const job = await created.json() as { job_id: string };
    vi.stubGlobal("fetch", vi.fn(async () => {
      const finalizedAt = new Date().toISOString();
      await bindings.DB.prepare(
        `UPDATE wukong_jobs
         SET status = 'failed', stage = 'startup_failed',
             updated_at = ?, finished_at = ?
         WHERE job_id = ?`
      ).bind(finalizedAt, finalizedAt, job.job_id).run();
      return Response.json({
        id: 7126,
        event: "workflow_dispatch",
        display_title: `${job.job_id} · Wukong Hybrid`,
        path: ".github/workflows/wukong-build.yml",
        repository: { full_name: "luukhanh24/Wukong-ROM-Studio-Hybrid" }
      });
    }));

    const body = JSON.stringify({ jobId: job.job_id, runId: 7126 });
    const response = await SELF.fetch("https://worker.example/internal/actions/bootstrap", {
      method: "POST",
      headers: {
        ...(await actionsHeaders(body)),
        Authorization: `Bearer ${"g".repeat(40)}`
      },
      body
    });

    expect(response.status).toBe(409);
    const dispatchedEvents = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_job_events
       WHERE job_id = ? AND event_type = 'dispatched'`
    ).bind(job.job_id).first<{ count: number }>();
    expect(Number(dispatchedEvents?.count)).toBe(0);
  });
});

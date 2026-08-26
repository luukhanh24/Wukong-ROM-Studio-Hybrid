import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tmaHeaders } from "./helpers";

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
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(
        "https://api.github.com/repos/luukhanh24/Wukong-ROM-Studio-Hybrid/actions/runs/7123"
      );
      return Response.json({
        id: 7123,
        event: "workflow_dispatch",
        display_title: `${job.job_id} · Wukong Hybrid`,
        path: ".github/workflows/wukong-build.yml",
        repository: { full_name: "luukhanh24/Wukong-ROM-Studio-Hybrid" }
      });
    }));

    const response = await SELF.fetch("https://worker.example/internal/actions/bootstrap", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${"g".repeat(40)}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ jobId: job.job_id, runId: 7123 })
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

    const response = await SELF.fetch(
      "https://worker.example/internal/actions/bootstrap",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${"g".repeat(40)}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ jobId: job.job_id, runId: 7124 })
      }
    );
    expect(response.status).toBe(409);
  });
});

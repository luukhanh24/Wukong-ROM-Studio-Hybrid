import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { actionsHeaders, tmaHeaders } from "./helpers";

const recipe = {
  schemaVersion: 1,
  task: "build",
  device: "PJD110",
  source: { kind: "https", uri: "https://downloads.example/rom.zip" },
  execution: { target: "github-auto" },
  build: { preset: "custom", modVersion: "ColorOS_16.0.10", mods: ["Core"] }
};

describe("GitHub Actions callbacks", () => {
  it("deduplicates callbacks, prevents progress regression, and releases locks once", async () => {
    const headers = {
      ...(await tmaHeaders(1678823419)),
      "Content-Type": "application/json",
      "Idempotency-Key": "callback-job"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify(recipe)
    });
    const job = await created.json() as { job_id: string };

    const progressBody = JSON.stringify({
      jobId: job.job_id,
      runId: 9001,
      sequence: 4,
      status: "running",
      stage: "download",
      progress: 0.6,
      events: [{ sequence: 4, type: "state", stage: "download", progress: 0.6 }]
    });
    const progressed = await SELF.fetch("https://worker.example/internal/actions/progress", {
      method: "POST",
      headers: await actionsHeaders(progressBody),
      body: progressBody
    });
    const duplicate = await SELF.fetch("https://worker.example/internal/actions/progress", {
      method: "POST",
      headers: await actionsHeaders(progressBody),
      body: progressBody
    });
    expect(progressed.status).toBe(200);
    expect(duplicate.status).toBe(200);

    const staleBody = JSON.stringify({
      jobId: job.job_id,
      runId: 9001,
      sequence: 3,
      status: "running",
      stage: "preflight",
      progress: 0.6,
      events: [{ sequence: 3, type: "state", stage: "preflight", progress: 0.6 }]
    });
    await SELF.fetch("https://worker.example/internal/actions/progress", {
      method: "POST",
      headers: await actionsHeaders(staleBody),
      body: staleBody
    });

    const terminalBody = JSON.stringify({
      jobId: job.job_id,
      runId: 9001,
      workflowResult: "success",
      sequence: 5,
      manifest: {
        status: "succeeded",
        stage: "complete",
        progress: 1,
        runner: "ubuntu-24.04",
        rom_metadata: {
          version: "PJD110_16.0.10.500(CN01)",
          androidVersion: "16",
          securityPatch: "2026-08-01",
          buildDate: "2026-08-11 09:38:18"
        },
        created_at: "2026-08-26T15:00:00.000Z",
        finished_at: "2026-08-26T15:42:05.000Z",
        artifacts: [{
          name: "Wukong_Plus_V6.0_PJD110.zip",
          size_bytes: 8_444_909_399,
          sha256: "a".repeat(64),
          public_url: "https://drive.google.com/file/d/fixture/view"
        }]
      }
    });
    const terminalHeaders = await actionsHeaders(terminalBody);
    const terminal = await SELF.fetch("https://worker.example/internal/actions/callback", {
      method: "POST",
      headers: terminalHeaders,
      body: terminalBody
    });
    const terminalRetry = await SELF.fetch("https://worker.example/internal/actions/callback", {
      method: "POST",
      headers: terminalHeaders,
      body: terminalBody
    });
    expect(terminal.status).toBe(200);
    expect(terminalRetry.status).toBe(200);

    const detail = await SELF.fetch(`https://worker.example/v1/jobs/${job.job_id}`, { headers });
    await expect(detail.json()).resolves.toMatchObject({
      status: "succeeded",
      stage: "complete",
      progress: 1,
      artifacts: [{
        edition: "Plus",
        downloadAvailable: true,
        publicUrl: "https://drive.google.com/file/d/fixture/view"
      }],
      rom_metadata: {
        version: "PJD110_16.0.10.500(CN01)",
        androidVersion: "16",
        securityPatch: "2026-08-01",
        buildDate: "2026-08-11 09:38:18"
      }
    });
    const bindings = env as unknown as Env;
    const locks = await bindings.DB.prepare(
      "SELECT COUNT(*) AS count FROM wukong_build_locks WHERE job_id = ?"
    ).bind(job.job_id).first<{ count: number }>();
    const notifications = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count, payload_json
       FROM wukong_telegram_notification_outbox WHERE dedupe_key = ?`
    ).bind(`job-terminal:${job.job_id}`).first<{ count: number; payload_json: string }>();
    expect(Number(locks?.count)).toBe(0);
    expect(Number(notifications?.count)).toBe(1);
    const notification = JSON.parse(String(notifications?.payload_json)) as {
      text: string;
      reply_markup: { inline_keyboard: Array<Array<Record<string, unknown>>> };
    };
    expect(notification.text).toContain("<b>Wukong ROM Studio</b>");
    expect(notification.text).toContain("<b>Build ROM hoàn tất</b>");
    expect(notification.text).toContain("Thiết bị  <code>PJD110</code>");
    expect(notification.text).toContain("Phiên bản  <code>PJD110_16.0.10.500(CN01)</code>");
    expect(notification.text).toContain("Android  <code>16</code>");
    expect(notification.text).toContain("Bản vá  <code>2026-08-01</code>");
    expect(notification.text).toContain("Ngày build  <code>2026-08-11 09:38:18</code>");
    expect(notification.text).toContain("Bản build  <code>Custom</code>");
    expect(notification.text).toContain("MOD pack  <code>ColorOS_16.0.10</code>");
    expect(notification.text).toContain("Runner  <code>ubuntu-24.04</code>");
    expect(notification.text).toContain("Thời gian  <code>42 phút 5 giây</code>");
    expect(notification.text).toContain("<b>Plus</b> · 7.86 GiB");
    expect(notification.text).toContain(`SHA-256  <code>${"a".repeat(64)}</code>`);
    expect(notification.reply_markup.inline_keyboard).toEqual([
      [{
        text: "Tải Plus · 7.86 GiB",
        url: "https://drive.google.com/file/d/fixture/view"
      }],
      [{
        text: "Mở Wukong Mini App",
        web_app: { url: "https://wukong-rom-studio.vercel.app/" }
      }]
    ]);
  });

  it("compensates a pre-executor failure exactly once", async () => {
    const bindings = env as unknown as Env;
    const subject = "43001";
    const now = new Date().toISOString();
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at,
          build_credits, lifetime_granted)
         VALUES (?, 'approved', 'user', ?, ?, 1, 1)`
      ).bind(subject, now, now),
      bindings.DB.prepare(
        "INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user')"
      ).bind(subject)
    ]);
    const headers = {
      ...(await tmaHeaders(Number(subject))),
      "Content-Type": "application/json",
      "Idempotency-Key": "pre-executor-failure"
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers,
      body: JSON.stringify({ ...recipe, device: "PJD111" })
    });
    expect(created.status).toBe(201);
    const job = await created.json() as { job_id: string };
    const terminalBody = JSON.stringify({
      jobId: job.job_id,
      runId: 9002,
      workflowResult: "failure",
      preExecutorFailure: true,
      sequence: 3
    });
    const terminalHeaders = await actionsHeaders(terminalBody);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const terminal = await SELF.fetch(
        "https://worker.example/internal/actions/callback",
        {
          method: "POST",
          headers: terminalHeaders,
          body: terminalBody
        }
      );
      expect(terminal.status).toBe(200);
    }

    const me = await SELF.fetch("https://worker.example/v1/me", { headers });
    await expect(me.json()).resolves.toMatchObject({
      user: { buildCredits: 1, lifetimeUsed: 0, jobCount: 1 }
    });
    const compensation = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count
       FROM wukong_telegram_quota_ledger
       WHERE job_id = ? AND entry_type = 'compensate'`
    ).bind(job.job_id).first<{ count: number }>();
    expect(Number(compensation?.count)).toBe(1);
  });
});

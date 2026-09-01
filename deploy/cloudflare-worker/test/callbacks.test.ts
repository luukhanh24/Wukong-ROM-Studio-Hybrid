import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { actionsHeaders, tmaHeaders } from "./helpers";

const recipe = {
  schemaVersion: 1,
  task: "build",
  device: "PJD110",
  source: { kind: "https", uri: "https://downloads.example/rom.zip" },
  execution: { target: "github-auto" },
  build: { preset: "custom", modVersion: "ColorOS_16.0.10", modReleaseVersion: "V6.0", mods: ["Core"] }
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
          public_url: "https://drive.google.com/file/d/fixture/view",
          mirrors: [{
            provider: "dccloud",
            status: "failed",
            error_code: "remote_upload_failed"
          }]
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
    const automaticRepairs = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count, state, attempts
       FROM wukong_mirror_repair_outbox WHERE job_id = ?`
    ).bind(job.job_id).first<{ count: number; state: string; attempts: number }>();
    expect(automaticRepairs).toMatchObject({ count: 1, state: "dispatched", attempts: 1 });
    const notification = JSON.parse(String(notifications?.payload_json)) as {
      text: string;
      reply_markup: { inline_keyboard: Array<Array<Record<string, unknown>>> };
    };
    expect(notification.text).toContain("<b>✅ BUILD ROM HOÀN TẤT</b>");
    expect(notification.text).toContain("<i>Wukong ROM Studio</i>");
    expect(notification.text).toContain("<b>OnePlus 12</b> · <code>PJD110</code>");
    expect(notification.text).toContain("<b>Thành công</b>");
    expect(notification.text).toContain("<i>Phiên bản ROM</i>  <code>PJD110_16.0.10.500(CN01)</code>");
    expect(notification.text).toContain("<i>Android</i>  <code>16</code>");
    expect(notification.text).toContain("<i>Bản vá</i>  <code>2026-08-01</code>");
    expect(notification.text).toContain("<i>Ngày build</i>  <code>2026-08-11 09:38:18</code>");
    expect(notification.text).toContain("<b>Custom</b> · <code>ColorOS_16.0.10</code> · <code>V6.0</code>");
    expect(notification.text).toContain("<i>Runner</i>  <code>ubuntu-24.04</code>");
    expect(notification.text).toContain("<i>Thời gian</i>  <code>42 phút 5 giây</code>");
    expect(notification.text).toContain("<b>Plus</b> · <b>7.86 GiB</b>");
    expect(notification.text).toContain(`<i>SHA-256</i>  <code>${"a".repeat(64)}</code>`);
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

  it("syncs a repaired DC Cloud mirror into the control-plane manifest", async () => {
    const bindings = env as unknown as Env;
    const jobId = "mirror-callback-fixture";
    const subject = "43002";
    const now = new Date().toISOString();
    const artifact = {
      name: "Wukong_Plus_V6.0_fixture.zip",
      uri: "wukong-gdrive:WukongROM/artifacts/fixture.zip",
      size_bytes: 123456,
      sha256: "b".repeat(64),
      public_url: "https://drive.google.com/file/d/fixture/view",
      mirrors: [{ provider: "dccloud", status: "failed", error_code: "remote_upload_failed" }]
    };
    await bindings.DB.batch([
      bindings.DB.prepare("DELETE FROM wukong_jobs WHERE job_id = ?").bind(jobId),
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at, build_credits, lifetime_granted)
         VALUES (?, 'approved', 'user', ?, ?, 1, 1)
         ON CONFLICT (subject) DO UPDATE SET access_status = 'approved', role = 'user'`
      ).bind(subject, now, now),
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user')
         ON CONFLICT (subject) DO UPDATE SET role = 'user'`
      ).bind(subject),
      bindings.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at, owner_channel,
          owner_subject, device, status, stage, progress)
         VALUES (?, ?, '{}', ?, ?, 'telegram', ?, 'PJD110', 'succeeded', 'complete', 1)`
      ).bind(jobId, JSON.stringify({ job_id: jobId, status: "succeeded", artifacts: [artifact] }), now, now, subject)
    ]);
    const body = JSON.stringify({
      jobId,
      runId: 99001,
      manifest: {
        job_id: jobId,
        artifacts: [{
          ...artifact,
          mirrors: [{
            provider: "dccloud",
            status: "available",
            uri: "https://cloud.dabeecao.org/dav/ROM/artifacts/fixture.zip",
            browse_url: "https://cloud.dabeecao.org/s/BokhN"
          }]
        }]
      }
    });
    const response = await SELF.fetch("https://worker.example/internal/actions/mirror-repair", {
      method: "POST",
      headers: await actionsHeaders(body),
      body
    });
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ jobId, mirrorRepair: true });

    const headers = await tmaHeaders(Number(subject));
    const detail = await SELF.fetch(`https://worker.example/v1/jobs/${jobId}`, { headers });
    await expect(detail.json()).resolves.toMatchObject({
      status: "succeeded",
      artifacts: [{
        mirrors: [{
          provider: "dccloud",
          status: "available",
          browse_url: "https://cloud.dabeecao.org/s/BokhN"
        }]
      }]
    });
    const repairedNotification = await bindings.DB.prepare(
      `SELECT payload_json FROM wukong_telegram_notification_outbox
       WHERE dedupe_key = ?`
    ).bind(`job-mirror-repaired:${jobId}:99001`).first<{ payload_json: string }>();
    const repairedPayload = JSON.parse(String(repairedNotification?.payload_json)) as {
      text: string;
      reply_markup: { inline_keyboard: Array<Array<Record<string, unknown>>> };
    };
    expect(repairedPayload.text).toContain("DC Cloud mirror  <i>sẵn sàng</i>");
    expect(repairedPayload.reply_markup.inline_keyboard).toContainEqual([{
      text: "Tải Plus · 120.56 KiB (DC Cloud)",
      url: "https://cloud.dabeecao.org/s/BokhN"
    }]);
    const duplicate = await SELF.fetch("https://worker.example/internal/actions/mirror-repair", {
      method: "POST",
      headers: await actionsHeaders(body),
      body
    });
    expect(duplicate.status).toBe(200);
    await expect(duplicate.json()).resolves.toMatchObject({ duplicate: true });
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

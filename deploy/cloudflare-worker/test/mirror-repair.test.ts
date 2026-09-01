import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";

describe("DC Cloud mirror repair endpoint", () => {
  it("dispatches repair for the owner of a completed job with a failed mirror", async () => {
    const bindings = env as unknown as Env;
    const now = new Date().toISOString();
    const jobId = "mirror-repair-fixture";
    const manifest = {
      job_id: jobId,
      status: "succeeded",
      artifacts: [{
        name: "fixture.zip",
        uri: "wukong-gdrive:WukongROM/artifacts/fixture.zip",
        mirrors: [{ provider: "dccloud", status: "failed", error_code: "remote_upload_failed" }]
      }]
    };
    await bindings.DB.batch([
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_users
         (subject, access_status, role, first_seen_at, last_seen_at, build_credits, lifetime_granted)
         VALUES ('43001', 'approved', 'user', ?, ?, 1, 1)
         ON CONFLICT (subject) DO UPDATE SET access_status = 'approved', role = 'user'`
      ).bind(now, now),
      bindings.DB.prepare(
        `INSERT INTO wukong_telegram_access (subject, role) VALUES ('43001', 'user')
         ON CONFLICT (subject) DO UPDATE SET role = 'user'`
      ),
      bindings.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at, owner_channel,
          owner_subject, device, status, stage, progress)
         VALUES (?, ?, '{}', ?, ?, 'telegram', '43001', 'PKG110', 'succeeded', 'complete', 1)`
      ).bind(jobId, JSON.stringify(manifest), now, now)
    ]);
    const response = await SELF.fetch(
      `https://worker.example/v1/jobs/${jobId}/mirror-repair`,
      { method: "POST", headers: await tmaHeaders(43001) }
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "queued",
      workflow: "mirror-repair.yml",
      jobId
    });
  });
});

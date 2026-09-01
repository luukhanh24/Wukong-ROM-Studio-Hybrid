import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { tmaHeaders } from "./helpers";

afterEach(() => vi.unstubAllGlobals());

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
    const updated = await bindings.DB.prepare(
      "SELECT manifest_json FROM wukong_jobs WHERE job_id = ?"
    ).bind(jobId).first<{ manifest_json: string }>();
    expect(JSON.parse(String(updated?.manifest_json)).artifacts[0].mirrors[0].status).toBe("repairing");
  });

  it("creates a temporary direct download URL for an available mirror", async () => {
    const bindings = env as unknown as Env;
    const now = new Date().toISOString();
    const jobId = "mirror-download-fixture";
    const subject = "43003";
    const name = "Wukong_Plus_V6.0_fixture.zip";
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
      ).bind(jobId, JSON.stringify({
        job_id: jobId,
        status: "succeeded",
        artifacts: [{
          name,
          size_bytes: 123,
          sha256: "c".repeat(64),
          mirrors: [{
            provider: "dccloud",
            status: "available",
            uri: `cloudreve://my/WukongROM/ROM/artifacts/PJD110/${name}`,
            browse_url: "https://cloud.dabeecao.org/s/BokhN"
          }]
        }]
      }), now, now, subject)
    ]);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe("https://cloud.dabeecao.org/api/v4/file/url");
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        uris: [`cloudreve://BokhN@share/artifacts/PJD110/${encodeURIComponent(name)}`]
      });
      return Response.json({
        code: 0,
        data: {
          urls: [{ url: "https://dabeecao-my.sharepoint.com/download/fixture?sig=temporary" }],
          expires: "2026-09-01T12:00:00+07:00"
        }
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const response = await SELF.fetch(
      `https://worker.example/v1/jobs/${jobId}/artifacts/0/dccloud-download`,
      { headers: await tmaHeaders(Number(subject)) }
    );
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      downloadUrl: "https://dabeecao-my.sharepoint.com/download/fixture?sig=temporary",
      provider: "dccloud",
      expires: "2026-09-01T12:00:00+07:00"
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

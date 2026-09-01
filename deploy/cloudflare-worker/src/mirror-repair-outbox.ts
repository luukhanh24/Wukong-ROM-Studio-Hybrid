import { dispatchMirrorRepair } from "./github";

type JsonObject = Record<string, unknown>;

const MAX_AUTOMATIC_REPAIR_DISPATCH_ATTEMPTS = 5;

function hasFailedDcCloudMirror(manifest: JsonObject): boolean {
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  return artifacts.some((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const mirrors = Array.isArray((value as JsonObject).mirrors)
      ? (value as JsonObject).mirrors as unknown[]
      : [];
    return mirrors.some((mirrorValue) => {
      if (!mirrorValue || typeof mirrorValue !== "object" || Array.isArray(mirrorValue)) return false;
      const mirror = mirrorValue as JsonObject;
      return String(mirror.provider ?? "").trim().toLowerCase() === "dccloud"
        && String(mirror.status ?? "").trim().toLowerCase() === "failed";
    });
  });
}

export function automaticMirrorRepairStatement(
  env: Env,
  jobId: string,
  jobStatus: string,
  manifest: JsonObject,
  now: string
): D1PreparedStatement | null {
  if (jobStatus !== "succeeded" || !hasFailedDcCloudMirror(manifest)) return null;
  return env.DB.prepare(
    `INSERT OR IGNORE INTO wukong_mirror_repair_outbox
     (job_id, state, attempts, available_at, created_at)
     VALUES (?, 'pending', 0, ?, ?)`
  ).bind(jobId, now, now);
}

export async function drainAutomaticMirrorRepairOutbox(
  env: Env,
  limit = 5
): Promise<void> {
  const now = new Date().toISOString();
  const leaseExpiresAt = new Date(Date.now() + 2 * 60 * 1000).toISOString();
  const result = await env.DB.prepare(
    `SELECT job_id, attempts
     FROM wukong_mirror_repair_outbox
     WHERE available_at <= ?
       AND state IN ('pending', 'failed', 'sending')
       AND attempts < ?
     ORDER BY created_at ASC LIMIT ?`
  ).bind(
    now,
    MAX_AUTOMATIC_REPAIR_DISPATCH_ATTEMPTS,
    Math.max(1, Math.min(limit, 25))
  ).all<Record<string, unknown>>();
  for (const row of result.results) {
    const jobId = String(row.job_id ?? "");
    const claimed = await env.DB.prepare(
      `UPDATE wukong_mirror_repair_outbox
       SET state = 'sending', attempts = attempts + 1, available_at = ?
       WHERE job_id = ?
         AND available_at <= ?
         AND state IN ('pending', 'failed', 'sending')
         AND attempts < ?`
    ).bind(
      leaseExpiresAt,
      jobId,
      now,
      MAX_AUTOMATIC_REPAIR_DISPATCH_ATTEMPTS
    ).run();
    if ((claimed.meta.changes ?? 0) !== 1) continue;
    try {
      await dispatchMirrorRepair(env, jobId);
      await env.DB.prepare(
        `UPDATE wukong_mirror_repair_outbox
         SET state = 'dispatched', dispatched_at = ?, last_error = ''
         WHERE job_id = ?`
      ).bind(new Date().toISOString(), jobId).run();
    } catch (error) {
      const attempts = Number(row.attempts ?? 0) + 1;
      const delaySeconds = Math.min(3600, 2 ** Math.min(attempts, 10));
      await env.DB.prepare(
        `UPDATE wukong_mirror_repair_outbox
         SET state = 'failed', available_at = ?, last_error = ?
         WHERE job_id = ?`
      ).bind(
        new Date(Date.now() + delaySeconds * 1000).toISOString(),
        (error instanceof Error ? error.message : String(error)).slice(0, 1024),
        jobId
      ).run();
    }
  }
}

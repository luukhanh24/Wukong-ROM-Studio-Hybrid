import {
  cancelWorkflowRun,
  listWorkflowRuns,
  rerunWorkflowRun,
  type WorkflowRun
} from "./github";
import {
  acceptedJobCompensationStatements,
  type JobRow
} from "./jobs";

const MAX_DISPATCH_ATTEMPTS = 3;
const QUEUED_TIMEOUT_MS = 15 * 60 * 1000;
const RETRY_COOLDOWN_MS = 2 * 60 * 1000;

interface RecoveryJobRow extends JobRow {
  created_at: string;
  updated_at: string;
  finished_at: string;
  next_event_sequence: number;
  github_run_id: number | null;
  dispatch_attempts: number;
  dispatch_last_attempt_at: string;
}

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function matchingRun(
  env: Env,
  jobId: string,
  runs: WorkflowRun[]
): WorkflowRun | undefined {
  const expectedTitle = `${jobId} · Wukong Hybrid`;
  return runs.find((run) =>
    run.event === "workflow_dispatch" &&
    run.displayTitle === expectedTitle &&
    (!run.path || run.path.endsWith(`/${env.WUKONG_GITHUB_WORKFLOW}`))
  );
}

function parseManifest(row: RecoveryJobRow): Record<string, unknown> {
  try {
    const value = JSON.parse(row.manifest_json);
    return value && typeof value === "object" && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

async function markRecoveredDispatch(
  env: Env,
  row: RecoveryJobRow,
  runId: number,
  attempts: number,
  now: string
): Promise<void> {
  await env.DB.prepare(
    `UPDATE wukong_jobs
     SET github_run_id = COALESCE(github_run_id, ?),
         status = 'dispatched',
         stage = 'github-actions-queued',
         dispatch_attempts = ?,
         dispatch_last_attempt_at = ?,
         updated_at = ?
     WHERE job_id = ?
       AND status NOT IN ('succeeded', 'failed', 'cancelled')
       AND stage IN ('queued', 'github-actions-queued')`
  ).bind(runId, attempts, now, now, row.job_id).run();
}

async function failStartup(
  env: Env,
  row: RecoveryJobRow,
  runId: number | null,
  reason: string,
  now: string
): Promise<void> {
  const sequence = Number(row.next_event_sequence ?? 2);
  const manifest = {
    ...parseManifest(row),
    status: "failed",
    stage: "startup_failed",
    progress: Number(row.progress ?? 0),
    updated_at: now,
    finished_at: now,
    error: {
      code: "github_actions_startup_failed",
      message: reason
    }
  };
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE wukong_jobs
       SET manifest_json = ?,
           github_run_id = COALESCE(github_run_id, ?),
           status = 'failed',
           stage = 'startup_failed',
           updated_at = ?,
           finished_at = ?,
           next_event_sequence = MAX(next_event_sequence, ?)
       WHERE job_id = ?
         AND status NOT IN ('succeeded', 'failed', 'cancelled')
         AND stage IN ('queued', 'github-actions-queued')`
    ).bind(
      JSON.stringify(manifest),
      runId,
      now,
      now,
      sequence + 1,
      row.job_id
    ),
    env.DB.prepare(
      `DELETE FROM wukong_build_locks
       WHERE job_id = ?
         AND EXISTS (
           SELECT 1 FROM wukong_jobs
           WHERE job_id = ? AND status = 'failed' AND stage = 'startup_failed'
         )`
    ).bind(row.job_id, row.job_id),
    env.DB.prepare(
      `UPDATE wukong_telegram_users
       SET last_job_id = ?, last_job_status = 'failed'
       WHERE subject = ?
         AND EXISTS (
           SELECT 1 FROM wukong_jobs
           WHERE job_id = ? AND status = 'failed' AND stage = 'startup_failed'
         )`
    ).bind(row.job_id, row.owner_subject, row.job_id),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_job_events
       (job_id, sequence, timestamp, event_type, payload_json)
       SELECT ?, ?, ?, 'failed', ?
       WHERE EXISTS (
         SELECT 1 FROM wukong_jobs
         WHERE job_id = ? AND status = 'failed' AND stage = 'startup_failed'
       )`
    ).bind(
      row.job_id,
      sequence,
      now,
      JSON.stringify({
        status: "failed",
        stage: "startup_failed",
        code: "github_actions_startup_failed"
      }),
      row.job_id
    ),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
       (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
       SELECT ?, ?, ?, ?, ?, ?
       WHERE EXISTS (
         SELECT 1 FROM wukong_jobs
         WHERE job_id = ? AND status = 'failed' AND stage = 'startup_failed'
       )`
    ).bind(
      crypto.randomUUID(),
      `job-terminal:${row.job_id}`,
      row.owner_subject,
      JSON.stringify({
        text: [
          "⚠️ <b>Build không thể khởi động</b>",
          "",
          `Job: <code>${row.job_id}</code>`,
          "GitHub Actions không cấp được runner sau nhiều lần thử.",
          "Lượt build đã được hoàn lại tự động."
        ].join("\n"),
        parse_mode: "HTML",
        disable_web_page_preview: true
      }),
      now,
      now,
      row.job_id
    ),
    ...acceptedJobCompensationStatements(
      env,
      row,
      reason,
      now,
      "failed",
      { status: "failed", stage: "startup_failed" }
    )
  ]);
}

export async function recoverPreBootstrapJobs(env: Env): Promise<void> {
  const jobs = await env.DB.prepare(
    `SELECT * FROM wukong_jobs
     WHERE status NOT IN ('succeeded', 'failed', 'cancelled')
       AND stage IN ('queued', 'github-actions-queued')
       AND finished_at = ''
     ORDER BY created_at ASC
     LIMIT 50`
  ).all<RecoveryJobRow>();
  if (jobs.results.length === 0) return;

  const runs = await listWorkflowRuns(env);
  const nowMs = Date.now();
  const now = new Date(nowMs).toISOString();

  for (const row of jobs.results) {
    try {
      const run = matchingRun(env, row.job_id, runs);
      if (!run) {
        const ageMs = nowMs - timestamp(row.dispatch_last_attempt_at || row.created_at);
        if (ageMs >= QUEUED_TIMEOUT_MS) {
          await failStartup(
            env,
            row,
            null,
            "GitHub Actions did not create a workflow run before the startup timeout",
            now
          );
        }
        continue;
      }

      const attempts = Math.max(1, Number(row.dispatch_attempts ?? 0));
      const runActivityAt = Math.max(
        timestamp(run.createdAt),
        timestamp(run.updatedAt),
        timestamp(row.dispatch_last_attempt_at),
        timestamp(row.created_at)
      );
      const runAgeMs = nowMs - runActivityAt;
      if (run.status === "completed" && run.conclusion === "startup_failure") {
        if (attempts >= MAX_DISPATCH_ATTEMPTS) {
          await failStartup(
            env,
            row,
            run.id,
            "GitHub Actions reported startup_failure after all retry attempts",
            now
          );
          continue;
        }
        const sinceAttemptMs = nowMs - timestamp(row.dispatch_last_attempt_at || row.updated_at);
        if (sinceAttemptMs < RETRY_COOLDOWN_MS) continue;
        await rerunWorkflowRun(env, run.id);
        await markRecoveredDispatch(env, row, run.id, attempts + 1, now);
        continue;
      }

      if (run.status === "queued" && runAgeMs >= QUEUED_TIMEOUT_MS) {
        try {
          await cancelWorkflowRun(env, run.id);
        } catch (error) {
          console.error("Failed to cancel a timed-out pre-bootstrap run", {
            jobId: row.job_id,
            runId: run.id,
            error: error instanceof Error ? error.message : String(error)
          });
        }
        await failStartup(
          env,
          row,
          run.id,
          "GitHub Actions workflow remained queued beyond the startup timeout",
          now
        );
        continue;
      }

      await markRecoveredDispatch(env, row, run.id, attempts, now);
    } catch (error) {
      console.error("Pre-bootstrap recovery failed for a job", {
        jobId: row.job_id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
}

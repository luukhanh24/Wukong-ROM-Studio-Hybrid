import type { JobRow } from "./jobs";

type JsonObject = Record<string, unknown>;

export interface WorkflowRun {
  id: number;
  event: string;
  displayTitle: string;
  path: string;
  status: string;
  conclusion: string;
  createdAt: string;
  updatedAt: string;
}

export class GitHubHttpError extends Error {
  constructor(message: string, readonly status = 502) {
    super(message);
  }
}

function repositoryParts(env: Env): [string, string] {
  const parts = env.WUKONG_GITHUB_REPOSITORY.trim().split("/");
  if (
    parts.length !== 2 ||
    !parts[0] ||
    !parts[1] ||
    !/^[A-Za-z0-9_.-]+$/.test(parts[0]) ||
    !/^[A-Za-z0-9_.-]+$/.test(parts[1])
  ) {
    throw new GitHubHttpError("GitHub repository is not configured", 503);
  }
  return [parts[0], parts[1]];
}

async function githubFetch(
  env: Env,
  path: string,
  init: RequestInit = {},
  token = env.WUKONG_GITHUB_TOKEN
): Promise<Response> {
  const response = await fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "User-Agent": "wukong-control-plane-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers ?? {})
    }
  });
  return response;
}

export async function dispatchBuild(env: Env, jobId: string): Promise<void> {
  if (env.WUKONG_DISABLE_EXTERNAL_DISPATCH === "1") return;
  if (!env.WUKONG_GITHUB_TOKEN.trim()) {
    throw new GitHubHttpError("GitHub Actions dispatch is not configured", 503);
  }
  const [owner, repository] = repositoryParts(env);
  const workflow = encodeURIComponent(env.WUKONG_GITHUB_WORKFLOW || "wukong-build.yml");
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      body: JSON.stringify({
        ref: env.WUKONG_GITHUB_REF || "main",
        inputs: {
          job_id: jobId,
          recipe_ref: `worker://${jobId}`
        }
      })
    }
  );
  if (response.status !== 204) {
    const detail = (await response.text()).slice(0, 512);
    throw new GitHubHttpError(
      `GitHub Actions dispatch failed (${response.status})${detail ? `: ${detail}` : ""}`
    );
  }
}

export async function listWorkflowRuns(env: Env): Promise<WorkflowRun[]> {
  if (!env.WUKONG_GITHUB_TOKEN.trim()) {
    throw new GitHubHttpError("GitHub Actions run lookup is not configured", 503);
  }
  const [owner, repository] = repositoryParts(env);
  const workflow = encodeURIComponent(env.WUKONG_GITHUB_WORKFLOW || "wukong-build.yml");
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/workflows/${workflow}/runs?event=workflow_dispatch&per_page=100`
  );
  if (!response.ok) {
    throw new GitHubHttpError(`GitHub Actions run lookup failed (${response.status})`);
  }
  const payload = await response.json() as JsonObject;
  const runs = Array.isArray(payload.workflow_runs) ? payload.workflow_runs : [];
  return runs.flatMap((value): WorkflowRun[] => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const item = value as JsonObject;
    const id = Number(item.id);
    if (!Number.isSafeInteger(id) || id <= 0) return [];
    return [{
      id,
      event: String(item.event ?? ""),
      displayTitle: String(item.display_title ?? ""),
      path: String(item.path ?? ""),
      status: String(item.status ?? ""),
      conclusion: String(item.conclusion ?? ""),
      createdAt: String(item.created_at ?? ""),
      updatedAt: String(item.updated_at ?? "")
    }];
  });
}

export async function rerunWorkflowRun(env: Env, runId: number): Promise<void> {
  if (!env.WUKONG_GITHUB_TOKEN.trim()) {
    throw new GitHubHttpError("GitHub Actions rerun is not configured", 503);
  }
  const [owner, repository] = repositoryParts(env);
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/runs/${runId}/rerun`,
    { method: "POST" }
  );
  if (![201, 202].includes(response.status)) {
    throw new GitHubHttpError(`GitHub Actions rerun failed (${response.status})`);
  }
}

function bearerToken(request: Request): string {
  const authorization = request.headers.get("Authorization") ?? "";
  const [scheme, token] = authorization.split(/\s+/, 2);
  if (scheme?.toLowerCase() !== "bearer" || !token || token.length < 20) {
    throw new GitHubHttpError("Actions bootstrap authentication failed", 403);
  }
  return token;
}

function bootstrapPayload(value: unknown): { jobId: string; runId: number } {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new GitHubHttpError("Actions bootstrap payload is invalid", 400);
  }
  const payload = value as JsonObject;
  const jobId = typeof payload.jobId === "string" ? payload.jobId.trim() : "";
  const runId = Number(payload.runId);
  if (
    !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(jobId) ||
    !Number.isSafeInteger(runId) ||
    runId <= 0
  ) {
    throw new GitHubHttpError("Actions bootstrap payload is invalid", 400);
  }
  return { jobId, runId };
}

async function verifyRun(
  env: Env,
  jobId: string,
  runId: number
): Promise<void> {
  if (!env.WUKONG_GITHUB_TOKEN.trim()) {
    throw new GitHubHttpError("GitHub Actions verification is not configured", 503);
  }
  const [owner, repository] = repositoryParts(env);
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/runs/${runId}`
  );
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json() as JsonObject;
      detail = typeof payload.message === "string" ? payload.message.slice(0, 256) : "";
    } catch {
      detail = "";
    }
    throw new GitHubHttpError(
      `GitHub run verification failed (${response.status})${detail ? `: ${detail}` : ""}`,
      403
    );
  }
  const run = await response.json() as JsonObject;
  const repositoryInfo = run.repository && typeof run.repository === "object"
    ? run.repository as JsonObject
    : {};
  const fullName = String(repositoryInfo.full_name ?? "").toLowerCase();
  const displayTitle = String(run.display_title ?? "");
  const workflowPath = String(run.path ?? "");
  const expectedRepository = env.WUKONG_GITHUB_REPOSITORY.toLowerCase();
  if (Number(run.id) !== runId) {
    throw new GitHubHttpError("Actions bootstrap run ID does not match", 403);
  }
  if (fullName !== expectedRepository) {
    throw new GitHubHttpError("Actions bootstrap repository does not match", 403);
  }
  if (run.event !== "workflow_dispatch") {
    throw new GitHubHttpError("Actions bootstrap event does not match", 403);
  }
  if (!displayTitle.includes(jobId)) {
    throw new GitHubHttpError("Actions bootstrap job title does not match", 403);
  }
  if (workflowPath && !workflowPath.endsWith(`/${env.WUKONG_GITHUB_WORKFLOW}`)) {
    throw new GitHubHttpError("Actions bootstrap workflow does not match", 403);
  }
}

export async function bootstrapActions(
  request: Request,
  env: Env,
  value: unknown
): Promise<JsonObject> {
  bearerToken(request);
  const { jobId, runId } = bootstrapPayload(value);
  const row = await env.DB.prepare("SELECT * FROM wukong_jobs WHERE job_id = ?")
    .bind(jobId)
    .first<JobRow>();
  if (!row) throw new GitHubHttpError("Job not found", 404);
  if (["succeeded", "failed", "cancelled"].includes(row.status)) {
    throw new GitHubHttpError("Actions bootstrap job is already terminal", 409);
  }
  if (row.github_run_id != null && Number(row.github_run_id) !== runId) {
    throw new GitHubHttpError("Actions bootstrap run does not match the job", 409);
  }
  await verifyRun(env, jobId, runId);
  const now = new Date().toISOString();
  const sequence = Number(row.next_event_sequence ?? 2);
  const results = await env.DB.batch([
    env.DB.prepare(
      `UPDATE wukong_jobs SET github_run_id = ?, status = 'dispatched',
       stage = 'github-actions', updated_at = ?, next_event_sequence = MAX(next_event_sequence, ?)
       WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')`
    ).bind(runId, now, sequence + 1, jobId),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_job_events
       (job_id, sequence, timestamp, event_type, payload_json)
       SELECT ?, ?, ?, 'dispatched', ?
       WHERE EXISTS (
         SELECT 1 FROM wukong_jobs
         WHERE job_id = ? AND status = 'dispatched'
           AND stage = 'github-actions' AND github_run_id = ?
       )`
    ).bind(
      jobId,
      sequence,
      now,
      JSON.stringify({ runner: "github-actions" }),
      jobId,
      runId
    )
  ]);
  if ((results[0]?.meta.changes ?? 0) !== 1) {
    throw new GitHubHttpError("Actions bootstrap job became terminal", 409);
  }
  return {
    jobId,
    runId,
    repository: env.WUKONG_GITHUB_REPOSITORY,
    recipe: JSON.parse(row.recipe_json),
    nextEventSequence: sequence + 1
  };
}

export async function cancelWorkflowRun(env: Env, runId: number): Promise<void> {
  if (env.WUKONG_DISABLE_EXTERNAL_DISPATCH === "1") return;
  if (!env.WUKONG_GITHUB_TOKEN.trim()) {
    throw new GitHubHttpError("GitHub Actions cancel is not configured", 503);
  }
  const [owner, repository] = repositoryParts(env);
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/runs/${runId}/cancel`,
    { method: "POST" }
  );
  if (![202, 409].includes(response.status)) {
    throw new GitHubHttpError(`GitHub Actions cancel failed (${response.status})`);
  }
}

export async function cancelWorkflowRunForJob(
  env: Env,
  jobId: string,
  knownRunId: number | null
): Promise<number | null> {
  if (env.WUKONG_DISABLE_EXTERNAL_DISPATCH === "1") return knownRunId;
  if (!env.WUKONG_GITHUB_TOKEN.trim()) {
    throw new GitHubHttpError("GitHub Actions cancel is not configured", 503);
  }
  if (knownRunId != null) {
    await cancelWorkflowRun(env, knownRunId);
    return knownRunId;
  }
  const runs = await listWorkflowRuns(env);
  const run = runs.find((item) => {
    return (
      item.event === "workflow_dispatch" &&
      item.displayTitle.startsWith(`${jobId} ·`) &&
      (!item.path || item.path.endsWith(`/${env.WUKONG_GITHUB_WORKFLOW}`))
    );
  });
  const runId = Number(run?.id);
  if (!Number.isSafeInteger(runId) || runId <= 0) return null;
  await cancelWorkflowRun(env, runId);
  return runId;
}

export async function listActionsCaches(env: Env): Promise<JsonObject> {
  const [owner, repository] = repositoryParts(env);
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/caches?per_page=100`
  );
  if (!response.ok) throw new GitHubHttpError(`GitHub Actions cache query failed (${response.status})`);
  const payload = await response.json() as JsonObject;
  const caches = Array.isArray(payload.actions_caches) ? payload.actions_caches : [];
  return {
    entryCount: Number(payload.total_count ?? caches.length),
    totalBytes: caches.reduce((total, value) => {
      const item = value && typeof value === "object" ? value as JsonObject : {};
      return total + Number(item.size_in_bytes ?? 0);
    }, 0),
    entries: caches
  };
}

export async function clearActionsCaches(env: Env): Promise<JsonObject> {
  const [owner, repository] = repositoryParts(env);
  const response = await githubFetch(
    env,
    `/repos/${owner}/${repository}/actions/caches`,
    { method: "DELETE" }
  );
  if (![204, 404].includes(response.status)) {
    throw new GitHubHttpError(`GitHub Actions cache clearing failed (${response.status})`);
  }
  return { entryCount: 0, totalBytes: 0 };
}

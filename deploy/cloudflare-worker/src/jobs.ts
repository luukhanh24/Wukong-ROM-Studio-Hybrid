import type { AuthenticatedRequest } from "./auth";
import { artifactEdition } from "./artifact-metadata";
import { cancelWorkflowRunForJob, dispatchBuild } from "./github";
import { directArtifactUrl } from "./public-links";
import { terminalTelegramNotification } from "./telegram-notifications";
import { buildStartedAdminStatements } from "./activity";

type JsonObject = Record<string, unknown>;

const JOB_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

async function queueBuildStartedAdminAlert(
  env: Env,
  auth: AuthenticatedRequest,
  jobId: string,
  recipe: JsonObject,
  now: string,
  previousJobId = ""
): Promise<void> {
  const statements = buildStartedAdminStatements(
    env,
    auth,
    jobId,
    recipe,
    now,
    previousJobId
  );
  if (!statements.length) return;
  await env.DB.batch(statements).catch(() => {
    console.error("Build-start admin notification could not be queued");
  });
}

async function repairBuildStartedAdminAlert(
  env: Env,
  auth: AuthenticatedRequest,
  row: JobRow,
  previousJobId = ""
): Promise<void> {
  if (Number(row.dispatch_attempts ?? 0) < 1) return;
  await queueBuildStartedAdminAlert(
    env,
    auth,
    row.job_id,
    parseJson(row.recipe_json),
    String(row.created_at ?? new Date().toISOString()),
    previousJobId
  );
}
const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);
const PRIVATE_PUBLIC_KEYS = new Set([
  "actionsurl",
  "externalrunid",
  "githubrunid",
  "githubowner",
  "githuburl",
  "htmlurl",
  "ownerlogin",
  "repository",
  "repositoryowner",
  "repo",
  "runid"
]);

export interface JobRow extends Record<string, unknown> {
  job_id: string;
  manifest_json: string;
  recipe_json: string;
  status: string;
  owner_subject: string;
  owner_channel: string;
  stage: string;
  progress: number;
}

export class JobHttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = ""
  ) {
    super(message);
  }
}

function object(value: unknown, label: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new JobHttpError(`${label} must be an object`, 400);
  }
  return value as JsonObject;
}

function requiredText(value: unknown, label: string, maxLength = 8192): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized || normalized.length > maxLength) {
    throw new JobHttpError(`${label} is required`, 400);
  }
  return normalized;
}

export function validateRecipe(value: unknown): JsonObject {
  const recipe = object(value, "Build recipe");
  if (recipe.schemaVersion !== 1) {
    throw new JobHttpError("Build recipe schemaVersion must be 1", 400);
  }
  const task = requiredText(recipe.task, "Build task", 64);
  if (!["build", "source_mirror", "artifact_publish"].includes(task)) {
    throw new JobHttpError("Build task is not supported", 400);
  }
  const device = requiredText(recipe.device, "Build device", 64);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(device)) {
    throw new JobHttpError("Build device is invalid", 400);
  }
  const source = object(recipe.source, "ROM source");
  const uri = requiredText(source.uri, "ROM source URL");
  const kind = requiredText(source.kind, "ROM source kind", 32).toLowerCase();
  if (
    !["https", "http", "drive", "rclone", "danielspringer"].includes(kind) ||
    (!/^https?:\/\//i.test(uri) && !/^[A-Za-z0-9_.-]+:.+/.test(uri))
  ) {
    throw new JobHttpError("ROM source is invalid", 400);
  }
  const build = object(recipe.build, "Build configuration");
  const preset = requiredText(build.preset, "Build preset", 16).toLowerCase();
  if (!["lite", "plus", "both", "custom"].includes(preset)) {
    throw new JobHttpError("Build preset is invalid", 400);
  }
  requiredText(build.modVersion, "MOD version", 128);
  object(recipe.execution, "Execution policy");
  const storage = recipe.storage === undefined ? {} : object(recipe.storage, "Storage configuration");
  if (storage.artifactRoot !== undefined) {
    const root = requiredText(storage.artifactRoot, "Artifact root", 256).replaceAll("\\", "/");
    if (root.startsWith("/") || /^[A-Za-z]:/.test(root) || root.split("/").some(part => !part || part === ".." || /[\u0000-\u001f]/.test(part))) {
      throw new JobHttpError("Artifact root must be a safe relative Drive path", 400);
    }
    storage.artifactRoot = root;
  }
  const canonical = JSON.stringify(recipe);
  if (new TextEncoder().encode(canonical).byteLength > 1024 * 1024) {
    throw new JobHttpError("Build recipe is too large", 413);
  }
  return JSON.parse(canonical) as JsonObject;
}

function parseJson(value: unknown): JsonObject {
  try {
    const parsed = JSON.parse(String(value ?? "{}"));
    return object(parsed, "Stored JSON");
  } catch {
    return {};
  }
}

function escapedPattern(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function sanitizePublicValue(value: unknown, env: Env): unknown {
  if (typeof value === "string") {
    let sanitized = value.replace(/https?:\/\/[^\s<>"']+/gi, (raw) => {
      try {
        const url = new URL(raw);
        const signed = [...url.searchParams.keys()].some(key => /^(s|sign|signature|awsaccesskeyid|x-amz-.+)$|token|secret|password|credential|authorization|api[_-]?key/i.test(key));
        if (signed || url.username || url.password) return `${url.origin}${url.pathname}?[redacted]`;
      } catch { /* Keep non-URL prose intact. */ }
      return raw;
    }).replace(/\b(authorization\s*[:=]\s*)(?:Bearer|Basic)\s+[^\s,;]+/gi, "$1[redacted]")
      .replace(/\b((?:access[_-]?token|refresh[_-]?token|token|secret|password|authorization|api[_-]?key)\s*[:=]\s*)[^\s,;]+/gi, "$1[redacted]").replace(
      /https?:\/\/(?:api\.)?github\.com\/\S+/gi,
      "[internal build reference]"
    );
    const repository = env.WUKONG_GITHUB_REPOSITORY.trim();
    if (repository) {
      sanitized = sanitized.replace(
        new RegExp(`\\b${escapedPattern(repository)}\\b`, "gi"),
        "[internal repository]"
      );
      const owner = repository.split("/", 1)[0]?.trim();
      if (owner) {
        sanitized = sanitized.replace(
          new RegExp(`\\b${escapedPattern(owner)}\\b`, "gi"),
          "[internal account]"
        );
      }
    }
    return sanitized.replace(
      /\b((?:(?:github|repository|repo)(?:\s+|[:=]\s*)|(?:dispatch|workflow|build|cloud\s+sync|sync)\s+(?:failed|error)\s+(?:for|in)\s+|failed\s+checkout\s+of\s+|(?:cannot|could\s+not)\s+access\s+|repository\s+lookup\s+|(?:checkout|clone|fetch|pull|push)\s+))[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\b/gi,
      "$1[internal repository]"
    );
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizePublicValue(item, env));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as JsonObject)
        .filter(([key]) => {
          const normalized = key.replace(/[^a-z0-9]/gi, "").toLowerCase();
          return !PRIVATE_PUBLIC_KEYS.has(normalized) && !/token|secret|password|credential|authorization|apikey|privatekey|clientid/.test(normalized);
        })
        .map(([key, item]) => [key, sanitizePublicValue(item, env)])
    );
  }
  return value;
}

function publicRecipe(recipe: JsonObject): JsonObject {
  const source = (recipe.source && typeof recipe.source === "object"
    ? recipe.source
    : {}) as JsonObject;
  const build = (recipe.build && typeof recipe.build === "object"
    ? recipe.build
    : {}) as JsonObject;
  const execution = (recipe.execution && typeof recipe.execution === "object"
    ? recipe.execution
    : {}) as JsonObject;
  const storage = (recipe.storage && typeof recipe.storage === "object"
    ? recipe.storage
    : {}) as JsonObject;
  return {
    task: recipe.task,
    schemaVersion: recipe.schemaVersion,
    device: recipe.device,
    source: {
      kind: source.kind,
      sha256: source.sha256 ?? null,
      sizeBytes: source.sizeBytes ?? null,
      metadata: source.metadata && typeof source.metadata === "object" ? source.metadata : {}
    },
    build,
    execution,
    storage: {
      publishArtifact: Boolean(storage.publishArtifact ?? true),
      ...(typeof storage.artifactRoot === "string" ? { artifactRoot: storage.artifactRoot } : {})
    }
  };
}

export { directArtifactUrl } from "./public-links";

export function publicJob(row: JobRow, env: Env, includeCreator = false): JsonObject {
  const manifest = parseJson(row.manifest_json);
  const recipe = parseJson(row.recipe_json);
  const build = recipe.build && typeof recipe.build === "object"
    ? recipe.build as JsonObject
    : {};
  delete manifest.owner;
  delete manifest.createdBy;
  delete manifest.external_run_id;
  manifest.status = row.status;
  manifest.stage = row.stage;
  manifest.progress = Number(row.progress ?? 0);
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  manifest.artifacts = artifacts.map((value, index) => {
    const artifact = value && typeof value === "object" ? { ...(value as JsonObject) } : {};
    const url = directArtifactUrl(artifact.public_url ?? artifact.publicUrl, env);
    delete artifact.uri;
    delete artifact.public_url;
    delete artifact.publicUrl;
    return {
      ...artifact,
      edition: artifactEdition(artifact.name, index + 1, build.preset),
      downloadAvailable: Boolean(url),
      ...(url ? { publicUrl: url } : {})
    };
  });
  const result = sanitizePublicValue(
    { ...manifest, recipe: publicRecipe(recipe), ...(includeCreator && row.owner_channel === "telegram" ? {
      createdBy: { telegramId: row.owner_subject, displayName: row.owner_display_name || "", username: row.owner_username || "", photoUrl: row.owner_photo_url || "" }
    } : {}) },
    env
  ) as JsonObject;
  // Validated download capabilities are intentionally shareable. Redacting their
  // signature would break the artifact buttons while still reporting availability.
  const sanitizedArtifacts = result.artifacts as JsonObject[];
  (manifest.artifacts as JsonObject[]).forEach((artifact, index) => {
    if (artifact.publicUrl) sanitizedArtifacts[index]!.publicUrl = artifact.publicUrl;
  });
  return result;
}

export function artifactDownloadUrl(row: JobRow, env: Env): string {
  const manifest = parseJson(row.manifest_json);
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  return artifacts.map((value) => {
    const item = value && typeof value === "object" ? value as JsonObject : {};
    return directArtifactUrl(item.public_url ?? item.publicUrl, env);
  }).find(Boolean) ?? "";
}

async function existingByIdempotency(
  env: Env,
  subject: string,
  requestKey: string
): Promise<JobRow | null> {
  return env.DB.prepare(
    `SELECT j.*
     FROM wukong_telegram_quota_ledger q
     JOIN wukong_jobs j ON j.job_id = q.job_id
     WHERE q.subject = ? AND q.idempotency_key IN (?, ?)
     ORDER BY CASE WHEN q.idempotency_key = ? THEN 0 ELSE 1 END
     LIMIT 1`
  ).bind(subject, `${subject}:${requestKey}`, requestKey, `${subject}:${requestKey}`)
    .first<JobRow>();
}

function mapD1JobError(error: unknown): JobHttpError {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes("build_quota_exhausted")) {
    return new JobHttpError("No build credits remain", 403, "build_quota_exhausted");
  }
  if (message.includes("access_denied")) {
    return new JobHttpError("Telegram account is not approved", 403, "access_denied");
  }
  if (message.includes("build_concurrency_limit")) {
    return new JobHttpError(
      "The system has reached its concurrent build limit; wait for one to finish",
      409,
      "build_concurrency_limit"
    );
  }
  if (
    message.includes("wukong_build_locks") ||
    message.includes("UNIQUE constraint failed: wukong_build_locks.lock_key")
  ) {
    return new JobHttpError(
      "Another build is already active for this user or device; wait for it to finish",
      409,
      "build_concurrency_conflict"
    );
  }
  return new JobHttpError("Build job could not be accepted", 400);
}

async function recordDispatchAttempt(env: Env, jobId: string): Promise<void> {
  const dispatchedAt = new Date().toISOString();
  try {
    await env.DB.prepare(
      `UPDATE wukong_jobs
       SET dispatch_attempts = 1, dispatch_last_attempt_at = ?, updated_at = ?
       WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')`
    ).bind(dispatchedAt, dispatchedAt, jobId).run();
  } catch (error) {
    console.error("Failed to persist the initial GitHub dispatch attempt", {
      jobId,
      error: error instanceof Error ? error.message : String(error)
    });
  }
}

export async function createJob(
  env: Env,
  auth: AuthenticatedRequest,
  recipeValue: unknown,
  rawIdempotencyKey: string,
  allowBatchStorage = false
): Promise<{ job: JsonObject; created: boolean }> {
  const recipe = validateRecipe(recipeValue);
  const storage = recipe.storage && typeof recipe.storage === "object" ? recipe.storage as JsonObject : {};
  if (storage.artifactRoot !== undefined && !allowBatchStorage) {
    throw new JobHttpError("Batch artifact storage is reserved for admin batch builds", 403, "batch_storage_forbidden");
  }
  const idempotencyKey = rawIdempotencyKey.trim() || crypto.randomUUID().replaceAll("-", "");
  if (!IDEMPOTENCY_KEY.test(idempotencyKey)) {
    throw new JobHttpError("Build idempotency key is invalid", 400);
  }
  const alreadyAccepted = await existingByIdempotency(env, auth.subject, idempotencyKey);
  if (alreadyAccepted) {
    await repairBuildStartedAdminAlert(env, auth, alreadyAccepted);
    return { job: publicJob(alreadyAccepted, env), created: false };
  }
  const jobId = crypto.randomUUID().replaceAll("-", "");
  const now = new Date().toISOString();
  const device = String(recipe.device);
  const manifest: JsonObject = {
    schema_version: 1,
    job_id: jobId,
    owner: { channel: "telegram", subject: auth.subject, role: auth.role },
    task: recipe.task,
    status: "queued",
    stage: "queued",
    progress: 0,
    runner: "github-actions",
    external_run_id: "",
    created_at: now,
    updated_at: now,
    finished_at: "",
    checkpoint: null,
    artifacts: [],
    error: null
  };
  const requestKey = `${auth.subject}:${idempotencyKey}`;
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at,
          next_event_sequence, owner_channel, owner_subject, device, status, stage, progress)
         VALUES (?, ?, ?, ?, ?, 2, 'telegram', ?, ?, 'queued', 'queued', 0)`
      ).bind(jobId, JSON.stringify(manifest), JSON.stringify(recipe), now, now, auth.subject, device),
      env.DB.prepare(
        `INSERT INTO wukong_job_events
         (job_id, sequence, timestamp, event_type, payload_json)
         VALUES (?, 1, ?, 'submitted', ?)`
      ).bind(jobId, now, JSON.stringify({ runner: "github-actions", channel: "telegram" })),
      env.DB.prepare(
        `UPDATE wukong_telegram_users SET
           build_credits = CASE WHEN unlimited = 1 THEN build_credits ELSE build_credits - 1 END,
           lifetime_used = lifetime_used + CASE WHEN unlimited = 1 THEN 0 ELSE 1 END,
           job_count = job_count + 1,
           last_job_id = ?,
           last_job_status = 'queued'
         WHERE subject = ? AND access_status = 'approved'
           AND (unlimited = 1 OR build_credits > 0)`
      ).bind(jobId, auth.subject),
      env.DB.prepare(
        `INSERT INTO wukong_telegram_quota_ledger
         (ledger_id, subject, entry_type, delta, balance_after, job_id,
          idempotency_key, consumed, created_at)
         SELECT ?, subject, 'consume',
                CASE WHEN unlimited = 1 THEN 0 ELSE -1 END,
                build_credits, ?, ?, CASE WHEN unlimited = 1 THEN 0 ELSE 1 END, ?
         FROM wukong_telegram_users WHERE subject = ?`
      ).bind(crypto.randomUUID(), jobId, requestKey, now, auth.subject),
      env.DB.prepare(
        `INSERT INTO wukong_telegram_user_events
         (event_id, subject, event_type, details_json, created_at)
         VALUES (?, ?, 'build_reserved', ?, ?)`
      ).bind(
        crypto.randomUUID(),
        auth.subject,
        JSON.stringify({ jobId, consumed: !auth.profile.unlimited }),
        now
      )
    ]);
  } catch (error) {
    const retry = await existingByIdempotency(env, auth.subject, idempotencyKey);
    if (retry) {
      await repairBuildStartedAdminAlert(env, auth, retry);
      return { job: publicJob(retry, env), created: false };
    }
    throw mapD1JobError(error);
  }
  const row = await env.DB.prepare("SELECT * FROM wukong_jobs WHERE job_id = ?")
    .bind(jobId)
    .first<JobRow>();
  if (!row) throw new JobHttpError("Accepted Job is not available", 500);
  try {
    await dispatchBuild(env, jobId);
  } catch (error) {
    await compensateDispatchFailure(env, row, error instanceof Error ? error.message : "Dispatch failed");
    throw new JobHttpError(error instanceof Error ? error.message : "Build dispatch failed", 400);
  }
  await recordDispatchAttempt(env, jobId);
  await queueBuildStartedAdminAlert(env, auth, jobId, recipe, now);
  return { job: publicJob(row, env), created: true };
}

export async function resumeJob(
  env: Env,
  auth: AuthenticatedRequest,
  previousJobId: string,
  rawIdempotencyKey: string
): Promise<{ job: JsonObject; created: boolean }> {
  const previous = await inspectJob(env, auth, previousJobId);
  if (!["failed", "cancelled"].includes(previous.status)) {
    throw new JobHttpError("Only failed or cancelled jobs can be resumed", 409);
  }
  const previousManifest = parseJson(previous.manifest_json);
  const checkpoint = typeof previousManifest.checkpoint === "string"
    ? previousManifest.checkpoint.trim()
    : "";
  if (!checkpoint) throw new JobHttpError("Job has no resumable checkpoint", 409);
  const checkpointAt = String(
    previousManifest.checkpoint_at ?? previousManifest.checkpointAt ?? ""
  ).trim();
  if (checkpointAt) {
    const checkpointTime = Date.parse(checkpointAt);
    if (
      !Number.isFinite(checkpointTime) ||
      Date.now() - checkpointTime > 7 * 24 * 60 * 60 * 1000
    ) {
      throw new JobHttpError("Job checkpoint has expired after 7 days", 409);
    }
  }
  const recipe = validateRecipe(parseJson(previous.recipe_json));
  const idempotencyKey = rawIdempotencyKey.trim()
    || `resume-${previousJobId}-${crypto.randomUUID().replaceAll("-", "")}`;
  if (!IDEMPOTENCY_KEY.test(idempotencyKey)) {
    throw new JobHttpError("Build idempotency key is invalid", 400);
  }
  const alreadyAccepted = await existingByIdempotency(env, auth.subject, idempotencyKey);
  if (alreadyAccepted) {
    await repairBuildStartedAdminAlert(env, auth, alreadyAccepted, previousJobId);
    return { job: publicJob(alreadyAccepted, env), created: false };
  }

  const jobId = crypto.randomUUID().replaceAll("-", "");
  const now = new Date().toISOString();
  const device = String(recipe.device);
  const manifest: JsonObject = {
    schema_version: 1,
    job_id: jobId,
    owner: { channel: "telegram", subject: auth.subject, role: auth.role },
    task: recipe.task,
    status: "queued",
    stage: "queued",
    progress: 0,
    runner: "github-actions",
    external_run_id: "",
    created_at: now,
    updated_at: now,
    finished_at: "",
    checkpoint,
    checkpoint_at: checkpointAt,
    resumed_from_job_id: previousJobId,
    artifacts: [],
    error: null
  };
  const requestKey = `${auth.subject}:${idempotencyKey}`;
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_jobs
         (job_id, manifest_json, recipe_json, created_at, updated_at,
          next_event_sequence, owner_channel, owner_subject, device, status, stage, progress)
         VALUES (?, ?, ?, ?, ?, 2, 'telegram', ?, ?, 'queued', 'queued', 0)`
      ).bind(jobId, JSON.stringify(manifest), JSON.stringify(recipe), now, now, auth.subject, device),
      env.DB.prepare(
        `INSERT INTO wukong_job_events
         (job_id, sequence, timestamp, event_type, payload_json)
         VALUES (?, 1, ?, 'resumed', ?)`
      ).bind(jobId, now, JSON.stringify({ previousJobId })),
      env.DB.prepare(
        `UPDATE wukong_telegram_users SET
           build_credits = CASE WHEN unlimited = 1 THEN build_credits ELSE build_credits - 1 END,
           lifetime_used = lifetime_used + CASE WHEN unlimited = 1 THEN 0 ELSE 1 END,
           job_count = job_count + 1,
           last_job_id = ?,
           last_job_status = 'queued'
         WHERE subject = ? AND access_status = 'approved'
           AND (unlimited = 1 OR build_credits > 0)`
      ).bind(jobId, auth.subject),
      env.DB.prepare(
        `INSERT INTO wukong_telegram_quota_ledger
         (ledger_id, subject, entry_type, delta, balance_after, job_id,
          idempotency_key, consumed, reason, created_at)
         SELECT ?, subject, 'consume',
                CASE WHEN unlimited = 1 THEN 0 ELSE -1 END,
                build_credits, ?, ?, CASE WHEN unlimited = 1 THEN 0 ELSE 1 END, ?, ?
         FROM wukong_telegram_users WHERE subject = ?`
      ).bind(
        crypto.randomUUID(),
        jobId,
        requestKey,
        `Resume checkpoint from ${previousJobId}`,
        now,
        auth.subject
      ),
      env.DB.prepare(
        `INSERT INTO wukong_telegram_user_events
         (event_id, subject, event_type, details_json, created_at)
         VALUES (?, ?, 'build_reserved', ?, ?)`
      ).bind(
        crypto.randomUUID(),
        auth.subject,
        JSON.stringify({
          jobId,
          resumedFromJobId: previousJobId,
          consumed: !auth.profile.unlimited
        }),
        now
      )
    ]);
  } catch (error) {
    const retry = await existingByIdempotency(env, auth.subject, idempotencyKey);
    if (retry) {
      await repairBuildStartedAdminAlert(env, auth, retry, previousJobId);
      return { job: publicJob(retry, env), created: false };
    }
    throw mapD1JobError(error);
  }
  const row = await env.DB.prepare("SELECT * FROM wukong_jobs WHERE job_id = ?")
    .bind(jobId)
    .first<JobRow>();
  if (!row) throw new JobHttpError("Accepted Job is not available", 500);
  try {
    await dispatchBuild(env, jobId);
  } catch (error) {
    await compensateDispatchFailure(
      env,
      row,
      error instanceof Error ? error.message : "Dispatch failed"
    );
    throw new JobHttpError(error instanceof Error ? error.message : "Build dispatch failed", 400);
  }
  await recordDispatchAttempt(env, jobId);
  await queueBuildStartedAdminAlert(env, auth, jobId, recipe, now, previousJobId);
  return { job: publicJob(row, env), created: true };
}

async function compensateDispatchFailure(
  env: Env,
  row: JobRow,
  reason: string
): Promise<void> {
  const now = new Date().toISOString();
  await env.DB.batch([
    ...acceptedJobCompensationStatements(env, row, reason, now, "dispatch_failed"),
    env.DB.prepare(
      `UPDATE wukong_jobs SET status = 'failed', stage = 'dispatch_failed',
       updated_at = ?, finished_at = ? WHERE job_id = ?`
    ).bind(now, now, row.job_id),
    env.DB.prepare("DELETE FROM wukong_build_locks WHERE job_id = ?").bind(row.job_id)
  ]);
}

export function acceptedJobCompensationStatements(
  env: Env,
  row: JobRow,
  reason: string,
  now: string,
  lastJobStatus: string,
  requiredJobState?: { status: string; stage: string }
): D1PreparedStatement[] {
  const compensationKey = `compensate:${row.job_id}`;
  const jobGuard = requiredJobState
    ? ` AND EXISTS (
          SELECT 1 FROM wukong_jobs
          WHERE job_id = ? AND status = ? AND stage = ?
        )`
    : "";
  const jobGuardBindings = requiredJobState
    ? [row.job_id, requiredJobState.status, requiredJobState.stage]
    : [];
  return [
    env.DB.prepare(
      `UPDATE wukong_telegram_users SET
         build_credits = build_credits + CASE WHEN unlimited = 1 THEN 0 ELSE 1 END,
         lifetime_used = MAX(
           0, lifetime_used - CASE WHEN unlimited = 1 THEN 0 ELSE 1 END
         ),
         last_job_status = ?
       WHERE subject = ?
         AND EXISTS (
           SELECT 1 FROM wukong_telegram_quota_ledger
           WHERE subject = ? AND job_id = ? AND entry_type = 'consume'
         )
          AND NOT EXISTS (
            SELECT 1 FROM wukong_telegram_quota_ledger WHERE idempotency_key = ?
          )
          ${jobGuard}`
    ).bind(
      lastJobStatus.slice(0, 64),
      row.owner_subject,
      row.owner_subject,
      row.job_id,
      compensationKey,
      ...jobGuardBindings
    ),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_telegram_quota_ledger
       (ledger_id, subject, entry_type, delta, balance_after, job_id,
        idempotency_key, consumed, reason, created_at)
       SELECT ?, subject, 'compensate',
              CASE WHEN unlimited = 1 THEN 0 ELSE 1 END,
              build_credits, ?, ?, CASE WHEN unlimited = 1 THEN 0 ELSE 1 END, ?, ?
       FROM wukong_telegram_users
       WHERE subject = ?
          AND EXISTS (
            SELECT 1 FROM wukong_telegram_quota_ledger
            WHERE subject = ? AND job_id = ? AND entry_type = 'consume'
          )
          ${jobGuard}`
    ).bind(
      crypto.randomUUID(),
      row.job_id,
      compensationKey,
      reason.slice(0, 1024),
      now,
      row.owner_subject,
      row.owner_subject,
      row.job_id,
      ...jobGuardBindings
    ),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_telegram_user_events
       (event_id, subject, event_type, details_json, created_at)
       SELECT ?, ?, 'build_compensated', ?, ?
        WHERE EXISTS (
          SELECT 1 FROM wukong_telegram_quota_ledger
          WHERE subject = ? AND job_id = ? AND entry_type = 'compensate'
        )
        ${jobGuard}`
    ).bind(
      `build-compensated:${row.job_id}`,
      row.owner_subject,
      JSON.stringify({ jobId: row.job_id, reason: reason.slice(0, 1024) }),
      now,
      row.owner_subject,
      row.job_id,
      ...jobGuardBindings
    )
  ];
}

const JOB_WITH_CREATOR = `SELECT j.*, u.display_name AS owner_display_name,
  u.username AS owner_username, u.photo_url AS owner_photo_url
  FROM wukong_jobs j LEFT JOIN wukong_telegram_users u
  ON j.owner_channel = 'telegram' AND u.subject = j.owner_subject`;

export async function listJobs(
  env: Env,
  auth: AuthenticatedRequest
): Promise<JsonObject[]> {
  const query = auth.role === "admin"
    ? env.DB.prepare(`${JOB_WITH_CREATOR} ORDER BY j.created_at DESC, j.job_id DESC LIMIT 100`)
    : env.DB.prepare(
      `SELECT * FROM wukong_jobs
       WHERE owner_channel = 'telegram' AND owner_subject = ?
       ORDER BY created_at DESC LIMIT 100`
    ).bind(auth.subject);
  const result = await query.all<JobRow>();
  return result.results.map((row) => publicJob(row, env, auth.role === "admin"));
}

export async function listJobsForSubject(env: Env, subject: string, cursor = "") {
  let anchor: { created_at: string; job_id: string } | null = null;
  if (cursor) {
    if (!JOB_ID.test(cursor)) throw new JobHttpError("Invalid job history cursor", 400);
    anchor = await env.DB.prepare("SELECT created_at, job_id FROM wukong_jobs WHERE job_id = ? AND owner_subject = ? AND owner_channel = 'telegram'")
      .bind(cursor, subject).first<{ created_at: string; job_id: string }>();
    if (!anchor) throw new JobHttpError("Invalid job history cursor", 400);
  }
  const result = await env.DB.prepare(
    `${JOB_WITH_CREATOR}
     WHERE j.owner_channel = 'telegram' AND j.owner_subject = ?
     ${anchor ? "AND (j.created_at < ? OR (j.created_at = ? AND j.job_id < ?))" : ""}
     ORDER BY j.created_at DESC, j.job_id DESC LIMIT 51`
  ).bind(subject, ...(anchor ? [anchor.created_at, anchor.created_at, anchor.job_id] : [])).all<JobRow>();
  const rows = result.results.slice(0, 50);
  const hasMore = result.results.length > 50;
  return { jobs: rows.map(row => publicJob(row, env, true)), hasMore, nextCursor: hasMore ? rows.at(-1)!.job_id : "" };
}

export async function inspectJob(
  env: Env,
  auth: AuthenticatedRequest,
  jobId: string
): Promise<JobRow> {
  if (!JOB_ID.test(jobId)) throw new JobHttpError("Job not found", 404);
  const row = await env.DB.prepare(`${JOB_WITH_CREATOR} WHERE j.job_id = ?`)
    .bind(jobId)
    .first<JobRow>();
  if (
    !row ||
    (auth.role !== "admin" &&
      (row.owner_channel !== "telegram" || row.owner_subject !== auth.subject))
  ) {
    throw new JobHttpError("Job not found", 404);
  }
  return row;
}

export async function jobEvents(
  env: Env,
  auth: AuthenticatedRequest,
  jobId: string,
  after: number
): Promise<JsonObject[]> {
  await inspectJob(env, auth, jobId);
  const result = await env.DB.prepare(
    `SELECT sequence, timestamp, event_type, payload_json
     FROM wukong_job_events WHERE job_id = ? AND sequence > ?
     ORDER BY sequence ASC LIMIT 500`
  ).bind(jobId, after).all<Record<string, unknown>>();
  return result.results.map((row) => publicJobEvent(row, env, jobId));
}

export function publicJobEvent(row: Record<string, unknown>, env: Env, jobId: string): JsonObject {
  return sanitizePublicValue({
    sequence: Number(row.sequence), jobId, timestamp: row.timestamp,
    type: row.event_type, ...parseJson(row.payload_json)
  }, env) as JsonObject;
}

export async function latestJobEvents(
  env: Env,
  auth: AuthenticatedRequest,
  jobId: string,
  limit = 50
): Promise<JsonObject[]> {
  await inspectJob(env, auth, jobId);
  const bounded = Math.max(1, Math.min(100, Math.trunc(limit)));
  const result = await env.DB.prepare(
    `SELECT sequence, timestamp, event_type, payload_json
     FROM wukong_job_events WHERE job_id = ?
     ORDER BY sequence DESC LIMIT ?`
  ).bind(jobId, bounded).all<Record<string, unknown>>();
  return result.results.reverse().map((row) => publicJobEvent(row, env, jobId));
}

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

export async function cancelJob(
  env: Env,
  auth: AuthenticatedRequest,
  jobId: string
): Promise<JsonObject> {
  const row = await inspectJob(env, auth, jobId);
  if (isTerminalStatus(row.status)) return publicJob(row, env);
  await cancelWorkflowRunForJob(
    env,
    jobId,
    row.github_run_id == null ? null : Number(row.github_run_id)
  );
  const now = new Date().toISOString();
  const sequence = Number(row.next_event_sequence ?? 2);
  let manifest: JsonObject;
  try { manifest = JSON.parse(row.manifest_json) as JsonObject; } catch { manifest = {}; }
  manifest = {
    ...manifest,
    status: "cancelled",
    stage: "cancelled",
    updated_at: now,
    finished_at: now
  };
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE wukong_jobs SET manifest_json = ?, status = 'cancelled',
       stage = 'cancelled', updated_at = ?, finished_at = ?,
       next_event_sequence = ? WHERE job_id = ?
       AND status NOT IN ('succeeded', 'failed', 'cancelled')`
    ).bind(JSON.stringify(manifest), now, now, sequence + 1, jobId),
    env.DB.prepare("DELETE FROM wukong_build_locks WHERE job_id = ?").bind(jobId),
    env.DB.prepare(
      `UPDATE wukong_telegram_users SET last_job_id = ?, last_job_status = 'cancelled'
       WHERE subject = ?`
    ).bind(jobId, row.owner_subject),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_job_events
       (job_id, sequence, timestamp, event_type, payload_json)
       VALUES (?, ?, ?, 'cancelled', '{}')`
    ).bind(jobId, sequence, now),
    env.DB.prepare(
      `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
       (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      crypto.randomUUID(),
      `job-terminal:${jobId}`,
      row.owner_subject,
      JSON.stringify(terminalTelegramNotification(env, row, "cancelled", manifest)),
      now,
      now
    )
  ]);
  const refreshed = await env.DB.prepare("SELECT * FROM wukong_jobs WHERE job_id = ?")
    .bind(jobId)
    .first<JobRow>();
  if (!refreshed) throw new JobHttpError("Job not found", 404);
  return publicJob(refreshed, env);
}

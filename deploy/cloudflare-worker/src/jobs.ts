import type { AuthenticatedRequest } from "./auth";
import { artifactEdition } from "./artifact-metadata";
import { cancelWorkflowRunForJob, dispatchBuild, dispatchMirrorRepair } from "./github";
import { directArtifactUrl } from "./public-links";
import { terminalTelegramNotification } from "./telegram-notifications";
import { buildStartedAdminStatements } from "./activity";
import { PRESET_LABEL } from "./catalog";
import { markMirrorsRepairing } from "./mirror-repair-outbox";

type JsonObject = Record<string, unknown>;

const JOB_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const JOB_HISTORY_PAGE_SIZE = 20;
const JOB_HISTORY_STATUSES = new Set(["active", "succeeded", "failed"]);
const JOB_PRESETS = new Set(["lite", "plus", "both", "custom"]);

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
  if (build.modReleaseVersion !== undefined || build.mod_release_version !== undefined) {
    const release = requiredText(build.modReleaseVersion ?? build.mod_release_version, "MOD release version", 64).trim();
    if (!PRESET_LABEL.test(release)) {
      throw new JobHttpError("MOD release version is not filename-safe", 400);
    }
    build.modReleaseVersion = release;
    delete build.mod_release_version;
  }
  if (build.editionLabels !== undefined || build.edition_labels !== undefined) {
    const rawLabels = build.editionLabels ?? build.edition_labels;
    const labels = object(rawLabels, "Edition labels");
    const normalizedLabels: JsonObject = {};
    for (const [rawKey, rawValue] of Object.entries(labels)) {
      const key = rawKey.trim().toLowerCase();
      if (!["lite", "plus", "both", "custom"].includes(key)) {
        throw new JobHttpError("Edition label key is invalid", 400);
      }
      const label = typeof rawValue === "string" ? rawValue.trim() : "";
      if (!PRESET_LABEL.test(label)) {
        throw new JobHttpError("Edition label is not filename-safe", 400);
      }
      normalizedLabels[key] = label;
    }
    build.editionLabels = normalizedLabels;
    delete build.edition_labels;
  }
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
      edition: artifactEdition(artifact.name, index + 1, build.preset, build.editionLabels ?? build.edition_labels),
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

function cloudreveShareUri(env: Env, mirrorUri: string): { endpoint: string; uri: string } {
  let share: URL;
  try {
    share = new URL(env.WUKONG_DCCLOUD_SHARE_URL.trim());
  } catch {
    throw new JobHttpError("DC Cloud download is not configured", 503, "dccloud_unconfigured");
  }
  if (share.protocol !== "https:") {
    throw new JobHttpError("DC Cloud download is not configured", 503, "dccloud_unconfigured");
  }
  const parts = share.pathname.split("/").filter(Boolean);
  if (parts.length !== 2 || parts[0] !== "s" || !/^[A-Za-z0-9_-]{1,128}$/.test(parts[1] ?? "")) {
    throw new JobHttpError("DC Cloud share link is invalid", 503, "dccloud_unconfigured");
  }
  const prefix = "cloudreve://my/";
  const normalized = mirrorUri.replaceAll("\\", "/");
  if (!normalized.toLowerCase().startsWith(prefix)) {
    throw new JobHttpError("DC Cloud artifact URI is invalid", 409, "dccloud_uri_invalid");
  }
  const path = normalized.slice(prefix.length);
  const root = env.WUKONG_DCCLOUD_ROOT.trim().replace(/^\/+|\/+$/g, "");
  const rootPrefix = root ? `${root}/` : "";
  const nestedMarker = root ? `/${root}/` : "";
  const markerIndex = rootPrefix && path.startsWith(rootPrefix)
    ? 0
    : nestedMarker
      ? path.indexOf(nestedMarker)
      : -1;
  if (markerIndex < 0) {
    throw new JobHttpError("DC Cloud artifact path is invalid", 409, "dccloud_uri_invalid");
  }
  const relative = markerIndex === 0
    ? path.slice(rootPrefix.length)
    : path.slice(markerIndex + nestedMarker.length);
  const encoded = relative.split("/").filter(Boolean).map((segment) => {
    try {
      return encodeURIComponent(decodeURIComponent(segment));
    } catch {
      throw new JobHttpError("DC Cloud artifact path is invalid", 409, "dccloud_uri_invalid");
    }
  }).join("/");
  if (!encoded || encoded.split("/").some((segment) => segment === "." || segment === "..")) {
    throw new JobHttpError("DC Cloud artifact path is invalid", 409, "dccloud_uri_invalid");
  }
  return {
    endpoint: `${share.origin}/api/v4/file/url`,
    uri: `cloudreve://${parts[1]}@share/${encoded}`
  };
}

export async function dcCloudArtifactDownload(
  env: Env,
  row: JobRow,
  artifactIndex: number
): Promise<JsonObject> {
  if (!Number.isSafeInteger(artifactIndex) || artifactIndex < 0) {
    throw new JobHttpError("Artifact not found", 404);
  }
  const manifest = parseJson(row.manifest_json);
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  const rawArtifact = artifacts[artifactIndex];
  if (!rawArtifact || typeof rawArtifact !== "object" || Array.isArray(rawArtifact)) {
    throw new JobHttpError("Artifact not found", 404);
  }
  const artifact = rawArtifact as JsonObject;
  const mirrors = Array.isArray(artifact.mirrors) ? artifact.mirrors : [];
  const mirror = mirrors.find((item) => item && typeof item === "object" && !Array.isArray(item)
    && String((item as JsonObject).provider ?? "").trim().toLowerCase() === "dccloud") as JsonObject | undefined;
  if (!mirror || String(mirror.status ?? "").trim().toLowerCase() !== "available") {
    throw new JobHttpError("DC Cloud mirror is not available yet", 409, "dccloud_unavailable");
  }
  const mirrorUri = typeof mirror.uri === "string" ? mirror.uri.trim() : "";
  const target = cloudreveShareUri(env, mirrorUri);
  let response: Response;
  try {
    response = await fetch(target.endpoint, {
      method: "POST",
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ uris: [target.uri] })
    });
  } catch {
    throw new JobHttpError("DC Cloud download URL could not be created", 502, "dccloud_download_failed");
  }
  if (!response.ok) {
    throw new JobHttpError("DC Cloud download URL could not be created", 502, "dccloud_download_failed");
  }
  const payload = await response.json().catch(() => null) as JsonObject | null;
  const data = payload?.data && typeof payload.data === "object" && !Array.isArray(payload.data)
    ? payload.data as JsonObject
    : null;
  const urls = data?.urls;
  const url = Array.isArray(urls) && urls[0] && typeof urls[0] === "object" && !Array.isArray(urls[0])
    ? (urls[0] as JsonObject).url
    : "";
  const downloadUrl = directArtifactUrl(url, env);
  if (Number(payload?.code ?? -1) !== 0 || !downloadUrl) {
    throw new JobHttpError("DC Cloud download URL could not be created", 502, "dccloud_download_failed");
  }
  const expires = typeof data?.expires === "string" ? data.expires : "";
  return {
    downloadUrl,
    provider: "dccloud",
    ...(expires ? { expires } : {})
  };
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

interface JobHistoryFilters {
  page: number;
  q: string;
  status: string;
  preset: string;
  modVersion: string;
  createdFrom: string;
  createdTo: string;
}

export interface JobHistoryPage {
  jobs: JsonObject[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  statusCounts: {
    active: number;
    succeeded: number;
    failed: number;
  };
}

function escapedLike(value: string): string {
  return value.replace(/[\\%_]/g, (character) => `\\${character}`);
}

function historyFilters(params: URLSearchParams): JobHistoryFilters {
  const rawPage = params.get("page") ?? "1";
  if (!/^\d+$/.test(rawPage) || Number(rawPage) < 1 || !Number.isSafeInteger(Number(rawPage))) {
    throw new JobHttpError("Job history page is invalid", 400);
  }
  const q = (params.get("q") ?? "").trim();
  const modVersion = (params.get("modVersion") ?? "").trim();
  if (q.length > 128) throw new JobHttpError("Job history search is too long", 400);
  if (modVersion.length > 128) throw new JobHttpError("MOD version filter is too long", 400);
  const status = (params.get("status") ?? "").trim().toLowerCase();
  if (status && !JOB_HISTORY_STATUSES.has(status)) throw new JobHttpError("Job history status is invalid", 400);
  const preset = (params.get("preset") ?? "").trim().toLowerCase();
  if (preset && !JOB_PRESETS.has(preset)) throw new JobHttpError("Job history preset is invalid", 400);
  const createdFrom = (params.get("createdFrom") ?? "").trim();
  const createdTo = (params.get("createdTo") ?? "").trim();
  for (const value of [createdFrom, createdTo]) {
    if (value && (value.length > 64 || !Number.isFinite(Date.parse(value)))) {
      throw new JobHttpError("Job history date filter is invalid", 400);
    }
  }
  if (createdFrom && createdTo && Date.parse(createdFrom) >= Date.parse(createdTo)) {
    throw new JobHttpError("Job history date range is invalid", 400);
  }
  return {
    page: Number(rawPage),
    q,
    status,
    preset,
    modVersion,
    createdFrom,
    createdTo
  };
}

function historyClauses(
  auth: AuthenticatedRequest,
  filters: JobHistoryFilters,
  subject = "",
  includeStatus = true
): { sql: string; bindings: string[] } {
  const clauses = ["j.owner_channel = 'telegram'"];
  const bindings: string[] = [];
  if (subject || auth.role !== "admin") {
    clauses.push("j.owner_subject = ?");
    bindings.push(subject || auth.subject);
  }
  if (filters.q) {
    const needle = `%${escapedLike(filters.q.toLowerCase())}%`;
    clauses.push(`(
      LOWER(j.job_id) LIKE ? ESCAPE '\\' OR
      LOWER(j.device) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(json_extract(j.recipe_json, '$.device'), '')) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(json_extract(j.recipe_json, '$.build.modVersion'), '')) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(json_extract(j.recipe_json, '$.build.modReleaseVersion'), '')) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(json_extract(j.recipe_json, '$.source.metadata.version'), '')) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(json_extract(j.manifest_json, '$.rom_metadata.version'), '')) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(u.display_name, '')) LIKE ? ESCAPE '\\' OR
      LOWER(COALESCE(u.username, '')) LIKE ? ESCAPE '\\' OR
      LOWER(j.owner_subject) LIKE ? ESCAPE '\\'
    )`);
    bindings.push(...Array.from({ length: 10 }, () => needle));
  }
  if (filters.preset) {
    clauses.push("LOWER(COALESCE(json_extract(j.recipe_json, '$.build.preset'), '')) = ?");
    bindings.push(filters.preset);
  }
  if (filters.modVersion) {
    clauses.push("LOWER(COALESCE(json_extract(j.recipe_json, '$.build.modVersion'), '')) = ?");
    bindings.push(filters.modVersion.toLowerCase());
  }
  if (filters.createdFrom) {
    clauses.push("j.created_at >= ?");
    bindings.push(new Date(filters.createdFrom).toISOString());
  }
  if (filters.createdTo) {
    clauses.push("j.created_at < ?");
    bindings.push(new Date(filters.createdTo).toISOString());
  }
  if (includeStatus && filters.status) {
    if (filters.status === "active") clauses.push("j.status NOT IN ('succeeded', 'failed', 'cancelled')");
    if (filters.status === "succeeded") clauses.push("j.status = 'succeeded'");
    if (filters.status === "failed") clauses.push("j.status IN ('failed', 'cancelled')");
  }
  return { sql: `WHERE ${clauses.join(" AND ")}`, bindings };
}

export async function listJobHistory(
  env: Env,
  auth: AuthenticatedRequest,
  params: URLSearchParams,
  subject = ""
): Promise<JobHistoryPage> {
  const filters = historyFilters(params);
  const common = historyClauses(auth, filters, subject, false);
  const filtered = historyClauses(auth, filters, subject, true);
  const statusCounts = await env.DB.prepare(
    `SELECT
       COALESCE(SUM(CASE WHEN j.status NOT IN ('succeeded', 'failed', 'cancelled') THEN 1 ELSE 0 END), 0) AS active,
       COALESCE(SUM(CASE WHEN j.status = 'succeeded' THEN 1 ELSE 0 END), 0) AS succeeded,
       COALESCE(SUM(CASE WHEN j.status IN ('failed', 'cancelled') THEN 1 ELSE 0 END), 0) AS failed
     FROM wukong_jobs j LEFT JOIN wukong_telegram_users u
       ON j.owner_channel = 'telegram' AND u.subject = j.owner_subject
     ${common.sql}`
  ).bind(...common.bindings).first<{ active: number; succeeded: number; failed: number }>();
  const totalResult = await env.DB.prepare(
    `SELECT COUNT(*) AS total
     FROM wukong_jobs j LEFT JOIN wukong_telegram_users u
       ON j.owner_channel = 'telegram' AND u.subject = j.owner_subject
     ${filtered.sql}`
  ).bind(...filtered.bindings).first<{ total: number }>();
  const total = Number(totalResult?.total ?? 0);
  const totalPages = Math.max(1, Math.ceil(total / JOB_HISTORY_PAGE_SIZE));
  const page = Math.min(filters.page, totalPages);
  const result = await env.DB.prepare(
    `${JOB_WITH_CREATOR} ${filtered.sql}
     ORDER BY j.created_at DESC, j.job_id DESC LIMIT ? OFFSET ?`
  ).bind(...filtered.bindings, JOB_HISTORY_PAGE_SIZE, (page - 1) * JOB_HISTORY_PAGE_SIZE).all<JobRow>();
  return {
    jobs: result.results.map((row) => publicJob(row, env, auth.role === "admin" || Boolean(subject))),
    page,
    pageSize: JOB_HISTORY_PAGE_SIZE,
    total,
    totalPages,
    statusCounts: {
      active: Number(statusCounts?.active ?? 0),
      succeeded: Number(statusCounts?.succeeded ?? 0),
      failed: Number(statusCounts?.failed ?? 0)
    }
  };
}

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

export async function repairMirror(
  env: Env,
  auth: AuthenticatedRequest,
  jobId: string
): Promise<JsonObject> {
  const row = await inspectJob(env, auth, jobId);
  if (!isTerminalStatus(row.status)) {
    throw new JobHttpError("Mirror repair is available after the job finishes", 409);
  }
  let manifest: JsonObject;
  try {
    manifest = JSON.parse(row.manifest_json) as JsonObject;
  } catch {
    throw new JobHttpError("Job manifest is unavailable", 409);
  }
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  const repairable = artifacts.some((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const artifact = value as JsonObject;
    if (!String(artifact.name ?? "").toLowerCase().endsWith(".zip")) return false;
    const mirrors = Array.isArray(artifact.mirrors) ? artifact.mirrors : [];
    return mirrors.some((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return false;
      const mirror = item as JsonObject;
      return String(mirror.provider ?? "").toLowerCase() === "dccloud"
        && String(mirror.status ?? "").toLowerCase() !== "available";
    });
  });
  if (!repairable) {
    throw new JobHttpError("This job has no failed DC Cloud mirror to repair", 409);
  }
  await dispatchMirrorRepair(env, jobId);
  const now = new Date().toISOString();
  const repairingManifest = {
    ...markMirrorsRepairing(manifest),
    updated_at: now
  };
  await env.DB.prepare(
    `UPDATE wukong_jobs SET manifest_json = ?, updated_at = ?
     WHERE job_id = ? AND status IN ('succeeded', 'failed', 'cancelled')`
  ).bind(JSON.stringify(repairingManifest), now, jobId).run();
  return { status: "queued", workflow: "mirror-repair.yml", jobId };
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

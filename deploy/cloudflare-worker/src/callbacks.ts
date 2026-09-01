import { bytes, constantTimeHexEqual, hmacHex, hmacSha256, sha256Hex } from "./crypto";
import {
  acceptedJobCompensationStatements,
  type JobRow
} from "./jobs";
import { automaticMirrorRepairStatement } from "./mirror-repair-outbox";
import { terminalTelegramNotification } from "./telegram-notifications";

type JsonObject = Record<string, unknown>;

export class CallbackHttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function bodyObject(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CallbackHttpError("Actions callback payload must be an object", 400);
  }
  return value as JsonObject;
}

function jobIdFrom(payload: JsonObject): string {
  const jobId = typeof payload.jobId === "string" ? payload.jobId.trim() : "";
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(jobId)) {
    throw new CallbackHttpError("Actions callback job is invalid", 400);
  }
  return jobId;
}

function runIdFrom(payload: JsonObject): number {
  const runId = Number(payload.runId);
  if (!Number.isSafeInteger(runId) || runId <= 0) {
    throw new CallbackHttpError("Actions callback run is invalid", 400);
  }
  return runId;
}

async function callbackJob(env: Env, jobId: string): Promise<JobRow> {
  const row = await env.DB.prepare("SELECT * FROM wukong_jobs WHERE job_id = ?")
    .bind(jobId)
    .first<JobRow>();
  if (!row) throw new CallbackHttpError("Job not found", 404);
  return row;
}

export async function verifyActionsHmac(
  request: Request,
  env: Env,
  body: string
): Promise<void> {
  if (env.WUKONG_ACTIONS_CALLBACK_SECRET.length < 20) {
    throw new CallbackHttpError("Actions callback is not configured", 503);
  }
  const timestamp = request.headers.get("X-Wukong-Timestamp") ?? "";
  const signature = (request.headers.get("X-Wukong-Signature") ?? "").toLowerCase();
  const issuedAt = Number(timestamp);
  if (!/^[0-9]+$/.test(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - issuedAt) > 300) {
    throw new CallbackHttpError("Actions callback authentication failed", 403);
  }
  const key = await hmacSha256(
    bytes("WukongActionsCallback\0"),
    env.WUKONG_ACTIONS_CALLBACK_SECRET
  );
  const expected = await hmacHex(key, `${timestamp}.${body}`);
  if (!constantTimeHexEqual(signature, expected)) {
    throw new CallbackHttpError("Actions callback authentication failed", 403);
  }
}

async function existingReceipt(
  env: Env,
  receiptKey: string,
  payloadHash: string
): Promise<boolean> {
  const row = await env.DB.prepare(
    "SELECT payload_hash FROM wukong_actions_callback_receipts WHERE receipt_key = ?"
  ).bind(receiptKey).first<{ payload_hash: string }>();
  if (!row) return false;
  if (row.payload_hash !== payloadHash) {
    throw new CallbackHttpError("Actions callback sequence was reused with different content", 409);
  }
  return true;
}

function progressValue(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new CallbackHttpError("Actions progress is invalid", 400);
  return Math.max(0, Math.min(1, parsed));
}

function sequenceValue(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 2) {
    throw new CallbackHttpError("Actions callback sequence is invalid", 400);
  }
  return parsed;
}

function eventStatements(
  env: Env,
  jobId: string,
  events: unknown
): D1PreparedStatement[] {
  if (!Array.isArray(events)) return [];
  return events.slice(0, 100).flatMap((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const event = value as JsonObject;
    const sequence = Number(event.sequence);
    const type = typeof event.type === "string" ? event.type.trim().slice(0, 64) : "";
    if (!Number.isSafeInteger(sequence) || sequence < 2 || !type) return [];
    const payload = { ...event };
    delete payload.sequence;
    delete payload.type;
    return [
      env.DB.prepare(
        `INSERT OR IGNORE INTO wukong_job_events
         (job_id, sequence, timestamp, event_type, payload_json)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(
        jobId,
        sequence,
        typeof event.timestamp === "string" ? event.timestamp : new Date().toISOString(),
        type,
        JSON.stringify(payload)
      )
    ];
  });
}

function maximumEventSequence(events: unknown): number {
  if (!Array.isArray(events)) return 0;
  return events.reduce((maximum, value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return maximum;
    const sequence = Number((value as JsonObject).sequence);
    return Number.isSafeInteger(sequence) && sequence >= 2
      ? Math.max(maximum, sequence)
      : maximum;
  }, 0);
}

export async function handleProgress(
  env: Env,
  body: string
): Promise<JsonObject> {
  const payload = bodyObject(JSON.parse(body));
  const jobId = jobIdFrom(payload);
  const runId = runIdFrom(payload);
  const sequence = sequenceValue(payload.sequence);
  const incomingProgress = progressValue(payload.progress);
  const incomingStatus = typeof payload.status === "string"
    ? payload.status.trim().toLowerCase().slice(0, 64)
    : "running";
  if (["succeeded", "failed", "cancelled"].includes(incomingStatus)) {
    throw new CallbackHttpError("Terminal status must use the terminal callback", 400);
  }
  const incomingStage = typeof payload.stage === "string"
    ? payload.stage.trim().slice(0, 128)
    : incomingStatus;
  const row = await callbackJob(env, jobId);
  if (row.github_run_id != null && Number(row.github_run_id) !== runId) {
    throw new CallbackHttpError("Actions callback run does not match the job", 409);
  }
  const payloadHash = await sha256Hex(body);
  const receiptKey = `${jobId}:progress:${sequence}`;
  if (await existingReceipt(env, receiptKey, payloadHash)) {
    return { jobId, status: row.status, terminal: false, duplicate: true };
  }
  if (["succeeded", "failed", "cancelled"].includes(row.status)) {
    return { jobId, status: row.status, terminal: true, outOfOrder: true };
  }
  const now = new Date().toISOString();
  const nextEventSequence = Math.max(sequence, maximumEventSequence(payload.events)) + 1;
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_actions_callback_receipts
         (receipt_key, job_id, run_id, callback_kind, sequence, payload_hash, received_at)
         VALUES (?, ?, ?, 'progress', ?, ?, ?)`
      ).bind(receiptKey, jobId, runId, sequence, payloadHash, now),
      env.DB.prepare(
        `UPDATE wukong_jobs SET
           github_run_id = COALESCE(github_run_id, ?),
           status = CASE WHEN next_event_sequence <= ? THEN ? ELSE status END,
           stage = CASE WHEN next_event_sequence <= ? THEN ? ELSE stage END,
           progress = MAX(progress, ?),
           updated_at = ?,
           next_event_sequence = MAX(next_event_sequence, ?)
         WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')`
      ).bind(
        runId,
        sequence, incomingStatus,
        sequence, incomingStage,
        incomingProgress,
        now,
        nextEventSequence,
        jobId
      ),
      ...eventStatements(env, jobId, payload.events)
    ]);
  } catch (error) {
    if (await existingReceipt(env, receiptKey, payloadHash)) {
      return { jobId, status: row.status, terminal: false, duplicate: true };
    }
    throw error;
  }
  const refreshed = await callbackJob(env, jobId);
  return { jobId, status: refreshed.status, terminal: false };
}

function terminalStatus(result: string): "succeeded" | "failed" | "cancelled" {
  if (result === "success") return "succeeded";
  if (result === "failure") return "failed";
  if (result === "cancelled") return "cancelled";
  throw new CallbackHttpError("Actions callback result is invalid", 400);
}

function mergedManifest(row: JobRow, payload: JsonObject, status: string, now: string): JsonObject {
  let current: JsonObject = {};
  try {
    current = JSON.parse(row.manifest_json) as JsonObject;
  } catch {
    current = {};
  }
  const incoming = payload.manifest && typeof payload.manifest === "object" && !Array.isArray(payload.manifest)
    ? payload.manifest as JsonObject
    : {};
  return {
    ...current,
    ...incoming,
    status,
    stage: typeof incoming.stage === "string" ? incoming.stage : status === "succeeded" ? "complete" : status,
    progress: status === "succeeded" ? 1 : Math.max(Number(row.progress ?? 0), Number(incoming.progress ?? 0)),
    updated_at: now,
    finished_at: typeof incoming.finished_at === "string"
      ? incoming.finished_at
      : typeof incoming.finishedAt === "string"
        ? incoming.finishedAt
        : now
  };
}

export async function handleTerminal(
  env: Env,
  body: string
): Promise<JsonObject> {
  const payload = bodyObject(JSON.parse(body));
  const jobId = jobIdFrom(payload);
  const runId = runIdFrom(payload);
  const result = typeof payload.workflowResult === "string"
    ? payload.workflowResult.trim().toLowerCase()
    : "";
  const status = terminalStatus(result);
  const sequence = Number.isSafeInteger(Number(payload.sequence))
    ? Math.max(2, Number(payload.sequence))
    : 2;
  const row = await callbackJob(env, jobId);
  if (row.github_run_id != null && Number(row.github_run_id) !== runId) {
    throw new CallbackHttpError("Actions callback run does not match the job", 409);
  }
  const payloadHash = await sha256Hex(body);
  const receiptKey = `${jobId}:terminal:${runId}:${result}`;
  if (await existingReceipt(env, receiptKey, payloadHash)) {
    return { jobId, status: row.status, terminal: true, duplicate: true };
  }
  if (["succeeded", "failed", "cancelled"].includes(row.status)) {
    return { jobId, status: row.status, terminal: true, outOfOrder: true };
  }
  const now = new Date().toISOString();
  const manifest = mergedManifest(row, payload, status, now);
  const nextEventSequence = sequence + 1;
  const compensationStatements = payload.preExecutorFailure === true
    ? acceptedJobCompensationStatements(
      env,
      row,
      "GitHub Actions failed before the executor started",
      now,
      status
    )
    : [];
  const automaticRepair = automaticMirrorRepairStatement(env, jobId, status, manifest, now);
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_actions_callback_receipts
         (receipt_key, job_id, run_id, callback_kind, sequence, payload_hash, received_at)
         VALUES (?, ?, ?, 'terminal', ?, ?, ?)`
      ).bind(receiptKey, jobId, runId, sequence, payloadHash, now),
      env.DB.prepare(
        `UPDATE wukong_jobs SET
           manifest_json = ?, github_run_id = COALESCE(github_run_id, ?),
           status = ?, stage = ?, progress = ?, updated_at = ?, finished_at = ?
           , next_event_sequence = MAX(next_event_sequence, ?)
         WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')`
      ).bind(
        JSON.stringify(manifest),
        runId,
        status,
        String(manifest.stage),
        Number(manifest.progress),
        now,
        now,
        nextEventSequence,
        jobId
      ),
      env.DB.prepare("DELETE FROM wukong_build_locks WHERE job_id = ?").bind(jobId),
      env.DB.prepare(
        `UPDATE wukong_telegram_users
         SET last_job_id = ?, last_job_status = ?
         WHERE subject = ?`
      ).bind(jobId, status, row.owner_subject),
      env.DB.prepare(
        `INSERT OR IGNORE INTO wukong_job_events
         (job_id, sequence, timestamp, event_type, payload_json)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(jobId, sequence, now, status, JSON.stringify({ status })),
      env.DB.prepare(
        `INSERT OR IGNORE INTO wukong_telegram_notification_outbox
         (notification_id, dedupe_key, chat_id, payload_json, available_at, created_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      ).bind(
        crypto.randomUUID(),
        `job-terminal:${jobId}`,
        row.owner_subject,
        JSON.stringify(terminalTelegramNotification(env, row, status, manifest)),
        now,
        now
      ),
      ...(automaticRepair ? [automaticRepair] : []),
      ...compensationStatements
    ]);
  } catch (error) {
    if (await existingReceipt(env, receiptKey, payloadHash)) {
      const refreshed = await callbackJob(env, jobId);
      return { jobId, status: refreshed.status, terminal: true, duplicate: true };
    }
    throw error;
  }
  const refreshed = await callbackJob(env, jobId);
  return { jobId, status: refreshed.status, terminal: true };
}

function callbackManifest(payload: JsonObject): JsonObject {
  const value = payload.manifest;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CallbackHttpError("Mirror repair manifest is required", 400);
  }
  return value as JsonObject;
}

function callbackArtifactMap(manifest: JsonObject): Map<string, JsonObject> {
  const artifacts = manifest.artifacts;
  if (!Array.isArray(artifacts)) {
    throw new CallbackHttpError("Mirror repair manifest artifacts are invalid", 400);
  }
  const result = new Map<string, JsonObject>();
  for (const value of artifacts) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    const artifact = value as JsonObject;
    const name = typeof artifact.name === "string" ? artifact.name.trim() : "";
    if (name) result.set(name, artifact);
  }
  return result;
}

function repairMirrorValue(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CallbackHttpError("Mirror repair result is invalid", 400);
  }
  const source = value as JsonObject;
  const status = typeof source.status === "string" ? source.status.trim().toLowerCase() : "";
  if (!["pending", "available", "failed"].includes(status)) {
    throw new CallbackHttpError("Mirror repair status is invalid", 400);
  }
  const uri = typeof source.uri === "string" ? source.uri.trim().slice(0, 4096) : "";
  const browseUrl = typeof source.browse_url === "string"
    ? source.browse_url.trim().slice(0, 2048)
    : typeof source.browseUrl === "string"
      ? source.browseUrl.trim().slice(0, 2048)
      : "";
  const errorCode = typeof source.error_code === "string"
    ? source.error_code.trim().slice(0, 128)
    : typeof source.errorCode === "string"
      ? source.errorCode.trim().slice(0, 128)
      : "";
  if (status === "available" && !uri) {
    throw new CallbackHttpError("Available mirror is missing its URI", 400);
  }
  return {
    provider: "dccloud",
    status,
    ...(uri ? { uri } : {}),
    ...(browseUrl ? { browse_url: browseUrl } : {}),
    ...(errorCode ? { error_code: errorCode } : {})
  };
}

function repairedManifest(row: JobRow, payload: JsonObject, now: string): JsonObject {
  const current = (() => {
    try {
      return JSON.parse(row.manifest_json) as JsonObject;
    } catch {
      throw new CallbackHttpError("Stored job manifest is unavailable", 409);
    }
  })();
  const incoming = callbackManifest(payload);
  const currentArtifacts = callbackArtifactMap(current);
  const incomingArtifacts = callbackArtifactMap(incoming);
  const expectedNames = [...currentArtifacts.values()]
    .filter((artifact) => String(artifact.name ?? "").toLowerCase().endsWith(".zip"))
    .map((artifact) => String(artifact.name));
  for (const name of expectedNames) {
    const replacement = incomingArtifacts.get(name);
    const mirrors = replacement && Array.isArray(replacement.mirrors) ? replacement.mirrors : [];
    if (!replacement || !mirrors.some((item) => item && typeof item === "object" && !Array.isArray(item)
      && String((item as JsonObject).provider ?? "").trim().toLowerCase() === "dccloud")) {
      throw new CallbackHttpError("Mirror repair manifest does not contain every ZIP artifact", 409);
    }
  }
  const mergedArtifacts = (Array.isArray(current.artifacts) ? current.artifacts : []).map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return value;
    const artifact = { ...(value as JsonObject) };
    const name = typeof artifact.name === "string" ? artifact.name.trim() : "";
    const replacement = name ? incomingArtifacts.get(name) : undefined;
    if (!replacement) return artifact;

    const currentSha = typeof artifact.sha256 === "string" ? artifact.sha256.trim().toLowerCase() : "";
    const incomingSha = typeof replacement.sha256 === "string" ? replacement.sha256.trim().toLowerCase() : "";
    if (currentSha && incomingSha && currentSha !== incomingSha) {
      throw new CallbackHttpError("Mirror repair checksum does not match the job artifact", 409);
    }
    const currentSize = Number(artifact.size_bytes ?? artifact.sizeBytes);
    const incomingSize = Number(replacement.size_bytes ?? replacement.sizeBytes);
    if (Number.isSafeInteger(currentSize) && Number.isSafeInteger(incomingSize) && currentSize > 0 && incomingSize > 0 && currentSize !== incomingSize) {
      throw new CallbackHttpError("Mirror repair size does not match the job artifact", 409);
    }
    const mirrors = Array.isArray(replacement.mirrors) ? replacement.mirrors : [];
    const mirror = mirrors.find((item) => item && typeof item === "object" && !Array.isArray(item)
      && String((item as JsonObject).provider ?? "").trim().toLowerCase() === "dccloud");
    if (!mirror) return artifact;
    const existingMirrors = Array.isArray(artifact.mirrors) ? artifact.mirrors : [];
    return {
      ...artifact,
      mirrors: [
        ...existingMirrors.filter((item) => !item || typeof item !== "object" || Array.isArray(item)
          || String((item as JsonObject).provider ?? "").trim().toLowerCase() !== "dccloud"),
        repairMirrorValue(mirror)
      ]
    };
  });
  return { ...current, artifacts: mergedArtifacts, updated_at: now };
}

export async function handleMirrorRepair(
  env: Env,
  body: string
): Promise<JsonObject> {
  const payload = bodyObject(JSON.parse(body));
  const jobId = jobIdFrom(payload);
  const runId = runIdFrom(payload);
  const row = await callbackJob(env, jobId);
  if (!["succeeded", "failed", "cancelled"].includes(row.status)) {
    throw new CallbackHttpError("Mirror repair is only accepted for terminal jobs", 409);
  }
  const payloadHash = await sha256Hex(body);
  const receiptKey = `${jobId}:mirror-repair:${runId}`;
  if (await existingReceipt(env, receiptKey, payloadHash)) {
    return { jobId, status: row.status, mirrorRepair: true, duplicate: true };
  }
  const now = new Date().toISOString();
  const manifest = repairedManifest(row, payload, now);
  try {
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO wukong_actions_callback_receipts
         (receipt_key, job_id, run_id, callback_kind, sequence, payload_hash, received_at)
         VALUES (?, ?, ?, 'mirror_repair', 0, ?, ?)`
      ).bind(receiptKey, jobId, runId, payloadHash, now),
      env.DB.prepare(
        `UPDATE wukong_jobs SET manifest_json = ?, updated_at = ?
         WHERE job_id = ? AND status IN ('succeeded', 'failed', 'cancelled')`
      ).bind(JSON.stringify(manifest), now, jobId)
    ]);
  } catch (error) {
    if (await existingReceipt(env, receiptKey, payloadHash)) {
      return { jobId, status: row.status, mirrorRepair: true, duplicate: true };
    }
    throw error;
  }
  return { jobId, status: row.status, mirrorRepair: true };
}

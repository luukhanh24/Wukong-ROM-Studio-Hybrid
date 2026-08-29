import type { AuthenticatedRequest } from "./auth";
import catalog from "../../../telegram_mini_app/catalog.json";
import { createJob, publicJobEvent, JobHttpError } from "./jobs";
import { profile } from "./state";
import { RomCatalogHttpError, romCatalog } from "./rom-catalog";
import { presetLabels, releaseVersions } from "./catalog";
import { SourceProbeHttpError } from "./source-probe";

type JsonObject = Record<string, unknown>;
type BatchRow = { batch_id: string; owner_subject: string; idempotency_key: string; release_version: string; editions_json: string; status: string; created_at: string; updated_at: string; finished_at: string };
type ItemRow = { item_id: string; batch_id: string; device: string; mod_version: string; release_version: string; status: string; source_url: string; source_version: string; job_id: string; error: string; error_code: string; source_attempts: number; source_retry_at: string; created_at: string; updated_at: string };

const SAFE_LABEL = /^(?=.{1,64}$)(?!.*[ .]$)(?!\.+$)[^/\\\u0000-\u001f<>:\"|?*]+$/;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MAX_BATCH_COMBINATIONS = 200;
const SOURCE_LOOKUP_ERROR_CODE = "source_temporarily_unavailable";
const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

export class BatchBuildHttpError extends Error {
  constructor(message: string, readonly status = 400) { super(message); }
}

function strings(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw new BatchBuildHttpError(`${label} must be a list`);
  const result = [...new Set(value.map(item => String(item ?? "").trim()).filter(Boolean))];
  if (!result.length) throw new BatchBuildHttpError(`${label} is required`);
  return result;
}

async function event(env: Env, batchId: string, type: string, message: string, itemId = "", details: JsonObject = {}): Promise<void> {
  await env.DB.prepare(`INSERT INTO wukong_batch_build_events (event_id,batch_id,item_id,event_type,message,details_json,created_at) VALUES (?,?,?,?,?,?,?)`)
    .bind(crypto.randomUUID(), batchId, itemId, type, message, JSON.stringify(details), new Date().toISOString()).run();
}

function osVersion(modVersion: string): string {
  return modVersion.replace(/^[^_]+_/, "");
}

function normalizeRelease(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.filter(row => row && typeof row === "object") as JsonObject[] : [];
}

async function findSource(env: Env, device: string, modVersion: string): Promise<JsonObject | null> {
  const realmeDevice = /^RMX/i.test(device);
  if (modVersion.startsWith("RealmeUI_") !== realmeDevice) return null;
  const request = new Request(`https://worker.internal/v1/rom-catalog?model=${encodeURIComponent(device)}&latest=0`);
  const result = await romCatalog(request, env) as JsonObject;
  const desired = osVersion(modVersion);
  const versionPattern = new RegExp(`(^|\\D)${desired.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\d)`);
  return normalizeRelease(result.releases).find(row => {
    const version = `${row.version ?? ""} ${row.otaVersion ?? ""}`;
    return versionPattern.test(version) && /^https?:\/\//i.test(String(row.sourceUrl ?? ""));
  }) ?? null;
}

function transientSourceLookupError(error: unknown): error is RomCatalogHttpError | SourceProbeHttpError {
  return error instanceof RomCatalogHttpError || error instanceof SourceProbeHttpError;
}

function sourceRetryDelaySeconds(attempt: number): number {
  return Math.min(30 * 2 ** Math.min(Math.max(attempt - 1, 0), 6), 30 * 60);
}

function sourceRetryDueSql(alias = ""): string {
  const column = alias ? `${alias}.source_retry_at` : "source_retry_at";
  return `(${column}='' OR ${column}<=?)`;
}

async function scheduleSourceLookupRetry(env: Env, batchId: string, item: ItemRow, error: Error): Promise<void> {
  const attempt = Number(item.source_attempts ?? 0) + 1;
  const now = new Date().toISOString();
  const retryAt = new Date(Date.now() + sourceRetryDelaySeconds(attempt) * 1000).toISOString();
  await env.DB.prepare("UPDATE wukong_batch_build_items SET status='pending_source',error=?,error_code=?,source_attempts=?,source_retry_at=?,updated_at=? WHERE item_id=? AND status='resolving'")
    .bind(`Tạm thời chưa truy cập được nguồn ROM; sẽ tự thử lại (lần ${attempt})`, SOURCE_LOOKUP_ERROR_CODE, attempt, retryAt, now, item.item_id).run();
  await event(env, batchId, "source_retry", `Nguồn ROM tạm thời gián đoạn; sẽ thử lại ${item.device}`, item.item_id, {
    attempt, retryAt, reason: error.message
  });
}

function recipeFor(item: ItemRow, batch: BatchRow, editions: string[], source: JsonObject, labels: Record<string, string>): JsonObject {
  const data = catalog as unknown as JsonObject;
  const presets = data.presetDefaultsByVersion as Record<string, Record<string, string[]>>;
  const preset = editions.length === 2 ? "both" : (editions[0] ?? "lite");
  const releaseVersion = item.release_version || batch.release_version;
  return {
    schemaVersion: 1,
    task: "build",
    device: item.device,
    source: { kind: "https", uri: source.sourceUrl, metadata: {
      productName: String(source.device ?? item.device), device: String(source.model ?? item.device),
      version: String(source.version ?? ""), securityPatch: String(source.securityPatch ?? "")
    } },
    execution: { target: "github-auto" },
    storage: { remote: "wukong-gdrive", publishArtifact: true, artifactRoot: `ROM/${releaseVersion}` },
    build: {
      preset, modVersion: item.mod_version, modReleaseVersion: releaseVersion,
      editionLabels: labels,
      mods: presets?.[item.mod_version]?.[preset] ?? presets?.[item.mod_version]?.plus ?? [],
      enabledSteps: Array.isArray(data.pipelineSteps) ? (data.pipelineSteps as JsonObject[]).filter(step => step.default).map(step => step.id) : [],
      package: true, notifyTelegram: true
    }
  };
}

async function loadBatch(env: Env, batchId: string): Promise<BatchRow> {
  const row = await env.DB.prepare("SELECT * FROM wukong_batch_builds WHERE batch_id = ?").bind(batchId).first<BatchRow>();
  if (!row) throw new BatchBuildHttpError("Batch build was not found", 404);
  return row;
}

async function existingBatchPayload(env: Env, batch: BatchRow): Promise<JsonObject> {
  const rows = await env.DB.prepare("SELECT mod_version,release_version FROM wukong_batch_build_items WHERE batch_id=?")
    .bind(batch.batch_id).all<{mod_version:string;release_version:string}>();
  return {
    batchId: batch.batch_id,
    releaseVersion: batch.release_version || null,
    releaseVersions: Object.fromEntries(rows.results.map(row => [row.mod_version, row.release_version || batch.release_version])),
    itemCount: rows.results.length,
    status: batch.status
  };
}

export async function processBatch(env: Env, batchId: string, limit = 3): Promise<void> {
  const batch = await loadBatch(env, batchId);
  if (["succeeded", "partial", "failed", "cancelled"].includes(batch.status)) return;
  const owner = await profile(env, batch.owner_subject);
  if (!owner || owner.role !== "admin") throw new BatchBuildHttpError("Batch owner is no longer an admin", 403);
  const auth = { subject: batch.owner_subject, role: "admin", profile: owner } as AuthenticatedRequest;
  const editions = JSON.parse(batch.editions_json) as string[];
  const labels = await presetLabels(env);
  const pending = await env.DB.prepare(`SELECT * FROM wukong_batch_build_items WHERE batch_id = ? AND status = 'pending_source' AND ${sourceRetryDueSql()} ORDER BY created_at,item_id LIMIT ?`)
    .bind(batchId, new Date().toISOString(), limit).all<ItemRow>();
  for (const item of pending.results) {
    const claimed = await env.DB.prepare("UPDATE wukong_batch_build_items SET status='resolving',error='',updated_at=? WHERE item_id=? AND status='pending_source'")
      .bind(new Date().toISOString(), item.item_id).run();
    if (!claimed.meta.changes) continue;
    try {
      await event(env, batchId, "source_search", `Đang tìm ROM nguồn cho ${item.device} · ${item.mod_version}`, item.item_id);
      const source = await findSource(env, item.device, item.mod_version);
      if (!source) {
        await env.DB.prepare("UPDATE wukong_batch_build_items SET status='source_failed',error=?,updated_at=? WHERE item_id=?")
          .bind(`Không tìm thấy ROM ${osVersion(item.mod_version)} phù hợp`, new Date().toISOString(), item.item_id).run();
        await event(env, batchId, "source_failed", `Không tìm thấy ROM phù hợp cho ${item.device}`, item.item_id, { modVersion: item.mod_version });
        continue;
      }
      await event(env, batchId, "source_found", `Đã tìm thấy ${source.version ?? "ROM nguồn"}`, item.item_id, { version: source.version, region: source.region });
      const result = await createJob(env, auth, recipeFor(item, batch, editions, source, labels), `batch:${batchId}:${item.item_id}`, true);
      const jobId = String(result.job.job_id ?? result.job.jobId ?? "");
      const now = new Date().toISOString();
      await env.DB.prepare("UPDATE wukong_batch_build_items SET status='job_created',source_url=?,source_version=?,job_id=?,error='',updated_at=? WHERE item_id=?")
        .bind(String(source.sourceUrl), String(source.version ?? ""), jobId, now, item.item_id).run();
      await event(env, batchId, "job_created", `Đã gửi job build ${item.device} · ${item.mod_version}`, item.item_id, { jobId });
    } catch (error) {
      if (error instanceof JobHttpError && ["build_concurrency_limit", "build_concurrency_conflict"].includes(error.code)) {
        await env.DB.prepare("UPDATE wukong_batch_build_items SET status='pending_source',updated_at=? WHERE item_id=? AND status='resolving'")
          .bind(new Date().toISOString(), item.item_id).run();
        break;
      }
      if (transientSourceLookupError(error)) {
        await scheduleSourceLookupRetry(env, batchId, item, error);
        continue;
      }
      const message = error instanceof Error ? error.message : "Batch item failed";
      await env.DB.prepare("UPDATE wukong_batch_build_items SET status='failed',error=?,updated_at=? WHERE item_id=?")
        .bind(message, new Date().toISOString(), item.item_id).run();
      await event(env, batchId, "item_failed", message, item.item_id);
    }
  }
  await refreshBatchStatus(env, batchId);
}

function batchStatus(values: string[]): string {
  const pending = values.some(value => ![...TERMINAL, "source_failed", "failed"].includes(value));
  const successes = values.filter(value => value === "succeeded").length;
  const failures = values.filter(value => ["failed", "cancelled", "source_failed"].includes(value)).length;
  return pending ? "running" : failures === 0 ? "succeeded" : successes ? "partial" : "failed";
}

async function refreshBatchStatus(env: Env, batchId: string): Promise<void> {
  const rows = await env.DB.prepare(`SELECT i.status item_status,j.status job_status FROM wukong_batch_build_items i LEFT JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=?`).bind(batchId).all<{item_status:string;job_status:string|null}>();
  const values = rows.results.map(row => row.job_status || row.item_status);
  const status = batchStatus(values);
  const pending = status === "running";
  const now = new Date().toISOString();
  await env.DB.prepare("UPDATE wukong_batch_builds SET status=?,updated_at=?,finished_at=? WHERE batch_id=?")
    .bind(status, now, pending ? "" : now, batchId).run();
}

export async function createBatchBuild(env: Env, auth: AuthenticatedRequest, value: unknown, rawIdempotencyKey: string): Promise<{batch:JsonObject;created:boolean}> {
  if (auth.role !== "admin") throw new BatchBuildHttpError("Admin access is required", 403);
  const payload = value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
  const devices = strings(payload.devices, "devices");
  const modVersions = strings(payload.modVersions, "modVersions");
  const editions = [...new Set(strings(payload.editions, "editions").map(value => value.toLowerCase()))];
  const data = catalog as unknown as JsonObject;
  const knownDevices = new Set((data.devices as JsonObject[]).map(item => String(item.product)));
  const knownMods = new Set(data.modVersions as string[]);
  if (devices.some(value => !knownDevices.has(value))) throw new BatchBuildHttpError("Unknown supported device");
  if (modVersions.some(value => !knownMods.has(value))) throw new BatchBuildHttpError("Unknown MOD base");
  if (editions.some(value => !["lite", "plus"].includes(value))) throw new BatchBuildHttpError("Only Lite and Plus editions are supported");
  if (devices.length * modVersions.length > MAX_BATCH_COMBINATIONS) {
    throw new BatchBuildHttpError(`A batch can contain at most ${MAX_BATCH_COMBINATIONS} device/MOD combinations`);
  }
  const idempotencyKey = rawIdempotencyKey.trim();
  if (!IDEMPOTENCY_KEY.test(idempotencyKey)) throw new BatchBuildHttpError("Batch idempotency key is invalid");
  const existing = await env.DB.prepare("SELECT * FROM wukong_batch_builds WHERE owner_subject=? AND idempotency_key=?")
    .bind(auth.subject, idempotencyKey).first<BatchRow>();
  if (existing) {
    return { batch: await existingBatchPayload(env, existing), created: false };
  }
  const labels = await releaseVersions(env);
  const itemReleaseVersions = Object.fromEntries(modVersions.map(modVersion => [modVersion, String(labels[modVersion] ?? "").trim()]));
  if (Object.values(itemReleaseVersions).some(label => !SAFE_LABEL.test(label))) throw new BatchBuildHttpError("Release version is invalid");
  const distinctReleaseVersions = [...new Set(Object.values(itemReleaseVersions))];
  const releaseVersion = distinctReleaseVersions.length === 1 ? distinctReleaseVersions[0] ?? "" : "";
  const batchId = crypto.randomUUID().replaceAll("-", "");
  const now = new Date().toISOString();
  const items = devices.flatMap(device => modVersions.map(modVersion => ({
    itemId: crypto.randomUUID().replaceAll("-", ""), device, modVersion, releaseVersion: itemReleaseVersions[modVersion] ?? ""
  })));
  const itemInserts = Array.from({ length: Math.ceil(items.length / 10) }, (_, index) => items.slice(index * 10, index * 10 + 10))
    .map(chunk => env.DB.prepare(`INSERT INTO wukong_batch_build_items
      (item_id,batch_id,device,mod_version,release_version,created_at,updated_at) VALUES
      ${chunk.map(() => "(?,?,?,?,?,?,?)").join(",")}`)
      .bind(...chunk.flatMap(item => [item.itemId, batchId, item.device, item.modVersion, item.releaseVersion, now, now])));
  try {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO wukong_batch_builds (batch_id,owner_subject,idempotency_key,release_version,editions_json,status,created_at,updated_at) VALUES (?,?,?,?,?, 'queued',?,?)")
        .bind(batchId, auth.subject, idempotencyKey, releaseVersion, JSON.stringify(editions), now, now),
      ...itemInserts,
      env.DB.prepare("INSERT INTO wukong_batch_build_events (event_id,batch_id,event_type,message,details_json,created_at) VALUES (?,?,'batch_created',?,?,?)")
        .bind(crypto.randomUUID(), batchId, `Đã tạo ${items.length} cấu hình build`, JSON.stringify({ devices, modVersions, editions, releaseVersions: itemReleaseVersions }), now)
    ]);
  } catch (error) {
    const winner = await env.DB.prepare("SELECT * FROM wukong_batch_builds WHERE owner_subject=? AND idempotency_key=?")
      .bind(auth.subject, idempotencyKey).first<BatchRow>();
    if (!winner) throw error;
    return { batch: await existingBatchPayload(env, winner), created: false };
  }
  return { batch: { batchId, releaseVersion: releaseVersion || null, releaseVersions: itemReleaseVersions, itemCount: items.length, status: "queued" }, created: true };
}

export async function batchBuild(env: Env, auth: AuthenticatedRequest, batchId: string): Promise<JsonObject> {
  if (auth.role !== "admin") throw new BatchBuildHttpError("Admin access is required", 403);
  const batch = await loadBatch(env, batchId);
  const items = await env.DB.prepare(`SELECT i.*,j.status job_status,j.stage job_stage,j.progress job_progress FROM wukong_batch_build_items i LEFT JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=? ORDER BY i.created_at,i.item_id`).bind(batchId).all<ItemRow & {job_status:string;job_stage:string;job_progress:number}>();
  const events = await env.DB.prepare("SELECT * FROM wukong_batch_build_events WHERE batch_id=? ORDER BY created_at,event_id LIMIT 500").bind(batchId).all<Record<string, unknown>>();
  const jobEventRows = await env.DB.prepare(`SELECT job_id,sequence,timestamp,event_type,payload_json FROM (
    SELECT e.*,ROW_NUMBER() OVER (PARTITION BY e.job_id ORDER BY e.sequence DESC) event_rank
    FROM wukong_job_events e JOIN wukong_batch_build_items i ON i.job_id=e.job_id WHERE i.batch_id=?
  ) WHERE event_rank<=50 ORDER BY job_id,sequence`).bind(batchId).all<Record<string, unknown>>();
  const eventsByJob = new Map<string, JsonObject[]>();
  jobEventRows.results.forEach(row => {
    const jobId = String(row.job_id || "");
    if (!eventsByJob.has(jobId)) eventsByJob.set(jobId, []);
    eventsByJob.get(jobId)?.push(publicJobEvent(row, env, jobId));
  });
  const publicItems = items.results.map(row => ({
    itemId: row.item_id, device: row.device, modVersion: row.mod_version, status: row.job_status || row.status,
    releaseVersion: row.release_version || batch.release_version,
    itemStatus: row.status, sourceVersion: row.source_version, jobId: row.job_id, stage: row.job_stage || "",
    progress: Number(row.job_progress || 0), error: row.error,
    jobEvents: eventsByJob.get(row.job_id) || []
  }));
  const liveStatus = batchStatus(items.results.map(row => row.job_status || row.status));
  return {
    batchId: batch.batch_id, releaseVersion: batch.release_version || null,
    releaseVersions: Object.fromEntries(publicItems.map(item => [item.modVersion, item.releaseVersion])),
    editions: JSON.parse(batch.editions_json), status: liveStatus,
    createdAt: batch.created_at, updatedAt: batch.updated_at, finishedAt: batch.finished_at,
    items: publicItems,
    events: events.results.map(row => ({ eventId: row.event_id, itemId: row.item_id, eventType: row.event_type, message: row.message, details: JSON.parse(String(row.details_json || "{}")), createdAt: row.created_at }))
  };
}

export async function listBatchBuilds(env: Env, auth: AuthenticatedRequest): Promise<JsonObject> {
  if (auth.role !== "admin") throw new BatchBuildHttpError("Admin access is required", 403);
  const rows = await env.DB.prepare("SELECT * FROM wukong_batch_builds ORDER BY created_at DESC LIMIT 50").all<BatchRow>();
  return { batches: rows.results.map(row => ({ batchId: row.batch_id, releaseVersion: row.release_version || null, status: row.status, createdAt: row.created_at, updatedAt: row.updated_at })) };
}

export async function processOpenBatches(env: Env): Promise<void> {
  await env.DB.prepare(`UPDATE wukong_batch_build_items
    SET status='pending_source', error='Previous source lookup timed out and will be retried', updated_at=?
    WHERE status='resolving' AND unixepoch(updated_at) < unixepoch('now','-10 minutes')`)
    .bind(new Date().toISOString()).run();
  const eligibleAt = new Date().toISOString();
  const rows = await env.DB.prepare(`SELECT b.batch_id FROM wukong_batch_builds b
    WHERE b.status IN ('queued','running') AND EXISTS (
      SELECT 1 FROM wukong_batch_build_items i WHERE i.batch_id=b.batch_id AND i.status='pending_source'
        AND ${sourceRetryDueSql("i")}
    ) ORDER BY b.created_at LIMIT 1`).bind(eligibleAt).all<{batch_id:string}>();
  for (const row of rows.results) await processBatch(env, row.batch_id).catch(error => console.error("Batch processing failed", error));
  const now = new Date().toISOString();
  await env.DB.prepare(`UPDATE wukong_batch_builds AS b SET
    status=CASE
      WHEN EXISTS (SELECT 1 FROM wukong_batch_build_items i LEFT JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=b.batch_id AND COALESCE(j.status,i.status) NOT IN ('succeeded','failed','cancelled','source_failed')) THEN 'running'
      WHEN EXISTS (SELECT 1 FROM wukong_batch_build_items i JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=b.batch_id AND j.status='succeeded')
       AND EXISTS (SELECT 1 FROM wukong_batch_build_items i LEFT JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=b.batch_id AND COALESCE(j.status,i.status) IN ('failed','cancelled','source_failed')) THEN 'partial'
      WHEN EXISTS (SELECT 1 FROM wukong_batch_build_items i LEFT JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=b.batch_id AND COALESCE(j.status,i.status) IN ('failed','cancelled','source_failed')) THEN 'failed'
      ELSE 'succeeded' END,
    updated_at=?,
    finished_at=CASE WHEN EXISTS (SELECT 1 FROM wukong_batch_build_items i LEFT JOIN wukong_jobs j ON j.job_id=i.job_id WHERE i.batch_id=b.batch_id AND COALESCE(j.status,i.status) NOT IN ('succeeded','failed','cancelled','source_failed')) THEN '' ELSE ? END
    WHERE b.status IN ('queued','running')`).bind(now, now).run();
}

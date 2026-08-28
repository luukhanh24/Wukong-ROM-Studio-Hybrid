import type { AuthenticatedRequest } from "./auth";
import catalog from "../../../telegram_mini_app/catalog.json";
import { createJob, publicJobEvent, JobHttpError } from "./jobs";
import { profile } from "./state";
import { romCatalog } from "./rom-catalog";

type JsonObject = Record<string, unknown>;
type BatchRow = { batch_id: string; owner_subject: string; idempotency_key: string; release_version: string; editions_json: string; status: string; created_at: string; updated_at: string; finished_at: string };
type ItemRow = { item_id: string; batch_id: string; device: string; mod_version: string; status: string; source_url: string; source_version: string; job_id: string; error: string; created_at: string; updated_at: string };

const SAFE_LABEL = /^[^/\\\u0000-\u001f]{1,64}$/;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
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

function recipeFor(item: ItemRow, batch: BatchRow, editions: string[], source: JsonObject): JsonObject {
  const data = catalog as unknown as JsonObject;
  const presets = data.presetDefaultsByVersion as Record<string, Record<string, string[]>>;
  const preset = editions.length === 2 ? "both" : (editions[0] ?? "lite");
  return {
    schemaVersion: 1,
    task: "build",
    device: item.device,
    source: { kind: "https", uri: source.sourceUrl, metadata: {
      productName: String(source.device ?? item.device), device: String(source.model ?? item.device),
      version: String(source.version ?? ""), securityPatch: String(source.securityPatch ?? "")
    } },
    execution: { target: "github-auto" },
    storage: { remote: "wukong-gdrive", publishArtifact: true, artifactRoot: `ROM/${batch.release_version}` },
    build: {
      preset, modVersion: item.mod_version, modReleaseVersion: batch.release_version,
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

export async function processBatch(env: Env, batchId: string, limit = 3): Promise<void> {
  const batch = await loadBatch(env, batchId);
  if (["succeeded", "partial", "failed", "cancelled"].includes(batch.status)) return;
  const owner = await profile(env, batch.owner_subject);
  if (!owner || owner.role !== "admin") throw new BatchBuildHttpError("Batch owner is no longer an admin", 403);
  const auth = { subject: batch.owner_subject, role: "admin", profile: owner } as AuthenticatedRequest;
  const editions = JSON.parse(batch.editions_json) as string[];
  const pending = await env.DB.prepare("SELECT * FROM wukong_batch_build_items WHERE batch_id = ? AND status = 'pending_source' ORDER BY created_at,item_id LIMIT ?")
    .bind(batchId, limit).all<ItemRow>();
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
      const result = await createJob(env, auth, recipeFor(item, batch, editions, source), `batch:${batchId}:${item.item_id}`, true);
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
  if (devices.length * modVersions.length > 50) throw new BatchBuildHttpError("A batch can contain at most 50 device/MOD combinations");
  const idempotencyKey = rawIdempotencyKey.trim();
  if (!IDEMPOTENCY_KEY.test(idempotencyKey)) throw new BatchBuildHttpError("Batch idempotency key is invalid");
  const existing = await env.DB.prepare("SELECT * FROM wukong_batch_builds WHERE owner_subject=? AND idempotency_key=?")
    .bind(auth.subject, idempotencyKey).first<BatchRow>();
  if (existing) {
    const count = await env.DB.prepare("SELECT COUNT(*) count FROM wukong_batch_build_items WHERE batch_id=?").bind(existing.batch_id).first<{count:number}>();
    return { batch: { batchId: existing.batch_id, releaseVersion: existing.release_version, itemCount: Number(count?.count || 0), status: existing.status }, created: false };
  }
  const labels = data.modReleaseVersions as Record<string, string>;
  const releaseVersion = String(payload.releaseVersion ?? labels[modVersions[0] ?? ""] ?? "").trim();
  if (!SAFE_LABEL.test(releaseVersion)) throw new BatchBuildHttpError("Release version is invalid");
  const batchId = crypto.randomUUID().replaceAll("-", "");
  const now = new Date().toISOString();
  const items = devices.flatMap(device => modVersions.map(modVersion => ({ itemId: crypto.randomUUID().replaceAll("-", ""), device, modVersion })));
  try {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO wukong_batch_builds (batch_id,owner_subject,idempotency_key,release_version,editions_json,status,created_at,updated_at) VALUES (?,?,?,?,?, 'queued',?,?)")
        .bind(batchId, auth.subject, idempotencyKey, releaseVersion, JSON.stringify(editions), now, now),
      ...items.map(item => env.DB.prepare("INSERT INTO wukong_batch_build_items (item_id,batch_id,device,mod_version,created_at,updated_at) VALUES (?,?,?,?,?,?)")
        .bind(item.itemId, batchId, item.device, item.modVersion, now, now)),
      env.DB.prepare("INSERT INTO wukong_batch_build_events (event_id,batch_id,event_type,message,details_json,created_at) VALUES (?,?,'batch_created',?,?,?)")
        .bind(crypto.randomUUID(), batchId, `Đã tạo ${items.length} cấu hình build`, JSON.stringify({ devices, modVersions, editions, releaseVersion }), now)
    ]);
  } catch (error) {
    const winner = await env.DB.prepare("SELECT * FROM wukong_batch_builds WHERE owner_subject=? AND idempotency_key=?")
      .bind(auth.subject, idempotencyKey).first<BatchRow>();
    if (!winner) throw error;
    const count = await env.DB.prepare("SELECT COUNT(*) count FROM wukong_batch_build_items WHERE batch_id=?").bind(winner.batch_id).first<{count:number}>();
    return { batch: { batchId: winner.batch_id, releaseVersion: winner.release_version, itemCount: Number(count?.count || 0), status: winner.status }, created: false };
  }
  return { batch: { batchId, releaseVersion, itemCount: items.length, status: "queued" }, created: true };
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
    itemStatus: row.status, sourceVersion: row.source_version, jobId: row.job_id, stage: row.job_stage || "",
    progress: Number(row.job_progress || 0), error: row.error,
    jobEvents: eventsByJob.get(row.job_id) || []
  }));
  const liveStatus = batchStatus(items.results.map(row => row.job_status || row.status));
  return {
    batchId: batch.batch_id, releaseVersion: batch.release_version, editions: JSON.parse(batch.editions_json), status: liveStatus,
    createdAt: batch.created_at, updatedAt: batch.updated_at, finishedAt: batch.finished_at,
    items: publicItems,
    events: events.results.map(row => ({ eventId: row.event_id, itemId: row.item_id, eventType: row.event_type, message: row.message, details: JSON.parse(String(row.details_json || "{}")), createdAt: row.created_at }))
  };
}

export async function listBatchBuilds(env: Env, auth: AuthenticatedRequest): Promise<JsonObject> {
  if (auth.role !== "admin") throw new BatchBuildHttpError("Admin access is required", 403);
  const rows = await env.DB.prepare("SELECT * FROM wukong_batch_builds ORDER BY created_at DESC LIMIT 50").all<BatchRow>();
  return { batches: rows.results.map(row => ({ batchId: row.batch_id, releaseVersion: row.release_version, status: row.status, createdAt: row.created_at, updatedAt: row.updated_at })) };
}

export async function processOpenBatches(env: Env): Promise<void> {
  await env.DB.prepare(`UPDATE wukong_batch_build_items
    SET status='pending_source', error='Previous source lookup timed out and will be retried', updated_at=?
    WHERE status='resolving' AND unixepoch(updated_at) < unixepoch('now','-10 minutes')`)
    .bind(new Date().toISOString()).run();
  const rows = await env.DB.prepare(`SELECT b.batch_id FROM wukong_batch_builds b
    WHERE b.status IN ('queued','running') AND EXISTS (
      SELECT 1 FROM wukong_batch_build_items i WHERE i.batch_id=b.batch_id AND i.status='pending_source'
    ) ORDER BY b.created_at LIMIT 1`).all<{batch_id:string}>();
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

import {
  authenticate,
  type AuthenticatedRequest,
  validateArtifactDownloadTicket
} from "./auth";
import {
  CallbackHttpError,
  handleProgress,
  handleTerminal,
  verifyActionsHmac
} from "./callbacks";
import {
  JobHttpError,
  artifactDownloadUrl,
  cancelJob,
  createJob,
  inspectJob,
  jobEvents,
  listJobs,
  listJobsForSubject,
  publicJob,
  resumeJob
} from "./jobs";
import {
  GitHubHttpError,
  bootstrapActions,
  clearActionsCaches,
  listActionsCaches
} from "./github";
import {
  catalogPayload,
  releaseVersions,
  saveReleaseVersions
} from "./catalog";
import { cloudLibrary } from "./drive";
import {
  SourceProbeHttpError,
  claimSourceTransport,
  createProbeSession,
  proxyProbeRange
} from "./source-probe";
import {
  SessionHttpError,
  beginPairing,
  clearSourceDraft,
  pairingStatus,
  sourceDraft
} from "./sessions";
import {
  TelegramHttpError,
  handleTelegramWebhook,
  maintenance
} from "./telegram";
import {
  approveUser,
  createUser,
  decodeAuditCursor,
  encodeAuditCursor,
  ensureConfiguredAdmins,
  listUsers,
  openSession,
  profile,
  profileWithActivity,
  revokeUser,
  updateAllowance,
  userEvents,
  userEventsSince
} from "./state";
import {
  maintenanceState,
  setMaintenanceState
} from "./system";
import {
  RomCatalogHttpError,
  romCatalog,
  validateRomCatalogRequest
} from "./rom-catalog";
import {
  createRomSearchTrace,
  completeRomSearch,
  failRomSearch,
  recordRomSearchStart
} from "./activity";

const RELEASE_SHA = /^[0-9a-f]{40}$/;

function json(payload: unknown, status = 200, headers?: HeadersInit): Response {
  const response = Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      ...headers
    }
  });
  return response;
}

function allowedOrigins(env: Env): Set<string> {
  return new Set(env.WUKONG_ALLOWED_ORIGINS
    .split(",")
    .map((value) => value.trim().replace(/\/+$/, "").toLowerCase())
    .filter(Boolean));
}

function withCors(response: Response, request: Request, env: Env): Response {
  const origin = (request.headers.get("Origin") ?? "").replace(/\/+$/, "").toLowerCase();
  if (!allowedOrigins(env).has(origin)) return response;
  const headers = new Headers(response.headers);
  headers.set("Access-Control-Allow-Origin", origin);
  headers.set(
    "Access-Control-Allow-Headers",
    "Authorization, Content-Type, Idempotency-Key, X-Wukong-Session-Id, X-Wukong-Client-Version, X-Telegram-Platform"
  );
  headers.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
  headers.set("Access-Control-Max-Age", "600");
  headers.set("Vary", "Origin");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

function isPublicPath(path: string): boolean {
  return path === "/healthz" || path === "/readyz";
}

async function routeWithIdentity(
  request: Request,
  env: Env,
  path: string,
  auth: AuthenticatedRequest,
  ctx: ExecutionContext
): Promise<Response> {
  if (path === "/v1/session/open" && request.method === "POST") {
    try {
      const user = await openSession(env, auth.subject, request.headers.get("X-Wukong-Session-Id") ?? "");
      return json({ user, maintenance: await maintenanceState(env) });
    } catch (error) {
      return json({
        error: error instanceof Error ? error.message : "Mini App session is invalid",
        code: "invalid_session"
      }, 400);
    }
  }
  if (path === "/v1/me" && request.method === "GET") {
    const user = await profile(env, auth.subject);
    return user
      ? json({ user, maintenance: await maintenanceState(env) })
      : json({ error: "Telegram profile is unavailable" }, 404);
  }
  if (path === "/v1/system/maintenance" && request.method === "GET") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    return json({ maintenance: await maintenanceState(env) });
  }
  if (path === "/v1/system/maintenance" && request.method === "PUT") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    const payload = await request.json().catch(() => ({})) as Record<string, unknown>;
    try {
      return json({ maintenance: await setMaintenanceState(env, auth.subject, payload) });
    } catch (error) {
      return json({
        error: error instanceof Error ? error.message : "Maintenance state is invalid"
      }, 400);
    }
  }
  if (path === "/v1/drafts/source" && request.method === "GET") {
    return json({ uri: await sourceDraft(env, auth.subject) });
  }
  if (path === "/v1/drafts/source" && request.method === "DELETE") {
    await clearSourceDraft(env, auth.subject);
    return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  }
  if (path === "/v1/catalog" && request.method === "GET") {
    return json(catalogPayload());
  }
  if (path === "/v1/sources/resolve" && request.method === "POST") {
    try {
      return json(await createProbeSession(request, env, await request.json(), auth.subject, true));
    } catch (error) {
      if (error instanceof SourceProbeHttpError) return json({ error: error.message, code: error.code }, error.status);
      return json({ error: "ROM source could not be resolved", code: "source_unreachable" }, 502);
    }
  }
  if (["/v1/rom-catalog", "/v1/rom-catalog/devices"].includes(path) && request.method === "GET") {
    if (path === "/v1/rom-catalog") {
      try {
        validateRomCatalogRequest(request);
      } catch (error) {
        if (error instanceof RomCatalogHttpError) {
          return json({ error: error.message, code: "rom_catalog_unavailable" }, error.status);
        }
        return json({ error: "ROM catalog request is invalid", code: "rom_catalog_unavailable" }, 400);
      }
    }
    const trace = path === "/v1/rom-catalog"
      ? await createRomSearchTrace(auth, request).catch(() => null)
      : null;
    const startActivity = trace
      ? recordRomSearchStart(env, auth, trace).catch(() => {
        console.error("ROM search start activity could not be recorded");
      })
      : Promise.resolve();
    if (trace) ctx.waitUntil(startActivity);
    try {
      const result = await romCatalog(request, env);
      if (trace) {
        ctx.waitUntil(startActivity.then(() => completeRomSearch(env, trace, result)).catch(() => {
          console.error("ROM search completion activity could not be recorded");
        }));
      }
      return json(result, 200, {
        "Cache-Control": "private, max-age=300"
      });
    } catch (error) {
      if (trace) {
        ctx.waitUntil(startActivity.then(() => failRomSearch(env, trace, error)).catch(() => {
          console.error("ROM search failure activity could not be recorded");
        }));
      }
      if (error instanceof RomCatalogHttpError) {
        return json({ error: error.message, code: "rom_catalog_unavailable" }, error.status);
      }
      return json({
        error: "ROM catalog is temporarily unavailable",
        code: "rom_catalog_unavailable"
      }, 503);
    }
  }
  if (path === "/v1/mod-release-versions" && request.method === "GET") {
    return json({
      modReleaseVersions: await releaseVersions(env),
      editable: auth.role === "admin"
    });
  }
  if (path === "/v1/mod-release-versions" && request.method === "PUT") {
    if (auth.role !== "admin") {
      return json({ error: "Admin access is required to edit MOD release versions" }, 403);
    }
    const payload = await request.json().catch(() => ({})) as Record<string, unknown>;
    try {
      return json({
        modReleaseVersions: await saveReleaseVersions(env, payload.modReleaseVersions)
      });
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Release version is invalid" }, 400);
    }
  }
  if (path === "/v1/sync" && request.method === "GET") {
    const params = new URL(request.url).searchParams;
    const jobs = await listJobs(env, auth);
    const selectedId = params.get("jobId") || String(
      jobs.find((job) => !["succeeded", "failed", "cancelled"].includes(String(job.status)))?.job_id
      ?? jobs[0]?.job_id
      ?? ""
    );
    let activeJob: Record<string, unknown> | null = null;
    let events: Record<string, unknown>[] = [];
    if (selectedId) {
      try {
        const row = await inspectJob(env, auth, selectedId);
        activeJob = publicJob(row, env, auth.role === "admin");
        const after = /^[0-9]+$/.test(params.get("after") ?? "")
          ? Number(params.get("after"))
          : 0;
        events = await jobEvents(env, auth, selectedId, after);
      } catch {
        activeJob = null;
      }
    }
    return json({
      user: await profile(env, auth.subject),
      maintenance: await maintenanceState(env),
      jobs,
      activeJob,
      events,
      serverTime: new Date().toISOString()
    });
  }
  if (path === "/v1/diagnostics" && request.method === "GET") {
    return json({
      system: { status: "ready", stateBackend: "d1", release: env.WUKONG_RELEASE_SHA },
      runner: { provider: "github-actions" },
      cache: { provider: "github-actions" },
      cloud: { provider: "google-drive", configured: Boolean(env.WUKONG_GOOGLE_DRIVE_FOLDER_ID) }
    });
  }
  if (path === "/v1/cache" && request.method === "GET") {
    try {
      return json(await listActionsCaches(env));
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Cache query failed" }, 502);
    }
  }
  if (path === "/v1/cache/clear" && request.method === "POST") {
    if (auth.role !== "admin") {
      return json({ error: "Admin access is required to clear shared cache" }, 403);
    }
    try {
      return json(await clearActionsCaches(env));
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Cache clearing failed" }, 409);
    }
  }
  if (path === "/v1/cloud/library" && request.method === "GET") {
    try {
      return json(await cloudLibrary(
        env,
        new URL(request.url).searchParams.get("category") ?? "artifacts"
      ));
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Cloud library failed" }, 400);
    }
  }
  if (path === "/v1/jobs" && request.method === "POST") {
    try {
      const result = await createJob(
        env,
        auth,
        await request.json(),
        request.headers.get("Idempotency-Key") ?? ""
      );
      return json(result.job, result.created ? 201 : 200);
    } catch (error) {
      if (error instanceof JobHttpError) {
        return json({ error: error.message, ...(error.code ? { code: error.code } : {}) }, error.status);
      }
      return json({ error: error instanceof Error ? error.message : "Build job could not be accepted" }, 400);
    }
  }
  if (path === "/v1/jobs" && request.method === "GET") {
    return json({ jobs: await listJobs(env, auth) });
  }
  if (path === "/v1/admin/users" && request.method === "GET") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    return json(await listUsers(env, new URL(request.url).searchParams));
  }
  if (path === "/v1/admin/users" && request.method === "POST") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    try {
      const payload = await request.json() as Record<string, unknown>;
      const user = await createUser(
        env,
        payload.telegramId,
        auth.subject,
        String(payload.username ?? ""),
        String(payload.displayName ?? "")
      );
      return json({ user }, 201);
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Telegram user is invalid" }, 400);
    }
  }
  const adminActivity = path.match(/^\/v1\/admin\/users\/([1-9][0-9]*)\/activity$/);
  if (adminActivity && request.method === "GET") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    const search = new URL(request.url).searchParams;
    const afterCreatedAt = (search.get("afterCreatedAt") ?? "1970-01-01T00:00:00.000Z").trim();
    const afterEventId = (search.get("afterEventId") ?? "").trim().slice(0, 128);
    if (!Number.isFinite(Date.parse(afterCreatedAt)) || afterCreatedAt.length > 64) {
      return json({ error: "Activity cursor is invalid" }, 400);
    }
    const user = await profileWithActivity(env, adminActivity[1]!);
    if (!user) return json({ error: "Telegram user was not found" }, 404);
    const events = await userEventsSince(
      env,
      adminActivity[1]!,
      new Date(afterCreatedAt).toISOString(),
      afterEventId,
      51
    );
    return json({
      user,
      events: events.slice(0, 50),
      hasMore: events.length > 50
    });
  }
  const adminJobs = path.match(/^\/v1\/admin\/users\/([1-9][0-9]*)\/jobs$/);
  if (adminJobs && request.method === "GET") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    try {
      return json(await listJobsForSubject(env, adminJobs[1]!, new URL(request.url).searchParams.get("cursor") || ""));
    } catch (error) {
      if (error instanceof JobHttpError) return json({ error: error.message }, error.status);
      throw error;
    }
  }
  const adminDetail = path.match(/^\/v1\/admin\/users\/([1-9][0-9]*)$/);
  if (adminDetail && request.method === "GET") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    const subject = adminDetail[1]!;
    const user = await profileWithActivity(env, subject);
    if (!user) return json({ error: "Telegram user was not found" }, 404);
    const events = await userEvents(env, subject, 101);
    const visibleEvents = events.slice(0, 100);
    const hasMore = events.length > 100;
    const jobPage = await listJobsForSubject(env, subject);
    return json({
      user,
      events: visibleEvents,
      eventsHasMore: hasMore,
      eventsNextCursor: hasMore && visibleEvents.length
        ? encodeAuditCursor(visibleEvents[visibleEvents.length - 1]!)
        : "",
      jobs: jobPage.jobs,
      jobsHasMore: jobPage.hasMore,
      jobsNextCursor: jobPage.nextCursor
    });
  }
  const adminEvents = path.match(/^\/v1\/admin\/users\/([1-9][0-9]*)\/events$/);
  if (adminEvents && request.method === "GET") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    const search = new URL(request.url).searchParams;
    const limit = Math.max(1, Math.min(Number(search.get("limit") ?? 100) || 100, 100));
    try {
      const before = decodeAuditCursor(search.get("cursor") ?? "");
      const events = await userEvents(env, adminEvents[1]!, limit + 1, before ?? undefined);
      const visibleEvents = events.slice(0, limit);
      const hasMore = events.length > limit;
      return json({
        events: visibleEvents,
        hasMore,
        nextCursor: hasMore && visibleEvents.length
          ? encodeAuditCursor(visibleEvents[visibleEvents.length - 1]!)
          : ""
      });
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Audit cursor is invalid" }, 400);
    }
  }
  const adminAction = path.match(
    /^\/v1\/admin\/users\/([1-9][0-9]*)\/(approve|revoke|allowance)$/
  );
  if (adminAction && request.method === "POST") {
    if (auth.role !== "admin") return json({ error: "Admin access is required" }, 403);
    const payload = await request.json().catch(() => ({})) as Record<string, unknown>;
    try {
      const user = adminAction[2] === "approve"
        ? await approveUser(env, adminAction[1]!, auth.subject, String(payload.reason ?? ""))
        : adminAction[2] === "revoke"
          ? await revokeUser(env, adminAction[1]!, auth.subject, String(payload.reason ?? ""))
          : await updateAllowance(env, adminAction[1]!, auth.subject, payload);
      return json({ user });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Admin update failed";
      const status = adminAction[2] === "revoke" && !String(payload.reason ?? "").trim() ? 400 : 409;
      return json({ error: message }, status);
    }
  }
  const detail = path.match(/^\/v1\/jobs\/([A-Za-z0-9-]{1,64})$/);
  if (detail && request.method === "GET") {
    try {
      const row = await inspectJob(env, auth, detail[1]!);
      return json(publicJob(row, env, auth.role === "admin"));
    } catch (error) {
      const status = error instanceof JobHttpError ? error.status : 404;
      return json({ error: error instanceof Error ? error.message : "Job not found" }, status);
    }
  }
  const events = path.match(/^\/v1\/jobs\/([A-Za-z0-9-]{1,64})\/events$/);
  if (events && request.method === "GET") {
    const rawAfter = new URL(request.url).searchParams.get("after") ?? "0";
    if (!/^[0-9]+$/.test(rawAfter)) return json({ error: "Event cursor must be an integer" }, 400);
    try {
      return json({ events: await jobEvents(env, auth, events[1]!, Number(rawAfter)) });
    } catch (error) {
      const status = error instanceof JobHttpError ? error.status : 404;
      return json({ error: error instanceof Error ? error.message : "Job not found" }, status);
    }
  }
  const cancel = path.match(/^\/v1\/jobs\/([A-Za-z0-9-]{1,64})\/cancel$/);
  if (cancel && request.method === "POST") {
    try {
      return json(await cancelJob(env, auth, cancel[1]!));
    } catch (error) {
      if (error instanceof JobHttpError || error instanceof GitHubHttpError) {
        return json({ error: error.message }, error.status);
      }
      return json({ error: "Job could not be cancelled" }, 409);
    }
  }
  const resume = path.match(/^\/v1\/jobs\/([A-Za-z0-9-]{1,64})\/resume$/);
  if (resume && request.method === "POST") {
    try {
      const result = await resumeJob(
        env,
        auth,
        resume[1]!,
        request.headers.get("Idempotency-Key") ?? ""
      );
      return json(result.job, result.created ? 201 : 200);
    } catch (error) {
      if (error instanceof JobHttpError) {
        return json({ error: error.message, ...(error.code ? { code: error.code } : {}) }, error.status);
      }
      return json({ error: "Job could not be resumed" }, 409);
    }
  }
  const download = path.match(/^\/v1\/jobs\/([A-Za-z0-9-]{1,64})\/download$/);
  if (download && request.method === "GET") {
    try {
      const row = await inspectJob(env, auth, download[1]!);
      const target = artifactDownloadUrl(row, env);
      if (!target) return json({ error: "Artifact download is not available yet" }, 409);
      return json({ downloadUrl: target, provider: new URL(target).hostname });
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Job not found" }, 404);
    }
  }
  return json({ error: "Not found" }, 404);
}

async function privateRoute(
  request: Request,
  env: Env,
  path: string,
  ctx: ExecutionContext
): Promise<Response> {
  let auth: AuthenticatedRequest;
  try {
    auth = await authenticate(request, env);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Authentication failed" }, 401);
  }
  const pendingAllowed = path === "/v1/session/open" || path === "/v1/me";
  const systemMaintenance = await maintenanceState(env);
  if (systemMaintenance.enabled && auth.role !== "admin" && !pendingAllowed) {
    return json({
      error: systemMaintenance.message,
      code: "maintenance_mode",
      maintenance: systemMaintenance
    }, 503);
  }
  if (auth.profile.accessStatus !== "approved" && !pendingAllowed) {
    const revoked = auth.profile.accessStatus === "revoked";
    return json({
      error: revoked ? "Telegram account is revoked" : "Telegram account is awaiting approval",
      code: revoked ? "access_revoked" : "access_pending"
    }, 403);
  }
  return routeWithIdentity(request, env, path, auth, ctx);
}

async function readiness(env: Env): Promise<boolean> {
  try {
    await env.DB.prepare("SELECT 1 AS ready").first();
    await ensureConfiguredAdmins(env);
    return true;
  } catch {
    return false;
  }
}

const worker: ExportedHandler<Env> = {
  async fetch(request, env, ctx): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (path === "/healthz" && request.method === "GET") {
      const ready = await readiness(env);
      const release = env.WUKONG_RELEASE_SHA.trim().toLowerCase();
      return json(
        {
          status: ready ? "ready" : "starting",
          service: "wukong-control-plane",
          stateBackend: "d1",
          release: RELEASE_SHA.test(release) ? release : "development"
        },
        ready ? 200 : 503
      );
    }
    if (path === "/readyz" && request.method === "GET") {
      const ready = await readiness(env);
      return json({ status: ready ? "ready" : "starting" }, ready ? 200 : 503);
    }
    if (path === "/telegram/webhook" && request.method === "POST") {
      try {
        await ensureConfiguredAdmins(env);
        await handleTelegramWebhook(request, env);
        return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
      } catch (error) {
        if (error instanceof TelegramHttpError) {
          return json({ error: error.message }, error.status);
        }
        return json({ error: "Telegram webhook processing failed" }, 503);
      }
    }
    if (
      request.method === "POST" &&
      (path === "/internal/actions/progress" || path === "/internal/actions/callback")
    ) {
      const body = await request.text();
      try {
        await verifyActionsHmac(request, env, body);
        const result = path.endsWith("/progress")
          ? await handleProgress(env, body)
          : await handleTerminal(env, body);
        return json(result);
      } catch (error) {
        if (error instanceof CallbackHttpError) {
          return json({ error: error.message }, error.status);
        }
        return json({ error: error instanceof Error ? error.message : "Actions callback failed" }, 400);
      }
    }
    if (path === "/internal/actions/bootstrap" && request.method === "POST") {
      const body = await request.text();
      try {
        await verifyActionsHmac(request, env, body);
        return json(await bootstrapActions(request, env, JSON.parse(body)));
      } catch (error) {
        if (error instanceof CallbackHttpError) {
          return json({ error: error.message }, error.status);
        }
        if (error instanceof GitHubHttpError) {
          return json({ error: error.message }, error.status);
        }
        return json({ error: error instanceof Error ? error.message : "Actions bootstrap failed" }, 400);
      }
    }
    if (path === "/internal/source-transport/claim" && request.method === "POST") {
      return claimSourceTransport(request, env);
    }
    const ticketDownload = path.match(/^\/v1\/jobs\/([A-Za-z0-9-]{1,64})\/download$/);
    const ticket = new URL(request.url).searchParams.get("ticket") ?? "";
    if (ticketDownload && request.method === "GET" && ticket) {
      try {
        const subject = await validateArtifactDownloadTicket(
          ticketDownload[1]!,
          ticket,
          env.WUKONG_TELEGRAM_BOT_TOKEN
        );
        await ensureConfiguredAdmins(env);
        const user = await profile(env, subject);
        const row = await env.DB.prepare("SELECT * FROM wukong_jobs WHERE job_id = ?")
          .bind(ticketDownload[1]!)
          .first<import("./jobs").JobRow>();
        if (
          !user ||
          user.accessStatus !== "approved" ||
          !row ||
          (user.role !== "admin" &&
            (row.owner_channel !== "telegram" || row.owner_subject !== subject))
        ) {
          return json({ error: "Artifact download is not available" }, 404);
        }
        const target = artifactDownloadUrl(row, env);
        if (!target) return json({ error: "Artifact download is not available yet" }, 409);
        return new Response(null, {
          status: 302,
          headers: {
            "Cache-Control": "no-store",
            Location: target
          }
        });
      } catch (error) {
        return json({
          error: error instanceof Error ? error.message : "Artifact download ticket is invalid"
        }, 403);
      }
    }
    if (
      request.method === "POST" &&
      (path === "/v1/session/pair" || path === "/v1/session/pair/status")
    ) {
      const origin = (request.headers.get("Origin") ?? "").replace(/\/+$/, "").toLowerCase();
      if (!allowedOrigins(env).has(origin)) {
        return json({ error: "This Mini App origin is not allowed" }, 403);
      }
      try {
        if (path.endsWith("/status")) {
          const result = await pairingStatus(env, await request.json());
          return withCors(json(result.payload, result.status), request, env);
        }
        return withCors(json(await beginPairing(env), 201), request, env);
      } catch (error) {
        if (error instanceof SessionHttpError) {
          return withCors(json({ error: error.message }, error.status), request, env);
        }
        return withCors(json({ error: "Telegram pairing is unavailable" }, 503), request, env);
      }
    }
    const rangeRoute = path.match(/^\/v1\/sources\/probe\/([0-9a-f]{32})\/range$/);
    if (rangeRoute && request.method === "GET") {
      const origin = (request.headers.get("Origin") ?? "").replace(/\/+$/, "").toLowerCase();
      if (!allowedOrigins(env).has(origin)) {
        return json({ error: "This Mini App origin is not allowed" }, 403);
      }
      try {
        return withCors(await proxyProbeRange(request, env, rangeRoute[1]!), request, env);
      } catch (error) {
        if (error instanceof SourceProbeHttpError) {
          return withCors(json({ error: error.message, code: error.code }, error.status), request, env);
        }
        return withCors(json({ error: "ROM source range failed", code: "source_unreachable" }, 400), request, env);
      }
    }
    if (path === "/v1/sources/probe" && request.method === "POST") {
      const origin = (request.headers.get("Origin") ?? "").replace(/\/+$/, "").toLowerCase();
      if (!allowedOrigins(env).has(origin)) {
        return json({ error: "This Mini App origin is not allowed" }, 403);
      }
      let subject = "";
      if (request.headers.get("Authorization")) {
        try {
          subject = (await authenticate(request, env)).subject;
        } catch {
          return withCors(json({ error: "Telegram Mini App authentication is invalid" }, 401), request, env);
        }
      }
      try {
        return withCors(
          json(await createProbeSession(request, env, await request.json(), subject)),
          request,
          env
        );
      } catch (error) {
        if (error instanceof SourceProbeHttpError) {
          return withCors(json({ error: error.message, code: error.code }, error.status), request, env);
        }
        console.error("Unexpected source probe failure", error instanceof Error ? error.message : String(error));
        return withCors(json({ error: "ROM source is unavailable", code: "source_unreachable" }, 400), request, env);
      }
    }
    if (!isPublicPath(path)) {
      const origin = (request.headers.get("Origin") ?? "").replace(/\/+$/, "").toLowerCase();
      if (!allowedOrigins(env).has(origin)) {
        return json({ error: "This Mini App origin is not allowed" }, 403);
      }
      if (request.method === "OPTIONS") {
        return withCors(new Response(null, { status: 204 }), request, env);
      }
      await ensureConfiguredAdmins(env);
      return withCors(await privateRoute(request, env, path, ctx), request, env);
    }
    return json({ error: "Not found" }, 404);
  },
  async scheduled(_controller, env, ctx): Promise<void> {
    ctx.waitUntil(maintenance(env));
  }
};

export default worker;

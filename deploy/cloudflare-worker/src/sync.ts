import type { AuthenticatedRequest } from "./auth";
import { JobHttpError, inspectJob, listJobHistory, listJobs, publicJob, selectJob, readJobEventPage } from "./jobs";
import { profile } from "./state";
import { maintenanceState } from "./system";

/** History is optional for new clients; the legacy response remains unchanged. */
export async function syncJobs(env: Env, auth: AuthenticatedRequest, params: URLSearchParams) {
  const includeHistory = params.get("includeHistory") !== "0";
  const afterText = params.get("after") || "0";
  const after = /^\d+$/.test(afterText) && Number.isSafeInteger(Number(afterText)) ? Number(afterText) : 0;
  const history = includeHistory && params.has("page") ? await listJobHistory(env, auth, params) : null;
  const jobs = includeHistory ? history?.jobs ?? await listJobs(env, auth) : undefined;
  let row = null;
  const selectedId = params.get("jobId");
  try {
    row = selectedId ? await inspectJob(env, auth, selectedId) : await selectJob(env, auth);
  } catch (error) {
    // An inaccessible/deleted job keeps the legacy null response. Storage and
    // transport failures must never masquerade as a successful empty snapshot.
    if (!(error instanceof JobHttpError) || error.status !== 404) throw error;
  }
  const [eventPage, user, maintenance] = await Promise.all([
    row ? readJobEventPage(env, row, after, Number.isSafeInteger(Number(params.get("before"))) ? Math.max(0, Number(params.get("before"))) : 0) : { events: [], eventsHasMore: false, nextEventSequence: after },
    profile(env, auth.subject), maintenanceState(env)
  ]);
  return {
    user, maintenance,
    ...(includeHistory ? { jobs } : {}),
    ...(history ? {
      page: history.page, pageSize: history.pageSize, total: history.total,
      totalPages: history.totalPages, statusCounts: history.statusCounts
    } : {}),
    activeJob: row ? publicJob(row, env, auth.role === "admin") : null,
    ...eventPage,
    serverTime: new Date().toISOString()
  };
}

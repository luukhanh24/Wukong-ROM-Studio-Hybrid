/** Bounded transport shared by authenticated and public Mini App requests. */
export const RETRYABLE_STATUSES = new Set([429, 502, 503, 504]);

export function retryDelay(value, now = Date.now()) {
  if (!value) return 0;
  const seconds = Number(value);
  return Number.isFinite(seconds) ? Math.max(0, seconds * 1000) : Math.max(0, Date.parse(value) - now) || 0;
}

function aborted(signal) {
  return signal?.reason || new DOMException("Aborted", "AbortError");
}

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(aborted(signal)); return; }
    const cancel = () => { clearTimeout(timer); reject(aborted(signal)); };
    const timer = setTimeout(() => { signal?.removeEventListener("abort", cancel); resolve(); }, ms);
    signal?.addEventListener("abort", cancel, { once: true });
  });
}

export async function requestJson(url, options = {}) {
  const { timeoutMs = 15000, retries = 2, signal, ...init } = options;
  const method = String(init.method || "GET").toUpperCase();
  const attempts = ["GET", "HEAD"].includes(method) ? retries + 1 : 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (signal?.aborted) throw aborted(signal);
    const controller = new AbortController();
    const cancel = () => controller.abort(aborted(signal));
    signal?.addEventListener("abort", cancel, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    let retryAfterMs = 0;
    try {
      const response = await fetch(url, { ...init, signal: controller.signal });
      retryAfterMs = retryDelay(response.headers.get("Retry-After"));
      let payload;
      try { payload = await response.json(); }
      catch (cause) {
        if (controller.signal.aborted) throw cause;
        if (!response.ok) payload = {};
        else {
          const error = new Error("Invalid server response");
          error.code = "invalid_response";
          error.connectionFailed = true;
          throw error;
        }
      }
      retryAfterMs = Math.max(retryDelay(response.headers.get("Retry-After")), Number(payload?.retryAfterMs) || 0);
      if (!response.ok) {
        const error = new Error(payload?.error || `HTTP ${response.status}`);
        Object.assign(error, {
          status: response.status, code: payload?.code || "", payload,
          requestId: payload?.requestId || response.headers.get("X-Request-Id") || "",
          retryable: payload?.retryable ?? RETRYABLE_STATUSES.has(response.status), retryAfterMs,
          sourceRejected: response.status >= 400 && response.status < 500 && response.status !== 429,
          uncertain: method !== "GET" && response.status >= 500
        });
        throw error;
      }
      return { payload, status: response.status };
    } catch (cause) {
      if (signal?.aborted) throw aborted(signal);
      const error = timedOut ? Object.assign(new Error("Request timed out"), { code: "request_timeout" }) : cause;
      const networkFailure = timedOut || !error.status;
      if (networkFailure) Object.assign(error, { connectionFailed: true, retryable: true, uncertain: method !== "GET" });
      if (attempt + 1 >= attempts || !(networkFailure || (RETRYABLE_STATUSES.has(error.status) && error.retryable !== false))) throw error;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancel);
    }
    await delay(Math.max(retryAfterMs, 500 * 2 ** attempt), signal);
  }
}

/** A new read in a scope invalidates and cancels the previous one. */
export class RequestScopes {
  #controllers = new Map();
  start(scope) {
    this.cancel(scope);
    const controller = new AbortController();
    this.#controllers.set(scope, controller);
    return controller.signal;
  }
  cancel(scope) {
    this.#controllers.get(scope)?.abort();
    this.#controllers.delete(scope);
  }
  cancelAll() {
    for (const scope of this.#controllers.keys()) this.cancel(scope);
  }
  isCurrent(scope, signal) {
    return !signal.aborted && this.#controllers.get(scope)?.signal === signal;
  }
}

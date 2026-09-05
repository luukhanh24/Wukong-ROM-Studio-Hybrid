import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { requestJson, RequestScopes, retryDelay } from "../lib/http.js";

const fetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = fetch; });

test("reads recover from transient failures; writes are never automatically replayed", async () => {
  let calls = 0;
  globalThis.fetch = async () => ++calls < 2 ? Response.json({ error: "busy" }, { status: 503 }) : Response.json({ job: 1 });
  assert.deepEqual((await requestJson("http://fixture")).payload, { job: 1 });
  assert.equal(calls, 2);
  calls = 0;
  await assert.rejects(requestJson("http://fixture", { method: "POST" }), { uncertain: true, status: 503 });
  assert.equal(calls, 1);
});

test("timeout aborts body transport and preserves uncertain write status", async () => {
  globalThis.fetch = async (_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(signal.reason)));
  await assert.rejects(requestJson("http://fixture", { method: "POST", timeoutMs: 10 }), { code: "request_timeout", uncertain: true });
});

test("caller cancellation never retries and superseded reads are aborted", async () => {
  const scopes = new RequestScopes();
  const first = scopes.start("job");
  const second = scopes.start("job");
  assert.equal(first.aborted, true);
  assert.equal(second.aborted, false);
  scopes.cancelAll();
  await assert.rejects(requestJson("http://fixture", { signal: second }), { name: "AbortError" });
});

test("Retry-After supports seconds and HTTP dates; invalid JSON is not an empty snapshot", async () => {
  assert.equal(retryDelay("2"), 2000);
  assert.equal(retryDelay("Thu, 01 Jan 1970 00:00:05 GMT", 1000), 4000);
  globalThis.fetch = async () => new Response("<html>proxy unavailable</html>");
  await assert.rejects(requestJson("http://fixture", { retries: 0 }), { code: "invalid_response" });
});

import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

describe("control plane readiness", () => {
  it("reports D1 and seeds the configured admin", async () => {
    const health = await SELF.fetch("https://worker.example/healthz");

    expect(health.status).toBe(200);
    await expect(health.json()).resolves.toEqual({
      status: "ready",
      service: "wukong-control-plane",
      stateBackend: "d1",
      release: "a".repeat(40)
    });

    const admin = await (env as unknown as Env).DB.prepare(
      "SELECT access_status, role, unlimited, configured_admin FROM wukong_telegram_users WHERE subject = ?"
    ).bind("1678823419").first();
    expect(admin).toEqual({
      access_status: "approved",
      role: "admin",
      unlimited: 1,
      configured_admin: 1
    });
  });

  it("exposes the compact readiness contract", async () => {
    const readiness = await SELF.fetch("https://worker.example/readyz");
    expect(readiness.status).toBe(200);
    await expect(readiness.json()).resolves.toEqual({ status: "ready" });
  });
});

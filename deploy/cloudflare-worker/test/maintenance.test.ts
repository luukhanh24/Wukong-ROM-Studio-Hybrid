import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";

describe("system maintenance mode", () => {
  it("locks approved users out while the configured admin keeps access", async () => {
    const adminHeaders = await tmaHeaders(1678823419, { username: "owner" });
    const userHeaders = await tmaHeaders(77011, { username: "approved_user" });

    await SELF.fetch("https://worker.example/v1/session/open", {
      method: "POST",
      headers: userHeaders
    });
    const approved = await SELF.fetch(
      "https://worker.example/v1/admin/users/77011/approve",
      {
        method: "POST",
        headers: {
          ...adminHeaders,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ reason: "Maintenance test" })
      }
    );
    expect(approved.status).toBe(200);

    const enabled = await SELF.fetch("https://worker.example/v1/system/maintenance", {
      method: "PUT",
      headers: {
        ...adminHeaders,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        enabled: true,
        message: "Đang nâng cấp hệ thống build ROM."
      })
    });
    expect(enabled.status).toBe(200);
    await expect(enabled.json()).resolves.toMatchObject({
      maintenance: {
        enabled: true,
        message: "Đang nâng cấp hệ thống build ROM.",
        updatedBy: "1678823419"
      }
    });

    const opened = await SELF.fetch("https://worker.example/v1/session/open", {
      method: "POST",
      headers: userHeaders
    });
    expect(opened.status).toBe(200);
    await expect(opened.json()).resolves.toMatchObject({
      user: { telegramId: "77011", accessStatus: "approved" },
      maintenance: {
        enabled: true,
        message: "Đang nâng cấp hệ thống build ROM."
      }
    });

    const denied = await SELF.fetch("https://worker.example/v1/sync", {
      headers: userHeaders
    });
    expect(denied.status).toBe(503);
    await expect(denied.json()).resolves.toMatchObject({
      code: "maintenance_mode",
      maintenance: {
        enabled: true,
        message: "Đang nâng cấp hệ thống build ROM."
      }
    });

    const adminSync = await SELF.fetch("https://worker.example/v1/sync", {
      headers: adminHeaders
    });
    expect(adminSync.status).toBe(200);

    const disabled = await SELF.fetch("https://worker.example/v1/system/maintenance", {
      method: "PUT",
      headers: {
        ...adminHeaders,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ enabled: false })
    });
    expect(disabled.status).toBe(200);

    const restored = await SELF.fetch("https://worker.example/v1/sync", {
      headers: userHeaders
    });
    expect(restored.status).toBe(200);
  });

  it("does not allow a normal user to change maintenance state", async () => {
    const userHeaders = await tmaHeaders(77012);
    const response = await SELF.fetch("https://worker.example/v1/system/maintenance", {
      method: "PUT",
      headers: {
        ...userHeaders,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ enabled: true })
    });

    expect(response.status).toBe(403);
  });
});

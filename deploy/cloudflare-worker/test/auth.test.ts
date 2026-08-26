import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";

describe("Telegram Mini App authentication", () => {
  it("records a pending user and limits them to their profile", async () => {
    const headers = await tmaHeaders(77001, {
      last_name: "Pending",
      username: "pending_user",
      photo_url: "https://cdn.example/pending.jpg"
    });
    const opened = await SELF.fetch("https://worker.example/v1/session/open", {
      method: "POST",
      headers
    });

    expect(opened.status).toBe(200);
    await expect(opened.json()).resolves.toMatchObject({
      user: {
        telegramId: "77001",
        accessStatus: "pending",
        role: "user",
        displayName: "Fixture Pending",
        username: "pending_user",
        photoUrl: "https://cdn.example/pending.jpg",
        miniAppOpenCount: 1,
        buildCredits: 0,
        unlimited: false
      }
    });

    const denied = await SELF.fetch("https://worker.example/v1/jobs", { headers });
    expect(denied.status).toBe(403);
    await expect(denied.json()).resolves.toMatchObject({ code: "access_pending" });
  });

  it("keeps the configured admin approved and unlimited without manual approval", async () => {
    const headers = await tmaHeaders(1678823419, { username: "owner" });
    const me = await SELF.fetch("https://worker.example/v1/me", { headers });

    expect(me.status).toBe(200);
    await expect(me.json()).resolves.toMatchObject({
      user: {
        telegramId: "1678823419",
        username: "owner",
        accessStatus: "approved",
        role: "admin",
        unlimited: true,
        configuredAdmin: true
      }
    });
  });

  it("rejects an untrusted origin before checking credentials", async () => {
    const response = await SELF.fetch("https://worker.example/v1/me", {
      headers: {
        Origin: "https://evil.example",
        Authorization: "tma invalid"
      }
    });
    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({
      error: "This Mini App origin is not allowed"
    });
  });
});

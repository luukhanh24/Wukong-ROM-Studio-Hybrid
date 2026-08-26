import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";

describe("admin user management", () => {
  it("shows complete user identity, approves access, and updates Build Allowance", async () => {
    const pendingHeaders = await tmaHeaders(88001, {
      username: "rom_user",
      first_name: "ROM",
      last_name: "User",
      photo_url: "https://cdn.example/avatar.jpg"
    });
    await SELF.fetch("https://worker.example/v1/session/open", {
      method: "POST",
      headers: pendingHeaders
    });
    const adminHeaders = {
      ...(await tmaHeaders(1678823419)),
      "Content-Type": "application/json"
    };
    const listed = await SELF.fetch(
      "https://worker.example/v1/admin/users?query=rom_user&status=pending",
      { headers: adminHeaders }
    );
    expect(listed.status).toBe(200);
    await expect(listed.json()).resolves.toMatchObject({
      total: 1,
      users: [{
        telegramId: "88001",
        username: "rom_user",
        displayName: "ROM User",
        photoUrl: "https://cdn.example/avatar.jpg",
        accessStatus: "pending"
      }]
    });

    const approved = await SELF.fetch(
      "https://worker.example/v1/admin/users/88001/approve",
      {
        method: "POST",
        headers: adminHeaders,
        body: JSON.stringify({ reason: "Approved for ROM testing" })
      }
    );
    expect(approved.status).toBe(200);
    await expect(approved.json()).resolves.toMatchObject({
      user: { accessStatus: "approved", buildCredits: 1 }
    });

    const allowance = await SELF.fetch(
      "https://worker.example/v1/admin/users/88001/allowance",
      {
        method: "POST",
        headers: adminHeaders,
        body: JSON.stringify({ operation: "add", value: 3, reason: "Test batch" })
      }
    );
    await expect(allowance.json()).resolves.toMatchObject({
      user: { buildCredits: 4, lifetimeGranted: 4 }
    });

    const me = await SELF.fetch("https://worker.example/v1/me", { headers: pendingHeaders });
    await expect(me.json()).resolves.toMatchObject({
      user: { accessStatus: "approved", buildCredits: 4 }
    });
  });

  it("does not allow the configured admin to be revoked", async () => {
    const response = await SELF.fetch(
      "https://worker.example/v1/admin/users/1678823419/revoke",
      {
        method: "POST",
        headers: {
          ...(await tmaHeaders(1678823419)),
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ reason: "should fail" })
      }
    );
    expect(response.status).toBe(409);
  });

  it("paginates the access audit with an opaque cursor and no duplicate events", async () => {
    const subject = "88002";
    const pendingHeaders = await tmaHeaders(Number(subject), {
      username: "audit_user",
      first_name: "Audit",
      last_name: "User"
    });
    for (let index = 0; index < 105; index += 1) {
      await SELF.fetch("https://worker.example/v1/session/open", {
        method: "POST",
        headers: {
          ...pendingHeaders,
          "X-Wukong-Session-Id": `audit-page-${index}`
        }
      });
    }
    const adminHeaders = await tmaHeaders(1678823419);
    const detail = await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}`,
      { headers: adminHeaders }
    );
    const firstPage = await detail.json() as {
      events: Array<{ eventId: string; telegramId: string }>;
      eventsHasMore: boolean;
      eventsNextCursor: string;
    };
    expect(firstPage.events).toHaveLength(100);
    expect(firstPage.eventsHasMore).toBe(true);
    expect(firstPage.eventsNextCursor).not.toBe("");
    expect(firstPage.events.every((event) => event.telegramId === subject)).toBe(true);

    const next = await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}/events?cursor=${encodeURIComponent(firstPage.eventsNextCursor)}&limit=100`,
      { headers: adminHeaders }
    );
    const secondPage = await next.json() as {
      events: Array<{ eventId: string }>;
      hasMore: boolean;
      nextCursor: string;
    };
    expect(secondPage.events.length).toBeGreaterThan(0);
    expect(secondPage.hasMore).toBe(false);
    expect(secondPage.nextCursor).toBe("");
    expect(
      secondPage.events.some((event) =>
        firstPage.events.some((first) => first.eventId === event.eventId)
      )
    ).toBe(false);

    const invalid = await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}/events?cursor=not-a-cursor`,
      { headers: adminHeaders }
    );
    expect(invalid.status).toBe(400);
  });
});

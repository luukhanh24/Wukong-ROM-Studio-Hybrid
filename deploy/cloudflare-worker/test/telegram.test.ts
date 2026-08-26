import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { drainTelegramOutbox } from "../src/telegram";

describe("Telegram webhook and pairing", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a waiting message, confirms pairing, and deduplicates the update", async () => {
    const sent: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("https://api.telegram.org/bot");
      sent.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return Response.json({ ok: true, result: { message_id: 1 } });
    }));
    const pair = await SELF.fetch("https://worker.example/v1/session/pair", {
      method: "POST",
      headers: { Origin: "https://wukong-rom-studio.vercel.app" }
    });
    const pairing = await pair.json() as { pairId: string; pairSecret: string };
    const update = {
      update_id: 912345,
      message: {
        message_id: 1,
        chat: { id: 99001 },
        from: {
          id: 99001,
          first_name: "Pending",
          username: "pending_99001",
          language_code: "vi"
        },
        text: `/start pair_${pairing.pairId}`
      }
    };
    const webhook = () => SELF.fetch("https://worker.example/telegram/webhook", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": "fixture-webhook-secret"
      },
      body: JSON.stringify(update)
    });
    expect((await webhook()).status).toBe(204);
    expect((await webhook()).status).toBe(204);
    expect(sent).toHaveLength(1);
    expect(String(sent[0]?.text)).toContain("Chờ quản trị viên cấp quyền");
    expect(String(sent[0]?.text)).not.toContain("1678823419");

    const status = await SELF.fetch("https://worker.example/v1/session/pair/status", {
      method: "POST",
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(pairing)
    });
    expect(status.status).toBe(200);
    const confirmed = await status.json() as { launchToken: string };
    const me = await SELF.fetch("https://worker.example/v1/me", {
      headers: {
        Origin: "https://wukong-rom-studio.vercel.app",
        Authorization: `wla ${confirmed.launchToken}`
      }
    });
    await expect(me.json()).resolves.toMatchObject({
      user: { telegramId: "99001", accessStatus: "pending" }
    });
  });

  it("reclaims an expired sending lease instead of losing the notification", async () => {
    const sent: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return Response.json({ ok: true, result: { message_id: 2 } });
    }));
    const old = new Date(Date.now() - 60_000).toISOString();
    await env.DB.prepare(
      `INSERT INTO wukong_telegram_notification_outbox
       (notification_id, dedupe_key, chat_id, payload_json, state, attempts, available_at, created_at)
       VALUES (?, ?, ?, ?, 'sending', 1, ?, ?)`
    ).bind(
      "stale-notification",
      "stale-notification-dedupe",
      "99002",
      JSON.stringify({ text: "Recovered" }),
      old,
      old
    ).run();

    await drainTelegramOutbox(env as unknown as Env, 10);

    const row = await env.DB.prepare(
      "SELECT state, attempts, sent_at FROM wukong_telegram_notification_outbox WHERE notification_id = ?"
    ).bind("stale-notification").first<Record<string, unknown>>();
    expect(row).toMatchObject({ state: "sent", attempts: 2 });
    expect(String(row?.sent_at)).not.toBe("");
    expect(sent).toEqual([{ chat_id: "99002", text: "Recovered" }]);
  });
});

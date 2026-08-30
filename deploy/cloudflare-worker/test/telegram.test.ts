import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { drainTelegramOutbox } from "../src/telegram";
import { tmaHeaders } from "./helpers";

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
    expect(sent).toHaveLength(2);
    const userMessage = sent.find((payload) => payload.chat_id === "99001");
    const adminMessage = sent.find((payload) => payload.chat_id === "1678823419");
    expect(String(userMessage?.text)).toContain("Chờ quản trị viên cấp quyền");
    expect(String(userMessage?.text)).not.toContain("1678823419");
    expect(String(adminMessage?.text)).toContain("YÊU CẦU CẤP QUYỀN MỚI");
    expect(String(adminMessage?.text)).toContain("<code>/approve 99001</code>");

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

  it("restores the approved-user menu, account command, Mini App build launcher, and language callbacks", async () => {
    const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({
        method: String(input).split("/").at(-1) ?? "",
        payload: JSON.parse(String(init?.body)) as Record<string, unknown>
      });
      return Response.json({ ok: true, result: { message_id: calls.length } });
    }));
    const webhook = (update: Record<string, unknown>) => SELF.fetch(
      "https://worker.example/telegram/webhook",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": "fixture-webhook-secret"
        },
        body: JSON.stringify(update)
      }
    );
    const from = { id: 1678823419, first_name: "Admin", username: "wukong_admin", language_code: "vi" };
    expect((await webhook({
      update_id: 912346,
      message: { message_id: 2, chat: { id: 1678823419 }, from, text: "/start" }
    })).status).toBe(204);
    expect(String(calls[0]?.payload.text)).toContain("Wukong ROM Studio");
    expect(
      (calls[0]?.payload.reply_markup as {
        inline_keyboard: Array<Array<Record<string, unknown>>>;
      }).inline_keyboard[0]
    ).toEqual([
      { text: "Mở Wukong Mini App", web_app: { url: "https://wukong-rom-studio.vercel.app/" } }
    ]);
    const menuButtons = (
      calls[0]?.payload.reply_markup as {
        inline_keyboard: Array<Array<Record<string, unknown>>>;
      }
    ).inline_keyboard.flat();
    expect(menuButtons).not.toContainEqual(expect.objectContaining({ callback_data: "v1:cloud" }));
    expect(menuButtons.map((button) => String(button.text))).not.toContain("☁️ Thư viện cloud");
    expect(menuButtons.map((button) => String(button.text))).not.toContain("☁️ Cloud library");

    expect((await webhook({
      update_id: 912347,
      message: { message_id: 3, chat: { id: 1678823419 }, from, text: "/account" }
    })).status).toBe(204);
    expect(String(calls[1]?.payload.text)).toContain("Telegram ID  <code>1678823419</code>");
    expect(String(calls[1]?.payload.text)).toContain("Lượt build  <b>Không giới hạn</b>");

    expect((await webhook({
      update_id: 912348,
      message: { message_id: 4, chat: { id: 1678823419 }, from, text: "/new" }
    })).status).toBe(204);
    expect(String(calls[2]?.payload.text)).toContain("Mini App");
    expect(String(calls[2]?.payload.text)).not.toContain("recipe JSON");

    expect((await webhook({
      update_id: 912349,
      callback_query: {
        id: "callback-language",
        from,
        data: "v1:lang:en",
        message: { message_id: 5, chat: { id: 1678823419 } }
      }
    })).status).toBe(204);
    expect(calls.some((call) =>
      call.method === "answerCallbackQuery"
      && call.payload.callback_query_id === "callback-language"
    )).toBe(true);
    expect(calls.some((call) => String(call.payload.text).includes("Choose a feature below"))).toBe(true);
  });

  it("restores job callbacks and exposes only a direct cloud artifact link", async () => {
    const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({
        method: String(input).split("/").at(-1) ?? "",
        payload: JSON.parse(String(init?.body)) as Record<string, unknown>
      });
      return Response.json({ ok: true, result: { message_id: calls.length } });
    }));
    const jobId = "telegram-parity-job";
    const now = new Date().toISOString();
    await env.DB.prepare(
      `INSERT INTO wukong_jobs
       (job_id, manifest_json, recipe_json, created_at, updated_at, finished_at,
        next_event_sequence, owner_channel, owner_subject, device, status, stage, progress)
       VALUES (?, ?, ?, ?, ?, ?, 3, 'telegram', '1678823419', 'PJD110',
               'succeeded', 'complete', 1)`
    ).bind(
      jobId,
      JSON.stringify({
        job_id: jobId,
        status: "succeeded",
        stage: "complete",
        progress: 1,
        artifacts: [{
          name: "Wukong_Plus.zip",
          sha256: "b".repeat(64),
          size_bytes: 4096,
          public_url: "https://drive.google.com/file/d/direct/view"
        }]
      }),
      JSON.stringify({
        schemaVersion: 1,
        task: "build",
        device: "PJD110",
        source: { kind: "https", uri: "https://downloads.example/rom.zip" },
        build: { preset: "plus", modVersion: "ColorOS_16.0.10" },
        execution: { target: "github-auto" }
      }),
      now,
      now,
      now
    ).run();
    await env.DB.prepare(
      `INSERT INTO wukong_telegram_ui_state (subject, language, updated_at)
       VALUES ('1678823419', 'vi', ?)
       ON CONFLICT (subject) DO UPDATE SET language = 'vi', updated_at = excluded.updated_at`
    ).bind(now).run();
    const from = { id: 1678823419, first_name: "Admin", language_code: "vi" };
    const response = await SELF.fetch("https://worker.example/telegram/webhook", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": "fixture-webhook-secret"
      },
      body: JSON.stringify({
        update_id: 912350,
        callback_query: {
          id: "callback-artifact",
          from,
          data: `v1:artifact:${jobId}`,
          message: { message_id: 6, chat: { id: 1678823419 } }
        }
      })
    });
    expect(response.status).toBe(204);
    const message = calls.find((call) => call.method === "sendMessage");
    expect(String(message?.payload.text)).toContain("Link Drive/cloud trực tiếp");
    const keyboard = (message?.payload.reply_markup as {
      inline_keyboard: Array<Array<Record<string, unknown>>>;
    }).inline_keyboard;
    expect(keyboard.flat()).toContainEqual({
      text: "Tải artifact",
      url: "https://drive.google.com/file/d/direct/view"
    });
    expect(JSON.stringify(message?.payload)).not.toContain("workers.dev");
    expect(JSON.stringify(message?.payload)).not.toContain("onrender.com");
  });

  it("does not expose the private GitHub repository in bot or API diagnostics", async () => {
    const calls: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return Response.json({ ok: true, result: { message_id: calls.length } });
    }));
    await env.DB.prepare(
      `INSERT INTO wukong_telegram_ui_state (subject, language, updated_at)
       VALUES ('1678823419', 'vi', ?)
       ON CONFLICT (subject) DO UPDATE SET language = 'vi', updated_at = excluded.updated_at`
    ).bind(new Date().toISOString()).run();
    const webhook = await SELF.fetch("https://worker.example/telegram/webhook", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": "fixture-webhook-secret"
      },
      body: JSON.stringify({
        update_id: 912351,
        callback_query: {
          id: "callback-diagnostics",
          from: { id: 1678823419, first_name: "Admin", language_code: "vi" },
          data: "v1:diag",
          message: { message_id: 7, chat: { id: 1678823419 } }
        }
      })
    });
    expect(webhook.status).toBe(204);
    const botMessage = calls.find((payload) => typeof payload.text === "string");
    expect(String(botMessage?.text)).toContain("Runner  <code>GitHub Actions</code>");
    expect(String(botMessage?.text)).not.toContain("fixture-owner");
    expect(String(botMessage?.text)).not.toContain("Wukong-ROM-Studio-Hybrid");

    const api = await SELF.fetch("https://worker.example/v1/diagnostics", {
      headers: await tmaHeaders(1678823419)
    });
    expect(api.status).toBe(200);
    const diagnostics = await api.json() as Record<string, unknown>;
    expect(diagnostics.runner).toEqual({ provider: "github-actions" });
    expect(JSON.stringify(diagnostics)).not.toContain("fixture-owner");
    expect(JSON.stringify(diagnostics)).not.toContain("Wukong-ROM-Studio-Hybrid");
  });

  it("answers the cloud callback with a visible error when Drive authorization expires", async () => {
    const calls: Array<{ url: string; payload: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "https://oauth2.googleapis.com/token") {
        return Response.json(
          { error: "invalid_grant", error_description: "Token has been expired or revoked." },
          { status: 400 }
        );
      }
      calls.push({
        url,
        payload: JSON.parse(String(init?.body)) as Record<string, unknown>
      });
      return Response.json({ ok: true, result: { message_id: calls.length } });
    }));
    const response = await SELF.fetch("https://worker.example/telegram/webhook", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": "fixture-webhook-secret"
      },
      body: JSON.stringify({
        update_id: 912352,
        callback_query: {
          id: "callback-cloud-expired",
          from: { id: 1678823419, first_name: "Admin", language_code: "vi" },
          data: "v1:cloud",
          message: { message_id: 8, chat: { id: 1678823419 } }
        }
      })
    });
    expect(response.status).toBe(204);
    expect(calls.some((call) =>
      call.url.endsWith("/answerCallbackQuery")
      && call.payload.callback_query_id === "callback-cloud-expired"
    )).toBe(true);
    expect(calls.some((call) =>
      call.url.endsWith("/sendMessage")
      && String(call.payload.text).includes("Google Drive")
      && String(call.payload.text).includes("xác thực")
    )).toBe(true);
  });
});

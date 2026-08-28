import { env, SELF } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { actionsHeaders, tmaHeaders } from "./helpers";
import { createJob } from "../src/jobs";
import { profile } from "../src/state";

const bindings = env as unknown as Env;

async function seedApprovedUser(subject: string): Promise<void> {
  const now = new Date().toISOString();
  await bindings.DB.batch([
    bindings.DB.prepare(
      `INSERT INTO wukong_telegram_users
       (subject, access_status, role, first_seen_at, last_seen_at, build_credits, lifetime_granted)
       VALUES (?, 'approved', 'user', ?, ?, 5, 5)
       ON CONFLICT (subject) DO UPDATE SET access_status = 'approved', build_credits = 5`
    ).bind(subject, now, now),
    bindings.DB.prepare(
      `INSERT INTO wukong_telegram_access (subject, role) VALUES (?, 'user')
       ON CONFLICT (subject) DO UPDATE SET role = 'user'`
    ).bind(subject)
  ]);
}

describe("admin user activity telemetry", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a user's live build configuration and queues one private admin alert", async () => {
    const subject = "78101";
    await seedApprovedUser(subject);
    const recipe = {
      schemaVersion: 1,
      task: "build",
      device: "PKG110",
      source: {
        kind: "https",
        uri: "https://downloads.example/private-rom.zip?Signature=private",
        metadata: { productName: "PKG110", device: "OP5D2BL1", version: "PKG110_16.0.10.500(CN01)" }
      },
      execution: { target: "github-auto" },
      build: {
        preset: "custom",
        modVersion: "ColorOS_16.0.10",
        modReleaseVersion: "V6.0",
        mods: ["WK_Manager"],
        notifyTelegram: true
      },
      storage: { publishArtifact: true }
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers: {
        ...await tmaHeaders(Number(subject), { first_name: "Build User", username: "build_user" }),
        "Content-Type": "application/json",
        "Idempotency-Key": "activity-build"
      },
      body: JSON.stringify(recipe)
    });
    expect(created.status).toBe(201);
    const job = await created.json() as { job_id: string };
    await bindings.DB.prepare(
      "DELETE FROM wukong_telegram_notification_outbox WHERE dedupe_key = ?"
    ).bind(`admin-activity:build:${job.job_id}:1678823419`).run();
    expect((await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers: {
        ...await tmaHeaders(Number(subject), { first_name: "Build User", username: "build_user" }),
        "Content-Type": "application/json",
        "Idempotency-Key": "activity-build"
      },
      body: JSON.stringify(recipe)
    })).status).toBe(200);

    const users = await (await SELF.fetch(
      `https://worker.example/v1/admin/users?query=${subject}`,
      { headers: await tmaHeaders(1678823419) }
    )).json() as any;
    expect(users.users[0].currentActivity).toMatchObject({
      type: "build",
      status: "queued",
      jobId: job.job_id,
      deviceName: "OnePlus Ace 5",
      productCode: "PKG110",
      preset: "custom",
      modVersion: "ColorOS_16.0.10",
      releaseVersion: "V6.0"
    });
    expect(users.users[0].currentActivities).toHaveLength(1);

    const searchStartedAt = new Date().toISOString();
    await bindings.DB.prepare(
      `INSERT INTO wukong_telegram_user_events
       (event_id, subject, event_type, details_json, created_at)
       VALUES (?, ?, 'rom_search_started', ?, ?)`
    ).bind(
      crypto.randomUUID(),
      subject,
      JSON.stringify({ device: "OP 13", region: "EU", latest: true, startedAt: searchStartedAt }),
      searchStartedAt
    ).run();
    const concurrent = await (await SELF.fetch(
      `https://worker.example/v1/admin/users?query=${subject}`,
      { headers: await tmaHeaders(1678823419) }
    )).json() as any;
    expect(concurrent.users[0].currentActivities.map((activity: any) => activity.type)).toEqual([
      "build",
      "rom_search"
    ]);

    const rows = await bindings.DB.prepare(
      `SELECT payload_json FROM wukong_telegram_notification_outbox
       WHERE dedupe_key = ?`
    ).bind(`admin-activity:build:${job.job_id}:1678823419`).all<{ payload_json: string }>();
    expect(rows.results).toHaveLength(1);
    const alert = JSON.parse(rows.results[0]!.payload_json) as { text: string };
    expect(alert.text).toContain("Build User");
    expect(alert.text).toContain("<code>PKG110</code>");
    expect(alert.text).toContain("<code>custom</code>");
    expect(alert.text).toContain("<code>V6.0</code>");
    expect(alert.text).not.toContain("private-rom.zip");
    expect(alert.text).not.toContain("Signature");
  });

  it("tracks ROM search start/result logs and queues one admin alert without exposing source URLs", async () => {
    const subject = "78102";
    await seedApprovedUser(subject);
    let releaseFetch!: () => void;
    const pending = new Promise<void>((resolve) => { releaseFetch = resolve; });
    vi.stubGlobal("fetch", vi.fn(async () => {
      await pending;
      return Response.json({ releases: [{
        id: "activity-rom",
        device: "OP 13",
        model: "CPH2653",
        region: "EU",
        version: "CPH2653_16.0.10.500(EX01)",
        source_url: "https://component-ota.example/downloadCheck?secret=hidden"
      }] });
    }));
    const headers = await tmaHeaders(Number(subject), {
      first_name: "ROM Hunter",
      username: "rom_hunter"
    });
    const search = SELF.fetch(
      "https://worker.example/v1/rom-catalog?device=OP+13&region=EU&latest=1",
      { headers }
    );

    await vi.waitFor(async () => {
      const users = await (await SELF.fetch(
        `https://worker.example/v1/admin/users?query=${subject}`,
        { headers: await tmaHeaders(1678823419) }
      )).json() as any;
      expect(users.users[0].currentActivity).toMatchObject({
        type: "rom_search",
        status: "searching",
        device: "OP 13",
        region: "EU",
        latest: true
      });
    });

    releaseFetch();
    const searchResponse = await search;
    expect(searchResponse.status, await searchResponse.clone().text()).toBe(200);
    const repeated = await SELF.fetch(
      "https://worker.example/v1/rom-catalog?device=OP+13&region=EU&latest=1",
      { headers }
    );
    expect(repeated.status).toBe(200);

    const detail = await (await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}`,
      { headers: await tmaHeaders(1678823419) }
    )).json() as any;
    expect(detail.user.currentActivity).toMatchObject({
      type: "rom_search",
      status: "completed",
      device: "OP 13",
      region: "EU",
      resultCount: 1
    });
    expect(detail.user.currentActivities).toHaveLength(1);
    expect(detail.events.slice(0, 2).map((event: any) => event.type)).toEqual([
      "rom_search_completed",
      "rom_search_started"
    ]);
    const delta = await (await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}/activity?afterCreatedAt=${encodeURIComponent("1970-01-01T00:00:00.000Z")}`,
      { headers: await tmaHeaders(1678823419) }
    )).json() as any;
    expect(delta.user.currentActivity).toMatchObject({ type: "rom_search", status: "completed" });
    expect(delta.events.map((event: any) => event.type)).toEqual([
      "rom_search_started",
      "rom_search_completed"
    ]);
    expect(delta.jobs).toBeUndefined();
    expect(detail.events[0].details).toMatchObject({
      device: "OP 13",
      region: "EU",
      resultCount: 1
    });
    const serializedEvents = JSON.stringify(detail.events);
    expect(serializedEvents).not.toContain("downloadCheck");
    expect(serializedEvents).not.toContain("secret");

    const rows = await bindings.DB.prepare(
      `SELECT payload_json FROM wukong_telegram_notification_outbox
       WHERE chat_id = '1678823419'`
    ).all<{ payload_json: string }>();
    const alerts = rows.results
      .map((row) => JSON.parse(row.payload_json) as { text: string })
      .filter((alert) => alert.text.includes(subject));
    expect(alerts).toHaveLength(1);
    expect(alerts[0]!.text).toContain("ROM Hunter");
    expect(alerts[0]!.text).toContain("<code>OP 13</code>");
    expect(alerts[0]!.text).toContain("<code>EU</code>");
    expect(alerts[0]!.text).not.toContain("downloadCheck");
  });

  it("loads a full 100-user admin page without exceeding D1 parameter limits", async () => {
    const now = new Date().toISOString();
    const statements = Array.from({ length: 100 }, (_, index) => bindings.DB.prepare(
      `INSERT INTO wukong_telegram_users
       (subject, access_status, role, first_seen_at, last_seen_at)
       VALUES (?, 'approved', 'user', ?, ?)
       ON CONFLICT (subject) DO NOTHING`
    ).bind(String(79000 + index), now, now));
    await bindings.DB.batch(statements);
    const response = await SELF.fetch(
      "https://worker.example/v1/admin/users?limit=100",
      { headers: await tmaHeaders(1678823419) }
    );
    expect(response.status, await response.clone().text()).toBe(200);
    const payload = await response.json() as any;
    expect(payload.users).toHaveLength(100);
    expect(payload.users.every((user: any) => Array.isArray(user.currentActivities))).toBe(true);
  });

  it("pages activity deltas oldest-first without skipping overflow events", async () => {
    const subject = "78107";
    await seedApprovedUser(subject);
    const base = Date.now() - 60_000;
    await bindings.DB.batch(Array.from({ length: 55 }, (_, index) => bindings.DB.prepare(
      `INSERT INTO wukong_telegram_user_events
       (event_id, subject, event_type, details_json, created_at)
       VALUES (?, ?, 'fixture_activity', '{}', ?)`
    ).bind(
      `delta-${String(index).padStart(3, "0")}`,
      subject,
      new Date(base + index).toISOString()
    )));
    const headers = await tmaHeaders(1678823419);
    const first = await (await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}/activity?afterCreatedAt=${encodeURIComponent("1970-01-01T00:00:00.000Z")}`,
      { headers }
    )).json() as any;
    expect(first.events).toHaveLength(50);
    expect(first.hasMore).toBe(true);
    expect(first.events[0].eventId).toBe("delta-000");
    const consumed = first.events.at(-1);
    const secondQuery = new URLSearchParams({
      afterCreatedAt: consumed.createdAt,
      afterEventId: consumed.eventId
    });
    const second = await (await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}/activity?${secondQuery}`,
      { headers }
    )).json() as any;
    expect(second.events).toHaveLength(5);
    expect(second.hasMore).toBe(false);
    expect(second.events.at(-1).eventId).toBe("delta-054");
  });

  it("rejects invalid catalog filters without creating activity or admin spam", async () => {
    const subject = "78105";
    await seedApprovedUser(subject);
    const response = await SELF.fetch(
      "https://worker.example/v1/rom-catalog?latest=1",
      { headers: await tmaHeaders(Number(subject)) }
    );
    expect(response.status).toBe(400);
    const events = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_telegram_user_events
       WHERE subject = ? AND event_type LIKE 'rom_search_%'`
    ).bind(subject).first<{ count: number }>();
    const alerts = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_telegram_notification_outbox
       WHERE payload_json LIKE ?`
    ).bind(`%${subject}%`).first<{ count: number }>();
    expect(Number(events?.count ?? 0)).toBe(0);
    expect(Number(alerts?.count ?? 0)).toBe(0);
  });

  it("stores a safe ROM-search failure without signed URLs or credentials", async () => {
    const subject = "78104";
    await seedApprovedUser(subject);
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("upstream https://cdn.example/rom.zip?Signature=private&AWSAccessKeyId=secret failed");
    }));
    const response = await SELF.fetch(
      "https://worker.example/v1/rom-catalog?device=Privacy+Failure+78104&region=EU&latest=1",
      { headers: await tmaHeaders(Number(subject)) }
    );
    expect(response.status).toBe(503);
    const detail = await (await SELF.fetch(
      `https://worker.example/v1/admin/users/${subject}`,
      { headers: await tmaHeaders(1678823419) }
    )).json() as any;
    const failure = detail.events.find((event: any) => event.type === "rom_search_failed");
    expect(failure.details).toMatchObject({ errorCode: "source_unavailable" });
    const serialized = JSON.stringify(failure);
    expect(serialized).not.toContain("Signature");
    expect(serialized).not.toContain("AWSAccessKeyId");
    expect(serialized).not.toContain("cdn.example");
  });

  it("does not announce a build that GitHub rejects before dispatch", async () => {
    const subject = "78103";
    await seedApprovedUser(subject);
    const actorProfile = await profile(bindings, subject);
    expect(actorProfile).not.toBeNull();
    const dispatchEnv = new Proxy(bindings, {
      get(target, property, receiver) {
        if (property === "WUKONG_DISABLE_EXTERNAL_DISPATCH") return "0";
        return Reflect.get(target, property, receiver);
      }
    }) as Env;
    vi.stubGlobal("fetch", vi.fn(async () => new Response("dispatch rejected", { status: 500 })));
    await expect(createJob(dispatchEnv, {
      subject,
      role: "user",
      profile: actorProfile!
    }, {
      schemaVersion: 1,
      task: "build",
      device: "PKG110",
      source: { kind: "https", uri: "https://downloads.example/rom.zip" },
      execution: { target: "github-auto" },
      build: { preset: "custom", modVersion: "ColorOS_16.0.10", modReleaseVersion: "V6.0" },
      storage: { publishArtifact: true }
    }, "dispatch-rejected")).rejects.toThrow("GitHub Actions dispatch failed");
    const row = await bindings.DB.prepare(
      `SELECT COUNT(*) AS count FROM wukong_telegram_notification_outbox
       WHERE dedupe_key LIKE 'admin-activity:build:%' AND payload_json LIKE ?`
    ).bind(`%${subject}%`).first<{ count: number }>();
    expect(Number(row?.count ?? 0)).toBe(0);
  });

  it("repairs a missing build alert when the accepted Actions run bootstraps", async () => {
    const subject = "78106";
    await seedApprovedUser(subject);
    const recipe = {
      schemaVersion: 1,
      task: "build",
      device: "PKG110",
      source: { kind: "https", uri: "https://downloads.example/rom.zip" },
      execution: { target: "github-auto" },
      build: { preset: "custom", modVersion: "ColorOS_16.0.10", modReleaseVersion: "V6.0" },
      storage: { publishArtifact: true }
    };
    const created = await SELF.fetch("https://worker.example/v1/jobs", {
      method: "POST",
      headers: {
        ...await tmaHeaders(Number(subject), { first_name: "Bootstrap User" }),
        "Content-Type": "application/json",
        "Idempotency-Key": "bootstrap-alert-repair"
      },
      body: JSON.stringify(recipe)
    });
    const job = await created.json() as { job_id: string };
    const dedupeKey = `admin-activity:build:${job.job_id}:1678823419`;
    await bindings.DB.prepare(
      "DELETE FROM wukong_telegram_notification_outbox WHERE dedupe_key = ?"
    ).bind(dedupeKey).run();
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({
      id: 718106,
      event: "workflow_dispatch",
      display_title: `${job.job_id} · Wukong Hybrid`,
      path: ".github/workflows/wukong-build.yml",
      repository: { full_name: "fixture-owner/fixture-repository" }
    })));
    const body = JSON.stringify({ jobId: job.job_id, runId: 718106 });
    const bootstrapped = await SELF.fetch("https://worker.example/internal/actions/bootstrap", {
      method: "POST",
      headers: {
        ...await actionsHeaders(body),
        Authorization: `Bearer ${"g".repeat(40)}`
      },
      body
    });
    expect(bootstrapped.status, await bootstrapped.clone().text()).toBe(200);
    const repaired = await bindings.DB.prepare(
      "SELECT payload_json FROM wukong_telegram_notification_outbox WHERE dedupe_key = ?"
    ).bind(dedupeKey).first<{ payload_json: string }>();
    expect(repaired?.payload_json).toContain("Bootstrap User");
  });
});

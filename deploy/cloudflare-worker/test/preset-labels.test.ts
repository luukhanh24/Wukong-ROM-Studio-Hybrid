import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { tmaHeaders } from "./helpers";

describe("preset labels", () => {
  it("lets the admin persist labels while users can only read them", async () => {
    const admin = await tmaHeaders(1678823419);
    const initial = await SELF.fetch("https://worker.example/v1/preset-labels", { headers: admin });
    expect(initial.status).toBe(200);
    expect(await initial.json()).toMatchObject({
      editable: true,
      presetLabels: { lite: "Lite", plus: "Plus", custom: "Custom" }
    });

    const saved = await SELF.fetch("https://worker.example/v1/preset-labels", {
      method: "PUT",
      headers: admin,
      body: JSON.stringify({ presetLabels: { lite: "Essential", plus: "Complete", custom: "Studio" } })
    });
    expect(saved.status).toBe(200);
    expect(await saved.json()).toMatchObject({
      presetLabels: { lite: "Essential", plus: "Complete", custom: "Studio" }
    });

    const db = (env as unknown as Env).DB;
    const now = new Date().toISOString();
    await db.batch([
      db.prepare("INSERT OR REPLACE INTO wukong_telegram_users (subject,username,display_name,first_seen_at,last_seen_at,access_status,role) VALUES ('78003','','Fixture',?,?, 'approved','user')").bind(now, now),
      db.prepare("INSERT OR REPLACE INTO wukong_telegram_access (subject,role) VALUES ('78003','user')")
    ]);
    const user = await SELF.fetch("https://worker.example/v1/preset-labels", { headers: await tmaHeaders(78003) });
    expect(user.status).toBe(200);
    expect(await user.json()).toMatchObject({ editable: false, presetLabels: { lite: "Essential", plus: "Complete", custom: "Studio" } });

    const denied = await SELF.fetch("https://worker.example/v1/preset-labels", {
      method: "PUT",
      headers: await tmaHeaders(78003),
      body: JSON.stringify({ presetLabels: { lite: "Nope" } })
    });
    expect(denied.status).toBe(403);
  });

  it("rejects unsafe labels", async () => {
    const response = await SELF.fetch("https://worker.example/v1/preset-labels", {
      method: "PUT",
      headers: await tmaHeaders(1678823419),
      body: JSON.stringify({ presetLabels: { plus: "Build:Pro" } })
    });
    expect(response.status).toBe(400);
  });
});

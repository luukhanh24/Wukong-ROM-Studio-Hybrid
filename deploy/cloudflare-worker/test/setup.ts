import { applyD1Migrations, env } from "cloudflare:test";
import { beforeAll } from "vitest";

beforeAll(async () => {
  const bindings = env as unknown as Env;
  await applyD1Migrations(bindings.DB, bindings.TEST_MIGRATIONS ?? []);
});

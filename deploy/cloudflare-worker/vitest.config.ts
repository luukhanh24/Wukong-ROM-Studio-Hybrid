import path from "node:path";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig(async () => {
  const migrations = await readD1Migrations(path.join(import.meta.dirname, "migrations"));
  return {
    plugins: [
      cloudflareTest({
        main: "./src/index.ts",
        miniflare: {
          compatibilityDate: "2026-08-22",
          d1Databases: ["DB"],
          bindings: {
            TEST_MIGRATIONS: migrations,
            WUKONG_RELEASE_SHA: "a".repeat(40),
            WUKONG_ALLOWED_ORIGINS: "https://wukong-rom-studio.vercel.app",
            WUKONG_TELEGRAM_ADMIN_IDS: "1678823419",
            WUKONG_TELEGRAM_BOT_USERNAME: "WK_build_bot",
            WUKONG_TELEGRAM_WEB_APP_URL: "https://wukong-rom-studio.vercel.app/",
            WUKONG_GITHUB_REPOSITORY: "fixture-owner/fixture-repository",
            WUKONG_GITHUB_WORKFLOW: "wukong-build.yml",
            WUKONG_GITHUB_REF: "main",
            WUKONG_GOOGLE_DRIVE_FOLDER_ID: "fixture-root-folder",
            WUKONG_PUBLIC_API_URL: "https://wukong-control-plane.wukong-rom-studio-api.workers.dev",
            WUKONG_SOURCE_TRANSPORT_URL: "https://wukong-rom-studio.vercel.app/api/source-transport",
            WUKONG_TELEGRAM_BOT_TOKEN: "123456789:fixture_bot_secret_value",
            WUKONG_TELEGRAM_WEBHOOK_SECRET: "fixture-webhook-secret",
            WUKONG_ACTIONS_CALLBACK_SECRET: "fixture-actions-callback-secret-value",
            WUKONG_GITHUB_TOKEN: "fixture-worker-github-token-value",
            WUKONG_DISABLE_EXTERNAL_DISPATCH: "1",
            WUKONG_GOOGLE_CLIENT_ID: "fixture-client-id",
            WUKONG_GOOGLE_CLIENT_SECRET: "fixture-client-secret",
            WUKONG_GOOGLE_REFRESH_TOKEN: "fixture-refresh-token"
          }
        }
      })
    ],
    test: {
      include: ["test/**/*.test.ts"],
      setupFiles: ["./test/setup.ts"],
      testTimeout: 10_000
    }
  };
});

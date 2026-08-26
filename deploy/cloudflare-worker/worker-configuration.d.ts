interface Env {
  DB: D1Database;
  TEST_MIGRATIONS?: Array<{ name: string; queries: string[] }>;
  WUKONG_RELEASE_SHA: string;
  WUKONG_ALLOWED_ORIGINS: string;
  WUKONG_TELEGRAM_ADMIN_IDS: string;
  WUKONG_TELEGRAM_BOT_USERNAME: string;
  WUKONG_TELEGRAM_WEB_APP_URL: string;
  WUKONG_GITHUB_REPOSITORY: string;
  WUKONG_GITHUB_WORKFLOW: string;
  WUKONG_GITHUB_REF: string;
  WUKONG_GOOGLE_DRIVE_FOLDER_ID: string;
  WUKONG_SOURCE_TRANSPORT_URL: string;
  WUKONG_TELEGRAM_BOT_TOKEN: string;
  WUKONG_TELEGRAM_WEBHOOK_SECRET: string;
  WUKONG_ACTIONS_CALLBACK_SECRET: string;
  WUKONG_GITHUB_TOKEN: string;
  WUKONG_DISABLE_EXTERNAL_DISPATCH?: string;
  WUKONG_GOOGLE_CLIENT_ID: string;
  WUKONG_GOOGLE_CLIENT_SECRET: string;
  WUKONG_GOOGLE_REFRESH_TOKEN: string;
}

declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    TEST_MIGRATIONS?: Array<{ name: string; queries: string[] }>;
  }
}

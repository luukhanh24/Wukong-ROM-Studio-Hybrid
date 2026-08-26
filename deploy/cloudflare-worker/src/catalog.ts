import catalog from "../../../telegram_mini_app/catalog.json";

type JsonObject = Record<string, unknown>;

const MOD_RELEASE_VERSION = /^[^/\\\u0000-\u001f]{1,64}$/;

export function catalogPayload(): JsonObject {
  return JSON.parse(JSON.stringify(catalog)) as JsonObject;
}

async function storedReleaseVersions(env: Env): Promise<Record<string, string>> {
  const row = await env.DB.prepare(
    "SELECT value FROM wukong_control_plane_metadata WHERE key = 'mod_release_versions'"
  ).first<{ value: string }>();
  if (!row) return {};
  try {
    const parsed = JSON.parse(row.value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, string>
      : {};
  } catch {
    return {};
  }
}

export async function releaseVersions(env: Env): Promise<Record<string, string>> {
  const defaults = (catalog as JsonObject).modReleaseVersions;
  return {
    ...(defaults && typeof defaults === "object" ? defaults as Record<string, string> : {}),
    ...await storedReleaseVersions(env)
  };
}

export async function saveReleaseVersions(
  env: Env,
  value: unknown
): Promise<Record<string, string>> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("modReleaseVersions must be an object");
  }
  const known = new Set(Array.isArray((catalog as JsonObject).modVersions)
    ? (catalog as JsonObject).modVersions as string[]
    : []);
  const normalized: Record<string, string> = {};
  for (const [pack, labelValue] of Object.entries(value as Record<string, unknown>)) {
    const label = String(labelValue ?? "").trim();
    if (!known.has(pack)) throw new Error("Unknown MOD pack in release versions");
    if (!MOD_RELEASE_VERSION.test(label)) {
      throw new Error("Release version must be 1–64 printable characters without / or \\");
    }
    normalized[pack] = label;
  }
  const merged = { ...await releaseVersions(env), ...normalized };
  await env.DB.prepare(
    `INSERT INTO wukong_control_plane_metadata (key, value)
     VALUES ('mod_release_versions', ?)
     ON CONFLICT (key) DO UPDATE SET value = excluded.value`
  ).bind(JSON.stringify(merged)).run();
  return merged;
}

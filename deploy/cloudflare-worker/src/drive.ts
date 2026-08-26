type JsonObject = Record<string, unknown>;

let cachedAccessToken = "";
let cachedAccessTokenExpiresAt = 0;

async function googleAccessToken(env: Env): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cachedAccessToken && cachedAccessTokenExpiresAt > now + 60) return cachedAccessToken;
  if (
    !env.WUKONG_GOOGLE_CLIENT_ID ||
    !env.WUKONG_GOOGLE_CLIENT_SECRET ||
    !env.WUKONG_GOOGLE_REFRESH_TOKEN
  ) {
    throw new Error("Google Drive OAuth is not configured");
  }
  const body = new URLSearchParams({
    client_id: env.WUKONG_GOOGLE_CLIENT_ID,
    client_secret: env.WUKONG_GOOGLE_CLIENT_SECRET,
    refresh_token: env.WUKONG_GOOGLE_REFRESH_TOKEN,
    grant_type: "refresh_token"
  });
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  const payload = await response.json() as JsonObject;
  if (!response.ok || typeof payload.access_token !== "string") {
    throw new Error("Google Drive OAuth refresh failed");
  }
  cachedAccessToken = payload.access_token;
  cachedAccessTokenExpiresAt = now + Math.max(60, Number(payload.expires_in ?? 3600));
  return cachedAccessToken;
}

function directDriveUrl(item: JsonObject): string {
  const webViewLink = typeof item.webViewLink === "string" ? item.webViewLink : "";
  if (webViewLink.startsWith("https://drive.google.com/")) return webViewLink;
  const id = typeof item.id === "string" ? item.id : "";
  return id ? `https://drive.google.com/file/d/${encodeURIComponent(id)}/view` : "";
}

export async function cloudLibrary(env: Env, category: string): Promise<JsonObject> {
  const rootFolder = env.WUKONG_GOOGLE_DRIVE_FOLDER_ID.trim();
  if (!rootFolder) return { available: false, entries: [] };
  const normalizedCategory = ["artifacts", "checkpoints", "recipes", "sources"].includes(category)
    ? category
    : "artifacts";
  const token = await googleAccessToken(env);
  const query = new URLSearchParams({
    q: `'${rootFolder.replaceAll("'", "\\'")}' in parents and trashed = false`,
    orderBy: "modifiedTime desc",
    pageSize: "100",
    fields: "files(id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,webContentLink,description)"
  });
  const response = await fetch(`https://www.googleapis.com/drive/v3/files?${query}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) throw new Error(`Google Drive library query failed (${response.status})`);
  const payload = await response.json() as JsonObject;
  const files = Array.isArray(payload.files) ? payload.files : [];
  const entries = files.flatMap((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const item = value as JsonObject;
    const description = String(item.description ?? "").toLowerCase();
    if (description && !description.includes(normalizedCategory)) return [];
    return [{
      id: item.id,
      name: item.name,
      mimeType: item.mimeType,
      sizeBytes: Number(item.size ?? 0),
      modifiedAt: item.modifiedTime,
      md5: item.md5Checksum ?? "",
      publicUrl: directDriveUrl(item)
    }];
  });
  return { available: true, category: normalizedCategory, entries };
}

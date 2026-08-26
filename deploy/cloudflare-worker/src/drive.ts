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
    if (payload.error === "invalid_grant") {
      throw new Error("Google Drive cần xác thực lại");
    }
    throw new Error("Google Drive tạm thời không thể xác thực");
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

const DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder";
const MAX_LIBRARY_ENTRIES = 500;
const MAX_LIBRARY_FOLDERS = 100;

function escapeDriveQueryValue(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll("'", "\\'");
}

async function listDriveChildren(
  token: string,
  parentId: string,
  options: { folderName?: string } = {}
): Promise<JsonObject[]> {
  const files: JsonObject[] = [];
  let pageToken = "";
  do {
    const clauses = [
      `'${escapeDriveQueryValue(parentId)}' in parents`,
      "trashed = false"
    ];
    if (options.folderName) {
      clauses.push(`name = '${escapeDriveQueryValue(options.folderName)}'`);
      clauses.push(`mimeType = '${DRIVE_FOLDER_MIME_TYPE}'`);
    }
    const query = new URLSearchParams({
      q: clauses.join(" and "),
      orderBy: "modifiedTime desc",
      pageSize: "1000",
      fields: "nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,webContentLink,description)",
      supportsAllDrives: "true",
      includeItemsFromAllDrives: "true"
    });
    if (pageToken) query.set("pageToken", pageToken);
    const response = await fetch(`https://www.googleapis.com/drive/v3/files?${query}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!response.ok) throw new Error(`Google Drive library query failed (${response.status})`);
    const payload = await response.json() as JsonObject;
    if (Array.isArray(payload.files)) {
      for (const value of payload.files) {
        if (value && typeof value === "object" && !Array.isArray(value)) {
          files.push(value as JsonObject);
        }
      }
    }
    pageToken = typeof payload.nextPageToken === "string" ? payload.nextPageToken : "";
  } while (pageToken && files.length < MAX_LIBRARY_ENTRIES + MAX_LIBRARY_FOLDERS);
  return files;
}

export async function cloudLibrary(env: Env, category: string): Promise<JsonObject> {
  const rootFolder = env.WUKONG_GOOGLE_DRIVE_FOLDER_ID.trim();
  if (!rootFolder) return { available: false, entries: [] };
  const normalizedCategory = ["artifacts", "checkpoints", "recipes", "sources"].includes(category)
    ? category
    : "artifacts";
  const token = await googleAccessToken(env);
  const categoryFolders = await listDriveChildren(token, rootFolder, {
    folderName: normalizedCategory
  });
  const categoryFolder = categoryFolders.find(
    (item) => item.mimeType === DRIVE_FOLDER_MIME_TYPE && typeof item.id === "string"
  );
  if (!categoryFolder || typeof categoryFolder.id !== "string") {
    return { available: true, category: normalizedCategory, entries: [] };
  }

  const entries: JsonObject[] = [];
  const pendingFolders = [categoryFolder.id];
  let visitedFolders = 0;
  while (
    pendingFolders.length > 0
    && visitedFolders < MAX_LIBRARY_FOLDERS
    && entries.length < MAX_LIBRARY_ENTRIES
  ) {
    const folderId = pendingFolders.shift();
    if (!folderId) break;
    visitedFolders += 1;
    const children = await listDriveChildren(token, folderId);
    for (const item of children) {
      if (item.mimeType === DRIVE_FOLDER_MIME_TYPE && typeof item.id === "string") {
        if (pendingFolders.length + visitedFolders < MAX_LIBRARY_FOLDERS) {
          pendingFolders.push(item.id);
        }
        continue;
      }
      entries.push({
        id: item.id,
        name: item.name,
        mimeType: item.mimeType,
        sizeBytes: Number(item.size ?? 0),
        modifiedAt: item.modifiedTime,
        md5: item.md5Checksum ?? "",
        publicUrl: directDriveUrl(item)
      });
      if (entries.length >= MAX_LIBRARY_ENTRIES) break;
    }
  }
  return { available: true, category: normalizedCategory, entries };
}

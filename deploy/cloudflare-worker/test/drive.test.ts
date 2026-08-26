import { afterEach, describe, expect, it, vi } from "vitest";
import { cloudLibrary } from "../src/drive";

describe("Google Drive library", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("enters the requested category and paginates nested folders", async () => {
    const queries: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "https://oauth2.googleapis.com/token") {
        return Response.json({ access_token: "drive-access-token", expires_in: 3600 });
      }
      const parsed = new URL(url);
      const query = parsed.searchParams.get("q") ?? "";
      const pageToken = parsed.searchParams.get("pageToken") ?? "";
      queries.push(`${query} page=${pageToken}`);
      if (query.includes("'root-folder' in parents") && query.includes("name = 'artifacts'")) {
        return Response.json({
          files: [{
            id: "artifacts-folder",
            name: "artifacts",
            mimeType: "application/vnd.google-apps.folder"
          }]
        });
      }
      if (query.includes("'artifacts-folder' in parents") && !pageToken) {
        return Response.json({
          nextPageToken: "page-2",
          files: [
            {
              id: "device-folder",
              name: "PKG110",
              mimeType: "application/vnd.google-apps.folder"
            },
            {
              id: "artifact-1",
              name: "rom-1.zip",
              mimeType: "application/zip",
              size: "12",
              modifiedTime: "2026-08-26T00:00:00Z",
              md5Checksum: "a".repeat(32)
            }
          ]
        });
      }
      if (query.includes("'artifacts-folder' in parents") && pageToken === "page-2") {
        return Response.json({
          files: [{
            id: "artifact-2",
            name: "rom-2.zip",
            mimeType: "application/zip",
            webViewLink: "https://drive.google.com/file/d/artifact-2/view"
          }]
        });
      }
      if (query.includes("'device-folder' in parents")) {
        return Response.json({
          files: [{
            id: "artifact-3",
            name: "rom-3.zip",
            mimeType: "application/zip"
          }]
        });
      }
      throw new Error(`Unexpected Drive query: ${url}`);
    }));

    const payload = await cloudLibrary({
      WUKONG_GOOGLE_CLIENT_ID: "client-id",
      WUKONG_GOOGLE_CLIENT_SECRET: "client-secret",
      WUKONG_GOOGLE_REFRESH_TOKEN: "refresh-token",
      WUKONG_GOOGLE_DRIVE_FOLDER_ID: "root-folder"
    } as Env, "artifacts") as { entries: Array<Record<string, unknown>> };

    expect(payload.entries.map((entry) => entry.name)).toEqual([
      "rom-1.zip",
      "rom-2.zip",
      "rom-3.zip"
    ]);
    expect(payload.entries.map((entry) => entry.publicUrl)).toEqual([
      "https://drive.google.com/file/d/artifact-1/view",
      "https://drive.google.com/file/d/artifact-2/view",
      "https://drive.google.com/file/d/artifact-3/view"
    ]);
    expect(queries.some((query) => query.includes("page=page-2"))).toBe(true);
  });
});

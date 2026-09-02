import type { JobRow } from "./jobs";
import { artifactEdition, presetEditionLabel } from "./artifact-metadata";
import { friendlyDeviceName } from "./catalog";
import { directArtifactUrl } from "./public-links";
import { issueDcCloudArtifactDownloadTicket } from "./auth";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function parseObject(value: unknown): JsonObject {
  try {
    return object(JSON.parse(String(value ?? "{}")));
  } catch {
    return {};
  }
}

function text(value: unknown, fallback = "—", limit = 240): string {
  const normalized = String(value ?? "").trim() || fallback;
  return normalized.slice(0, limit)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function sizeLabel(value: unknown): string {
  let size = Math.max(0, Number(value ?? 0));
  if (!Number.isFinite(size)) size = 0;
  for (const unit of ["B", "KiB", "MiB", "GiB", "TiB"]) {
    if (size < 1024 || unit === "TiB") {
      return unit === "B" ? `${Math.round(size)} ${unit}` : `${size.toFixed(2)} ${unit}`;
    }
    size /= 1024;
  }
  return `${Math.round(size)} B`;
}

function durationLabel(startValue: unknown, endValue: unknown): string {
  const start = Date.parse(String(startValue ?? ""));
  const end = Date.parse(String(endValue ?? ""));
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "";
  let seconds = Math.round((end - start) / 1000);
  const hours = Math.floor(seconds / 3600);
  seconds %= 3600;
  const minutes = Math.floor(seconds / 60);
  seconds %= 60;
  return [
    hours ? `${hours} giờ` : "",
    minutes ? `${minutes} phút` : "",
    seconds || (!hours && !minutes) ? `${seconds} giây` : ""
  ].filter(Boolean).join(" ");
}

function boundedHtml(lines: string[], limit = 4096): string {
  const output: string[] = [];
  const suffix = "<i>…</i>";
  for (const line of lines) {
    if ([...output, line].join("\n").length <= limit) {
      output.push(line);
      continue;
    }
    while (output.length && [...output, suffix].join("\n").length > limit) output.pop();
    if ([...output, suffix].join("\n").length <= limit) output.push(suffix);
    break;
  }
  return output.join("\n");
}

async function dcCloudDownloadLink(
  env: Env,
  jobId: string,
  artifactIndex: number
): Promise<string> {
  let api: URL;
  try {
    api = new URL(env.WUKONG_PUBLIC_API_URL.trim());
  } catch {
    return "";
  }
  if (
    api.protocol !== "https:"
    || !api.hostname
    || api.username
    || api.password
    || api.search
    || api.hash
  ) return "";
  try {
    const ticket = await issueDcCloudArtifactDownloadTicket(
      jobId,
      artifactIndex,
      env.WUKONG_TELEGRAM_BOT_TOKEN
    );
    const link = new URL(
      `/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${artifactIndex}/dccloud-download`,
      api
    );
    link.searchParams.set("ticket", ticket);
    return link.toString();
  } catch {
    return "";
  }
}

export async function terminalTelegramNotification(
  env: Env,
  row: JobRow,
  status: string,
  manifest: JsonObject
): Promise<JsonObject> {
  const recipe = parseObject(row.recipe_json);
  const source = object(recipe.source);
  const metadata = {
    ...object(source.metadata),
    ...object(manifest.rom_metadata ?? manifest.romMetadata)
  };
  const build = object(recipe.build);
  const editionLabel = presetEditionLabel(build.preset, build.editionLabels ?? build.edition_labels);
  const succeeded = status === "succeeded";
  const title = succeeded
    ? "✅ BUILD ROM HOÀN TẤT"
    : status === "cancelled"
      ? "⚪ BUILD ROM ĐÃ HỦY"
      : "⚠️ BUILD ROM CẦN KIỂM TRA";
  const statusLabel = succeeded
    ? "Thành công"
    : status === "cancelled"
      ? "Đã hủy"
      : "Thất bại";
  const lines = [
    `<b>${title}</b>`,
    "<i>Wukong ROM Studio</i>",
    "",
    `<b>${text(friendlyDeviceName(recipe.device, metadata.device ?? metadata.deviceName))}</b> · <code>${text(recipe.device)}</code>`,
    `<b>${statusLabel}</b> · <code>${text(row.job_id, "—", 64)}</code>`,
    "",
    "<b>THÔNG TIN ROM</b>",
    `<i>Phiên bản ROM</i>  <code>${text(metadata.version)}</code>`,
    `<i>Android</i>  <code>${text(metadata.androidVersion ?? metadata.android_version)}</code>`,
    `<i>Bản vá</i>  <code>${text(metadata.securityPatch ?? metadata.security_patch)}</code>`,
    `<i>Ngày build</i>  <code>${text(metadata.buildDate ?? metadata.build_date)}</code>`,
    "",
    "<b>CẤU HÌNH</b>",
    `<b>${text(editionLabel)}</b> · <code>${text(build.modVersion ?? build.mod_version)}</code> · <code>${text(build.modReleaseVersion ?? build.mod_release_version)}</code>`,
    `<i>Runner</i>  <code>${text(manifest.runner ?? row.runner)}</code>`
  ];
  const duration = durationLabel(
    manifest.created_at ?? manifest.createdAt ?? row.created_at,
    manifest.finished_at ?? manifest.finishedAt ?? row.finished_at
  );
  if (duration) lines.push(`<i>Thời gian</i>  <code>${duration}</code>`);
  const error = String(manifest.error ?? row.error ?? "").trim();
  if (error) {
    lines.push("", "<b>LƯU Ý</b>", text(error, "—", 640));
  }

  const keyboard: JsonObject[][] = [];
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts.slice(0, 8) : [];
  if (artifacts.length) lines.push("", `<b>ARTIFACT · ${artifacts.length}</b>`);
  for (const [offset, value] of artifacts.entries()) {
    const artifact = object(value);
    const name = String(artifact.name ?? "").trim();
    const edition = artifactEdition(name, offset + 1, build.preset, build.editionLabels ?? build.edition_labels);
    const size = sizeLabel(artifact.size_bytes ?? artifact.sizeBytes);
    lines.push(
      `${offset + 1}. <b>${text(edition)}</b> · <b>${size}</b>`,
      `<code>${text(name)}</code>`,
      `<i>SHA-256</i>  <code>${text(artifact.sha256, "—", 128)}</code>`
    );
    const url = directArtifactUrl(artifact.public_url ?? artifact.publicUrl, env);
    if (url) keyboard.push([{ text: `Tải ${edition} · ${size}`, url }]);
    const mirrors = Array.isArray(artifact.mirrors) ? artifact.mirrors : [];
    for (const value of mirrors) {
      const mirror = object(value);
      if (String(mirror.provider ?? "").trim().toLowerCase() !== "dccloud") continue;
      const status = String(mirror.status ?? "").trim().toLowerCase();
      const mirrorUri = typeof mirror.uri === "string" ? mirror.uri.trim() : "";
      const mirrorUrl = status === "available" && mirrorUri
        ? await dcCloudDownloadLink(env, row.job_id, offset)
        : "";
      if (status === "available" && mirrorUrl) {
        lines.push("DC Cloud mirror  <i>sẵn sàng</i>");
        keyboard.push([{ text: `Tải ${edition} · ${size} (DC Cloud)`, url: mirrorUrl }]);
      } else if (status === "repairing") {
        lines.push("DC Cloud mirror  <i>đang repair…</i>");
      } else if (status === "failed") {
        lines.push("DC Cloud mirror  <i>chưa sẵn sàng</i>");
      } else {
        lines.push(status === "available"
          ? "DC Cloud mirror  <i>sẵn sàng · mở Mini App để tải</i>"
          : "DC Cloud mirror  <i>đang upload</i>");
      }
    }
  }
  if (env.WUKONG_TELEGRAM_WEB_APP_URL.startsWith("https://")) {
    keyboard.push([{
      text: "Mở Wukong Mini App",
      web_app: { url: env.WUKONG_TELEGRAM_WEB_APP_URL }
    }]);
  }
  return {
    text: boundedHtml(lines),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    ...(keyboard.length ? { reply_markup: { inline_keyboard: keyboard } } : {})
  };
}

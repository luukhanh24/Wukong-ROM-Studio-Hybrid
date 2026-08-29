import type { JobRow } from "./jobs";
import { artifactEdition, presetEditionLabel } from "./artifact-metadata";
import { directArtifactUrl } from "./public-links";

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

export function terminalTelegramNotification(
  env: Env,
  row: JobRow,
  status: string,
  manifest: JsonObject
): JsonObject {
  const recipe = parseObject(row.recipe_json);
  const source = object(recipe.source);
  const metadata = {
    ...object(source.metadata),
    ...object(manifest.rom_metadata ?? manifest.romMetadata)
  };
  const build = object(recipe.build);
  const editionLabel = presetEditionLabel(build.preset, build.editionLabels ?? build.edition_labels);
  const succeeded = status === "succeeded";
  const title = succeeded ? "Build ROM hoàn tất" : "Build ROM cần kiểm tra";
  const statusLabel = succeeded
    ? "Thành công"
    : status === "cancelled"
      ? "Đã hủy"
      : "Thất bại";
  const lines = [
    "<b>Wukong ROM Studio</b>",
    `<b>${title}</b>`,
    "",
    "<b>Thông tin bản ROM</b>",
    `Trạng thái  <b>${statusLabel}</b>`,
    `Job  <code>${text(row.job_id, "—", 64)}</code>`,
    `Thiết bị  <code>${text(recipe.device)}</code>`,
    `Phiên bản  <code>${text(metadata.version)}</code>`,
    `Android  <code>${text(metadata.androidVersion ?? metadata.android_version)}</code>`,
    `Bản vá  <code>${text(metadata.securityPatch ?? metadata.security_patch)}</code>`,
    `Ngày build  <code>${text(metadata.buildDate ?? metadata.build_date)}</code>`,
    "",
    "<b>Cấu hình</b>",
    `Bản build  <code>${text(editionLabel)}</code>`,
    `MOD pack  <code>${text(build.modVersion ?? build.mod_version)}</code>`,
    `Phát hành  <code>${text(build.modReleaseVersion ?? build.mod_release_version)}</code>`,
    `Runner  <code>${text(manifest.runner ?? row.runner)}</code>`
  ];
  const duration = durationLabel(
    manifest.created_at ?? manifest.createdAt ?? row.created_at,
    manifest.finished_at ?? manifest.finishedAt ?? row.finished_at
  );
  if (duration) lines.push(`Thời gian  <code>${duration}</code>`);
  const error = String(manifest.error ?? row.error ?? "").trim();
  if (error) {
    lines.push("", "<b>Thông tin cần lưu ý</b>", text(error, "—", 640));
  }

  const keyboard: JsonObject[][] = [];
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts.slice(0, 8) : [];
  if (artifacts.length) lines.push("", "<b>Artifact</b>");
  artifacts.forEach((value, offset) => {
    const artifact = object(value);
    const name = String(artifact.name ?? "").trim();
    const edition = artifactEdition(name, offset + 1, build.preset, build.editionLabels ?? build.edition_labels);
    const size = sizeLabel(artifact.size_bytes ?? artifact.sizeBytes);
    lines.push(
      `${offset + 1}. <b>${text(edition)}</b> · ${size}`,
      `<code>${text(name)}</code>`,
      `SHA-256  <code>${text(artifact.sha256, "—", 128)}</code>`
    );
    const url = directArtifactUrl(artifact.public_url ?? artifact.publicUrl, env);
    if (url) keyboard.push([{ text: `Tải ${edition} · ${size}`, url }]);
  });
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

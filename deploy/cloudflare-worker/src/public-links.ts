export function directArtifactUrl(value: unknown, env: Env): string {
  const candidate = typeof value === "string" ? value.trim() : "";
  if (!candidate || candidate.includes("\\") || /\s/.test(candidate)) return "";
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password) return "";
    const blocked = new Set(["wukong-mini-api.onrender.com"]);
    try {
      blocked.add(new URL(env.WUKONG_TELEGRAM_WEB_APP_URL).hostname.toLowerCase());
    } catch {
      // Deployment validates the web app URL; malformed local fixtures are ignored.
    }
    if (
      blocked.has(parsed.hostname.toLowerCase())
      || parsed.hostname.toLowerCase().endsWith(".workers.dev")
      || ["github.com", "githubusercontent.com"].some(host =>
        parsed.hostname.toLowerCase() === host || parsed.hostname.toLowerCase().endsWith(`.${host}`))
    ) {
      return "";
    }
    return candidate;
  } catch {
    return "";
  }
}

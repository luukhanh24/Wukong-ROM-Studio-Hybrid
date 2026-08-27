export function artifactEdition(name: unknown, index: number, preset: unknown): string {
  const normalized = String(name ?? "").toLowerCase();
  if (normalized.includes("lite")) return "Lite";
  if (normalized.includes("plus")) return "Plus";
  if (normalized.includes("custom") || String(preset ?? "").toLowerCase() === "custom") {
    return "Custom";
  }
  return `Artifact ${index}`;
}

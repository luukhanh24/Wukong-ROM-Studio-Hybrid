type EditionLabels = Record<string, unknown>;

export function presetEditionLabel(preset: unknown, labels: unknown = undefined): string {
  let key = String(preset ?? "").trim().toLowerCase();
  if (key === "resume") key = "plus";
  if (key === "standard") key = "lite";
  const map = labels && typeof labels === "object" && !Array.isArray(labels)
    ? labels as EditionLabels
    : {};
  const label = (name: string, fallback: string) => {
    const value = String(map[name] ?? "").trim();
    return value || fallback;
  };
  if (key === "both") return `${label("lite", "Lite")} + ${label("plus", "Plus")}`;
  return label(key, ({ lite: "Lite", plus: "Plus", custom: "Custom" } as Record<string, string>)[key] || key);
}

export function artifactEdition(name: unknown, index: number, preset: unknown, labels: unknown = undefined): string {
  const normalized = String(name ?? "").toLowerCase();
  const configured = labels && typeof labels === "object" && !Array.isArray(labels)
    ? labels as EditionLabels
    : {};
  const normalizedPreset = String(preset ?? "").trim().toLowerCase();
  const expectedKey = normalizedPreset === "both"
    ? (index === 1 ? "lite" : "plus")
    : normalizedPreset === "resume"
      ? "plus"
      : normalizedPreset === "standard"
        ? "lite"
        : normalizedPreset;
  if (["lite", "plus", "custom"].includes(expectedKey)) {
    const expected = presetEditionLabel(expectedKey, configured);
    // A recipe contains the internal preset and its label snapshot, so this
    // is the authoritative answer even when labels overlap (e.g. Build and
    // Build Pro). Use the filename only for legacy recipes without labels.
    if (configured[expectedKey]) return expected;
    if (normalized.includes(`_${expected.toLowerCase()}_`) || normalized.endsWith(`_${expected.toLowerCase()}.zip`)) {
      return expected;
    }
  }
  for (const key of ["lite", "plus", "custom"]) {
    const label = String(configured[key] ?? "").trim();
    if (label && (normalized.includes(`_${label.toLowerCase()}_`) || normalized.endsWith(`_${label.toLowerCase()}.zip`))) return label;
  }
  if (normalized.includes("_lite_") || normalized.endsWith("_lite.zip")) return "Lite";
  if (normalized.includes("_plus_") || normalized.endsWith("_plus.zip")) return "Plus";
  if (normalized.includes("_custom_") || normalized.endsWith("_custom.zip")) return "Custom";
  if (["lite", "plus", "custom"].includes(expectedKey)) return presetEditionLabel(expectedKey, configured);
  return `Artifact ${index}`;
}

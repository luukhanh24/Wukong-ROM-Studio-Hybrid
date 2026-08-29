import { describe, expect, it } from "vitest";
import { artifactEdition, presetEditionLabel } from "../src/artifact-metadata";

describe("artifact metadata", () => {
  it("identifies Lite, Plus and Custom build outputs", () => {
    expect(artifactEdition("Wukong_Lite_V6.0.zip", 1, "both")).toBe("Lite");
    expect(artifactEdition("Wukong_Plus_V6.0.zip", 2, "both")).toBe("Plus");
    expect(artifactEdition("Wukong_V6.0_PKG110.zip", 1, "custom")).toBe("Custom");
  });

  it("uses configured labels for renamed outputs", () => {
    const labels = { lite: "Essential", plus: "Complete", custom: "Studio" };
    expect(presetEditionLabel("plus", labels)).toBe("Complete");
    expect(presetEditionLabel("both", labels)).toBe("Essential + Complete");
    expect(artifactEdition("Wukong_Complete_V6.0_PKG110.zip", 1, "plus", labels)).toBe("Complete");
    expect(artifactEdition("Wukong_Studio_V6.0_PKG110.zip", 1, "custom", labels)).toBe("Studio");
  });

  it("uses the preset/index snapshot when labels overlap", () => {
    const labels = { lite: "Build", plus: "Build Pro", custom: "Studio" };
    expect(artifactEdition("Wukong_Build Pro_V6.0.zip", 2, "both", labels)).toBe("Build Pro");
    expect(artifactEdition("Wukong_Build_V6.0.zip", 1, "both", labels)).toBe("Build");
  });

});

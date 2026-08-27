import { describe, expect, it } from "vitest";
import { artifactEdition } from "../src/artifact-metadata";

describe("artifact metadata", () => {
  it("identifies Lite, Plus and Custom build outputs", () => {
    expect(artifactEdition("Wukong_Lite_V6.0.zip", 1, "both")).toBe("Lite");
    expect(artifactEdition("Wukong_Plus_V6.0.zip", 2, "both")).toBe("Plus");
    expect(artifactEdition("Wukong_V6.0_PKG110.zip", 1, "custom")).toBe("Custom");
  });
});

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["node-test/**/*.test.ts"],
    testTimeout: 10_000
  }
});

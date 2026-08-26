import { describe, expect, it, vi } from "vitest";
import { cancelWorkflowRunForJob } from "../src/github";

describe("GitHub Actions cancellation", () => {
  it("finds a just-dispatched workflow by job ID before cancelling it", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      if ((init?.method ?? "GET") === "GET") {
        return Response.json({
          workflow_runs: [{
            id: 8123,
            event: "workflow_dispatch",
            display_title: "cancelled-before-bootstrap · Wukong Hybrid",
            path: ".github/workflows/wukong-build.yml"
          }]
        });
      }
      return new Response(null, { status: 202 });
    }));
    const environment = {
      WUKONG_DISABLE_EXTERNAL_DISPATCH: "",
      WUKONG_GITHUB_TOKEN: "github-token-" + "x".repeat(32),
      WUKONG_GITHUB_REPOSITORY: "luukhanh24/Wukong-ROM-Studio-Hybrid",
      WUKONG_GITHUB_WORKFLOW: "wukong-build.yml"
    } as Env;

    await expect(
      cancelWorkflowRunForJob(environment, "cancelled-before-bootstrap", null)
    ).resolves.toBe(8123);
    expect(calls).toEqual([
      "GET https://api.github.com/repos/luukhanh24/Wukong-ROM-Studio-Hybrid/actions/workflows/wukong-build.yml/runs?event=workflow_dispatch&per_page=100",
      "POST https://api.github.com/repos/luukhanh24/Wukong-ROM-Studio-Hybrid/actions/runs/8123/cancel"
    ]);
    vi.unstubAllGlobals();
  });
});

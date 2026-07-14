import { describe, expect, it } from "vitest";

import { createMcpBridge } from "./bin.js";

describe("MCP runtime adapter", () => {
  it("routes managed runtime status to stderr and returns the bridge", async () => {
    const stderr: string[] = [];
    const bridge = { call: async () => ({}) };
    const result = await createMcpBridge({
      discoverPython: async (options) => {
        options.onManagedRuntimeStatus?.("creating", "Creating isolated Python runtime");
        return { executable: "python-test", version: "3.12.0", coreVersion: "0.2.0" };
      },
      createBridge: () => bridge,
      stderr: (value) => stderr.push(value),
      cwd: () => "C:/project",
    });

    expect(result).toBe(bridge);
    expect(stderr).toEqual(["Creating isolated Python runtime"]);
  });
});

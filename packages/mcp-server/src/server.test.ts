import { describe, expect, it } from "vitest";

import { handleTool, type BridgePort } from "./server.js";

class FakeBridge implements BridgePort {
  calls: Array<[string, Record<string, unknown>]> = [];
  response: unknown = {};
  error: Error | undefined;

  async call<T>(command: string, payload: Record<string, unknown>): Promise<T> {
    this.calls.push([command, payload]);
    if (this.error) throw this.error;
    return this.response as T;
  }
}

describe("MCP bridge adapter", () => {
  it("creates an asynchronous task and returns its queued ID", async () => {
    const bridge = new FakeBridge();
    bridge.response = { task_id: "task-a", status: "queued", output_dir: "/out/tasks/task-a" };

    const result = await handleTool("create_team_task", { description: "build it" }, bridge);

    expect(bridge.calls).toEqual([
      [
        "task-start",
        { description: "build it", project_root: process.cwd(), output_root: "./ato-output" },
      ],
    ]);
    expect(result.isError).not.toBe(true);
    expect(result.content[0].text).toContain("task-a");
    expect(result.content[0].text).toContain("queued");
  });

  it("requires task IDs for status and audit bridge calls", async () => {
    const bridge = new FakeBridge();
    bridge.response = { task_id: "task-a", status: "running" };

    await handleTool("get_task_status", { taskId: "task-a", outputDir: "/out" }, bridge);
    await handleTool("get_task_audit", { taskId: "task-a", outputDir: "/out" }, bridge);

    expect(bridge.calls).toEqual([
      ["task-status", { task_id: "task-a", output_root: "/out" }],
      ["task-audit", { task_id: "task-a", output_root: "/out" }],
    ]);
  });

  it("forwards the exact approval tuple", async () => {
    const bridge = new FakeBridge();
    bridge.response = { task_id: "task-a", status: "running" };

    const result = await handleTool(
      "approve_step",
      { taskId: "task-a", requestId: "approval-1", approved: true, outputDir: "/out" },
      bridge,
    );

    expect(bridge.calls).toEqual([
      [
        "task-approve",
        {
          task_id: "task-a",
          request_id: "approval-1",
          approved: true,
          output_root: "/out",
        },
      ],
    ]);
    expect(result.isError).not.toBe(true);
  });

  it("returns MCP errors for stale approval IDs", async () => {
    const bridge = new FakeBridge();
    bridge.error = Object.assign(new Error("request is not pending"), {
      code: "APPROVAL_NOT_PENDING",
    });

    const result = await handleTool(
      "approve_step",
      { taskId: "task-a", requestId: "stale", approved: true },
      bridge,
    );

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("APPROVAL_NOT_PENDING");
  });
});

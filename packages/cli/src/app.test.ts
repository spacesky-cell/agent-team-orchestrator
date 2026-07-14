import { describe, expect, it } from "vitest";

import {
  defaultDependencies,
  runCli,
  type BridgePort,
  type CliDependencies,
} from "./app.js";

class FakeBridge implements BridgePort {
  calls: Array<[string, Record<string, unknown>]> = [];
  responses: unknown[] = [];
  error: Error | undefined;

  async call<T>(command: string, payload: Record<string, unknown>): Promise<T> {
    this.calls.push([command, payload]);
    if (this.error) throw this.error;
    return this.responses.shift() as T;
  }
}

function setup(bridge = new FakeBridge()) {
  const stdout: string[] = [];
  const stderr: string[] = [];
  const deps: CliDependencies = {
    bridge,
    version: "0.2.1",
    cwd: () => "C:/project",
    stdout: (value) => stdout.push(value),
    stderr: (value) => stderr.push(value),
    promptApproval: async () => true,
    sleep: async () => undefined,
  };
  return { bridge, deps, stdout, stderr };
}

describe("CLI bridge adapter", () => {
  it("returns zero for version without discovering Python", async () => {
    const { deps, stdout } = setup();

    const code = await runCli(["node", "ato", "--version"], deps);

    expect(code).toBe(0);
    expect(stdout).toEqual(["0.2.1"]);
  });

  it("maps read commands to exact bridge requests", async () => {
    const { bridge, deps } = setup();
    bridge.responses = [
      { core_version: "0.2.1" },
      { roles: [] },
      { task_id: "task-a", status: "running" },
      { task_id: "task-a", events: [] },
      { tasks: [] },
      { summary: "empty" },
    ];

    await runCli(["node", "ato", "doctor"], deps);
    await runCli(["node", "ato", "roles"], deps);
    await runCli(["node", "ato", "status", "task-a", "-o", "C:/out"], deps);
    await runCli(["node", "ato", "audit", "task-a", "-o", "C:/out"], deps);
    await runCli(["node", "ato", "tasks", "-o", "C:/out"], deps);
    await runCli(["node", "ato", "memory"], deps);

    expect(bridge.calls).toEqual([
      ["doctor", { project_root: "C:/project" }],
      ["roles-list", {}],
      ["task-status", { task_id: "task-a", output_root: "C:/out" }],
      ["task-audit", { task_id: "task-a", output_root: "C:/out" }],
      ["task-list", { output_root: "C:/out" }],
      ["memory-summary", { project_root: "C:/project" }],
    ]);
  });

  it("starts a detached task and returns immediately", async () => {
    const { bridge, deps, stdout } = setup();
    bridge.responses = [{ task_id: "task-a", status: "queued", output_dir: "C:/out/tasks/task-a" }];

    const code = await runCli(
      ["node", "ato", "run", "build it", "--detach", "-o", "C:/out"],
      deps,
    );

    expect(code).toBe(0);
    expect(bridge.calls).toEqual([
      [
        "task-start",
        { description: "build it", project_root: "C:/project", output_root: "C:/out" },
      ],
    ]);
    expect(stdout.join("\n")).toContain("task-a");
  });

  it("approves the exact active request and continues polling", async () => {
    const { bridge, deps } = setup();
    bridge.responses = [
      { task_id: "task-a", status: "queued", output_dir: "C:/out/tasks/task-a" },
      {
        task_id: "task-a",
        status: "waiting_approval",
        active_approval: { request_id: "approval-1", tool_name: "write_file" },
      },
      { task_id: "task-a", status: "running" },
      { task_id: "task-a", status: "completed", completed_subtasks: 1, total_subtasks: 1 },
    ];

    const code = await runCli(["node", "ato", "run", "build it", "-o", "C:/out"], deps);

    expect(code).toBe(0);
    expect(bridge.calls[2]).toEqual([
      "task-approve",
      {
        task_id: "task-a",
        request_id: "approval-1",
        approved: true,
        output_root: "C:/out",
      },
    ]);
  });

  it("forwards explicit rejection and renders blocked", async () => {
    const { bridge, deps, stdout } = setup();
    deps.promptApproval = async () => false;
    bridge.responses = [
      { task_id: "task-a", status: "queued" },
      {
        task_id: "task-a",
        status: "waiting_approval",
        active_approval: { request_id: "approval-1", tool_name: "write_file" },
      },
      { task_id: "task-a", status: "blocked" },
      { task_id: "task-a", status: "blocked" },
    ];

    const code = await runCli(["node", "ato", "run", "build it"], deps);

    expect(code).toBe(2);
    expect(stdout.at(-1)).toContain("blocked");
  });

  it("prints stable bridge error codes and exits non-zero", async () => {
    const { bridge, deps, stderr } = setup();
    const error = Object.assign(new Error("missing"), { code: "TASK_NOT_FOUND" });
    bridge.error = error;

    const code = await runCli(["node", "ato", "status", "task-a"], deps);

    expect(code).toBe(1);
    expect(stderr).toEqual(["TASK_NOT_FOUND: missing"]);
  });

  it("keeps discovery lazy and routes managed status to stderr", async () => {
    const bridge = new FakeBridge();
    bridge.responses = [{ core_version: "0.2.1" }];
    const stdout: string[] = [];
    const stderr: string[] = [];
    let discoveries = 0;
    const deps = await defaultDependencies({
      discoverPython: async (options) => {
        discoveries += 1;
        options.onManagedRuntimeStatus?.("installing", "Installing bundled ATO core");
        return { executable: "python-test", version: "3.12.0", coreVersion: "0.2.1" };
      },
      createBridge: () => bridge,
      cwd: () => "C:/project",
      stdout: (value) => stdout.push(value),
      stderr: (value) => stderr.push(value),
    });

    expect(await runCli(["node", "ato", "--version"], deps)).toBe(0);
    expect(discoveries).toBe(0);
    expect(stderr).toEqual([]);

    expect(await runCli(["node", "ato", "doctor"], deps)).toBe(0);
    expect(discoveries).toBe(1);
    expect(stderr).toEqual(["Installing bundled ATO core"]);
    expect(stdout).toEqual(["0.2.1", JSON.stringify({ core_version: "0.2.1" }, null, 2)]);
  });
});

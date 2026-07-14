import { createInterface } from "node:readline/promises";

import {
  BridgeClient,
  discoverPython,
  type DiscoveryOptions,
  type PythonRuntime,
} from "@spacesky-cell/ato-shared";
import { Command, CommanderError } from "commander";

export interface BridgePort {
  call<T>(command: string, payload: Record<string, unknown>): Promise<T>;
}

export interface ApprovalPrompt {
  request_id: string;
  tool_name: string;
  args_summary?: Record<string, unknown>;
}

export interface CliDependencies {
  bridge: BridgePort;
  version: string;
  cwd: () => string;
  stdout: (value: string) => void;
  stderr: (value: string) => void;
  promptApproval: (request: ApprovalPrompt) => Promise<boolean>;
  sleep: (milliseconds: number) => Promise<void>;
}

export interface DefaultDependenciesOptions {
  discoverPython?: (options: DiscoveryOptions) => Promise<PythonRuntime>;
  createBridge?: (runtime: PythonRuntime) => BridgePort;
  cwd?: () => string;
  stdout?: (value: string) => void;
  stderr?: (value: string) => void;
}

interface TaskRecord {
  task_id: string;
  status: string;
  output_dir?: string;
  completed_subtasks?: number;
  total_subtasks?: number;
  active_approval?: ApprovalPrompt | null;
}

class CliStatus extends Error {
  constructor(readonly exitCode: number) {
    super("CLI terminal status");
  }
}

function outputRoot(value: string): string {
  return value;
}

function render(deps: CliDependencies, value: unknown): void {
  deps.stdout(JSON.stringify(value, null, 2));
}

async function watchTask(
  deps: CliDependencies,
  taskId: string,
  root: string,
): Promise<void> {
  while (true) {
    const record = await deps.bridge.call<TaskRecord>("task-status", {
      task_id: taskId,
      output_root: root,
    });
    if (record.status === "waiting_approval" && record.active_approval) {
      const approved = await deps.promptApproval(record.active_approval);
      await deps.bridge.call<TaskRecord>("task-approve", {
        task_id: taskId,
        request_id: record.active_approval.request_id,
        approved,
        output_root: root,
      });
      if (!approved) {
        deps.stdout(`Task ${taskId}: blocked`);
        throw new CliStatus(2);
      }
      continue;
    }
    if (["completed", "blocked", "failed"].includes(record.status)) {
      deps.stdout(
        `Task ${taskId}: ${record.status} (${record.completed_subtasks ?? 0}/${record.total_subtasks ?? 0})`,
      );
      if (record.status !== "completed") throw new CliStatus(record.status === "blocked" ? 2 : 1);
      return;
    }
    await deps.sleep(500);
  }
}

export function createCli(deps: CliDependencies): Command {
  const program = new Command();
  program
    .name("ato")
    .description("Agent Team Orchestrator")
    .version(deps.version)
    .exitOverride()
    .configureOutput({
      writeOut: (value) => deps.stdout(value.trimEnd()),
      writeErr: (value) => deps.stderr(value.trimEnd()),
    });

  program.command("doctor").action(async () => {
    render(
      deps,
      await deps.bridge.call("doctor", { project_root: deps.cwd() }),
    );
  });

  program.command("roles").action(async () => {
    render(deps, await deps.bridge.call("roles-list", {}));
  });

  program
    .command("run <task>")
    .option("-o, --output <dir>", "Task output root", "./ato-output")
    .option("--project-root <dir>", "Project root")
    .option("--detach", "Return after starting the worker")
    .action(async (task: string, options: { output: string; projectRoot?: string; detach?: boolean }) => {
      const root = outputRoot(options.output);
      const record = await deps.bridge.call<TaskRecord>("task-start", {
        description: task,
        project_root: options.projectRoot ?? deps.cwd(),
        output_root: root,
      });
      deps.stdout(`Task ${record.task_id}: ${record.status}${record.output_dir ? `\n${record.output_dir}` : ""}`);
      if (!options.detach) await watchTask(deps, record.task_id, root);
    });

  program
    .command("status <taskId>")
    .option("-o, --output <dir>", "Task output root", "./ato-output")
    .action(async (taskId: string, options: { output: string }) => {
      render(
        deps,
        await deps.bridge.call("task-status", {
          task_id: taskId,
          output_root: outputRoot(options.output),
        }),
      );
    });

  program
    .command("audit <taskId>")
    .option("-o, --output <dir>", "Task output root", "./ato-output")
    .action(async (taskId: string, options: { output: string }) => {
      render(
        deps,
        await deps.bridge.call("task-audit", {
          task_id: taskId,
          output_root: outputRoot(options.output),
        }),
      );
    });

  program
    .command("tasks")
    .option("-o, --output <dir>", "Task output root", "./ato-output")
    .action(async (options: { output: string }) => {
      render(
        deps,
        await deps.bridge.call("task-list", { output_root: outputRoot(options.output) }),
      );
    });

  program
    .command("approve <taskId> <requestId>")
    .option("--reject", "Reject the request")
    .option("-o, --output <dir>", "Task output root", "./ato-output")
    .action(
      async (
        taskId: string,
        requestId: string,
        options: { reject?: boolean; output: string },
      ) => {
        render(
          deps,
          await deps.bridge.call("task-approve", {
            task_id: taskId,
            request_id: requestId,
            approved: !options.reject,
            output_root: outputRoot(options.output),
          }),
        );
      },
    );

  program
    .command("memory")
    .option("--query <text>", "Query relevant context")
    .option("--top-k <count>", "Maximum query results", "5")
    .action(async (options: { query?: string; topK: string }) => {
      const result = options.query
        ? await deps.bridge.call("memory-query", {
            project_root: deps.cwd(),
            query: options.query,
            top_k: Number(options.topK),
          })
        : await deps.bridge.call("memory-summary", { project_root: deps.cwd() });
      render(deps, result);
    });

  return program;
}

export async function runCli(argv: string[], deps: CliDependencies): Promise<number> {
  try {
    await createCli(deps).parseAsync(argv);
    return 0;
  } catch (error) {
    if (error instanceof CliStatus) return error.exitCode;
    if (
      error instanceof CommanderError &&
      ["commander.helpDisplayed", "commander.version"].includes(error.code)
    ) {
      return 0;
    }
    const code =
      error && typeof error === "object" && "code" in error ? String(error.code) : "CLI_ERROR";
    const message = error instanceof Error ? error.message : String(error);
    deps.stderr(`${code}: ${message}`);
    return 1;
  }
}

export async function defaultDependencies(
  options: DefaultDependenciesOptions = {},
): Promise<CliDependencies> {
  const cwd = options.cwd ?? (() => process.cwd());
  const stdout = options.stdout ?? ((value: string) => console.log(value));
  const stderr = options.stderr ?? ((value: string) => console.error(value));
  const discover = options.discoverPython ?? discoverPython;
  const createBridge =
    options.createBridge ?? ((runtime: PythonRuntime) => new BridgeClient(runtime, { cwd: cwd() }));
  let bridge: Promise<BridgePort> | undefined;
  const getBridge = () => {
    bridge ??= discover({
      projectRoot: cwd(),
      onManagedRuntimeStatus: (_status, message) => stderr(message),
    }).then((runtime) => createBridge(runtime));
    return bridge;
  };
  return {
    bridge: {
      call: async <T>(command: string, payload: Record<string, unknown>) =>
        (await getBridge()).call<T>(command, payload),
    },
    version: "0.2.1",
    cwd,
    stdout,
    stderr,
    promptApproval: async (request) => {
      const prompt = createInterface({ input: process.stdin, output: process.stderr });
      const answer = await prompt.question(`Approve ${request.tool_name} (${request.request_id})? [y/N] `);
      prompt.close();
      return answer.trim().toLowerCase() === "y";
    },
    sleep: (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
  };
}

export async function main(argv = process.argv): Promise<number> {
  try {
    return await runCli(argv, await defaultDependencies());
  } catch (error) {
    const code =
      error && typeof error === "object" && "code" in error ? String(error.code) : "CLI_ERROR";
    const message = error instanceof Error ? error.message : String(error);
    console.error(`${code}: ${message}`);
    return 1;
  }
}

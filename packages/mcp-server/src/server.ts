import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type CallToolResult,
} from "@modelcontextprotocol/sdk/types.js";

export interface BridgePort {
  call<T>(command: string, payload: Record<string, unknown>): Promise<T>;
}

export type ToolResult = CallToolResult;

function text(value: unknown): ToolResult {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

function requiredString(args: Record<string, unknown>, key: string): string {
  const value = args[key];
  if (typeof value !== "string" || value.trim().length === 0) {
    throw Object.assign(new Error(`${key} is required`), { code: "INVALID_REQUEST" });
  }
  return value;
}

function requiredBoolean(args: Record<string, unknown>, key: string): boolean {
  const value = args[key];
  if (typeof value !== "boolean") {
    throw Object.assign(new Error(`${key} is required`), { code: "INVALID_REQUEST" });
  }
  return value;
}

export async function handleTool(
  name: string,
  args: Record<string, unknown>,
  bridge: BridgePort,
): Promise<ToolResult> {
  try {
    switch (name) {
      case "create_team_task":
        return text(
          await bridge.call("task-start", {
            description: requiredString(args, "description"),
            project_root: typeof args.projectRoot === "string" ? args.projectRoot : process.cwd(),
            output_root: typeof args.outputDir === "string" ? args.outputDir : "./ato-output",
          }),
        );
      case "get_task_status":
        return text(
          await bridge.call("task-status", {
            task_id: requiredString(args, "taskId"),
            output_root: typeof args.outputDir === "string" ? args.outputDir : "./ato-output",
          }),
        );
      case "get_task_audit":
        return text(
          await bridge.call("task-audit", {
            task_id: requiredString(args, "taskId"),
            output_root: typeof args.outputDir === "string" ? args.outputDir : "./ato-output",
          }),
        );
      case "approve_step":
        return text(
          await bridge.call("task-approve", {
            task_id: requiredString(args, "taskId"),
            request_id: requiredString(args, "requestId"),
            approved: requiredBoolean(args, "approved"),
            output_root: typeof args.outputDir === "string" ? args.outputDir : "./ato-output",
          }),
        );
      case "list_available_roles":
        return text(await bridge.call("roles-list", {}));
      case "list_tasks":
        return text(
          await bridge.call("task-list", {
            output_root: typeof args.outputDir === "string" ? args.outputDir : "./ato-output",
          }),
        );
      case "query_team_memory":
        return text(
          await bridge.call("memory-query", {
            query: requiredString(args, "query"),
            top_k: typeof args.topK === "number" ? args.topK : 5,
            project_root: typeof args.projectRoot === "string" ? args.projectRoot : process.cwd(),
          }),
        );
      case "get_memory_summary":
        return text(
          await bridge.call("memory-summary", {
            project_root: typeof args.projectRoot === "string" ? args.projectRoot : process.cwd(),
          }),
        );
      case "self_check":
        return text(
          await bridge.call("doctor", {
            project_root: typeof args.projectRoot === "string" ? args.projectRoot : process.cwd(),
          }),
        );
      default:
        throw Object.assign(new Error(`Unknown tool: ${name}`), { code: "UNKNOWN_TOOL" });
    }
  } catch (error) {
    const code =
      error && typeof error === "object" && "code" in error ? String(error.code) : "MCP_ERROR";
    const message = error instanceof Error ? error.message : String(error);
    return { content: [{ type: "text", text: `${code}: ${message}` }], isError: true };
  }
}

const tools = [
  {
    name: "create_team_task",
    description: "Start an asynchronous team task.",
    inputSchema: {
      type: "object",
      properties: {
        description: { type: "string" },
        projectRoot: { type: "string" },
        outputDir: { type: "string" },
      },
      required: ["description"],
    },
  },
  {
    name: "get_task_status",
    description: "Read one persisted task status.",
    inputSchema: {
      type: "object",
      properties: { taskId: { type: "string" }, outputDir: { type: "string" } },
      required: ["taskId"],
    },
  },
  {
    name: "get_task_audit",
    description: "Read one task's tool audit events.",
    inputSchema: {
      type: "object",
      properties: { taskId: { type: "string" }, outputDir: { type: "string" } },
      required: ["taskId"],
    },
  },
  {
    name: "approve_step",
    description: "Approve or reject one active approval request.",
    inputSchema: {
      type: "object",
      properties: {
        taskId: { type: "string" },
        requestId: { type: "string" },
        approved: { type: "boolean" },
        outputDir: { type: "string" },
      },
      required: ["taskId", "requestId", "approved"],
    },
  },
  {
    name: "list_available_roles",
    description: "List packaged agent roles.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "list_tasks",
    description: "List persisted tasks.",
    inputSchema: { type: "object", properties: { outputDir: { type: "string" } } },
  },
  {
    name: "query_team_memory",
    description: "Query relevant team memory.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        topK: { type: "number" },
        projectRoot: { type: "string" },
      },
      required: ["query"],
    },
  },
  {
    name: "get_memory_summary",
    description: "Read the team memory summary.",
    inputSchema: { type: "object", properties: { projectRoot: { type: "string" } } },
  },
  {
    name: "self_check",
    description: "Check the installed ATO core runtime.",
    inputSchema: { type: "object", properties: { projectRoot: { type: "string" } } },
  },
];

export function createAtoServer(bridge: BridgePort): Server {
  const server = new Server(
    { name: "ato", version: "0.2.0" },
    { capabilities: { tools: {} } },
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));
  server.setRequestHandler(CallToolRequestSchema, async (request) =>
    handleTool(
      request.params.name,
      (request.params.arguments ?? {}) as Record<string, unknown>,
      bridge,
    ),
  );
  return server;
}

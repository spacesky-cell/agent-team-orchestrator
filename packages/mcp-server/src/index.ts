import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  executePythonJson,
  getCoreModulePath,
  getProjectRoot,
  getPythonPath,
} from "@ato/shared";
import { mkdirSync } from "fs";
import { resolve } from "path";

interface RoleInfo {
  id: string;
  name: string;
  description: string;
  expertise: string[];
  tools: string[];
}

interface TaskStatus {
  task_id: string;
  status: string;
  summary?: string;
  subtasks: Array<Record<string, any>>;
  artifacts: Record<string, any>;
  source?: string;
  error?: string;
}

function normalizeRoot(path?: string): string {
  return resolve(path || ".");
}

function buildTaskScript(): string {
  return `
import json
from pathlib import Path

from dotenv import load_dotenv
from src.orchestrator.simple_orchestrator import SimpleOrchestrator
from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

payload = json.loads(input_path.read_text(encoding="utf-8"))
description = payload["description"]
task_id = payload["task_id"]
output_dir = Path(payload["output_dir"])
project_root = Path(payload["project_root"])

load_dotenv(project_root / ".env")
load_dotenv()

output_dir.mkdir(parents=True, exist_ok=True)

simple_orchestrator = SimpleOrchestrator()
decomposition = simple_orchestrator.decompose_task(description)
subtasks = [
    {
        "id": st.id,
        "name": st.name,
        "role": st.role,
        "dependencies": st.dependencies,
        "expected_output": st.expected_output,
        "status": "pending",
    }
    for st in decomposition.subtasks
]

tool_orchestrator = ToolEnabledOrchestrator(
    db_path=output_dir / "checkpoints.db",
    project_root=project_root,
    memory_dir=".ato/memory",
)
result = tool_orchestrator.run(
    task_id=task_id,
    subtasks=subtasks,
    thread_id=task_id,
    resume=False,
)

result_payload = {
    "task_id": task_id,
    "status": result.get("status"),
    "artifacts": result.get("artifacts", {}),
    "subtasks": result.get("subtasks", []),
    "summary": decomposition.summary,
}

(output_dir / "result.json").write_text(
    json.dumps(result_payload, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(json.dumps({
    "task_id": task_id,
    "status": result_payload["status"],
    "summary": decomposition.summary,
    "subtask_count": len(subtasks),
    "completed_count": sum(1 for st in result.get("subtasks", []) if st.get("status") == "completed"),
}, ensure_ascii=False))
`;
}

function buildStatusScript(): string {
  return `
import json
from pathlib import Path

payload = json.loads(input_path.read_text(encoding="utf-8"))
task_id = payload["task_id"]
output_dir = Path(payload["output_dir"])
status = {
    "task_id": task_id,
    "status": "unknown",
    "subtasks": [],
    "artifacts": {},
}

result_path = output_dir / "result.json"
if result_path.exists():
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        if data.get("task_id") == task_id:
            data["source"] = "result.json"
            print(json.dumps(data, ensure_ascii=False))
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        status["error"] = f"Failed to read result.json: {exc}"

db_path = output_dir / "checkpoints.db"
if db_path.exists():
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC LIMIT 1", (task_id,))
        row = cursor.fetchone()
        if row:
            status["status"] = "checkpoint_found"
            status["source"] = "checkpoint"
        conn.close()
    except Exception as exc:
        status["error"] = str(exc)

print(json.dumps(status, ensure_ascii=False))
`;
}

function buildRolesScript(): string {
  return `
import json
from src.models.role import RoleLoader

loader = RoleLoader()
roles = []
for role_id in loader.list_roles():
    role = loader.load(role_id)
    roles.append({
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "expertise": role.expertise,
        "tools": role.tools,
    })

print(json.dumps(roles, ensure_ascii=False))
`;
}

function buildTasksScript(): string {
  return `
import json
from pathlib import Path

payload = json.loads(input_path.read_text(encoding="utf-8"))
output_dir = Path(payload["output_dir"])
tasks = []

result_path = output_dir / "result.json"
if result_path.exists():
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "completed":
            tasks.append({
                "task_id": result.get("task_id"),
                "status": result.get("status", "unknown"),
                "completed_subtasks": sum(1 for s in result.get("subtasks", []) if s.get("status") == "completed"),
                "total_subtasks": len(result.get("subtasks", [])),
                "source": "result.json",
            })
    except Exception:
        pass

print(json.dumps(tasks, ensure_ascii=False))
`;
}

function buildMemoryScript(summary: boolean): string {
  const body = summary
    ? `result = memory.summary()`
    : `result = memory.retrieve_relevant_context(payload["query"], top_k=int(payload.get("top_k") or 5))`;
  return `
import json
from src.memory.team_memory import TeamMemory

payload = json.loads(input_path.read_text(encoding="utf-8"))
memory = TeamMemory(project_root=payload["project_root"])
${body}
print(json.dumps({"result": result}, ensure_ascii=False))
`;
}

function buildSelfCheckScript(): string {
  return `
import json
import os
import shutil
import subprocess
from pathlib import Path

from src.models.role import RoleLoader

payload = json.loads(input_path.read_text(encoding="utf-8"))
loader = RoleLoader()
claude_path = shutil.which("claude")
claude_version = "UNAVAILABLE"
if claude_path:
    try:
        completed = subprocess.run(
            [claude_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if completed.returncode == 0:
            claude_version = completed.stdout.strip()
    except Exception as exc:
        claude_version = f"ERROR: {exc}"

print(json.dumps({
    "python": os.sys.executable,
    "project_root": payload["project_root"],
    "core_module_path": payload["core_module_path"],
    "roles": loader.list_roles(),
    "env": {
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "claude-cli"),
        "ANTHROPIC_API_KEY": "SET" if os.getenv("ANTHROPIC_API_KEY") else "UNSET",
        "OPENAI_API_KEY": "SET" if os.getenv("OPENAI_API_KEY") else "UNSET",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL") or "UNSET",
        "CLAUDE_CLI": claude_version,
    },
}, ensure_ascii=False))
`;
}

const server = new Server(
  {
    name: "ato",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  },
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "create_team_task",
        description:
          "Create a team task with automatic decomposition and multi-agent execution.",
        inputSchema: {
          type: "object",
          properties: {
            description: { type: "string", description: "Task description" },
            outputDir: {
              type: "string",
              description: "Directory to save outputs and artifacts",
              default: "./ato-output",
            },
            projectRoot: {
              type: "string",
              description: "Root directory of the project to work on",
              default: ".",
            },
            timeoutMs: {
              type: "number",
              description: "Maximum task execution time in milliseconds",
              default: 900000,
            },
          },
          required: ["description"],
        },
      },
      {
        name: "get_task_status",
        description: "Query execution status of a team task",
        inputSchema: {
          type: "object",
          properties: {
            taskId: { type: "string", description: "The task ID to query" },
            outputDir: {
              type: "string",
              description: "Directory containing task outputs",
              default: "./ato-output",
            },
          },
          required: ["taskId"],
        },
      },
      {
        name: "approve_step",
        description: "Approve or reject current execution step",
        inputSchema: {
          type: "object",
          properties: {
            taskId: { type: "string", description: "The task ID" },
            approved: { type: "boolean", description: "Whether to approve current step" },
          },
          required: ["taskId", "approved"],
        },
      },
      {
        name: "list_available_roles",
        description: "List all available agent roles",
        inputSchema: { type: "object", properties: {} },
      },
      {
        name: "list_incomplete_tasks",
        description: "List incomplete tasks from the output directory",
        inputSchema: {
          type: "object",
          properties: {
            outputDir: {
              type: "string",
              description: "Directory containing task outputs",
              default: "./ato-output",
            },
          },
        },
      },
      {
        name: "query_team_memory",
        description: "Query team memory for relevant context",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query" },
            topK: { type: "number", description: "Number of results", default: 5 },
            projectRoot: {
              type: "string",
              description: "Root directory of the project",
              default: ".",
            },
          },
          required: ["query"],
        },
      },
      {
        name: "get_memory_summary",
        description: "Get a summary of team memory contents",
        inputSchema: {
          type: "object",
          properties: {
            projectRoot: {
              type: "string",
              description: "Root directory of the project",
              default: ".",
            },
          },
        },
      },
      {
        name: "self_check",
        description: "Run an ATO installation smoke check without calling an LLM",
        inputSchema: {
          type: "object",
          properties: {
            projectRoot: {
              type: "string",
              description: "Root directory of the project",
              default: ".",
            },
          },
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const rawArgs = (args ?? {}) as Record<string, any>;

  try {
    switch (name) {
      case "create_team_task": {
        const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const projectRoot = normalizeRoot(rawArgs.projectRoot);
        const outputDir = resolve(rawArgs.outputDir || "./ato-output");
        mkdirSync(outputDir, { recursive: true });

        const result = executePythonJson<{
          task_id: string;
          status: string;
          summary: string;
          subtask_count: number;
          completed_count: number;
        }>({
          script: buildTaskScript(),
          cwd: projectRoot,
          input: {
            description: rawArgs.description,
            task_id: taskId,
            output_dir: outputDir,
            project_root: projectRoot,
          },
          timeoutMs: Number(rawArgs.timeoutMs || 900000),
        });

        return {
          content: [
            {
              type: "text",
              text:
                `Team task executed\n\nTask ID: ${result.task_id}\n` +
                `Status: ${result.status}\nSummary: ${result.summary}\n` +
                `Progress: ${result.completed_count}/${result.subtask_count}\n\n` +
                `Output saved to: ${outputDir}/result.json`,
            },
          ],
        };
      }

      case "get_task_status": {
        const outputDir = resolve(rawArgs.outputDir || "./ato-output");
        const taskStatus = executePythonJson<TaskStatus>({
          script: buildStatusScript(),
          cwd: getProjectRoot(process.cwd()),
          input: { task_id: rawArgs.taskId, output_dir: outputDir },
        });

        const subtaskDetails =
          taskStatus.subtasks
            ?.map((st: any) => `- ${st.name || st.id} (${st.role || "unknown"}) - ${st.status}`)
            .join("\n") || "No subtasks";
        const artifactList = Object.keys(taskStatus.artifacts || {}).join(", ") || "None";

        return {
          content: [
            {
              type: "text",
              text:
                `## Task Status: ${rawArgs.taskId}\n\n` +
                `**Overall Status:** ${taskStatus.status}\n` +
                `**Source:** ${taskStatus.source || "none"}\n\n` +
                `### Subtasks\n${subtaskDetails}\n\n### Artifacts\n${artifactList}`,
            },
          ],
        };
      }

      case "approve_step": {
        return {
          content: [
            {
              type: "text",
              text: rawArgs.approved
                ? `Step approved for task ${rawArgs.taskId}.`
                : `Step rejected for task ${rawArgs.taskId}.`,
            },
          ],
        };
      }

      case "list_available_roles": {
        const roles = executePythonJson<RoleInfo[]>({
          script: buildRolesScript(),
          cwd: getProjectRoot(process.cwd()),
        });

        const roleText =
          roles
            .map((role) => {
              const tools = role.tools.length > 0 ? role.tools.join(", ") : "None";
              const expertise =
                role.expertise.length > 0 ? role.expertise.join(", ") : "None";
              return `### ${role.id}\n**${role.name}**\n${role.description}\n\n**Expertise:** ${expertise}\n**Tools:** ${tools}`;
            })
            .join("\n\n---\n\n") || "No roles found.";

        return { content: [{ type: "text", text: `## Available Agent Roles\n\n${roleText}` }] };
      }

      case "list_incomplete_tasks": {
        const outputDir = resolve(rawArgs.outputDir || "./ato-output");
        const tasks = executePythonJson<any[]>({
          script: buildTasksScript(),
          cwd: getProjectRoot(process.cwd()),
          input: { output_dir: outputDir },
        });
        const taskText =
          tasks
            .map(
              (task) =>
                `- **${task.task_id}**\n  Status: ${task.status}\n  Progress: ${task.completed_subtasks}/${task.total_subtasks}`,
            )
            .join("\n\n") || "No incomplete tasks found.";

        return { content: [{ type: "text", text: `## Incomplete Tasks\n\n${taskText}` }] };
      }

      case "query_team_memory": {
        const projectRoot = normalizeRoot(rawArgs.projectRoot);
        const result = executePythonJson<{ result: string }>({
          script: buildMemoryScript(false),
          cwd: projectRoot,
          input: {
            project_root: projectRoot,
            query: rawArgs.query,
            top_k: rawArgs.topK || 5,
          },
        });

        return {
          content: [
            {
              type: "text",
              text: `## Team Memory Search Results\n\nQuery: "${rawArgs.query}"\n\n${result.result}`,
            },
          ],
        };
      }

      case "get_memory_summary": {
        const projectRoot = normalizeRoot(rawArgs.projectRoot);
        const result = executePythonJson<{ result: string }>({
          script: buildMemoryScript(true),
          cwd: projectRoot,
          input: { project_root: projectRoot },
        });

        return { content: [{ type: "text", text: `## Team Memory Summary\n\n${result.result}` }] };
      }

      case "self_check": {
        const projectRoot = normalizeRoot(rawArgs.projectRoot);
        const result = executePythonJson<any>({
          script: buildSelfCheckScript(),
          cwd: projectRoot,
          input: {
            project_root: projectRoot,
            core_module_path: getCoreModulePath(projectRoot),
          },
        });

        return {
          content: [
            {
              type: "text",
              text:
                `## ATO Self Check\n\n` +
                `Python: ${getPythonPath(projectRoot)}\n` +
                `Core module path: ${result.core_module_path}\n` +
                `Roles: ${result.roles.join(", ")}\n` +
                `LLM provider: ${result.env.LLM_PROVIDER}\n` +
                `ANTHROPIC_API_KEY: ${result.env.ANTHROPIC_API_KEY}\n` +
                `OPENAI_API_KEY: ${result.env.OPENAI_API_KEY}\n` +
                `OLLAMA_BASE_URL: ${result.env.OLLAMA_BASE_URL}\n` +
                `Claude CLI: ${result.env.CLAUDE_CLI}`,
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    return {
      content: [{ type: "text", text: `Error: ${error.message}` }],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});

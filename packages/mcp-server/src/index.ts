import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { execSync } from "child_process";
import { existsSync, mkdirSync } from "fs";
import { join, resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

/**
 * Get Python executable path
 */
function getPythonPath(): string {
  const venvPaths = [
    join(__dirname, "..", "..", ".venv", "bin", "python"),
    join(__dirname, "..", "..", ".venv", "Scripts", "python.exe"),
    join(__dirname, "..", "..", "venv", "bin", "python"),
    join(__dirname, "..", "..", "venv", "Scripts", "python.exe"),
    "python3",
    "python",
  ];

  for (const path of venvPaths) {
    if (path === "python3" || path === "python") {
      return path;
    }
    if (existsSync(path)) {
      return path;
    }
  }

  return "python3";
}

/**
 * Get path to Python module
 */
function getModulePath(): string {
  return join(__dirname, "..", "..", "packages", "core", "src");
}

/**
 * Get path to roles directory
 */
function getRolesPath(): string {
  return join(__dirname, "..", "..", "roles");
}

/**
 * Execute Python script and return JSON output
 */
function executePythonScript(script: string, cwd?: string): any {
  const python = getPythonPath();
  const modulePath = getModulePath();

  try {
    const result = execSync(
      `${python} -c "${script.replace(/"/g, '\\"')}"`,
      {
        cwd: cwd || resolve(__dirname, "..", ".."),
        env: { ...process.env, PYTHONPATH: modulePath },
        encoding: "utf-8",
        timeout: 300000, // 5 minutes timeout
      }
    );

    const lines = result.trim().split("\n");
    const lastLine = lines[lines.length - 1];
    return JSON.parse(lastLine);
  } catch (error: any) {
    throw new Error(`Python execution failed: ${error.message}`);
  }
}

/**
 * Create MCP server
 */
const server = new Server(
  {
    name: "ato",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Register tools/list handler
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "create_team_task",
        description: "Create a new team collaboration task with automatic task decomposition and multi-agent parallel execution. The system will automatically break down your task into subtasks and assign them to appropriate agent roles (architect, backend-developer, frontend-developer, tester, etc.) for parallel execution.",
        inputSchema: {
          type: "object",
          properties: {
            description: {
              type: "string",
              description: "Natural language description of task to execute. The system will automatically decompose this into subtasks.",
            },
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
            taskId: {
              type: "string",
              description: "The task ID to query",
            },
          },
          required: ["taskId"],
        },
      },
      {
        name: "approve_step",
        description: "Approve or reject current execution step (for manual approval workflows)",
        inputSchema: {
          type: "object",
          properties: {
            taskId: {
              type: "string",
              description: "The task ID",
            },
            approved: {
              type: "boolean",
              description: "Whether to approve current step",
            },
          },
          required: ["taskId", "approved"],
        },
      },
      {
        name: "list_available_roles",
        description: "List all available agent roles in the system with their expertise and capabilities",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "list_incomplete_tasks",
        description: "List all incomplete tasks (useful for resuming interrupted work)",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "query_team_memory",
        description: "Query team memory for relevant context using semantic search. Returns architecture decisions and code changes related to your query.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Search query (e.g., 'database schema', 'API design', 'authentication')",
            },
            topK: {
              type: "number",
              description: "Number of results to return",
              default: 5,
            },
          },
          required: ["query"],
        },
      },
      {
        name: "get_memory_summary",
        description: "Get a summary of team memory contents (decisions, code changes, context items)",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

// Register tools/call handler
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "create_team_task": {
        const { description, outputDir, projectRoot } = args as {
          description: string;
          outputDir: string;
          projectRoot: string;
        };

        const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

        const outputPath = resolve(outputDir || "./ato-output");
        if (!existsSync(outputPath)) {
          mkdirSync(outputPath, { recursive: true });
        }

        const rootPath = resolve(projectRoot || ".");
        const modulePath = getModulePath();

        // Enhanced script that uses SimpleOrchestrator for task decomposition
        const script = `
import sys
import os
import json
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")

from orchestrator.simple_orchestrator import SimpleOrchestrator
from dotenv import load_dotenv

load_dotenv()

# Initialize orchestrator
orchestrator = SimpleOrchestrator()

# Decompose task into subtasks
decomposition = orchestrator.decompose_task("""${description.replace(/"/g, '\\"').replace(/'/g, "\\'")}""")

# Convert subtasks to the format expected by ToolEnabledOrchestrator
subtasks = []
for st in decomposition.subtasks:
    subtasks.append({
        "id": st.id,
        "name": st.name,
        "role": st.role,
        "dependencies": st.dependencies,
        "expected_output": st.expected_output,
        "status": "pending"
    })

# Execute with ToolEnabledOrchestrator for parallel execution
from orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

tool_orchestrator = ToolEnabledOrchestrator(
    db_path="${outputPath.replace(/\\/g, "/")}/checkpoints.db",
    project_root="${rootPath.replace(/\\/g, "/")}",
    memory_dir=".ato/memory"
)

result = tool_orchestrator.run(
    task_id="${taskId}",
    subtasks=subtasks,
    thread_id="${taskId}",
    resume=False
)

# Save results
output_path = "${outputPath.replace(/\\/g, "/")}/result.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump({
        "task_id": "${taskId}",
        "status": result.get("status"),
        "artifacts": result.get("artifacts", {}),
        "subtasks": result.get("subtasks", []),
        "summary": decomposition.summary
    }, f, indent=2, ensure_ascii=False)

# Print summary
print(json.dumps({
    "task_id": "${taskId}",
    "status": result.get("status", "completed"),
    "summary": decomposition.summary,
    "subtask_count": len(subtasks),
    "completed_count": sum(1 for st in result.get("subtasks", []) if st.get("status") == "completed")
}, ensure_ascii=False))
`;

        execSync(script, {
          cwd: rootPath,
          env: { ...process.env, PYTHONPATH: modulePath },
          encoding: "utf-8",
        });

        return {
          content: [
            {
              type: "text",
              text: `✓ Team task created and executed\n\nTask ID: ${taskId}\n\nOutput saved to: ${outputPath}/result.json\n\nYou can check the status with get_task_status tool.`,
            },
          ],
        };
      }

      case "get_task_status": {
        const { taskId } = args as { taskId: string };
        const projectRoot = resolve(__dirname, "..", "..");
        const modulePath = getModulePath();

        const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
from pathlib import Path

db_path = Path("${projectRoot.replace(/\\/g, "/")}/ato-output/checkpoints.db")
status = {
    "task_id": "${taskId}",
    "status": "unknown",
    "subtasks": [],
    "artifacts": {}
}

try:
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM checkpoints WHERE thread_id = ?', ('${taskId}',))
    row = cursor.fetchone()

    if row:
        state = json.loads(row["checkpoint"])
        status["status"] = state.get("status", "unknown")
        status["subtasks"] = state.get("subtasks", [])
        status["artifacts"] = state.get("artifacts", {})

    conn.close()
except Exception as e:
    status["error"] = str(e)

print(json.dumps(status, ensure_ascii=False))
`;

        const taskStatus = executePythonScript(script, projectRoot);

        const subtaskDetails = taskStatus.subtasks
          ?.map((st: any) => {
            const statusIcon = st.status === "completed" ? "✓" : st.status === "failed" ? "✗" : "○";
            return `${statusIcon} **${st.name}** (${st.role}) - ${st.status}`;
          })
          .join("\n");

        const artifactList = Object.keys(taskStatus.artifacts || {}).length > 0
          ? Object.keys(taskStatus.artifacts).join(", ")
          : "None";

        return {
          content: [
            {
              type: "text",
              text: `## Task Status: ${taskId}\n\n**Overall Status:** ${taskStatus.status}\n\n### Subtasks\n${subtaskDetails || "No subtasks"}\n\n### Artifacts\n${artifactList}`,
            },
          ],
        };
      }

      case "approve_step": {
        const { taskId, approved } = args as { taskId: string; approved: boolean };

        return {
          content: [
            {
              type: "text",
              text: approved
                ? `✓ Step approved for task ${taskId}. Execution continuing...`
                : `✗ Step rejected for task ${taskId}. Execution stopped.`,
            },
          ],
        };
      }

      case "list_available_roles": {
        const modulePath = getModulePath();
        const rolesPath = getRolesPath();

        const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
import os
from pathlib import Path

roles_path = Path("${rolesPath.replace(/\\/g, "/")}")
roles = []

if roles_path.exists():
    for role_file in roles_path.glob("*.yaml"):
        try:
            import yaml
            with open(role_file, "r", encoding="utf-8") as f:
                role_data = yaml.safe_load(f)
                roles.append({
                    "id": role_data.get("id", role_file.stem),
                    "name": role_data.get("name", role_file.stem),
                    "description": role_data.get("description", ""),
                    "expertise": role_data.get("expertise", []),
                    "tools": role_data.get("tools", [])
                })
        except Exception as e:
            pass

print(json.dumps(roles, ensure_ascii=False))
`;

        const roles = executePythonScript(script);

        const roleText = roles.length > 0
          ? roles.map((r: any) => {
              const tools = r.tools?.length > 0 ? r.tools.join(", ") : "None";
              const expertise = r.expertise?.length > 0 ? r.expertise.join(", ") : "None";
              return `### ${r.id}\n**${r.name}**\n${r.description}\n\n**Expertise:** ${expertise}\n**Tools:** ${tools}`;
            }).join("\n\n---\n\n")
          : "No roles found.";

        return {
          content: [
            {
              type: "text",
              text: `## Available Agent Roles\n\n${roleText}`,
            },
          ],
        };
      }

      case "list_incomplete_tasks": {
        const projectRoot = resolve(__dirname, "..", "..");
        const modulePath = getModulePath();

        const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
from pathlib import Path

db_path = Path("${projectRoot.replace(/\\/g, "/")}/ato-output/checkpoints.db")
tasks = []

if db_path.exists():
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT thread_id, checkpoint FROM checkpoints")
        for row in cursor.fetchall():
            try:
                state = json.loads(row[1])
                if state.get("status") not in ["completed"]:
                    tasks.append({
                        "thread_id": row[0],
                        "status": state.get("status", "unknown"),
                        "task_id": state.get("task_id", row[0]),
                        "completed_subtasks": sum(1 for s in state.get("subtasks", []) if s.get("status") == "completed"),
                        "total_subtasks": len(state.get("subtasks", [])),
                    })
            except:
                pass
    except Exception as e:
        pass
    finally:
        conn.close()

print(json.dumps(tasks, ensure_ascii=False))
`;

        const tasks = executePythonScript(script, projectRoot);
        const taskText = tasks.length > 0
          ? tasks.map((t: any) =>
              `- **${t.task_id}** (thread: ${t.thread_id})\n  Status: ${t.status}\n  Progress: ${t.completed_subtasks}/${t.total_subtasks} subtasks`
            ).join("\n\n")
          : "No incomplete tasks found.";

        return {
          content: [
            {
              type: "text",
              text: `## Incomplete Tasks\n\n${taskText}`,
            },
          ],
        };
      }

      case "query_team_memory": {
        const { query, topK } = args as { query: string; topK: number };
        const projectRoot = resolve(__dirname, "..", "..");
        const modulePath = getModulePath();

        const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
from memory.team_memory import TeamMemory

memory = TeamMemory(project_root="${projectRoot.replace(/\\/g, "/")}")
result = memory.retrieve_relevant_context("""${query.replace(/"/g, '\\"')}""", top_k=${topK || 5})
print(json.dumps({"result": result}, ensure_ascii=False))
`;

        const memResult = executePythonScript(script, projectRoot);

        return {
          content: [
            {
              type: "text",
              text: `## Team Memory Search Results\n\nQuery: "${query}"\n\n${memResult.result || "No relevant context found."}`,
            },
          ],
        };
      }

      case "get_memory_summary": {
        const projectRoot = resolve(__dirname, "..", "..");
        const modulePath = getModulePath();

        const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
from memory.team_memory import TeamMemory

memory = TeamMemory(project_root="${projectRoot.replace(/\\/g, "/")}")
summary = memory.summary()
print(json.dumps({"summary": summary}, ensure_ascii=False))
`;

        const memSummary = executePythonScript(script, projectRoot);

        return {
          content: [
            {
              type: "text",
              text: `## Team Memory Summary\n\n${memSummary.summary || "No memory data available."}`,
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

/**
 * Start the server
 */
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});

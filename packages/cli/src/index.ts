#!/usr/bin/env node

import { Command } from "commander";
import { spawn, execSync } from "child_process";
import { join, resolve } from "path";
import { existsSync, mkdirSync, writeFileSync, readFileSync, unlinkSync } from "fs";
import dotenv from "dotenv";
import chalk from "chalk";
import ora from "ora";

// Load environment variables
dotenv.config();

const program = new Command();

/**
 * Get to path to Python virtual environment
 */
function getPythonPath(): string {
  // Check for virtual environment in order of preference
  const venvPaths = [
    join(process.cwd(), ".venv", "bin", "python"),
    join(process.cwd(), ".venv", "Scripts", "python.exe"), // Windows
    join(process.cwd(), "venv", "bin", "python"),
    join(process.cwd(), "venv", "Scripts", "python.exe"), // Windows
    "python3",
    "python",
  ];

  for (const path of venvPaths) {
    if (path === "python3" || path === "python") {
      // These are system Pythons, always available
      return path;
    }
    if (existsSync(path)) {
      return path;
    }
  }

  return "python3";
}

/**
 * Get path to core Python module (parent of src/ so relative imports work)
 */
function getModulePath(): string {
  const corePath = join(process.cwd(), "packages", "core");
  if (existsSync(join(corePath, "src"))) {
    return corePath;
  }
  // Fallback for installed package
  return join(__dirname, "..", "..", "core");
}

/**
 * Get project root path
 */
function getProjectRoot(): string {
  const corePath = join(process.cwd(), "packages", "core", "src");
  if (existsSync(corePath)) {
    return process.cwd();
  }
  // Fallback to __dirname for installed package
  return resolve(__dirname, "..", "..");
}

/**
 * Execute Python script and return JSON output
 */
function executePythonScript(script: string, cwd?: string): any {
  const python = getPythonPath();
  const modulePath = getModulePath();
  const projectRoot = cwd || getProjectRoot();

  // Write script to temp file to avoid issues with spaces in paths
  const tempScript = join(projectRoot, "ato-output", ".temp_query.py");
  mkdirSync(join(projectRoot, "ato-output"), { recursive: true });
  writeFileSync(tempScript, script);

  try {
    const result = execSync(
      `"${python}" "${tempScript}"`,
      {
        cwd: projectRoot,
        env: { ...process.env, PYTHONPATH: modulePath },
        encoding: "utf-8",
        timeout: 300000, // 5 minutes
      }
    );

    // Clean up temp file
    try {
      if (existsSync(tempScript)) {
        unlinkSync(tempScript);
      }
    } catch (e) {
      // Ignore cleanup errors
    }

    const lines = result.trim().split("\n");
    const lastLine = lines[lines.length - 1];
    return JSON.parse(lastLine);
  } catch (error: any) {
    // Clean up temp file on error
    try {
      if (existsSync(tempScript)) {
        unlinkSync(tempScript);
      }
    } catch (e) {
      // Ignore cleanup errors
    }
    throw new Error(`Python execution failed: ${error.message}`);
  }
}

/**
 * Execute Python script with streaming output
 */
async function executePythonScriptWithOutput(
  script: string,
  cwd?: string
): Promise<{ exitCode: number }> {
  return new Promise((resolve, reject) => {
    const python = getPythonPath();
    const modulePath = getModulePath();
    const projectRoot = cwd || getProjectRoot();

    const tempScript = join(projectRoot, "ato-output", ".temp_script.py");
    mkdirSync(join(projectRoot, "ato-output"), { recursive: true });
    writeFileSync(tempScript, script);

    const proc = spawn(python, [tempScript], {
      cwd: projectRoot,
      env: { ...process.env, PYTHONPATH: modulePath },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      const text = data.toString();
      stdout += text;
      process.stdout.write(text);
    });

    proc.stderr.on("data", (data) => {
      const text = data.toString();
      stderr += text;
      process.stderr.write(chalk.dim(text));
    });

    proc.on("close", (code) => {
      // Clean up temp file
      try {
        if (existsSync(tempScript)) {
          unlinkSync(tempScript);
        }
      } catch (e) {
        // Ignore cleanup errors
      }
      resolve({ exitCode: code ?? 0 });
    });

    proc.on("error", (err) => {
      reject(err);
    });
  });
}

/**
 * Check for API key
 */
function checkApiKey(): string | null {
  const provider = process.env.LLM_PROVIDER || "anthropic";
  const apiKey =
    provider === "anthropic"
      ? process.env.ANTHROPIC_API_KEY
      : provider === "openai"
        ? process.env.OPENAI_API_KEY
        : process.env.OLLAMA_BASE_URL;

  if (!apiKey && provider !== "ollama") {
    console.error(
      chalk.red("Error:"),
      `No API key found. Please set ${provider === "anthropic" ? "ANTHROPIC_API_KEY" : "OPENAI_API_KEY"} in your environment.`
    );
    console.log(chalk.dim("You can also create a .env file with your API key."));
    return null;
  }

  return apiKey ?? null;
}

/**
 * Run a task through the orchestrator
 */
async function runTask(description: string, options: { output: string }) {
  console.log(chalk.cyan.bold("\n🚀 Agent Team Orchestrator\n"));
  console.log(chalk.dim("Task:"), description);
  console.log();

  if (!checkApiKey()) {
    process.exit(1);
  }

  const projectRoot = getProjectRoot();
  const modulePath = getModulePath();
  const outputDir = resolve(options.output);

  if (!existsSync(outputDir)) {
    mkdirSync(outputDir, { recursive: true });
  }

  const spinner = ora("Starting task execution...").start();

  try {
    // Generate task ID
    const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    const script = `
import sys
import json
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")

from src.orchestrator.simple_orchestrator import SimpleOrchestrator
from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator
from dotenv import load_dotenv

load_dotenv()

# Step 1: Decompose task into subtasks (same as MCP Server)
simple_orchestrator = SimpleOrchestrator()
decomposition = simple_orchestrator.decompose_task("""${description.replace(/"/g, '\\"').replace(/'/g, "\\'")}""")

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

# Step 2: Execute with ToolEnabledOrchestrator for parallel execution
tool_orchestrator = ToolEnabledOrchestrator(
    db_path="${outputDir.replace(/\\/g, "/")}/checkpoints.db",
    project_root="${projectRoot.replace(/\\/g, "/")}",
    memory_dir=".ato/memory"
)

result = tool_orchestrator.run(
    task_id="${taskId}",
    subtasks=subtasks,
    thread_id="${taskId}",
    resume=False
)

# Step 3: Save results
output_path = "${outputDir.replace(/\\/g, "/")}/result.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump({
        "task_id": "${taskId}",
        "status": result.get("status"),
        "artifacts": result.get("artifacts", {}),
        "subtasks": result.get("subtasks", []),
        "summary": decomposition.summary
    }, f, indent=2, ensure_ascii=False)

print(json.dumps({
    "task_id": "${taskId}",
    "status": result.get("status", "completed"),
    "summary": decomposition.summary,
    "subtask_count": len(subtasks),
    "completed_count": sum(1 for st in result.get("subtasks", []) if st.get("status") == "completed")
}, ensure_ascii=False))
`;

    spinner.stop();

    const result = await executePythonScriptWithOutput(script, projectRoot);

    console.log();
    if (result.exitCode === 0) {
      console.log(chalk.green.bold("✓ Task completed successfully!"));
      console.log(chalk.dim("Output saved to:"), chalk.cyan(outputDir));
    } else {
      console.log(chalk.red.bold("✗ Task failed with exit code:"), result.exitCode);
    }
  } catch (error) {
    spinner.stop();
    console.error(chalk.red.bold("✗ Error:"), error);
    process.exit(1);
  }
}

/**
 * List available roles
 */
async function listRoles() {
  console.log(chalk.cyan.bold("\n📋 Available Roles\n"));

  const modulePath = getModulePath();
  const projectRoot = getProjectRoot();

  const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
from src.models.role import RoleLoader

loader = RoleLoader()
roles = loader.list_roles()

role_list = []
for role_id in roles:
    role = loader.load(role_id)
    role_list.append({
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "expertise": role.expertise
    })

print(json.dumps(role_list, ensure_ascii=False))
`;

  try {
    const roles = executePythonScript(script, projectRoot);

    if (Array.isArray(roles) && roles.length > 0) {
      for (const role of roles) {
        console.log(chalk.bold(role.id) + chalk.dim(` - ${role.name}`));
        console.log(chalk.dim(`  ${role.description}`));
        if (role.expertise && role.expertise.length > 0) {
          console.log(chalk.dim(`  Expertise: ${role.expertise.join(", ")}`));
        }
        console.log();
      }
    } else {
      console.log(chalk.dim("No roles found."));
    }
  } catch (error) {
    console.error(chalk.red("Error loading roles:"), error);
    process.exit(1);
  }
}

/**
 * Get task status
 */
async function getTaskStatus(taskId: string) {
  console.log(chalk.cyan.bold("\n📊 Task Status\n"));

  const projectRoot = getProjectRoot();
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

  try {
    const taskStatus = executePythonScript(script, projectRoot);

    console.log(chalk.bold("Task ID:"), taskStatus.task_id);
    console.log(chalk.bold("Status:"), getStatusColor(taskStatus.status, taskStatus.status));
    console.log();

    if (taskStatus.subtasks && taskStatus.subtasks.length > 0) {
      console.log(chalk.bold("Subtasks:"));
      for (const st of taskStatus.subtasks) {
        console.log(
          `  ${getStatusIcon(st.status)} ${st.name || st.id}: ${getStatusColor(st.status, st.status)}`
        );
      }
      console.log();
    }

    const artifactCount = Object.keys(taskStatus.artifacts || {}).length;
    console.log(chalk.bold("Artifacts:"), artifactCount > 0 ? `${artifactCount} items` : "None");
  } catch (error) {
    console.error(chalk.red("Error getting task status:"), error);
    process.exit(1);
  }
}

/**
 * List incomplete tasks
 */
async function listIncompleteTasks() {
  console.log(chalk.cyan.bold("\n📋 Incomplete Tasks\n"));

  const projectRoot = getProjectRoot();
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

  try {
    const tasks = executePythonScript(script, projectRoot);

    if (tasks.length > 0) {
      for (const t of tasks) {
        console.log(
          chalk.bold(`  ${t.task_id}`) + chalk.dim(` (thread: ${t.thread_id})`)
        );
        console.log(
          `    Status: ${getStatusColor(t.status, t.status)}`
        );
        console.log(
          `    Progress: ${t.completed_subtasks}/${t.total_subtasks} subtasks`
        );
        console.log();
      }
    } else {
      console.log(chalk.dim("No incomplete tasks found."));
    }
  } catch (error) {
    console.error(chalk.red("Error listing tasks:"), error);
    process.exit(1);
  }
}

/**
 * Get memory summary
 */
async function getMemorySummary() {
  console.log(chalk.cyan.bold("\n📚 Team Memory Summary\n"));

  const projectRoot = getProjectRoot();
  const modulePath = getModulePath();

  const script = `
import sys
sys.path.insert(0, "${modulePath.replace(/\\/g, "/")}")
import json
from src.memory.team_memory import TeamMemory

memory = TeamMemory(project_root="${projectRoot.replace(/\\/g, "/")}")
summary = memory.summary()
print(json.dumps({"summary": summary}, ensure_ascii=False))
`;

  try {
    const mem = executePythonScript(script, projectRoot);
    console.log(mem.summary);
  } catch (error) {
    console.error(chalk.red("Error getting memory summary:"), error);
    process.exit(1);
  }
}

/**
 * Get status color
 */
function getStatusColor(status: string, text: string): string {
  switch (status) {
    case "completed":
      return chalk.green(text);
    case "running":
      return chalk.blue(text);
    case "failed":
      return chalk.red(text);
    case "pending":
      return chalk.dim(text);
    default:
      return chalk.yellow(text);
  }
}

/**
 * Get status icon
 */
function getStatusIcon(status: string): string {
  switch (status) {
    case "completed":
      return chalk.green("✓");
    case "running":
      return chalk.blue("⟳");
    case "failed":
      return chalk.red("✗");
    case "pending":
      return chalk.dim("○");
    default:
      return chalk.yellow("?");
  }
}

// Configure CLI
program
  .name("ato")
  .description("Agent Team Orchestrator - Multi-agent collaboration CLI")
  .version("0.1.0");

program
  .command("run <task>")
  .description("Run a task through the agent team")
  .option("-o, --output <dir>", "Output directory for artifacts", "./ato-output")
  .action(runTask);

program
  .command("roles")
  .description("List all available roles")
  .action(listRoles);

program
  .command("status <taskId>")
  .description("Get the status of a task")
  .action(getTaskStatus);

program
  .command("tasks")
  .description("List all incomplete tasks")
  .action(listIncompleteTasks);

program
  .command("memory")
  .description("Get team memory summary")
  .action(getMemorySummary);

program
  .command("init")
  .description("Initialize a new ATO project")
  .action(() => {
    console.log(chalk.cyan.bold("\n🔧 Initializing ATO project...\n"));

    // Create directories
    const dirs = ["roles", "examples", "ato-output", ".ato"];
    for (const dir of dirs) {
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true });
        console.log(chalk.green("✓"), `Created ${dir}/`);
      } else {
        console.log(chalk.dim("○"), `${dir}/ already exists`);
      }
    }

    // Create .env from example
    const envExample = join(process.cwd(), ".env.example");
    const envFile = join(process.cwd(), ".env");
    if (existsSync(envExample) && !existsSync(envFile)) {
      const content = readFileSync(envExample, "utf-8");
      writeFileSync(envFile, content);
      console.log(chalk.green("✓"), "Created .env (please add your API key)");
    }

    console.log();
    console.log(chalk.green.bold("✓ Project initialized!"));
    console.log();
    console.log("Next steps:");
    console.log(chalk.dim("  1. Edit .env and add your API key"));
    console.log(chalk.dim("  2. Run: ato run \"Your task description\""));
    console.log();
  });

// Parse arguments
program.parse();

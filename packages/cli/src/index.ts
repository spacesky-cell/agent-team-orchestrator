#!/usr/bin/env node

import chalk from "chalk";
import { Command } from "commander";
import dotenv from "dotenv";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import ora from "ora";
import { join, resolve } from "path";
import {
  executePythonJson,
  executePythonStreaming,
  getCoreModulePath,
  getProjectRoot,
  getPythonPath,
  readAuditSummary,
} from "@spacesky-cell/ato-shared";

dotenv.config();

const program = new Command();

function checkApiKey(): boolean {
  const provider = process.env.LLM_PROVIDER || "claude-cli";
  if (provider === "claude-cli" || provider === "ollama") {
    return true;
  }

  const apiKey =
    provider === "anthropic"
      ? process.env.ANTHROPIC_API_KEY
      : provider === "openai"
        ? process.env.OPENAI_API_KEY
        : undefined;

  if (!apiKey) {
    const variable = provider === "anthropic" ? "ANTHROPIC_API_KEY" : "OPENAI_API_KEY";
    console.error(chalk.red("Error:"), `No API key found. Set ${variable} first.`);
    console.log(chalk.dim("You can create a .env file from .env.example."));
    return false;
  }

  return true;
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

function buildStatusScript(): string {
  return `
import json
from pathlib import Path

payload = json.loads(input_path.read_text(encoding="utf-8"))
task_id = payload["task_id"]
output_dir = Path(payload["output_dir"])
status = {"task_id": task_id, "status": "unknown", "subtasks": [], "artifacts": {}}

result_path = output_dir / "result.json"
if result_path.exists():
    data = json.loads(result_path.read_text(encoding="utf-8"))
    if data.get("task_id") == task_id:
        data["source"] = "result.json"
        print(json.dumps(data, ensure_ascii=False))
        raise SystemExit(0)

db_path = output_dir / "checkpoints.db"
if db_path.exists():
    status["status"] = "checkpoint_found"
    status["source"] = "checkpoint"

print(json.dumps(status, ensure_ascii=False))
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
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "completed":
        tasks.append({
            "task_id": result.get("task_id"),
            "status": result.get("status", "unknown"),
            "completed_subtasks": sum(1 for s in result.get("subtasks", []) if s.get("status") == "completed"),
            "total_subtasks": len(result.get("subtasks", [])),
        })
print(json.dumps(tasks, ensure_ascii=False))
`;
}

function buildMemoryScript(): string {
  return `
import json
from src.memory.team_memory import TeamMemory

payload = json.loads(input_path.read_text(encoding="utf-8"))
memory = TeamMemory(project_root=payload["project_root"])
print(json.dumps({"summary": memory.summary()}, ensure_ascii=False))
`;
}

function buildDoctorScript(): string {
  return `
import json
import os
import shutil
import subprocess
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

function printAuditSummary(outputDir: string) {
  const audit = readAuditSummary(outputDir);
  console.log(chalk.bold("Audit file:"), audit.path);
  console.log(
    chalk.bold("Audit events:"),
    `${audit.total} completed=${audit.completed} blocked=${audit.blocked} failed=${audit.failed} parseErrors=${audit.parseErrors}`,
  );
  if (audit.recent.length > 0) {
    console.log(chalk.bold("Recent tool calls:"));
    for (const event of audit.recent) {
      const error = event.error ? chalk.red(` - ${event.error}`) : "";
      console.log(
        `  - ${event.tool_name || "unknown"} [${event.status || "unknown"}, ${event.decision || "unknown"}]${error}`,
      );
    }
  } else {
    console.log(chalk.dim("No audit events found."));
  }
}

async function runTask(description: string, options: { output: string }) {
  console.log(chalk.cyan.bold("\nAgent Team Orchestrator\n"));
  console.log(chalk.dim("Task:"), description);
  console.log();

  if (!checkApiKey()) {
    process.exit(1);
  }

  const projectRoot = getProjectRoot(process.cwd());
  const outputDir = resolve(options.output);
  mkdirSync(outputDir, { recursive: true });
  const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const spinner = ora("Starting task execution...").start();

  try {
    spinner.stop();
    const result = await executePythonStreaming({
      script: buildTaskScript(),
      cwd: projectRoot,
      input: {
        description,
        task_id: taskId,
        output_dir: outputDir,
        project_root: projectRoot,
      },
    });

    console.log();
    if (result.exitCode === 0) {
      console.log(chalk.green.bold("Task completed successfully."));
      console.log(chalk.dim("Output saved to:"), chalk.cyan(outputDir));
      console.log(chalk.dim("Tool audit:"), chalk.cyan(join(outputDir, "tool-audit.jsonl")));
    } else {
      console.log(chalk.red.bold("Task failed with exit code:"), result.exitCode);
      process.exit(result.exitCode);
    }
  } catch (error: any) {
    spinner.stop();
    console.error(chalk.red.bold("Error:"), error.message || error);
    process.exit(1);
  }
}

async function listRoles() {
  const projectRoot = getProjectRoot(process.cwd());
  const roles = executePythonJson<any[]>({ script: buildRolesScript(), cwd: projectRoot });

  console.log(chalk.cyan.bold("\nAvailable Roles\n"));
  for (const role of roles) {
    console.log(chalk.bold(role.id) + chalk.dim(` - ${role.name}`));
    console.log(chalk.dim(`  ${role.description}`));
    console.log(chalk.dim(`  Tools: ${role.tools.join(", ")}`));
    console.log();
  }
}

async function getTaskStatus(taskId: string, options: { output: string }) {
  const projectRoot = getProjectRoot(process.cwd());
  const outputDir = resolve(options.output);
  const taskStatus = executePythonJson<any>({
    script: buildStatusScript(),
    cwd: projectRoot,
    input: { task_id: taskId, output_dir: outputDir },
  });

  console.log(chalk.cyan.bold("\nTask Status\n"));
  console.log(chalk.bold("Task ID:"), taskStatus.task_id);
  console.log(chalk.bold("Status:"), taskStatus.status);
  console.log(chalk.bold("Source:"), taskStatus.source || "none");
  console.log(chalk.bold("Artifacts:"), Object.keys(taskStatus.artifacts || {}).length);
  console.log();
  printAuditSummary(outputDir);
}

async function listIncompleteTasks(options: { output: string }) {
  const projectRoot = getProjectRoot(process.cwd());
  const tasks = executePythonJson<any[]>({
    script: buildTasksScript(),
    cwd: projectRoot,
    input: { output_dir: resolve(options.output) },
  });

  console.log(chalk.cyan.bold("\nIncomplete Tasks\n"));
  if (tasks.length === 0) {
    console.log(chalk.dim("No incomplete tasks found."));
    return;
  }

  for (const task of tasks) {
    console.log(chalk.bold(task.task_id));
    console.log(`  Status: ${task.status}`);
    console.log(`  Progress: ${task.completed_subtasks}/${task.total_subtasks}`);
  }
}

async function getMemorySummary() {
  const projectRoot = getProjectRoot(process.cwd());
  const memory = executePythonJson<{ summary: string }>({
    script: buildMemoryScript(),
    cwd: projectRoot,
    input: { project_root: projectRoot },
  });
  console.log(chalk.cyan.bold("\nTeam Memory Summary\n"));
  console.log(memory.summary);
}

async function doctor() {
  const projectRoot = getProjectRoot(process.cwd());
  const result = executePythonJson<any>({
    script: buildDoctorScript(),
    cwd: projectRoot,
    input: {
      project_root: projectRoot,
      core_module_path: getCoreModulePath(projectRoot),
    },
  });

  console.log(chalk.cyan.bold("\nATO Doctor\n"));
  console.log("Project root:", projectRoot);
  console.log("Python command:", getPythonPath(projectRoot));
  console.log("Python executable:", result.python);
  console.log("Core module path:", result.core_module_path);
  console.log("Roles:", result.roles.join(", "));
  console.log("LLM provider:", result.env.LLM_PROVIDER);
  console.log("ANTHROPIC_API_KEY:", result.env.ANTHROPIC_API_KEY);
  console.log("OPENAI_API_KEY:", result.env.OPENAI_API_KEY);
  console.log("OLLAMA_BASE_URL:", result.env.OLLAMA_BASE_URL);
  console.log("Claude CLI:", result.env.CLAUDE_CLI);
}

async function getTaskAudit(options: { output: string }) {
  console.log(chalk.cyan.bold("\nTool Audit\n"));
  printAuditSummary(resolve(options.output));
}

program
  .name("ato")
  .description("Agent Team Orchestrator - Multi-agent collaboration CLI")
  .version("0.1.0");

program
  .command("run <task>")
  .description("Run a task through the agent team")
  .option("-o, --output <dir>", "Output directory for artifacts", "./ato-output")
  .action(runTask);

program.command("roles").description("List all available roles").action(listRoles);

program
  .command("status <taskId>")
  .description("Get the status of a task")
  .option("-o, --output <dir>", "Output directory for artifacts", "./ato-output")
  .action(getTaskStatus);

program
  .command("audit")
  .description("Summarize tool execution audit events")
  .option("-o, --output <dir>", "Output directory for artifacts", "./ato-output")
  .action(getTaskAudit);

program
  .command("tasks")
  .description("List all incomplete tasks")
  .option("-o, --output <dir>", "Output directory for artifacts", "./ato-output")
  .action(listIncompleteTasks);

program.command("memory").description("Get team memory summary").action(getMemorySummary);

program.command("doctor").description("Run install/configuration smoke checks").action(doctor);

program.command("init").description("Initialize a new ATO project").action(() => {
  console.log(chalk.cyan.bold("\nInitializing ATO project...\n"));

  const dirs = ["roles", "examples", "ato-output", ".ato"];
  for (const dir of dirs) {
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
      console.log(chalk.green("created"), `${dir}/`);
    } else {
      console.log(chalk.dim("exists"), `${dir}/`);
    }
  }

  const envExample = join(process.cwd(), ".env.example");
  const envFile = join(process.cwd(), ".env");
  if (existsSync(envExample) && !existsSync(envFile)) {
    const content = readFileSync(envExample, "utf-8");
    writeFileSync(envFile, content);
    console.log(chalk.green("created"), ".env (please add your API key)");
  }

  console.log();
  console.log(chalk.green.bold("Project initialized."));
  console.log(chalk.dim('Next: edit .env and run ato run "Your task description"'));
});

program.parse();

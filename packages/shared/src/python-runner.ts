import { execFileSync, spawn } from "child_process";
import { existsSync, mkdirSync, unlinkSync, writeFileSync } from "fs";
import { delimiter, join, resolve } from "path";
import { randomUUID } from "crypto";

export interface PythonRunnerOptions {
  script: string;
  input?: unknown;
  cwd?: string;
  timeoutMs?: number;
  streamOutput?: boolean;
}

export interface PythonProcessResult {
  exitCode: number;
}

function parseLastJsonLine<T>(output: string): T {
  const lines = output.trim().split(/\r?\n/).filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      return JSON.parse(lines[index]) as T;
    } catch {
      // Keep scanning upward; Python libraries may print warnings after JSON.
    }
  }
  throw new Error(`No JSON object found in Python output:\n${output}`);
}

export function getProjectRoot(cwd = process.cwd()): string {
  const candidate = resolve(cwd);
  if (existsSync(join(candidate, "packages", "core", "src"))) {
    return candidate;
  }

  const fromSharedDist = resolve(cwd, "..", "..");
  if (existsSync(join(fromSharedDist, "packages", "core", "src"))) {
    return fromSharedDist;
  }

  return candidate;
}

export function getCoreModulePath(cwd = process.cwd()): string {
  const projectRoot = getProjectRoot(cwd);
  return join(projectRoot, "packages", "core");
}

export function getPythonPath(cwd = process.cwd()): string {
  const projectRoot = getProjectRoot(cwd);
  const candidates = [
    join(projectRoot, ".venv", "bin", "python"),
    join(projectRoot, ".venv", "Scripts", "python.exe"),
    join(projectRoot, "venv", "bin", "python"),
    join(projectRoot, "venv", "Scripts", "python.exe"),
    ...(process.platform === "win32" ? ["python", "python3"] : ["python3", "python"]),
  ];

  for (const candidate of candidates) {
    if (candidate === "python3" || candidate === "python") {
      return candidate;
    }
    if (existsSync(candidate)) {
      return candidate;
    }
  }

  return "python3";
}

function getRunnerPaths(projectRoot: string): { outputDir: string; scriptPath: string; inputPath: string } {
  const outputDir = join(projectRoot, "ato-output");
  const runId = randomUUID();
  return {
    outputDir,
    scriptPath: join(outputDir, `.runner-${runId}.py`),
    inputPath: join(outputDir, `.runner-input-${runId}.json`),
  };
}

function cleanup(paths: { scriptPath: string; inputPath: string }): void {
  for (const path of [paths.scriptPath, paths.inputPath]) {
    try {
      if (existsSync(path)) {
        unlinkSync(path);
      }
    } catch {
      // Best-effort cleanup. The next run overwrites these files.
    }
  }
}

function wrapScript(script: string): string {
  return `
import json
from pathlib import Path

input_path = Path(__import__("os").environ["ATO_RUNNER_INPUT"])

${script}
`;
}

function buildEnv(projectRoot: string): NodeJS.ProcessEnv {
  const modulePath = getCoreModulePath(projectRoot);
  const existingPythonPath = process.env.PYTHONPATH;
  return {
    ...process.env,
    PYTHONPATH: existingPythonPath ? `${modulePath}${delimiter}${existingPythonPath}` : modulePath,
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
  };
}

export function executePythonJson<T = any>(options: PythonRunnerOptions): T {
  const projectRoot = getProjectRoot(options.cwd);
  const paths = getRunnerPaths(projectRoot);
  mkdirSync(paths.outputDir, { recursive: true });

  writeFileSync(paths.scriptPath, wrapScript(options.script), { encoding: "utf-8" });
  writeFileSync(paths.inputPath, JSON.stringify(options.input ?? {}, null, 2), {
    encoding: "utf-8",
  });

  try {
    const output = execFileSync(getPythonPath(projectRoot), [paths.scriptPath], {
      cwd: projectRoot,
      env: { ...buildEnv(projectRoot), ATO_RUNNER_INPUT: paths.inputPath },
      encoding: "utf-8",
      timeout: options.timeoutMs ?? 300000,
    });

    return parseLastJsonLine<T>(output);
  } catch (error: any) {
    const stderr = error?.stderr ? `\n${error.stderr}` : "";
    const stdout = error?.stdout ? `\n${error.stdout}` : "";
    throw new Error(
      `Python execution failed with ${getPythonPath(projectRoot)}. PYTHONPATH=${getCoreModulePath(
        projectRoot,
      )}.${stdout}${stderr || `\n${error.message}`}`,
    );
  } finally {
    cleanup(paths);
  }
}

export function executePythonStreaming(options: PythonRunnerOptions): Promise<PythonProcessResult> {
  const projectRoot = getProjectRoot(options.cwd);
  const paths = getRunnerPaths(projectRoot);
  mkdirSync(paths.outputDir, { recursive: true });

  writeFileSync(paths.scriptPath, wrapScript(options.script), { encoding: "utf-8" });
  writeFileSync(paths.inputPath, JSON.stringify(options.input ?? {}, null, 2), {
    encoding: "utf-8",
  });

  return new Promise((resolvePromise, reject) => {
    const child = spawn(getPythonPath(projectRoot), [paths.scriptPath], {
      cwd: projectRoot,
      env: { ...buildEnv(projectRoot), ATO_RUNNER_INPUT: paths.inputPath },
      stdio: options.streamOutput === false ? "pipe" : "inherit",
    });

    child.on("close", (code) => {
      cleanup(paths);
      resolvePromise({ exitCode: code ?? 0 });
    });

    child.on("error", (error) => {
      cleanup(paths);
      reject(error);
    });
  });
}

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { promisify } from "node:util";

import {
  ensureManagedRuntime,
  type ManagedRuntimeOptions,
  type ManagedRuntimeStatus,
} from "./managed-runtime.js";
import type { PythonRuntime } from "./protocol.js";

const execFileAsync = promisify(execFile);

export class PythonDiscoveryError extends Error {
  readonly code = "PYTHON_NOT_FOUND";

  constructor(readonly attempts: string[]) {
    super(`No Python runtime with ato_core was found. Tried: ${attempts.join(", ")}`);
    this.name = "PythonDiscoveryError";
  }
}

export interface DiscoveryOptions {
  projectRoot?: string;
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  probeTimeoutMs?: number;
  managedRuntimeTimeoutMs?: number;
  exists?: (path: string) => boolean;
  probe?: (executable: string, timeoutMs: number) => Promise<PythonRuntime>;
  onManagedRuntimeStatus?: (status: ManagedRuntimeStatus, message: string) => void;
  prepareManagedRuntime?: (
    manifestPath: string,
    options: ManagedRuntimeOptions,
  ) => Promise<PythonRuntime>;
}

async function probePython(executable: string, timeoutMs: number): Promise<PythonRuntime> {
  const script = [
    "import json, platform, ato_core",
    "print(json.dumps({'version': platform.python_version(), 'coreVersion': ato_core.__version__}))",
  ].join("; ");
  const { stdout } = await execFileAsync(executable, ["-c", script], {
    encoding: "utf8",
    timeout: timeoutMs,
    windowsHide: true,
  });
  const payload = JSON.parse(stdout.trim()) as { version?: unknown; coreVersion?: unknown };
  if (typeof payload.version !== "string" || typeof payload.coreVersion !== "string") {
    throw new Error("invalid Python probe response");
  }
  return { executable, version: payload.version, coreVersion: payload.coreVersion };
}

export async function discoverPython(options: DiscoveryOptions = {}): Promise<PythonRuntime> {
  const projectRoot = options.projectRoot ?? process.cwd();
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const exists = options.exists ?? existsSync;
  const probe = options.probe ?? probePython;
  const timeoutMs = options.probeTimeoutMs ?? 5_000;
  const venv =
    platform === "win32"
      ? join(projectRoot, ".venv", "Scripts", "python.exe")
      : join(projectRoot, ".venv", "bin", "python");
  const pathCandidates = platform === "win32" ? ["python", "python3"] : ["python3", "python"];
  const candidates = [env.ATO_PYTHON, exists(venv) ? venv : undefined, ...pathCandidates].filter(
    (candidate): candidate is string => Boolean(candidate),
  );
  const unique = [...new Set(candidates)];
  const attempts: string[] = [];

  for (const candidate of unique) {
    try {
      return await probe(candidate, timeoutMs);
    } catch {
      attempts.push(candidate);
    }
  }
  const manifestPath = env.ATO_BUNDLED_RUNTIME_MANIFEST?.trim();
  if (manifestPath) {
    const prepareManagedRuntime = options.prepareManagedRuntime ?? ensureManagedRuntime;
    return prepareManagedRuntime(manifestPath, {
      env,
      platform,
      onStatus: options.onManagedRuntimeStatus,
      timeoutMs: options.managedRuntimeTimeoutMs,
      basePythonCandidates: unique,
    });
  }
  throw new PythonDiscoveryError(attempts.slice(0, 5));
}

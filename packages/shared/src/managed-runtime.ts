import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  copyFile,
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  unlink,
  writeFile,
  type FileHandle,
} from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, posix, relative, resolve, sep, win32 } from "node:path";

import type { PythonRuntime } from "./protocol.js";

const MANIFEST_FIELDS = ["coreVersion", "packageVersion", "schemaVersion", "sha256", "wheel"];
const MARKER_FIELDS = [
  "completedAt",
  "coreVersion",
  "pythonExecutable",
  "schemaVersion",
  "wheelSha256",
];
const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;
const HASH_PATTERN = /^[a-f0-9]{64}$/;
const DEFAULT_LOCK_TIMEOUT_MS = 180_000;
const STALE_LOCK_MS = 10 * 60_000;
const LOCK_POLL_MS = 500;
const MAX_PROCESS_OUTPUT_BYTES = 1024 * 1024;
const MAX_ERROR_LENGTH = 4_096;

export type ManagedRuntimeStatus = "checking" | "creating" | "installing" | "ready";

export type ManagedRuntimeErrorCode =
  | "PYTHON_NOT_FOUND"
  | "PYTHON_VERSION_UNSUPPORTED"
  | "BUNDLED_RUNTIME_INVALID"
  | "MANAGED_RUNTIME_BUSY"
  | "MANAGED_RUNTIME_INSTALL_FAILED";

export type ManagedRuntimeStage = "python-version" | "venv" | "pip" | "core-probe";

export interface ManagedRuntimeProcess {
  executable: string;
  args: string[];
  timeoutMs: number;
  stage: ManagedRuntimeStage;
}

export interface ManagedRuntimeProcessResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export interface ManagedRuntimeDependencies {
  runProcess: (process: ManagedRuntimeProcess) => Promise<ManagedRuntimeProcessResult>;
  now: () => number;
  sleep: (milliseconds: number) => Promise<void>;
  randomUUID: () => string;
}

export interface ManagedRuntimeOptions {
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  homeDir?: string;
  onStatus?: (status: ManagedRuntimeStatus, message: string) => void;
  timeoutMs?: number;
  basePythonCandidates?: string[];
  /** @internal Test and embedding seam; ordinary callers should use process defaults. */
  dependencies?: Partial<ManagedRuntimeDependencies>;
}

export class ManagedRuntimeError extends Error {
  constructor(
    readonly code: ManagedRuntimeErrorCode,
    message: string,
    readonly stage?: ManagedRuntimeStage,
  ) {
    super(sanitize(message));
    this.name = "ManagedRuntimeError";
  }
}

interface RuntimeManifest {
  schemaVersion: 1;
  packageVersion: string;
  coreVersion: string;
  wheel: string;
  sha256: string;
  wheelPath: string;
}

interface RuntimeMarker {
  schemaVersion: 1;
  coreVersion: string;
  wheelSha256: string;
  pythonExecutable: string;
  completedAt: string;
}

interface RuntimePathOptions {
  env: NodeJS.ProcessEnv;
  platform: NodeJS.Platform;
  homeDir: string;
}

interface PythonVersion {
  executable: string;
  version: string;
}

class ProcessExecutionError extends Error {}

function sanitize(value: string): string {
  return value
    .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, "$1[redacted]@")
    .replace(/((?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s&]+/gi, "$1[redacted]")
    .replace(/\b(?:npm|gh[pousr])_[A-Za-z0-9_-]+\b/g, "[redacted]")
    .replace(/\bsk-[A-Za-z0-9_-]+\b/g, "[redacted]")
    .slice(0, MAX_ERROR_LENGTH);
}

function platformPath(platform: NodeJS.Platform) {
  return platform === "win32" ? win32 : posix;
}

export function resolveManagedRuntimeRoot(
  coreVersion: string,
  options: RuntimePathOptions,
): string {
  const path = platformPath(options.platform);
  const atoHome = options.env.ATO_HOME?.trim();
  if (atoHome) return path.join(atoHome, "runtime", coreVersion);
  if (options.platform === "win32") {
    const localAppData = options.env.LOCALAPPDATA?.trim();
    const base = localAppData || path.join(options.homeDir, "AppData", "Local");
    return path.join(base, "AgentTeamOrchestrator", "runtime", coreVersion);
  }
  if (options.platform === "darwin") {
    return path.join(
      options.homeDir,
      "Library",
      "Application Support",
      "AgentTeamOrchestrator",
      "runtime",
      coreVersion,
    );
  }
  const dataHome = options.env.XDG_DATA_HOME?.trim() || path.join(options.homeDir, ".local", "share");
  return path.join(dataHome, "agent-team-orchestrator", "runtime", coreVersion);
}

function isInside(parent: string, child: string): boolean {
  const path = relative(parent, child);
  return path !== "" && path !== ".." && !path.startsWith(`..${sep}`) && !isAbsolute(path);
}

async function sha256(path: string): Promise<string> {
  const content = await readFile(path);
  return createHash("sha256").update(content).digest("hex");
}

function invalidManifest(message: string): ManagedRuntimeError {
  return new ManagedRuntimeError("BUNDLED_RUNTIME_INVALID", `Bundled runtime manifest is invalid: ${message}`);
}

async function readManifest(manifestPath: string): Promise<RuntimeManifest> {
  let value: unknown;
  try {
    value = JSON.parse(await readFile(manifestPath, "utf8"));
  } catch {
    throw invalidManifest("cannot read valid JSON");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw invalidManifest("expected an object");
  }
  const record = value as Record<string, unknown>;
  if (Object.keys(record).sort().join(",") !== MANIFEST_FIELDS.join(",")) {
    throw invalidManifest("fields do not match schema version 1");
  }
  if (record.schemaVersion !== 1) throw invalidManifest("unsupported schemaVersion");
  if (typeof record.packageVersion !== "string" || !VERSION_PATTERN.test(record.packageVersion)) {
    throw invalidManifest("packageVersion must be major.minor.patch");
  }
  if (typeof record.coreVersion !== "string" || !VERSION_PATTERN.test(record.coreVersion)) {
    throw invalidManifest("coreVersion must be major.minor.patch");
  }
  if (record.packageVersion !== record.coreVersion) {
    throw invalidManifest("packageVersion and coreVersion differ");
  }
  if (typeof record.wheel !== "string" || record.wheel.length === 0) {
    throw invalidManifest("wheel must be a filename");
  }
  if (typeof record.sha256 !== "string" || !HASH_PATTERN.test(record.sha256)) {
    throw invalidManifest("sha256 must be 64 lowercase hexadecimal characters");
  }

  const manifestDirectory = resolve(dirname(manifestPath));
  const wheelCandidate = resolve(manifestDirectory, record.wheel);
  if (!isInside(manifestDirectory, wheelCandidate)) {
    throw invalidManifest("wheel resolves outside the manifest directory");
  }
  let realDirectory: string;
  let wheelPath: string;
  try {
    [realDirectory, wheelPath] = await Promise.all([realpath(manifestDirectory), realpath(wheelCandidate)]);
  } catch {
    throw invalidManifest("wheel does not exist");
  }
  if (!isInside(realDirectory, wheelPath)) {
    throw invalidManifest("wheel symlink resolves outside the manifest directory");
  }
  if ((await sha256(wheelPath)) !== record.sha256) {
    throw invalidManifest("wheel hash does not match sha256");
  }
  return {
    schemaVersion: 1,
    packageVersion: record.packageVersion,
    coreVersion: record.coreVersion,
    wheel: record.wheel,
    sha256: record.sha256,
    wheelPath,
  };
}

function appendBounded(current: string, chunk: Buffer | string): string {
  if (Buffer.byteLength(current) >= MAX_PROCESS_OUTPUT_BYTES) return current;
  const remaining = MAX_PROCESS_OUTPUT_BYTES - Buffer.byteLength(current);
  const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
  return current + buffer.subarray(0, remaining).toString("utf8");
}

async function runBoundedProcess(process: ManagedRuntimeProcess): Promise<ManagedRuntimeProcessResult> {
  return new Promise((resolveProcess, rejectProcess) => {
    const child = spawn(process.executable, process.args, {
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      callback();
    };
    child.stdout.on("data", (chunk: Buffer) => (stdout = appendBounded(stdout, chunk)));
    child.stderr.on("data", (chunk: Buffer) => (stderr = appendBounded(stderr, chunk)));
    child.once("error", (error) => finish(() => rejectProcess(new ProcessExecutionError(error.message))));
    child.once("close", (code) =>
      finish(() => resolveProcess({ exitCode: code ?? 1, stdout, stderr })),
    );
    const timer = setTimeout(() => {
      child.kill();
      finish(() => rejectProcess(new ProcessExecutionError(`${process.stage} timed out after ${process.timeoutMs}ms`)));
    }, process.timeoutMs);
  });
}

function dependencies(options: ManagedRuntimeOptions): ManagedRuntimeDependencies {
  return {
    runProcess: options.dependencies?.runProcess ?? runBoundedProcess,
    now: options.dependencies?.now ?? Date.now,
    sleep:
      options.dependencies?.sleep ??
      ((milliseconds) => new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds))),
    randomUUID: options.dependencies?.randomUUID ?? randomUUID,
  };
}

function parseVersion(stdout: string): string | undefined {
  try {
    const value = JSON.parse(stdout.trim()) as { version?: unknown };
    return typeof value.version === "string" ? value.version : undefined;
  } catch {
    return undefined;
  }
}

function supportedPython(version: string): boolean {
  const [major, minor] = version.split(".").map(Number);
  return major > 3 || (major === 3 && minor >= 10);
}

async function selectBasePython(
  candidates: string[],
  deps: ManagedRuntimeDependencies,
): Promise<PythonVersion> {
  let foundUnsupported = false;
  for (const executable of [...new Set(candidates.filter(Boolean))]) {
    try {
      const result = await deps.runProcess({
        executable,
        args: ["-c", "import json, platform; print(json.dumps({'version': platform.python_version()}))"],
        timeoutMs: 10_000,
        stage: "python-version",
      });
      const version = result.exitCode === 0 ? parseVersion(result.stdout) : undefined;
      if (!version) continue;
      if (!supportedPython(version)) {
        foundUnsupported = true;
        continue;
      }
      return { executable, version };
    } catch {
      continue;
    }
  }
  if (foundUnsupported) {
    throw new ManagedRuntimeError(
      "PYTHON_VERSION_UNSUPPORTED",
      "ATO requires Python 3.10 or newer. Install a supported Python and retry.",
      "python-version",
    );
  }
  throw new ManagedRuntimeError(
    "PYTHON_NOT_FOUND",
    "ATO could not find Python 3.10 or newer. Install Python and ensure it is on PATH.",
    "python-version",
  );
}

function venvPython(runtimeRoot: string, platform: NodeJS.Platform): string {
  const path = platformPath(platform);
  return platform === "win32"
    ? path.join(runtimeRoot, "venv", "Scripts", "python.exe")
    : path.join(runtimeRoot, "venv", "bin", "python");
}

async function probeCore(
  executable: string,
  expectedCoreVersion: string,
  deps: ManagedRuntimeDependencies,
): Promise<PythonRuntime | undefined> {
  try {
    const result = await deps.runProcess({
      executable,
      args: [
        "-c",
        "import json, platform, ato_core; print(json.dumps({'version': platform.python_version(), 'coreVersion': ato_core.__version__}))",
      ],
      timeoutMs: 10_000,
      stage: "core-probe",
    });
    if (result.exitCode !== 0) return undefined;
    const value = JSON.parse(result.stdout.trim()) as { version?: unknown; coreVersion?: unknown };
    if (typeof value.version !== "string" || value.coreVersion !== expectedCoreVersion) return undefined;
    return { executable, version: value.version, coreVersion: expectedCoreVersion };
  } catch {
    return undefined;
  }
}

async function readMarker(path: string): Promise<RuntimeMarker | undefined> {
  try {
    const value = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    if (Object.keys(value).sort().join(",") !== MARKER_FIELDS.join(",")) return undefined;
    if (
      value.schemaVersion !== 1 ||
      typeof value.coreVersion !== "string" ||
      typeof value.wheelSha256 !== "string" ||
      typeof value.pythonExecutable !== "string" ||
      typeof value.completedAt !== "string"
    ) {
      return undefined;
    }
    return value as unknown as RuntimeMarker;
  } catch {
    return undefined;
  }
}

async function readyRuntime(
  runtimeRoot: string,
  manifest: RuntimeManifest,
  platform: NodeJS.Platform,
  deps: ManagedRuntimeDependencies,
): Promise<PythonRuntime | undefined> {
  const executable = venvPython(runtimeRoot, platform);
  const marker = await readMarker(platformPath(platform).join(runtimeRoot, "ato-runtime.json"));
  if (
    !marker ||
    marker.coreVersion !== manifest.coreVersion ||
    marker.wheelSha256 !== manifest.sha256 ||
    marker.pythonExecutable !== executable
  ) {
    return undefined;
  }
  return probeCore(executable, manifest.coreVersion, deps);
}

function installationFailure(
  stage: ManagedRuntimeStage,
  result: ManagedRuntimeProcessResult | Error,
): ManagedRuntimeError {
  const diagnostic =
    result instanceof Error ? result.message : result.stderr.trim() || result.stdout.trim() || "no diagnostic output";
  return new ManagedRuntimeError(
    "MANAGED_RUNTIME_INSTALL_FAILED",
    `Managed Python runtime ${stage} stage failed: ${diagnostic}. Fix Python/network access and retry.`,
    stage,
  );
}

async function runInstallStage(
  process: ManagedRuntimeProcess,
  deps: ManagedRuntimeDependencies,
): Promise<ManagedRuntimeProcessResult> {
  let result: ManagedRuntimeProcessResult;
  try {
    result = await deps.runProcess(process);
  } catch (error) {
    throw installationFailure(process.stage, error instanceof Error ? error : new Error(String(error)));
  }
  if (result.exitCode !== 0) throw installationFailure(process.stage, result);
  return result;
}

async function writeMarkerAtomically(path: string, marker: RuntimeMarker): Promise<void> {
  const temporary = `${path}.tmp`;
  await writeFile(temporary, `${JSON.stringify(marker, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  await rename(temporary, path);
}

async function removeContained(parent: string, target: string): Promise<void> {
  if (!isInside(parent, target)) {
    throw new ManagedRuntimeError(
      "MANAGED_RUNTIME_INSTALL_FAILED",
      "Refusing to remove a runtime path outside the managed runtime directory.",
    );
  }
  await rm(target, { recursive: true, force: true });
}

function defaultBaseCandidates(env: NodeJS.ProcessEnv, platform: NodeJS.Platform): string[] {
  const pathCandidates = platform === "win32" ? ["python", "python3"] : ["python3", "python"];
  return [env.ATO_PYTHON, ...pathCandidates].filter((candidate): candidate is string => Boolean(candidate));
}

export async function ensureManagedRuntime(
  manifestPath: string,
  options: ManagedRuntimeOptions = {},
): Promise<PythonRuntime> {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const homeDir = options.homeDir ?? homedir();
  const deps = dependencies(options);
  options.onStatus?.("checking", "Checking ATO Python runtime");
  const manifest = await readManifest(manifestPath);
  const runtimeRoot = resolveManagedRuntimeRoot(manifest.coreVersion, { env, platform, homeDir });
  const path = platformPath(platform);
  const runtimeParent = dirname(runtimeRoot);
  const lockPath = `${runtimeRoot}.lock`;
  const markerPath = path.join(runtimeRoot, "ato-runtime.json");
  const cached = await readyRuntime(runtimeRoot, manifest, platform, deps);
  if (cached) {
    options.onStatus?.("ready", "ATO Python runtime is ready");
    return cached;
  }

  const basePython = await selectBasePython(
    options.basePythonCandidates ?? defaultBaseCandidates(env, platform),
    deps,
  );
  await mkdir(runtimeParent, { recursive: true });
  const lockStarted = deps.now();
  const lockTimeoutMs = options.timeoutMs ?? DEFAULT_LOCK_TIMEOUT_MS;
  let lock: FileHandle | undefined;
  while (!lock) {
    const becameReady = await readyRuntime(runtimeRoot, manifest, platform, deps);
    if (becameReady) {
      options.onStatus?.("ready", "ATO Python runtime is ready");
      return becameReady;
    }
    try {
      const candidateLock = await open(lockPath, "wx");
      try {
        await candidateLock.writeFile(
          `${JSON.stringify({ pid: process.pid, createdAt: new Date(deps.now()).toISOString() })}\n`,
        );
        lock = candidateLock;
      } catch (error) {
        await candidateLock.close().catch(() => undefined);
        await unlink(lockPath).catch(() => undefined);
        throw error;
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      try {
        const lockStat = await stat(lockPath);
        if (deps.now() - lockStat.mtimeMs > STALE_LOCK_MS) {
          await unlink(lockPath);
          continue;
        }
      } catch (statError) {
        if ((statError as NodeJS.ErrnoException).code === "ENOENT") continue;
        throw statError;
      }
      if (deps.now() - lockStarted >= lockTimeoutMs) {
        throw new ManagedRuntimeError(
          "MANAGED_RUNTIME_BUSY",
          `Another ATO process did not finish preparing Python within ${lockTimeoutMs}ms. Retry after it completes.`,
        );
      }
      await deps.sleep(Math.min(LOCK_POLL_MS, lockTimeoutMs));
    }
  }

  const temporaryRoot = path.join(runtimeParent, `${manifest.coreVersion}.tmp-${deps.randomUUID()}`);
  let promoted = false;
  try {
    const becameReady = await readyRuntime(runtimeRoot, manifest, platform, deps);
    if (becameReady) {
      options.onStatus?.("ready", "ATO Python runtime is ready");
      return becameReady;
    }
    await removeContained(runtimeParent, runtimeRoot);
    await mkdir(temporaryRoot, { recursive: false });
    options.onStatus?.("creating", `Creating an isolated Python ${basePython.version} runtime`);
    await runInstallStage(
      {
        executable: basePython.executable,
        args: ["-m", "venv", path.join(temporaryRoot, "venv")],
        timeoutMs: 120_000,
        stage: "venv",
      },
      deps,
    );
    const temporaryPython = venvPython(temporaryRoot, platform);
    const installWheel = path.join(
      temporaryRoot,
      `ato_core-${manifest.coreVersion}-py3-none-any.whl`,
    );
    await copyFile(manifest.wheelPath, installWheel);
    options.onStatus?.("installing", "Installing bundled ATO core and Python dependencies");
    await runInstallStage(
      {
        executable: temporaryPython,
        args: [
          "-m",
          "pip",
          "install",
          "--disable-pip-version-check",
          "--no-input",
          installWheel,
        ],
        timeoutMs: 600_000,
        stage: "pip",
      },
      deps,
    );
    const probed = await probeCore(temporaryPython, manifest.coreVersion, deps);
    if (!probed) {
      throw installationFailure("core-probe", new Error("installed core did not pass its version probe"));
    }
    const finalPython = venvPython(runtimeRoot, platform);
    const marker: RuntimeMarker = {
      schemaVersion: 1,
      coreVersion: manifest.coreVersion,
      wheelSha256: manifest.sha256,
      pythonExecutable: finalPython,
      completedAt: new Date(deps.now()).toISOString(),
    };
    await writeMarkerAtomically(path.join(temporaryRoot, "ato-runtime.json"), marker);
    await rename(temporaryRoot, runtimeRoot);
    promoted = true;
    options.onStatus?.("ready", "ATO Python runtime is ready");
    return { executable: finalPython, version: probed.version, coreVersion: manifest.coreVersion };
  } finally {
    if (!promoted) await removeContained(runtimeParent, temporaryRoot).catch(() => undefined);
    await lock.close().catch(() => undefined);
    await unlink(lockPath).catch(() => undefined);
    if (promoted) {
      const marker = await readMarker(markerPath);
      if (!marker) {
        await removeContained(runtimeParent, runtimeRoot).catch(() => undefined);
      }
    }
  }
}

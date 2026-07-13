import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

import type { BridgeEvent, BridgeResponse, PythonRuntime } from "./protocol.js";

export class BridgeClientError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "BridgeClientError";
  }
}

export interface BridgeClientOptions {
  bridgeArgs?: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
}

function protocolError(message: string): BridgeClientError {
  return new BridgeClientError("BRIDGE_PROTOCOL_ERROR", message);
}

function parseResponse<T>(stdout: string): BridgeResponse<T> {
  const lines = stdout.split(/\r?\n/).filter((line) => line.length > 0);
  if (lines.length !== 1) {
    throw protocolError(`Expected exactly one JSON response, received ${lines.length} lines`);
  }
  let value: unknown;
  try {
    value = JSON.parse(lines[0]);
  } catch {
    throw protocolError("Bridge stdout was not valid JSON");
  }
  if (!value || typeof value !== "object" || typeof (value as { ok?: unknown }).ok !== "boolean") {
    throw protocolError("Bridge response envelope is invalid");
  }
  return value as BridgeResponse<T>;
}

function parseEvent(line: string): BridgeEvent {
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch {
    throw protocolError("Bridge event was not valid JSON");
  }
  if (
    !value ||
    typeof value !== "object" ||
    typeof (value as { type?: unknown }).type !== "string" ||
    typeof (value as { task_id?: unknown }).task_id !== "string" ||
    typeof (value as { data?: unknown }).data !== "object"
  ) {
    throw protocolError("Bridge event envelope is invalid");
  }
  return value as BridgeEvent;
}

export class BridgeClient {
  constructor(
    readonly runtime: PythonRuntime,
    private readonly options: BridgeClientOptions = {},
  ) {}

  async call<T = Record<string, unknown>>(
    command: string,
    payload: Record<string, unknown>,
  ): Promise<T> {
    const child = this.start(command);
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => (stdout += chunk));
    child.stderr.on("data", (chunk: string) => (stderr += chunk));
    child.stdin.end(JSON.stringify(payload));

    const exitCode = await this.wait(child);
    let response: BridgeResponse<T>;
    try {
      response = parseResponse<T>(stdout);
    } catch (error) {
      if (exitCode !== 0 && error instanceof BridgeClientError) {
        throw new BridgeClientError("BRIDGE_PROCESS_ERROR", stderr.trim() || error.message);
      }
      throw error;
    }
    if (!response.ok) {
      throw new BridgeClientError(response.code, response.message, response.details);
    }
    if (exitCode !== 0) {
      throw new BridgeClientError("BRIDGE_PROCESS_ERROR", stderr.trim() || "Bridge exited non-zero");
    }
    return response.data;
  }

  async *stream(
    command: string,
    payload: Record<string, unknown>,
  ): AsyncGenerator<BridgeEvent> {
    const child = this.start(command);
    let stderr = "";
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk: string) => (stderr += chunk));
    child.stdin.end(JSON.stringify(payload));
    const exit = this.wait(child);
    const lines = createInterface({ input: child.stdout, crlfDelay: Infinity });
    for await (const line of lines) {
      if (line.length > 0) yield parseEvent(line);
    }
    const exitCode = await exit;
    if (exitCode !== 0) {
      throw new BridgeClientError("BRIDGE_PROCESS_ERROR", stderr.trim() || "Bridge exited non-zero");
    }
  }

  private start(command: string) {
    return spawn(
      this.runtime.executable,
      [...(this.options.bridgeArgs ?? ["-m", "ato_core.bridge"]), command],
      {
        cwd: this.options.cwd,
        env: {
          ...process.env,
          ...this.options.env,
          PYTHONIOENCODING: "utf-8",
          PYTHONUTF8: "1",
        },
        shell: false,
        stdio: "pipe",
        windowsHide: true,
      },
    );
  }

  private wait(child: ReturnType<typeof spawn>): Promise<number> {
    const timeoutMs = this.options.timeoutMs ?? 300_000;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        child.kill();
        reject(new BridgeClientError("BRIDGE_TIMEOUT", `Bridge timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      child.once("error", (error) => {
        clearTimeout(timer);
        reject(new BridgeClientError("BRIDGE_PROCESS_ERROR", error.message));
      });
      child.once("close", (code) => {
        clearTimeout(timer);
        resolve(code ?? 1);
      });
    });
  }
}

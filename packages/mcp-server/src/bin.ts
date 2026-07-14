#!/usr/bin/env node

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  BridgeClient,
  discoverPython,
  type DiscoveryOptions,
  type PythonRuntime,
} from "@spacesky-cell/ato-shared";
import { pathToFileURL } from "node:url";

import { createAtoServer, type BridgePort } from "./server.js";

export interface McpRuntimeDependencies {
  discoverPython?: (options: DiscoveryOptions) => Promise<PythonRuntime>;
  createBridge?: (runtime: PythonRuntime) => BridgePort;
  stderr?: (value: string) => void;
  cwd?: () => string;
}

export async function createMcpBridge(
  dependencies: McpRuntimeDependencies = {},
): Promise<BridgePort> {
  const cwd = dependencies.cwd ?? (() => process.cwd());
  const stderr = dependencies.stderr ?? ((value: string) => console.error(value));
  const discover = dependencies.discoverPython ?? discoverPython;
  const runtime = await discover({
    projectRoot: cwd(),
    onManagedRuntimeStatus: (_status, message) => stderr(message),
  });
  return (dependencies.createBridge ?? ((selected) => new BridgeClient(selected, { cwd: cwd() })))(
    runtime,
  );
}

export async function main(dependencies: McpRuntimeDependencies = {}): Promise<void> {
  const bridge = await createMcpBridge(dependencies);
  await createAtoServer(bridge).connect(new StdioServerTransport());
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    const code =
      error && typeof error === "object" && "code" in error ? String(error.code) : "MCP_ERROR";
    const message = error instanceof Error ? error.message : String(error);
    console.error(`${code}: ${message}`);
    process.exitCode = 1;
  });
}

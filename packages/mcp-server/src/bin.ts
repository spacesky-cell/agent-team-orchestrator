#!/usr/bin/env node

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { BridgeClient, discoverPython } from "@spacesky-cell/ato-shared";
import { pathToFileURL } from "node:url";

import { createAtoServer } from "./server.js";

export async function main(): Promise<void> {
  const runtime = await discoverPython({ projectRoot: process.cwd() });
  const bridge = new BridgeClient(runtime, { cwd: process.cwd() });
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

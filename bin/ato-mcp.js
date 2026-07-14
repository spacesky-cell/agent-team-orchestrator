#!/usr/bin/env node

import { fileURLToPath } from "node:url";

process.env.ATO_BUNDLED_RUNTIME_MANIFEST ??= fileURLToPath(
  new URL("../vendor/runtime-manifest.json", import.meta.url),
);

const { main } = await import("@spacesky-cell/ato-mcp-server/bin");
main().catch((error) => {
  const code = error && typeof error === "object" && "code" in error ? String(error.code) : "MCP_ERROR";
  const message = error instanceof Error ? error.message : String(error);
  console.error(`${code}: ${message}`);
  process.exitCode = 1;
});

#!/usr/bin/env node

import { main } from "@spacesky-cell/ato-mcp-server/bin";

main().catch((error) => {
  const code = error && typeof error === "object" && "code" in error ? String(error.code) : "MCP_ERROR";
  const message = error instanceof Error ? error.message : String(error);
  console.error(`${code}: ${message}`);
  process.exitCode = 1;
});

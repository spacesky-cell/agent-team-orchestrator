#!/usr/bin/env node

import { fileURLToPath } from "node:url";

process.env.ATO_BUNDLED_RUNTIME_MANIFEST ??= fileURLToPath(
  new URL("../vendor/runtime-manifest.json", import.meta.url),
);

const { main } = await import("@spacesky-cell/ato-cli");
process.exitCode = await main(process.argv);

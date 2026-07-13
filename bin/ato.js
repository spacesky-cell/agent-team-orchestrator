#!/usr/bin/env node

import { main } from "@spacesky-cell/ato-cli";

process.exitCode = await main(process.argv);

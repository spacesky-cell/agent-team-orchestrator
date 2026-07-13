import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("npm package entry points", () => {
  it("ships both root command shims", () => {
    const root = resolve(import.meta.dirname, "../../..");
    const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8")) as {
      bin?: Record<string, string>;
    };

    expect(manifest.bin).toEqual({ ato: "bin/ato.js", "ato-mcp": "bin/ato-mcp.js" });
    expect(existsSync(resolve(root, "bin/ato.js"))).toBe(true);
    expect(existsSync(resolve(root, "bin/ato-mcp.js"))).toBe(true);
  });

  it("imports CLI and MCP libraries without starting a process", async () => {
    const cli = await import("./index.js");
    const mcp = await import("../../mcp-server/src/index.js");

    expect(typeof cli.createCli).toBe("function");
    expect(typeof mcp.createAtoServer).toBe("function");
  });
});

import { describe, expect, it } from "vitest";

import { executePythonJson, getCoreModulePath, getProjectRoot, getPythonPath } from "@ato/shared";

describe("MCP server smoke", () => {
  it("discovers project root", () => {
    const root = getProjectRoot(process.cwd());
    expect(root.endsWith("agent-team-orchestrator")).toBe(true);
  });

  it("resolves core module path", () => {
    const corePath = getCoreModulePath(process.cwd());
    expect(corePath).toContain("packages");
    expect(corePath).toContain("core");
  });

  it("finds a Python interpreter", () => {
    const python = getPythonPath(process.cwd());
    expect(python.length).toBeGreaterThan(0);
  });

  it("loads roles via the Python runner", () => {
    const root = getProjectRoot(process.cwd());

    const roles = executePythonJson<string[]>({
      script: `
import json
from src.models.role import RoleLoader
loader = RoleLoader()
print(json.dumps(loader.list_roles(), ensure_ascii=False))
`,
      cwd: root,
    });

    expect(Array.isArray(roles)).toBe(true);
    expect(roles.length).toBeGreaterThan(0);
    expect(roles).toContain("architect");
    expect(roles).toContain("backend-developer");
    expect(roles).toContain("tester");
  });

  it("self_check logic runs end-to-end", () => {
    const root = getProjectRoot(process.cwd());

    const result = executePythonJson<{
      roles: string[];
      env: Record<string, string>;
    }>({
      script: `
import json
import os
import shutil
import subprocess

from src.models.role import RoleLoader

payload = json.loads(input_path.read_text(encoding="utf-8"))
loader = RoleLoader()
claude_path = shutil.which("claude")
claude_version = "UNAVAILABLE"
if claude_path:
    try:
        completed = subprocess.run(
            [claude_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if completed.returncode == 0:
            claude_version = completed.stdout.strip()
    except Exception as exc:
        claude_version = f"ERROR: {exc}"

print(json.dumps({
    "roles": loader.list_roles(),
    "env": {
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "claude-cli"),
        "ANTHROPIC_API_KEY": "SET" if os.getenv("ANTHROPIC_API_KEY") else "UNSET",
        "OPENAI_API_KEY": "SET" if os.getenv("OPENAI_API_KEY") else "UNSET",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL") or "UNSET",
        "CLAUDE_CLI": claude_version,
    },
}, ensure_ascii=False))
`,
      cwd: root,
      input: {
        project_root: root,
        core_module_path: getCoreModulePath(root),
      },
    });

    expect(result.roles).toBeDefined();
    expect(Array.isArray(result.roles)).toBe(true);
    expect(result.roles.length).toBeGreaterThan(0);
    expect(result.env).toBeDefined();
    expect(result.env.LLM_PROVIDER).toBe("claude-cli");
  });
});

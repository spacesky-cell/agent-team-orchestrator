import { describe, expect, it } from "vitest";

import { executePythonJson, getProjectRoot, readAuditSummary } from "@spacesky-cell/ato-shared";
import { mkdtempSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

describe("CLI module smoke", () => {
  it("can invoke the Python runner for role listing", () => {
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
    expect(roles).toContain("architect");
    expect(roles).toContain("backend-developer");
    expect(roles).toContain("tester");
  });

  it("can read audit summary for CLI audit/status commands", () => {
    const dir = mkdtempSync(join(tmpdir(), "ato-cli-audit-"));
    writeFileSync(
      join(dir, "tool-audit.jsonl"),
      JSON.stringify({
        timestamp: "2026-07-07T00:00:00.000Z",
        task_id: "task-1",
        subtask_id: "st-1",
        role: "tester",
        tool_name: "search_code",
        decision: "auto_allowed",
        status: "completed",
        duration_ms: 1,
      }),
      "utf-8",
    );

    const summary = readAuditSummary(dir);

    expect(summary.exists).toBe(true);
    expect(summary.total).toBe(1);
    expect(summary.completed).toBe(1);
    expect(summary.recent[0].tool_name).toBe("search_code");
  });
});

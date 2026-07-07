import { mkdtempSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { describe, expect, it } from "vitest";

import { readAuditSummary } from "./audit-reader.js";

describe("audit reader", () => {
  it("summarizes valid audit events", () => {
    const dir = mkdtempSync(join(tmpdir(), "ato-audit-"));
    const auditPath = join(dir, "tool-audit.jsonl");
    writeFileSync(
      auditPath,
      [
        JSON.stringify({
          timestamp: "2026-07-07T00:00:00.000Z",
          task_id: "task-1",
          subtask_id: "st-1",
          role: "tester",
          tool_name: "search_code",
          args_summary: { query: "abc" },
          decision: "auto_allowed",
          status: "completed",
          duration_ms: 2,
        }),
        JSON.stringify({
          timestamp: "2026-07-07T00:00:01.000Z",
          task_id: "task-1",
          subtask_id: "st-2",
          role: "tester",
          tool_name: "execute_command",
          args_summary: { command: "pytest" },
          decision: "requires_approval",
          status: "blocked",
          duration_ms: 0,
          error: "requires approval",
        }),
      ].join("\n"),
      "utf-8",
    );

    const summary = readAuditSummary(dir);

    expect(summary.path).toBe(auditPath);
    expect(summary.exists).toBe(true);
    expect(summary.total).toBe(2);
    expect(summary.blocked).toBe(1);
    expect(summary.failed).toBe(0);
    expect(summary.recent).toHaveLength(2);
    expect(summary.recent[1].tool_name).toBe("execute_command");
  });

  it("reports missing audit file without throwing", () => {
    const dir = mkdtempSync(join(tmpdir(), "ato-audit-missing-"));

    const summary = readAuditSummary(dir);

    expect(summary.exists).toBe(false);
    expect(summary.total).toBe(0);
    expect(summary.recent).toEqual([]);
  });

  it("records malformed audit lines as parse errors", () => {
    const dir = mkdtempSync(join(tmpdir(), "ato-audit-bad-"));
    writeFileSync(join(dir, "tool-audit.jsonl"), "{not-json}\n", "utf-8");

    const summary = readAuditSummary(dir);

    expect(summary.exists).toBe(true);
    expect(summary.total).toBe(0);
    expect(summary.parseErrors).toBe(1);
  });
});

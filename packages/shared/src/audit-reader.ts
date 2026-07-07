import { existsSync, readFileSync } from "fs";
import { join } from "path";

export interface ToolAuditEvent {
  timestamp?: string;
  task_id?: string;
  subtask_id?: string;
  role?: string;
  tool_name?: string;
  args_summary?: Record<string, unknown>;
  decision?: string;
  status?: string;
  duration_ms?: number;
  error?: string;
}

export interface ToolAuditSummary {
  path: string;
  exists: boolean;
  total: number;
  completed: number;
  blocked: number;
  failed: number;
  parseErrors: number;
  recent: ToolAuditEvent[];
}

export function readAuditSummary(outputDir: string, limit = 10): ToolAuditSummary {
  const auditPath = join(outputDir, "tool-audit.jsonl");
  const summary: ToolAuditSummary = {
    path: auditPath,
    exists: existsSync(auditPath),
    total: 0,
    completed: 0,
    blocked: 0,
    failed: 0,
    parseErrors: 0,
    recent: [],
  };

  if (!summary.exists) {
    return summary;
  }

  const events: ToolAuditEvent[] = [];
  const lines = readFileSync(auditPath, "utf-8").split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    try {
      const event = JSON.parse(line) as ToolAuditEvent;
      events.push(event);
      summary.total += 1;
      if (event.status === "completed") summary.completed += 1;
      if (event.status === "blocked") summary.blocked += 1;
      if (event.status === "failed") summary.failed += 1;
    } catch {
      summary.parseErrors += 1;
    }
  }

  summary.recent = events.slice(-limit);
  return summary;
}

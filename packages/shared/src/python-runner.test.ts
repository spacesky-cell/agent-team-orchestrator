import { existsSync, readdirSync } from "fs";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { describe, expect, it } from "vitest";

import {
  executePythonJson,
  executePythonStreaming,
  getCoreModulePath,
  getProjectRoot,
  getPythonPath,
} from "./python-runner.js";

describe("python runner", () => {
  it("passes JSON input without embedding user strings in Python source", () => {
    const root = getProjectRoot(process.cwd());
    const result = executePythonJson({
      script: `
import json
payload = json.loads(input_path.read_text(encoding="utf-8"))
print(json.dumps({"description": payload["description"]}, ensure_ascii=False))
`,
      input: {
        description: '中文 task with "quotes", apostrophes, and\nnewlines',
      },
      cwd: root,
    });

    expect(result.description).toBe('中文 task with "quotes", apostrophes, and\nnewlines');
  });

  it("cleans up temporary script and input files", () => {
    const tempRoot = mkdtempSync(join(tmpdir(), "ato-runner-"));

    try {
      const result = executePythonJson({
        script: `
import json
payload = json.loads(input_path.read_text(encoding="utf-8"))
print(json.dumps({"ok": payload["ok"]}))
`,
        input: { ok: true },
        cwd: tempRoot,
      });

      expect(result.ok).toBe(true);
      expect(readdirSync(join(tempRoot, "ato-output"))).toEqual([]);
    } finally {
      rmSync(tempRoot, { recursive: true, force: true });
    }
  });

  it("isolates concurrent streaming executions that share the same project root", async () => {
    const tempRoot = mkdtempSync(join(tmpdir(), "ato-runner-"));

    try {
      const script = `
import json
import time
from pathlib import Path
payload = json.loads(input_path.read_text(encoding="utf-8"))
time.sleep(0.2)
Path(payload["result_path"]).write_text(payload["id"], encoding="utf-8")
`;

      const resultPaths = ["first", "second", "third"].map((id) =>
        join(tempRoot, `${id}.txt`),
      );

      await Promise.all(
        ["first", "second", "third"].map((id, index) =>
          executePythonStreaming({
              script,
              input: { id, result_path: resultPaths[index] },
              cwd: tempRoot,
              streamOutput: false,
            }),
        ),
      );

      expect(resultPaths.map((path) => existsSync(path))).toEqual([true, true, true]);
    } finally {
      rmSync(tempRoot, { recursive: true, force: true });
    }
  });

  it("discovers repo paths for the current workspace", () => {
    expect(getProjectRoot(process.cwd()).endsWith("agent-team-orchestrator")).toBe(true);
    expect(getCoreModulePath(process.cwd()).endsWith("packages\\core")).toBe(true);
    expect(getPythonPath(process.cwd()).length).toBeGreaterThan(0);
  });
});

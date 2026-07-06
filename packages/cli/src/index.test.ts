import { describe, expect, it } from "vitest";

import { executePythonJson, getProjectRoot } from "@ato/shared";

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
});

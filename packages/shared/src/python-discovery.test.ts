import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { PythonDiscoveryError, discoverPython } from "./python-discovery.js";

const runtime = (executable: string) => ({
  executable,
  version: "3.12.0",
  coreVersion: "0.2.0",
});

describe("Python discovery", () => {
  it("prefers ATO_PYTHON then the project virtual environment", async () => {
    const attempted: string[] = [];
    const selected = await discoverPython({
      projectRoot: "C:/project",
      platform: "win32",
      env: { ATO_PYTHON: "C:/custom/python.exe" },
      exists: () => true,
      probe: async (candidate) => {
        attempted.push(candidate);
        return runtime(candidate);
      },
    });

    expect(selected.executable).toBe("C:/custom/python.exe");
    expect(attempted).toEqual(["C:/custom/python.exe"]);
  });

  it("skips a Python without ato_core and uses the Windows venv", async () => {
    const venv = join("C:/project", ".venv", "Scripts", "python.exe");
    const selected = await discoverPython({
      projectRoot: "C:/project",
      platform: "win32",
      env: { ATO_PYTHON: "C:/missing-core/python.exe" },
      exists: () => true,
      probe: async (candidate, timeoutMs) => {
        expect(timeoutMs).toBe(1234);
        if (candidate.includes("missing-core")) throw new Error("ato_core unavailable");
        return runtime(candidate);
      },
      probeTimeoutMs: 1234,
    });

    expect(selected.executable).toBe(venv);
  });

  it("reports bounded secret-free diagnostics when every candidate fails", async () => {
    await expect(
      discoverPython({
        projectRoot: "/project",
        platform: "linux",
        env: { ATO_PYTHON: "/bad/python", API_TOKEN: "do-not-print" },
        exists: () => true,
        probe: async () => {
          throw new Error("probe failed");
        },
      }),
    ).rejects.toSatisfy((error: PythonDiscoveryError) => {
      expect(error.code).toBe("PYTHON_NOT_FOUND");
      expect(error.message).not.toContain("do-not-print");
      expect(error.attempts.length).toBeLessThanOrEqual(5);
      return true;
    });
  });

  it("uses the managed runtime only after every existing core probe fails", async () => {
    const attempted: string[] = [];
    let managedCalls = 0;
    const managed = runtime("C:/managed/python.exe");
    const selected = await discoverPython({
      projectRoot: "C:/project",
      platform: "win32",
      env: {
        ATO_PYTHON: "C:/custom/python.exe",
        ATO_BUNDLED_RUNTIME_MANIFEST: "C:/package/vendor/runtime-manifest.json",
      },
      exists: () => false,
      probe: async (candidate) => {
        attempted.push(candidate);
        throw new Error("ato_core unavailable");
      },
      prepareManagedRuntime: async (manifestPath, options) => {
        managedCalls += 1;
        expect(manifestPath).toBe("C:/package/vendor/runtime-manifest.json");
        expect(options.basePythonCandidates).toEqual([
          "C:/custom/python.exe",
          "python",
          "python3",
        ]);
        return managed;
      },
    });

    expect(selected).toEqual(managed);
    expect(attempted).toEqual(["C:/custom/python.exe", "python", "python3"]);
    expect(managedCalls).toBe(1);
  });

  it("never prepares a managed runtime when an existing core is usable", async () => {
    let managedCalls = 0;
    const selected = await discoverPython({
      projectRoot: "/project",
      platform: "linux",
      env: { ATO_BUNDLED_RUNTIME_MANIFEST: "/package/vendor/runtime-manifest.json" },
      exists: () => false,
      probe: async (candidate) => runtime(candidate),
      prepareManagedRuntime: async () => {
        managedCalls += 1;
        return runtime("/managed/python");
      },
    });

    expect(selected.executable).toBe("python3");
    expect(managedCalls).toBe(0);
  });

  it("forwards managed runtime status without exposing other environment values", async () => {
    const statuses: string[] = [];
    await discoverPython({
      projectRoot: "/project",
      platform: "linux",
      env: {
        ATO_BUNDLED_RUNTIME_MANIFEST: "/package/vendor/runtime-manifest.json",
        API_TOKEN: "do-not-print",
      },
      exists: () => false,
      probe: async () => {
        throw new Error("unavailable");
      },
      onManagedRuntimeStatus: (_status, message) => statuses.push(message),
      prepareManagedRuntime: async (_manifest, options) => {
        options.onStatus?.("installing", "Installing bundled ATO core");
        return runtime("/managed/python");
      },
    });

    expect(statuses).toEqual(["Installing bundled ATO core"]);
    expect(statuses.join("\n")).not.toContain("do-not-print");
  });
});

import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  ManagedRuntimeError,
  ensureManagedRuntime,
  resolveManagedRuntimeRoot,
  type ManagedRuntimeDependencies,
  type ManagedRuntimeProcess,
} from "./managed-runtime.js";

const temporaryDirectories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const directory = join(tmpdir(), `ato-managed-runtime-${crypto.randomUUID()}`);
  await mkdir(directory, { recursive: true });
  temporaryDirectories.push(directory);
  return directory;
}

afterEach(async () => {
  const { rm } = await import("node:fs/promises");
  await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

interface Harness {
  manifestPath: string;
  home: string;
  commands: ManagedRuntimeProcess[];
  dependencies: Partial<ManagedRuntimeDependencies>;
}

async function createHarness(
  overrides: Partial<ManagedRuntimeDependencies> = {},
): Promise<Harness> {
  const root = await temporaryDirectory();
  const vendor = join(root, "vendor");
  const home = join(root, "home");
  const wheelPath = join(vendor, "ato-core.whl");
  const manifestPath = join(vendor, "runtime-manifest.json");
  const wheel = Buffer.from("ato-core-wheel");
  await mkdir(vendor, { recursive: true });
  await writeFile(wheelPath, wheel);
  await writeFile(
    manifestPath,
    JSON.stringify({
      schemaVersion: 1,
      packageVersion: "0.2.1",
      coreVersion: "0.2.1",
      wheel: "ato-core.whl",
      sha256: createHash("sha256").update(wheel).digest("hex"),
    }),
  );
  const commands: ManagedRuntimeProcess[] = [];
  const runProcess: ManagedRuntimeDependencies["runProcess"] = async (process) => {
    commands.push(process);
    if (process.stage === "python-version") {
      return { exitCode: 0, stdout: '{"version":"3.12.4"}\n', stderr: "" };
    }
    if (process.stage === "core-probe") {
      return {
        exitCode: 0,
        stdout: '{"version":"3.12.4","coreVersion":"0.2.1"}\n',
        stderr: "",
      };
    }
    return { exitCode: 0, stdout: "", stderr: "" };
  };
  return {
    manifestPath,
    home,
    commands,
    dependencies: { runProcess, ...overrides },
  };
}

async function install(harness: Harness) {
  return ensureManagedRuntime(harness.manifestPath, {
    env: { ATO_HOME: harness.home },
    platform: process.platform,
    homeDir: harness.home,
    basePythonCandidates: ["python-test"],
    dependencies: harness.dependencies,
  });
}

describe("managed runtime manifest", () => {
  it.each([
    ["unknown field", { extra: true }],
    ["unsupported schema", { schemaVersion: 2 }],
    ["invalid version", { coreVersion: "0.2" }],
    ["version drift", { packageVersion: "0.2.2" }],
  ])("rejects %s", async (_name, replacement) => {
    const harness = await createHarness();
    const manifest = JSON.parse(await readFile(harness.manifestPath, "utf8")) as Record<string, unknown>;
    await writeFile(harness.manifestPath, JSON.stringify({ ...manifest, ...replacement }));

    await expect(install(harness)).rejects.toMatchObject({ code: "BUNDLED_RUNTIME_INVALID" });
    expect(harness.commands).toEqual([]);
  });

  it("rejects traversal and hash mismatch before running Python", async () => {
    const traversal = await createHarness();
    const manifest = JSON.parse(await readFile(traversal.manifestPath, "utf8")) as Record<string, unknown>;
    await writeFile(traversal.manifestPath, JSON.stringify({ ...manifest, wheel: "../ato-core.whl" }));
    await expect(install(traversal)).rejects.toMatchObject({ code: "BUNDLED_RUNTIME_INVALID" });

    const mismatch = await createHarness();
    const second = JSON.parse(await readFile(mismatch.manifestPath, "utf8")) as Record<string, unknown>;
    await writeFile(mismatch.manifestPath, JSON.stringify({ ...second, sha256: "0".repeat(64) }));
    await expect(install(mismatch)).rejects.toMatchObject({ code: "BUNDLED_RUNTIME_INVALID" });
    expect([...traversal.commands, ...mismatch.commands]).toEqual([]);
  });
});

describe("managed runtime storage", () => {
  it("uses ATO_HOME before platform defaults", () => {
    expect(
      resolveManagedRuntimeRoot("0.2.1", {
        env: { ATO_HOME: "/opt/ato" },
        platform: "linux",
        homeDir: "/home/user",
      }),
    ).toBe("/opt/ato/runtime/0.2.1");
  });

  it("resolves Windows, macOS, and Linux data roots", () => {
    expect(
      resolveManagedRuntimeRoot("0.2.1", {
        env: { LOCALAPPDATA: "C:\\Users\\user\\AppData\\Local" },
        platform: "win32",
        homeDir: "C:\\Users\\user",
      }),
    ).toBe("C:\\Users\\user\\AppData\\Local\\AgentTeamOrchestrator\\runtime\\0.2.1");
    expect(
      resolveManagedRuntimeRoot("0.2.1", {
        env: {},
        platform: "darwin",
        homeDir: "/Users/user",
      }),
    ).toBe("/Users/user/Library/Application Support/AgentTeamOrchestrator/runtime/0.2.1");
    expect(
      resolveManagedRuntimeRoot("0.2.1", {
        env: { XDG_DATA_HOME: "/data" },
        platform: "linux",
        homeDir: "/home/user",
      }),
    ).toBe("/data/agent-team-orchestrator/runtime/0.2.1");
    expect(
      resolveManagedRuntimeRoot("0.2.1", {
        env: {},
        platform: "linux",
        homeDir: "/home/user",
      }),
    ).toBe("/home/user/.local/share/agent-team-orchestrator/runtime/0.2.1");
  });
});

describe("managed runtime lifecycle", () => {
  it("installs atomically and reuses a live matching environment", async () => {
    const harness = await createHarness();
    const statuses: string[] = [];
    const first = await ensureManagedRuntime(harness.manifestPath, {
      env: { ATO_HOME: harness.home },
      platform: process.platform,
      homeDir: harness.home,
      basePythonCandidates: ["python-test"],
      dependencies: harness.dependencies,
      onStatus: (status) => statuses.push(status),
    });
    const runtimeRoot = resolveManagedRuntimeRoot("0.2.1", {
      env: { ATO_HOME: harness.home },
      platform: process.platform,
      homeDir: harness.home,
    });
    const marker = JSON.parse(await readFile(join(runtimeRoot, "ato-runtime.json"), "utf8")) as {
      coreVersion: string;
      wheelSha256: string;
      pythonExecutable: string;
    };

    expect(harness.commands.map((command) => command.stage)).toEqual([
      "python-version",
      "venv",
      "pip",
      "core-probe",
    ]);
    expect(marker).toMatchObject({ coreVersion: "0.2.1", pythonExecutable: first.executable });
    expect(marker.wheelSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(statuses).toEqual(["checking", "creating", "installing", "ready"]);

    const second = await install(harness);
    expect(second).toEqual(first);
    expect(harness.commands.filter((command) => command.stage === "pip")).toHaveLength(1);
    expect(harness.commands.at(-1)?.stage).toBe("core-probe");
  });

  it("rebuilds a corrupt marker while holding the version lock", async () => {
    const harness = await createHarness();
    await install(harness);
    const runtimeRoot = resolveManagedRuntimeRoot("0.2.1", {
      env: { ATO_HOME: harness.home },
      platform: process.platform,
      homeDir: harness.home,
    });
    await writeFile(join(runtimeRoot, "ato-runtime.json"), "not json");

    await install(harness);

    expect(harness.commands.filter((command) => command.stage === "pip")).toHaveLength(2);
  });

  it("recovers a stale lock", async () => {
    const harness = await createHarness();
    const finalRoot = resolveManagedRuntimeRoot("0.2.1", {
      env: { ATO_HOME: harness.home },
      platform: process.platform,
      homeDir: harness.home,
    });
    const lock = `${finalRoot}.lock`;
    await mkdir(dirname(lock), { recursive: true });
    await writeFile(lock, "stale");
    const stale = new Date(Date.now() - 11 * 60_000);
    await utimes(lock, stale, stale);

    await install(harness);

    await expect(stat(lock)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("returns MANAGED_RUNTIME_BUSY when a live lock exceeds the bound", async () => {
    let now = 10_000;
    const harness = await createHarness({
      now: () => now,
      sleep: async (milliseconds) => {
        now += milliseconds;
      },
    });
    const finalRoot = resolveManagedRuntimeRoot("0.2.1", {
      env: { ATO_HOME: harness.home },
      platform: process.platform,
      homeDir: harness.home,
    });
    const lock = `${finalRoot}.lock`;
    await mkdir(dirname(lock), { recursive: true });
    await writeFile(lock, "live");

    await expect(
      ensureManagedRuntime(harness.manifestPath, {
        env: { ATO_HOME: harness.home },
        platform: process.platform,
        homeDir: harness.home,
        basePythonCandidates: ["python-test"],
        timeoutMs: 1_000,
        dependencies: harness.dependencies,
      }),
    ).rejects.toMatchObject({ code: "MANAGED_RUNTIME_BUSY" });
  });

  it("rejects Python below 3.10 with a stable code", async () => {
    const harness = await createHarness({
      runProcess: async (process) => {
        if (process.stage === "python-version") {
          return { exitCode: 0, stdout: '{"version":"3.9.18"}', stderr: "" };
        }
        return { exitCode: 0, stdout: "", stderr: "" };
      },
    });

    await expect(install(harness)).rejects.toMatchObject({ code: "PYTHON_VERSION_UNSUPPORTED" });
  });

  it("redacts pip credentials and cleans temporary state after failure", async () => {
    const harness = await createHarness({
      runProcess: async (process) => {
        if (process.stage === "python-version") {
          return { exitCode: 0, stdout: '{"version":"3.12.4"}', stderr: "" };
        }
        if (process.stage === "pip") {
          return {
            exitCode: 1,
            stdout: "",
            stderr: `download https://user:password@example.test/simple token=super-secret ${"x".repeat(5_000)}`,
          };
        }
        return { exitCode: 0, stdout: "", stderr: "" };
      },
    });

    const error = await install(harness).catch((value: unknown) => value as ManagedRuntimeError);
    expect(error.code).toBe("MANAGED_RUNTIME_INSTALL_FAILED");
    expect(error.message).not.toContain("password");
    expect(error.message).not.toContain("super-secret");
    expect(error.message.length).toBeLessThanOrEqual(4_096);

    const runtimeParent = dirname(
      resolveManagedRuntimeRoot("0.2.1", {
        env: { ATO_HOME: harness.home },
        platform: process.platform,
        homeDir: harness.home,
      }),
    );
    const leftovers = await readdir(runtimeParent);
    expect(leftovers.filter((name) => name.includes(".tmp-") || name.endsWith(".lock"))).toEqual([]);
  });
});

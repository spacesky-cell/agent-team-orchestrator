import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { prepareNpmRuntime } from "./prepare-npm-runtime.mjs";

const roots = [];

async function fixture(version = "0.2.1") {
  const root = join(tmpdir(), `ato-prepare-runtime-${randomUUID()}`);
  const distDir = join(root, "dist");
  const vendorDir = join(root, "vendor");
  const packageJsonPath = join(root, "package.json");
  await mkdir(distDir, { recursive: true });
  await writeFile(packageJsonPath, `${JSON.stringify({ version })}\n`);
  roots.push(root);
  return { root, distDir, vendorDir, packageJsonPath };
}

test.afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

test("requires exactly one wheel", async () => {
  const empty = await fixture();
  await assert.rejects(prepareNpmRuntime(empty), /exactly one ato_core wheel/i);

  const multiple = await fixture();
  await writeFile(join(multiple.distDir, "ato_core-0.2.1-py3-none-any.whl"), "one");
  await writeFile(join(multiple.distDir, "ato_core-0.2.2-py3-none-any.whl"), "two");
  await assert.rejects(prepareNpmRuntime(multiple), /exactly one ato_core wheel/i);
});

test("rejects a wheel whose version differs from package.json", async () => {
  const paths = await fixture("0.2.1");
  await writeFile(join(paths.distDir, "ato_core-0.2.2-py3-none-any.whl"), "wheel");

  await assert.rejects(prepareNpmRuntime(paths), /wheel version 0\.2\.2.*package version 0\.2\.1/i);
});

test("writes a stable wheel name and exact hash manifest", async () => {
  const paths = await fixture("0.2.1");
  const wheel = Buffer.from("wheel-content");
  await writeFile(join(paths.distDir, "ato_core-0.2.1-py3-none-any.whl"), wheel);

  const result = await prepareNpmRuntime(paths);
  const copied = await readFile(join(paths.vendorDir, "ato-core.whl"));
  const manifest = JSON.parse(
    await readFile(join(paths.vendorDir, "runtime-manifest.json"), "utf8"),
  );

  assert.deepEqual(copied, wheel);
  assert.deepEqual(Object.keys(manifest).sort(), [
    "coreVersion",
    "packageVersion",
    "schemaVersion",
    "sha256",
    "wheel",
  ]);
  assert.deepEqual(manifest, {
    schemaVersion: 1,
    packageVersion: "0.2.1",
    coreVersion: "0.2.1",
    wheel: "ato-core.whl",
    sha256: createHash("sha256").update(wheel).digest("hex"),
  });
  assert.equal(result.manifestPath, join(paths.vendorDir, "runtime-manifest.json"));
});

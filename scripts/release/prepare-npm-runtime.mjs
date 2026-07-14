import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { copyFile, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;
const WHEEL_PATTERN = /^ato_core-(\d+\.\d+\.\d+)-py3-none-any\.whl$/;

async function fileSha256(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

async function atomicReplace(temporary, target) {
  try {
    await rename(temporary, target);
  } catch (error) {
    if (error.code !== "EEXIST" && error.code !== "EPERM") throw error;
    await rm(target, { force: true });
    await rename(temporary, target);
  }
}

export async function prepareNpmRuntime({ distDir, vendorDir, packageJsonPath }) {
  const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
  if (typeof packageJson.version !== "string" || !VERSION_PATTERN.test(packageJson.version)) {
    throw new Error("Root package.json version must be major.minor.patch");
  }
  const entries = await readdir(distDir, { withFileTypes: true });
  const wheels = entries.filter((entry) => entry.isFile() && WHEEL_PATTERN.test(entry.name));
  if (wheels.length !== 1) {
    throw new Error(`Expected exactly one ato_core wheel, found ${wheels.length}`);
  }
  const sourceName = wheels[0].name;
  const wheelVersion = WHEEL_PATTERN.exec(sourceName)?.[1];
  if (wheelVersion !== packageJson.version) {
    throw new Error(
      `Python wheel version ${wheelVersion ?? "unknown"} differs from package version ${packageJson.version}`,
    );
  }

  const sourcePath = join(distDir, sourceName);
  const sha256 = await fileSha256(sourcePath);
  const manifest = {
    schemaVersion: 1,
    packageVersion: packageJson.version,
    coreVersion: packageJson.version,
    wheel: "ato-core.whl",
    sha256,
  };
  await mkdir(vendorDir, { recursive: true });
  const suffix = `.tmp-${randomUUID()}`;
  const wheelPath = join(vendorDir, "ato-core.whl");
  const manifestPath = join(vendorDir, "runtime-manifest.json");
  const temporaryWheel = `${wheelPath}${suffix}`;
  const temporaryManifest = `${manifestPath}${suffix}`;
  try {
    await copyFile(sourcePath, temporaryWheel);
    await writeFile(temporaryManifest, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    await atomicReplace(temporaryWheel, wheelPath);
    await atomicReplace(temporaryManifest, manifestPath);
  } finally {
    await Promise.all([
      rm(temporaryWheel, { force: true }),
      rm(temporaryManifest, { force: true }),
    ]);
  }
  return { wheelPath, manifestPath, manifest };
}

const scriptPath = fileURLToPath(import.meta.url);
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [distDir, vendorDir] = process.argv.slice(2);
  if (!distDir || !vendorDir || process.argv.length !== 4) {
    console.error("Usage: node scripts/release/prepare-npm-runtime.mjs <python-dist-dir> <vendor-dir>");
    process.exitCode = 2;
  } else {
    const repositoryRoot = resolve(dirname(scriptPath), "../..");
    await prepareNpmRuntime({
      distDir: resolve(distDir),
      vendorDir: resolve(vendorDir),
      packageJsonPath: join(repositoryRoot, "package.json"),
    });
  }
}

import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { basename, resolve } from "node:path";

const roots = process.argv.slice(2, -1);
const output = resolve(process.argv.at(-1) ?? "release-manifest.json");
const selected = roots.length > 0 ? roots : ["packages/core/dist", "release-artifacts"];

function files(path) {
  const absolute = resolve(path);
  if (statSync(absolute).isFile()) return [absolute];
  return readdirSync(absolute, { withFileTypes: true }).flatMap((entry) =>
    files(resolve(absolute, entry.name)),
  );
}

const artifacts = selected
  .flatMap(files)
  .sort()
  .map((path) => {
    const data = readFileSync(path);
    return {
      name: basename(path),
      size: data.length,
      sha256: createHash("sha256").update(data).digest("hex"),
    };
  });

const names = artifacts.map((artifact) => artifact.name);
if (new Set(names).size !== names.length) {
  throw new Error("Release artifacts must have unique basenames");
}
const wheels = names.filter((name) => name.endsWith(".whl"));
const sdists = names.filter((name) => name.endsWith(".tar.gz"));
const npmTarballs = names.filter((name) => name.endsWith(".tgz"));
if (artifacts.length !== 6 || wheels.length !== 1 || sdists.length !== 1 || npmTarballs.length !== 4) {
  throw new Error(
    `Expected one wheel, one sdist, and four npm tarballs; found ${wheels.length}, ${sdists.length}, and ${npmTarballs.length}`,
  );
}

writeFileSync(
  output,
  `${JSON.stringify({ generated_at: new Date().toISOString(), artifacts }, null, 2)}\n`,
  "utf8",
);
console.log(output);

import { rmSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";

const cwd = process.cwd();
for (const target of process.argv.slice(2)) {
  const absolute = resolve(cwd, target);
  const fromCwd = relative(cwd, absolute);
  if (isAbsolute(fromCwd) || fromCwd.startsWith("..")) {
    throw new Error(`Refusing to clean outside package: ${absolute}`);
  }
  rmSync(absolute, { recursive: true, force: true });
}

import { spawn } from "node:child_process";

const entry = process.argv[2];
if (!entry) throw new Error("MCP entry path is required");

const child = spawn(process.execPath, [entry], {
  cwd: process.cwd(),
  env: process.env,
  shell: false,
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
});
let stdout = "";
let stderr = "";
child.stdout.setEncoding("utf8").on("data", (chunk) => (stdout += chunk));
child.stderr.setEncoding("utf8").on("data", (chunk) => (stderr += chunk));

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

await delay(1500);
if (child.exitCode !== null) {
  throw new Error(`MCP server exited during startup (${child.exitCode}): ${stderr}`);
}
if (stdout.length > 0) {
  throw new Error(`MCP server polluted stdout: ${stdout}`);
}
const closed = new Promise((resolve) => child.once("close", resolve));
child.kill();
await Promise.race([
  closed,
  delay(5000).then(() => {
    child.kill("SIGKILL");
    throw new Error("MCP server did not stop within five seconds");
  }),
]);
console.log("MCP stdio startup passed");

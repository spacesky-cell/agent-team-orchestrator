import { spawn } from "node:child_process";

const entry = process.argv[2];
if (!entry) throw new Error("MCP entry path is required");
const expectFailure = process.argv[3] === "--expect-failure";
const expectedCode = process.argv[4];

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
const closed = new Promise((resolve) => child.once("close", resolve));

if (expectFailure) {
  const exitCode = await Promise.race([
    closed,
    delay(10_000).then(() => {
      child.kill("SIGKILL");
      throw new Error("MCP server did not fail within ten seconds");
    }),
  ]);
  if (exitCode === 0) throw new Error("MCP failure smoke exited successfully");
  if (stdout.length > 0) throw new Error(`MCP failure polluted stdout: ${stdout}`);
  if (expectedCode && !stderr.includes(expectedCode)) {
    throw new Error(`MCP failure did not include ${expectedCode}: ${stderr}`);
  }
  if (Buffer.byteLength(stderr) > 8_192) throw new Error("MCP failure diagnostic was unbounded");
  console.log("MCP failure diagnostics passed");
  process.exit(0);
}

await delay(1500);
if (child.exitCode !== null) {
  throw new Error(`MCP server exited during startup (${child.exitCode}): ${stderr}`);
}
if (stdout.length > 0) {
  throw new Error(`MCP server polluted stdout: ${stdout}`);
}
child.kill();
await Promise.race([
  closed,
  delay(5000).then(() => {
    child.kill("SIGKILL");
    throw new Error("MCP server did not stop within five seconds");
  }),
]);
console.log("MCP stdio startup passed");

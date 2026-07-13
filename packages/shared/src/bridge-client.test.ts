import { describe, expect, it } from "vitest";

import { BridgeClient, BridgeClientError } from "./bridge-client.js";

const nodeRuntime = {
  executable: process.execPath,
  version: process.version,
  coreVersion: "test",
};

function client(script: string, timeoutMs = 2_000): BridgeClient {
  return new BridgeClient(nodeRuntime, { bridgeArgs: ["-e", script], timeoutMs });
}

describe("BridgeClient", () => {
  it("parses one strict success envelope", async () => {
    const result = await client('process.stdout.write(JSON.stringify({ok:true,data:{value:1}})+"\\n")').call(
      "doctor",
      {},
    );
    expect(result).toEqual({ value: 1 });
  });

  it("rejects human text on the machine-readable channel", async () => {
    const promise = client('process.stdout.write("warning\\n{}\\n")').call("doctor", {});
    await expect(promise).rejects.toMatchObject({ code: "BRIDGE_PROTOCOL_ERROR" });
  });

  it("preserves structured bridge failures", async () => {
    const script =
      'process.stdout.write(JSON.stringify({ok:false,code:"TASK_NOT_FOUND",message:"missing",details:{}})+"\\n");process.exitCode=1';
    await expect(client(script).call("task-status", {})).rejects.toMatchObject({
      code: "TASK_NOT_FOUND",
      message: "missing",
    });
  });

  it("allows stderr diagnostics but rejects malformed stdout", async () => {
    const success = client(
      'process.stderr.write("diagnostic\\n");process.stdout.write(JSON.stringify({ok:true,data:{ok:true}})+"\\n")',
    );
    await expect(success.call("doctor", {})).resolves.toEqual({ ok: true });

    await expect(client('process.stdout.write("{broken\\n")').call("doctor", {})).rejects.toBeInstanceOf(
      BridgeClientError,
    );
  });

  it("bounds a non-responsive process", async () => {
    await expect(client("setInterval(() => {}, 1000)", 50).call("doctor", {})).rejects.toMatchObject({
      code: "BRIDGE_TIMEOUT",
    });
  });

  it("parses JSONL stream events and rejects malformed lines", async () => {
    const good = client(
      'process.stdout.write(JSON.stringify({type:"progress",task_id:"task-a",data:{step:1}})+"\\n")',
    );
    const events = [];
    for await (const event of good.stream("task-run", {})) events.push(event);
    expect(events).toEqual([{ type: "progress", task_id: "task-a", data: { step: 1 } }]);

    const bad = client('process.stdout.write("not-json\\n")');
    const consume = async () => {
      for await (const _event of bad.stream("task-run", {})) void _event;
    };
    await expect(consume()).rejects.toMatchObject({ code: "BRIDGE_PROTOCOL_ERROR" });
  });
});

export type BridgeResponse<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      code: string;
      message: string;
      details: Record<string, unknown>;
    };

export interface BridgeEvent {
  type: "progress" | "approval_required" | "completed" | "blocked" | "failed";
  task_id: string;
  data: Record<string, unknown>;
}

export interface PythonRuntime {
  executable: string;
  version: string;
  coreVersion: string;
}

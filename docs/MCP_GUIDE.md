# MCP Guide

ATO ships an MCP stdio adapter named `ato-mcp`. It is a protocol adapter over the installed `ato_core` bridge; it does not execute embedded Python or read task files directly.

## Configuration

```json
{
  "mcpServers": {
    "ato": {
      "command": "ato-mcp",
      "env": {
        "ATO_PYTHON": "/absolute/path/to/python",
        "LLM_PROVIDER": "claude-cli"
      }
    }
  }
}
```

Use an absolute Python path when the MCP host has a different PATH from your terminal. Run `ato doctor` in the same environment before configuring the client.

## Tools

| MCP tool | Core command | Required identity |
| --- | --- | --- |
| `create_team_task` | `task-start` | description |
| `get_task_status` | `task-status` | task ID |
| `get_task_audit` | `task-audit` | task ID |
| `approve_step` | `task-approve` | task ID, request ID, approved boolean |
| `list_available_roles` | `roles-list` | none |
| `list_tasks` | `task-list` | output root |
| `query_team_memory` | `memory-query` | query |
| `get_memory_summary` | `memory-summary` | project root |
| `self_check` | `doctor` | project root |

## Asynchronous task flow

1. `create_team_task` persists `queued` state before starting a detached worker and returns immediately.
2. Poll `get_task_status` using the returned task ID.
3. If status is `waiting_approval`, read `active_approval.request_id`.
4. Call `approve_step` with the exact task and request IDs.
5. Continue polling until `completed`, `blocked`, or `failed`.

An approval response is successful only when the Python core accepted the request and restarted the checkpoint worker. Bridge errors are returned with `isError: true` and the stable error code.

## Security notes

- Tool arguments are summarized and secret-like keys are redacted before audit persistence.
- Relative tool paths resolve against the task project root.
- Git commands run in the configured repository.
- Unknown tools are denied by the Python policy layer.
- MCP stdout is reserved for protocol messages; diagnostics go to stderr.

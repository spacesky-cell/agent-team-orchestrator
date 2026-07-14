# @spacesky-cell/ato-mcp-server

MCP stdio adapter for Agent Team Orchestrator. It exposes asynchronous task, status, audit, role, memory, and approval tools backed by the Python owner layer.

End users should install `@spacesky-cell/agent-team-orchestrator`, which includes this adapter and a managed Python core. Direct adapter installation requires `ATO_PYTHON` to point to a compatible environment containing `ato_core`. Runtime diagnostics use stderr; stdout remains MCP protocol-only.

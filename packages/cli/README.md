# @spacesky-cell/ato-cli

Command-line adapter for Agent Team Orchestrator. End users should install `@spacesky-cell/agent-team-orchestrator`, which includes this adapter and the managed Python core.

The CLI delegates task execution, status, audit, memory, and approvals to the installed `ato_core` bridge.

Direct installation of this adapter is intended for development and requires `ATO_PYTHON` to point to a compatible environment containing `ato_core`.

# Agent Team Orchestrator

[![CI](https://github.com/spacesky-cell/agent-team-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/spacesky-cell/agent-team-orchestrator/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/@spacesky-cell/agent-team-orchestrator)](https://www.npmjs.com/package/@spacesky-cell/agent-team-orchestrator)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

ATO is a local multi-agent task runner built on LangGraph. It decomposes a task into role-based work, runs ready branches in parallel, checkpoints progress, and puts mutating tools behind durable approvals. The same Python runtime is exposed through a CLI and an MCP stdio server.

[中文说明](README_CN.md) | [Quickstart](docs/QUICKSTART.md) | [MCP guide](docs/MCP_GUIDE.md) | [Architecture](docs/architecture.md)

## Install

Requirements: Python 3.10+, Node.js 18+, and an LLM provider. The default provider reuses an authenticated [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installation.

```bash
npm install --global @spacesky-cell/agent-team-orchestrator
ato doctor
```

The npm package includes the ATO Python wheel. The first command that needs the core creates an isolated, versioned runtime and may download Python dependencies; npm installation itself runs no postinstall script and does not modify global Python. `ato --version` and help remain immediate.

`ato doctor` verifies the managed Python executable, `ato_core` version, packaged roles, project root, and Claude CLI availability. Advanced users can set `ATO_PYTHON` to a compatible Python that already contains `ato_core`.

## Run A Task

```bash
ato roles
ato run "Review this repository and implement the highest-impact reliability fix" --detach
ato status <task-id>
ato audit <task-id>
```

Omit `--detach` to keep the CLI attached. When a mutating tool needs approval, the CLI shows the durable request ID and resumes the same LangGraph checkpoint after your decision.

```bash
ato approve <task-id> <request-id>
ato approve <task-id> <request-id> --reject
```

Each task owns an isolated directory:

```text
ato-output/tasks/<task-id>/
  task.json
  decomposition.json
  checkpoints.db
  approvals.jsonl
  tool-audit.jsonl
  result.json
```

Task status and approval truth come from `ato_core`; the Node adapters do not infer completion from files.

## MCP

Add the installed stdio command to your MCP client:

```json
{
  "mcpServers": {
    "ato": {
      "command": "ato-mcp",
      "env": {
        "LLM_PROVIDER": "claude-cli"
      }
    }
  }
}
```

The MCP server exposes asynchronous task creation, task-scoped status and audit, exact approval requests, packaged roles, memory queries, and installation diagnostics. `create_team_task` returns a queued task ID immediately.

## Why ATO

| Option | Best fit | ATO difference |
| --- | --- | --- |
| Raw LangGraph | Building a custom agent application | ATO supplies a ready task model, role resources, approvals, persistence, CLI, and MCP adapters. |
| CrewAI | Role-oriented agent applications | ATO emphasizes local checkpoint recovery, task-scoped audit, and explicit tool approval IDs. |
| AutoGen | Conversational multi-agent systems | ATO focuses on dependency graphs and operational task execution rather than open-ended group chat. |
| ATO | Local repository work through CLI or MCP | One Python owner layer, parallel ready branches, durable approvals, and inspectable task directories. |

ATO does not claim to replace those frameworks. It is a focused runtime for users who want an installable, inspectable local workflow instead of assembling the execution boundary themselves.

## Providers

```bash
# Default: authenticated Claude Code CLI
set LLM_PROVIDER=claude-cli

# Anthropic API
set LLM_PROVIDER=anthropic
set ANTHROPIC_API_KEY=...

# OpenAI-compatible provider
set LLM_PROVIDER=openai
set OPENAI_API_KEY=...
```

Use `export` instead of `set` on Unix shells. See [.env.example](.env.example) for all supported settings.

## Current Limits

- Workers and SQLite checkpoints are local to one machine; ATO is not a distributed scheduler.
- LLM task decomposition is validated for roles, dependencies, duplicate IDs, and cycles, but output quality still depends on the selected model.
- Mutating tools pause for approval unless `ATO_AUTO_APPROVE_TOOLS=1` is explicitly enabled for development.
- Semantic memory uses ChromaDB when available and degrades to local structured storage when it is not installed.
- First runtime creation needs access to the configured Python package index unless dependencies are already cached.
- The separately installable CLI and MCP adapter packages do not embed the wheel; end users should install the root package shown above.

## Development

```bash
git clone https://github.com/spacesky-cell/agent-team-orchestrator.git
cd agent-team-orchestrator
python -m pip install -e "packages/core[dev]"
pnpm install --frozen-lockfile
pnpm run verify
```

The Windows clean-install release gate is `./scripts/e2e/cold-install.ps1`; Linux uses `./scripts/e2e/cold-install.sh`.

## Uninstall

```bash
npm uninstall --global @spacesky-cell/agent-team-orchestrator
```

Uninstall does not silently remove task outputs or the managed Python runtime. Runtime data is stored below `%LOCALAPPDATA%\AgentTeamOrchestrator` on Windows, `~/Library/Application Support/AgentTeamOrchestrator` on macOS, and `${XDG_DATA_HOME:-~/.local/share}/agent-team-orchestrator` on Linux. Set `ATO_HOME` to choose a different root, or remove that directory deliberately after uninstalling.

Task outputs are ordinary local files and are not removed automatically.

## License

[MIT](LICENSE)

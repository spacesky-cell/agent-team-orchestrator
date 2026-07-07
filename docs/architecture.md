# ATO Architecture

## Claude Code MCP Flow

ATO exposes a project-level MCP server that lets Claude Code call into the local orchestrator without committing secrets:

```text
Claude Code
  -> ATO MCP server (TypeScript stdio)
  -> @spacesky-cell/ato-shared Python runner
  -> Python ToolEnabledOrchestrator
  -> Claude Code CLI or API LLM provider
  -> role-scoped project tools
  -> result.json + tool-audit.jsonl
```

## Structured Claude CLI Tool Bridge

The `claude-cli` provider does not expose native LangChain `tool_calls`, so ATO uses a small JSON protocol inside the Python orchestrator:

```json
{"type":"tool_call","name":"read_file","args":{"path":"README.md"}}
```

```json
{"type":"final","content":"final deliverable"}
```

The orchestrator owns parsing, policy checks, execution, and loop control. MCP and CLI remain adapters: they start tasks and display state, but they do not decide whether a tool is safe.

## Tool Policy

Read-only tools run automatically by default:

- `read_file`
- `list_directory`
- `search_code`
- `analyze_file`

Restricted tools require explicit local auto-approval in non-interactive runs:

- `write_file`
- `delete_file`
- `execute_command`
- `run_tests`
- `git_commit`

Set `ATO_AUTO_APPROVE_TOOLS=1` only for trusted local debugging. Without it, restricted tool requests return a structured blocked result and fail the subtask instead of hanging.

## Audit Trail

Every tool attempt is appended to `tool-audit.jsonl` in the task output directory. Each event records the task, subtask, role, tool name, redacted argument summary, policy decision, status, duration, and error when present.

Use these entrypoints to inspect it:

```bash
node packages/cli/dist/index.js audit --output ./ato-output
```

```text
get_task_audit(outputDir: "./ato-output")
```

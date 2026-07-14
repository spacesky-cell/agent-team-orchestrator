# Quickstart

## 1. Install ATO

```bash
npm install --global @spacesky-cell/agent-team-orchestrator
```

ATO needs Python 3.10+ and Node.js 18+. The npm package embeds the Python core wheel. The first real command creates a versioned virtual environment under the ATO data directory and may download its Python dependencies. npm installation has no postinstall script.

By default ATO invokes an authenticated Claude Code CLI. Advanced users can select a Python environment that already contains a compatible `ato_core`:

```bash
export ATO_PYTHON=/absolute/path/to/python
```

On PowerShell use `$env:ATO_PYTHON = "C:\path\to\python.exe"`.

## 2. Verify the installation

```bash
ato --version
ato doctor
ato roles
```

`doctor` does not call an LLM. On first use it prepares the managed runtime, then reports its exact Python path and core version. Later commands reuse that runtime.

## 3. Start a task

```bash
ato run "Inspect this project and add tests for the riskiest behavior" --detach
```

The command returns a task ID and its task directory. Use that exact ID:

```bash
ato status <task-id>
ato audit <task-id>
ato tasks
```

Without `--detach`, the CLI follows the task until it completes, fails, blocks, or requests approval.

## 4. Handle approvals

Read-only tools run automatically. Mutating tools persist an approval request and pause the checkpoint.

```bash
ato status <task-id>
ato approve <task-id> <request-id>
```

Reject with `--reject`. A stale or mismatched request ID fails with `APPROVAL_NOT_PENDING`; ATO never treats it as a successful approval.

## 5. Inspect outputs

```text
ato-output/tasks/<task-id>/task.json          current summary
ato-output/tasks/<task-id>/decomposition.json validated subtask graph
ato-output/tasks/<task-id>/checkpoints.db     LangGraph state
ato-output/tasks/<task-id>/approvals.jsonl    requests and decisions
ato-output/tasks/<task-id>/tool-audit.jsonl   redacted tool events
ato-output/tasks/<task-id>/result.json        terminal result only
```

If a worker dies after its heartbeat becomes stale, the next status check reports `WORKER_LOST` instead of a false running state.

## Provider configuration

```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
```

OpenAI-compatible providers use `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and optional `OPENAI_BASE_URL`. See [../.env.example](../.env.example).

Next: [MCP guide](MCP_GUIDE.md) or [examples](EXAMPLES.md).

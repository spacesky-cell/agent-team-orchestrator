# ato-core

Python owner layer for Agent Team Orchestrator. It provides task persistence, LangGraph execution, tool policy, durable approvals, packaged roles, memory, and the stable JSON bridge used by the npm adapters.

## Install

```bash
pip install ato-core
```

## Verify

```bash
python -c "import ato_core; print(ato_core.__version__)"
echo '{}' | python -m ato_core.bridge doctor
echo '{}' | python -m ato_core.bridge roles-list
```

On Windows, the bridge accepts UTF-8 stdin with or without a BOM.

## Configuration

The default `LLM_PROVIDER=claude-cli` reuses an authenticated Claude Code CLI. Anthropic, OpenAI-compatible, and Ollama providers are also supported through environment variables documented in the repository [.env.example](../../.env.example).

Most users should install the root npm package as well and operate ATO through `ato` or `ato-mcp`. The Python bridge is a machine protocol; human diagnostics belong on stderr.

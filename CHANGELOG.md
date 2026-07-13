# Changelog

All notable changes to the Agent Team Orchestrator (ATO) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-13

### Added
- Durable, request-ID-based approval records that resume the same LangGraph checkpoint after process recreation.
- Task-scoped state, checkpoints, audit logs, results, worker heartbeats, and background execution.
- A stable `python -m ato_core.bridge` protocol used by both CLI and MCP adapters.
- Clean-install gates for Windows and Linux plus SHA-256 release manifests.

### Changed
- Publish the Python owner layer as `ato-core` with the import package `ato_core` and bundled role resources.
- Run dependency-ready graph branches in parallel with reducer-safe execution deltas.
- Make the npm root, CLI, shared, and MCP packages independently inspectable and executable.
- Treat the CLI and MCP server as protocol adapters; task status, approvals, and audit truth stay in Python.
- Enforce Black, Ruff, strict MyPy, TypeScript checks, coverage, builds, and package smoke tests in CI.

### Fixed
- Reject invalid decomposition graphs, unsafe tool schemas, outside-root paths, stale approvals, and false worker health.
- Run Git and subprocess tools against the configured project root with bounded output and timeouts.
- Return success for `ato --version` without requiring Python discovery.
- Remove the broken `src.*` import path and duplicate graph implementations.
- Type-check worker launch flags on every platform and use the standard TOML parser when available.

### Security
- Redact secret-like tool arguments before persistence and require explicit approval for mutating tools by default.

### Migration
- Install both runtime layers with `pip install ato-core` and `npm install --global @spacesky-cell/agent-team-orchestrator`.
- Replace Python imports from `src.*` with `ato_core.*`; no compatibility package is shipped.
- Use exact task and request IDs for status, audit, and approval calls. Existing shared `ato-output/result.json` workflows are not supported.

### Known limitations
- Workers and SQLite checkpoints are local to one machine; ATO is not a distributed scheduler.
- The CLI and MCP adapters require both the npm package and the Python `ato-core` package.
- LLM decomposition quality depends on the selected provider even though graph structure is validated.

## [0.1.0] - 2026-07-07

### Added
- First public release
- Core orchestration engine based on LangGraph
- Python SDK (`ato_core`) and TypeScript packages (`@spacesky-cell/ato-mcp-server`, `@spacesky-cell/ato-cli`, `@spacesky-cell/ato-shared`)
- Role system with YAML-driven definitions
- Tool system with extensible base class architecture
- Claude Code CLI provider and project-level MCP integration
- Structured Claude CLI tool-call bridge with JSON Schema constrained responses
- Tool policy and JSONL audit trail for role-scoped tool execution
- CLI and MCP audit visibility via `ato audit`, `get_task_status`, and `get_task_audit`
- Team memory system with ADR and code-change tracking
- Task decomposition, checkpointing, and dependency-aware execution
- Mermaid visualization helpers

[Unreleased]: https://github.com/spacesky-cell/agent-team-orchestrator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/spacesky-cell/agent-team-orchestrator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/spacesky-cell/agent-team-orchestrator/releases/tag/v0.1.0
- Documentation for setup, MCP usage, and architecture

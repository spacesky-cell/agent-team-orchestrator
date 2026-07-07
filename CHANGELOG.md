# Changelog

All notable changes to the Agent Team Orchestrator (ATO) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Documentation for setup, MCP usage, and architecture

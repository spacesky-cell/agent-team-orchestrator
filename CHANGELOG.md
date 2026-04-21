# Changelog

All notable changes to the Agent Team Orchestrator (ATO) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of Agent Team Orchestrator (ATO)
- **5 Orchestrator Implementations**:
  - `SimpleOrchestrator`: Sequential execution for quick prototyping
  - `GraphOrchestrator`: LangGraph DAG with in-memory checkpointing
  - `ParallelGraphOrchestrator`: Parallel subtask execution via Send API
  - `PersistentGraphOrchestrator`: SQLite-based persistent checkpointing
  - `ToolEnabledOrchestrator`: Full ReAct loop with tool calling and team memory
- **Multi-LLM Provider Support**: Anthropic Claude, OpenAI, NVIDIA API, Ollama local models
- **3 Built-in Roles**: Architect, Backend Developer, Tester, Frontend Developer, Fullstack Developer
- **9 Built-in Tools**: ReadFile, WriteFile, ListDirectory, DeleteFile, SearchCode, ExecuteCommand, AnalyzeFile, RunTests, GitCommit
- **Team Memory System**: SQLite + ChromaDB for semantic search, ADR support, code change tracking
- **Task Decomposition**: AI-powered automatic task breakdown with dependency resolution
- **Visualization**: Mermaid diagram generation (DAG, timeline, state diagrams)
- **MCP Server**: Claude Code integration via Model Context Protocol
- **CLI Tool**: Command-line interface with task management commands
- **JSON Schema Validation**: Role definition validation against schema
- **Security Features**: Path sandboxing, command blacklist, file size limits

### Documentation
- Bilingual README (English/Chinese)
- Quick Start Guide
- MCP Integration Guide
- Usage Examples (10+ examples)
- Contributing Guidelines

## [0.1.0] - 2025-04-21

### Added
- First public release
- Core orchestration engine based on LangGraph
- Python SDK (`ato_core`) and TypeScript packages (`@ato/mcp-server`, `@ato/cli`, `@ato/shared`)
- Role system with YAML-driven definitions
- Tool system with extensible base class architecture

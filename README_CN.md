# Agent Team Orchestrator

[![CI](https://github.com/spacesky-cell/agent-team-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/spacesky-cell/agent-team-orchestrator/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ato-core)](https://pypi.org/project/ato-core/)
[![npm](https://img.shields.io/npm/v/@spacesky-cell/agent-team-orchestrator)](https://www.npmjs.com/package/@spacesky-cell/agent-team-orchestrator)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

ATO 是一个基于 LangGraph 的本地多智能体任务运行时。它会把任务拆成不同角色负责的子任务，并行执行当前可运行的分支，持久化 checkpoint，同时把写文件、执行命令、提交 Git 等变更操作放在可恢复的审批之后。Python 核心通过 CLI 与 MCP stdio server 提供同一套能力。

[English](README.md) | [快速开始](docs/QUICKSTART.md) | [MCP 指南](docs/MCP_GUIDE.md) | [架构](docs/architecture.md)

## 安装

需要 Python 3.10+、Node.js 18+ 和一个 LLM provider。默认复用已经登录的 Claude Code CLI。

```bash
pip install ato-core
npm install --global @spacesky-cell/agent-team-orchestrator
ato doctor
```

`ato doctor` 会检查 Python 路径、`ato_core` 版本、内置角色、项目目录和 Claude CLI。若目标 Python 不在 PATH 首位，请设置 `ATO_PYTHON`。

## 运行任务

```bash
ato roles
ato run "检查这个仓库，并实现影响最大的可靠性改进" --detach
ato status <task-id>
ato audit <task-id>
```

不加 `--detach` 时，CLI 会持续跟踪任务。变更类工具需要审批时，CLI 会显示持久化的 request ID；批准后恢复同一个 LangGraph checkpoint，不会从头执行。

```bash
ato approve <task-id> <request-id>
ato approve <task-id> <request-id> --reject
```

每个任务拥有独立目录：

```text
ato-output/tasks/<task-id>/
  task.json
  decomposition.json
  checkpoints.db
  approvals.jsonl
  tool-audit.jsonl
  result.json
```

状态和审批结论只由 `ato_core` 维护；Node CLI/MCP 不通过猜测文件来宣布成功。

## MCP

在 MCP 客户端中配置：

```json
{
  "mcpServers": {
    "ato": {
      "command": "ato-mcp",
      "env": {
        "ATO_PYTHON": "C:\\absolute\\path\\to\\python.exe"
      }
    }
  }
}
```

`create_team_task` 会立即返回 queued task ID。后续通过 task ID 查询状态、审计和 active approval；`approve_step` 必须同时提供 task ID、request ID 和批准结果。

## 适用边界

| 方案 | 更适合 | ATO 的侧重点 |
| --- | --- | --- |
| 原生 LangGraph | 自行开发完整 agent 应用 | ATO 已提供任务模型、角色资源、审批、持久化、CLI 和 MCP。 |
| CrewAI | 角色驱动的 agent 应用 | ATO 更强调本地 checkpoint 恢复、任务级审计和精确审批 ID。 |
| AutoGen | 对话型多智能体系统 | ATO 面向依赖图和可操作任务，而不是开放式群聊。 |
| ATO | 通过 CLI/MCP 执行本地仓库任务 | 单一 Python 真相源、ready 分支并行、持久审批、可检查任务目录。 |

## 当前限制

- worker 与 SQLite checkpoint 位于单机，ATO 不是分布式调度器。
- 任务拆分会校验角色、依赖、重复 ID 与环，但实际质量仍依赖模型。
- 变更工具默认必须审批；`ATO_AUTO_APPROVE_TOOLS=1` 只建议在开发环境显式使用。
- 安装了 ChromaDB 时可使用语义记忆，否则退化为本地结构化存储。
- CLI/MCP 同时依赖 npm 包与 Python `ato-core`。

## 开发与验证

```bash
git clone https://github.com/spacesky-cell/agent-team-orchestrator.git
cd agent-team-orchestrator
python -m pip install -e "packages/core[dev]"
pnpm install --frozen-lockfile
pnpm run verify
```

Windows 冷安装门禁：`./scripts/e2e/cold-install.ps1`；Linux：`./scripts/e2e/cold-install.sh`。

## 卸载

```bash
npm uninstall --global @spacesky-cell/agent-team-orchestrator
pip uninstall ato-core
```

任务输出是普通本地文件，不会自动删除。

## 许可证

[MIT](LICENSE)

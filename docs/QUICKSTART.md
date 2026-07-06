# 快速开始指南

本指南将帮助你快速上手 Agent Team Orchestrator (ATO)，在 5 分钟内启动你的第一个多 Agent 协作任务。

## 前置条件

- Python 3.10+
- Node.js 18+
- 已登录的 Claude Code CLI，或一个 LLM API Key（Anthropic、OpenAI 或 Ollama）

## 第一步：安装

```bash
# 克隆仓库
git clone <your-repo-url>
cd ato

# 创建 Python 虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装 Python 依赖
python -m pip install -e packages/core[dev]

# 安装 Node.js 依赖
pnpm install

# 如果 pnpm 拦截 esbuild build script，执行一次审批
pnpm approve-builds

# 构建 TypeScript 包
pnpm run build

# 不调用 LLM 的本地连通性检查
node packages/cli/dist/index.js doctor
```

## 第二步：配置 LLM

```bash
# 复制环境变量示例文件
cp .env.example .env

# 默认使用已登录的 Claude Code CLI，不需要 API Key
```

### 默认：复用 Claude Code CLI 登录态

```bash
LLM_PROVIDER=claude-cli
```

### Anthropic Claude 直连 API

```bash
ANTHROPIC_API_KEY=sk-ant-xxx
```

### OpenAI

```bash
OPENAI_API_KEY=sk-xxx
```

## 第三步：运行第一个任务

### 方式 1：通过 Python 脚本

```python
from src.orchestrator.simple_orchestrator import SimpleOrchestrator

orchestrator = SimpleOrchestrator()

# 一句话启动多 Agent 协作
decomposition = orchestrator.decompose_task("开发一个简单的待办事项管理 API")
result = orchestrator.execute_task(decomposition)

# 查看结果
print(f"任务状态: {result.status}")
for subtask_id, artifact in result.artifacts.items():
    print(f"\n{subtask_id}:\n{artifact}")
```

### 方式 2：通过 CLI

```bash
node packages/cli/dist/index.js run "开发一个简单的待办事项管理 API"
```

### 方式 3：通过 MCP Server（推荐）

仓库已包含项目级 `.mcp.json`：

```json
{
  "mcpServers": {
    "ato": {
      "command": "node",
      "args": ["packages/mcp-server/dist/index.js"],
      "env": {
        "LLM_PROVIDER": "claude-cli"
      }
    }
  }
}
```

然后在 Claude Code 中调用 `create_team_task` 工具。

先用 Claude Code 检查 MCP 是否连接：

```bash
claude mcp list
claude mcp get ato
```

默认 `claude-cli` 会复用本机 Claude Code CLI 登录态。若改用直连 API，真实密钥放在 shell 环境变量或 `.env` 中，不写入 `.mcp.json`：

```bash
ANTHROPIC_API_KEY=sk-ant-xxx
```

## 工作原理

当你运行一个任务时，ATO 会：

1. **任务分解** - 自动将你的任务拆解为多个子任务
2. **角色分配** - 根据子任务类型分配给合适的 Agent 角色
3. **并行执行** - 多个 Agent 同时工作
4. **结果合并** - 收集所有 Agent 的输出并保存

## 示例输出

```
============================================================
Task Decomposition
============================================================

Task ID: task-20240421-abc123
Summary: 开发一个简单的待办事项管理 API

Subtasks (4):
  1. 设计待办事项 API 架构 (architect)
  2. 实现待办事项 CRUD 接口 (backend-developer)
  3. 编写 API 测试用例 (tester)
  4. 编写 API 文档 (backend-developer)

============================================================
Executing Task: 开发一个简单的待办事项管理 API
============================================================

Subtask 1/4: 设计待办事项 API 架构 (architect)
  Output preview: ## API 架构设计
  ### 端点设计
  - GET /api/todos - 获取所有待办事项
  - POST /api/todos - 创建新待办事项
  ...

Subtask 2/4: 实现待办事项 CRUD 接口 (backend-developer)
  Output preview: from fastapi import FastAPI
  app = FastAPI()
  ...

Subtask 3/4: 编写 API 测试用例 (tester)
  Output preview: def test_create_todo():
      response = client.post("/api/todos", json={"title": "Test"})
      ...

Subtask 4/4: 编写 API 文档 (backend-developer)
  Output preview: # 待办事项 API 文档
  ## 概述
  ...

✓ Task completed successfully!

Artifacts saved to: /path/to/ato-output
```

## 下一步

- 查看 [README.md](README.md) 了解更多功能
- 查看 [roles/](../roles/) 目录了解内置角色
- 自定义你的角色和工具
- 集成到你的开发工作流中

## 常见问题

### Q: 如何添加自定义角色？

A: 在 `roles/` 目录创建新的 YAML 文件，参考 [roles/architect.yaml](../roles/architect.yaml)。

### Q: 如何使用本地模型？

A: 配置 Ollama 并设置环境变量：
```bash
LLM_PROVIDER=ollama
LLM_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434/v1
```

### Q: 如何查看任务历史？

A: 使用 `get_task_status` MCP 工具或查看 `ato-output/checkpoints.db`。

### Q: 如何恢复中断的任务？

A: 使用 `list_incomplete_tasks` MCP 工具查看未完成任务，然后使用相同的 task_id 重新执行。

## 获取帮助

- 提交 Issue: [GitHub Issues](https://github.com/spacesky-cell/agent-team-orchestrator/issues)
- 查看文档: [docs/](../docs/)

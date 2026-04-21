# MCP 集成指南

本指南详细介绍如何将 Agent Team Orchestrator (ATO) 作为 MCP Server 集成到 Claude Code 中。

## 什么是 MCP？

MCP (Model Context Protocol) 是一个开放标准，允许 AI 助手与外部工具和数据源进行交互。通过 MCP，你可以让 Claude Code 直接调用 ATO 的功能。

## 配置 MCP Server

### 步骤 1：找到 Claude Code 配置文件

Claude Code 的配置文件位置：

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### 步骤 2：添加 ATO MCP Server 配置

打开配置文件，添加以下内容：

```json
{
  "mcpServers": {
    "ato": {
      "command": "node",
      "args": ["./packages/mcp-server/dist/index.js"],
      "env": {
        "ANTHROPIC_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**重要提示：**
- 将 `your-api-key-here` 替换为你的实际 API Key
- 确保路径指向正确的项目位置
- 如果使用其他 LLM 提供商，修改相应的环境变量

### 步骤 3：重启 Claude Code

配置完成后，重启 Claude Code 以加载新的 MCP Server。

## 可用的 MCP 工具

配置成功后，你可以在 Claude Code 中使用以下工具：

### 1. create_team_task

创建并执行团队任务，自动分解并多 Agent 并行执行。

**参数：**
- `description` (必需): 任务描述
- `outputDir` (可选): 输出目录，默认 `./ato-output`
- `projectRoot` (可选): 项目根目录，默认 `.`

**示例：**
```
请使用 create_team_task 工具，帮我开发一个用户认证系统，包括注册、登录、登出功能
```

### 2. get_task_status

查询任务执行状态。

**参数：**
- `taskId` (必需): 任务 ID

**示例：**
```
请使用 get_task_status 工具，查询任务 task-123456 的状态
```

### 3. list_available_roles

列出所有可用的 Agent 角色及其能力。

**参数：** 无

**示例：**
```
请使用 list_available_roles 工具，查看所有可用的角色
```

### 4. query_team_memory

搜索团队记忆，返回相关的架构决策和代码变更。

**参数：**
- `query` (必需): 搜索查询
- `topK` (可选): 返回结果数量，默认 5

**示例：**
```
请使用 query_team_memory 工具，搜索关于数据库设计的相关信息
```

### 5. get_memory_summary

获取团队记忆摘要。

**参数：** 无

**示例：**
```
请使用 get_memory_summary 工具，查看团队记忆摘要
```

### 6. list_incomplete_tasks

列出未完成的任务。

**参数：** 无

**示例：**
```
请使用 list_incomplete_tasks 工具，查看所有未完成的任务
```

### 7. approve_step

批准或拒绝当前步骤（用于人工审批流程）。

**参数：**
- `taskId` (必需): 任务 ID
- `approved` (必需): 是否批准

**示例：**
```
请使用 approve_step 工具，批准任务 task-123456 的当前步骤
```

## 使用示例

### 示例 1：开发一个完整的 API

```
我需要开发一个待办事项管理 API，请使用 create_team_task 工具帮我完成。

需求：
- 支持创建、读取、更新、删除待办事项
- 每个待办事项包含标题、描述、完成状态
- 提供 RESTful API 接口
- 编写测试用例
```

ATO 会自动：
1. 分解任务为多个子任务
2. 分配给架构师、后端开发、测试工程师等角色
3. 并行执行所有子任务
4. 保存结果到 `ato-output/result.json`

### 示例 2：查看任务进度

```
请使用 get_task_status 工具，查看刚才创建的任务状态
```

### 示例 3：搜索历史决策

```
我之前在这个项目中做过数据库设计，请使用 query_team_memory 工具搜索相关信息
```

## 高级配置

### 使用不同的 LLM 提供商

#### OpenAI

```json
{
  "mcpServers": {
    "ato": {
      "command": "node",
      "args": ["./packages/mcp-server/dist/index.js"],
      "env": {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "your-openai-key"
      }
    }
  }
}
```

#### NVIDIA API

```json
{
  "mcpServers": {
    "ato": {
      "command": "node",
      "args": ["./packages/mcp-server/dist/index.js"],
      "env": {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "z-ai/glm4.7",
        "OPENAI_API_KEY": "nvapi-xxx",
        "OPENAI_BASE_URL": "https://integrate.api.nvidia.com/v1"
      }
    }
  }
}
```

#### Ollama（本地模型）

```json
{
  "mcpServers": {
    "ato": {
      "command": "node",
      "args": ["./packages/mcp-server/dist/index.js"],
      "env": {
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": "llama3",
        "OLLAMA_BASE_URL": "http://localhost:11434/v1"
      }
    }
  }
}
```

### 自定义输出目录

```json
{
  "mcpServers": {
    "ato": {
      "command": "node",
      "args": ["./packages/mcp-server/dist/index.js"],
      "env": {
        "ANTHROPIC_API_KEY": "your-key"
      }
    }
  }
}
```

然后在调用 `create_team_task` 时指定 `outputDir` 参数。

## 故障排查

### 问题：MCP Server 无法启动

**解决方案：**
1. 检查 Node.js 是否已安装（需要 18+）
2. 检查 TypeScript 包是否已构建：`npm run build`
3. 检查路径是否正确
4. 查看 Claude Code 日志获取详细错误信息

### 问题：工具调用失败

**解决方案：**
1. 检查 API Key 是否正确
2. 检查网络连接
3. 检查环境变量是否正确设置
4. 尝试使用不同的 LLM 提供商

### 问题：任务执行超时

**解决方案：**
1. 检查任务描述是否过于复杂
2. 考虑将大任务拆分为多个小任务
3. 检查 LLM API 的速率限制

### 问题：找不到 MCP 工具

**解决方案：**
1. 确认配置文件格式正确
2. 重启 Claude Code
3. 检查 MCP Server 是否成功启动

## 最佳实践

1. **任务描述要清晰**：提供详细的需求和期望输出
2. **合理拆分任务**：对于复杂项目，考虑分阶段执行
3. **利用团队记忆**：定期查询团队记忆，避免重复工作
4. **检查任务状态**：定期查看任务进度，及时发现问题
5. **保存重要结果**：将重要的架构决策和代码变更保存到团队记忆

## 下一步

- 查看 [快速开始指南](QUICKSTART.md)
- 了解 [内置角色](../roles/)
- 自定义你的角色和工具
- 探索更多 MCP 集成可能性

## 获取帮助

- 提交 Issue: [GitHub Issues](https://github.com/spacesky-cell/agent-team-orchestrator/issues)
- 查看 MCP 文档: [Model Context Protocol](https://modelcontextprotocol.io/)

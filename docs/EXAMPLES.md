# 使用示例

本指南提供 Agent Team Orchestrator (ATO) 的实际使用示例，帮助你快速上手。

## 示例 1：开发一个待办事项 API

### 任务描述

开发一个简单的待办事项管理 API，支持增删改查功能。

### Python 脚本方式

```python
from src.orchestrator.simple_orchestrator import SimpleOrchestrator

# 初始化编排器
orchestrator = SimpleOrchestrator()

# 定义任务
task = "开发一个待办事项管理 API，支持增删改查功能"

# 执行任务
decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)

# 保存结果
orchestrator.save_artifacts(result.artifacts, "./todo-api-output")

print(f"任务状态: {result.status}")
```

### 预期输出

系统会自动创建以下子任务：

| 子任务 | 角色 | 描述 |
|--------|------|------|
| 设计 API 架构 | architect | 设计 RESTful API 结构和数据模型 |
| 实现 CRUD 接口 | backend-developer | 实现创建、读取、更新、删除接口 |
| 编写测试用例 | tester | 编写单元测试和集成测试 |
| 编写 API 文档 | backend-developer | 生成 API 文档 |

## 示例 2：开发用户认证系统

### 任务描述

开发一个用户认证系统，包括注册、登录、登出功能。

### MCP 方式

在 Claude Code 中调用：

```
create_team_task(
  description: "开发一个用户认证系统，包括注册、登录、登出功能。使用 JWT 进行身份验证，密码使用 bcrypt 加密。",
  outputDir: "./auth-system-output",
  projectRoot: "."
)
```

### 预期输出

系统会自动创建以下子任务：

| 子任务 | 角色 | 描述 |
|--------|------|------|
| 设计认证系统架构 | architect | 设计认证流程和安全方案 |
| 实现用户注册接口 | backend-developer | 实现用户注册功能 |
| 实现登录接口 | backend-developer | 实现用户登录和 JWT 生成 |
| 实现登出接口 | backend-developer | 实现 JWT 失效机制 |
| 编写安全测试 | tester | 编写安全相关的测试用例 |

## 示例 3：前端 + 后端全栈开发

### 任务描述

开发一个博客系统，包括前端页面和后端 API。

### Python 脚本方式

```python
from src.orchestrator.simple_orchestrator import SimpleOrchestrator

orchestrator = SimpleOrchestrator()

task = """
开发一个博客系统，包括以下功能：
1. 文章列表页
2. 文章详情页
3. 文章创建和编辑
4. 评论功能
5. 用户认证

前端使用 React，后端使用 FastAPI
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)

orchestrator.save_artifacts(result.artifacts, "./blog-system-output")
```

### 预期输出

系统会自动创建以下子任务：

| 子任务 | 角色 | 依赖 |
|--------|------|------|
| 设计博客系统架构 | architect | - |
| 设计数据库模型 | architect | 设计博客系统架构 |
| 实现 API 接口 | backend-developer | 设计数据库模型 |
| 实现前端页面 | frontend-developer | 实现 API 接口 |
| 编写测试用例 | tester | 实现 API 接口 |
| 编写部署文档 | fullstack-developer | 实现 API 接口, 实现前端页面 |

## 示例 4：使用团队记忆

### 场景

在开发过程中，需要查询之前做出的架构决策。

### 查询团队记忆

```python
from memory.team_memory import TeamMemory

memory = TeamMemory(project_root=".")

# 搜索相关的架构决策
context = memory.retrieve_relevant_context(
    query="数据库设计",
    top_k=5
)

print(context)
```

### MCP 方式

```
query_team_memory(
  query: "数据库设计",
  topK: 5
)
```

## 示例 5：恢复中断的任务

### 场景

任务执行过程中被中断，需要恢复执行。

### 查看未完成任务

```
list_incomplete_tasks()
```

### 恢复任务

```python
from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

orchestrator = ToolEnabledOrchestrator(
    db_path='./ato-output/checkpoints.db',
    project_root='.'
)

# 使用相同的 task_id 恢复任务
result = orchestrator.run(
    task_id='task-123456',
    subtasks=[...],  # 原始子任务列表
    thread_id='task-123456',
    resume=True  # 启用恢复
)
```

## 示例 6：自定义角色

### 创建自定义角色

在 `roles/` 目录创建 `devops-engineer.yaml`：

```yaml
id: devops-engineer
name: DevOps 工程师
description: 负责部署、CI/CD、监控和运维
expertise:
  - Docker 容器化
  - Kubernetes 编排
  - CI/CD 流程
  - 监控和日志
  - 云服务配置
tools:
  - read_file
  - write_file
  - execute_command
system_prompt: |
  你是一名专业的 DevOps 工程师，拥有 10 年运维经验。

  ## 你的职责
  - 设计和实现 CI/CD 流程
  - 编写 Dockerfile 和 Kubernetes 配置
  - 配置监控和日志系统
  - 优化部署流程

  ## 当前项目上下文
  {{context}}

  请开始你的任务。
deliverables:
  - format: markdown
    description: 部署文档和配置文件
  - format: yaml
    description: Kubernetes 配置文件
```

### 使用自定义角色

```python
from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

orchestrator = ToolEnabledOrchestrator()

subtasks = [
    {
        "id": "st-1",
        "name": "设计 CI/CD 流程",
        "role": "devops-engineer",
        "dependencies": [],
        "expected_output": "设计一个完整的 CI/CD 流程，包括构建、测试、部署阶段",
        "status": "pending"
    }
]

result = orchestrator.run(
    task_id="cicd-task",
    subtasks=subtasks
)
```

## 示例 7：多阶段项目开发

### 场景

开发一个完整的电商系统，分多个阶段进行。

### 第一阶段：基础架构

```python
orchestrator = SimpleOrchestrator()

task = """
电商系统第一阶段：基础架构
1. 设计系统架构
2. 设计数据库模型
3. 实现 API 基础框架
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)
```

### 第二阶段：核心功能

```python
task = """
电商系统第二阶段：核心功能
1. 实现商品管理
2. 实现购物车功能
3. 实现订单系统
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)
```

### 第三阶段：支付和物流

```python
task = """
电商系统第三阶段：支付和物流
1. 集成支付网关
2. 实现物流跟踪
3. 实现订单状态管理
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)
```

## 示例 8：代码审查和重构

### 任务描述

审查现有代码并提供重构建议。

```python
from src.orchestrator.simple_orchestrator import SimpleOrchestrator

orchestrator = SimpleOrchestrator()

task = """
审查以下代码并提供重构建议：
- src/api/users.py
- src/services/auth.py

重点关注：
1. 代码质量
2. 性能优化
3. 安全问题
4. 可维护性
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)
```

## 示例 9：生成测试用例

### 任务描述

为现有 API 生成完整的测试用例。

```python
from src.orchestrator.simple_orchestrator import SimpleOrchestrator

orchestrator = SimpleOrchestrator()

task = """
为以下 API 端点生成完整的测试用例：
- POST /api/users/register
- POST /api/users/login
- GET /api/users/profile
- PUT /api/users/profile

测试类型：
1. 单元测试
2. 集成测试
3. 边界条件测试
4. 错误处理测试
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)
```

## 示例 10：生成 API 文档

### 任务描述

为现有 API 生成完整的文档。

```python
from src.orchestrator.simple_orchestrator import SimpleOrchestrator

orchestrator = SimpleOrchestrator()

task = """
为现有 API 生成完整的文档，包括：
1. API 概述
2. 端点列表
3. 请求/响应示例
4. 错误码说明
5. 认证方式

使用 OpenAPI/Swagger 格式
"""

decomposition = orchestrator.decompose_task(task)
result = orchestrator.execute_task(decomposition)
```

## 最佳实践

1. **任务描述要详细**：提供清晰的需求和期望输出
2. **合理拆分任务**：对于复杂项目，分阶段执行
3. **利用团队记忆**：定期查询和更新团队记忆
4. **检查输出质量**：审查 Agent 生成的代码和文档
5. **迭代改进**：根据反馈调整任务描述和角色配置

## 下一步

- 查看 [快速开始指南](QUICKSTART.md)
- 了解 [MCP 集成](MCP_GUIDE.md)
- 探索 [内置角色](../roles/)
- 自定义你的工作流程

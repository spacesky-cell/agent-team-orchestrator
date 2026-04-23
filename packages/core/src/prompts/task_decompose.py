"""Task decomposition prompts for supervisor agent."""

import uuid

from pydantic import BaseModel, Field

# Few-shot examples for task decomposition
EXAMPLES = """
## Example 1: User Login Feature

User Task: 开发一个用户登录功能，包含邮箱密码登录和忘记密码功能

Response:
{
  "task_id": "task-user-login-001",
  "summary": "开发用户登录功能系统，包含基础登录、密码重置等能力",
  "subtasks": [
    {
      "id": "subtask-1",
      "name": "设计登录功能架构",
      "role": "architect",
      "dependencies": [],
      "expected_output": "登录功能架构设计文档，包含数据流、安全方案、API 规范"
    },
    {
      "id": "subtask-2",
      "name": "实现登录 API 和认证服务",
      "role": "backend-developer",
      "dependencies": ["subtask-1"],
      "expected_output": "登录 API 实现代码，JWT 认证服务，单元测试"
    },
    {
      "id": "subtask-3",
      "name": "实现忘记密码功能",
      "role": "backend-developer",
      "dependencies": ["subtask-1"],
      "expected_output": "密码重置 API 实现，邮件发送服务，令牌验证"
    },
    {
      "id": "subtask-4",
      "name": "编写集成测试和 E2E 测试",
      "role": "tester",
      "dependencies": ["subtask-2", "subtask-3"],
      "expected_output": "登录功能测试套件，测试报告"
    }
  ]
}

## Example 2: Simple CRUD API

User Task: 创建一个简单的文章管理 API，支持增删改查

Response:
{
  "task_id": "task-article-crud-001",
  "summary": "实现文章管理 REST API，支持完整的 CRUD 操作",
  "subtasks": [
    {
      "id": "subtask-1",
      "name": "设计文章数据模型和 API 规范",
      "role": "architect",
      "dependencies": [],
      "expected_output": "数据模型设计，OpenAPI 规范文档"
    },
    {
      "id": "subtask-2",
      "name": "实现文章 CRUD API",
      "role": "backend-developer",
      "dependencies": ["subtask-1"],
      "expected_output": "文章 API 实现代码，数据库迁移脚本，单元测试"
    },
    {
      "id": "subtask-3",
      "name": "编写 API 测试",
      "role": "tester",
      "dependencies": ["subtask-2"],
      "expected_output": "API 集成测试，性能测试，测试报告"
    }
  ]
}
"""


class TaskDecompositionResult(BaseModel):
    """Structured output from task decomposition."""

    task_id: str = Field(description="Unique task identifier")
    summary: str = Field(description="Brief summary of the task")
    subtasks: list[dict] = Field(
        default_factory=list,
        description="List of subtasks, each with id, name, role, dependencies, expected_output",
    )

    @classmethod
    def generate_task_id(cls) -> str:
        """Generate a unique task ID."""
        return f"task-{uuid.uuid4().hex[:12]}"


class TaskDecomposer:
    """Prompts and templates for task decomposition by supervisor agent."""

    # Available roles for reference
    AVAILABLE_ROLES = {
        "architect": "Software Architect - system architecture, tech stack, API design",
        "backend-developer": (
            "Backend Developer - API implementation, business logic, unit tests"
        ),
        "frontend-developer": (
            "Frontend Developer - UI components, user experience, "
            "responsive design"
        ),
        "fullstack-developer": (
            "Fullstack Developer - end-to-end development, deployment configuration"
        ),
        "tester": "Test Engineer - test strategy, test cases, automation",
    }

    @classmethod
    def build_system_prompt(cls) -> str:
        """Build the system prompt for the supervisor agent."""
        return f"""You are a Task Decomposition Specialist for a multi-agent team.

## Your Role
Break down complex user tasks into smaller, manageable subtasks
that can be executed by different specialized agents.

## Available Roles
{cls._format_roles()}

## Your Responsibilities
1. Analyze the user's task description
2. Break it down into logical subtasks
3. Assign each subtask to the most appropriate role
4. Define dependencies between subtasks (a subtask should depend on outputs it needs)
5. Provide clear expectations for each subtask's output

## Task Decomposition Guidelines
- Start with architectural/design tasks first if applicable
- Developer tasks should come after design tasks (depend on architecture)
- Testing tasks should come last (depend on implementation)
- Keep subtasks focused and achievable (one subtask should complete one cohesive piece of work)
- Include 3-6 subtasks for most tasks
- Avoid circular dependencies
- Each subtask should have a clear deliverable

## Output Format
You must respond with a valid JSON object containing:
- task_id: unique identifier (use format "task-<short-uuid>")
- summary: brief task summary (1-2 sentences)
- subtasks: array of subtask objects, each with:
  - id: unique subtask identifier (format "subtask-1", "subtask-2", etc.)
  - name: descriptive subtask name
  - role: one of: {', '.join(cls.AVAILABLE_ROLES.keys())}
  - dependencies: array of subtask IDs this task depends on (empty array if no dependencies)
  - expected_output: description of what should be produced

Think carefully about the task flow and dependencies before outputting."""

    @classmethod
    def build_user_prompt(cls, task_description: str) -> str:
        """Build the user prompt with task description."""
        return f"""## Task to Decompose

{task_description}

## Examples

{EXAMPLES}

Now decompose the task above and respond with a JSON object.
"""

    @classmethod
    def _format_roles(cls) -> str:
        """Format available roles for the prompt."""
        lines = []
        for role_id, description in cls.AVAILABLE_ROLES.items():
            lines.append(f"- **{role_id}**: {description}")
        return "\n".join(lines)

    @classmethod
    def get_examples(cls) -> str:
        """Get few-shot examples."""
        return EXAMPLES

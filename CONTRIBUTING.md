# Contributing to Agent Team Orchestrator

Thank you for your interest in contributing to ATO! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Git

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/spacesky-cell/agent-team-orchestrator.git
cd agent-team-orchestrator
```

### 2. Install Dependencies

```bash
# Create Python virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Install Python dependencies
pip install -e packages/core
pip install -r requirements-dev.txt  # if available

# Install Node.js dependencies
npm install
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your API key for testing
```

## Project Structure

```
ato/
├── packages/
│   ├── core/           # Python core (LangGraph orchestration)
│   │   └── src/
│   │       ├── orchestrator/    # LangGraph-based orchestrators
│   │       ├── models/          # LLM providers, roles, state
│   │       ├── tools/           # File and code operation tools
│   │       ├── memory/          # Team memory module
│   │       └── prompts/         # Task decomposition prompts
│   ├── mcp-server/     # TypeScript MCP Server
│   ├── cli/            # TypeScript CLI
│   └── shared/         # Shared TypeScript types
├── roles/              # Agent role definitions (YAML)
└── docs/               # Documentation
```

## Making Changes

### Python Code

1. **Format**: Use `black` for formatting
   ```bash
   black packages/core/src/
   ```

2. **Lint**: Use `ruff` for linting
   ```bash
   ruff check packages/core/src/
   ```

3. **Type Check**: Use `mypy` (optional)
   ```bash
   mypy packages/core/src/
   ```

### TypeScript Code

1. **Build**: Compile TypeScript
   ```bash
   npm run build
   ```

2. **Lint**: Run ESLint
   ```bash
   npm run lint
   ```

## Testing

### Python Tests

```bash
cd packages/core
pytest

# With coverage
pytest --cov=src
```

### TypeScript Tests

```bash
cd packages/cli
npm test

# or for MCP server
cd packages/mcp-server
npm test
```

## Adding New Features

### Adding a New Role

1. Create a new YAML file in `roles/` directory:

```yaml
# roles/my-role.yaml
id: my-role
name: My Custom Role
description: What this role does
expertise:
  - Skill 1
  - Skill 2
tools:
  - read_file
  - write_file
  - search_code
system_prompt: |
  You are a specialist in...
  
  {{context}}
  
  Please start your task.
deliverables:
  - format: markdown
    description: Expected output
```

2. Test the role:
```bash
node packages/cli/dist/index.js roles
```

### Adding a New Tool

1. Create a new tool in `packages/core/src/tools/`:

```python
# packages/core/src/tools/my_tool.py
from .base import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            }
        },
        "required": ["param1"]
    }
    
    async def execute(self, param1: str) -> str:
        # Implementation
        return "Result"
```

2. Register the tool in `packages/core/src/tools/__init__.py`:

```python
from .my_tool import MyTool

def get_all_tools() -> list[BaseTool]:
    return get_file_tools() + get_code_tools() + [MyTool()]
```

### Adding a New MCP Tool

1. Add tool definition in `packages/mcp-server/src/index.ts`:

```typescript
{
  name: "my_new_tool",
  description: "Tool description",
  inputSchema: {
    type: "object",
    properties: {
      param1: {
        type: "string",
        description: "Parameter description"
      }
    },
    required: ["param1"]
  }
}
```

2. Add handler in the `switch` statement:

```typescript
case "my_new_tool": {
  const { param1 } = args as { param1: string };
  // Implementation
  return {
    content: [{ type: "text", text: "Result" }]
  };
}
```

## Commit Guidelines

### Commit Messages

Follow conventional commits format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(orchestrator): add checkpoint recovery support
fix(cli): handle paths with spaces on Windows
docs(readme): add Chinese documentation
```

## Pull Request Process

1. **Create a Branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make Changes and Commit**
   ```bash
   git add .
   git commit -m "feat: add my feature"
   ```

3. **Push to Your Fork**
   ```bash
   git push origin feature/my-feature
   ```

4. **Create Pull Request**
   - Go to GitHub and create a PR
   - Fill in the PR template
   - Link any related issues

5. **Code Review**
   - Address review comments
   - Keep the PR up to date with main

## Release Process

1. Update version in `package.json` and `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create a git tag
4. Build and publish packages

## Getting Help

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

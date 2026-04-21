# ATO Core

Core Python package for Agent Team Orchestrator.

## Installation

```bash
pip install -e .
```

## Usage

```python
from ato_core.orchestrator import SimpleOrchestrator

# Initialize orchestrator
orchestrator = SimpleOrchestrator()

# Decompose a task
decomposition = orchestrator.decompose_task("开发一个简单的用户登录功能")

# Execute the task
result = orchestrator.execute_task(decomposition)

# Save artifacts
orchestrator.save_artifacts(result.artifacts, "./ato-output")
```

## Environment Variables

- `LLM_PROVIDER`: Provider to use (anthropic, openai, ollama). Default: anthropic
- `LLM_MODEL`: Model name. Default: claude-sonnet-4-20250514
- `ANTHROPIC_API_KEY`: Anthropic API key (if using LLM_PROVIDER=anthropic)
- `OPENAI_API_KEY`: OpenAI API key (if using LLM_PROVIDER=openai)
- `OLLAMA_BASE_URL`: Ollama base URL (if using LLM_PROVIDER=ollama)

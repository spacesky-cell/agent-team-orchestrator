"""
Quick start example for Agent Team Orchestrator.

This script demonstrates basic usage of the orchestrator.
"""

import sys

from dotenv import load_dotenv

# Load .env file
load_dotenv()

from src.orchestrator.simple_orchestrator import SimpleOrchestrator


def main():
    """Run a simple example."""
    print("=" * 60)
    print("Agent Team Orchestrator - Quick Start Example")
    print("=" * 60)
    print()

    # Example task
    task_description = "开发一个简单的待办事项管理 API，支持增删改查功能"

    print(f"Task: {task_description}")
    print()
    print("Initializing orchestrator...")
    print()

    try:
        orchestrator = SimpleOrchestrator()

        # Step 1: Decompose task
        decomposition = orchestrator.decompose_task(task_description)

        # Step 2: Execute task
        result = orchestrator.execute_task(decomposition)

        # Step 3: Save artifacts
        output_dir = "./ato-output"
        orchestrator.save_artifacts(result.artifacts, output_dir)

        print()
        print("=" * 60)
        print("Example completed!")
        print(f"Artifacts saved to: {output_dir}")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        print("\nPlease check:")
        print("1. ANTHROPIC_API_KEY is set in your environment")
        print("2. All dependencies are installed (langchain, langgraph, etc.)")
        print("3. You're running Python 3.10+")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

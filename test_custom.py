"""
自定义测试脚本 - 测试 Agent Team Orchestrator
"""

from dotenv import load_dotenv
load_dotenv()  # 加载 .env 配置

from src.orchestrator.simple_orchestrator import SimpleOrchestrator


def main():
    # 初始化编排器
    orchestrator = SimpleOrchestrator()

    # 定义你的任务
    task = "帮我写一个用户登录功能，包括注册、登录、登出接口"

    print(f"任务: {task}\n")

    # 步骤1: 分解任务
    decomposition = orchestrator.decompose_task(task)

    # 步骤2: 执行任务
    result = orchestrator.execute_task(decomposition)

    # 步骤3: 保存产物
    if result.status == "completed":
        orchestrator.save_artifacts(result.artifacts, "./my-output")
        print(f"\n✓ 完成！产物已保存到 ./my-output/")
    else:
        print(f"\n✗ 失败: {result.error}")


if __name__ == "__main__":
    main()

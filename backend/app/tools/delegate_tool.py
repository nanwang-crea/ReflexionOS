"""
DelegateTool — 主 Agent 委托子任务给 SubAgentRunner 的工具。

当主 Agent 需要将独立子任务委托给子 agent 时调用此工具。
子 agent 在内存中执行完整的 Agent Loop 后返回结果。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# SubAgentRunner 的工厂函数类型签名
# 接收 task/input_data/expected_output，返回 SubAgentRunner 实例
RunnerFactory = Callable[..., Any]


class DelegateTool(BaseTool):
    """
    委托子任务给独立子 Agent 执行。

    子 Agent 拥有独立的工具集和执行上下文，与主 Agent 隔离。
    子 Agent 完成后返回结果，主 Agent 继续执行。
    """

    TOOL_NAME = "delegate"

    # 子 agent 工具集排除的工具（防递归）
    EXCLUDED_TOOLS: frozenset[str] = frozenset({"delegate"})

    def __init__(self, runner_factory: RunnerFactory):
        super().__init__()
        self._runner_factory = runner_factory

    @property
    def name(self) -> str:
        return self.TOOL_NAME

    @property
    def description(self) -> str:
        return (
            "委托一个独立子 Agent 执行子任务。"
            "子 Agent 拥有独立的工具集和执行上下文。"
            "适用于：可独立完成的原子任务、需要不同执行策略的子任务、"
            "可并行执行的独立任务。"
            "不适用于：需要与当前任务共享上下文的步骤、需要用户交互的步骤。"
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "委托给子 Agent 的任务描述，应清晰、具体、可独立完成",
                    },
                    "input": {
                        "type": "object",
                        "description": "附加输入数据（可选），子 Agent 可在任务描述之外获取的额外信息",
                    },
                    "expected_output": {
                        "type": "string",
                        "description": "预期输出的描述（可选），帮助子 Agent 理解目标格式",
                    },
                },
                "required": ["task"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行 delegate 工具：创建 SubAgentRunner 并运行"""
        task = args.get("task")
        if not task or not isinstance(task, str):
            return ToolResult(
                success=False,
                error="参数 'task' 是必需的，且必须是非空字符串",
            )

        input_data = args.get("input")
        expected_output = args.get("expected_output")

        logger.info("DelegateTool 执行: task=%.100s", task)

        try:
            # 通过工厂函数创建 SubAgentRunner
            runner = self._runner_factory(
                task=task,
                input_data=input_data,
                expected_output=expected_output,
            )

            # 执行 sub-agent
            result = await runner.run()

            if result.status == "completed":
                # 构建输出，包含 sub-agent 的结果和执行统计
                output_parts = [result.output]
                output_parts.append(
                    f"\n\n---\n子任务完成: {result.steps_taken} 步执行"
                )
                return ToolResult(
                    success=True,
                    output="\n".join(output_parts),
                )
            elif result.status == "cancelled":
                return ToolResult(
                    success=False,
                    output=result.output,
                    error="子任务被取消",
                )
            else:
                return ToolResult(
                    success=False,
                    output=result.output,
                    error=f"子任务执行失败: {result.output}",
                )

        except TimeoutError:
            logger.warning("DelegateTool 超时: task=%.100s", task)
            return ToolResult(
                success=False,
                error="子任务执行超时",
            )
        except Exception as e:
            logger.error("DelegateTool 异常: %s", e, exc_info=True)
            return ToolResult(
                success=False,
                error=f"子任务执行异常: {e}",
            )

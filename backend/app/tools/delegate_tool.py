"""
DelegateTool — 主 Agent 委托子任务给 SubAgentRunner 的工具。

当主 Agent 需要将独立子任务委托给子 agent 时调用此工具。
子 agent 在内存中执行完整的 Agent Loop 后返回结果。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from app.tools.base import BaseTool, ToolResult

# 事件回调类型签名（与 RapidExecutionLoop/SubAgentRunner 一致）
EventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

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

    def __init__(
        self,
        runner_factory: RunnerFactory,
        event_callback: EventCallback | None = None,
    ):
        super().__init__()
        self._runner_factory = runner_factory
        # 外部注入的事件回调，用于将子 agent 执行事件实时推送到前端
        self._event_callback: EventCallback | None = event_callback

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
        # 从 ToolCallExecutor 设置的上下文变量中获取当前 tool call ID
        # 用于让前端将子 agent 事件关联到正确的 DelegateToolCall 组件
        from app.execution.tool_call_executor import _current_tool_call_id

        delegate_call_id: str = _current_tool_call_id.get("")

        logger.info("DelegateTool 执行: task=%.100s", task)

        try:
            # 通过工厂函数创建 SubAgentRunner
            runner = self._runner_factory(
                task=task,
                input_data=input_data,
                expected_output=expected_output,
            )

            # 如果有外部事件回调，注入到 runner 并用 sub_agent: 前缀包装事件
            # 每个事件都携带 delegate_call_id，让前端能关联到正确的 DelegateToolCall 组件
            if self._event_callback:
                parent_cb = self._event_callback
                call_id = delegate_call_id

                async def _sub_agent_event_callback(
                    event_type: str, data: dict[str, Any]
                ) -> None:
                    # 注入 delegate_call_id 和 task 描述，前端用于关联和展示
                    enriched = {
                        **data,
                        "delegate_call_id": call_id,
                        "task": task[:200],
                    }
                    # 添加 sub_agent: 前缀，让前端区分主/子 agent 事件
                    await parent_cb(f"sub_agent:{event_type}", enriched)

                runner._event_callback = _sub_agent_event_callback

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

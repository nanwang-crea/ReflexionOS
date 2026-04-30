import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from app.execution.context_manager import LoopContext
from app.execution.models import LoopStep, StepStatus
from app.llm.base import LLMToolCall
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolCallExecutor:
    """Execute model tool calls and project the result back into loop context."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        emit: Callable[[str, dict], Awaitable[None]],
    ):
        self.tool_registry = tool_registry
        self.emit = emit

    async def execute(
        self,
        tool_call: LLMToolCall,
        context: LoopContext,
        step_number: int,
    ) -> LoopStep:
        from app.tools.plan_tool import PlanTool

        step = LoopStep(
            id=f"step-{uuid.uuid4().hex[:8]}",
            step_number=step_number,
            tool=tool_call.name,
            tool_call_id=tool_call.id,
            args=tool_call.arguments,
            status=StepStatus.RUNNING,
        )

        start_time = time.time()

        await self.emit(
            "tool:start",
            {
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "tool_call_id": tool_call.id,
                "step_number": step_number,
            },
        )

        try:
            tool = self.tool_registry.get(tool_call.name)
            if not tool:
                raise ValueError(f"工具不存在: {tool_call.name}")

            result = await tool.execute(tool_call.arguments)

            if result.approval_required:
                approval = result.approval
                step.status = StepStatus.WAITING_FOR_APPROVAL
                step.approval_id = approval.approval_id if approval else None
                step.output = approval.summary if approval else result.output
                step.duration = time.time() - start_time

                approval_payload = approval.model_dump() if approval else None
                await self.emit(
                    "approval:required",
                    {
                        "tool_name": tool_call.name,
                        "arguments": tool_call.arguments,
                        "tool_call_id": tool_call.id,
                        "approval_id": approval.approval_id if approval else None,
                        "step_number": step_number,
                        "approval": approval_payload,
                    },
                )

                logger.info("工具 %s 等待审批", tool_call.name)
                return step

            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time

            tool_output = result.output or result.error or ""
            context.update_history(tool_call, tool_output)
            context.add_message(
                "tool",
                content=tool_output,
                tool_call_id=tool_call.id,
            )

            await self.emit(
                "tool:result",
                {
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.id,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "duration": step.duration,
                },
            )

            if isinstance(tool, PlanTool) and tool.get_plan() is not None:
                context.plan = tool.get_plan()
                await self.emit("plan:updated", context.plan.to_dict())

            logger.info(
                "工具 %s 执行%s",
                tool_call.name,
                "成功" if result.success else "失败",
            )

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration = time.time() - start_time
            logger.error("工具执行异常: %s", e)

            context.update_history(tool_call, str(e))
            context.add_message(
                "tool",
                content=str(e),
                tool_call_id=tool_call.id,
            )

            await self.emit(
                "tool:error",
                {
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.id,
                    "error": str(e),
                },
            )

        return step

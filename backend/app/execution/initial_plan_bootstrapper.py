from collections.abc import Awaitable, Callable

from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.llm.base import LLMToolCall, UniversalLLMInterface


class InitialPlanBootstrapper:
    """Run the non-streamed initial planning pass before the main loop."""

    def __init__(
        self,
        *,
        llm: UniversalLLMInterface,
        tool_definitions: RuntimeToolDefinitions,
        message_builder: LoopMessageBuilder,
        emit: Callable[[str, dict], Awaitable[None]],
    ):
        self.llm = llm
        self.tool_definitions = tool_definitions
        self.message_builder = message_builder
        self.emit = emit

    async def bootstrap(self, context: LoopContext) -> None:
        plan_tool = self.tool_definitions.get_plan_tool()
        if plan_tool is None:
            return

        plan_tool.set_plan(None)
        if context.plan is not None:
            return

        tool_calls: list[LLMToolCall] = []
        tools = self.tool_definitions.for_initial_plan()
        messages = self.message_builder.build_initial_plan(context)

        async for chunk in self.llm.stream_complete(messages, tools):
            if chunk.type == "tool_calls":
                tool_calls = chunk.tool_calls
                break
            if chunk.type == "done":
                break
            if chunk.type == "error":
                raise RuntimeError(chunk.error or "LLM 初始计划判断失败")

        for tool_call in tool_calls:
            if tool_call.name != plan_tool.name:
                continue
            if tool_call.arguments.get("action") != "create":
                continue

            result = await plan_tool.execute(tool_call.arguments)
            if result.success and plan_tool.get_plan() is not None:
                context.plan = plan_tool.get_plan()
                await self.emit("plan:updated", context.plan.to_dict())
            elif result.error:
                context.add_message("system", f"初始计划创建失败: {result.error}")
            return

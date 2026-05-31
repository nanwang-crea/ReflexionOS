from collections.abc import Awaitable, Callable

from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.execution.plan_file_sync import PlanFileSync
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

        # Check for recovery plan file
        plan_file_sync = PlanFileSync()
        recovery_path = plan_file_sync.find_recovery_plan(context.project_path)
        if recovery_path is not None:
            recovered_plan = plan_file_sync.read(recovery_path)
            if recovered_plan is not None:
                context.plan = recovered_plan
                context.plan_file_path = recovery_path
                context.metadata["plan_update_required"] = False
                context.metadata["steps_since_last_plan_update"] = 0
                await self.emit("plan:updated", context.plan.to_dict())
                await self.emit("plan:recovered", {"path": recovery_path, "goal": recovered_plan.goal})
                return

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
                context.metadata["plan_update_required"] = False
                context.metadata["steps_since_last_plan_update"] = 0
                # Write plan file for persistence
                slug = context.task[:40].replace(" ", "-").lower()
                plan_file_sync = PlanFileSync()
                plan_path = plan_file_sync.write(context.plan, slug=slug, project_path=context.project_path)
                context.plan_file_path = plan_path
                await self.emit("plan:updated", context.plan.to_dict())
            elif result.error:
                context.add_message("system", f"初始计划创建失败: {result.error}")
            return

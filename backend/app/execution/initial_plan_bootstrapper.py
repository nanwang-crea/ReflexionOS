import logging
from collections.abc import Awaitable, Callable

from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.plan_file_sync import PlanFileSync
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.llm.base import LLMMessage, LLMToolCall, MessageRole, UniversalLLMInterface

logger = logging.getLogger(__name__)

_PLAN_RELEVANCE_PROMPT = """\
Determine whether the new task is related to the existing plan's goal.
Answer ONLY "yes" or "no".

Existing plan goal: {goal}
Completed steps: {completed}/{total}
Current step: {current_step}

New task: {task}

Is the new task a continuation or subtask of the existing plan goal?\
"""


class InitialPlanBootstrapper:
    """Run the non-streamed initial planning pass before the main loop."""

    PLAN_RECOVERY_MAX_AGE_HOURS = 24

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

    async def _check_plan_relevance(self, context: LoopContext, plan_goal: str, plan) -> bool:
        """Ask LLM whether the new task is related to the recovered plan's goal."""
        completed = sum(1 for s in plan.steps if s.status == "completed")
        total = len(plan.steps)
        current_step_desc = plan.current_step.content if plan.current_step else "N/A"
        prompt = _PLAN_RELEVANCE_PROMPT.format(
            goal=plan_goal,
            completed=completed,
            total=total,
            current_step=current_step_desc,
            task=context.task,
        )
        messages = [LLMMessage(role=MessageRole.USER, content=prompt)]
        try:
            response = await self.llm.complete(messages, tools=[])
            answer = (response.content or "").strip().lower()
            if answer.startswith("yes"):
                return True
            if answer.startswith("no"):
                return False
            return "yes" in answer
        except Exception:
            logger.warning("Plan relevance check failed, defaulting to not relevant")
            return False

    async def bootstrap(self, context: LoopContext) -> None:
        plan_tool = self.tool_definitions.get_plan_tool()
        if plan_tool is None:
            return

        plan_tool.set_plan(None)

        # Check for recovery plan file
        plan_file_sync = PlanFileSync()
        recovery_path = plan_file_sync.find_recovery_plan(
            context.project_path,
            max_age_hours=self.PLAN_RECOVERY_MAX_AGE_HOURS,
        )
        if recovery_path is not None:
            recovered_plan = plan_file_sync.read(recovery_path)
            if recovered_plan is not None:
                is_relevant = await self._check_plan_relevance(context, recovered_plan.goal, recovered_plan)
                if is_relevant:
                    context.plan = recovered_plan
                    plan_tool.set_plan(recovered_plan)
                    context.plan_file_path = recovery_path
                    await self.emit("plan:updated", context.plan.to_dict())
                    await self.emit("plan:recovered", {"path": recovery_path, "goal": recovered_plan.goal})
                    return
                else:
                    logger.info(
                        "Recovered plan (goal: %s) is not relevant to new task: %s — discarding",
                        recovered_plan.goal[:80],
                        context.task[:80],
                    )
                    plan_file_sync.delete(recovery_path, project_path=context.project_path)
                    await self.emit("plan:discarded", {"path": recovery_path, "goal": recovered_plan.goal})

        if context.plan is not None:
            return

        tools = self.tool_definitions.for_initial_plan()
        messages = self.message_builder.build_initial_plan(context)
        response = await self.llm.complete(messages, tools)
        tool_calls: list[LLMToolCall] = response.tool_calls

        for tool_call in tool_calls:
            if tool_call.name != plan_tool.name:
                continue

            result = await plan_tool.execute(tool_call.arguments)
            if result.success and plan_tool.get_plan() is not None:
                context.plan = plan_tool.get_plan()
                # Write plan file for persistence
                plan_file_sync = PlanFileSync()
                plan_path = plan_file_sync.write(context.plan, session_id=context.run_id, project_path=context.project_path)
                context.plan_file_path = plan_path
                await self.emit("plan:updated", context.plan.to_dict())
            elif result.error:
                context.add_message("system", f"初始计划创建失败: {result.error}")
            return

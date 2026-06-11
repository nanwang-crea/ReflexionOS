import logging
from collections.abc import Awaitable, Callable

from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.plan_file_sync import PlanFileSync
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.llm.base import LLMMessage, LLMToolCall, MessageRole, UniversalLLMInterface

logger = logging.getLogger(__name__)

_PLAN_RELEVANCE_PROMPT = """\
You are deciding whether to RESUME an existing plan or DISCARD it and create a new one.

Existing plan goal: {goal}

Full plan ({total} steps):
{steps_detail}

New user task: {task}

Question: Should the agent RESUME the existing plan (continue from where it left off)
to fulfill the new task? Or should it DISCARD the plan and create a fresh one?

Resume criteria (answer "yes" ONLY if ALL are true):
1. The new task is asking to CONTINUE the same work described in the plan goal
2. The remaining pending/blocked steps are directly relevant to completing the new task
3. Starting a fresh plan would be wasteful because the completed steps already cover
   what the new task needs

Answer "no" if:
- The new task is a DIFFERENT focus area, even if it's in the same project/domain
- The new task only overlaps partially with the plan goal
- The user wants to investigate or work on something specific, not continue the full plan

Answer ONLY "yes" or "no".\
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

    async def _check_plan_relevance(self, context: LoopContext, plan) -> bool:
        """Ask LLM whether the new task is related to the recovered plan."""
        steps_lines = []
        for i, s in enumerate(plan.steps, 1):
            line = f"  {i}. [{s.status}] {s.content}"
            if s.findings:
                line += f"\n     Findings: {s.findings}"
            steps_lines.append(line)
        steps_detail = "\n".join(steps_lines)

        prompt = _PLAN_RELEVANCE_PROMPT.format(
            goal=plan.goal,
            total=len(plan.steps),
            steps_detail=steps_detail,
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
        context.plan = None

        # Check for recovery plan file
        plan_file_sync = PlanFileSync()
        recovery_path = plan_file_sync.find_recovery_plan(
            context.project_path,
            session_id=context.session_id,
            max_age_hours=self.PLAN_RECOVERY_MAX_AGE_HOURS,
        )
        if recovery_path is not None:
            recovered_plan = plan_file_sync.read(recovery_path)
            if recovered_plan is not None:
                logger.info("Recovered plan: goal=%s", recovered_plan.goal[:80])
                is_relevant = await self._check_plan_relevance(context, recovered_plan)
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
                    context.plan = None

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
                plan_path = plan_file_sync.write(context.plan, session_id=context.session_id, project_path=context.project_path)
                context.plan_file_path = plan_path
                await self.emit("plan:updated", context.plan.to_dict())
            elif result.error:
                context.add_message("system", f"初始计划创建失败: {result.error}")
            return

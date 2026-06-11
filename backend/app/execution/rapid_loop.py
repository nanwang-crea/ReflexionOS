import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from app.config.settings import config_manager
from app.execution.approval_flow import ApprovalFlow
from app.execution.context_manager import LoopContext
from app.execution.initial_plan_bootstrapper import InitialPlanBootstrapper
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.models import (
    LoopPhase,
    LoopResult,
    LoopStatus,
    LoopStep,
    RuntimeState,
    StepStatus,
)
from app.execution.plan_file_sync import PlanFileSync
from app.execution.prompt_manager import PromptManager
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.execution.tool_call_executor import ToolCallExecutor
from app.llm.base import LLMResponse, LLMToolCall, UniversalLLMInterface
from app.llm.retry import LLMRetryExhaustedError
from app.llm.token_counter import count_messages_tokens
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class RapidExecutionLoop:
    """
    快速执行循环 - Agent 核心执行引擎

    状态机设计：
    PLANNING → TOOL_EXECUTION → PLANNING → ... → FINAL_SUMMARY → DONE
                    ↓
              ERROR_RECOVERY → PLANNING
    """

    # 重试配置
    MAX_TURN_RETRIES = 5  # 每轮最大重试
    MAX_SUMMARY_RETRIES = 5  # 总结最大重试
    MAX_ERROR_RETRIES = 5  # 错误恢复最大重试
    MAX_PREMATURE_STOP_RETRIES = 5  # 过早停止最大重试（assistant prefill + user nudge）
    MAX_CONTEXT_GROUPS = 10  # 最近上下文分组数，保证 tool_call 与 tool 输出成组保留
    MAX_EMPTY_RESPONSE_RETRIES = 5  # 空响应最大重试
    MAX_READ_ONLY_PASSES = 10  # 只读工具调用最大轮次
    MAX_STAGNANT_READ_ONLY_PASSES = 5  # 停滞的只读工具调用最大轮次
    DOOM_LOOP_THRESHOLD = 3  # 致命循环阈值

    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int | None = None,
        event_callback: Callable[[str, dict], Awaitable[None]] | None = None,
        context_window: int = 128000,
    ):
        self.llm = llm
        self._tool_registry = tool_registry
        self.max_steps = max_steps or config_manager.settings.execution.max_steps
        self.prompt_manager = PromptManager(model_name=self.llm.get_model_name())
        self.event_callback = event_callback
        self.context_window = context_window
        self._overflow_retry_count = 0
        self.tool_definitions = RuntimeToolDefinitions(self._tool_registry)
        self.message_builder = LoopMessageBuilder(
            prompt_manager=self.prompt_manager,
            max_context_groups=self.MAX_CONTEXT_GROUPS,
            tool_output_max_chars=config_manager.settings.execution.tool_output_max_chars,
            task_anchor_interval=8,
        )
        self.initial_plan_bootstrapper = InitialPlanBootstrapper(
            llm=self.llm,
            tool_definitions=self.tool_definitions,
            message_builder=self.message_builder,
            emit=self._emit,
        )
        self.tool_executor = ToolCallExecutor(
            tool_registry=self._tool_registry,
            emit=self._emit,
        )
        self.approval_flow = ApprovalFlow(emit=self._emit)
        self._runtime: RuntimeState | None = None
        self.plan_file_sync = PlanFileSync()

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    async def _emit(self, event_type: str, data: dict) -> None:
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error("事件回调失败: %s", e)
                raise

    def get_approval_resume_event(self) -> asyncio.Event:
        return self.approval_flow._resume_event

    def set_approval_result(self, result: dict | None) -> None:
        self.approval_flow.set_approval_result(result)

    # -- phase handlers ---------------------------------------------------

    async def _handle_planning(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """PLANNING 阶段：调用 LLM 决策，决定下一阶段。"""
        # Check for plan_exit confirmation
        if rt._plan_exit_confirmed:
            rt._plan_exit_confirmed = False
            await self._confirm_plan_exit(context, rt)

        self._overflow_retry_count = 0
        rt.response = await self._call_llm(context)

        logger.info(
            "Planning LLM response: has_tool_calls=%s, has_content=%s, content_preview=%s, "
            "has_executed_tools=%s, plan_is_none=%s",
            rt.response.has_tool_calls,
            rt.response.has_content,
            (rt.response.content or "")[:80],
            rt.has_executed_tools,
            context.plan is None,
        )

        # Completion firewall: check BEFORE routing to TOOL_EXECUTION.
        # If agent has been using tools and plan is unfinished, nudge to continue
        # even if the LLM returned tool_calls alongside content.
        if rt.has_executed_tools and not rt.response.has_tool_calls:
            plan_has_unfinished = (
                context.plan is not None
                and not context.plan.is_complete
            )
            blocked_steps = [s for s in context.plan.steps if s.status == "blocked"] if context.plan else []
            current_step = context.plan.current_step if context.plan else None
            allow_stop_for_clarification = (
                context.plan is not None
                and current_step is None
                and len(blocked_steps) > 0
            )
            should_nudge = False
            if plan_has_unfinished and not allow_stop_for_clarification:
                should_nudge = rt.premature_stop_count < self.MAX_PREMATURE_STOP_RETRIES
            elif not allow_stop_for_clarification:
                should_nudge = rt.premature_stop_count < 1

            logger.info(
                "Anti-stop check: should_nudge=%s, plan_has_unfinished=%s, premature_stop_count=%s",
                should_nudge, plan_has_unfinished, rt.premature_stop_count,
            )

            if should_nudge:
                rt.premature_stop_count += 1
                if plan_has_unfinished:
                    pending_count = sum(1 for s in context.plan.steps if s.status == "pending")
                    nudge = (
                        "The plan is NOT complete yet. "
                        f"There are still {pending_count} pending step(s). "
                        "You MUST continue executing the plan with your tools. Do NOT stop until all steps are completed."
                    )
                else:
                    nudge = (
                        "Check your work: is the original task fully complete with verification? "
                        "If not, continue using tools. Do NOT stop to report partial progress."
                    )
                prefill = "I'll continue working on the task using my tools."
                context.add_message("user", nudge)
                context.metadata["_prefill_assistant"] = prefill
                return LoopPhase.PLANNING

        if rt.response.has_tool_calls:
            rt.consecutive_failures = 0
            return LoopPhase.TOOL_EXECUTION

        # 没有工具调用
        if rt.has_executed_tools:
            if rt.response.has_content:
                content = rt.response.content or ""

                result.status = LoopStatus.COMPLETED
                result.result = rt.response.content
                return LoopPhase.DONE
            else:
                # 没有最终回答时，再进入兜底总结阶段
                return LoopPhase.FINAL_SUMMARY
        else:
            # 没执行过工具，直接完成
            if rt.response.has_content:
                result.status = LoopStatus.COMPLETED
                result.result = rt.response.content
                return LoopPhase.DONE
            else:
                if rt.response.finish_reason == "length":
                    result.status = LoopStatus.COMPLETED
                    result.result = "模型输出被截断（max_tokens 不足），请尝试增大 max_tokens 配置"
                    return LoopPhase.DONE
                if rt.response.finish_reason == "stop":
                    result.status = LoopStatus.COMPLETED
                    result.result = "模型未返回有效内容（可能触发了内容审核），请调整输入或更换模型"
                    return LoopPhase.DONE
                rt.consecutive_failures += 1
                if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                    raise RuntimeError(
                        f"模型连续 {self.MAX_ERROR_RETRIES} 次返回空响应（finish_reason={rt.response.finish_reason}），"
                        "请检查模型配置或更换模型"
                    )
                return LoopPhase.PLANNING

    def _record_tool_signature(self, context: LoopContext, tool_call: LLMToolCall) -> None:
        sig = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True)}"
        recent_sigs: list[str] = context.metadata.setdefault("_recent_tool_signatures", [])
        recent_sigs.append(sig)
        if len(recent_sigs) > self.DOOM_LOOP_THRESHOLD * 2:
            recent_sigs[:] = recent_sigs[-self.DOOM_LOOP_THRESHOLD * 2:]

    def _is_doom_loop(self, context: LoopContext) -> bool:
        recent_sigs: list[str] = context.metadata.get("_recent_tool_signatures", [])
        if len(recent_sigs) >= self.DOOM_LOOP_THRESHOLD:
            tail = recent_sigs[-self.DOOM_LOOP_THRESHOLD:]
            if len(set(tail)) == 1:
                return True
        return False

    async def _handle_tool_execution(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """TOOL_EXECUTION 阶段：执行工具调用，只读工具并行，写操作串行。"""
        error_recovery_needed = False

        read_only_calls = []
        write_calls = []

        # Handle plan_exit — emit event, wait for user confirmation
        for tool_call in list(rt.response.tool_calls):
            if tool_call.name == "plan_exit":
                rt.step_num += 1
                step = await self.tool_executor.execute(tool_call, context, rt.step_num)
                result.steps.append(step)
                context.add_step(step)
                if step.status == StepStatus.SUCCESS:
                    await self._emit("plan:exit_requested", {
                        "run_id": result.id,
                        "summary": step.args.get("summary", ""),
                    })
                    context.metadata["plan_exit_requested"] = True
                    context.metadata["plan_exit_summary"] = step.args.get("summary", "")
                return LoopPhase.PLANNING

        for tool_call in rt.response.tool_calls:
            if self.tool_executor._is_read_only_call(tool_call):
                read_only_calls.append(tool_call)
            else:
                write_calls.append(tool_call)

        read_only_calls = self.tool_executor.prepare_read_only_batch(read_only_calls)
        batch_produced_new_facts = False
        if read_only_calls:
            rt.read_only_passes_used += 1
            read_only_signatures = {
                self.tool_executor._read_only_signature(tool_call)
                for tool_call in read_only_calls
            }
            seen_signatures = context.metadata.setdefault("seen_read_only_signatures", [])
            new_signatures = read_only_signatures - set(seen_signatures)
            if new_signatures:
                batch_produced_new_facts = True
                rt.stagnant_read_only_passes = 0
                seen_signatures.extend(new_signatures)
            else:
                rt.stagnant_read_only_passes += 1

        # Execute read-only tools in parallel
        if read_only_calls:
            start_step = rt.step_num + 1
            parallel_steps = await asyncio.gather(
                *[
                    self.tool_executor.execute(tc, context, start_step + i)
                    for i, tc in enumerate(read_only_calls)
                ]
            )
            rt.step_num = start_step + len(read_only_calls) - 1
            for step in parallel_steps:
                result.steps.append(step)
                context.add_step(step)

                if step.status == StepStatus.FAILED:
                    rt.consecutive_failures += 1
                    await self._emit(
                        "tool:error",
                        {
                            "tool_name": step.tool,
                            "step_number": step.step_number,
                            "tool_call_id": step.tool_call_id,
                            "success": False,
                            "output": step.output,
                            "error": step.error,
                            "duration": step.duration,
                            "arguments": step.args,
                        },
                    )
                    if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                        error_recovery_needed = True
                else:
                    rt.consecutive_failures = 0
                    rt.has_executed_tools = True
                    rt.premature_stop_count = 0

            for step in parallel_steps:
                if step.status == StepStatus.WAITING_FOR_APPROVAL:
                    return await self._handle_approval(step, context, result, rt)

        if (
            read_only_calls
            and not write_calls
            and (
                (
                    not batch_produced_new_facts
                    and rt.read_only_passes_used > 1
                )
                or rt.read_only_passes_used >= self.MAX_READ_ONLY_PASSES
            )
        ):
            context.metadata["investigation_budget_exhausted"] = True
            return LoopPhase.FINAL_SUMMARY

        if read_only_calls:
            for tool_call in read_only_calls:
                self._record_tool_signature(context, tool_call)
            for _step_rc, tool_call in zip(
                parallel_steps, read_only_calls, strict=True
            ):
                if self._is_doom_loop(context):
                    doom_prompt = (
                        f"[Doom Loop Detected] You have called "
                        f"{tool_call.name} with the same arguments "
                        f"{self.DOOM_LOOP_THRESHOLD} times in a row "
                        f"with no new information.\n"
                        f"Arguments: {json.dumps(tool_call.arguments)}\n\n"
                        f"You MUST change your approach. Try different "
                        f"search terms, different files, or move on "
                        f"to the next step."
                    )
                    context.add_message("user", doom_prompt)
                    rt.consecutive_failures = 0
                    context.metadata.setdefault("_recent_tool_signatures", []).clear()
                    return LoopPhase.PLANNING
        for tool_call in write_calls:
            self._record_tool_signature(context, tool_call)
            rt.step_num += 1
            step = await self.tool_executor.execute(tool_call, context, rt.step_num)
            result.steps.append(step)
            context.add_step(step)

            if step.status == StepStatus.WAITING_FOR_APPROVAL:
                return await self._handle_approval(step, context, result, rt)

            if step.status == StepStatus.FAILED:
                rt.consecutive_failures += 1
                await self._emit(
                    "tool:error",
                    {
                        "tool_name": tool_call.name,
                        "step_number": step.step_number,
                        "tool_call_id": step.tool_call_id,
                        "success": False,
                        "output": step.output,
                        "error": step.error,
                        "duration": step.duration,
                        "arguments": step.args,
                    },
                )
                if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                    error_recovery_needed = True
            else:
                rt.consecutive_failures = 0
                rt.has_executed_tools = True
                rt.premature_stop_count = 0
                rt.stagnant_read_only_passes = 0

            if self._is_doom_loop(context):
                doom_prompt = (
                    f"[Doom Loop Detected] You have called "
                    f"{tool_call.name} with the same arguments "
                    f"{self.DOOM_LOOP_THRESHOLD} times in a row, "
                    f"and it keeps failing or producing no progress.\n"
                    f"Arguments: {json.dumps(tool_call.arguments)}\n"
                    f"Last error: {step.error or 'no error (success but no progress)'}\n\n"
                    f"You MUST change your approach:\n"
                    f"- If the tool keeps failing, try a different "
                    f"tool or different arguments.\n"
                    f"- If you are stuck, mark the step as blocked in the plan tool.\n"
                    f"- Do NOT retry with the same parameters again."
                )
                context.add_message("user", doom_prompt)
                rt.consecutive_failures = 0
                context.metadata.setdefault("_recent_tool_signatures", []).clear()
                return LoopPhase.PLANNING

        if error_recovery_needed:
            return LoopPhase.ERROR_RECOVERY

        # Sync plan file after plan tool changes
        if context.plan and context.plan_file_path:
            self.plan_file_sync.sync(context.plan, context.plan_file_path, project_path=context.project_path)

        # Pruning: lightweight context recovery after each tool execution round
        settings = config_manager.settings.execution
        context.prune_tool_outputs(
            protect_recent_groups=settings.prune_protect_groups,
            minimum_recovery_tokens=settings.prune_minimum_recovery_tokens,
        )

        return LoopPhase.PLANNING

    async def _handle_approval(
        self,
        step: LoopStep,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """审批子处理器：等待审批结果，决定后续状态。"""
        result.status = LoopStatus.WAITING_FOR_APPROVAL
        result.result = step.output

        await self._emit(
            "run:waiting_for_approval",
            {
                "run_id": result.id,
                "approval_id": step.approval_id,
                "step_number": step.step_number,
                "tool_name": step.tool,
            },
        )

        approval = await self.approval_flow.wait_for_approval(step, result.id)

        if approval.approved:
            result.status = LoopStatus.RESUMING
            tool_output = approval.output or approval.error or ""
            context.add_message(
                "tool",
                content=tool_output,
                tool_call_id=step.tool_call_id,
            )
            context.update_history(step, tool_output)
            step.status = StepStatus.SUCCESS if approval.success else StepStatus.FAILED
            step.output = approval.output
            step.error = approval.error
            step.duration = 0.0

            # Emit tool:result so the runtime adapter closes the
            # waiting-for-approval tool_trace (updates payload and
            # streamState from streaming → completed/failed).
            await self._emit(
                "tool:result",
                {
                    "tool_name": step.tool,
                    "tool_call_id": step.tool_call_id,
                    "step_number": step.step_number,
                    "success": approval.success,
                    "output": approval.output,
                    "error": approval.error,
                    "duration": 0.0,
                },
            )

            await self._emit(
                "run:resuming",
                {
                    "run_id": result.id,
                    "approval_id": step.approval_id,
                    "execution_success": approval.success,
                },
            )

            rt.has_executed_tools = True
            return LoopPhase.PLANNING
        else:
            step.status = StepStatus.FAILED
            step.error = "审批被拒绝"

            # Emit tool:error so the runtime adapter closes the
            # waiting-for-approval tool_trace (streamState → failed).
            await self._emit(
                "tool:error",
                {
                    "tool_name": step.tool,
                    "tool_call_id": step.tool_call_id,
                    "step_number": step.step_number,
                    "error": "审批被拒绝",
                    "duration": 0.0,
                    "arguments": step.args,
                },
            )

            # Emit run:cancelled so the runtime adapter and
            # projection transition the run to CANCELLED and
            # close any open messages.
            await self._emit(
                "run:cancelled",
                {
                    "status": LoopStatus.CANCELLED.value,
                    "result": "审批被拒绝",
                    "total_steps": len(result.steps),
                },
            )

            result.status = LoopStatus.CANCELLED
            result.result = "审批被拒绝"
            return LoopPhase.DONE

    async def _handle_error_recovery(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """ERROR_RECOVERY 阶段：将错误信息注入上下文，准备重试。"""
        last_step = result.steps[-1] if result.steps else None

        if not last_step:
            return LoopPhase.FINAL_SUMMARY

        original_args = last_step.args if last_step.args else None
        available_actions = None
        if last_step.tool:
            tool_instance = self._tool_registry.get(last_step.tool)
            if tool_instance:
                schema = tool_instance.get_schema()
                action_prop = schema.get("parameters", {}).get("properties", {}).get("action", {})
                if "enum" in action_prop:
                    available_actions = action_prop["enum"]

        error_prompt = self.prompt_manager.get_error_prompt(
            error=last_step.error or "工具执行失败（无错误详情）",
            tool=last_step.tool,
            original_args=original_args,
            available_actions=available_actions,
        )

        # 添加错误信息到上下文
        context.add_message("user", error_prompt)

        # 重置连续失败计数
        rt.consecutive_failures = 0
        rt.turn_retries += 1

        if rt.turn_retries > self.MAX_TURN_RETRIES:
            # 超过重试次数，强制总结
            return LoopPhase.FINAL_SUMMARY

        return LoopPhase.PLANNING

    async def _confirm_plan_exit(self, context: LoopContext, rt: RuntimeState) -> None:
        """Handle user confirmation of plan_exit — switch to build mode."""
        context.agent_mode = "build"
        context.metadata.pop("plan_exit_requested", None)
        summary = context.metadata.pop("plan_exit_summary", "")
        injection = f"计划已批准，开始执行。{summary}"
        if context.plan_file_path:
            injection += f"\n计划文件: {context.plan_file_path}"
        context.add_message("user", injection)

    async def confirm_plan_exit_from_external(self, run_id: str) -> None:
        """Called externally when user confirms plan_exit via WebSocket."""
        if self._runtime is not None:
            self._runtime._plan_exit_confirmed = True

    async def _handle_final_summary(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """FINAL_SUMMARY 阶段：获取最终总结。"""
        summary = await self._get_final_summary(context)
        result.result = summary
        result.status = LoopStatus.COMPLETED
        return LoopPhase.DONE

    # -- main loop --------------------------------------------------------

    async def run(
        self,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        created_at: datetime | None = None,
        seed_messages: list[dict[str, str]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
        agent_mode: str = "build",
    ) -> LoopResult:
        """
        执行任务

        Args:
            task: 任务描述
            project_path: 项目路径

        Returns:
            LoopResult: 执行结果
        """
        start_time = time.time()

        loop_result = LoopResult(
            id=run_id or f"run-{uuid.uuid4().hex[:8]}",
            task=task,
            status=LoopStatus.RUNNING,
            created_at=created_at or datetime.now(),
        )

        context = LoopContext.from_run_input(
            task=task,
            project_path=project_path,
            run_id=loop_result.id,
            agent_mode=agent_mode,
            seed_messages=seed_messages,
            supplemental_context=supplemental_context,
            system_sections=system_sections,
        )

        rt = RuntimeState()
        self._runtime = rt

        # 发送开始事件
        await self._emit("run:start", {"run_id": loop_result.id, "task": task})

        logger.info("开始执行任务: %s", task)

        try:
            if context.agent_mode != "plan":
                await self.initial_plan_bootstrapper.bootstrap(context)

            handlers: dict[LoopPhase, Callable] = {
                LoopPhase.PLANNING: self._handle_planning,
                LoopPhase.TOOL_EXECUTION: self._handle_tool_execution,
                LoopPhase.ERROR_RECOVERY: self._handle_error_recovery,
                LoopPhase.FINAL_SUMMARY: self._handle_final_summary,
            }

            while rt.phase != LoopPhase.DONE and rt.step_num < self.max_steps:
                handler = handlers[rt.phase]
                rt.phase = await handler(context, loop_result, rt)

            # 超过最大步数
            if rt.step_num >= self.max_steps and loop_result.status != LoopStatus.WAITING_FOR_APPROVAL:
                loop_result.status = LoopStatus.COMPLETED
                loop_result.result = loop_result.result or "执行完成（达到最大步数）"
                logger.warning("执行达到最大步数")

        except asyncio.CancelledError:
            loop_result.status = LoopStatus.CANCELLED
            loop_result.result = loop_result.result or "执行已取消"
            logger.info("执行已取消: %s", loop_result.id)

            await self._emit(
                "run:cancelled",
                {
                    "status": loop_result.status.value,
                    "result": loop_result.result,
                    "total_steps": len(loop_result.steps),
                },
            )

        except LLMRetryExhaustedError as e:
            loop_result.status = LoopStatus.CANCELLED
            loop_result.result = "执行已取消：LLM 重试次数已达上限"
            logger.warning("LLM 重试次数已达上限，取消执行: %s", e)

            await self._emit(
                "run:cancelled",
                {
                    "status": loop_result.status.value,
                    "result": loop_result.result,
                    "total_steps": len(loop_result.steps),
                    "reason": "llm_retry_exhausted",
                    "error": str(e.last_exception),
                },
            )

        except Exception as e:
            import traceback

            loop_result.status = LoopStatus.FAILED
            loop_result.result = f"执行异常: {str(e)}"
            logger.error("执行异常: %s\n%s", e, traceback.format_exc())

            await self._emit("run:error", {"error": str(e)})

        finally:
            if context is not None:
                loop_result.compacted_summary = context.compacted_summary

                if context.plan is not None:
                    if context.plan_file_path:
                        self.plan_file_sync.sync(context.plan, context.plan_file_path, project_path=context.project_path)
                    await self._emit("plan:updated", context.plan.to_dict())

            self._runtime = None
            loop_result.total_duration = time.time() - start_time
            loop_result.completed_at = datetime.now()

            # 发送完成事件
            if loop_result.status not in {
                LoopStatus.CANCELLED,
                LoopStatus.WAITING_FOR_APPROVAL,
            }:
                await self._emit(
                    "run:complete",
                    {
                        "status": loop_result.status.value,
                        "result": loop_result.result,
                        "total_steps": len(loop_result.steps),
                        "duration": loop_result.total_duration,
                    },
                )

        return loop_result

    # -- helpers ----------------------------------------------------------

    async def _call_llm(self, context: LoopContext) -> LLMResponse:
        """
        调用 LLM（使用原生工具调用），特定条件下重试空响应

        仅在 finish_reason=length 或流式错误时重试（这些是临时问题）。
        finish_reason=stop 但内容为空时不再重试（国产模型常见的内容审核/拒绝，
        重试只会浪费 token 和产生幽灵消息）。

        Args:
            context: 执行上下文

        Returns:
            LLMResponse: LLM 响应
        """
        await self._compact_context(context)

        for attempt in range(self.MAX_EMPTY_RESPONSE_RETRIES):
            tools = (
                self.tool_definitions.for_plan_mode()
                if context.agent_mode == "plan"
                else self.tool_definitions.for_context(context)
            )
            messages = self.message_builder.build(context)
            call_started_at = time.perf_counter()
            first_chunk_latency: float | None = None

            content_parts = []
            reasoning_parts = []
            tool_calls = []
            finish_reason = "stop"

            async for chunk in self.llm.stream_complete(messages, tools):
                if first_chunk_latency is None:
                    first_chunk_latency = time.perf_counter() - call_started_at
                if chunk.type == "content" and chunk.content:
                    content_parts.append(chunk.content)
                    await self._emit("llm:content", {"content": chunk.content})
                elif chunk.type == "reasoning" and chunk.reasoning_content:
                    reasoning_parts.append(chunk.reasoning_content)
                    await self._emit("llm:reasoning", {"reasoning_content": chunk.reasoning_content})
                elif chunk.type == "tool_calls":
                    tool_calls = chunk.tool_calls
                    finish_reason = chunk.finish_reason or "tool_calls"
                    break
                elif chunk.type == "done":
                    finish_reason = chunk.finish_reason or "stop"
                    break
                elif chunk.type == "error":
                    await self._emit_llm_metrics(
                        context=context,
                        messages=messages,
                        tools=tools,
                        attempt=attempt + 1,
                        call_started_at=call_started_at,
                        first_chunk_latency=first_chunk_latency,
                        finish_reason="error",
                        content_chars=sum(len(part) for part in content_parts),
                        reasoning_chars=sum(len(part) for part in reasoning_parts),
                        tool_call_count=len(tool_calls),
                        error=chunk.error or "LLM 流式调用失败",
                    )
                    if attempt < self.MAX_EMPTY_RESPONSE_RETRIES - 1:
                        logger.warning(
                            "LLM 流式错误 (attempt %d/%d): %s, 重试中",
                            attempt + 1,
                            self.MAX_EMPTY_RESPONSE_RETRIES,
                            chunk.error,
                        )
                        break
                    raise RuntimeError(chunk.error or "LLM 流式调用失败")

            response = LLMResponse(
                content="".join(content_parts),
                reasoning_content="".join(reasoning_parts) or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                model=self.llm.get_model_name(),
            )
            await self._emit_llm_metrics(
                context=context,
                messages=messages,
                tools=tools,
                attempt=attempt + 1,
                call_started_at=call_started_at,
                first_chunk_latency=first_chunk_latency,
                finish_reason=finish_reason,
                content_chars=len(response.content or ""),
                reasoning_chars=len(response.reasoning_content or ""),
                tool_call_count=len(response.tool_calls),
            )

            if response.has_content or response.has_tool_calls:
                prefill = context.metadata.pop("_prefill_assistant", None)
                merged_content = response.content
                if prefill:
                    if merged_content:
                        merged_content = prefill + merged_content
                    else:
                        merged_content = prefill

                context.add_message(
                    "assistant",
                    content=merged_content or None,
                    tool_calls=[tool_call.model_dump() for tool_call in response.tool_calls],
                )

                logger.info(
                    "LLM 响应: %s | tool_calls: %s",
                    response.content[:50] if response.content else "(无内容)",
                    [tc.name for tc in response.tool_calls],
                )
                return response

            if finish_reason == "stop":
                if attempt == 0 and context.task:
                    logger.warning(
                        "LLM 返回空响应且 finish_reason=stop (attempt %d/%d), model=%s — "
                        "注入任务提醒后重试一次",
                        attempt + 1,
                        self.MAX_EMPTY_RESPONSE_RETRIES,
                        self.llm.get_model_name(),
                    )
                    context.add_message(
                        "user",
                        f"[System] The model produced no output. Please continue the task using tools. "
                        f"Original task: {context.task}",
                    )
                    continue
                logger.warning(
                    "LLM 返回空响应且 finish_reason=stop (attempt %d/%d), model=%s — "
                    "重试后仍为空，放弃",
                    attempt + 1,
                    self.MAX_EMPTY_RESPONSE_RETRIES,
                    self.llm.get_model_name(),
                )
                break

            if finish_reason == "length":
                logger.warning(
                    "LLM 空响应且 finish_reason=length (attempt %d/%d), model=%s — "
                    "max_tokens 可能不足",
                    attempt + 1,
                    self.MAX_EMPTY_RESPONSE_RETRIES,
                    self.llm.get_model_name(),
                )

                # API overflow handling: try compaction then retry once
                if self._overflow_retry_count < 1 and context.total_tokens > 0:
                    self._overflow_retry_count += 1
                    logger.info("Attempting overflow compaction + retry")
                    try:
                        await self._compact_tier3(context)
                        context.prune_tool_outputs(
                            protect_recent_groups=config_manager.settings.execution.prune_protect_groups,
                            minimum_recovery_tokens=1,
                        )
                    except Exception:
                        logger.exception("Overflow compaction failed")
                    return await self._call_llm(context)

            logger.warning(
                "LLM 空响应 (attempt %d/%d), finish_reason=%s, model=%s",
                attempt + 1,
                self.MAX_EMPTY_RESPONSE_RETRIES,
                finish_reason,
                self.llm.get_model_name(),
            )

        logger.error(
            "LLM 空响应, finish_reason=%s, model=%s",
            finish_reason,
            self.llm.get_model_name(),
        )
        return response

    async def _emit_llm_metrics(
        self,
        *,
        context: LoopContext,
        messages: list,
        tools: list,
        attempt: int,
        call_started_at: float,
        first_chunk_latency: float | None,
        finish_reason: str,
        content_chars: int,
        reasoning_chars: int,
        tool_call_count: int,
        error: str | None = None,
    ) -> None:
        message_dicts = [
            message.model_dump(exclude_none=True)
            if hasattr(message, "model_dump")
            else dict(message)
            for message in messages
        ]
        payload = {
            "run_id": context.run_id,
            "model": self.llm.get_model_name(),
            "attempt": attempt,
            "duration": time.perf_counter() - call_started_at,
            "first_chunk_latency": first_chunk_latency,
            "prompt_tokens": count_messages_tokens(message_dicts, self.llm.get_model_name()),
            "message_count": len(messages),
            "tool_count": len(tools or []),
            "finish_reason": finish_reason,
            "content_chars": content_chars,
            "reasoning_chars": reasoning_chars,
            "tool_call_count": tool_call_count,
        }
        if error:
            payload["error"] = error
        await self._emit("metrics:llm_call", payload)

    async def _compact_context(self, context: LoopContext) -> None:
        """
        检测上下文 token 压力，超阈值时触发逐级压缩：
        - total_tokens > tier3_threshold → Tier 3 LLM 摘要压缩
        - Tier 2 截断由 LoopMessageBuilder._build_tier2_messages() 在 build 时自动处理
        阈值根据 model context window 动态计算。
        """
        settings = config_manager.settings.execution
        usable = self.context_window - settings.compaction_buffer
        tier3_threshold = int(usable * settings.tier3_ratio)
        if context.total_tokens <= tier3_threshold:
            return
        await self._compact_tier3(context)

    async def _compact_tier3(self, context: LoopContext) -> None:
        """
        Tier 3 压缩：将窗口外的旧消息经 LLM 压缩为摘要，替换 context.messages。
        - 使用 llm.complete()（非流式、无 tools），不走 _call_llm 避免递归
        - 压缩结果存入 context.compacted_summary，摘要中包含 [可 session_recall 取回] 标记
        - 保留最近 N 组消息不变，旧消息从 context.messages 移除（DB 原始消息不受影响）
        - 压缩失败时降级跳过，不中断 run
        """
        try:
            grouped = self.message_builder._group_messages(context.messages)
            if len(grouped) <= self.MAX_CONTEXT_GROUPS:
                return

            older_groups = grouped[: -self.MAX_CONTEXT_GROUPS]
            older_messages = [msg for group in older_groups for msg in group]

            transcript_parts = []
            for msg in older_messages:
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    role = msg.get("role", "unknown")
                    transcript_parts.append(f"[{role}] {content[:2000]}")

            transcript = "\n\n".join(transcript_parts)

            system_prompt = self.prompt_manager.get_midrun_compression_system_prompt()
            user_prompt = self.prompt_manager.get_midrun_compression_prompt(
                task=context.task,
                transcript=transcript,
                existing_summary=context.compacted_summary,
            )

            from app.llm.base import LLMMessage, MessageRole
            response = await self.llm.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                    LLMMessage(role=MessageRole.USER, content=user_prompt),
                ],
                tools=None,
            )

            content = (response.content or "").strip()
            if not content:
                logger.warning("Tier 3 compaction returned empty, skipping")
                return

            context.compacted_summary = content

            recent_groups = grouped[-self.MAX_CONTEXT_GROUPS :]
            context.messages = [msg for group in recent_groups for msg in group]
            context.recalculate_tokens()

            logger.info(
                "Tier 3 compaction completed. Summary length=%d, remaining messages=%d, tokens=%d",
                len(content), len(context.messages), context.total_tokens,
            )
        except Exception:
            logger.exception("Tier 3 compaction failed, skipping")

    async def _get_final_summary(self, context: LoopContext) -> str:
        """
        获取最终回答

        Args:
            context: 执行上下文

        Returns:
            str: 最终回答内容
        """
        context.add_message("user", self.prompt_manager.get_final_response_prompt(context.task))

        messages = self.message_builder.build_final_summary(context)

        try:
            summary_parts = []
            async for chunk in self.llm.stream_complete(messages, tools=None):
                if chunk.type == "content" and chunk.content:
                    summary_parts.append(chunk.content)
                    await self._emit("summary:token", {"token": chunk.content})
                elif chunk.type == "done":
                    break

            summary = "".join(summary_parts)

            if summary:
                return summary

        except LLMRetryExhaustedError:
            raise
        except Exception as e:
            logger.error("获取总结失败: %s", e)

        steps_count = len(context.steps)
        fallback = f"任务执行完成，共执行了 {steps_count} 个步骤。"
        return fallback

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
from app.execution.runtime_tool_definitions import (
    DEFAULT_TOOL_SET_CONFIG,
    RuntimeToolDefinitions,
    ToolSetConfig,
)
from app.execution.tool_call_executor import ToolCallExecutor
from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    MessageRole,
    UniversalLLMInterface,
)
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
    MAX_CONTEXT_GROUPS = 10  # 最近上下文分组数，保证 tool_call 与 tool 输出成组保留
    MAX_EMPTY_RESPONSE_RETRIES = 5  # 空响应最大重试
    MAX_READ_ONLY_PASSES = 50  # 只读工具调用最大轮次
    DOOM_LOOP_THRESHOLD = 3  # 致命循环阈值

    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int | None = None,
        event_callback: Callable[[str, dict], Awaitable[None]] | None = None,
        context_window: int = 128000,
        approval_flow: ApprovalFlow | None = None,  # 可选的共享审批流（用于 SubAgent）
        tool_set_config: ToolSetConfig | None = None,  # 可选的工具集配置（用于 SubAgent 跳过首轮探索门禁）
    ):
        self.llm = llm
        self._tool_registry = tool_registry
        self.max_steps = max_steps or config_manager.settings.execution.max_steps
        self.prompt_manager = PromptManager(model_name=self.llm.get_model_name())
        self.event_callback = event_callback
        self.context_window = context_window
        self._overflow_retry_count = 0
        self.tool_definitions = RuntimeToolDefinitions(
            self._tool_registry,
            config=tool_set_config or DEFAULT_TOOL_SET_CONFIG,
        )
        self.message_builder = LoopMessageBuilder(
            prompt_manager=self.prompt_manager,
            max_context_groups=self.MAX_CONTEXT_GROUPS,
            tool_output_max_chars=config_manager.settings.execution.tool_output_max_chars,
            task_anchor_interval=8,
        )
        self.tool_executor = ToolCallExecutor(
            tool_registry=self._tool_registry,
            emit=self._emit,
        )
        # 如果传入了 approval_flow，则复用它（用于 SubAgent 共享主 Agent 的审批流）
        # 否则创建新的审批流实例（用于主 Agent）
        self.approval_flow = approval_flow or ApprovalFlow(emit=self._emit)
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

    def set_approval_result(
        self, result: dict | None, approval_id: str | None = None
    ) -> None:
        self.approval_flow.set_approval_result(result, approval_id=approval_id)

    def _create_summarizer(self) -> Callable[[str, str], Awaitable[str]]:
        """创建摘要生成器回调（解耦 LLM 依赖）"""

        async def summarizer(task: str, transcript: str) -> str:
            system_prompt = self.prompt_manager.get_midrun_compression_system_prompt()
            user_prompt = self.prompt_manager.get_midrun_compression_prompt(
                task=task,
                transcript=transcript,
                existing_summary=self.context.compressor.get_compacted_summary(),
            )
            response = await self.llm.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                    LLMMessage(role=MessageRole.USER, content=user_prompt),
                ],
                tools=None,
            )
            return (response.content or "").strip()

        return summarizer

    # -- phase handlers ---------------------------------------------------

    async def _handle_planning(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """PLANNING 阶段：调用 LLM 决策，决定下一阶段。"""
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

        # Route based on response
        if rt.response.has_tool_calls:
            rt.consecutive_failures = 0
            return LoopPhase.TOOL_EXECUTION

        # No tool calls - validate if stopping is reasonable
        return await self._validate_stop_decision(context, result, rt)

    MAX_DECISION_RETRIES = 5

    async def _validate_stop_decision(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """验证停止决策是否合理"""

        logger.info(
            "验证停止决策: has_executed_tools=%s, has_plan=%s, plan_complete=%s, has_content=%s",
            rt.has_executed_tools,
            context.plan is not None,
            context.plan.is_complete if context.plan else "N/A",
            rt.response.has_content,
        )

        # 没执行过工具 - 纯问答，可以停止
        if not rt.has_executed_tools:
            if rt.response.has_content:
                result.status = LoopStatus.COMPLETED
                result.result = rt.response.content
                return LoopPhase.DONE
            else:
                # 空响应处理
                if rt.response.finish_reason == "length":
                    result.status = LoopStatus.COMPLETED
                    result.result = (
                        "模型输出被截断（max_tokens 不足），请尝试增大 max_tokens 配置"
                    )
                    return LoopPhase.DONE
                if rt.response.finish_reason == "stop":
                    result.status = LoopStatus.COMPLETED
                    result.result = (
                        "模型未返回有效内容（可能触发了内容审核），请调整输入或更换模型"
                    )
                    return LoopPhase.DONE
                rt.consecutive_failures += 1
                if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                    raise RuntimeError(
                        f"模型连续 {self.MAX_ERROR_RETRIES} 次返回空响应（finish_reason={rt.response.finish_reason}），"
                        "请检查模型配置或更换模型"
                    )
                return LoopPhase.PLANNING

        # 执行过工具，检查计划状态，先占时注释掉，判断是否需要这个地方，如果需要，再打开
        # if context.plan and not context.plan.is_complete:
        #     # 检查是否是合理的停止（等待用户输入）
        #     blocked_steps = [s for s in context.plan.steps if s.status == "blocked"]
        #     current_step = context.plan.current_step

        #     if blocked_steps and not current_step:
        #         # 有阻塞步骤且没有进行中的步骤 - 合理停止
        #         result.status = LoopStatus.COMPLETED
        #         result.result = rt.response.content or "需要更多信息才能继续"
        #         return LoopPhase.DONE

            # 计划未完成但停止了 - 直接进入总结阶段，先占时注释掉，判断是否需要这个地方，如果需要，再打开
            # logger.info("计划未完成但 LLM 停止，进入总结阶段")
            # return LoopPhase.FINAL_SUMMARY

        # 没计划或计划完成
        if rt.response.has_content:
            # 正常完成
            result.status = LoopStatus.COMPLETED
            result.result = rt.response.content
            return LoopPhase.DONE
        else:
            # 没有最终回答，进入兜底总结
            return LoopPhase.FINAL_SUMMARY

    def _record_tool_signature(
        self, context: LoopContext, tool_call: LLMToolCall
    ) -> None:
        sig = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True)}"
        recent_sigs: list[str] = context.metadata.setdefault(
            "_recent_tool_signatures", []
        )
        recent_sigs.append(sig)
        if len(recent_sigs) > self.DOOM_LOOP_THRESHOLD * 2:
            recent_sigs[:] = recent_sigs[-self.DOOM_LOOP_THRESHOLD * 2 :]

    def _is_doom_loop(self, context: LoopContext) -> bool:
        recent_sigs: list[str] = context.metadata.get("_recent_tool_signatures", [])
        if len(recent_sigs) >= self.DOOM_LOOP_THRESHOLD:
            tail = recent_sigs[-self.DOOM_LOOP_THRESHOLD :]
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

        for tool_call in rt.response.tool_calls:
            if self.tool_executor._is_read_only_call(tool_call):
                read_only_calls.append(tool_call)
            else:
                write_calls.append(tool_call)

        read_only_calls = self.tool_executor.prepare_read_only_batch(read_only_calls)
        if read_only_calls:
            rt.read_only_passes_used += 1

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

            for step in parallel_steps:
                if step.status == StepStatus.WAITING_FOR_APPROVAL:
                    return await self._handle_approval(step, context, result, rt)

        # 只在达到最大只读轮次时才触发调查预算限制
        if (
            read_only_calls
            and not write_calls
            and rt.read_only_passes_used >= self.MAX_READ_ONLY_PASSES
        ):
            # 如果有未完成的计划，推动LLM继续执行而不是强制总结
            if context.plan and not context.plan.is_complete:
                pending_count = sum(
                    1 for s in context.plan.steps if s.status == "pending"
                )
                in_progress_count = sum(
                    1 for s in context.plan.steps if s.status == "in_progress"
                )

                nudge_prompt = (
                    f"[Investigation Budget Limit] You've reached the maximum number of read-only operations ({self.MAX_READ_ONLY_PASSES} passes). "
                    f"Your plan has {pending_count} pending and {in_progress_count} in-progress steps remaining.\n\n"
                    f"Please proceed with concrete actions now:\n"
                    f"- Call the plan tool to update step status if investigation is complete\n"
                    f"- Call edit/write tools to implement the planned changes\n"
                    f"- Or call plan tool to mark steps as blocked if you need user input\n\n"
                    f"Do NOT continue reading files without making progress."
                )
                context.add_message(MessageRole.USER, nudge_prompt)
                logger.info(
                    "达到最大只读轮次(%d)但计划未完成，推动LLM继续执行: pending=%d, in_progress=%d",
                    self.MAX_READ_ONLY_PASSES,
                    pending_count,
                    in_progress_count,
                )
                return LoopPhase.PLANNING

            # 没有计划或计划已完成，才进入强制总结
            context.metadata["investigation_budget_exhausted"] = True
            logger.info("达到最大只读轮次(%d)，进入总结阶段", self.MAX_READ_ONLY_PASSES)
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
                    context.add_message(MessageRole.USER, doom_prompt)
                    rt.consecutive_failures = 0
                    context.metadata.setdefault("_recent_tool_signatures", []).clear()
                    return LoopPhase.PLANNING
        write_index = 0
        while write_index < len(write_calls):
            tool_call = write_calls[write_index]

            if tool_call.name != "delegate":
                self._record_tool_signature(context, tool_call)
                rt.step_num += 1
                step = await self.tool_executor.execute(tool_call, context, rt.step_num)
                result.steps.append(step)
                context.add_step(step)

                if step.status == StepStatus.WAITING_FOR_APPROVAL:
                    return await self._handle_approval(step, context, result, rt)

                phase, needs_error_recovery = await self._finalize_write_step(
                    tool_call, step, context, rt
                )
                error_recovery_needed = error_recovery_needed or needs_error_recovery
                if phase is not None:
                    return phase

                write_index += 1
                continue

            # 连续的 delegate 段：按 max_concurrent 分批并发执行。
            # delegate 不会触发 WAITING_FOR_APPROVAL（审批已在子 agent
            # 内部通过共享的 approval_flow 消化完毕），因此并发批次内
            # 无需处理审批中断，收尾逻辑与串行路径完全一致。
            delegate_run: list[LLMToolCall] = []
            while (
                write_index < len(write_calls)
                and write_calls[write_index].name == "delegate"
            ):
                delegate_run.append(write_calls[write_index])
                write_index += 1

            max_concurrent = config_manager.settings.subagent.max_concurrent
            for chunk_start in range(0, len(delegate_run), max_concurrent):
                chunk = delegate_run[chunk_start : chunk_start + max_concurrent]
                for tc in chunk:
                    self._record_tool_signature(context, tc)

                start_step = rt.step_num + 1
                chunk_steps = await asyncio.gather(
                    *[
                        self.tool_executor.execute(tc, context, start_step + i)
                        for i, tc in enumerate(chunk)
                    ]
                )
                rt.step_num = start_step + len(chunk) - 1

                for tc, step in zip(chunk, chunk_steps, strict=True):
                    result.steps.append(step)
                    context.add_step(step)

                    phase, needs_error_recovery = await self._finalize_write_step(
                        tc, step, context, rt
                    )
                    error_recovery_needed = error_recovery_needed or needs_error_recovery
                    if phase is not None:
                        return phase

        if error_recovery_needed:
            return LoopPhase.ERROR_RECOVERY

        # Sync plan file after plan tool changes
        if context.plan and context.plan_file_path:
            self.plan_file_sync.sync(
                context.plan, context.plan_file_path, project_path=context.project_path
            )

        # Pruning: lightweight context recovery after each tool execution round
        settings = config_manager.settings.execution
        context.compressor.prune_tool_outputs(
            protect_recent_groups=settings.prune_protect_groups,
            minimum_recovery_tokens=settings.prune_minimum_recovery_tokens,
        )

        return LoopPhase.PLANNING

    async def _finalize_write_step(
        self,
        tool_call: LLMToolCall,
        step: LoopStep,
        context: LoopContext,
        rt: RuntimeState,
    ) -> tuple[LoopPhase | None, bool]:
        """写操作单步收尾：失败计数/emit、doom loop 检测。

        串行 write_call 和并发 delegate 批次共用同一份收尾逻辑，避免
        两条路径的失败处理/doom loop 检测出现不一致。

        返回 (phase, needs_error_recovery)：
        - phase 非 None 时，调用方应立即以该 phase 结束 _handle_tool_execution。
        - needs_error_recovery 为 True 时，调用方应在本轮循环结束后转入 ERROR_RECOVERY。
        """
        needs_error_recovery = False

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
                needs_error_recovery = True
        else:
            rt.consecutive_failures = 0
            rt.has_executed_tools = True

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
            context.add_message(MessageRole.USER, doom_prompt)
            rt.consecutive_failures = 0
            context.metadata.setdefault("_recent_tool_signatures", []).clear()
            return LoopPhase.PLANNING, needs_error_recovery

        return None, needs_error_recovery

    async def _handle_approval(
        self,
        step: LoopStep,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """审批子处理器：等待审批结果，决定后续状态。"""
        logger.info("[_handle_approval] Entering: tool=%s, step_number=%s", step.tool, step.step_number)
        result.status = LoopStatus.WAITING_FOR_APPROVAL
        result.result = step.output

        # 发送运行状态事件：通知整个运行进入"等待审批"状态
        # 注意：此时 tool_call_executor 已发送了 approval:required 事件（包含完整工具信息）
        # 此事件用于标记运行状态，与 approval:required 协同工作：
        # - approval:required: 工具层审批细节（前端用于显示审批对话框，包含完整参数）
        # - run:waiting_for_approval: 运行层状态标记（前端用于更新运行状态）
        await self._emit(
            "run:waiting_for_approval",
            {
                "run_id": result.id,
                "approval_id": step.approval_id,
                "step_number": step.step_number,
                "tool_name": step.tool,
                "tool_call_id": step.tool_call_id,
            },
        )

        logger.info("[_handle_approval] Calling wait_for_approval, tool=%s", step.tool)
        approval = await self.approval_flow.wait_for_approval(step, result.id)
        logger.info("[_handle_approval] wait_for_approval returned: approved=%s, success=%s", approval.approved, approval.success)

        if approval.approved:
            result.status = LoopStatus.RESUMING
            tool_output = approval.output or approval.error or ""
            context.add_message(
                MessageRole.TOOL,
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
            logger.info("[_handle_approval] Emitting tool:result for tool=%s, tool_call_id=%s", step.tool, step.tool_call_id)
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
            logger.info("[_handle_approval] tool:result emitted successfully")

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
                action_prop = (
                    schema.get("parameters", {}).get("properties", {}).get("action", {})
                )
                if "enum" in action_prop:
                    available_actions = action_prop["enum"]

        error_prompt = self.prompt_manager.get_error_prompt(
            error=last_step.error or "工具执行失败（无错误详情）",
            tool=last_step.tool,
            original_args=original_args,
            available_actions=available_actions,
        )

        # 添加错误信息到上下文
        context.add_message(MessageRole.USER, error_prompt)

        # 重置连续失败计数
        rt.consecutive_failures = 0
        rt.turn_retries += 1

        if rt.turn_retries > self.MAX_TURN_RETRIES:
            # 超过重试次数，强制总结
            return LoopPhase.FINAL_SUMMARY

        return LoopPhase.PLANNING

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
        session_id: str | None = None,
        created_at: datetime | None = None,
        history_messages: list[dict[str, str]] | None = None,
        agent_mode: str = "build",
        task_content: str | list[dict] | None = None,
    ) -> LoopResult:
        """
        执行任务

        Args:
            task: 任务描述（纯文本），用于日志记录、事件发送、生成会话标题
            task_content: 实际传递给 LLM 的内容。
                         - 默认等于 task（纯文本场景）
                         - 当用户上传图片时，会是多模态格式的 list[dict]，如：
                           [{"type": "text", "text": "..."}, {"type": "image_url", "url": "..."}]
            project_path: 项目路径
            run_id: 运行 ID
            session_id: 会话 ID
            created_at: 创建时间
            history_messages: 历史对话消息（来自 ConversationHistoryLoader 的 seed messages）
            agent_mode: Agent 模式（build/plan 等）

        Returns:
            LoopResult: 执行结果
        """
        start_time = time.time()
        # 在这儿先构造LoopResult，因为LoopContext需要用到run_id

        loop_result = LoopResult(
            id=run_id or f"run-{uuid.uuid4().hex[:8]}",
            task=task,
            status=LoopStatus.RUNNING,
            created_at=created_at or datetime.now(),
        )
        # 构造LoopContext，此时已将用户的原始输入，上下文，系统提示词等注入到LoopContext中

        context = LoopContext.from_run_input(
            task=task,
            project_path=project_path,
            run_id=loop_result.id,
            session_id=session_id,
            agent_mode=agent_mode,
            history_messages=history_messages,
            task_content=task_content,
        )

        rt = RuntimeState()
        self._runtime = rt

        # 发送开始事件
        await self._emit("run:start", {"run_id": loop_result.id, "task": task})

        logger.info("开始执行任务: %s", task)

        try:
            # 尝试恢复旧计划，存储到 context.recovered_plan 供主循环使用
            if context.agent_mode != "plan":
                await self._try_recover_plan(context)

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
            if (
                rt.step_num >= self.max_steps
                and loop_result.status != LoopStatus.WAITING_FOR_APPROVAL
            ):
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
                loop_result.compacted_summary = (
                    context.compressor.get_compacted_summary()
                )

                if context.plan is not None:
                    if context.plan_file_path:
                        self.plan_file_sync.sync(
                            context.plan,
                            context.plan_file_path,
                            project_path=context.project_path,
                        )
                    await self._emit("plan:updated", context.plan.to_dict())

            self._runtime = None
            loop_result.total_duration = time.time() - start_time
            loop_result.completed_at = datetime.now()

            # 发送完成事件
            if loop_result.status not in {
                LoopStatus.CANCELLED,
                LoopStatus.WAITING_FOR_APPROVAL,
                LoopStatus.FAILED,
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

    async def _try_recover_plan(self, context: LoopContext) -> None:
        """尝试恢复旧计划，存储到 context.recovered_plan，由主循环决定是否使用。"""
        plan_tool = self.tool_definitions.get_plan_tool()
        if not plan_tool:
            logger.info("无 plan_tool，跳过计划恢复")
            return

        # Set context for file operations
        plan_tool.set_context(context.project_path, context.session_id)
        plan_tool.set_plan(None)
        context.plan = None

        # Try to recover existing plan
        recovered_plan = plan_tool.try_recover(max_age_hours=24)
        logger.info(
            "计划恢复: recovered_plan=%s, goal=%s",
            recovered_plan is not None,
            recovered_plan.goal[:80] if recovered_plan else "N/A",
        )

        if recovered_plan:
            # 存储旧计划到 context，由主循环在首轮注入提示，让 LLM 自己决定
            context.recovered_plan = recovered_plan
            logger.info("旧计划已恢复，将在首轮提示 LLM 决定是否继续")
        else:
            context.recovered_plan = None

    # -- LLM calls --------------------------------------------------------

    async def _call_llm(self, context: LoopContext) -> LLMResponse:
        """
        调用 LLM 并处理响应

        职责：
        1. 上下文压力检查与压缩
        2. 调用 adapter 的 stream_collect 获取响应
        3. 处理空响应（注入任务提醒、overflow 压缩）
        4. Prefill 合并
        5. 发射指标事件

        Args:
            context: 执行上下文

        Returns:
            LLMResponse: LLM 响应
        """
        # 1. 上下文压力检查
        if context.compressor.check_pressure(
            self.context_window,
            config_manager.settings.execution.tier3_ratio,
        ):
            await context.compressor.compact_tier3(
                task=context.task,
                summarizer=self._create_summarizer(),
            )

        tools = (
            self.tool_definitions.for_plan_mode()
            if context.agent_mode == "plan"
            else self.tool_definitions.for_context(context)
        )
        messages = self.message_builder.build(context)
        call_started_at = time.perf_counter()

        # 2. 调用 adapter 流式收集（不处理空响应重试，由我们自己处理）
        response, first_chunk_latency = await self.llm.stream_collect(
            messages,
            tools,
            on_content=lambda c: self._emit("llm:content", {"content": c}),
            on_reasoning=lambda r: self._emit("llm:reasoning", {"reasoning_content": r}),
            max_empty_retries=0,
            track_first_chunk_latency=True,
        )

        # 3. 发射指标
        await self._emit_llm_metrics(
            context=context,
            messages=messages,
            tools=tools,
            attempt=1,
            call_started_at=call_started_at,
            first_chunk_latency=first_chunk_latency,
            finish_reason=response.finish_reason,
            content_chars=len(response.content or ""),
            reasoning_chars=len(response.reasoning_content or ""),
            tool_call_count=len(response.tool_calls),
        )

        # 4. 处理空响应
        if not response.has_content and not response.has_tool_calls:
            response = await self._handle_empty_response(
                context, response, messages, tools, call_started_at
            )

        # 5. 添加到上下文
        context.add_message(
            MessageRole.ASSISTANT,
            content=response.content or None,
            tool_calls=[tc.model_dump() for tc in response.tool_calls],
        )

        logger.info(
            "LLM 响应: %s | tool_calls: %s",
            (response.content or "")[:50] or "(无内容)",
            [tc.name for tc in response.tool_calls],
        )
        return response

    async def _handle_empty_response(
        self,
        context: LoopContext,
        response: LLMResponse,
        messages: list[LLMMessage],
        tools: list,
        call_started_at: float,
    ) -> LLMResponse:
        """
        处理 LLM 空响应

        策略：
        - finish_reason=stop: 注入任务提醒后重试一次
        - finish_reason=length: 压缩上下文后重试一次

        Returns:
            LLMResponse: 可能是空响应，调用方需继续处理
        """
        finish_reason = response.finish_reason

        if finish_reason == "stop":
            # 注入任务提醒后重试一次
            logger.warning(
                "LLM 空响应且 finish_reason=stop, model=%s — 注入任务提醒后重试",
                self.llm.get_model_name(),
            )
            context.add_message(
                MessageRole.USER,
                f"[System] The model produced no output. Please continue the task using tools. "
                f"Original task: {context.task}",
            )
            # 重新构建消息（包含新注入的任务提醒）
            messages = self.message_builder.build(context)
            response, _ = await self.llm.stream_collect(
                messages,
                tools,
                on_content=lambda c: self._emit("llm:content", {"content": c}),
                on_reasoning=lambda r: self._emit("llm:reasoning", {"reasoning_content": r}),
                max_empty_retries=0,
            )
            # 重试后有内容，添加到上下文并返回
            if response.has_content or response.has_tool_calls:
                context.add_message(
                    MessageRole.ASSISTANT,
                    content=response.content or None,
                    tool_calls=[tc.model_dump() for tc in response.tool_calls],
                )
            return response

        elif finish_reason == "length":
            # Overflow 处理：压缩上下文后重试
            logger.warning(
                "LLM 空响应且 finish_reason=length, model=%s — 尝试压缩上下文",
                self.llm.get_model_name(),
            )
            if self._overflow_retry_count < 1 and context.compressor.get_total_tokens() > 0:
                self._overflow_retry_count += 1
                try:
                    await context.compressor.compact_tier3(
                        task=context.task,
                        summarizer=self._create_summarizer(),
                    )
                    context.compressor.prune_tool_outputs(
                        protect_recent_groups=config_manager.settings.execution.prune_protect_groups,
                        minimum_recovery_tokens=1,
                    )
                except Exception:
                    logger.exception("Overflow compaction failed")
                return await self._call_llm(context)

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
            (
                message.model_dump(exclude_none=True)
                if hasattr(message, "model_dump")
                else dict(message)
            )
            for message in messages
        ]
        payload = {
            "run_id": context.run_id,
            "model": self.llm.get_model_name(),
            "attempt": attempt,
            "duration": time.perf_counter() - call_started_at,
            "first_chunk_latency": first_chunk_latency,
            "prompt_tokens": count_messages_tokens(
                message_dicts, self.llm.get_model_name()
            ),
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

    async def _get_final_summary(self, context: LoopContext) -> str:
        """
        获取最终回答

        Args:
            context: 执行上下文

        Returns:
            str: 最终回答内容
        """
        context.add_message(
            MessageRole.USER, self.prompt_manager.get_final_response_prompt(context.task)
        )

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

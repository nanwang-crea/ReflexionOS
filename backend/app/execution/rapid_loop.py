import asyncio
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
from app.execution.prompt_manager import PromptManager
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.execution.tool_call_executor import ToolCallExecutor
from app.llm.base import LLMResponse, UniversalLLMInterface
from app.llm.retry import LLMRetryExhaustedError
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
    MAX_TURN_RETRIES = 2  # 每轮最大重试
    MAX_SUMMARY_RETRIES = 2  # 总结最大重试
    MAX_ERROR_RETRIES = 2  # 错误恢复最大重试
    MAX_CONTEXT_GROUPS = 10  # 最近上下文分组数，保证 tool_call 与 tool 输出成组保留
    MAX_EMPTY_RESPONSE_RETRIES = 3  # 空响应最大重试

    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int | None = None,
        event_callback: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self.llm = llm
        self._tool_registry = tool_registry
        self.max_steps = max_steps or config_manager.settings.execution.max_steps
        self.prompt_manager = PromptManager()
        self.event_callback = event_callback
        self.tool_definitions = RuntimeToolDefinitions(self._tool_registry)
        self.message_builder = LoopMessageBuilder(
            prompt_manager=self.prompt_manager,
            max_context_groups=self.MAX_CONTEXT_GROUPS,
            tool_output_max_chars=config_manager.settings.execution.tool_output_max_chars,
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
        rt.response = await self._call_llm(context)

        if rt.response.has_tool_calls:
            rt.consecutive_failures = 0
            return LoopPhase.TOOL_EXECUTION

        # 没有工具调用
        if rt.has_executed_tools:
            if rt.response.has_content:
                # 已经有可直接返回给用户的答案，不再强制进入总结
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

                if step.status == StepStatus.WAITING_FOR_APPROVAL:
                    return await self._handle_approval(step, context, result, rt)

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

        # Execute write tools serially
        for tool_call in write_calls:
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

        if error_recovery_needed:
            return LoopPhase.ERROR_RECOVERY
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

        error_prompt = self.prompt_manager.get_error_prompt(
            error=last_step.error or "Unknown error",
            tool=last_step.tool,
            code_snippet="",
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
            tools = self.tool_definitions.for_context(context)
            messages = self.message_builder.build(context, tools)

            content_parts = []
            tool_calls = []
            finish_reason = "stop"

            async for chunk in self.llm.stream_complete(messages, tools):
                if chunk.type == "content" and chunk.content:
                    content_parts.append(chunk.content)
                elif chunk.type == "tool_calls":
                    tool_calls = chunk.tool_calls
                    finish_reason = chunk.finish_reason or "tool_calls"
                    break
                elif chunk.type == "done":
                    finish_reason = chunk.finish_reason or "stop"
                    break
                elif chunk.type == "error":
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
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                model=self.llm.get_model_name(),
            )

            if response.has_content or response.has_tool_calls:
                for part in content_parts:
                    await self._emit("llm:content", {"content": part})

                context.add_message(
                    "assistant",
                    content=response.content or None,
                    tool_calls=[tool_call.model_dump() for tool_call in response.tool_calls],
                )

                logger.info(
                    "LLM 响应: %s | tool_calls: %s",
                    response.content[:50] if response.content else "(无内容)",
                    [tc.name for tc in response.tool_calls],
                )
                return response

            if finish_reason == "stop":
                logger.warning(
                    "LLM 返回空响应且 finish_reason=stop (attempt %d/%d), model=%s — "
                    "可能是内容审核过滤或模型拒绝，不再重试",
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

    async def _compact_context(self, context: LoopContext) -> None:
        """
        检测上下文 token 压力，超阈值时触发逐级压缩：
        - total_tokens > tier3_compact_threshold_tokens → Tier 3 LLM 摘要压缩
        - Tier 2 截断由 LoopMessageBuilder._build_tier2_messages() 在 build 时自动处理
        """
        settings = config_manager.settings.execution
        if context.total_tokens <= settings.tier3_compact_threshold_tokens:
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

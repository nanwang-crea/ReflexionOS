"""
文件功能：任务执行引擎的主循环（状态机驱动的 Agent 执行核心）
文件描述：实现 RapidExecutionLoop，是整个 Agent 执行系统的中枢——驱动 LLM 交替进行
         "规划决策 → 工具执行 → （审批/错误恢复）→ 最终总结" 直到任务完成或达到终止条件。
         协调上下文压缩（context_manager）、工具执行（tool_call_executor）、审批流程
         （approval_flow）、计划文件同步（plan_file_sync）、Prompt 组装（prompt_manager）
         等多个子模块，是它们的编排者。
核心逻辑：以显式状态机（LoopPhase：PLANNING/TOOL_EXECUTION/ERROR_RECOVERY/FINAL_SUMMARY/
         DONE）驱动主循环，每个 phase handler 接收当前状态并返回下一个 phase，而不是用
         单个庞大协程隐式嵌套处理审批中断、重试与错误恢复，这样审批暂停/恢复、多轮重试等
         流程都能显式地在状态转移中体现，便于跟踪与排查。只读工具调用并行执行以提速，写操作
         （有副作用）串行执行以保证顺序正确性；连续失败、"死循环"检测（doom loop）、只读调查
         预算耗尽等情况都会触发对应的状态转移或提示注入，防止执行失控。
"""

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
    """Main agent execution loop.

    The runtime alternates between planning, tool execution and recovery until
    it can emit a final summary or reaches a terminal state. Keeping the phase
    machine explicit makes approval pauses, retries and error recovery easier to
    reason about than a single monolithic coroutine.
    """

    # 重试配置
    # Retry guards keep the loop responsive even when the model stalls.
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
        """
        函数名：__init__
        入参：
          - llm (UniversalLLMInterface)：统一 LLM 接口，用于对话补全与流式收集
          - tool_registry (ToolRegistry)：工具注册表，提供可调用工具的定义与执行入口
          - max_steps (int | None)：单次 run 最大执行步数，为 None 时取全局配置默认值
          - event_callback：事件回调，用于向外（如 WebSocket/前端）推送执行过程中的各类事件
          - context_window (int)：模型上下文窗口大小（token 数），供压缩阈值判断使用
          - approval_flow (ApprovalFlow | None)：共享的审批流实例，SubAgent 复用主 Agent 的
                                                  审批流；为 None 时新建一个（用于主 Agent）
          - tool_set_config (ToolSetConfig | None)：工具集配置，SubAgent 场景用于跳过首轮
                                                      只读探索门禁；为 None 时用默认配置
        功能：初始化执行循环所需的全部协作组件（Prompt 管理器、消息构建器、工具执行器、
             审批流、计划文件同步器等）
        运行逻辑：保存 llm/tool_registry/max_steps 等基础配置；构造 PromptManager（按模型名
                 选择模板族）；构造 RuntimeToolDefinitions（决定当前可用工具集）；构造
                 LoopMessageBuilder（负责把 LoopContext 转换为发给 LLM 的消息列表）；构造
                 ToolCallExecutor（独立负责工具校验+执行+事件发射，与主循环的阶段流转解耦）；
                 复用或新建 ApprovalFlow；初始化运行时状态占位符 self._runtime 为 None
        出参：无
        """
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
        # Tool execution stays in a separate component so the loop can focus
        # on phase transitions while the executor focuses on validation + event
        # emission.
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
        """只读属性：暴露内部使用的工具注册表实例"""
        return self._tool_registry

    async def _emit(self, event_type: str, data: dict) -> None:
        """
        函数名：_emit
        入参：
          - event_type (str)：事件类型标识（如 "run:start"、"tool:error"）
          - data (dict)：事件携带的数据
        功能：统一的事件发射入口，转发给外部注入的 event_callback
        运行逻辑：未配置回调时直接跳过；配置了回调则调用，回调本身抛异常时记录错误日志
                 并重新抛出（不吞掉事件发送失败）
        出参：无
        """
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error("事件回调失败: %s", e)
                raise

    def set_approval_result(
        self, result: dict | None, approval_id: str | None = None
    ) -> None:
        """
        函数名：set_approval_result
        入参：
          - result (dict | None)：审批结果数据（同意/拒绝及附带信息）
          - approval_id (str | None)：对应的审批记录 ID
        功能：外部（如 API 层收到用户审批操作）回填审批结果，唤醒等待中的执行流程
        运行逻辑：直接转发给 self.approval_flow.set_approval_result 处理
        出参：无
        """
        self.approval_flow.set_approval_result(result, approval_id=approval_id)

    def _create_summarizer(
        self, context: LoopContext
    ) -> Callable[[str, str], Awaitable[str]]:
        """创建摘要生成器回调（解耦 LLM 依赖）

        Args:
            context: 当前循环上下文，用于读取已有的压缩摘要
                     （RapidExecutionLoop 实例本身不持有 context，
                     必须由调用方传入，否则会因 self.context 不存在而报错）
        """

        async def summarizer(task: str, transcript: str) -> str:
            """
            函数名：summarizer（闭包）
            入参：
              - task (str)：当前任务描述
              - transcript (str)：待压缩的对话/工具调用记录原文
            功能：调用 LLM 对给定 transcript 生成压缩摘要，供 ContextCompressor 在
                 Tier 3 压缩时使用
            运行逻辑：组装 system + user 两条消息（分别来自 PromptManager 的中途压缩
                     system 提示词和携带已有摘要的用户提示词），调用 LLM 非流式补全，
                     返回去除首尾空白的文本内容
            出参：str - LLM 生成的压缩摘要文本
            """
            system_prompt = self.prompt_manager.get_midrun_compression_system_prompt()
            user_prompt = self.prompt_manager.get_midrun_compression_prompt(
                task=task,
                transcript=transcript,
                existing_summary=context.compressor.get_compacted_summary(),
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
        """
        函数名：_handle_planning
        入参：
          - context (LoopContext)：当前执行上下文（消息历史、计划、压缩器等）
          - result (LoopResult)：本轮 Loop 的结果累积对象
          - rt (RuntimeState)：状态机运行时状态
        功能：PLANNING 阶段处理函数——调用 LLM 做决策，判断是继续调用工具还是准备停止
        运行逻辑：
          1. 重置 overflow 重试计数
          2. 调用 _call_llm 获取本轮 LLM 响应并记录日志
          3. 若响应包含工具调用，重置连续失败计数，转入 TOOL_EXECUTION 阶段
          4. 若无工具调用，交给 _validate_stop_decision 判断停止是否合理，返回其决定的下一阶段
        出参：LoopPhase - 状态机下一阶段
        """
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
        """
        函数名：_validate_stop_decision
        入参：
          - context (LoopContext)：当前执行上下文
          - result (LoopResult)：本轮 Loop 结果累积对象
          - rt (RuntimeState)：状态机运行时状态（本次判断依赖 rt.response）
        功能：验证停止决策是否合理——在 LLM 未返回工具调用时，判断是应正常结束、
             重试规划、还是转入兜底总结
        运行逻辑：
          1. 若本轮从未执行过工具（纯问答场景）：
             - 有内容则直接标记完成并结束（DONE）
             - 无内容需按 finish_reason 分支处理：length（截断）/stop（可能被内容审核拦截）
               都直接结束并给出对应提示；其他情况计入连续失败次数，超阈值则抛异常终止，
               否则回到 PLANNING 重试
          2. 若已执行过工具：有最终文本内容则视为正常完成（DONE）；否则转入 FINAL_SUMMARY
             兜底生成总结（说明：这里存在一段关于"计划未完成但停止"的逻辑，当前被注释掉，
             保留但未启用，如需要可参考注释内容打开）
        出参：LoopPhase - 状态机下一阶段
        """

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
        """
        函数名：_record_tool_signature
        入参：
          - context (LoopContext)：当前执行上下文，用于存取"最近工具调用签名"列表
          - tool_call (LLMToolCall)：本次待记录的工具调用
        功能：记录一次工具调用的"签名"（工具名+参数），用于后续检测是否陷入死循环
        运行逻辑：将工具名与排序后的参数 JSON 拼成签名字符串，追加到
                 context.metadata["_recent_tool_signatures"] 列表；列表超过阈值
                 （DOOM_LOOP_THRESHOLD 的2倍）时只保留最近的部分，避免无限增长
        出参：无
        """
        sig = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True)}"
        recent_sigs: list[str] = context.metadata.setdefault(
            "_recent_tool_signatures", []
        )
        recent_sigs.append(sig)
        if len(recent_sigs) > self.DOOM_LOOP_THRESHOLD * 2:
            recent_sigs[:] = recent_sigs[-self.DOOM_LOOP_THRESHOLD * 2 :]

    def _is_doom_loop(self, context: LoopContext) -> bool:
        """
        函数名：_is_doom_loop
        入参：
          - context (LoopContext)：当前执行上下文，读取其中记录的最近工具调用签名
        功能：判断是否陷入"死循环"——连续多次调用同一工具+同一参数却没有推进任务
        运行逻辑：取最近 DOOM_LOOP_THRESHOLD 次工具调用签名，若数量已达阈值且这些
                 签名全部相同（去重后只剩1个），判定为死循环
        出参：bool - True 表示检测到死循环
        """
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
        """
        函数名：_handle_tool_execution
        入参：
          - context (LoopContext)：当前执行上下文
          - result (LoopResult)：本轮 Loop 结果累积对象
          - rt (RuntimeState)：状态机运行时状态（本次读取 rt.response.tool_calls）
        功能：TOOL_EXECUTION 阶段处理函数——执行 LLM 本轮请求的所有工具调用，
             只读工具并行执行，有副作用的写操作串行执行（delegate 子任务除外，
             支持分批并发）
        运行逻辑：
          1. 将本轮工具调用拆分为只读（read_only_calls）与写操作（write_calls）两组
          2. 只读组：经 prepare_read_only_batch 预处理后用 asyncio.gather 并行执行；
             记录只读调用轮次；逐个处理执行结果——失败则累加连续失败计数并发送
             tool:error 事件，超过 MAX_ERROR_RETRIES 标记需要错误恢复；成功则清零
             失败计数、标记 has_executed_tools
          3. 只读结果中若有步骤处于等待审批状态，立即转入 _handle_approval 处理
          4. 若已达最大只读轮次（MAX_READ_ONLY_PASSES）且本轮没有写操作：
             计划未完成时向上下文注入"预算已到，请采取具体行动"的提示并回到 PLANNING
             推动 LLM 继续；否则标记调查预算耗尽并转入 FINAL_SUMMARY 强制总结
          5. 记录只读调用签名，检测死循环，命中则注入提示并回到 PLANNING
          6. 写操作组：按顺序处理，普通写工具逐个串行执行并调用 _finalize_write_step
             收尾；连续的 delegate（子任务委派）调用按 max_concurrent 分批并发执行
             （delegate 内部审批已通过共享 approval_flow 消化，无需在此处理等待审批）
          7. 若过程中标记了需要错误恢复，转入 ERROR_RECOVERY
          8. 若本轮涉及计划变更，同步计划文件到磁盘
          9. 执行完一轮后做一次轻量的上下文裁剪（prune_tool_outputs），回收部分 token
          10. 默认返回 PLANNING，继续下一轮决策
        出参：LoopPhase - 状态机下一阶段
        """
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

        函数名：_finalize_write_step
        入参：
          - tool_call (LLMToolCall)：本次执行的写操作工具调用
          - step (LoopStep)：该工具调用执行后得到的步骤记录
          - context (LoopContext)：当前执行上下文
          - rt (RuntimeState)：状态机运行时状态
        功能：统一处理单个写操作步骤执行后的收尾逻辑——失败计数、事件发射、
             死循环检测，供串行写操作和并发 delegate 批次共用
        运行逻辑：
          1. 步骤失败：累加连续失败计数并发送 tool:error 事件；达到 MAX_ERROR_RETRIES
             则标记 needs_error_recovery=True
          2. 步骤成功：清零连续失败计数，标记已执行过工具
          3. 检测死循环：命中则注入"必须更换方案"的提示消息、清零失败计数与签名记录，
             并返回 (PLANNING, needs_error_recovery) 让调用方立即回到 PLANNING
          4. 未命中死循环则返回 (None, needs_error_recovery)，调用方按常规流程继续
        出参：tuple[LoopPhase | None, bool] - (需要立即跳转到的阶段或 None, 是否需要错误恢复)
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
        """Pause the run until the user approves or rejects the current step.

        函数名：_handle_approval
        入参：
          - step (LoopStep)：处于 WAITING_FOR_APPROVAL 状态、需要人工审批的步骤
          - context (LoopContext)：当前执行上下文
          - result (LoopResult)：本轮 Loop 结果累积对象
          - rt (RuntimeState)：状态机运行时状态
        功能：暂停当前运行，等待用户批准或拒绝该步骤，并根据审批结果决定后续走向
        运行逻辑：
          1. 将 result.status 置为 WAITING_FOR_APPROVAL 并发送 run:waiting_for_approval
             事件通知运行层状态变更（与 tool_call_executor 已发送的 approval:required
             工具层事件协同，前者标记运行状态，后者携带完整审批参数供前端弹窗）
          2. 调用 approval_flow.wait_for_approval 挂起协程，直到外部通过
             set_approval_result 回填结果才会恢复
          3. 若审批通过：把工具的实际输出/错误回填进对话上下文和步骤记录，更新步骤状态
             为 SUCCESS/FAILED，发送 tool:result 和 run:resuming 事件，标记已执行过工具，
             回到 PLANNING 阶段继续决策
          4. 若审批被拒绝：将步骤标记为 FAILED，发送 tool:error 和 run:cancelled 事件，
             整体运行状态置为 CANCELLED，转入 DONE 结束
        出参：LoopPhase - 状态机下一阶段（PLANNING 或 DONE）
        """
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
        """
        函数名：_handle_error_recovery
        入参：
          - context (LoopContext)：当前执行上下文
          - result (LoopResult)：本轮 Loop 结果累积对象（用于取最后一个失败步骤）
          - rt (RuntimeState)：状态机运行时状态
        功能：ERROR_RECOVERY 阶段处理函数——将最近一次失败的错误信息整理成提示词
             注入对话上下文，为下一轮 LLM 重试做准备
        运行逻辑：
          1. 取最后一个执行步骤，若没有步骤记录（异常情况）直接转入 FINAL_SUMMARY
          2. 从该步骤取出失败时使用的原始参数；若该工具的 schema 中声明了 action 的
             枚举可选值，取出作为"可用操作"提示
          3. 通过 prompt_manager.get_error_prompt 生成结构化错误提示词，注入为
             一条 USER 消息，引导 LLM 参考错误信息、原始参数、可用操作来纠正后重试
          4. 重置连续失败计数，累加本轮 turn_retries；超过 MAX_TURN_RETRIES 则放弃重试，
             转入 FINAL_SUMMARY 强制总结；否则回到 PLANNING 让 LLM 重新决策
        出参：LoopPhase - 状态机下一阶段（PLANNING 或 FINAL_SUMMARY）
        """
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
        """
        函数名：_handle_final_summary
        入参：
          - context (LoopContext)：当前执行上下文
          - result (LoopResult)：本轮 Loop 结果累积对象
          - rt (RuntimeState)：状态机运行时状态（本函数未直接使用，保持 handler 签名一致）
        功能：FINAL_SUMMARY 阶段处理函数——请求 LLM 生成最终总结文本，并结束本轮 Loop
        运行逻辑：调用 _get_final_summary 获取总结文本，写入 result.result，
                 将 result.status 置为 COMPLETED
        出参：LoopPhase - 固定返回 DONE，结束状态机
        """
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

            # Each handler returns the next phase, which keeps retries and
            # approval resumes explicit instead of hiding them inside recursion.
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
        """尝试恢复旧计划，存储到 context.recovered_plan，由主循环决定是否使用。

        函数名：_try_recover_plan
        入参：
          - context (LoopContext)：当前执行上下文，恢复到的计划会存入其 recovered_plan 字段
        功能：会话开始时尝试从磁盘恢复此前未完成的计划文件，供主循环决定是否续接
        运行逻辑：
          1. 若当前工具集里没有 plan 工具（未启用计划功能），直接跳过
          2. 为 plan 工具设置项目路径/会话上下文，并清空其内部计划状态与 context.plan
          3. 调用 plan 工具的 try_recover（24 小时有效期）尝试从磁盘找回未完成的旧计划
          4. 找到则存入 context.recovered_plan，留给主循环首轮向 LLM 提示是否继续该计划；
             找不到则显式置为 None
        出参：无
        """
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
                summarizer=self._create_summarizer(context),
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

        函数名：_handle_empty_response
        入参：
          - context (LoopContext)：当前执行上下文
          - response (LLMResponse)：本轮既无内容又无工具调用的空响应
          - messages (list[LLMMessage])：本轮发给 LLM 的消息列表（stop 分支会重新构建）
          - tools (list)：本轮可用工具定义列表，重试时原样透传
          - call_started_at (float)：本次 LLM 调用起始时间戳（当前实现未在本函数内使用，
                                      保留以与调用方签名对齐）
        功能：LLM 返回空响应（既无文本也无工具调用）时的兜底重试处理
        运行逻辑：
          1. finish_reason == "stop"：注入一条系统提醒消息（告知模型未产生输出，
             要求继续使用工具完成任务），重新构建消息后再调用一次 LLM；若重试后
             有内容或工具调用，则写入对话历史
          2. finish_reason == "length"：说明输出被截断，若尚未做过 overflow 重试且
             当前上下文有 token 占用，执行一次 Tier 3 压缩 + 工具输出裁剪，然后递归
             调用 _call_llm 完整重跑一次（包含压力检查等全流程）
          3. 其他 finish_reason 或重试条件不满足：原样返回该空响应，交由调用方
             （_validate_stop_decision）按连续失败计数处理
        出参：LLMResponse - 重试后的响应（可能仍为空），调用方需继续处理
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
                        summarizer=self._create_summarizer(context),
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
        """
        函数名：_emit_llm_metrics
        入参：
          - context (LoopContext)：当前执行上下文，取 run_id
          - messages (list)：本次发给 LLM 的消息列表，用于统计 prompt token 数
          - tools (list)：本次可用工具列表，用于统计工具数量
          - attempt (int)：本次调用是第几次尝试
          - call_started_at (float)：调用起始时间戳（time.perf_counter 基准）
          - first_chunk_latency (float | None)：首个流式响应块的延迟
          - finish_reason (str)：LLM 返回的结束原因
          - content_chars (int)：响应正文字符数
          - reasoning_chars (int)：响应推理内容字符数（如有）
          - tool_call_count (int)：本次响应中的工具调用数量
          - error (str | None)：若调用出错，附带的错误信息
        功能：统计并发射一次 LLM 调用的性能与结果指标事件，供监控/前端展示使用
        运行逻辑：将消息对象统一转为可序列化字典，组装包含耗时、token 数、消息数、
                 工具数、结束原因等字段的 payload，附带错误信息（如有），通过
                 metrics:llm_call 事件发出
        出参：无
        """
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

        函数名：_get_final_summary
        入参：
          - context (LoopContext)：当前执行上下文
        功能：请求 LLM 流式生成最终总结文本；若生成失败或为空，退回到基于步骤数的
             兜底文案，保证任务始终有一个可展示的结束回复
        运行逻辑：
          1. 向上下文追加一条引导生成最终回复的 USER 消息（来自 prompt_manager）
          2. 用 message_builder.build_final_summary 构建适合总结阶段的消息列表
             （通常会做更激进的裁剪，避免总结阶段仍带着大量历史工具输出）
          3. 流式调用 LLM，逐块拼接内容并通过 summary:token 事件实时推送给前端，
             遇到 "done" 块结束流式读取
          4. 若拼出的 summary 非空则直接返回
          5. LLMRetryExhaustedError 直接向上抛出（重试耗尽是需要让调用方感知的失败）；
             其他异常记录错误日志但不抛出，继续走兜底分支
          6. 兜底：summary 为空或过程中出现异常时，返回"任务执行完成，共执行了 N 个步骤"
             的固定文案
        出参：str - 最终回答内容（LLM 生成的总结，或兜底文案）
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

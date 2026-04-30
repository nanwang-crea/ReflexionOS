import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from app.config.settings import config_manager
from app.execution.context_manager import LoopContext
from app.execution.initial_plan_bootstrapper import InitialPlanBootstrapper
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.models import LoopResult, LoopStatus, StepStatus
from app.execution.prompt_manager import PromptManager
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.execution.tool_call_executor import ToolCallExecutor
from app.llm.base import LLMResponse, UniversalLLMInterface
from app.llm.retry import RetryExhaustedError
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# loop 阶段
class LoopPhase:
    PLANNING = "planning"
    TOOL_EXECUTION = "tool_execution"
    ERROR_RECOVERY = "error_recovery"
    FINAL_SUMMARY = "final_summary"
    DONE = "done"


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

    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int = None,
        event_callback: Callable[[str, dict], Awaitable[None]] = None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps or config_manager.settings.execution.max_steps
        self.prompt_manager = PromptManager()
        self.event_callback = event_callback
        self.tool_definitions = RuntimeToolDefinitions(tool_registry)
        self.message_builder = LoopMessageBuilder(
            prompt_manager=self.prompt_manager,
            max_context_groups=self.MAX_CONTEXT_GROUPS,
        )
        self.initial_plan_bootstrapper = InitialPlanBootstrapper(
            llm=self.llm,
            tool_definitions=self.tool_definitions,
            message_builder=self.message_builder,
            emit=self._emit,
        )
        self.tool_executor = ToolCallExecutor(
            tool_registry=self.tool_registry,
            emit=self._emit,
        )

        # 状态追踪
        self.has_executed_tools = False
        self.consecutive_failures = 0

    async def _emit(self, event_type: str, data: dict) -> None:
        """发送事件"""
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error("事件回调失败: %s", e)

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

        # 发送开始事件
        await self._emit("run:start", {"run_id": loop_result.id, "task": task})

        logger.info("开始执行任务: %s", task)

        try:
            await self.initial_plan_bootstrapper.bootstrap(context)

            state = LoopPhase.PLANNING
            step_num = 0
            turn_retries = 0

            while state != LoopPhase.DONE and step_num < self.max_steps:
                if state == LoopPhase.PLANNING:
                    # 调用 LLM 决策
                    response = await self._call_llm(context)

                    # 检查是否有工具调用
                    if response.has_tool_calls:
                        state = LoopPhase.TOOL_EXECUTION
                        turn_retries = 0
                    else:
                        # 没有工具调用
                        if self.has_executed_tools:
                            if response.has_content:
                                # 已经有可直接返回给用户的答案，不再强制进入总结
                                loop_result.status = LoopStatus.COMPLETED
                                loop_result.result = response.content
                                state = LoopPhase.DONE
                            else:
                                # 没有最终回答时，再进入兜底总结阶段
                                state = LoopPhase.FINAL_SUMMARY
                        else:
                            # 没执行过工具，直接完成
                            if response.has_content:
                                loop_result.status = LoopStatus.COMPLETED
                                loop_result.result = response.content
                                state = LoopPhase.DONE
                            else:
                                raise RuntimeError("模型未返回任何内容，也未发起工具调用")

                elif state == LoopPhase.TOOL_EXECUTION:
                    step_num += 1

                    # 执行所有工具调用
                    for tool_call in response.tool_calls:
                        step = await self.tool_executor.execute(tool_call, context, step_num)
                        loop_result.steps.append(step)
                        context.add_step(step)

                        if step.status == StepStatus.WAITING_FOR_APPROVAL:
                            loop_result.status = LoopStatus.WAITING_FOR_APPROVAL
                            loop_result.result = step.output
                            state = LoopPhase.DONE
                            break

                        if step.status == StepStatus.FAILED:
                            self.consecutive_failures += 1

                            # 发送工具失败事件
                            await self._emit(
                                "tool:error",
                                {
                                    "tool_name": tool_call.name,
                                    "step_number": step.step_number,
                                    "tool_call_id": step.tool_call_id,
                                    "error": step.error,
                                    "duration": step.duration,
                                    "arguments": step.args,
                                },
                            )

                            # 检查是否需要进入错误恢复
                            if self.consecutive_failures >= self.MAX_ERROR_RETRIES:
                                state = LoopPhase.ERROR_RECOVERY
                                break
                        else:
                            self.consecutive_failures = 0
                            self.has_executed_tools = True

                    if state == LoopPhase.TOOL_EXECUTION:
                        # 工具执行完成，回到规划状态
                        state = LoopPhase.PLANNING

                elif state == LoopPhase.ERROR_RECOVERY:
                    # 错误恢复：给 LLM 错误信息，让它修正
                    last_step = loop_result.steps[-1] if loop_result.steps else None

                    if last_step:
                        error_prompt = self.prompt_manager.get_error_prompt(
                            error=last_step.error or "Unknown error",
                            tool=last_step.tool,
                            code_snippet="",
                        )

                        # 添加错误信息到上下文
                        context.add_message("user", error_prompt)

                        # 重置连续失败计数
                        self.consecutive_failures = 0

                        # 回到规划状态
                        state = LoopPhase.PLANNING
                        turn_retries += 1

                        if turn_retries > self.MAX_TURN_RETRIES:
                            # 超过重试次数，强制总结
                            state = LoopPhase.FINAL_SUMMARY

                elif state == LoopPhase.FINAL_SUMMARY:
                    # 强制获取最终总结
                    summary = await self._get_final_summary(context)
                    loop_result.result = summary
                    loop_result.status = LoopStatus.COMPLETED
                    state = LoopPhase.DONE

            # 超过最大步数
            if step_num >= self.max_steps and loop_result.status != LoopStatus.WAITING_FOR_APPROVAL:
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

        except RetryExhaustedError as e:
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

    async def _call_llm(self, context: LoopContext) -> LLMResponse:
        """
        调用 LLM（使用原生工具调用）

        Args:
            context: 执行上下文

        Returns:
            LLMResponse: LLM 响应
        """
        tools = self.tool_definitions.for_context(context)
        messages = self.message_builder.build(context, tools)

        # 流式调用 LLM，并在接收内容时持续推送到前端
        content_parts = []
        tool_calls = []
        finish_reason = "stop"

        async for chunk in self.llm.stream_complete(messages, tools):
            if chunk.type == "content" and chunk.content:
                content_parts.append(chunk.content)
                await self._emit("llm:content", {"content": chunk.content})
            elif chunk.type == "tool_calls":
                tool_calls = chunk.tool_calls
                finish_reason = chunk.finish_reason or "tool_calls"
                break
            elif chunk.type == "done":
                finish_reason = chunk.finish_reason or "stop"
                break
            elif chunk.type == "error":
                raise RuntimeError(chunk.error or "LLM 流式调用失败")

        response = LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=self.llm.get_model_name(),
        )

        # 记录到上下文
        if response.has_content or response.has_tool_calls:
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

    async def _get_final_summary(self, context: LoopContext) -> str:
        """
        获取最终回答

        Args:
            context: 执行上下文

        Returns:
            str: 最终回答内容
        """
        # 添加最终回答请求
        context.add_message("user", self.prompt_manager.get_final_response_prompt(context.task))

        tools = self.tool_definitions.for_context(context)
        messages = self.message_builder.build(context, tools)

        try:
            # 流式获取总结
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

        except RetryExhaustedError:
            raise
        except Exception as e:
            logger.error("获取总结失败: %s", e)

        # Fallback: 生成简单总结
        steps_count = len(context.steps)
        fallback = f"任务执行完成，共执行了 {steps_count} 个步骤。"
        return fallback

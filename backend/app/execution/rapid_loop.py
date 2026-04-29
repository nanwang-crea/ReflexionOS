import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from app.config.settings import config_manager
from app.execution.context_manager import LoopContext
from app.execution.models import LoopResult, LoopStatus, LoopStep, StepStatus
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMMessage, LLMResponse, LLMToolCall, UniversalLLMInterface
from app.llm.retry import RetryExhaustedError
from app.tools.plan_tool import PlanTool
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
    MAX_TURN_RETRIES = 2      # 每轮最大重试
    MAX_SUMMARY_RETRIES = 2   # 总结最大重试
    MAX_ERROR_RETRIES = 2     # 错误恢复最大重试
    MAX_CONTEXT_GROUPS = 10   # 最近上下文分组数，保证 tool_call 与 tool 输出成组保留
    
    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int = None,
        event_callback: Callable[[str, dict], Awaitable[None]] = None
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps or config_manager.settings.execution.max_steps
        self.prompt_manager = PromptManager()
        self.event_callback = event_callback
        
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
            created_at=created_at or datetime.now()
        )
        
        context = LoopContext(
            task=task,
            project_path=project_path,
            run_id=loop_result.id
        )

        allowed_seed_roles = {"user", "assistant", "tool"}
        for seeded in seed_messages or []:
            if not isinstance(seeded, dict):
                continue
            role = str(seeded.get("role") or "").strip().lower()
            if role not in allowed_seed_roles:
                continue
            content = seeded.get("content")
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue
            context.add_message(role, content)
        context.supplemental_context = supplemental_context
        context.system_sections = system_sections or []
        context.add_message("user", task)

        # 发送开始事件
        await self._emit("run:start", {
            "run_id": loop_result.id,
            "task": task
        })
        
        logger.info("开始执行任务: %s", task)
        
        try:
            state = LoopPhase.PLANNING
            step_num = 0
            turn_retries = 0
            
            while state != LoopPhase.DONE and step_num < self.max_steps:
                
                if state == LoopPhase.PLANNING:
                    # 调用 LLM 决策
                    response = await self._call_llm(context)

                    # 检查是否有工具调用
                    if response.has_tool_calls:
                        # 首次工具调用且没有 plan → 轻量提醒，引导模型先规划
                        if (
                            not self.has_executed_tools
                            and context.plan is None
                            and not any(tc.name == "plan" for tc in response.tool_calls)
                        ):
                            context.add_message(
                                "system",
                                "这是一个多步骤任务，建议先调用 plan.create 规划步骤再执行，"
                                "这样你的进度和发现会被追踪并传递给下一步。"
                                "如果认为任务足够简单可以直接完成，也可以跳过规划。",
                            )
                            response = await self._call_llm(context)

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
                        step = await self._execute_tool(tool_call, context, step_num)
                        loop_result.steps.append(step)
                        context.add_step(step)
                        
                        if step.status == StepStatus.FAILED:
                            self.consecutive_failures += 1
                            
                            # 发送工具失败事件
                            await self._emit("tool:error", {
                                "tool_name": tool_call.name,
                                "error": step.error,
                                "step_number": step_num
                            })
                            
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
                            code_snippet=""
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
            if step_num >= self.max_steps:
                loop_result.status = LoopStatus.COMPLETED
                loop_result.result = loop_result.result or "执行完成（达到最大步数）"
                logger.warning("执行达到最大步数")
        
        except asyncio.CancelledError:
            loop_result.status = LoopStatus.CANCELLED
            loop_result.result = loop_result.result or "执行已取消"
            logger.info("执行已取消: %s", loop_result.id)

            await self._emit("run:cancelled", {
                "status": loop_result.status.value,
                "result": loop_result.result,
                "total_steps": len(loop_result.steps)
            })

        except RetryExhaustedError as e:
            loop_result.status = LoopStatus.CANCELLED
            loop_result.result = "执行已取消：LLM 重试次数已达上限"
            logger.warning("LLM 重试次数已达上限，取消执行: %s", e)

            await self._emit("run:cancelled", {
                "status": loop_result.status.value,
                "result": loop_result.result,
                "total_steps": len(loop_result.steps),
                "reason": "llm_retry_exhausted",
                "error": str(e.last_exception),
            })

        except Exception as e:
            import traceback
            loop_result.status = LoopStatus.FAILED
            loop_result.result = f"执行异常: {str(e)}"
            logger.error("执行异常: %s\n%s", e, traceback.format_exc())
            
            await self._emit("run:error", {
                "error": str(e)
            })
        
        finally:
            loop_result.total_duration = time.time() - start_time
            loop_result.completed_at = datetime.now()
            
            # 发送完成事件
            if loop_result.status != LoopStatus.CANCELLED:
                await self._emit("run:complete", {
                    "status": loop_result.status.value,
                    "result": loop_result.result,
                    "total_steps": len(loop_result.steps),
                    "duration": loop_result.total_duration
                })
        
        return loop_result
    
    async def _call_llm(self, context: LoopContext) -> LLMResponse:
        """
        调用 LLM（使用原生工具调用）
        
        Args:
            context: 执行上下文
            
        Returns:
            LLMResponse: LLM 响应
        """
        # 构建消息
        messages = self._build_messages(context)
        
        # 获取工具定义
        tools = self.tool_registry.get_tool_definitions()
        
        # 流式调用 LLM，并在接收内容时持续推送到前端
        content_parts = []
        tool_calls = []
        finish_reason = "stop"

        async for chunk in self.llm.stream_complete(messages, tools):
            if chunk.type == "content" and chunk.content:
                content_parts.append(chunk.content)
                await self._emit("llm:content", {
                    "content": chunk.content
                })
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
            model=self.llm.get_model_name()
        )
        
        # 记录到上下文
        if response.has_content or response.has_tool_calls:
            context.add_message(
                "assistant",
                content=response.content or None,
                tool_calls=[tool_call.model_dump() for tool_call in response.tool_calls]
            )
        
        logger.info(
            "LLM 响应: %s | tool_calls: %s",
            response.content[:50] if response.content else "(无内容)",
            [tc.name for tc in response.tool_calls],
        )
        
        return response
    
    def _build_messages(self, context: LoopContext) -> list[LLMMessage]:
        """构建消息列表"""
        messages = []
        
        # 系统提示
        system_prompt = self._get_system_prompt()
        messages.append(LLMMessage(role="system", content=system_prompt))

        # Task 6: layered system context sections (AGENTS/USER/MEMORY/etc.)
        for section in getattr(context, "system_sections", []) or []:
            if str(section or "").strip():
                messages.append(LLMMessage(role="system", content=str(section)))

        # Task 6: supplemental context block (e.g., continuation artifact handoff)
        supplemental = getattr(context, "supplemental_context", None)
        if supplemental and str(supplemental).strip():
            messages.append(LLMMessage(role="system", content=str(supplemental).strip()))

        # Plan state — always injected, never truncated by message window
        if context.plan:
            messages.append(LLMMessage(role="system", content=context.plan.render_for_context()))
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                messages.append(LLMMessage(role="system", content=f"前序步骤发现:\n{findings_text}"))

        # 历史消息
        for msg in self._get_recent_context_messages(context):
            tool_calls = [
                LLMToolCall(**tool_call)
                for tool_call in msg.get("tool_calls", [])
            ]
            messages.append(LLMMessage(
                role=msg["role"],
                content=msg.get("content"),
                tool_calls=tool_calls,
                tool_call_id=msg.get("tool_call_id")
            ))
        
        return messages

    def _get_recent_context_messages(self, context: LoopContext) -> list[dict]:
        """
        获取最近的上下文消息。

        这里不能直接按消息条数截断，否则一次 assistant 工具调用产生的多条
        tool 消息可能被保留下来，但对应的 assistant/tool_calls 消息被截掉，
        从而让下游模型在处理 tool_call_id 时无法配对。
        """
        if not context.messages:
            return []

        grouped_messages: list[list[dict]] = []
        active_tool_group: list[dict] | None = None

        for msg in context.messages:
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                active_tool_group = [msg]
                grouped_messages.append(active_tool_group)
                continue

            if msg["role"] == "tool" and active_tool_group is not None:
                active_tool_group.append(msg)
                continue

            active_tool_group = None
            grouped_messages.append([msg])

        recent_groups = grouped_messages[-self.MAX_CONTEXT_GROUPS:]
        return [
            message
            for group in recent_groups
            for message in group
        ]
    
    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        tools = self.tool_registry.get_tool_definitions()
        return self.prompt_manager.get_system_prompt(tools)
    
    async def _execute_tool(
        self,
        tool_call: LLMToolCall,
        context: LoopContext,
        step_number: int
    ) -> LoopStep:
        """
        执行工具调用
        
        Args:
            tool_call: 工具调用
            context: 执行上下文
            step_number: 步骤编号
            
        Returns:
            LoopStep: 执行步骤
        """
        step = LoopStep(
            id=f"step-{uuid.uuid4().hex[:8]}",
            step_number=step_number,
            tool=tool_call.name,
            args=tool_call.arguments,
            status=StepStatus.RUNNING
        )
        
        start_time = time.time()
        
        # 发送工具开始事件
        await self._emit("tool:start", {
            "tool_name": tool_call.name,
            "arguments": tool_call.arguments,
            "step_number": step_number
        })
        
        try:
            # 获取工具
            tool = self.tool_registry.get(tool_call.name)
            
            if not tool:
                raise ValueError(f"工具不存在: {tool_call.name}")
            
            # 执行工具
            result = await tool.execute(tool_call.arguments)
            
            # 更新步骤状态
            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time
            
            # 更新上下文
            tool_output = result.output or result.error or ""
            context.update_history(tool_call, tool_output)
            context.add_message(
                "tool",
                content=tool_output,
                tool_call_id=tool_call.id
            )
            
            # 发送工具结果事件
            await self._emit("tool:result", {
                "tool_name": tool_call.name,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "duration": step.duration
            })

            # Sync plan state from PlanTool → LoopContext + emit plan event
            if isinstance(tool, PlanTool) and tool.get_plan() is not None:
                context.plan = tool.get_plan()
                await self._emit("plan:updated", context.plan.to_dict())
            
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
                tool_call_id=tool_call.id
            )
            
            await self._emit("tool:error", {
                "tool_name": tool_call.name,
                "error": str(e)
            })
        
        return step
    
    async def _get_final_summary(self, context: LoopContext) -> str:
        """
        获取最终回答
        
        Args:
            context: 执行上下文
            
        Returns:
            str: 最终回答内容
        """
        # 添加最终回答请求
        context.add_message(
            "user",
            self.prompt_manager.get_final_response_prompt(context.task)
        )
        
        # 调用 LLM
        messages = self._build_messages(context)

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

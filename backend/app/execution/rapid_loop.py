import time
from typing import Optional, Callable, Awaitable
from datetime import datetime
import uuid
import logging
import asyncio

from app.llm.base import (
    UniversalLLMInterface,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    StreamChunk
)
from app.models.execution import Execution, ExecutionStep, ExecutionStatus, StepStatus
from app.execution.context_manager import ExecutionContext
from app.execution.prompt_manager import PromptManager
from app.tools.registry import ToolRegistry
from app.config.settings import config_manager

logger = logging.getLogger(__name__)


# 执行状态
class ExecutionState:
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
                logger.error(f"事件回调失败: {e}")
    
    async def run(
        self,
        task: str,
        project_path: Optional[str] = None,
        execution_id: Optional[str] = None,
        created_at: Optional[datetime] = None
    ) -> Execution:
        """
        执行任务
        
        Args:
            task: 任务描述
            project_path: 项目路径
            
        Returns:
            Execution: 执行结果
        """
        start_time = time.time()
        
        execution = Execution(
            id=execution_id or f"exec-{uuid.uuid4().hex[:8]}",
            project_id=project_path or "standalone",
            task=task,
            status=ExecutionStatus.RUNNING,
            created_at=created_at or datetime.now()
        )
        
        context = ExecutionContext(
            task=task,
            project_path=project_path,
            execution_id=execution.id
        )
        
        # 发送开始事件
        await self._emit("execution:start", {
            "execution_id": execution.id,
            "task": task
        })
        
        logger.info(f"开始执行任务: {task}")
        
        try:
            state = ExecutionState.PLANNING
            step_num = 0
            turn_retries = 0
            
            while state != ExecutionState.DONE and step_num < self.max_steps:
                
                if state == ExecutionState.PLANNING:
                    # 调用 LLM 决策
                    response = await self._call_llm(context)
                    
                    # 检查是否有工具调用
                    if response.has_tool_calls:
                        if response.has_content:
                            await self._emit("llm:thought", {
                                "content": response.content
                            })

                        # 发送工具调用事件
                        for tc in response.tool_calls:
                            await self._emit("llm:tool_call", {
                                "tool_name": tc.name,
                                "arguments": tc.arguments,
                                "thought": response.content
                            })
                        
                        state = ExecutionState.TOOL_EXECUTION
                        turn_retries = 0
                    else:
                        # 没有工具调用
                        if self.has_executed_tools:
                            if response.has_content:
                                # 已经有可直接返回给用户的答案，不再强制进入总结
                                execution.status = ExecutionStatus.COMPLETED
                                execution.result = response.content
                                state = ExecutionState.DONE
                            else:
                                # 没有最终回答时，再进入兜底总结阶段
                                state = ExecutionState.FINAL_SUMMARY
                        else:
                            # 没执行过工具，直接完成
                            execution.status = ExecutionStatus.COMPLETED
                            execution.result = response.content or "任务完成"
                            state = ExecutionState.DONE
                
                elif state == ExecutionState.TOOL_EXECUTION:
                    step_num += 1
                    
                    # 执行所有工具调用
                    all_success = True
                    for tool_call in response.tool_calls:
                        step = await self._execute_tool(tool_call, context, step_num)
                        execution.steps.append(step)
                        context.add_step(step)
                        
                        if step.status == StepStatus.FAILED:
                            all_success = False
                            self.consecutive_failures += 1
                            
                            # 发送工具失败事件
                            await self._emit("tool:error", {
                                "tool_name": tool_call.name,
                                "error": step.error,
                                "step_number": step_num
                            })
                            
                            # 检查是否需要进入错误恢复
                            if self.consecutive_failures >= self.MAX_ERROR_RETRIES:
                                state = ExecutionState.ERROR_RECOVERY
                                break
                        else:
                            self.consecutive_failures = 0
                            self.has_executed_tools = True
                    
                    if state == ExecutionState.TOOL_EXECUTION:
                        # 工具执行完成，回到规划状态
                        state = ExecutionState.PLANNING
                
                elif state == ExecutionState.ERROR_RECOVERY:
                    # 错误恢复：给 LLM 错误信息，让它修正
                    last_step = execution.steps[-1] if execution.steps else None
                    
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
                        state = ExecutionState.PLANNING
                        turn_retries += 1
                        
                        if turn_retries > self.MAX_TURN_RETRIES:
                            # 超过重试次数，强制总结
                            state = ExecutionState.FINAL_SUMMARY
                
                elif state == ExecutionState.FINAL_SUMMARY:
                    # 强制获取最终总结
                    summary = await self._get_final_summary(context)
                    execution.result = summary
                    execution.status = ExecutionStatus.COMPLETED
                    state = ExecutionState.DONE
            
            # 超过最大步数
            if step_num >= self.max_steps:
                execution.status = ExecutionStatus.COMPLETED
                execution.result = execution.result or "执行完成（达到最大步数）"
                logger.warning("执行达到最大步数")
        
        except asyncio.CancelledError:
            execution.status = ExecutionStatus.CANCELLED
            execution.result = execution.result or "执行已取消"
            logger.info(f"执行已取消: {execution.id}")

            await self._emit("execution:cancelled", {
                "status": execution.status.value,
                "result": execution.result,
                "total_steps": len(execution.steps)
            })

        except Exception as e:
            import traceback
            execution.status = ExecutionStatus.FAILED
            execution.result = f"执行异常: {str(e)}"
            logger.error(f"执行异常: {str(e)}\n{traceback.format_exc()}")
            
            await self._emit("execution:error", {
                "error": str(e)
            })
        
        finally:
            execution.total_duration = time.time() - start_time
            execution.completed_at = datetime.now()
            
            # 发送完成事件
            if execution.status != ExecutionStatus.CANCELLED:
                await self._emit("execution:complete", {
                    "status": execution.status.value,
                    "result": execution.result,
                    "total_steps": len(execution.steps),
                    "duration": execution.total_duration
                })
        
        return execution
    
    async def _call_llm(self, context: ExecutionContext) -> LLMResponse:
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
        
        # 发送 LLM 开始事件
        await self._emit("llm:start", {})

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
            f"LLM 响应: "
            f"{response.content[:50] if response.content else '(无内容)'}"
            f" | tool_calls: {[tc.name for tc in response.tool_calls]}"
        )
        
        return response
    
    def _build_messages(self, context: ExecutionContext) -> list[LLMMessage]:
        """构建消息列表"""
        messages = []
        
        # 系统提示
        system_prompt = self._get_system_prompt()
        messages.append(LLMMessage(role="system", content=system_prompt))
        
        # 任务
        messages.append(LLMMessage(role="user", content=context.task))
        
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

    def _get_recent_context_messages(self, context: ExecutionContext) -> list[dict]:
        """
        获取最近的上下文消息。

        这里不能直接按消息条数截断，否则一次 assistant 工具调用产生的多条
        tool 消息可能被保留下来，但对应的 assistant/tool_calls 消息被截掉，
        从而让下游模型在处理 tool_call_id 时无法配对。
        """
        if not context.messages:
            return []

        grouped_messages: list[list[dict]] = []
        active_tool_group: Optional[list[dict]] = None

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
        context: ExecutionContext,
        step_number: int
    ) -> ExecutionStep:
        """
        执行工具调用
        
        Args:
            tool_call: 工具调用
            context: 执行上下文
            step_number: 步骤编号
            
        Returns:
            ExecutionStep: 执行步骤
        """
        step = ExecutionStep(
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
            
            logger.info(f"工具 {tool_call.name} 执行{'成功' if result.success else '失败'}")
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration = time.time() - start_time
            logger.error(f"工具执行异常: {str(e)}")

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
    
    async def _get_final_summary(self, context: ExecutionContext) -> str:
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
        
        await self._emit("summary:start", {})
        
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
                await self._emit("summary:complete", {"summary": summary})
                return summary
            
        except Exception as e:
            logger.error(f"获取总结失败: {e}")
        
        # Fallback: 生成简单总结
        steps_count = len(context.steps)
        fallback = f"任务执行完成，共执行了 {steps_count} 个步骤。"
        await self._emit("summary:complete", {"summary": fallback})
        return fallback

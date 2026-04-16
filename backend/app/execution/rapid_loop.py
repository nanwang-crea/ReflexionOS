import json
import time
from typing import Optional
from datetime import datetime
import uuid
import logging
import re

from app.llm.base import UniversalLLMInterface, Message
from app.models.action import Action, ToolCall
from app.models.execution import Execution, ExecutionStep, ExecutionStatus, StepStatus
from app.execution.context_manager import ExecutionContext
from app.execution.prompt_manager import PromptManager
from app.tools.registry import ToolRegistry
from app.config.settings import config_manager

logger = logging.getLogger(__name__)


class RapidExecutionLoop:
    """快速执行循环 - Agent 核心执行引擎
    
    OpenAI Assistant 风格：
    - content: 对用户说的话（思考过程/进度说明/结果总结）
    - tool_calls: 要执行的工具列表
    - 两者可以同时存在
    """
    
    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int = None
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps or config_manager.settings.execution.max_steps
        self.prompt_manager = PromptManager()
    
    async def run(self, task: str, project_path: Optional[str] = None) -> Execution:
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
            project_id=project_path or "standalone",
            task=task,
            status=ExecutionStatus.RUNNING
        )
        
        context = ExecutionContext(
            task=task,
            project_path=project_path,
            execution_id=execution.id
        )
        
        # 对话历史
        conversation: list[Message] = [
            Message(role="system", content=self.prompt_manager.get_system_prompt(
                list(self.tool_registry.tools.values())
            ))
        ]
        
        # 用户任务
        conversation.append(Message(role="user", content=task))
        
        logger.info(f"开始执行任务: {task}")
        
        final_message = ""
        last_action_had_tools = False
        
        try:
            step_num = 0
            while step_num < self.max_steps:
                step_num += 1
                
                # 调用 LLM
                action = await self.decide_action(conversation)
                
                # 记录 LLM 的回复内容
                if action.content:
                    final_message = action.content
                    context.add_message("assistant", action.content)
                    conversation.append(Message(role="assistant", content=action.content))
                
                # 检查是否完成（没有工具调用）
                if not action.has_tool_calls:
                    # 如果上一次有工具调用，这次没有，说明是最终总结
                    if last_action_had_tools or action.content:
                        execution.status = ExecutionStatus.COMPLETED
                        execution.result = final_message or "任务完成"
                        logger.info(f"任务完成: {execution.result}")
                        break
                    else:
                        # 没有工具调用也没有内容，可能是空响应，让 LLM 再试
                        conversation.append(Message(role="user", content="请总结你的发现并回复用户。"))
                        continue
                
                last_action_had_tools = True
                
                # 执行工具调用
                for tool_call in action.tool_calls:
                    step = await self.execute_tool_call(tool_call, context, step_num)
                    execution.steps.append(step)
                    context.add_step(step)
                    
                    # 将工具结果加入对话
                    if step.status == StepStatus.SUCCESS:
                        tool_result = f"Tool {tool_call.name} succeeded.\n{step.output or '(no output)'}"
                    else:
                        tool_result = f"Tool {tool_call.name} failed: {step.error}"
                        await self.handle_error(context, step)
                    
                    conversation.append(Message(role="user", content=tool_result))
            
            else:
                # 超过最大步数，强制获取总结
                conversation.append(Message(
                    role="user", 
                    content="已达到最大步数限制。请总结目前的发现并回复用户。"
                ))
                action = await self.decide_action(conversation)
                if action.content:
                    final_message = action.content
                
                execution.status = ExecutionStatus.COMPLETED
                execution.result = final_message or "执行完成"
                logger.warning("执行达到最大步数")
        
        except Exception as e:
            import traceback
            execution.status = ExecutionStatus.FAILED
            execution.result = f"执行异常: {str(e)}"
            logger.error(f"执行异常: {str(e)}\n{traceback.format_exc()}")
        
        finally:
            execution.total_duration = time.time() - start_time
            execution.completed_at = datetime.now()
        
        return execution
    
    async def decide_action(self, conversation: list[Message]) -> Action:
        """
        决定下一步动作
        
        Args:
            conversation: 对话历史
            
        Returns:
            Action: 决定的动作
        """
        # 调用 LLM
        response = await self.llm.complete(conversation)
        content = response.content.strip()
        
        # 解析为 Action
        action = self._parse_action(content)
        
        log_msg = f"LLM 回复"
        if action.content:
            log_msg += f": {action.content[:50]}{'...' if len(action.content) > 50 else ''}"
        if action.has_tool_calls:
            log_msg += f" | 工具调用: {[tc.name for tc in action.tool_calls]}"
        logger.info(log_msg)
        
        return action
    
    def _parse_action(self, content: str) -> Action:
        """解析 LLM 输出为 Action"""
        
        # 尝试提取 JSON
        json_str = self._extract_json(content)
        
        if json_str:
            try:
                data = json.loads(json_str)
                return self._create_action_from_dict(data)
            except json.JSONDecodeError:
                pass
        
        # 无法解析为 JSON，作为纯文本回复
        return Action(content=content)
    
    def _extract_json(self, content: str) -> Optional[str]:
        """从内容中提取 JSON"""
        content = content.strip()
        
        # 尝试直接解析
        if content.startswith('{') and content.endswith('}'):
            return content
        
        # 尝试提取 ```json ... ``` 块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试找到第一个 { 和最后一个 }
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            return content[start:end+1]
        
        return None
    
    def _create_action_from_dict(self, data: dict) -> Action:
        """从字典创建 Action，兼容多种格式"""
        
        content = data.get('content') or data.get('message') or data.get('text')
        thought = data.get('thought') or data.get('thinking')
        
        tool_calls = []
        
        # 解析 tool_calls（多种格式兼容）
        raw_tool_calls = data.get('tool_calls') or data.get('tools') or []
        
        # 单个工具调用
        if not raw_tool_calls:
            if 'tool' in data or 'name' in data:
                raw_tool_calls = [data]
        
        for tc in raw_tool_calls:
            name = tc.get('name') or tc.get('tool') or tc.get('function')
            args = tc.get('args') or tc.get('arguments') or tc.get('input') or {}
            if name:
                tool_calls.append(ToolCall(name=name, args=args))
        
        return Action(
            content=content,
            tool_calls=tool_calls,
            thought=thought
        )
    
    async def execute_tool_call(
        self,
        tool_call: ToolCall,
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
            args=tool_call.args,
            status=StepStatus.RUNNING
        )
        
        start_time = time.time()
        
        try:
            # 获取工具
            tool = self.tool_registry.get(tool_call.name)
            
            if not tool:
                raise ValueError(f"工具不存在: {tool_call.name}")
            
            # 执行工具
            result = await tool.execute(tool_call.args)
            
            # 更新步骤状态
            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time
            
            # 更新上下文
            context.update_history(tool_call, result.output or result.error or "")
            
            logger.info(f"工具 {tool_call.name} 执行{'成功' if result.success else '失败'}")
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration = time.time() - start_time
            logger.error(f"工具执行异常: {str(e)}")
        
        return step
    
    async def handle_error(self, context: ExecutionContext, step: ExecutionStep) -> None:
        """处理错误"""
        error_message = self.prompt_manager.get_error_prompt(
            error=step.error or "Unknown error",
            tool=step.tool,
            code_snippet=""
        )
        context.metadata["last_error"] = error_message
        logger.warning(f"处理错误: {step.error}")

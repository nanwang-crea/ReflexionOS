import json
import time
from typing import Optional, List
from datetime import datetime
import uuid
import logging

from app.llm.base import UniversalLLMInterface, Message
from app.models.action import Action, ActionType
from app.models.execution import Execution, ExecutionStep, ExecutionStatus, StepStatus
from app.execution.context_manager import ExecutionContext
from app.execution.prompt_manager import PromptManager
from app.tools.registry import ToolRegistry
from app.config.settings import config_manager

logger = logging.getLogger(__name__)


class RapidExecutionLoop:
    """快速执行循环 - Agent 核心执行引擎"""
    
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
        
        logger.info(f"开始执行任务: {task}")
        
        try:
            for step_num in range(1, self.max_steps + 1):
                # 决策下一步动作
                action = await self.decide_action(context)
                
                # 检查是否完成
                if action.type == ActionType.FINISH:
                    execution.status = ExecutionStatus.COMPLETED
                    execution.result = str(action.confidence)
                    logger.info(f"任务完成: {action.confidence}")
                    break
                
                # 执行动作
                step = await self.execute_action(action, context, step_num)
                execution.steps.append(step)
                context.add_step(step)
                
                # 处理错误
                if step.status == StepStatus.FAILED and step.error:
                    await self.handle_error(context, step)
            
            else:
                # 超过最大步数
                execution.status = ExecutionStatus.FAILED
                execution.result = "超过最大步数限制"
                logger.warning("执行超过最大步数限制")
        
        except Exception as e:
            execution.status = ExecutionStatus.FAILED
            execution.result = str(e)
            logger.error(f"执行异常: {str(e)}")
        
        finally:
            execution.total_duration = time.time() - start_time
            execution.completed_at = datetime.now()
        
        return execution
    
    async def decide_action(self, context: ExecutionContext) -> Action:
        """
        决定下一步动作
        
        Args:
            context: 执行上下文
            
        Returns:
            Action: 决定的动作
        """
        # 构建消息
        system_prompt = self.prompt_manager.get_system_prompt(
            list(self.tool_registry.tools.values())
        )
        step_prompt = self.prompt_manager.get_step_prompt(context)
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=step_prompt)
        ]
        
        # 调用LLM
        response = await self.llm.complete(messages)
        
        # 解析响应
        try:
            action_data = json.loads(response.content)
            action = Action(**action_data)
            logger.info(f"LLM 决策: {action.type} - {action.tool or 'finish'}")
            return action
        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应失败: {str(e)}")
            return Action(
                type=ActionType.FINISH,
                thought="解析失败",
                confidence=0.0
            )
        except Exception as e:
            logger.error(f"创建 Action 失败: {str(e)}")
            return Action(
                type=ActionType.FINISH,
                thought="创建失败",
                confidence=0.0
            )
    
    async def execute_action(
        self,
        action: Action,
        context: ExecutionContext,
        step_number: int
    ) -> ExecutionStep:
        """
        执行动作
        
        Args:
            action: 要执行的动作
            context: 执行上下文
            step_number: 步骤编号
            
        Returns:
            ExecutionStep: 执行步骤
        """
        step = ExecutionStep(
            id=f"step-{uuid.uuid4().hex[:8]}",
            step_number=step_number,
            tool=action.tool or "",
            args=action.args,
            status=StepStatus.RUNNING
        )
        
        start_time = time.time()
        
        try:
            # 获取工具
            tool = self.tool_registry.get(action.tool)
            
            if not tool:
                raise ValueError(f"工具不存在: {action.tool}")
            
            # 执行工具
            result = await tool.execute(action.args)
            
            # 更新步骤状态
            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time
            
            # 更新上下文
            context.update_history(action, result.output or result.error or "")
            
            logger.info(f"步骤 {step_number} 执行{'成功' if result.success else '失败'}: {action.tool}")
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration = time.time() - start_time
            logger.error(f"步骤 {step_number} 执行异常: {str(e)}")
        
        return step
    
    async def handle_error(self, context: ExecutionContext, step: ExecutionStep) -> None:
        """
        处理错误
        
        Args:
            context: 执行上下文
            step: 失败的步骤
        """
        error_message = self.prompt_manager.get_error_prompt(
            error=step.error or "Unknown error",
            tool=step.tool,
            code_snippet=""
        )
        
        context.metadata["last_error"] = error_message
        logger.warning(f"处理错误: {step.error}")

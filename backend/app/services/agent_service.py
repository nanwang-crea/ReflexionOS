from typing import Dict, Optional
from app.models.execution import Execution, ExecutionCreate
from app.models.llm_config import LLMConfig, LLMProvider
from app.execution.rapid_loop import RapidExecutionLoop
from app.tools.registry import ToolRegistry
from app.tools.file_tool import FileTool
from app.tools.shell_tool import ShellTool
from app.tools.patch_tool import PatchTool
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity
from app.llm import LLMAdapterFactory
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentService:
    """Agent 执行服务"""
    
    def __init__(self):
        self.executions: Dict[str, Execution] = {}
        self.tool_registry = self._init_tool_registry()
        self.llm_config: Optional[LLMConfig] = None
    
    def _init_tool_registry(self) -> ToolRegistry:
        """初始化工具注册中心"""
        registry = ToolRegistry()
        
        path_security = PathSecurity(["/tmp"])
        shell_security = ShellSecurity()
        
        registry.register(FileTool(path_security))
        registry.register(ShellTool(shell_security))
        registry.register(PatchTool(path_security))
        
        logger.info("工具注册中心初始化完成")
        return registry
    
    def set_llm_config(self, config: LLMConfig) -> None:
        """设置 LLM 配置"""
        self.llm_config = config
        logger.info(f"设置 LLM 配置: {config.provider} - {config.model}")
    
    def get_llm_config(self) -> Optional[LLMConfig]:
        """获取 LLM 配置"""
        return self.llm_config
    
    async def execute_task(self, execution_create: ExecutionCreate) -> Execution:
        """执行任务"""
        if not self.llm_config:
            raise ValueError("LLM 配置未设置，请先在设置页面配置 API Key")
        
        llm = LLMAdapterFactory.create(self.llm_config)
        
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self.tool_registry
        )
        
        project_path = execution_create.project_id
        if project_path and Path(project_path).exists():
            path_security = PathSecurity([project_path])
            if "file" in self.tool_registry.tools:
                self.tool_registry.tools["file"].security = path_security
            if "patch" in self.tool_registry.tools:
                self.tool_registry.tools["patch"].security = path_security
        
        execution = await execution_loop.run(
            task=execution_create.task,
            project_path=project_path
        )
        
        self.executions[execution.id] = execution
        
        logger.info(f"任务执行完成: {execution.id} - {execution.status}")
        return execution
    
    def get_execution(self, execution_id: str) -> Optional[Execution]:
        """获取执行结果"""
        return self.executions.get(execution_id)
    
    def list_executions(self, project_id: Optional[str] = None) -> list:
        """列出执行历史"""
        executions = list(self.executions.values())
        if project_id:
            executions = [e for e in executions if e.project_id == project_id]
        return executions


agent_service = AgentService()

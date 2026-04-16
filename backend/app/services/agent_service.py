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
from app.config.settings import config_manager, LLMSettings
from app.api.websocket import ws_manager
import logging
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class AgentService:
    """Agent 执行服务"""
    
    def __init__(self):
        self.executions: Dict[str, Execution] = {}
        self.tool_registry = self._init_tool_registry()
        self.llm_config: Optional[LLMConfig] = self._load_llm_config()
    
    def _init_tool_registry(self) -> ToolRegistry:
        """初始化工具注册中心"""
        registry = ToolRegistry()
        
        allowed_paths = [str(Path.cwd())]
        path_security = PathSecurity(allowed_paths, base_dir=str(Path.cwd()))
        shell_security = ShellSecurity()
        
        registry.register(FileTool(path_security))
        registry.register(ShellTool(shell_security, path_security))
        registry.register(PatchTool(path_security))
        
        logger.info(f"工具注册中心初始化完成, 允许路径: {allowed_paths}")
        return registry

    def _load_llm_config(self) -> Optional[LLMConfig]:
        """从持久化配置加载 LLM 配置"""
        llm_settings = config_manager.settings.llm
        return LLMConfig(
            provider=LLMProvider(llm_settings.provider),
            model=llm_settings.model,
            api_key=llm_settings.api_key,
            base_url=llm_settings.base_url,
            temperature=llm_settings.temperature,
            max_tokens=llm_settings.max_tokens
        )

    def _persist_llm_config(self, config: LLMConfig) -> None:
        """持久化 LLM 配置"""
        config_manager.update_llm(
            LLMSettings(
                provider=config.provider.value,
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                max_tokens=config.max_tokens
            )
        )
    
    def set_llm_config(self, config: LLMConfig) -> None:
        """设置 LLM 配置"""
        existing_config = self.llm_config or self._load_llm_config()

        merged_config = LLMConfig(
            provider=config.provider,
            model=config.model,
            api_key=config.api_key or (existing_config.api_key if existing_config else None),
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )

        self.llm_config = merged_config
        self._persist_llm_config(merged_config)
        logger.info(f"设置 LLM 配置: {merged_config.provider} - {merged_config.model}")
    
    def get_llm_config(self) -> Optional[LLMConfig]:
        """获取 LLM 配置"""
        if not self.llm_config:
            self.llm_config = self._load_llm_config()
        return self.llm_config
    
    async def execute_task(self, execution_create: ExecutionCreate) -> Execution:
        """执行任务（同步模式，兼容旧接口）"""
        execution = await self.create_execution(execution_create)
        return await self.run_execution(execution.id)
    
    async def create_execution(self, execution_create: ExecutionCreate) -> Execution:
        """创建执行任务"""
        execution = Execution(
            project_id=execution_create.project_id or "standalone",
            task=execution_create.task
        )
        
        # 更新路径安全配置
        project_path = execution_create.project_id
        if project_path and Path(project_path).exists():
            current_allowed = self.tool_registry.tools.get("file").security.allowed_base_paths if "file" in self.tool_registry.tools else []
            allowed_paths = list(set(current_allowed + [str(Path(project_path).resolve())]))
            path_security = PathSecurity(allowed_paths, base_dir=project_path)
            
            if "file" in self.tool_registry.tools:
                self.tool_registry.tools["file"].security = path_security
            if "patch" in self.tool_registry.tools:
                self.tool_registry.tools["patch"].security = path_security
            if "shell" in self.tool_registry.tools:
                self.tool_registry.tools["shell"].path_security = path_security
            
            logger.info(f"更新允许路径: {allowed_paths}")
        
        self.executions[execution.id] = execution
        return execution
    
    async def run_execution(self, execution_id: str) -> Execution:
        """运行执行任务"""
        execution = self.executions.get(execution_id)
        if not execution:
            raise ValueError(f"执行不存在: {execution_id}")
        
        if not self.llm_config or not self.llm_config.api_key:
            raise ValueError("LLM 配置未设置，请先在设置页面配置 API Key")
        
        llm = LLMAdapterFactory.create(self.llm_config)
        
        # 创建事件回调（推送到 WebSocket）
        async def event_callback(event_type: str, data: dict):
            await ws_manager.send_event(execution_id, event_type, data)
        
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self.tool_registry,
            event_callback=event_callback
        )
        
        result = await execution_loop.run(
            task=execution.task,
            project_path=execution.project_id
        )
        
        # 更新执行记录
        self.executions[execution_id] = result
        
        logger.info(f"任务执行完成: {execution_id} - {result.status}")
        return result
    
    async def start_execution_async(self, execution_create: ExecutionCreate) -> str:
        """异步启动执行任务"""
        execution = await self.create_execution(execution_create)
        
        # 后台运行
        asyncio.create_task(self.run_execution(execution.id))
        
        return execution.id
    
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

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from openai import AsyncOpenAI

from app.api.websocket import ws_manager
from app.config.settings import config_manager
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm import LLMAdapterFactory
from app.models.execution import Execution, ExecutionCreate, ExecutionStatus
from app.models.llm_config import (
    DefaultLLMSelection,
    LLMSettings,
    ProviderConnectionTestResult,
    ProviderInstanceConfig,
    ProviderModelConfig,
    ProviderType,
    ResolvedLLMConfig,
)
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity
from app.storage.database import db
from app.storage.repositories.execution_repo import ExecutionRepository
from app.storage.repositories.project_repo import ProjectRepository
from app.tools.file_tool import FileTool
from app.tools.patch_tool import PatchTool
from app.tools.registry import ToolRegistry
from app.tools.shell_tool import ShellTool

logger = logging.getLogger(__name__)


class AgentService:
    """Agent 执行服务"""

    def __init__(
        self,
        execution_repo: Optional[ExecutionRepository] = None,
        project_repo: Optional[ProjectRepository] = None,
    ):
        self.executions: Dict[str, Execution] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.execution_repo = execution_repo or ExecutionRepository(db)
        self.project_repo = project_repo or ProjectRepository(db)
        self.tool_registry = self._init_tool_registry()
        self.llm_settings = self._load_llm_settings()

    def _persist_execution(self, execution: Execution) -> Execution:
        self.execution_repo.save(execution)
        self.executions[execution.id] = execution
        return execution

    def _load_execution(self, execution_id: str) -> Optional[Execution]:
        execution = self.executions.get(execution_id)
        if execution is not None:
            return execution

        execution = self.execution_repo.get(execution_id)
        if execution is not None:
            self.executions[execution.id] = execution
        return execution

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

    def _load_llm_settings(self) -> LLMSettings:
        """从持久化配置加载 LLM 设置"""
        return self._normalize_settings(config_manager.settings.llm)

    def _persist_llm_settings(self, settings: LLMSettings) -> None:
        """持久化 LLM 设置"""
        normalized = self._normalize_settings(settings)
        self.llm_settings = normalized
        config_manager.update_llm(normalized)

    def _available_models(self, provider: ProviderInstanceConfig) -> list[ProviderModelConfig]:
        return [model for model in provider.models if model.enabled]

    def _normalize_model(self, model: ProviderModelConfig) -> ProviderModelConfig:
        model_id = model.id.strip() if model.id else ""
        display_name = model.display_name.strip()
        model_name = model.model_name.strip()

        if not display_name:
            raise ValueError("模型显示名称不能为空")
        if not model_name:
            raise ValueError("模型名称不能为空")

        return ProviderModelConfig(
            id=model_id or f"model-{uuid4().hex[:8]}",
            display_name=display_name,
            model_name=model_name,
            enabled=model.enabled,
        )

    def _normalize_provider(self, provider: ProviderInstanceConfig) -> ProviderInstanceConfig:
        provider_id = provider.id.strip() if provider.id else ""
        name = provider.name.strip()
        if not name:
            raise ValueError("供应商名称不能为空")

        normalized_models: list[ProviderModelConfig] = []
        seen_model_ids: set[str] = set()

        for raw_model in provider.models:
            model = self._normalize_model(raw_model)
            if model.id in seen_model_ids:
                raise ValueError("同一个供应商下的模型 ID 不能重复")
            seen_model_ids.add(model.id)
            normalized_models.append(model)

        if not normalized_models:
            raise ValueError("请至少配置一个模型")

        enabled_models = [model for model in normalized_models if model.enabled]
        if provider.default_model_id and any(model.id == provider.default_model_id for model in normalized_models):
            default_model_id = provider.default_model_id
        elif enabled_models:
            default_model_id = enabled_models[0].id
        else:
            default_model_id = normalized_models[0].id

        base_url = provider.base_url.strip() if provider.base_url else None
        api_key = provider.api_key.strip() if provider.api_key else None

        return ProviderInstanceConfig(
            id=provider_id or f"provider-{uuid4().hex[:8]}",
            name=name,
            provider_type=provider.provider_type,
            api_key=api_key or None,
            base_url=base_url or None,
            models=normalized_models,
            default_model_id=default_model_id,
            enabled=provider.enabled,
        )

    def _normalize_settings(self, settings: LLMSettings) -> LLMSettings:
        normalized_providers = [self._normalize_provider(provider) for provider in settings.providers]

        normalized = LLMSettings(
            providers=normalized_providers,
            default_provider_id=settings.default_provider_id,
            default_model_id=settings.default_model_id,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

        available_providers = [
            provider for provider in normalized.providers
            if provider.enabled and self._available_models(provider)
        ]

        if not available_providers:
            normalized.default_provider_id = None
            normalized.default_model_id = None
            return normalized

        default_provider = next(
            (provider for provider in available_providers if provider.id == normalized.default_provider_id),
            available_providers[0]
        )
        available_models = self._available_models(default_provider)

        default_model = next(
            (model for model in available_models if model.id == normalized.default_model_id),
            None
        )
        if not default_model:
            default_model = next(
                (model for model in available_models if model.id == default_provider.default_model_id),
                available_models[0]
            )

        normalized.default_provider_id = default_provider.id
        normalized.default_model_id = default_model.id
        return normalized

    def _resolve_provider_model(
        self,
        provider: ProviderInstanceConfig,
        model_id: Optional[str],
        *,
        strict_model: bool,
        temperature: float,
        max_tokens: int,
    ) -> ResolvedLLMConfig:
        available_models = self._available_models(provider)
        if not available_models:
            raise ValueError("所选供应商没有可用模型")

        selected_model = None
        if model_id:
            selected_model = next((model for model in available_models if model.id == model_id), None)
            if not selected_model and strict_model:
                raise ValueError("所选模型不存在或已禁用")

        if not selected_model and provider.default_model_id:
            selected_model = next(
                (model for model in available_models if model.id == provider.default_model_id),
                None
            )

        if not selected_model:
            selected_model = available_models[0]

        return ResolvedLLMConfig(
            provider_id=provider.id,
            provider_type=provider.provider_type,
            model_id=selected_model.id,
            model=selected_model.model_name,
            api_key=provider.api_key,
            base_url=provider.base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def get_llm_settings(self) -> LLMSettings:
        """获取 LLM 设置"""
        self.llm_settings = self._load_llm_settings()
        return self.llm_settings

    def list_providers(self) -> list[ProviderInstanceConfig]:
        """列出供应商实例"""
        return self.get_llm_settings().providers

    def create_provider(self, provider: ProviderInstanceConfig) -> ProviderInstanceConfig:
        settings = self.get_llm_settings().model_copy(deep=True)
        normalized_provider = self._normalize_provider(provider)

        if any(existing.id == normalized_provider.id for existing in settings.providers):
            raise ValueError("供应商 ID 已存在")

        settings.providers.append(normalized_provider)
        self._persist_llm_settings(settings)
        return next(item for item in self.llm_settings.providers if item.id == normalized_provider.id)

    def update_provider(self, provider_id: str, provider: ProviderInstanceConfig) -> ProviderInstanceConfig:
        settings = self.get_llm_settings().model_copy(deep=True)
        target_index = next(
            (index for index, item in enumerate(settings.providers) if item.id == provider_id),
            None
        )
        if target_index is None:
            raise ValueError("供应商不存在")

        normalized_provider = self._normalize_provider(provider.model_copy(update={"id": provider_id}))
        settings.providers[target_index] = normalized_provider
        self._persist_llm_settings(settings)
        return next(item for item in self.llm_settings.providers if item.id == provider_id)

    def delete_provider(self, provider_id: str) -> None:
        settings = self.get_llm_settings().model_copy(deep=True)
        next_providers = [provider for provider in settings.providers if provider.id != provider_id]
        if len(next_providers) == len(settings.providers):
            raise ValueError("供应商不存在")

        settings.providers = next_providers
        self._persist_llm_settings(settings)

    def get_default_selection(self) -> DefaultLLMSelection:
        try:
            resolved = self.resolve_llm_config()
            return DefaultLLMSelection(
                provider_id=resolved.provider_id,
                model_id=resolved.model_id,
                configured=True,
            )
        except ValueError:
            settings = self.get_llm_settings()
            return DefaultLLMSelection(
                provider_id=settings.default_provider_id,
                model_id=settings.default_model_id,
                configured=False,
            )

    def set_default_selection(self, selection: DefaultLLMSelection) -> DefaultLLMSelection:
        if not selection.provider_id or not selection.model_id:
            raise ValueError("默认供应商和默认模型不能为空")

        settings = self.get_llm_settings().model_copy(deep=True)
        provider = next(
            (
                item for item in settings.providers
                if item.id == selection.provider_id and item.enabled
            ),
            None
        )
        if not provider:
            raise ValueError("默认供应商不存在或已禁用")

        if not any(model.id == selection.model_id and model.enabled for model in provider.models):
            raise ValueError("默认模型不存在或已禁用")

        settings.default_provider_id = selection.provider_id
        settings.default_model_id = selection.model_id
        self._persist_llm_settings(settings)
        return self.get_default_selection()

    async def test_provider_connection(
        self,
        provider: ProviderInstanceConfig,
        model_id: Optional[str] = None
    ) -> ProviderConnectionTestResult:
        settings = self.get_llm_settings()
        normalized_provider = self._normalize_provider(provider)
        resolved = self._resolve_provider_model(
            normalized_provider,
            model_id,
            strict_model=bool(model_id),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

        if resolved.provider_type != ProviderType.OPENAI_COMPATIBLE:
            raise ValueError("当前第一阶段仅支持 OpenAI-compatible 供应商的连接测试")

        client = AsyncOpenAI(
            api_key=resolved.api_key or "reflexion-placeholder-key",
            base_url=resolved.base_url if resolved.base_url else None
        )
        await client.chat.completions.create(
            model=resolved.model,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0,
            max_tokens=1,
        )

        return ProviderConnectionTestResult(
            provider_id=resolved.provider_id,
            provider_type=resolved.provider_type,
            model_id=resolved.model_id,
            model=resolved.model,
            message="连接测试成功",
        )

    def resolve_llm_config(
        self,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None
    ) -> ResolvedLLMConfig:
        settings = self.get_llm_settings()
        strict_provider = bool(provider_id)
        strict_model = bool(model_id)

        selected_provider = None
        if provider_id:
            selected_provider = next(
                (
                    provider for provider in settings.providers
                    if provider.id == provider_id and provider.enabled
                ),
                None
            )
            if not selected_provider and strict_provider:
                raise ValueError("所选供应商不存在或已禁用")

        if not selected_provider:
            if not settings.default_provider_id:
                raise ValueError("请先在设置页面配置默认供应商和默认模型")

            selected_provider = next(
                (
                    provider for provider in settings.providers
                    if provider.id == settings.default_provider_id and provider.enabled
                ),
                None
            )
            if not selected_provider:
                raise ValueError("默认供应商不存在或已禁用，请重新配置")

        selected_model_id = model_id
        if not selected_model_id and settings.default_provider_id == selected_provider.id:
            selected_model_id = settings.default_model_id

        return self._resolve_provider_model(
            selected_provider,
            selected_model_id,
            strict_model=strict_model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

    async def execute_task(self, execution_create: ExecutionCreate) -> Execution:
        """执行任务（同步模式）"""
        execution = await self.create_execution(execution_create)
        return await self.run_execution(execution.id)

    async def create_execution(self, execution_create: ExecutionCreate) -> Execution:
        """创建执行任务"""
        project = self.project_repo.get(execution_create.project_id)
        if not project:
            raise ValueError("项目不存在")

        project_path = project.path
        execution = Execution(
            project_id=project.id,
            project_path=project_path,
            task=execution_create.task,
            provider_id=execution_create.provider_id,
            model_id=execution_create.model_id,
        )

        if project_path and Path(project_path).exists():
            current_allowed = (
                self.tool_registry.tools.get("file").security.allowed_base_paths
                if "file" in self.tool_registry.tools else []
            )
            allowed_paths = list(set(current_allowed + [str(Path(project_path).resolve())]))
            path_security = PathSecurity(allowed_paths, base_dir=project_path)

            if "file" in self.tool_registry.tools:
                self.tool_registry.tools["file"].security = path_security
            if "patch" in self.tool_registry.tools:
                self.tool_registry.tools["patch"].security = path_security
            if "shell" in self.tool_registry.tools:
                self.tool_registry.tools["shell"].path_security = path_security

            logger.info(f"更新允许路径: {allowed_paths}")

        return self._persist_execution(execution)

    async def run_execution(self, execution_id: str) -> Execution:
        """运行执行任务"""
        execution = self._load_execution(execution_id)
        if not execution:
            raise ValueError(f"执行不存在: {execution_id}")

        resolved_llm = self.resolve_llm_config(execution.provider_id, execution.model_id)
        llm = LLMAdapterFactory.create(resolved_llm)

        execution.status = ExecutionStatus.RUNNING
        self._persist_execution(execution)

        async def event_callback(event_type: str, data: dict):
            await ws_manager.send_event(execution_id, event_type, data)

        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self.tool_registry,
            event_callback=event_callback
        )

        result = await execution_loop.run(
            task=execution.task,
            project_path=execution.project_path,
            execution_id=execution.id,
            created_at=execution.created_at
        )

        self._persist_execution(result)
        logger.info(
            "任务执行完成: %s - %s - provider=%s model=%s",
            execution_id,
            result.status,
            resolved_llm.provider_id,
            resolved_llm.model,
        )
        return result

    async def start_execution_async(self, execution_create: ExecutionCreate) -> str:
        """异步启动执行任务"""
        execution = await self.create_execution(execution_create)
        self.schedule_execution(execution.id)
        return execution.id

    async def _run_execution_task(self, execution_id: str) -> None:
        try:
            await self.run_execution(execution_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            execution = self._load_execution(execution_id)
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.result = str(exc)
                execution.completed_at = datetime.now()
                self._persist_execution(execution)

            logger.exception("执行任务失败: %s", execution_id)
            await ws_manager.send_event(execution_id, "execution:error", {
                "error": str(exc)
            })

    def schedule_execution(self, execution_id: str) -> asyncio.Task:
        """调度后台执行并跟踪运行中的任务"""
        task = asyncio.create_task(self._run_execution_task(execution_id))
        self.running_tasks[execution_id] = task

        def _cleanup(_: asyncio.Task) -> None:
            self.running_tasks.pop(execution_id, None)

        task.add_done_callback(_cleanup)
        return task

    async def cancel_execution(self, execution_id: str) -> Execution:
        """取消正在运行的执行任务"""
        execution = self._load_execution(execution_id)
        if not execution:
            raise ValueError(f"执行不存在: {execution_id}")

        if execution.status in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED
        }:
            return execution

        task = self.running_tasks.get(execution_id)
        if task and not task.done():
            task.cancel()
            await asyncio.sleep(0)
            execution = self._load_execution(execution_id) or execution
            if execution.status != ExecutionStatus.CANCELLED and task.done():
                execution.status = ExecutionStatus.CANCELLED
                execution.result = execution.result or "执行已取消"
                execution.completed_at = datetime.now()
                self._persist_execution(execution)

                await ws_manager.send_event(execution_id, "execution:cancelled", {
                    "status": execution.status.value,
                    "result": execution.result,
                    "total_steps": len(execution.steps),
                    "duration": execution.total_duration
                })

            return execution

        execution.status = ExecutionStatus.CANCELLED
        execution.result = execution.result or "执行已取消"
        execution.completed_at = datetime.now()
        self._persist_execution(execution)

        await ws_manager.send_event(execution_id, "execution:cancelled", {
            "status": execution.status.value,
            "result": execution.result,
            "total_steps": len(execution.steps),
            "duration": execution.total_duration
        })

        return execution

    def get_execution(self, execution_id: str) -> Optional[Execution]:
        """获取执行结果"""
        return self._load_execution(execution_id)

    def list_executions(self, project_id: Optional[str] = None) -> list[Execution]:
        """列出执行历史"""
        if project_id:
            return self.execution_repo.list_by_project(project_id)
        return self.execution_repo.list_all()


agent_service = AgentService()

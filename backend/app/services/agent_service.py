import asyncio
import contextlib
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from openai import AsyncOpenAI

from app.api.websocket import ws_manager
from app.config.settings import config_manager
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.models import Execution, ExecutionCreate, ExecutionStatus
from app.llm import LLMAdapterFactory
from app.models.conversation import ConversationEvent, MessageType, Run, RunStatus
from app.models.conversation_snapshot import StartTurnResult
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
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository
from app.tools.file_tool import FileTool
from app.tools.patch_tool import PatchTool
from app.tools.registry import ToolRegistry
from app.tools.shell_tool import ShellTool

from .conversation_runtime_adapter import ConversationRuntimeAdapter
from .conversation_service import ConversationService, conversation_service as default_conversation_service

logger = logging.getLogger(__name__)


_CANCEL_WAIT_ATTEMPTS = 10
_CANCEL_WAIT_INTERVAL_SECONDS = 0.01


class AgentService:
    """Agent 执行服务"""

    def __init__(
        self,
        project_repo: ProjectRepository | None = None,
        session_repo: SessionRepository | None = None,
        conversation_service: ConversationService | None = None,
        execution_repo=None,  # backward-compatible arg, no longer used
    ):
        self.running_tasks: dict[str, asyncio.Task] = {}
        self._run_metadata: dict[str, dict] = {}
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or default_conversation_service
        self.tool_registry = self._init_tool_registry()
        self.llm_settings = self._load_llm_settings()

    def _init_tool_registry(self) -> ToolRegistry:
        """初始化工具注册中心"""
        registry = ToolRegistry()

        allowed_paths = [str(Path.cwd())]
        path_security = PathSecurity(allowed_paths, base_dir=str(Path.cwd()))
        shell_security = ShellSecurity()

        registry.register(FileTool(path_security))
        registry.register(ShellTool(shell_security, path_security))
        registry.register(PatchTool(path_security))

        logger.info("工具注册中心初始化完成, 允许路径: %s", allowed_paths)
        return registry

    def _base_allowed_paths(self) -> list[str]:
        file_tool = self.tool_registry.get("file")
        if isinstance(file_tool, FileTool):
            return list(file_tool.security.allowed_base_paths)
        return [str(Path.cwd().resolve())]

    def _build_run_tool_registry(self, project_path: str | None) -> ToolRegistry:
        resolved_project_path = (
            str(Path(project_path).resolve())
            if project_path and Path(project_path).exists()
            else None
        )
        allowed_paths = list(
            dict.fromkeys(
                self._base_allowed_paths() + ([resolved_project_path] if resolved_project_path else [])
            )
        )
        base_dir = resolved_project_path or str(Path.cwd().resolve())
        path_security = PathSecurity(allowed_paths, base_dir=base_dir)

        registry = ToolRegistry()
        registry.register(FileTool(path_security))
        registry.register(ShellTool(ShellSecurity(), path_security))
        registry.register(PatchTool(path_security))

        logger.info("构建运行时工具注册中心, run_base_dir=%s, allowed_paths=%s", base_dir, allowed_paths)
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
        if provider.default_model_id and any(
            model.id == provider.default_model_id for model in normalized_models
        ):
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
        normalized_providers = [
            self._normalize_provider(provider) for provider in settings.providers
        ]

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
            (
                provider
                for provider in available_providers
                if provider.id == normalized.default_provider_id
            ),
            available_providers[0]
        )
        available_models = self._available_models(default_provider)

        default_model = next(
            (model for model in available_models if model.id == normalized.default_model_id),
            None
        )
        if not default_model:
            default_model = next(
                (
                    model
                    for model in available_models
                    if model.id == default_provider.default_model_id
                ),
                available_models[0]
            )

        normalized.default_provider_id = default_provider.id
        normalized.default_model_id = default_model.id
        return normalized

    def _resolve_provider_model(
        self,
        provider: ProviderInstanceConfig,
        model_id: str | None,
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
            selected_model = next(
                (model for model in available_models if model.id == model_id),
                None,
            )
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
        return next(
            item
            for item in self.llm_settings.providers
            if item.id == normalized_provider.id
        )

    def update_provider(
        self,
        provider_id: str,
        provider: ProviderInstanceConfig,
    ) -> ProviderInstanceConfig:
        settings = self.get_llm_settings().model_copy(deep=True)
        target_index = next(
            (index for index, item in enumerate(settings.providers) if item.id == provider_id),
            None
        )
        if target_index is None:
            raise ValueError("供应商不存在")

        normalized_provider = self._normalize_provider(
            provider.model_copy(update={"id": provider_id})
        )
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
        model_id: str | None = None
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
        provider_id: str | None = None,
        model_id: str | None = None
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

    async def start_turn(
        self,
        *,
        project_id: str,
        session_id: str,
        content: str,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> StartTurnResult:
        project = self.project_repo.get(project_id)
        if not project:
            raise ValueError("项目不存在")

        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("会话不存在")
        if session.project_id != project.id:
            raise ValueError("会话不属于当前项目")

        before_seq = session.last_event_seq
        resolved_llm = self.resolve_llm_config(provider_id, model_id)

        started = self.conversation_service.start_turn(
            session_id=session_id,
            content=content,
            provider_id=resolved_llm.provider_id,
            model_id=resolved_llm.model_id,
            workspace_ref=project.path,
        )

        self._run_metadata[started.run.id] = {
            "task": content,
            "project_id": project.id,
            "project_path": project.path,
            "provider_id": resolved_llm.provider_id,
            "model_id": resolved_llm.model_id,
            "session_id": session_id,
            "turn_id": started.turn.id,
        }
        seed_events = self.conversation_service.list_events_after(session_id, before_seq)
        await self._broadcast_conversation_events(
            session_id=session_id,
            events=seed_events,
        )
        self.schedule_turn(
            run_id=started.run.id,
            session_id=session_id,
            turn_id=started.turn.id,
            task=content,
            project_id=project.id,
            project_path=project.path,
            provider_id=resolved_llm.provider_id,
            model_id=resolved_llm.model_id,
        )
        return started

    def schedule_turn(
        self,
        *,
        run_id: str,
        session_id: str,
        turn_id: str,
        task: str,
        project_id: str,
        project_path: str,
        provider_id: str | None,
        model_id: str | None,
    ) -> asyncio.Task:
        running = self.running_tasks.get(run_id)
        if running is not None:
            return running

        execution_task = asyncio.create_task(
            self._run_turn(
                run_id=run_id,
                session_id=session_id,
                turn_id=turn_id,
                task=task,
                project_id=project_id,
                project_path=project_path,
                provider_id=provider_id,
                model_id=model_id,
            )
        )
        self.running_tasks[run_id] = execution_task

        def _cleanup(_: asyncio.Task) -> None:
            self.running_tasks.pop(run_id, None)

        execution_task.add_done_callback(_cleanup)
        return execution_task

    async def _broadcast_conversation_events(
        self,
        *,
        session_id: str,
        events: list[ConversationEvent],
    ) -> None:
        for event in events:
            await ws_manager.send_event(
                session_id,
                "conversation.event",
                event.model_dump(mode="json"),
            )

    async def _run_turn(
        self,
        *,
        run_id: str,
        session_id: str,
        turn_id: str,
        task: str,
        project_id: str,
        project_path: str,
        provider_id: str | None,
        model_id: str | None,
    ) -> None:
        resolved_llm = self.resolve_llm_config(provider_id, model_id)
        llm = LLMAdapterFactory.create(resolved_llm)
        runtime_adapter = ConversationRuntimeAdapter(
            conversation_service=self.conversation_service,
            session_id=session_id,
            turn_id=turn_id,
            run_id=run_id,
        )

        async def persist_and_broadcast(event_type: str, data: dict) -> None:
            persisted_events = runtime_adapter.handle_event(event_type, data)
            await self._broadcast_conversation_events(
                session_id=session_id,
                events=persisted_events,
            )

        async def event_callback(event_type: str, data: dict):
            await persist_and_broadcast(event_type, data)

        run_tool_registry = self._build_run_tool_registry(project_path)
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=run_tool_registry,
            event_callback=event_callback,
        )

        try:
            await execution_loop.run(
                task=task,
                project_path=project_path,
                execution_id=run_id,
                session_id=session_id,
                project_id=project_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("运行失败: run_id=%s", run_id)
            await persist_and_broadcast("execution:error", {"error": str(exc)})

    async def cancel_run(self, run_id: str) -> Run:
        running = self.running_tasks.get(run_id)
        if running is not None and not running.done():
            running.cancel()
            for _ in range(_CANCEL_WAIT_ATTEMPTS):
                if running.done():
                    break
                await asyncio.sleep(_CANCEL_WAIT_INTERVAL_SECONDS)
            with contextlib.suppress(asyncio.CancelledError):
                await running

        run = self.conversation_service.run_repo.get(run_id)
        if run is None:
            raise ValueError("运行不存在")
        if run.status in {RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED}:
            return run

        runtime_adapter = ConversationRuntimeAdapter(
            conversation_service=self.conversation_service,
            session_id=run.session_id,
            turn_id=run.turn_id,
            run_id=run_id,
        )
        persisted_events = runtime_adapter.handle_event("execution:cancelled", {})
        await self._broadcast_conversation_events(
            session_id=run.session_id,
            events=persisted_events,
        )

        cancelled = self.conversation_service.run_repo.get(run_id)
        if cancelled is None:
            raise ValueError("运行不存在")
        return cancelled

    async def execute_task(self, execution_create: ExecutionCreate) -> Execution:
        started = await self.start_turn(
            project_id=execution_create.project_id,
            session_id=execution_create.session_id,
            content=execution_create.task,
            provider_id=execution_create.provider_id,
            model_id=execution_create.model_id,
        )
        running = self.running_tasks.get(started.run.id)
        if running is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await running
        execution = self._execution_from_run(started.run.id, fallback_task=execution_create.task)
        if execution is None:
            raise ValueError(f"执行不存在: {started.run.id}")
        return execution

    async def create_execution(self, execution_create: ExecutionCreate) -> Execution:
        started = await self.start_turn(
            project_id=execution_create.project_id,
            session_id=execution_create.session_id,
            content=execution_create.task,
            provider_id=execution_create.provider_id,
            model_id=execution_create.model_id,
        )
        execution = self._execution_from_run(started.run.id, fallback_task=execution_create.task)
        if execution is None:
            raise ValueError(f"执行不存在: {started.run.id}")
        return execution

    async def run_execution(self, execution_id: str) -> Execution:
        running = self.running_tasks.get(execution_id)
        if running is not None and not running.done():
            with contextlib.suppress(asyncio.CancelledError):
                await running

        execution = self._execution_from_run(execution_id)
        if execution is None:
            raise ValueError(f"执行不存在: {execution_id}")
        return execution

    async def start_execution_async(self, execution_create: ExecutionCreate) -> str:
        started = await self.start_turn(
            project_id=execution_create.project_id,
            session_id=execution_create.session_id,
            content=execution_create.task,
            provider_id=execution_create.provider_id,
            model_id=execution_create.model_id,
        )
        return started.run.id

    def schedule_execution(self, execution_id: str) -> asyncio.Task:
        task = self.running_tasks.get(execution_id)
        if task is None:
            raise ValueError("执行不存在或已不支持单独调度，请使用 start_turn")
        return task

    async def cancel_execution(self, execution_id: str) -> Execution:
        await self.cancel_run(execution_id)
        execution = self._execution_from_run(execution_id)
        if execution is None:
            raise ValueError(f"执行不存在: {execution_id}")
        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        return self._execution_from_run(execution_id)

    def list_executions(self, project_id: str | None = None) -> list[Execution]:
        if project_id:
            projects = [project_id]
        else:
            projects = [project.id for project in self.project_repo.list_all()]

        executions: list[Execution] = []
        for pid in projects:
            sessions = self.session_repo.list_by_project(pid)
            for session in sessions:
                runs = self.conversation_service.run_repo.list_by_session(session.id)
                for run in runs:
                    execution = self._execution_from_run(run.id)
                    if execution is not None:
                        executions.append(execution)

        return sorted(executions, key=lambda item: item.created_at, reverse=True)

    def _execution_from_run(self, run_id: str, *, fallback_task: str | None = None) -> Execution | None:
        run = self.conversation_service.run_repo.get(run_id)
        if run is None:
            return None

        metadata = self._run_metadata.get(run_id, {})
        session = self.session_repo.get(run.session_id)
        project_id = metadata.get("project_id") or (session.project_id if session else "")
        project = self.project_repo.get(project_id) if project_id else None
        project_path = metadata.get("project_path") or (project.path if project else "")
        task = metadata.get("task") or fallback_task or self._task_from_run(run) or ""
        result = self._result_from_run(run)

        return Execution(
            id=run.id,
            project_id=project_id,
            session_id=run.session_id,
            project_path=project_path,
            task=task,
            provider_id=run.provider_id,
            model_id=run.model_id,
            status=self._execution_status_from_run(run.status),
            result=result,
            transcript_items=[],
            created_at=self._created_at_from_run(run),
            completed_at=run.finished_at,
        )

    def _task_from_run(self, run: Run) -> str | None:
        turn = self.conversation_service.turn_repo.get(run.turn_id)
        if turn is None:
            return None

        root_message = self.conversation_service.message_repo.get(turn.root_message_id)
        return root_message.content_text if root_message else None

    def _result_from_run(self, run: Run) -> str | None:
        if run.status == RunStatus.FAILED:
            return run.error_message

        messages = self.conversation_service.message_repo.list_by_turn(run.turn_id)
        assistant_messages = [
            message for message in messages
            if message.run_id == run.id and message.message_type == MessageType.ASSISTANT_MESSAGE
        ]
        if not assistant_messages:
            return None
        return assistant_messages[-1].content_text or run.error_message

    def _created_at_from_run(self, run: Run) -> datetime:
        turn = self.conversation_service.turn_repo.get(run.turn_id)
        if turn is None:
            return datetime.now()

        root_message = self.conversation_service.message_repo.get(turn.root_message_id)
        if root_message:
            return root_message.created_at
        if run.started_at:
            return run.started_at
        return datetime.now()

    def _execution_status_from_run(self, status: RunStatus) -> ExecutionStatus:
        return {
            RunStatus.CREATED: ExecutionStatus.PENDING,
            RunStatus.RUNNING: ExecutionStatus.RUNNING,
            RunStatus.COMPLETED: ExecutionStatus.COMPLETED,
            RunStatus.FAILED: ExecutionStatus.FAILED,
            RunStatus.CANCELLED: ExecutionStatus.CANCELLED,
        }[status]


agent_service = AgentService()

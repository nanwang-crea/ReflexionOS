import asyncio
import contextlib
import logging
from datetime import datetime
from pathlib import Path

from app.api.websocket import ws_manager
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.models import Execution, ExecutionCreate, ExecutionStatus
from app.llm import LLMAdapterFactory
from app.models.conversation import ConversationEvent, MessageType, Run, RunStatus
from app.models.conversation_snapshot import StartTurnResult
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
from .llm_provider_service import LLMProviderService, llm_provider_service as default_llm_provider_service

logger = logging.getLogger(__name__)


_CANCEL_WAIT_ATTEMPTS = 10
_CANCEL_WAIT_INTERVAL_SECONDS = 0.01
_EVENT_CLEANUP_INTERVAL_SECONDS = 300


class AgentService:
    """Agent 执行服务"""

    def __init__(
        self,
        project_repo: ProjectRepository | None = None,
        session_repo: SessionRepository | None = None,
        conversation_service: ConversationService | None = None,
        llm_provider_service: LLMProviderService | None = None,
        execution_repo=None,  # backward-compatible arg, no longer used
    ):
        self.running_tasks: dict[str, asyncio.Task] = {}
        self._runtime_adapters: dict[str, ConversationRuntimeAdapter] = {}
        self._run_metadata: dict[str, dict] = {}
        self._cleanup_task: asyncio.Task | None = None
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or default_conversation_service
        self.llm_provider_service = llm_provider_service or default_llm_provider_service
        self.tool_registry = self._init_tool_registry()

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
        resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)

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
            self._runtime_adapters.pop(run_id, None)

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

    async def _broadcast_conversation_live_event(
        self,
        *,
        session_id: str,
        data: dict,
    ) -> None:
        await ws_manager.send_event(
            session_id,
            "conversation.live_event",
            data,
        )

    def get_live_state(self, session_id: str) -> dict | None:
        for runtime_adapter in self._runtime_adapters.values():
            if runtime_adapter.session_id != session_id:
                continue
            live_state = runtime_adapter.get_live_state()
            if live_state is not None:
                return live_state
        return None

    def start_background_tasks(self, cleanup_interval_seconds: int = _EVENT_CLEANUP_INTERVAL_SECONDS) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(
            self._event_cleanup_loop(cleanup_interval_seconds),
            name="conversation-event-cleanup",
        )

    async def stop_background_tasks(self) -> None:
        cleanup_task = self._cleanup_task
        if cleanup_task is None:
            return
        self._cleanup_task = None
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task

    async def _event_cleanup_loop(self, cleanup_interval_seconds: int) -> None:
        while True:
            try:
                cleaned = self.conversation_service.cleanup_events()
                if cleaned:
                    logger.info("清理过期 conversation_events: deleted=%s", cleaned)
            except Exception:
                logger.exception("清理 conversation_events 失败")
            await asyncio.sleep(cleanup_interval_seconds)

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
        resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)
        llm = LLMAdapterFactory.create(resolved_llm)
        runtime_adapter = ConversationRuntimeAdapter(
            conversation_service=self.conversation_service,
            session_id=session_id,
            turn_id=turn_id,
            run_id=run_id,
        )
        self._runtime_adapters[run_id] = runtime_adapter

        async def persist_and_broadcast(event_type: str, data: dict) -> None:
            persisted_events = runtime_adapter.handle_event(event_type, data)
            live_event = runtime_adapter.build_live_event(event_type, data)
            if live_event is not None:
                await self._broadcast_conversation_live_event(
                    session_id=session_id,
                    data=live_event,
                )
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
        finally:
            self._runtime_adapters.pop(run_id, None)

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

        runtime_adapter = self._runtime_adapters.get(run_id)
        if runtime_adapter is None:
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

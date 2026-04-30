import asyncio
import contextlib
import logging
from pathlib import Path
from uuid import uuid4

from app.api.websocket import ws_manager
from app.execution.models import LoopStatus
from app.execution.prompt_manager import PromptManager
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm import LLMAdapterFactory
from app.llm.base import LLMMessage
from app.memory.context_assembly import ContextAssembler
from app.memory.continuation import build_continuation_artifact
from app.memory.continuation_builder import ContinuationArtifactBuilder
from app.models.conversation import ConversationEvent, Run, RunStatus
from app.models.conversation import EventType
from app.models.conversation_snapshot import StartTurnResult
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity
from app.storage.database import db
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository
from app.tools.file_tool import FileTool
from app.tools.memory_tool import MemoryTool
from app.tools.patch_tool import PatchTool
from app.tools.plan_tool import PlanTool
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
        self._cleanup_task: asyncio.Task | None = None
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or default_conversation_service
        self.llm_provider_service = llm_provider_service or default_llm_provider_service
        self.prompt_manager = PromptManager()
        self.context_assembler = ContextAssembler(conversation_service=self.conversation_service)
        self.continuation_builder = ContinuationArtifactBuilder()
    @staticmethod
    def _build_run_tool_registry(project_path: str | None) -> ToolRegistry:
        resolved_project_path = (
            str(Path(project_path).resolve())
            if project_path and Path(project_path).exists()
            else None
        )
        allowed_paths = list(
            dict.fromkeys(
                [str(Path.cwd().resolve())]
                + ([resolved_project_path] if resolved_project_path else [])
            )
        )
        base_dir = resolved_project_path or str(Path.cwd().resolve())
        path_security = PathSecurity(allowed_paths, base_dir=base_dir)

        registry = ToolRegistry()
        registry.register(FileTool(path_security))
        registry.register(ShellTool(ShellSecurity(), path_security))
        registry.register(PatchTool(path_security))
        registry.register(MemoryTool())
        registry.register(PlanTool())

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

        async def on_llm_retry(exc: Exception, attempt: int, delay: float) -> None:
            logger.warning(
                "LLM 请求失败 (%s)，第 %d/%d 次重试，%.1fs 后重试: %s",
                type(exc).__name__,
                attempt + 1,
                5,
                delay,
                exc,
            )
            await ws_manager.send_event(
                session_id,
                "llm:retry",
                {
                    "error_type": type(exc).__name__,
                    "attempt": attempt + 1,
                    "max_retries": 5,
                    "delay": round(delay, 1),
                    "message": str(exc),
                },
            )

        llm = LLMAdapterFactory.create(resolved_llm, on_retry=on_llm_retry)
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
            if event_type == "plan:updated":
                # Plan state is ephemeral per-run, only broadcast to frontend
                await ws_manager.send_event(session_id, "plan.updated", data)
            else:
                await persist_and_broadcast(event_type, data)

        run_tool_registry = self._build_run_tool_registry(project_path)
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=run_tool_registry,
            event_callback=event_callback,
        )

        try:
            # 该部分拿回来了最近的历史信息，同时也拿回了supplemental_block,这个也是从message拿到的
            assembly = self.context_assembler.build_for_session(
                session_id=session_id,
                project_id=project_id,
                project_path=project_path,
                current_turn_id=turn_id,
                current_user_input=task,
            )
            loop_result = await execution_loop.run(
                task=task,
                project_path=project_path,
                run_id=run_id,
                seed_messages=assembly.recent_messages,
                supplemental_context=assembly.supplemental_block,
                system_sections=assembly.system_sections,
            )
            if loop_result.status != LoopStatus.COMPLETED:
                return
            try:
                await self._generate_and_persist_continuation_artifact(
                    llm=llm,
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    task=task,
                )
            except Exception:
                # Best-effort: never fail an already-completed run due to continuation generation.
                logger.exception("Continuation artifact generation failed: run_id=%s", run_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("运行失败: run_id=%s", run_id)
            await persist_and_broadcast("run:error", {"error": str(exc)})
        finally:
            self._runtime_adapters.pop(run_id, None)

    async def _generate_and_persist_continuation_artifact(
        self,
        *,
        llm,
        session_id: str,
        turn_id: str,
        run_id: str,
        task: str,
    ) -> None:
        """
        Task 6: Replace heuristic continuation generation with a single LLM-driven compression step,
        then persist as a real system_notice message (collapsed + excluded from recall/memory promotion).
        """
        turn_messages = self.conversation_service.message_repo.list_by_turn(turn_id)
        prompt_input = self.continuation_builder.build_prompt_input(
            task=task,
            messages=turn_messages,
        )
        if not prompt_input.transcript:
            return

        system_prompt = self.prompt_manager.get_continuation_compression_system_prompt()
        prompt_input = self.prompt_manager.get_continuation_compression_prompt(
            task=prompt_input.task,
            transcript=prompt_input.transcript,
        )
        response = await llm.complete(
            [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=prompt_input),
            ],
            tools=None,
        )
        content = (getattr(response, "content", None) or "").strip()
        if not content:
            return

        next_index = self.conversation_service.message_repo.next_turn_message_index(turn_id)
        message_id = f"msg-cont-{uuid4().hex[:8]}"
        artifact = build_continuation_artifact(
            session_id=session_id,
            turn_id=turn_id,
            content_text=content,
            message_id=message_id,
            turn_message_index=next_index,
        )

        events = self.conversation_service.append_events(
            session_id,
            [
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=message_id,
                    event_type=EventType.MESSAGE_CREATED,
                    payload_json={
                        "message_id": artifact.id,
                        "turn_id": artifact.turn_id,
                        "run_id": artifact.run_id,
                        "role": artifact.role,
                        "message_type": artifact.message_type.value,
                        "turn_message_index": artifact.turn_message_index,
                        "display_mode": artifact.display_mode,
                        "content_text": artifact.content_text,
                        "payload_json": artifact.payload_json,
                    },
                ),
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=message_id,
                    event_type=EventType.MESSAGE_COMPLETED,
                    payload_json={"completed_at": artifact.completed_at.isoformat() if artifact.completed_at else None},
                ),
            ],
        )

        await self._broadcast_conversation_events(session_id=session_id, events=events)

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
        persisted_events = runtime_adapter.handle_event("run:cancelled", {})
        await self._broadcast_conversation_events(
            session_id=run.session_id,
            events=persisted_events,
        )

        cancelled = self.conversation_service.run_repo.get(run_id)
        if cancelled is None:
            raise ValueError("运行不存在")
        return cancelled


agent_service = AgentService()

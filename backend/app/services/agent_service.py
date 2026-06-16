import asyncio
import contextlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config.settings import config_manager
from app.errors import NotFoundValueError
from app.execution.approval_store import PendingApprovalStore
from app.execution.models import LoopStatus
from app.execution.prompt_manager import PromptManager
from app.execution.rapid_loop import RapidExecutionLoop
from app.ids import new_event_id
from app.llm import LLMAdapterFactory
from app.llm.base import LLMMessage, MessageRole, UniversalLLMInterface
from app.memory.context_assembly import ContextAssembler
from app.memory.continuation import build_continuation_artifact
from app.memory.continuation_builder import ContinuationArtifactBuilder
from app.models.approval import AllowApprovalDecision, PendingToolApproval
from app.models.conversation import (
    ConversationEvent,
    EventType,
    Message,
    MessageType,
    Run,
    RunStatus,
)
from app.models.conversation_snapshot import ConversationSnapshot, StartTurnResult
from app.models.session import DEFAULT_SESSION_TITLE, SessionUpdate
from app.orchestration.package_resolver import PackageResolver
from app.orchestration.skill_registry import skill_registry as global_skill_registry
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.path_security import PathSecurity
from app.security.sandbox.factory import create_sandbox
from app.security.session_trust_store import SessionTrustStore, TrustRule
from app.security.shell_security import ShellSecurity
from app.storage.database import db
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository
from app.tools.base import ToolResult
from app.tools.edit_tool import EditTool
from app.tools.explore_tool import ExploreTool
from app.tools.file_tool import FileTool
from app.tools.glob_tool import GlobTool
from app.tools.grep_tool import GrepTool
from app.tools.memory_tool import MemoryTool
from app.tools.plan_exit_tool import PlanExitTool
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry
from app.tools.session_recall_tool import SessionRecallTool
from app.tools.shell_tool import ShellTool
from app.tools.skill_tool import SkillTool

logger = logging.getLogger(__name__)

try:
    from app.tools.browser_tool import BrowserTool as _BrowserTool
except ImportError:
    _BrowserTool = None  # type: ignore[assignment,misc]
    logger.warning("playwright 未安装，BrowserTool 不可用")

from .cleanup_service import CleanupService
from .conversation_broadcaster import ConversationBroadcaster, NoopConversationBroadcaster
from .conversation_runtime_adapter import ConversationRuntimeAdapter
from .conversation_service import ConversationService
from .conversation_service import conversation_service as default_conversation_service
from .llm_provider_service import LLMProviderService
from .llm_provider_service import llm_provider_service as default_llm_provider_service

_CANCEL_WAIT_ATTEMPTS = 10
_CANCEL_WAIT_INTERVAL_SECONDS = 0.01
_EVENT_CLEANUP_INTERVAL_SECONDS = 300


def resolve_active_run_id_from_conversation(snapshot: ConversationSnapshot) -> str | None:
    if not snapshot.session.active_turn_id:
        return None
    active_turn = next((t for t in snapshot.turns if t.id == snapshot.session.active_turn_id), None)
    if not active_turn or not active_turn.active_run_id:
        return None
    active_run = next((r for r in snapshot.runs if r.id == active_turn.active_run_id), None)
    if not active_run or active_run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
        return None
    return active_run.id


class AgentService:
    """Agent 执行服务"""

    def __init__(
        self,
        project_repo: ProjectRepository | None = None,
        session_repo: SessionRepository | None = None,
        conversation_service: ConversationService | None = None,
        llm_provider_service: LLMProviderService | None = None,
        conversation_broadcaster: ConversationBroadcaster | None = None,
        pending_approval_store: PendingApprovalStore | None = None,
        session_service=None,
    ):
        self.running_tasks: dict[str, asyncio.Task] = {}
        self._runtime_adapters: dict[str, ConversationRuntimeAdapter] = {}
        self._execution_loops: dict[str, RapidExecutionLoop] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._title_tasks: dict[str, asyncio.Task] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._upload_cleanup_task: asyncio.Task | None = None
        self._browser_tools: dict[str, _BrowserTool] = {}
        self._browser_tools_lock = threading.Lock()
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or default_conversation_service
        self.llm_provider_service = llm_provider_service or default_llm_provider_service
        self.conversation_broadcaster = conversation_broadcaster or NoopConversationBroadcaster()
        self.pending_approval_store = pending_approval_store or PendingApprovalStore()
        self.session_service = session_service
        self.prompt_manager = PromptManager()
        self.context_assembler = ContextAssembler(
            conversation_service=self.conversation_service,
            skill_registry=global_skill_registry,
        )
        self.continuation_builder = ContinuationArtifactBuilder()
        self.trust_store = SessionTrustStore()

    def _build_run_tool_registry(
        self,
        project_path: str | None,
        session_id: str | None = None,
        trust_store: SessionTrustStore | None = None,
    ) -> ToolRegistry:
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

        from app.config.settings import config_manager as _cfg_paths
        skill_install_dir = str(Path(_cfg_paths.settings.skill.install_dir).resolve())
        if skill_install_dir not in allowed_paths:
            allowed_paths.append(skill_install_dir)
        plugin_cache_dir = str(Path(_cfg_paths.settings.plugin.package_cache_dir).resolve())
        if plugin_cache_dir not in allowed_paths:
            allowed_paths.append(plugin_cache_dir)
        base_dir = resolved_project_path or str(Path.cwd().resolve())
        path_security = PathSecurity(
            allowed_paths, base_dir=base_dir,
            session_id=session_id, trust_store=trust_store,
        )

        registry = ToolRegistry()
        registry.register(FileTool(path_security))
        registry.register(GlobTool(path_security))
        registry.register(GrepTool(path_security))
        registry.register(ShellTool(
            ShellSecurity(), path_security, CommandEffectRegistry(), create_sandbox(),
            session_id=session_id,
            trust_store=trust_store,
        ))
        registry.register(EditTool(path_security))
        registry.register(MemoryTool())
        registry.register(PlanTool())
        registry.register(PlanExitTool())
        registry.register(ExploreTool(path_security))
        from app.config.settings import config_manager as _cfg_mgr
        _pkg_resolver = PackageResolver(Path(_cfg_mgr.settings.plugin.package_cache_dir))
        registry.register(SkillTool(global_skill_registry, resolver=_pkg_resolver))

        if _BrowserTool is not None and session_id is not None:
            with self._browser_tools_lock:
                browser_tool = self._browser_tools.get(session_id)
                if browser_tool is None:
                    from app.config.settings import config_manager as _cfg_browser
                    _browser_settings = _cfg_browser.settings.browser
                    browser_tool = _BrowserTool(config=_browser_settings)
                    self._browser_tools[session_id] = browser_tool
                    logger.info("为 session=%s 创建新 BrowserTool 实例", session_id)
                else:
                    logger.info("复用 session=%s 的已有 BrowserTool 实例", session_id)
            registry.register(browser_tool)
        elif _BrowserTool is not None:
            from app.config.settings import config_manager as _cfg_browser
            _browser_settings = _cfg_browser.settings.browser
            registry.register(_BrowserTool(config=_browser_settings))

        logger.info(
            "构建运行时工具注册中心, run_base_dir=%s, allowed_paths=%s", base_dir, allowed_paths
        )
        return registry

    async def start_turn(
        self,
        *,
        project_id: str,
        session_id: str,
        content: str,
        provider_id: str | None = None,
        model_id: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> StartTurnResult:
        project = self.project_repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")

        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")
        if session.project_id != project.id:
            raise ValueError("会话不属于当前项目")

        agent_mode = getattr(session, 'agent_mode', 'build') or 'build'

        before_seq = session.last_event_seq
        resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)

        started = self.conversation_service.start_turn(
            session_id=session_id,
            content=content,
            provider_id=resolved_llm.provider_id,
            model_id=resolved_llm.model_id,
            workspace_ref=project.path,
            attachment_ids=attachment_ids or [],
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
            agent_mode=agent_mode,
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
        agent_mode: str = "build",
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
                agent_mode=agent_mode,
            )
        )
        self.running_tasks[run_id] = execution_task

        def _cleanup(_: asyncio.Task) -> None:
            self.running_tasks.pop(run_id, None)
            self._runtime_adapters.pop(run_id, None)
            self._execution_loops.pop(run_id, None)

        execution_task.add_done_callback(_cleanup)
        return execution_task

    async def _broadcast_conversation_events(
        self,
        *,
        session_id: str,
        events: list[ConversationEvent],
    ) -> None:
        for event in events:
            await self.conversation_broadcaster.send_event(
                session_id,
                "conversation:event",
                event.model_dump(mode="json"),
            )

    async def _broadcast_conversation_live_event(
        self,
        *,
        session_id: str,
        data: dict,
    ) -> None:
        await self.conversation_broadcaster.send_event(
            session_id,
            "conversation:live_event",
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

    def start_background_tasks(
        self, cleanup_interval_seconds: int = _EVENT_CLEANUP_INTERVAL_SECONDS
    ) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(
            self._event_cleanup_loop(cleanup_interval_seconds),
            name="conversation-event-cleanup",
        )
        self._upload_cleanup_task = asyncio.create_task(
            self._upload_cleanup_loop(),
            name="upload-cleanup",
        )

    async def stop_background_tasks(self) -> None:
        cleanup_task = self._cleanup_task
        if cleanup_task is None:
            return
        self._cleanup_task = None
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task

        upload_cleanup_task = self._upload_cleanup_task
        if upload_cleanup_task is not None:
            self._upload_cleanup_task = None
            upload_cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await upload_cleanup_task

    async def cleanup_browser_for_session(self, session_id: str) -> None:
        """清理指定 session 的 BrowserTool 资源。

        在 session 被删除或销毁时调用，确保浏览器进程被正确关闭，
        不会留下僵尸 chromium 进程。
        """
        with self._browser_tools_lock:
            browser_tool = self._browser_tools.pop(session_id, None)
        if browser_tool is not None:
            logger.info("清理 session=%s 的 BrowserTool", session_id)
            await browser_tool.cleanup()

    async def shutdown(self) -> None:
        """服务关闭时清理所有资源，包括所有 session 的浏览器实例。"""
        with self._browser_tools_lock:
            tools_to_cleanup = list(self._browser_tools.items())
            self._browser_tools.clear()

        for session_id, browser_tool in tools_to_cleanup:
            try:
                await browser_tool.cleanup()
                logger.info("关闭 session=%s 的浏览器实例", session_id)
            except Exception:
                logger.warning("关闭 session=%s 的浏览器实例失败", session_id, exc_info=True)

    async def _event_cleanup_loop(self, cleanup_interval_seconds: int) -> None:
        while True:
            try:
                cleaned = self.conversation_service.cleanup_events()
                if cleaned:
                    logger.info("清理过期 conversation_events: deleted=%s", cleaned)
            except Exception:
                logger.exception("清理 conversation_events 失败")
            await asyncio.sleep(cleanup_interval_seconds)

    async def _upload_cleanup_loop(self) -> None:
        """图片清理循环"""
        cleanup_service = CleanupService()
        while True:
            try:
                await asyncio.to_thread(cleanup_service.cleanup_old_uploads_sync, max_age_days=1)
            except Exception:
                logger.exception("清理上传文件失败")
            await asyncio.sleep(3600)  # 每小时执行一次

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
        agent_mode: str = "build",
    ) -> None:
        resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)
        cancel_event = asyncio.Event()
        self._cancel_events[run_id] = cancel_event

        async def on_llm_retry(exc: Exception, attempt: int, delay: float) -> None:
            logger.warning(
                "LLM 请求失败 (%s)，第 %d/%d 次重试，%.1fs 后重试: %s",
                type(exc).__name__,
                attempt + 1,
                5,
                delay,
                exc,
            )
            await self.conversation_broadcaster.send_event(
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

        llm = LLMAdapterFactory.create(resolved_llm, on_retry=on_llm_retry, cancel_event=cancel_event)
        runtime_adapter = ConversationRuntimeAdapter(
            conversation_service=self.conversation_service,
            session_id=session_id,
            turn_id=turn_id,
            run_id=run_id,
        )
        self._runtime_adapters[run_id] = runtime_adapter

        async def persist_and_broadcast(event_type: str, data: dict) -> None:
            if event_type == "approval:required":
                self._register_pending_approval(
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    data=data,
                )
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
                await self.conversation_broadcaster.send_event(session_id, "plan:updated", data)
            elif event_type.startswith("metrics:"):
                await self.conversation_broadcaster.send_event(session_id, event_type, data)
            else:
                await persist_and_broadcast(event_type, data)

        run_tool_registry = self._build_run_tool_registry(project_path, session_id=session_id, trust_store=self.trust_store)
        run_tool_registry.register(SessionRecallTool(session_id=session_id, project_id=project_id))
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=run_tool_registry,
            event_callback=event_callback,
            context_window=resolved_llm.context_window,
        )
        self._execution_loops[run_id] = execution_loop

        try:
            session = self.session_repo.get(session_id)
            if session and session.title == DEFAULT_SESSION_TITLE:
                title_task = asyncio.create_task(
                    self._generate_session_title(
                        llm=llm,
                        session_id=session_id,
                        task=task,
                    )
                )
                self._title_tasks[run_id] = title_task
                title_task.add_done_callback(lambda _: self._title_tasks.pop(run_id, None))

            assembly = self.context_assembler.build_for_session(
                session_id=session_id,
                project_id=project_id,
                project_path=project_path,
                current_turn_id=turn_id,
                current_user_input=task,
                supports_vision=resolved_llm.supports_vision,
            )
            loop_result = await execution_loop.run(
                task=task,
                project_path=project_path,
                run_id=run_id,
                session_id=session_id,
                seed_messages=assembly.recent_messages,
                current_turn_message=assembly.current_turn_message,
                supplemental_context=assembly.supplemental_block,
                system_sections=assembly.system_sections,
                agent_mode=agent_mode,
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
                    compacted_summary=loop_result.compacted_summary,
                )
            except Exception:
                logger.exception("Continuation artifact generation failed: run_id=%s", run_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("运行失败: run_id=%s", run_id)
            await persist_and_broadcast("run:error", {"error": str(exc)})
        finally:
            self._runtime_adapters.pop(run_id, None)
            self._execution_loops.pop(run_id, None)
            self._cancel_events.pop(run_id, None)

    def _register_pending_approval(
        self,
        *,
        session_id: str,
        turn_id: str,
        run_id: str,
        data: dict,
    ) -> None:
        approval_id = data.get("approval_id")
        if not isinstance(approval_id, str) or not approval_id:
            raise ValueError("approval_id 不能为空")

        arguments = data.get("arguments")
        approval_payload = data.get("approval")
        self.pending_approval_store.create(
            approval_id=approval_id,
            session_id=session_id,
            turn_id=turn_id,
            run_id=run_id,
            step_number=int(data.get("step_number") or 0),
            tool_call_id=str(data.get("tool_call_id") or ""),
            tool_name=str(data.get("tool_name") or ""),
            tool_arguments=arguments if isinstance(arguments, dict) else {},
            approval_payload=approval_payload if isinstance(approval_payload, dict) else {},
        )

    async def _generate_session_title(
        self,
        *,
        llm: UniversalLLMInterface,
        session_id: str,
        task: str,
    ) -> None:
        try:
            session = self.session_repo.get(session_id)
            if not session or session.title != DEFAULT_SESSION_TITLE:
                return

            prompt = (
                "根据用户的第一条消息生成一个简短的会话标题（不超过20字），"
                "直接输出标题文本，不要加引号或其他格式。"
                f"用户消息：{task}"
            )
            response = await llm.complete(
                [
                    LLMMessage(role=MessageRole.USER, content=prompt),
                ],
                tools=None,
            )
            title = (getattr(response, "content", None) or "").strip()[:20]
            if not title:
                title = task[:20]
        except Exception:
            logger.exception("会话标题生成失败: session_id=%s", session_id)
            title = task[:20]

        try:
            session_svc = self.session_service
            if session_svc is None:
                from .session_service import session_service as session_svc
            updated = session_svc.update_session(
                session_id, SessionUpdate(title=title)
            )
            await self.conversation_broadcaster.send_event(
                session_id,
                "session:title_updated",
                {"session_id": session_id, "title": updated.title},
            )
        except Exception:
            logger.exception("会话标题更新失败: session_id=%s", session_id)

    async def _generate_and_persist_continuation_artifact(
        self,
        *,
        llm: UniversalLLMInterface,
        session_id: str,
        turn_id: str,
        run_id: str,
        task: str,
        compacted_summary: str | None = None,
    ) -> None:
        turn_messages = self.conversation_service.list_turn_messages(turn_id)
        if not turn_messages:
            logger.warning(
                "Continuation artifact skipped: no messages for turn %s (可能被编辑/截断删除), run_id=%s",
                turn_id,
                run_id,
            )
            return
        prompt_input = self.continuation_builder.build_prompt_input(
            task=task,
            messages=turn_messages,
            existing_summary=compacted_summary,
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
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(role=MessageRole.USER, content=prompt_input),
            ],
            tools=None,
        )
        content = (getattr(response, "content", None) or "").strip()
        if not content:
            return

        turn = self.conversation_service.get_turn(turn_id)
        if turn is None:
            logger.warning(
                "Continuation artifact skipped: turn %s no longer exists (可能被编辑/截断删除), run_id=%s",
                turn_id,
                run_id,
            )
            return

        next_index = self.conversation_service.next_message_index(turn_id)
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
                    id=new_event_id(),
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
                    id=new_event_id(),
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=message_id,
                    event_type=EventType.MESSAGE_COMPLETED,
                    payload_json={
                        "completed_at": artifact.completed_at.isoformat()
                        if artifact.completed_at
                        else None
                    },
                ),
            ],
        )

        if config_manager.should_show_continuation_notices():
            await self._broadcast_conversation_events(session_id=session_id, events=events)

    async def cancel_run(self, run_id: str) -> Run:
        cancel_event = self._cancel_events.get(run_id)
        if cancel_event is not None:
            cancel_event.set()

        title_task = self._title_tasks.pop(run_id, None)
        if title_task is not None and not title_task.done():
            title_task.cancel()

        running = self.running_tasks.get(run_id)
        if running is not None and not running.done():
            running.cancel()
            for _ in range(_CANCEL_WAIT_ATTEMPTS):
                if running.done():
                    break
                await asyncio.sleep(_CANCEL_WAIT_INTERVAL_SECONDS)
            with contextlib.suppress(asyncio.CancelledError):
                await running

        run = self.conversation_service.get_run(run_id)
        if run is None:
            raise NotFoundValueError("运行不存在")
        if run.status == RunStatus.CANCELLED:
            self.pending_approval_store.expire_for_run(run_id)
            return run
        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
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
        cancelled = self.conversation_service.get_run(run_id)
        if cancelled is None:
            raise NotFoundValueError("运行不存在")
        if cancelled.status == RunStatus.CANCELLED:
            self.pending_approval_store.expire_for_run(run_id)
        await self._broadcast_conversation_events(
            session_id=run.session_id,
            events=persisted_events,
        )

        return cancelled

    async def edit_and_rerun(
        self,
        *,
        project_id: str,
        session_id: str,
        message_id: str,
        new_content: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> StartTurnResult:
        project = self.project_repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")

        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")

        conversation = self.conversation_service.get_snapshot(session_id)
        active_run_id = resolve_active_run_id_from_conversation(conversation)
        if active_run_id:
            try:
                await self.cancel_run(active_run_id)
            except Exception:
                logger.warning("取消活跃运行失败: run_id=%s", active_run_id)

        resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)

        before_seq = self.session_repo.get(session_id).last_event_seq

        started = self.conversation_service.edit_and_rerun(
            session_id=session_id,
            message_id=message_id,
            new_content=new_content,
            provider_id=resolved_llm.provider_id,
            model_id=resolved_llm.model_id,
            workspace_ref=project.path,
        )

        events = self.conversation_service.list_events_after(session_id, before_seq)
        await self._broadcast_conversation_events(session_id=session_id, events=events)

        self.schedule_turn(
            run_id=started.run.id,
            session_id=session_id,
            turn_id=started.turn.id,
            task=started.user_message.content_text,
            project_id=project.id,
            project_path=project.path,
            provider_id=resolved_llm.provider_id,
            model_id=resolved_llm.model_id,
        )
        return started

    async def approve_tool_call(
        self, *, session_id: str, run_id: str, approval_id: str,
        decision: AllowApprovalDecision = "allow_once",
    ) -> None:
        await self._decide_tool_call_approval(
            session_id=session_id,
            run_id=run_id,
            approval_id=approval_id,
            approval_event_type=EventType.APPROVAL_APPROVED,
            decision=decision,
        )

    async def confirm_plan_exit(self, run_id: str) -> None:
        """Handle user confirmation of plan_exit — switch from plan to build agent."""
        execution_loop = self._execution_loops.get(run_id)
        if execution_loop is None:
            raise ValueError(f"运行不存在: {run_id}")
        await execution_loop.confirm_plan_exit_from_external(run_id)

    async def deny_tool_call(self, *, session_id: str, run_id: str, approval_id: str) -> None:
        await self._decide_tool_call_approval(
            session_id=session_id,
            run_id=run_id,
            approval_id=approval_id,
            approval_event_type=EventType.APPROVAL_DENIED,
        )

    async def _decide_tool_call_approval(
        self,
        *,
        session_id: str,
        run_id: str,
        approval_id: str,
        approval_event_type: EventType,
        decision: AllowApprovalDecision = "allow_once",
    ) -> None:
        terminal_event_type: EventType | None = None
        terminal_payload: dict | None = None

        with self.conversation_service.acquire_session_write_lock(session_id):
            run = self.conversation_service.get_run(run_id)
            if run is None:
                raise NotFoundValueError("运行不存在")
            if run.session_id != session_id:
                raise ValueError("运行不属于当前会话")
            if run.status != RunStatus.WAITING_FOR_APPROVAL:
                raise ValueError("运行未在等待审批")
            pending = self.pending_approval_store.get(approval_id)
            if pending is None:
                raise NotFoundValueError("审批不存在")
            if pending.session_id != session_id:
                raise ValueError("审批不属于当前会话")
            if pending.run_id != run_id:
                raise ValueError("审批不属于当前运行")
            if pending.status != "pending":
                raise ValueError("审批已处理")

            if approval_event_type == EventType.APPROVAL_APPROVED:
                self.pending_approval_store.approve(approval_id, decision=decision)
                trace_status = "approved"

                if decision == "trust_and_allow":
                    self._add_trust_rules_from_approval(pending, session_id)
                    await self._cascade_auto_approve(session_id)

                execution_result = await self._execute_approved_tool(pending, run_id=run_id)

                loop = self._execution_loops.get(run_id)
                if loop is not None:
                    loop.set_approval_result({
                        "success": execution_result.success,
                        "output": execution_result.output,
                        "error": execution_result.error,
                    })
                else:
                    terminal_event_type = EventType.RUN_COMPLETED
                    terminal_payload = {
                        "finished_at": datetime.now().isoformat(),
                        "result": "approval_executed_no_loop",
                        "execution_success": execution_result.success,
                        "execution_output": execution_result.output,
                        "execution_error": execution_result.error,
                    }
            else:
                self.pending_approval_store.deny(approval_id)
                trace_status = "denied"

                loop = self._execution_loops.get(run_id)
                if loop is not None:
                    loop.set_approval_result(None)
                else:
                    terminal_event_type = EventType.RUN_CANCELLED
                    terminal_payload = {
                        "finished_at": datetime.now().isoformat(),
                        "reason": "approval_denied",
                    }

            trace_message = self._find_pending_approval_trace_message(
                run_id=run_id,
                approval_id=approval_id,
            )
            events_to_append: list[ConversationEvent] = []
            if trace_message is not None:
                events_to_append.append(
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=run.turn_id,
                        run_id=run_id,
                        message_id=trace_message.id,
                        event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                        payload_json={
                            "payload_json": {
                                "approval_id": approval_id,
                                "status": trace_status,
                            }
                        },
                    )
                )

            events_to_append.append(
                ConversationEvent(
                    id=new_event_id(),
                    session_id=session_id,
                    turn_id=run.turn_id,
                    run_id=run_id,
                    event_type=approval_event_type,
                    payload_json={"approval_id": approval_id},
                )
            )

            if terminal_event_type is not None:
                events_to_append.append(
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=run.turn_id,
                        run_id=run_id,
                        event_type=terminal_event_type,
                        payload_json=terminal_payload,
                    )
                )

            events = self.conversation_service.append_events_locked(session_id, events_to_append)
        await self._broadcast_conversation_events(session_id=session_id, events=events)

    async def _execute_approved_tool(
        self, pending: PendingToolApproval, *, run_id: str
    ) -> "ToolResult":
        """Execute a previously approved tool call using the stored decision.

        Generic: uses pending.tool_name to find the right tool.
        Any tool that returns approval_required must accept _approved_decision
        in its args dict and execute the stored decision instead of re-evaluating.
        """
        approved_decision_data = (
            pending.approval_payload.get("payload", {}).get("approved_decision")
            or pending.approval_payload.get("approved_decision")
        )
        if not approved_decision_data:
            return ToolResult(
                success=False,
                error="审批缺少存储的决策数据，无法执行",
            )

        elevation_request = pending.approval_payload.get("payload", {}).get("elevation_request")
        if elevation_request and isinstance(approved_decision_data, dict):
            approved_decision_data["elevation_request"] = elevation_request

        project_path = approved_decision_data.get("cwd") if isinstance(approved_decision_data, dict) else None
        loop = self._execution_loops.get(run_id)
        tool_registry = getattr(loop, "tool_registry", None) or self._build_run_tool_registry(project_path)

        tool = tool_registry.get(pending.tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"工具 {pending.tool_name} 不可用",
            )

        try:
            result = await tool.execute({
                **pending.tool_arguments,
                "_approved_decision": approved_decision_data,
            })
            return result
        except Exception as exc:
            logger.exception("审批工具执行失败: approval_id=%s tool=%s", pending.id, pending.tool_name)
            return ToolResult(success=False, error=str(exc))

    def _find_pending_approval_trace_message(
        self, *, run_id: str, approval_id: str
    ) -> Message | None:
        run = self.conversation_service.get_run(run_id)
        if run is None:
            return None

        for message in self.conversation_service.list_turn_messages(run.turn_id):
            if message.run_id != run_id or message.message_type != MessageType.TOOL_TRACE:
                continue
            if message.payload_json.get("approval_id") == approval_id:
                return message
        return None

    def _add_trust_rules_from_approval(self, pending: PendingToolApproval, session_id: str) -> None:
        inner_payload = pending.approval_payload.get("payload", {})
        access_type = inner_payload.get("access_type")

        if access_type == "external_path_read":
            for key in ("suggested_prefix_rule", "prefix"):
                prefixes = inner_payload.get(key) if key == "suggested_prefix_rule" else None
                if not prefixes:
                    suggested_trust = pending.approval_payload.get("suggested_trust")
                    if isinstance(suggested_trust, dict):
                        prefixes = suggested_trust.get("prefix")
                if prefixes and isinstance(prefixes, list):
                    for prefix in prefixes:
                        if isinstance(prefix, str) and prefix:
                            self.trust_store.add_rule(session_id, TrustRule(permission="external_path", pattern=prefix))
            return

        suggested_trust = pending.approval_payload.get("suggested_trust")
        if isinstance(suggested_trust, dict):
            permission = suggested_trust.get("permission")
            pattern = suggested_trust.get("pattern")
            if permission and pattern:
                self.trust_store.add_rule(session_id, TrustRule(permission=permission, pattern=pattern))
                return

        suggested_prefixes = inner_payload.get("suggested_prefix_rule")
        if suggested_prefixes and isinstance(suggested_prefixes, list):
            for prefix in suggested_prefixes:
                if isinstance(prefix, str) and prefix:
                    self.trust_store.add_rule(session_id, TrustRule(permission="shell", pattern=prefix))

        if isinstance(suggested_trust, dict):
            trust_prefixes = suggested_trust.get("prefix")
            if trust_prefixes and isinstance(trust_prefixes, list):
                for prefix in trust_prefixes:
                    if isinstance(prefix, str) and prefix:
                        self.trust_store.add_rule(session_id, TrustRule(permission="shell", pattern=prefix))

        suggested_trust = pending.approval_payload.get("suggested_trust")
        if isinstance(suggested_trust, dict):
            trust_prefixes = suggested_trust.get("prefix")
            if isinstance(trust_prefixes, list):
                for prefix in trust_prefixes:
                    if isinstance(prefix, str) and prefix:
                        self.trust_store.add_rule(session_id, TrustRule(permission="shell", pattern=prefix))

    async def _cascade_auto_approve(self, session_id: str) -> None:
        for approval_id in self.pending_approval_store.list_pending_approval_ids_for_session(session_id):
            pending = self.pending_approval_store.get(approval_id)
            if pending is None or pending.status != "pending":
                continue
            inner_payload = pending.approval_payload.get("payload", {})
            access_type = inner_payload.get("access_type")
            approval_kind = inner_payload.get("approval_kind")

            if access_type == "external_path_read":
                path = inner_payload.get("path")
                if path and self.trust_store.matches(session_id, "external_path", path):
                    await self.approve_tool_call(
                        session_id=session_id,
                        run_id=pending.run_id,
                        approval_id=pending.id,
                        decision="allow_once",
                    )
            elif approval_kind == "sandbox_network_elevation":
                if self.trust_store.matches(session_id, "sandbox_network", "*"):
                    await self.approve_tool_call(
                        session_id=session_id,
                        run_id=pending.run_id,
                        approval_id=pending.id,
                        decision="allow_once",
                    )
            elif approval_kind == "sandbox_path_elevation":
                elevation_request = inner_payload.get("elevation_request")
                if elevation_request and elevation_request.get("denied_paths"):
                    all_matched = all(
                        self.trust_store.matches(session_id, "sandbox_path", p + "/*")
                        for p in elevation_request["denied_paths"]
                    )
                    if all_matched:
                        await self.approve_tool_call(
                            session_id=session_id,
                            run_id=pending.run_id,
                            approval_id=pending.id,
                            decision="allow_once",
                        )
            else:
                command = inner_payload.get("command") or pending.tool_arguments.get("command")
                if command and self.trust_store.matches(session_id, "shell", command):
                    await self.approve_tool_call(
                        session_id=session_id,
                        run_id=pending.run_id,
                        approval_id=pending.id,
                        decision="allow_once",
                    )
        return None

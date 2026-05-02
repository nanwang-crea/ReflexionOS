import asyncio
import contextlib
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.execution.approval_store import PendingApprovalStore
from app.execution.models import LoopStatus
from app.execution.prompt_manager import PromptManager
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm import LLMAdapterFactory
from app.llm.base import LLMMessage, MessageRole
from app.memory.context_assembly import ContextAssembler
from app.memory.continuation import build_continuation_artifact
from app.memory.continuation_builder import ContinuationArtifactBuilder
from app.models.conversation import ConversationEvent, EventType, Message, MessageType, Run, RunStatus
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

from .conversation_broadcaster import ConversationBroadcaster, NoopConversationBroadcaster
from .conversation_runtime_adapter import ConversationRuntimeAdapter
from .conversation_service import ConversationService
from .conversation_service import conversation_service as default_conversation_service
from .llm_provider_service import LLMProviderService
from .llm_provider_service import llm_provider_service as default_llm_provider_service

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
        conversation_broadcaster: ConversationBroadcaster | None = None,
        pending_approval_store: PendingApprovalStore | None = None,
    ):
        self.running_tasks: dict[str, asyncio.Task] = {}
        self._runtime_adapters: dict[str, ConversationRuntimeAdapter] = {}
        self._execution_loops: dict[str, "RapidExecutionLoop"] = {}
        self._cleanup_task: asyncio.Task | None = None
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or default_conversation_service
        self.llm_provider_service = llm_provider_service or default_llm_provider_service
        self.conversation_broadcaster = conversation_broadcaster or NoopConversationBroadcaster()
        self.pending_approval_store = pending_approval_store or PendingApprovalStore()
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

        llm = LLMAdapterFactory.create(resolved_llm, on_retry=on_llm_retry)
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
                # Plan state is ephemeral per-run, only broadcast to frontend
                await self.conversation_broadcaster.send_event(session_id, "plan:updated", data)
            else:
                await persist_and_broadcast(event_type, data)

        run_tool_registry = self._build_run_tool_registry(project_path)
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=run_tool_registry,
            event_callback=event_callback,
        )
        self._execution_loops[run_id] = execution_loop

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
            self._execution_loops.pop(run_id, None)

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
        then persist as a real system_notice message.
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
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(role=MessageRole.USER, content=prompt_input),
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
                    payload_json={
                        "completed_at": artifact.completed_at.isoformat()
                        if artifact.completed_at
                        else None
                    },
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
        cancelled = self.conversation_service.run_repo.get(run_id)
        if cancelled is None:
            raise ValueError("运行不存在")
        if cancelled.status == RunStatus.CANCELLED:
            self.pending_approval_store.expire_for_run(run_id)
        await self._broadcast_conversation_events(
            session_id=run.session_id,
            events=persisted_events,
        )

        return cancelled

    async def approve_tool_call(
        self, *, session_id: str, run_id: str, approval_id: str
    ) -> None:
        await self._decide_tool_call_approval(
            session_id=session_id,
            run_id=run_id,
            approval_id=approval_id,
            approval_event_type=EventType.APPROVAL_APPROVED,
        )

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
    ) -> None:
        terminal_event_type: EventType | None = None
        terminal_payload: dict | None = None

        with self.conversation_service._acquire_session_write_lock(session_id):
            run = self.conversation_service.run_repo.get(run_id)
            if run is None:
                raise ValueError("运行不存在")
            if run.session_id != session_id:
                raise ValueError("运行不属于当前会话")
            if run.status != RunStatus.WAITING_FOR_APPROVAL:
                raise ValueError("运行未在等待审批")
            pending = self.pending_approval_store.get(approval_id)
            if pending is None:
                raise ValueError("审批不存在")
            if pending.session_id != session_id:
                raise ValueError("审批不属于当前会话")
            if pending.run_id != run_id:
                raise ValueError("审批不属于当前运行")
            if pending.status != "pending":
                raise ValueError("审批已处理")

            if approval_event_type == EventType.APPROVAL_APPROVED:
                self.pending_approval_store.approve(approval_id)
                trace_status = "approved"

                execution_result = await self._execute_approved_tool(pending)

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
                        id=f"evt-{uuid4().hex[:8]}",
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
                    id=f"evt-{uuid4().hex[:8]}",
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
                        id=f"evt-{uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_id=run.turn_id,
                        run_id=run_id,
                        event_type=terminal_event_type,
                        payload_json=terminal_payload,
                    )
                )

            events = self.conversation_service._append_events_locked(session_id, events_to_append)
        await self._broadcast_conversation_events(session_id=session_id, events=events)

    async def _execute_approved_tool(
        self, pending
    ) -> "ToolResult":
        """Execute a previously approved tool call using the stored decision.

        Generic: uses pending.tool_name to find the right tool.
        Any tool that returns approval_required must accept _approved_decision
        in its args dict and execute the stored decision instead of re-evaluating.
        """
        from app.tools.base import ToolResult

        approved_decision_data = pending.approval_payload.get("approved_decision")
        if not approved_decision_data:
            return ToolResult(
                success=False,
                error="审批缺少存储的决策数据，无法执行",
            )

        project_path = approved_decision_data.get("cwd") if isinstance(approved_decision_data, dict) else None
        tool_registry = self._build_run_tool_registry(project_path)

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
        run = self.conversation_service.run_repo.get(run_id)
        if run is None:
            return None

        for message in self.conversation_service.message_repo.list_by_turn(run.turn_id):
            if message.run_id != run_id or message.message_type != MessageType.TOOL_TRACE:
                continue
            if message.payload_json.get("approval_id") == approval_id:
                return message
        return None


agent_service = AgentService()

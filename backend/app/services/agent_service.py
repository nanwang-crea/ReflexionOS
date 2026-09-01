"""Agent 执行服务：整个对话/Agent 运行时的顶层编排者。负责发起新轮次、调度后台执行任务
（_run_turn 驱动 RapidExecutionLoop）、构建每次运行所需的工具注册中心（含路径安全、Shell 沙箱、
SubAgent 委托等）、处理工具调用审批（含信任规则/级联自动批准）、取消运行、会话重置/编辑重跑、
会话标题自动生成，以及浏览器工具实例和后台清理任务（事件清理、上传文件清理）的生命周期管理。"""
import asyncio
import contextlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config.settings import config_manager
from app.errors import NotFoundValueError
from app.execution.approval_flow import ApprovalFlow
from app.execution.approval_store import PendingApprovalStore
from app.execution.models import LoopStatus
from app.execution.prompt_manager import PromptManager
from app.execution.rapid_loop import RapidExecutionLoop
from app.ids import new_event_id
from app.llm import LLMAdapterFactory
from app.llm.base import LLMMessage, MessageRole, UniversalLLMInterface
from app.execution.conversation_history_loader import ConversationHistoryLoader

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
from app.models.session import DEFAULT_SESSION_TITLE, Session, SessionUpdate
from app.orchestration.package_resolver import PackageResolver
from app.orchestration.skill_registry import skill_registry as global_skill_registry
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.path_security import PathSecurity
from app.security.permission_mode import PermissionMode
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
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry
from app.tools.session_recall_tool import SessionRecallTool
from app.tools.shell_tool import ShellTool
from app.tools.skill_tool import SkillTool
from app.tools.working_memory_tool import WorkingMemoryTool
from app.tools.delegate_tool import DelegateTool
from app.agents.sub_agent_runner import SubAgentRunner

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
from .attachment_service import convert_attachments_to_content_parts

_CANCEL_WAIT_ATTEMPTS = 10
_CANCEL_WAIT_INTERVAL_SECONDS = 0.01
_EVENT_CLEANUP_INTERVAL_SECONDS = 300


def resolve_active_run_id_from_conversation(snapshot: ConversationSnapshot) -> str | None:
    """从会话快照中解析出当前"活跃且未终结"的 Run ID（若存在）。
    输入：snapshot（ConversationSnapshot，含 session/turns/runs）
    逻辑：session.active_turn_id -> 对应 turn.active_run_id -> 对应 run，
          且该 run 状态不处于终态（COMPLETED/FAILED/CANCELLED）才视为真正活跃
    输出：活跃 run 的 id，或 None（无活跃轮次/运行，或已是终态）
    """
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
        """初始化服务，注册各类依赖并准备运行时状态容器。
        输入：project_repo/session_repo（仓储依赖，可选）、conversation_service/llm_provider_service（核心服务依赖，可选）、
              conversation_broadcaster（事件广播器，缺省用 Noop 实现）、pending_approval_store（待审批存储）、
              session_service（会话服务，用于标题更新，延迟注入避免循环导入）
        内部状态说明：
          - running_tasks：{run_id: asyncio.Task}，正在执行的主 Agent 运行任务；
          - _runtime_adapters：{run_id: ConversationRuntimeAdapter}，每次运行对应的事件适配器；
          - _execution_loops / _sub_agent_execution_loops：主/子 Agent 的执行循环实例，供审批恢复时定位；
          - _cancel_events：{run_id: asyncio.Event}，用于向执行循环传递取消信号；
          - _title_tasks：{run_id: asyncio.Task}，异步生成会话标题的任务；
          - _browser_tools：{session_id: BrowserTool}，按会话复用的浏览器工具实例；
          - _session_approval_flows：{session_id: ApprovalFlow}，用于将 SubAgent 审批结果路由回正确的审批流。
        """
        self.running_tasks: dict[str, asyncio.Task] = {}
        self._runtime_adapters: dict[str, ConversationRuntimeAdapter] = {}
        self._execution_loops: dict[str, RapidExecutionLoop] = {}
        self._sub_agent_execution_loops: dict[str, RapidExecutionLoop] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._title_tasks: dict[str, asyncio.Task] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._upload_cleanup_task: asyncio.Task | None = None
        self._browser_tools: dict[str, _BrowserTool] = {}
        self._browser_tools_lock = threading.Lock()
        # session_id → approval_flow 映射，用于 SubAgent 审批结果路由
        self._session_approval_flows: dict[str, "ApprovalFlow"] = {}
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or default_conversation_service
        self.llm_provider_service = llm_provider_service or default_llm_provider_service
        self.conversation_broadcaster = conversation_broadcaster or NoopConversationBroadcaster()
        self.pending_approval_store = pending_approval_store or PendingApprovalStore()
        self.session_service = session_service
        self.prompt_manager = PromptManager(skill_registry=global_skill_registry)
        # ConversationHistoryLoader 只负责对话历史加载，
        # 静态上下文（Skills 等）由 PromptManager 统一管理
        self.history_loader = ConversationHistoryLoader(
            conversation_service=self.conversation_service,
        )
        self.trust_store = SessionTrustStore()

    def _build_run_tool_registry(
        self,
        project_path: str | None,
        session_id: str | None = None,
        trust_store: SessionTrustStore | None = None,
        permission_mode: str = "auto",
    ) -> ToolRegistry:
        """为一次运行构建工具注册中心：确定路径安全边界，注册文件/Shell/浏览器等所有可用工具。
        输入：project_path（项目根目录，用于圈定可访问路径边界）、session_id（用于会话级信任规则和浏览器实例复用）、
              trust_store（会话信任规则存储，用于 Shell/路径访问的自动放行判断）、
              permission_mode（权限模式："ask"需人工确认/"auto"默认策略/"yolo"免确认）
        逻辑：
          1. 计算允许访问的路径集合：当前工作目录 + 项目路径 + skill 安装目录 + 插件缓存目录；
          2. 基于此构建 PathSecurity，注册 File/Glob/Grep/Shell/Edit/Plan/Explore/Skill 等基础工具；
          3. 若 playwright 可用：按 session_id 复用或新建 BrowserTool 实例（无 session_id 时每次新建，
             用于测试等场景）。
        输出：已注册好全部工具的 ToolRegistry 实例
        """
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

        skill_install_dir = str(Path(config_manager.settings.skill.install_dir).resolve())
        if skill_install_dir not in allowed_paths:
            allowed_paths.append(skill_install_dir)
        plugin_cache_dir = str(Path(config_manager.settings.plugin.package_cache_dir).resolve())
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
            permission_mode=PermissionMode(permission_mode) if permission_mode in {"ask", "auto", "yolo"} else PermissionMode.AUTO,
        ))
        registry.register(EditTool(path_security))
        registry.register(PlanTool())
        registry.register(ExploreTool(path_security))
        _pkg_resolver = PackageResolver(Path(config_manager.settings.plugin.package_cache_dir))
        registry.register(SkillTool(global_skill_registry, resolver=_pkg_resolver))

        if _BrowserTool is not None and session_id is not None:
            with self._browser_tools_lock:
                browser_tool = self._browser_tools.get(session_id)
                if browser_tool is None:
                    _browser_settings = config_manager.settings.browser
                    browser_tool = _BrowserTool(config=_browser_settings)
                    self._browser_tools[session_id] = browser_tool
                    logger.info("为 session=%s 创建新 BrowserTool 实例", session_id)
                else:
                    logger.info("复用 session=%s 的已有 BrowserTool 实例", session_id)
            registry.register(browser_tool)
        elif _BrowserTool is not None:
            _browser_settings = config_manager.settings.browser
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
        """发起一轮新对话：校验项目/会话归属，落地用户消息+Run 记录，并调度后台执行任务。
        输入：project_id、session_id、content（用户消息文本）、provider_id/model_id（可选，指定 LLM）、
              attachment_ids（可选，附件 ID 列表）
        逻辑：
          1. 校验项目、会话存在，且会话确实属于该项目；
          2. 解析出会话的 agent_mode（build 等）和 permission_mode（auto 等），解析最终使用的 LLM 配置；
          3. 调用 conversation_service.start_turn 落库（写入 TURN_CREATED/MESSAGE_CREATED/RUN_CREATED 事件）；
          4. 把刚产生的事件广播给前端（保证前端立刻看到新轮次和用户消息）；
          5. 调用 schedule_turn 异步调度真正的 Agent 执行。
        输出：StartTurnResult（turn/run/user_message）
        异常：NotFoundValueError（项目或会话不存在）、ValueError（会话不属于该项目）
        """
        project = self.project_repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")

        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")
        if session.project_id != project.id:
            raise ValueError("会话不属于当前项目")

        agent_mode = getattr(session, 'agent_mode', 'build') or 'build'
        permission_mode = getattr(session, 'permission_mode', 'auto') or 'auto'

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
            permission_mode=permission_mode,
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
        permission_mode: str = "auto",
    ) -> asyncio.Task:
        """将一次 Agent 运行调度为后台 asyncio 任务（若该 run_id 已在运行则直接复用，防止重复调度）。
        输入：run_id/session_id/turn_id（本次运行的标识）、task（任务文本）、project_id/project_path、
              provider_id/model_id（LLM 配置）、agent_mode（build 等执行模式）、permission_mode（权限模式）
        逻辑：创建 _run_turn 协程任务并记录到 running_tasks；任务结束后自动清理
              running_tasks/_runtime_adapters/_execution_loops 中对应的条目，避免内存泄漏。
        输出：对应的 asyncio.Task
        """
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
                permission_mode=permission_mode,
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
        """将一批已持久化的会话事件逐条广播给前端（WebSocket "conversation:event" 消息）。
        输入：session_id、events（待广播的事件列表）
        输出：无
        """
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
        """广播一条不落库的实时增量事件（WebSocket "conversation:live_event" 消息，用于流式打字机效果）。
        输入：session_id、data（实时事件负载）
        输出：无
        """
        await self.conversation_broadcaster.send_event(
            session_id,
            "conversation:live_event",
            data,
        )

    def get_live_state(self, session_id: str) -> dict | None:
        """获取指定会话当前正在流式生成的助手消息状态（供新建立的 WebSocket 连接补拉进度）。
        输入：session_id
        逻辑：遍历所有正在运行的 runtime_adapter，找到属于该会话的那个，取其 live_state
        输出：live_state 字典，或 None（该会话当前没有进行中的流式输出）
        """
        for runtime_adapter in self._runtime_adapters.values():
            if runtime_adapter.session_id != session_id:
                continue
            live_state = runtime_adapter.get_live_state()
            if live_state is not None:
                return live_state
        return None

    async def recover_orphaned_approvals(self) -> int:
        """服务启动时调用：清理上次进程退出前遗留在"等待审批"状态的孤儿 Run。

        背景：PendingApprovalStore（审批记录）和 RapidExecutionLoop（真正在等待审批结果的
        执行循环/asyncio.Event）都只存在于进程内存中。进程一旦重启（如桌面端整个退出重进），
        这两者必然清空；但 Run 的 WAITING_FOR_APPROVAL 状态是落库的，重进会话后前端会照常
        从历史读出一张"审批中"的卡片——此时这张卡片对应的审批请求已经没有任何执行上下文能够
        响应，用户点击"同意/拒绝"会直接命中 NotFoundValueError("审批不存在")。

        修复思路：跨进程的审批本来就不可能被真正恢复（执行到哪一步、子 agent 状态等全部随进程
        消失），与其让 UI 停留在一个死状态误导用户，不如在启动时主动把这些孤儿 Run 判定为终态，
        让前端把卡片刷新为"已取消"，提示用户重新发起操作。

        运行逻辑：
          1. 按状态查出所有仍处于 WAITING_FOR_APPROVAL 的 Run（跨会话）；
          2. 逐个调用已有的 cancel_run（其取消路径本就设计为在内存态缺失时优雅退化到
             直接落库 run:cancelled 事件），复用其状态转移与事件广播逻辑；
          3. 单个 Run 处理失败不应中断其余 Run 的清理，记录日志后继续。
        输出：int - 实际被清理的孤儿 Run 数量
        """
        orphaned_runs = self.conversation_service.run_repo.list_by_status(
            RunStatus.WAITING_FOR_APPROVAL.value
        )
        recovered = 0
        for run in orphaned_runs:
            try:
                await self.cancel_run(run.id)
                recovered += 1
            except Exception:
                logger.exception(
                    "[Startup] 清理孤儿审批 Run 失败: run_id=%s, session_id=%s",
                    run.id, run.session_id,
                )
        if recovered:
            logger.info("[Startup] 已清理 %d 个跨进程遗留的孤儿审批 Run", recovered)
        return recovered

    def start_background_tasks(
        self, cleanup_interval_seconds: int = _EVENT_CLEANUP_INTERVAL_SECONDS
    ) -> None:
        """启动后台常驻任务：会话事件清理循环 + 上传文件清理循环（幂等，重复调用不会重复启动）。
        输入：cleanup_interval_seconds（事件清理循环的执行间隔，默认 300 秒）
        输出：无
        """
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
        """停止并等待后台常驻任务（事件清理、上传清理）优雅退出，供服务关闭时调用。
        输出：无
        """
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

    def cleanup_session_security_state(self, session_id: str) -> None:
        """清理与 session 绑定的审批记忆和 trust rules。"""
        self.pending_approval_store.expire_for_session(session_id)
        self.trust_store.clear_session(session_id)

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
        """会话事件清理循环：定期调用 conversation_service.cleanup_events 清理过期事件日志，异常不中断循环。
        输入：cleanup_interval_seconds（每轮间隔秒数）
        输出：无（永久循环，直到任务被取消）
        """
        while True:
            try:
                cleaned = self.conversation_service.cleanup_events()
                if cleaned:
                    logger.info("清理过期 conversation_events: deleted=%s", cleaned)
            except Exception:
                logger.exception("清理 conversation_events 失败")
            await asyncio.sleep(cleanup_interval_seconds)

    async def _upload_cleanup_loop(self) -> None:
        """上传图片清理循环：每小时调用一次 CleanupService 清理超过 1 天的临时上传文件，异常不中断循环。
        输出：无（永久循环，直到任务被取消）
        """
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
        permission_mode: str = "auto",
    ) -> None:
        """驱动一次完整的 Agent 执行运行（作为后台 asyncio 任务被 schedule_turn 调度）。
        输入：run_id/session_id/turn_id（运行标识）、task（任务文本）、project_id/project_path、
              provider_id/model_id（LLM 配置）、agent_mode/permission_mode（执行/权限模式）
        逻辑（主干流程）：
          1. 解析 LLM 配置，创建带取消令牌和重试回调的 LLM 适配器；
          2. 创建 ConversationRuntimeAdapter，定义 persist_and_broadcast（落库+推送）和
             event_callback（区分 plan/metrics/sub_agent 等特殊事件类型，走不同处理路径）；
          3. 构建工具注册中心，注册 SessionRecallTool/WorkingMemoryTool；
          4. 创建主 RapidExecutionLoop，取出其 approval_flow 并记录到 _session_approval_flows
             （供后续 SubAgent 审批结果路由）；
          5. 注册 DelegateTool：闭包捕获当前上下文构造 _delegate_runner_factory，使主 Agent
             可以委托子任务给 SubAgentRunner（子 agent 共享父级审批流和事件回调，独立 session_id）；
          6. 若是会话首轮（标题仍为默认值），异步启动标题生成任务（不阻塞主流程）；
          7. 加载对话历史（不含静态上下文，静态上下文由 PromptManager 管理）；
          8. 若用户消息带图片附件，构建多模态 task_content（文本 + image_url 片段）；
          9. 调用 execution_loop.run 实际执行 Agent 循环；
          10. 无论成功/失败/取消，finally 中清理本次运行相关的所有内存态映射，防止泄漏。
        异常处理：CancelledError 直接重新抛出（不吞掉取消语义）；其余异常记录日志并广播 run:error 事件。
        输出：无（结果通过事件广播反映到前端和持久层）
        """
        resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)
        cancel_event = asyncio.Event()
        self._cancel_events[run_id] = cancel_event

        async def on_llm_retry(exc: Exception, attempt: int, delay: float) -> None:
            # LLM 请求失败时的重试回调：记录日志并向前端推送 "llm:retry" 提示，让用户感知到正在重试
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
            # 主 Agent 事件的标准处理路径：需要审批的先登记到 pending_approval_store，
            # 再交给 runtime_adapter 翻译为持久化事件，并分别推送实时增量事件和持久化事件
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
            # 执行循环所有事件的总入口回调，按事件类型分流：
            # plan:updated / metrics:* 直接透传给前端；sub_agent:* 需要单独登记审批并透传（不走持久化）；
            # 其余事件才走标准的 persist_and_broadcast（落库 + 推送）路径
            if event_type == "plan:updated":
                await self.conversation_broadcaster.send_event(session_id, "plan:updated", data)
            elif event_type.startswith("metrics:"):
                await self.conversation_broadcaster.send_event(session_id, event_type, data)
            elif event_type.startswith("sub_agent:"):
                # SubAgent 审批事件：注册到 pending_approval_store，使用父 session_id
                # 这样用户点击审批时后端能找到对应的审批记录
                if event_type == "sub_agent:approval:required":
                    approval_id = data.get("approval_id")
                    if isinstance(approval_id, str) and approval_id:
                        self.pending_approval_store.create(
                            approval_id=approval_id,
                            session_id=session_id,  # 使用父 session_id
                            turn_id="",
                            run_id=str(data.get("run_id", "")),
                            step_number=int(data.get("step_number") or 0),
                            tool_call_id=str(data.get("tool_call_id") or ""),
                            tool_name=str(data.get("tool_name") or ""),
                            tool_arguments=data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
                            approval_payload=data.get("approval") if isinstance(data.get("approval"), dict) else {},
                        )
                # 子 agent 事件直接透传到前端，不经过 runtime adapter 持久化
                # 前端通过 WebSocket 消息中的 sub_agent: 前缀识别并路由到子 agent store
                logger.info("[event_callback] Broadcasting sub_agent event: type=%s, session_id=%s, has_tool_call_id=%s", event_type, session_id, "tool_call_id" in data)
                await self.conversation_broadcaster.send_event(session_id, event_type, data)
            else:
                await persist_and_broadcast(event_type, data)

        run_tool_registry = self._build_run_tool_registry(project_path, session_id=session_id, trust_store=self.trust_store, permission_mode=permission_mode)
        run_tool_registry.register(SessionRecallTool(session_id=session_id, project_id=project_id))
        run_tool_registry.register(WorkingMemoryTool())

        # 先创建主 Agent 的 execution_loop（需要在工厂函数之前，以便获取其 approval_flow）
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=run_tool_registry,
            event_callback=event_callback,
            context_window=resolved_llm.context_window,
        )
        approval_flow = getattr(execution_loop, "approval_flow", None)
        self._execution_loops[run_id] = execution_loop
        # 存储 session → approval_flow 映射，供 SubAgent 审批结果路由使用
        if approval_flow is not None:
            self._session_approval_flows[session_id] = approval_flow

        # 注入 DelegateTool — 主 agent 可通过 delegate 工具委托子任务
        # runner_factory 闭包捕获当前执行上下文（llm_config, registry, project_path, approval_flow, event_callback）
        # event_callback 使子 agent 执行事件通过父级 SSE 链路实时推送到前端
        # parent_approval_flow 使子 agent 的审批请求路由到主 agent（用户在同一界面处理）
        def _delegate_runner_factory(task, input_data=None, expected_output=None):
            # 构造 SubAgentRunner：捕获当前主 Agent 的 LLM 配置、工具注册中心、项目路径、
            # 审批流和事件回调，使子 agent 与主 agent 共享执行上下文但拥有独立 session_id
            return SubAgentRunner(
                task=task,
                llm_config=resolved_llm,
                parent_tool_registry=run_tool_registry,
                input_data=input_data,
                expected_output=expected_output,
                project_path=project_path,
                # 并发 delegate 场景下多个子 agent 会同时创建，固定拼接会话 id 会
                # 相互碰撞，改为每次调用附加唯一短后缀
                session_id=f"{session_id}-sub-{uuid4().hex[:8]}",
                event_callback=event_callback,  # 传递事件回调，使 SubAgent 事件能发送到前端
                parent_approval_flow=execution_loop.approval_flow,  # 共享主 Agent 的审批流
                loop_started=self._register_sub_agent_loop,
                loop_finished=self._unregister_sub_agent_loop,
            )
        run_tool_registry.register(DelegateTool(
            runner_factory=_delegate_runner_factory,
            event_callback=event_callback,
            parent_session_id=session_id,  # 传递主 Agent 的 session_id，用于 SubAgent 审批路由
        ))

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

            # 加载对话历史（不含静态上下文，静态上下文由 PromptManager 管理）
            history_messages = self.history_loader.load_for_session(
                session_id=session_id,
                project_id=project_id,
                current_turn_id=turn_id,
                supports_vision=resolved_llm.supports_vision,
            )

            # 构建当前 turn 用户消息的多模态 content（含图片）
            # task: 纯文本任务描述，用于日志和标识
            # task_content: 实际传给 LLM 的内容，默认等于 task，但如果有图片附件则构造成多模态格式
            task_content: str | list[dict] = task
            user_message = self.conversation_service.message_repo.get_user_message_by_turn(turn_id)
            if user_message and user_message.attachments:
                content_parts = []
                if task.strip():
                    content_parts.append({"type": "text", "text": task})
                image_parts = convert_attachments_to_content_parts(
                    user_message.attachments, resolved_llm.supports_vision
                )
                content_parts.extend(image_parts)
                if content_parts:
                    task_content = content_parts

            loop_result = await execution_loop.run(
                task=task,
                task_content=task_content,
                project_path=project_path,
                run_id=run_id,
                session_id=session_id,
                history_messages=history_messages,
                agent_mode=agent_mode,
            )
            if loop_result.status != LoopStatus.COMPLETED:
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("运行失败: run_id=%s", run_id)
            await persist_and_broadcast("run:error", {"error": str(exc)})
        finally:
            self._runtime_adapters.pop(run_id, None)
            self._execution_loops.pop(run_id, None)
            self._cancel_events.pop(run_id, None)
            if approval_flow is not None and self._session_approval_flows.get(session_id) is approval_flow:
                self._session_approval_flows.pop(session_id, None)

    def _register_pending_approval(
        self,
        *,
        session_id: str,
        turn_id: str,
        run_id: str,
        data: dict,
    ) -> None:
        """将一次工具审批请求登记到 pending_approval_store，供后续用户批准/拒绝时查找。
        输入：session_id/turn_id/run_id（审批归属）、data（含 approval_id/arguments/approval 等原始数据）
        输出：无
        异常：ValueError（approval_id 缺失或为空）
        """
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
        """基于用户第一条消息，调用 LLM 异步生成简短会话标题并更新落库（作为独立后台任务运行，不阻塞主流程）。
        输入：llm（LLM 接口实例）、session_id、task（用户首条消息文本，用作生成标题的依据）
        逻辑：
          1. 若会话已不是默认标题（可能已被生成过或用户手动改过），直接跳过；
          2. 调用 LLM 生成不超过 20 字的标题，失败则截断 task 前 20 字兜底；
          3. 更新会话标题并广播 "session:title_updated" 事件通知前端刷新。
        输出：无；异常均被捕获记录日志，不向上抛出（不影响主执行流程）
        """
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

    async def cancel_run(self, run_id: str) -> Run:
        """取消一个正在执行（或等待审批）的 Run，等待其真正停止后写入取消事件。
        输入：run_id
        逻辑：
          1. 设置取消事件通知执行循环内部尽快退出；取消标题生成任务（若有）；
          2. 若主任务仍在运行，主动 cancel 并轮询等待其结束（最多 _CANCEL_WAIT_ATTEMPTS 次，
             每次间隔 _CANCEL_WAIT_INTERVAL_SECONDS），再 await 消化 CancelledError；
          3. 若 Run 已是终态（CANCELLED/COMPLETED/FAILED），直接返回当前状态（幂等）；
             其中若已是 CANCELLED，顺带清理该 run/session 的待审批记录；
          4. 否则通过 runtime_adapter（复用已有的或新建一个）落库 "run:cancelled" 事件，
             并在确认取消成功后清理待审批记录，最后广播新产生的事件。
        输出：取消后的 Run 对象
        异常：NotFoundValueError（Run 不存在）
        """
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
            self.pending_approval_store.expire_for_session(run.session_id)
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
            self.pending_approval_store.expire_for_session(run.session_id)
        await self._broadcast_conversation_events(
            session_id=run.session_id,
            events=persisted_events,
        )

        return cancelled

    async def reset_session(self, session_id: str) -> Session:
        """重置对话：先停后清。

        先在写锁外取消活跃 run（cancel_run 内部自取写锁并 await 任务真停，
        整段持锁会死锁），再交给 conversation_service 在写锁内重校验后清库。
        """
        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")

        conversation = self.conversation_service.get_snapshot(session_id)
        active_run_id = resolve_active_run_id_from_conversation(conversation)
        if active_run_id:
            try:
                await self.cancel_run(active_run_id)
            except Exception:
                logger.warning("重置前取消活跃运行失败: run_id=%s", active_run_id)

        reset_session = self.conversation_service.reset_session(session_id)
        self.cleanup_session_security_state(session_id)
        return reset_session

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
        """编辑历史消息（或重新生成 AI 回复）并重新调度执行（对 conversation_service.edit_and_rerun 的编排封装）。
        输入：project_id、session_id、message_id（目标消息）、new_content（新内容，可选）、
              provider_id/model_id（可选，指定本次使用的 LLM）
        逻辑：
          1. 校验项目、会话存在；
          2. 若会话当前有活跃运行，先尝试取消（失败仅记录警告，不阻断后续流程——旧运行的收尾是尽力而为）；
          3. 解析 LLM 配置，调用 conversation_service.edit_and_rerun 完成截断和新轮次创建；
          4. 广播新产生的事件，并调度新一轮 Agent 执行。
        输出：StartTurnResult（新轮次的 turn/run/user_message）
        异常：NotFoundValueError（项目或会话不存在）
        """
        project = self.project_repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")

        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")

        agent_mode = getattr(session, 'agent_mode', 'build') or 'build'
        permission_mode = getattr(session, 'permission_mode', 'auto') or 'auto'

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
            agent_mode=agent_mode,
            permission_mode=permission_mode,
        )
        return started

    def _register_sub_agent_loop(self, run_id: str, loop: RapidExecutionLoop) -> None:
        """记录一个正在运行的 SubAgent 执行循环，供审批恢复时定位（作为 SubAgentRunner 的 loop_started 回调）。
        输入：run_id（子 agent 的运行 ID，格式形如 "sub-run-*"）、loop（对应的执行循环实例）
        """
        self._sub_agent_execution_loops[run_id] = loop

    def _unregister_sub_agent_loop(self, run_id: str, loop: RapidExecutionLoop) -> None:
        """移除已结束的 SubAgent 执行循环记录（作为 SubAgentRunner 的 loop_finished 回调）。
        输入：run_id、loop（仅当当前记录确实是这个 loop 实例时才移除，防止竞态覆盖）
        """
        if self._sub_agent_execution_loops.get(run_id) is loop:
            self._sub_agent_execution_loops.pop(run_id, None)

    async def approve_tool_call(
        self, *, session_id: str, run_id: str, approval_id: str,
        decision: AllowApprovalDecision = "allow_once",
    ) -> None:
        """批准一次工具调用审批（用户点击"允许"/"始终允许"等操作的入口）。
        输入：session_id、run_id、approval_id（待批准的审批 ID）、
              decision（批准粒度："allow_once" 仅本次 / "trust_and_allow" 同时记为信任规则等）
        输出：无（内部委托 _decide_tool_call_approval 处理）
        """
        await self._decide_tool_call_approval(
            session_id=session_id,
            run_id=run_id,
            approval_id=approval_id,
            approval_event_type=EventType.APPROVAL_APPROVED,
            decision=decision,
        )

    async def deny_tool_call(self, *, session_id: str, run_id: str, approval_id: str) -> None:
        """拒绝一次工具调用审批（用户点击"拒绝"）。
        输入：session_id、run_id、approval_id
        输出：无
        """
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
        """处理审批决策的核心方法：批准则实际执行该工具调用并把结果喂回执行循环，拒绝则中止该调用。
        输入：session_id、run_id、approval_id、approval_event_type（APPROVAL_APPROVED/APPROVAL_DENIED）、
              decision（批准粒度，仅审批场景使用）
        逻辑（在会话写锁内执行，保证与其他事件写入互斥）：
          分两条路径处理，因为 SubAgent 的 Run 不落库（run_id 以 "sub-run-" 开头）：
          - SubAgent 审批路径：直接操作 pending_approval_store + approval_flow.set_approval_result
            恢复子 agent 执行，不涉及 conversation_service 的事件写入；
          - 主 Agent 审批路径：
            1. 校验 Run 存在、属于该会话、且正处于 WAITING_FOR_APPROVAL；校验待审批记录匹配且未处理；
            2. 批准时：若 decision 为 trust_and_allow，写入信任规则并级联自动批准其他匹配的待审批项；
               实际执行工具，将结果通过 execution_loop.set_approval_result 唤醒执行循环继续；
               若执行循环已不存在（如进程重启后恢复的孤儿审批），退化为直接把 Run 标记为终态完成；
            3. 拒绝时：唤醒执行循环并传入 None（表示拒绝），或同样退化为标记 Run 为 CANCELLED；
            4. 找到对应的工具追踪消息，追加状态更新事件（approved/denied）+ 审批决策事件 +
               （若走了退化路径）Run 终态事件，一次性写入并广播。
        输出：无
        异常：NotFoundValueError（Run/待审批记录/审批流不存在）、ValueError（归属不匹配/状态不合法）
        """
        is_sub_agent_run = run_id.startswith("sub-run-")

        with self.conversation_service.acquire_session_write_lock(session_id):
            # ── SubAgent 审批路径 ──
            # SubAgent 的 run 未存储到数据库，直接操作 approval_flow 恢复执行
            if is_sub_agent_run:
                pending = self.pending_approval_store.get(approval_id)
                if pending is None:
                    raise NotFoundValueError("审批不存在")
                if pending.session_id != session_id:
                    raise ValueError("审批不属于当前会话")
                if pending.run_id != run_id:
                    raise ValueError("审批不属于当前运行")
                if pending.status != "pending":
                    raise ValueError("审批已处理")

                approval_flow = self._session_approval_flows.get(session_id)
                if approval_flow is None:
                    logger.error("[SubAgent Approval] approval_flow not found for session_id=%s", session_id)
                    raise NotFoundValueError("审批流不存在")

                logger.info("[SubAgent Approval] Processing approval: session_id=%s, run_id=%s, approval_id=%s, decision=%s", session_id, run_id, approval_id, decision)

                if approval_event_type == EventType.APPROVAL_APPROVED:
                    self.pending_approval_store.approve(approval_id, decision=decision)
                    if decision == "trust_and_allow":
                        self._add_trust_rules_from_approval(pending, session_id)
                    # 执行已审批的工具，将执行结果通过 approval_flow 返回给 SubAgent
                    execution_result = await self._execute_approved_tool(pending, run_id=run_id)
                    logger.info("[SubAgent Approval] Tool executed: success=%s, calling set_approval_result", execution_result.success)
                    approval_flow.set_approval_result({
                        "success": execution_result.success,
                        "output": execution_result.output,
                        "error": execution_result.error,
                    }, approval_id=approval_id)
                    logger.info("[SubAgent Approval] set_approval_result called for approval_id=%s", approval_id)
                else:
                    self.pending_approval_store.deny(approval_id)
                    logger.info("[SubAgent Approval] Denying approval, calling set_approval_result(None)")
                    approval_flow.set_approval_result(None, approval_id=approval_id)
                return

            # ── 主 Agent 审批路径 ──
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

            terminal_event_type: EventType | None = None
            terminal_payload: dict | None = None

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
                    }, approval_id=approval_id)
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
                    loop.set_approval_result(None, approval_id=approval_id)
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
        """使用审批时存储的决策数据，实际执行一个已获批准的工具调用。
        输入：pending（待审批记录，含 tool_name/tool_arguments/approval_payload）、run_id（用于定位工具注册中心）
        逻辑：
          1. 从 approval_payload 中取出之前存储的 approved_decision（工具自身在请求审批时存入的决策数据），
             缺失则直接返回失败（说明审批数据不完整，无法安全执行）；
          2. 若存在权限提升请求（elevation_request，如沙箱网络/路径提权），一并塞入决策数据；
          3. 优先复用当前运行（主或子 agent）关联的工具注册中心，取不到则按决策中的 cwd 现建一个；
          4. 定位对应工具，调用其 execute，把 _approved_decision 传入使工具跳过重新评估、直接按存储决策执行
             （通用机制：任何返回 approval_required 的工具都需支持接收 _approved_decision 参数）。
        输出：ToolResult（执行结果；工具不存在或执行异常均包装为失败结果，不向上抛出）
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
        loop = self._execution_loops.get(run_id) or self._sub_agent_execution_loops.get(run_id)
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
        """在指定运行所属轮次的消息列表中，查找记录该审批请求的工具追踪消息。
        输入：run_id、approval_id
        输出：匹配的 Message（message_type=TOOL_TRACE 且 payload_json.approval_id 匹配），找不到或 Run 不存在返回 None
        """
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
        """根据一次审批的"始终允许"决策，为会话写入对应的信任规则（后续匹配的操作可自动放行）。
        输入：pending（待审批记录，含 approval_payload 中建议的信任规则）、session_id
        逻辑：
          - access_type 为 external_path_read（外部路径读取）：从 suggested_prefix_rule 或
            suggested_trust.prefix 中取路径前缀列表，逐个写入 "external_path" 类型信任规则；
          - 否则优先使用 approval_payload.suggested_trust（permission+pattern）写入单条规则；
            若无该结构，回退兼容旧格式：从 suggested_prefix_rule / suggested_trust.prefix
            取前缀列表，写入 "shell" 类型信任规则（可能同时命中两处从而写入多条规则，是历史兼容逻辑）。
        输出：无（直接写入 self.trust_store）
        """
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

    async def _cascade_auto_approve(self, session_id: str) -> None:
        """在写入一条"始终允许"的信任规则后，级联检查该会话下其余待审批项，凡是能匹配新规则的
        一并自动批准（避免用户对同一批相似操作反复确认）。
        输入：session_id
        逻辑：遍历会话下所有 pending 状态的待审批记录，按 approval_kind/access_type 分类匹配：
          - external_path_read：路径是否匹配 "external_path" 信任规则；
          - sandbox_network_elevation：是否已有 "sandbox_network" 全局放行规则；
          - sandbox_path_elevation：请求的所有 denied_paths 是否都匹配 "sandbox_path" 规则；
          - 其余（默认按 shell 命令处理）：命令是否匹配 "shell" 信任规则。
          命中则调用 approve_tool_call 自动批准（decision="allow_once"，因为信任规则已经生效，
          不需要再重复写入）。
        输出：无
        """
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

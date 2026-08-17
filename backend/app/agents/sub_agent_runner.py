"""
SubAgentRunner — 在内存中执行独立 Agent Loop 的引擎。

复用 RapidExecutionLoop 实现，但：
- 不走 Task → Execution → SSE 链路
- 工具集排除 delegate（防递归）
- temperature 设为 parent 的 60%（更确定性）
- 可选 event_callback：提供时将子 agent 执行事件实时推送到前端
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any, TYPE_CHECKING

from app.config.settings import ConfigManager

# 事件回调类型签名（与 RapidExecutionLoop 一致）
EventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

from app.execution.models import LoopResult, LoopStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.runtime_tool_definitions import ToolSetConfig
from app.llm import LLMAdapterFactory
from app.llm.base import UniversalLLMInterface
from app.models.llm_config import ResolvedLLMConfig
from app.tools.base import BaseTool
from app.tools.edit_tool import EditTool
from app.tools.explore_tool import ExploreTool
from app.tools.file_tool import FileTool
from app.tools.glob_tool import GlobTool
from app.tools.grep_tool import GrepTool
from app.tools.patch_tool import PatchTool
from app.tools.shell_tool import ShellTool
from app.tools.skill_tool import SkillTool
from app.tools.registry import ToolRegistry
from app.tools.working_memory_tool import WorkingMemoryTool

LoopLifecycleCallback = Callable[[str, RapidExecutionLoop], None]

if TYPE_CHECKING:
    from app.execution.approval_flow import ApprovalFlow

logger = logging.getLogger(__name__)

# Sub-agent 工具集中排除的工具（防递归调用和复用主会话态工具）
_SUB_AGENT_EXCLUDED_TOOLS: frozenset[str] = frozenset({"delegate", "plan", "browser"})


@dataclass
class SubAgentResult:
    """Sub-agent 执行结果"""

    output: str
    steps_taken: int
    tool_calls: list[dict[str, Any]]
    status: str  # "completed" | "failed" | "cancelled"
    loop_result: LoopResult | None = None


async def _noop_event_callback(event: str, data: dict[str, Any]) -> None:
    """
    空事件回调（默认值）

    参数：event 事件类型名，data 事件数据；不做任何处理，直接丢弃
    用途：未注入 event_callback 时，sub-agent 不广播 SSE 事件
    """
    pass


def _clone_tool_for_sub_agent(tool: BaseTool) -> BaseTool:
    """
    为 sub-agent 克隆一份工具实例，避免与父级共享带运行态的工具对象

    参数：tool 父级 ToolRegistry 中的原始工具实例
    逻辑：对持有单次运行状态的工具类型（WorkingMemoryTool、FileTool、GrepTool、
    GlobTool、EditTool、PatchTool、ExploreTool、SkillTool）逐一构造新实例，
    复用其内部的安全策略/依赖对象；其余无状态工具直接原样返回
    返回：可安全用于 sub-agent 的工具实例（新建或原对象）
    """
    if isinstance(tool, WorkingMemoryTool):
        return WorkingMemoryTool()
    if isinstance(tool, FileTool):
        return FileTool(tool.security)
    if isinstance(tool, GrepTool):
        return GrepTool(tool.security)
    if isinstance(tool, GlobTool):
        return GlobTool(tool.security)
    if isinstance(tool, EditTool):
        return EditTool(tool.security)
    if isinstance(tool, PatchTool):
        return PatchTool(tool.security)
    if isinstance(tool, ExploreTool):
        return ExploreTool(tool._path_security)
    if isinstance(tool, SkillTool):
        return SkillTool(tool._registry, resolver=tool._resolver)
    return tool


def _build_filtered_registry(parent_registry: ToolRegistry, *, session_id: str | None = None) -> ToolRegistry:
    """
    从父级 ToolRegistry 构建子 agent 专用的过滤版本

    参数：
        parent_registry: 父级（主 Agent）的完整工具注册表
        session_id: 子 agent 会话 ID，用于给 ShellTool 绑定独立会话
    逻辑：遍历父级已注册工具，剔除 _SUB_AGENT_EXCLUDED_TOOLS 中的工具（防递归），
    其余工具调用 _clone_tool_for_sub_agent 克隆隔离实例；若克隆结果是 ShellTool
    且提供了 session_id，则额外重建一个绑定该 session_id 的 ShellTool
    返回：仅包含子 agent 可用工具的新 ToolRegistry
    """
    filtered = ToolRegistry()
    for name in parent_registry.list_tools():
        if name not in _SUB_AGENT_EXCLUDED_TOOLS:
            tool = parent_registry.get(name)
            if tool is not None:
                cloned = _clone_tool_for_sub_agent(tool)
                if isinstance(cloned, ShellTool) and session_id:
                    cloned = ShellTool(
                        cloned.security,
                        cloned.path_security,
                        cloned.registry,
                        cloned.sandbox,
                        session_id=session_id,
                        trust_store=cloned.trust_store,
                        permission_mode=cloned.permission_mode,
                    )
                filtered.register(cloned)
    return filtered


class SubAgentRunner:
    """
    在内存中运行一个完整的 Agent Loop。

    复用 RapidExecutionLoop，但不走 Task → Execution → SSE 链路。
    Sub-agent 的工具集从父级 ToolRegistry 复制，但排除 delegate（防递归）。
    """

    # 子 agent 默认最大步数（从配置读取，每次实例化时获取最新值）

    def __init__(
        self,
        *,
        task: str,
        llm_config: ResolvedLLMConfig,
        parent_tool_registry: ToolRegistry,
        input_data: dict[str, Any] | None = None,
        expected_output: str | None = None,
        max_steps: int | None = None,
        project_path: str | None = None,
        session_id: str | None = None,
        event_callback: EventCallback | None = None,
        parent_approval_flow: ApprovalFlow | None = None,  # 主 Agent 的审批流（用于共享审批逻辑）
        loop_started: LoopLifecycleCallback | None = None,
        loop_finished: LoopLifecycleCallback | None = None,
    ):
        """
        初始化 SubAgentRunner

        参数：
            task: 子任务描述文本
            llm_config: 已解析的 LLM 配置（模型、密钥等）
            parent_tool_registry: 父级（主 Agent）的工具注册表，用于派生子 agent 工具集
            input_data: 传给子任务的输入数据，可为 None
            expected_output: 子任务预期输出说明，可为 None
            max_steps: 子 agent 最大执行步数，为 None 时读取 ConfigManager 的默认配置
            project_path: 子任务所在项目路径
            session_id: 子 agent 会话 ID，为 None 时自动生成 "sub-xxxxxxxx"
            event_callback: 外部注入的事件回调，用于实时推送子 agent 执行事件到前端
            parent_approval_flow: 主 Agent 的审批流实例，子 agent 复用以共享审批逻辑
            loop_started: RapidExecutionLoop 启动时的生命周期回调
            loop_finished: RapidExecutionLoop 结束时的生命周期回调
        逻辑：保存各配置项，从父级 ToolRegistry 过滤出子 agent 可用的工具集（排除 delegate 等）
        """
        self._task = task
        self._llm_config = llm_config
        self._input_data = input_data
        self._expected_output = expected_output
        # 优先使用调用方指定的 max_steps，否则从 ConfigManager.subagent.max_steps 获取最新配置值
        self._max_steps = max_steps or ConfigManager().settings.subagent.max_steps
        self._project_path = project_path
        self._session_id = session_id or f"sub-{uuid.uuid4().hex[:8]}"
        # 外部注入的事件回调（提供时实时推送子 agent 执行事件到前端）
        self._event_callback: EventCallback | None = event_callback
        # 主 Agent 的审批流（SubAgent 通过共享此实例，将审批请求路由到主 Agent）
        self._parent_approval_flow = parent_approval_flow
        self._loop_started = loop_started
        self._loop_finished = loop_finished

        # 从父级 registry 构建过滤版本（排除 delegate）
        self._tool_registry = _build_filtered_registry(
            parent_tool_registry,
            session_id=self._session_id,
        )

        logger.info(
            "SubAgentRunner 初始化: task=%.80s, max_steps=%d, tools=%s",
            task,
            self._max_steps,
            self._tool_registry.list_tools(),
        )

    async def run(self) -> SubAgentResult:
        """
        执行 sub-agent 的完整 Agent Loop

        逻辑：创建 LLM 适配器 -> 构建 RapidExecutionLoop（复用父 Agent 的审批流、
        包装事件回调注入 run_id）-> 拼装 task_content（任务+输入数据+预期输出）
        -> 运行 loop 并捕获异常 -> 从 LoopResult 提取结果
        返回：SubAgentResult，异常时 status="failed" 且 output 为异常信息
        """
        # 1. 创建 LLM 适配器
        llm: UniversalLLMInterface = LLMAdapterFactory.create(self._llm_config)

        # 4. 执行 loop（先生成 run_id，用于包装事件回调）
        run_id = f"sub-run-{uuid.uuid4().hex[:8]}"
        logger.info("SubAgent 开始执行: run_id=%s", run_id)

        # 2. 创建 RapidExecutionLoop（使用注入的 event_callback 或 no-op）
        # 如果提供了主 Agent 的 approval_flow，则复用它（实现审批共享）
        # 包装事件回调，自动注入 run_id 到所有事件 payload 中（前端需要此字段关联审批请求）
        base_callback = self._event_callback or _noop_event_callback
        
        async def callback_with_run_id(event_type: str, data: dict[str, Any]) -> None:
            """
            包装事件回调，自动添加 run_id 到 payload 中。
            - run_id: SubAgent 的运行 ID（如 sub-run-xxx）
            注意：parent_session_id 由 delegate_tool.py 在外层回调中注入，
            此处不设置，避免覆盖正确的父 session ID。
            """
            enriched_data = {**data, "run_id": run_id}
            await base_callback(event_type, enriched_data)
        
        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self._tool_registry,
            max_steps=self._max_steps,
            event_callback=callback_with_run_id,
            approval_flow=self._parent_approval_flow,  # 共享主 Agent 的审批流
            # 子 agent 任务通常已明确要执行的操作（如指定的 shell 命令），跳过主 Agent
            # 那套"首轮只给探索工具"的门禁，否则第一轮看不到 shell 会误报"没有该工具"
            tool_set_config=ToolSetConfig(skip_exploration_gate=True),
        )
        if self._loop_started is not None:
            self._loop_started(run_id, loop)

        # 3. 构建 task_content（包含 input_data 和 expected_output）
        task_content = self._build_task_content()

        try:
            loop_result: LoopResult = await loop.run(
                task=self._task,
                task_content=task_content,
                project_path=self._project_path,
                run_id=run_id,
                session_id=self._session_id,
                agent_mode="build",
            )
        except Exception as e:
            logger.error("SubAgent 执行异常: %s", e, exc_info=True)
            return SubAgentResult(
                output=f"子任务执行异常: {e}",
                steps_taken=0,
                tool_calls=[],
                status="failed",
            )
        finally:
            if self._loop_finished is not None:
                self._loop_finished(run_id, loop)

        # 5. 提取结果
        return self._extract_result(loop_result)

    def _build_task_content(self) -> str:
        """
        拼装传递给 LLM 的完整任务内容

        逻辑：以 self._task 为基础，若存在 input_data / expected_output 则分别
        追加对应小节
        返回：拼接后的任务描述字符串
        """
        parts = [self._task]

        if self._input_data:
            parts.append(f"\n\n## 输入数据\n{self._input_data}")

        if self._expected_output:
            parts.append(f"\n\n## 预期输出\n{self._expected_output}")

        return "\n".join(parts)

    def _extract_result(self, loop_result: LoopResult) -> SubAgentResult:
        """
        将 RapidExecutionLoop 的原始结果转换为对外的 SubAgentResult

        参数：loop_result 循环执行完成后的 LoopResult 对象
        逻辑：取 loop_result.result 作为最终输出文本；遍历 steps 汇总每步的
        工具调用信息（截断过长的 output）；将 LoopStatus 映射为字符串状态
        返回：包含 output/steps_taken/tool_calls/status/loop_result 的 SubAgentResult
        """
        # 提取最后一条 assistant 消息作为 output
        output = loop_result.result or ""

        # 统计 tool calls
        tool_calls = []
        for step in loop_result.steps:
            tool_calls.append(
                {
                    "tool": step.tool,
                    "args": step.args,
                    "status": step.status.value,
                    "output": (step.output or "")[:500],  # 截断过长输出
                    "error": step.error,
                }
            )

        # 确定状态
        status_map = {
            LoopStatus.COMPLETED: "completed",
            LoopStatus.CANCELLED: "cancelled",
            LoopStatus.FAILED: "failed",
        }
        status = status_map.get(loop_result.status, "completed")

        logger.info(
            "SubAgent 执行完成: status=%s, steps=%d",
            status,
            len(loop_result.steps),
        )

        return SubAgentResult(
            output=output,
            steps_taken=len(loop_result.steps),
            tool_calls=tool_calls,
            status=status,
            loop_result=loop_result,
        )

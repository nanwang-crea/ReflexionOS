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
from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import Callable, Coroutine
from typing import Any, TYPE_CHECKING

from app.config.settings import ConfigManager

# 事件回调类型签名（与 RapidExecutionLoop 一致）
EventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

from app.execution.models import LoopResult, LoopStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm import LLMAdapterFactory
from app.llm.base import UniversalLLMInterface
from app.models.llm_config import ResolvedLLMConfig
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.execution.approval_flow import ApprovalFlow

logger = logging.getLogger(__name__)

# Sub-agent 工具集中排除的工具（防递归调用）
_SUB_AGENT_EXCLUDED_TOOLS: frozenset[str] = frozenset({"delegate"})


@dataclass
class SubAgentResult:
    """Sub-agent 执行结果"""

    output: str
    steps_taken: int
    tool_calls: list[dict[str, Any]]
    status: str  # "completed" | "failed" | "cancelled"
    loop_result: LoopResult | None = None


async def _noop_event_callback(event: str, data: dict[str, Any]) -> None:
    """No-op event callback — sub-agent 不广播 SSE 事件"""
    pass


def _build_filtered_registry(parent_registry: ToolRegistry) -> ToolRegistry:
    """从父级 ToolRegistry 构建子 agent 的过滤版本（排除 delegate 等工具）"""
    filtered = ToolRegistry()
    for name in parent_registry.list_tools():
        if name not in _SUB_AGENT_EXCLUDED_TOOLS:
            tool = parent_registry.get(name)
            if tool is not None:
                filtered.register(tool)
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
    ):
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

        # 从父级 registry 构建过滤版本（排除 delegate）
        self._tool_registry = _build_filtered_registry(parent_tool_registry)

        logger.info(
            "SubAgentRunner 初始化: task=%.80s, max_steps=%d, tools=%s",
            task,
            self._max_steps,
            self._tool_registry.list_tools(),
        )

    async def run(self) -> SubAgentResult:
        """执行 sub-agent loop，返回结果"""
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
            包装事件回调，自动添加 run_id 和 parent_session_id 到 payload 中。
            - run_id: SubAgent 的运行 ID（如 sub-run-xxx）
            - parent_session_id: 父 Agent 的 session ID，用于前端路由审批响应到正确的 WebSocket 连接
            """
            enriched_data = {**data, "run_id": run_id, "parent_session_id": self._session_id}
            await base_callback(event_type, enriched_data)
        
        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self._tool_registry,
            max_steps=self._max_steps,
            event_callback=callback_with_run_id,
            approval_flow=self._parent_approval_flow,  # 共享主 Agent 的审批流
        )

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

        # 5. 提取结果
        return self._extract_result(loop_result)

    def _build_task_content(self) -> str:
        """构建传递给 LLM 的 task content"""
        parts = [self._task]

        if self._input_data:
            parts.append(f"\n\n## 输入数据\n{self._input_data}")

        if self._expected_output:
            parts.append(f"\n\n## 预期输出\n{self._expected_output}")

        return "\n".join(parts)

    def _extract_result(self, loop_result: LoopResult) -> SubAgentResult:
        """从 LoopResult 提取 SubAgentResult"""
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

"""
SubAgentRunner — 在内存中执行独立 Agent Loop 的引擎。

复用 RapidExecutionLoop 实现，但：
- 不走 Task → Execution → SSE 链路
- 使用 no-op event callback（不广播事件）
- 工具集排除 delegate（防递归）
- temperature 设为 parent 的 60%（更确定性）
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.execution.models import LoopResult, LoopStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm import LLMAdapterFactory
from app.llm.base import UniversalLLMInterface
from app.models.llm_config import ResolvedLLMConfig
from app.tools.registry import ToolRegistry

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

    # 子 agent 默认最大步数
    DEFAULT_MAX_STEPS = 50

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
    ):
        self._task = task
        self._llm_config = llm_config
        self._input_data = input_data
        self._expected_output = expected_output
        self._max_steps = max_steps or self.DEFAULT_MAX_STEPS
        self._project_path = project_path
        self._session_id = session_id or f"sub-{uuid.uuid4().hex[:8]}"

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

        # 2. 创建 RapidExecutionLoop（no-op event callback）
        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self._tool_registry,
            max_steps=self._max_steps,
            event_callback=_noop_event_callback,
        )

        # 3. 构建 task_content（包含 input_data 和 expected_output）
        task_content = self._build_task_content()

        # 4. 执行 loop
        run_id = f"sub-run-{uuid.uuid4().hex[:8]}"
        logger.info("SubAgent 开始执行: run_id=%s", run_id)

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

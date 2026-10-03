"""
文件功能：录制回放测试的端到端场景用例（E-01 / E-02 / E-03）
文件描述：用 ReplayLLM 驱动真实 RapidExecutionLoop 完整回放三个核心场景——
         纯问答直接完成、一次只读工具调用后完成、工具异常后恢复完成。
         断言归一化事件序列与 LoopResult 终态同夹具基线一致，
         且夹具响应恰好全部消费（由 run_scenario 内部强校验）。
注意点：tool-call-then-complete 使用真实 GrepTool 作用于 tmp_path 准备的
        文件树（经 PathSecurity 放行），夹具中的 "${WORK_DIR}" 占位符由
        run_scenario 的 variables 替换，保证夹具跨平台、与运行环境无关。
"""

from pathlib import Path
from typing import Any

import pytest

from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult
from app.tools.grep_tool import GrepTool
from app.tools.registry import ToolRegistry
from tests.support.replay_harness import assert_replay, run_scenario

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "replay"


class ExplodingTool(BaseTool):
    """执行时必抛异常的受控故障工具，用于覆盖 tool:error 恢复路径。"""

    @property
    def name(self) -> str:
        """工具名。入参：无。出参：str - 固定为 explode。"""
        return "explode"

    @property
    def description(self) -> str:
        """工具描述。入参：无。出参：str - 固定文案。"""
        return "A tool that always raises during execution (test double)"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """直接抛出运行时异常，模拟工具执行期故障。

        入参：args (dict) - 调用参数（不消费）。
        出参：无（永不返回，总是抛出 RuntimeError）。
        """
        raise RuntimeError("boom")


def _registry_with(*tools: BaseTool) -> ToolRegistry:
    """把若干工具实例注册进一个新注册表。

    入参：tools (BaseTool) - 可变长工具实例列表。
    出参：ToolRegistry - 装配完成的注册表。
    """
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


class TestReplayScenarios:
    """三个核心场景的端到端回放"""

    @pytest.mark.asyncio
    async def test_simple_completion(self):
        """E-01：纯问答，模型直接返回内容 → completed，全程无 tool:* 事件。

        入参：无。出参：无（断言即验证）。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "simple-completion.json",
            _registry_with(),
        )

        assert_replay(result, events, fixture.expected)
        event_types = [t for t, _ in events]
        assert not any(t.startswith("tool:") for t in event_types)
        assert "ReflexionOS" in (result.result or "")

    @pytest.mark.asyncio
    async def test_tool_call_then_complete(self, tmp_path):
        """E-02：grep 只读调用（真实 GrepTool 作用于临时文件树）→ 总结完成。

        入参：tmp_path (pytest 临时目录) - 预置一个含关键词的源码文件。
        出参：无。
        """
        (tmp_path / "main.py").write_text(
            "class ReflexionOS:\n    pass\n", encoding="utf-8"
        )
        registry = _registry_with(
            GrepTool(PathSecurity(allowed_base_paths=[str(tmp_path)]))
        )

        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "tool-call-then-complete.json",
            registry,
            variables={"WORK_DIR": str(tmp_path)},
        )

        assert_replay(result, events, fixture.expected)
        tool_results = [p for t, p in events if t == "tool:result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is True

    @pytest.mark.asyncio
    async def test_tool_error_recovery(self):
        """E-03：工具抛异常 → tool:error → 循环恢复并完成。

        入参：无。出参：无。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "tool-error-recovery.json",
            _registry_with(ExplodingTool()),
        )

        assert_replay(result, events, fixture.expected)
        tool_errors = [p for t, p in events if t == "tool:error"]
        assert len(tool_errors) == 1
        assert "boom" in (tool_errors[0]["error"] or "")

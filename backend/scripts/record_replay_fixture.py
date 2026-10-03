"""
文件功能：回放夹具录制脚本（需真实 API key，由持 key 者手动执行）
文件描述：用 RecordingLLM 包装真实 OpenAIAdapter 驱动 RapidExecutionLoop 跑一次
         真实任务，把 LLM 响应序列、捕获的事件序列与终态落盘为回放夹具 JSON，
         供 keyless 回放测试（test_replay.py）使用。
用法：
    python backend/scripts/record_replay_fixture.py \
        --scenario my-scenario --task "在工作目录搜索关键词并总结"
退出码：0 成功；2 未配置模型/缺 API key；1 任务执行失败。
注意：生成的 expected 基线来自本次实际运行，**必须人工核对合理性**
     （对照 docs/event-map.md 与状态机逻辑）后再提交，禁止照抄未核对的输出。
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# 让脚本可直接以文件路径运行：把 backend 根目录加入 import 路径（与 conftest 同法）
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.rapid_loop import RapidExecutionLoop
from app.llm.openai_adapter import OpenAIAdapter
from app.security.path_security import PathSecurity
from app.services.llm_provider_service import LLMProviderService
from app.tools.grep_tool import GrepTool
from app.tools.registry import ToolRegistry
from tests.support.recording_llm import RecordingLLM
from tests.support.replay_fixture import (
    ExpectedOutcome,
    ReplayFixture,
    save_fixture,
)
from tests.support.replay_harness import normalize_event_types

FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures" / "replay"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    入参：无（读 sys.argv）。
    出参：argparse.Namespace - 含 scenario / task / max_steps / output。
    """
    parser = argparse.ArgumentParser(
        description="录制回放测试夹具（需要已配置可用的 LLM 供应商与 API key）"
    )
    parser.add_argument("--scenario", required=True, help="场景名，即夹具文件名（不含 .json）")
    parser.add_argument("--task", required=True, help="要真实执行一次的任务描述")
    parser.add_argument("--max-steps", type=int, default=10, help="单 run 最大步数（默认 10）")
    parser.add_argument(
        "--output",
        default=None,
        help="夹具输出路径（默认 backend/tests/fixtures/replay/<scenario>.json）",
    )
    return parser.parse_args()


def build_registry(work_dir: str) -> ToolRegistry:
    """装配录制用的工具注册表（当前只注册真实 GrepTool，作用于工作目录内）。

    入参：work_dir (str) - 允许访问的根目录（PathSecurity 放行范围）。
    出参：ToolRegistry - 装配完成的注册表。
    """
    registry = ToolRegistry()
    registry.register(GrepTool(PathSecurity(allowed_base_paths=[work_dir])))
    return registry


async def record(args: argparse.Namespace) -> int:
    """执行一次真实任务并落盘夹具。

    入参：args (argparse.Namespace) - 命令行参数。
    功能：解析当前默认 LLM 配置（失败即退出码 2）→ 组装
         RecordingLLM(OpenAIAdapter) + 事件捕获 + 主循环 → 跑任务 →
         用录制响应与归一化事件序列生成夹具并保存。
    出参：int - 退出码（0 成功 / 1 执行失败 / 2 配置缺失）。
    """
    try:
        resolved = LLMProviderService().resolve_llm_config()
    except ValueError as exc:
        print(f"[错误] 无法解析当前 LLM 配置：{exc}")
        print("请先在 ReflexionOS 设置中配置默认供应商与模型，再重新录制。")
        return 2
    if not resolved.api_key:
        print("[错误] 当前默认供应商未配置 API key，无法录制。")
        print("请先配置 API key（回放测试本身不需要 key，只有录制需要）。")
        return 2

    recording = RecordingLLM(OpenAIAdapter(resolved))
    captured: list[tuple[str, dict]] = []

    async def capture(event_type: str, payload: dict) -> None:
        """事件捕获回调。入参：事件类型与负载。出参：无。"""
        captured.append((event_type, payload))

    loop = RapidExecutionLoop(
        llm=recording,
        tool_registry=build_registry(str(BACKEND_ROOT)),
        max_steps=args.max_steps,
        event_callback=capture,
    )

    try:
        result = await loop.run(args.task)
    except Exception as exc:  # 真实任务失败也要明确报告，不产出半成品夹具
        print(f"[错误] 任务执行失败：{exc}")
        return 1

    fixture = ReplayFixture(
        scenario=args.scenario,
        description="（待人工核对：请在此填写基线核对要点后再提交）",
        recorded_at=date.today().isoformat(),
        model=recording.get_model_name(),
        task=args.task,
        responses=recording.recorded,
        expected=ExpectedOutcome(
            loop_status=result.status.value,
            event_sequence=normalize_event_types(captured),
        ),
    )

    output = Path(args.output) if args.output else FIXTURE_DIR / f"{args.scenario}.json"
    save_fixture(fixture, output)

    print("=" * 60)
    print(f"夹具已生成: {output}")
    print(f"录制响应 {len(fixture.responses)} 条，事件序列 {len(fixture.expected.event_sequence)} 条")
    print("!! 提交前必须人工核对 expected 基线的合理性（对照 docs/event-map.md），")
    print("!! 并把核对要点写进夹具 description 字段。")
    print("=" * 60)
    return 0


def main() -> int:
    """脚本入口：解析参数并驱动 asyncio 事件循环执行录制。

    入参：无。
    出参：int - 进程退出码。
    """
    return asyncio.run(record(parse_args()))


if __name__ == "__main__":
    sys.exit(main())

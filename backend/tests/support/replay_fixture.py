"""
文件功能：回放测试夹具（ReplayFixture）的数据模型与 JSON 读写
文件描述：定义录制回放测试的夹具文件结构——一次任务执行中 LLM 的按序响应列表
         （RecordedResponse）、期望的执行结果（ExpectedOutcome）以及顶层夹具
         （ReplayFixture）。夹具以 JSON 文件形式存于 tests/fixtures/replay/ 下，
         供 ReplayLLM 播放、replay_harness 断言。
核心逻辑：全部使用 pydantic 模型，load/save 走 model_validate / model_dump，
         保证 JSON 与内存对象严格互转（round-trip）；usage（token 统计）字段
         录制但属易变数据，不参与任何断言。
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class RecordedToolCall(BaseModel):
    """录制的一次工具调用（对应 app.llm.base.LLMToolCall 的可序列化子集）

    id: 工具调用唯一标识（回放时保持录制值，保证 tool_call_id 关联稳定）
    name: 被调用的工具名称
    arguments: 调用参数（已解析为字典）
    """

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class RecordedResponse(BaseModel):
    """录制的一条 LLM 响应（对应一次 complete / stream_collect 调用的聚合结果）

    method: 该响应录制自哪种调用入口——"complete"（非流式）或 "stream"
            （stream_complete / stream_collect）。回放时 ReplayLLM 会校验
            实际被调用的方法与记录一致，用于抓住"主循环换了 LLM 调用入口"
            这类行为漂移。
    content / reasoning_content: 正文 / 推理内容（无则为 None）
    tool_calls: 本次响应携带的工具调用列表
    finish_reason: 结束原因（stop / tool_calls / length）
    usage: token 统计，仅录制存档用，属易变字段，不参与断言
    """

    method: Literal["complete", "stream"]
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[RecordedToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    """一条脚本的审批决策（回放时按顺序消费，与 responses 同理）

    tool_call_id: 目标工具调用 id——决策器用它与 approval:required 事件
                  负载校验，防止决策脚本与场景错位
    action: "approve"（批准并回填工具输出）或 "reject"（拒绝，回填 None）
    output: 批准时回填的工具输出（reject 时忽略）
    error: 批准但执行失败时回填的错误信息（reject 时忽略）
    success: 批准路径的执行成功标记（对应 tool:result 的 success 与
             run:resuming 的 execution_success）
    """

    tool_call_id: str
    action: Literal["approve", "reject"]
    output: str | None = None
    error: str | None = None
    success: bool = True


class ExpectedOutcome(BaseModel):
    """期望的执行结果（回放断言的基线）

    loop_status: LoopResult.status 的字符串值（如 "completed"）
    event_sequence: 归一化后的事件类型序列（连续同类事件已折叠为单条），
                    由 replay_harness.normalize_event_types 产出的形式填写；
                    首次跑通后须人工核对合理性再回填，禁止照抄未核对的输出
    """

    loop_status: str
    event_sequence: list[str]


class ReplayFixture(BaseModel):
    """回放测试夹具顶层结构（一个 JSON 文件对应一个场景）

    scenario: 场景标识（与文件名一致，如 "tool-call-then-complete"）
    description: 场景说明；基线经人工核对后，核对要点也记录在此
    recorded_at: 录制/创建日期（YYYY-MM-DD）
    model: 录制时使用的模型名（回放时由 ReplayLLM.get_model_name 返回，
           影响 PromptManager 等与模型名相关的逻辑，需与录制时一致）
    task: 回放时提交给主循环的任务描述文本
    responses: 按调用顺序排列的 LLM 响应列表，回放时逐条消费
    expected: 期望结果基线
    approval_decisions: 审批决策脚本（可选，缺省空列表——旧格式夹具
                       无此字段时走默认值，向后兼容）
    """

    scenario: str
    description: str = ""
    recorded_at: str = ""
    model: str = "deepseek-chat"
    task: str = "总结这个仓库"
    responses: list[RecordedResponse]
    expected: ExpectedOutcome
    approval_decisions: list[ApprovalDecision] = Field(default_factory=list)


def load_fixture(path: str | Path) -> ReplayFixture:
    """从 JSON 文件加载回放夹具。

    入参：path (str | Path) - 夹具 JSON 文件路径。
    功能：读取文件内容并校验为 ReplayFixture；文件缺失或结构非法时抛出
         对应异常（FileNotFoundError / pydantic.ValidationError）。
    出参：ReplayFixture - 校验通过的夹具对象。
    """
    raw = Path(path).read_text(encoding="utf-8")
    return ReplayFixture.model_validate(json.loads(raw))


def save_fixture(fixture: ReplayFixture, path: str | Path) -> None:
    """将回放夹具保存为 JSON 文件。

    入参：fixture (ReplayFixture) - 待保存的夹具对象；
         path (str | Path) - 目标文件路径（父目录需已存在）。
    功能：以 UTF-8、缩进 2 格、不转义非 ASCII 字符的格式写盘，
         保证夹具文件可直接阅读与手工编辑。
    出参：无。
    """
    Path(path).write_text(
        json.dumps(fixture.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

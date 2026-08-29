"""
文件功能：任务执行引擎的核心数据模型
文件描述：定义执行循环（Loop）中流转的各类状态枚举与数据结构，包括单步执行状态、
         Agent 运行模式、单个执行步骤记录、整轮 Loop 的结果，以及状态机阶段与运行时
         可变状态快照。这些模型贯穿 plan_engine / rapid_loop / tool_call_executor 等
         执行引擎模块，是它们之间传递状态的统一数据契约。
核心逻辑：以 pydantic BaseModel 承载可序列化的持久化/传输数据（LoopStep、LoopResult），
         以 dataclass 承载仅在单次 run 内存中流转的可变状态（RuntimeState），两者职责
         分离：前者用于落库、返回给前端；后者只服务于状态机 handler 内部的阶段推进。
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.llm.base import LLMResponse
from app.models.conversation import RunStatus as LoopStatus


class StepStatus(str, Enum):
    """单个执行步骤（工具调用）的状态：待执行 → 执行中 → (等待审批) → 成功/失败"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    SUCCESS = "success"
    FAILED = "failed"


class AgentMode(str, Enum):
    """Agent 运行模式：BUILD 为直接执行改动，PLAN 为仅规划不落地改动"""

    BUILD = "build"
    PLAN = "plan"


class LoopStep(BaseModel):
    """
    单个执行步骤的记录，对应一次工具调用的完整生命周期。
    字段说明：
      - id：步骤唯一标识，自动生成
      - step_number：步骤序号，从 1 开始递增
      - tool：调用的工具名称
      - tool_call_id：LLM 返回的原始工具调用 ID，用于回填结果
      - approval_id：需要人工审批时对应的审批记录 ID
      - args：工具调用的入参
      - status：当前步骤状态，见 StepStatus
      - output/error：执行成功的输出内容 / 失败的错误信息
      - duration：本步骤执行耗时（秒）
      - timestamp：记录创建时间
    """

    id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    step_number: int
    tool: str
    tool_call_id: str | None = None
    approval_id: str | None = None
    args: dict
    status: StepStatus = StepStatus.PENDING
    output: str | None = None
    error: str | None = None
    duration: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class LoopResult(BaseModel):
    """
    一整轮执行循环（Loop）的结果汇总，包含所有步骤记录及最终产出。
    字段说明：
      - id：本轮 Loop 唯一标识
      - task：本轮 Loop 要完成的任务描述
      - status：整体运行状态，见 RunStatus（此处别名为 LoopStatus）
      - steps：本轮所有 LoopStep 记录，按执行顺序排列
      - result：Loop 结束后的最终总结文本
      - total_duration：整轮耗时（秒）
      - created_at/completed_at：创建时间 / 完成时间
      - compacted_summary：Tier 3 压缩后的摘要，供后续 run 复用，避免二次全量压缩
    """

    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(default_factory=lambda: f"loop-{uuid.uuid4().hex[:8]}")
    task: str
    status: LoopStatus = LoopStatus.PENDING
    steps: list[LoopStep] = []
    result: str | None = None
    total_duration: float | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    # Tier 3 压缩后的摘要，供后续 run 复用，避免二次全量压缩
    compacted_summary: str | None = None


class LoopPhase(str, Enum):
    """状态机阶段 — 继承 str 保持与现有字符串比较兼容"""

    PLANNING = "planning"
    TOOL_EXECUTION = "tool_execution"
    ERROR_RECOVERY = "error_recovery"
    FINAL_SUMMARY = "final_summary"
    DONE = "done"


@dataclass
class RuntimeState:
    """
    单次 run 的可变状态快照 — handler 只操作这个对象。
    字段说明：
      - phase：当前处于状态机的哪个阶段，见 LoopPhase
      - step_num：已执行的步骤计数
      - turn_retries：当前轮次的重试次数
      - consecutive_failures：连续失败次数，用于触发错误恢复或中止
      - has_executed_tools：本轮是否已经执行过任意工具调用
      - response：最近一次 LLM 响应，供下一阶段处理使用
      - approval_resume_event：等待人工审批结果时用于挂起/唤醒协程的事件
      - approval_result：审批完成后回填的结果（同意/拒绝及附带信息）
      - read_only_passes_used：已消耗的只读工具调用轮次数（用于限制无副作用探查的次数）
    """

    phase: LoopPhase = LoopPhase.PLANNING
    step_num: int = 0
    turn_retries: int = 0
    consecutive_failures: int = 0
    has_executed_tools: bool = False
    response: LLMResponse | None = None
    approval_resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_result: dict | None = None
    read_only_passes_used: int = 0

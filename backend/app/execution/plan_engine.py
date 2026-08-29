"""
文件功能：执行计划（Plan）的内存数据模型与状态管理
文件描述：定义计划的最小单元 PlanStep（含状态/发现）与整体计划 Plan（目标+步骤列表），
         提供计划更新时的差异合并、Markdown 格式的序列化/反序列化，以及供 LLM 上下文
         使用的渲染格式。是 plan_file_sync.py 落盘同步的上游数据源。
核心逻辑：Plan 本身只在内存中维护当前计划状态；每次 LLM 重新生成计划时通过 replace_from
         做增量对比，自动找回被误删的已完成步骤（LLM 重建计划时常见的行为缺陷），并识别
         本次更新中"新完成"和"新开始"的步骤，供上层用于日志/事件通知。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """
    计划中的单个步骤。
    字段说明：
      - content：步骤内容描述
      - status：步骤状态，pending(待执行)/in_progress(执行中)/completed(已完成)/blocked(受阻)
      - findings：该步骤执行后的发现/结论，仅完成后才有意义
    """

    content: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    findings: str = ""

    def to_dict(self) -> dict:
        """
        函数名：to_dict
        入参：无（使用 self 自身字段）
        功能：将单个计划步骤序列化为可 JSON 化的字典
        运行逻辑：直接取出 content/status/findings 三个字段组装字典
        出参：dict - 包含 content、status、findings 三个键的字典
        """
        return {
            "content": self.content,
            "status": self.status,
            "findings": self.findings,
        }


@dataclass
class Plan:
    """
    整体执行计划，由一个目标（goal）和若干有序步骤（steps）组成。
    字段说明：
      - goal：本次计划要达成的目标描述
      - steps：按执行顺序排列的 PlanStep 列表
    """

    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def current_step(self) -> PlanStep | None:
        """
        函数名：current_step
        入参：无
        功能：获取当前正在执行的步骤
        运行逻辑：遍历 steps，返回第一个状态为 in_progress 的步骤；没有则返回 None
        出参：PlanStep | None - 当前进行中的步骤，若无则为 None
        """
        for s in self.steps:
            if s.status == "in_progress":
                return s
        return None

    @property
    def is_complete(self) -> bool:
        """
        函数名：is_complete
        入参：无
        功能：判断整个计划是否已全部完成
        运行逻辑：steps 非空，且所有步骤状态均为 completed 才算完成
        出参：bool - True 表示计划已全部完成
        """
        return bool(self.steps) and all(s.status == "completed" for s in self.steps)

    def replace_from(self, new_steps: list[PlanStep], goal: str | None = None) -> dict:
        """
        函数名：replace_from
        入参：
          - new_steps (list[PlanStep])：LLM 重新生成的新步骤列表，用于整体替换当前计划
          - goal (str | None)：新的目标描述，为 None 时保留原目标不变
        功能：用新步骤列表更新计划，并自动修复 LLM 重建计划时误删已完成步骤的问题
        运行逻辑：
          1. 对比旧计划中已完成的步骤集合与新列表中已完成的步骤集合，找出被"丢弃"的已完成步骤
          2. 若存在丢弃，记录警告日志，并将这些已完成步骤重新拼接到新列表前面（自动恢复而非拒绝整个更新）
          3. 用（可能已修复的）new_steps 覆盖 self.steps；若传入了 goal 则同步更新
          4. 计算本次更新中"新完成"的步骤内容列表，以及"新开始"（首次进入 in_progress）的步骤内容
        出参：dict - 包含 just_completed（本次新完成的步骤内容列表）和 just_started（本次新开始的步骤内容，可能为 None）
        """
        old_completed = {s.content for s in self.steps if s.status == "completed"}
        old_in_progress = next(
            (s.content for s in self.steps if s.status == "in_progress"), None
        )
        new_completed = {s.content for s in new_steps if s.status == "completed"}
        dropped = old_completed - new_completed
        if dropped:
            # Auto-recover: merge dropped completed steps back into the new list
            # instead of rejecting the entire update. LLMs frequently drop completed
            # steps when reconstructing the plan — this is a known behavioral issue.
            logger.warning(
                "Plan update dropped %d completed steps, auto-recovering: %s",
                len(dropped),
                dropped,
            )
            preserved = [
                s
                for s in self.steps
                if s.status == "completed" and s.content in dropped
            ]
            new_steps = preserved + new_steps
        self.steps = new_steps
        if goal is not None:
            self.goal = goal
        just_completed = [
            s.content
            for s in new_steps
            if s.status == "completed" and s.content not in old_completed
        ]
        just_started = None
        for s in new_steps:
            if s.status == "in_progress" and s.content != old_in_progress:
                just_started = s.content
                break
        return {
            "just_completed": just_completed,
            "just_started": just_started,
        }

    def completed_findings(self) -> list[str]:
        """
        函数名：completed_findings
        入参：无
        功能：收集所有已完成步骤中记录的发现/结论
        运行逻辑：遍历 steps，筛选状态为 completed 且 findings 非空的步骤，取出其 findings
        出参：list[str] - 所有已完成步骤的 findings 文本列表
        """
        return [
            s.findings for s in self.steps if s.status == "completed" and s.findings
        ]

    def render_for_context(self) -> str:
        """
        函数名：render_for_context
        入参：无
        功能：将计划渲染为便于 LLM 阅读的上下文文本（供注入对话上下文使用）
        运行逻辑：先输出目标行，再逐步骤输出状态符号（○待执行/►执行中/✓已完成/✗受阻）+ 内容，
                 已完成且有 findings 的步骤额外追加一行发现内容
        出参：str - 多行文本，可直接拼入 LLM 上下文
        """
        lines = [f"## 执行计划\n目标: {self.goal}", ""]
        for s in self.steps:
            mark = {
                "pending": "○",
                "in_progress": "►",
                "completed": "✓",
                "blocked": "✗",
            }[s.status]
            lines.append(f"{mark} {s.content}")
            if s.status == "completed" and s.findings:
                lines.append(f"  → {s.findings}")
        return "\n".join(lines)

    def render_to_markdown(self) -> str:
        """
        函数名：render_to_markdown
        入参：无
        功能：将计划渲染为可落盘保存的 Markdown 格式文本
        运行逻辑：输出标题、目标行、"## Steps"小节，每个步骤渲染为 "- [状态] 内容" 的
                 checklist 格式，有 findings 的步骤额外缩进一行输出
        出参：str - 符合 parse_from_markdown 可解析格式的 Markdown 文本
        """
        lines = ["# Execution Plan", f"goal: {self.goal}", "", "## Steps"]
        for s in self.steps:
            lines.append(f"- [{s.status}] {s.content}")
            if s.findings:
                lines.append(f"  findings: {s.findings}")
        return "\n".join(lines)

    @classmethod
    def parse_from_markdown(cls, text: str) -> Plan:
        """
        函数名：parse_from_markdown
        入参：
          - text (str)：render_to_markdown 生成的（或格式兼容的）Markdown 文本
        功能：将 Markdown 文本反序列化为 Plan 对象，是 render_to_markdown 的逆操作
        运行逻辑：
          1. 按行扫描文本，遇到 "goal:" 前缀的行提取目标
          2. 用正则匹配 "- [状态] 内容" 形式的行，构造 PlanStep 追加到 steps
          3. 用正则匹配缩进的 "findings: 内容" 行，回填到最近一个 PlanStep 的 findings 字段
        出参：Plan - 解析得到的计划对象
        """
        goal = ""
        steps: list[PlanStep] = []
        for line in text.splitlines():
            line = line.rstrip()
            if line.startswith("goal:"):
                goal = line[len("goal:") :].strip()
                continue
            step_match = re.match(r"^-\s*\[(\w+)\]\s*(.+)$", line)
            if step_match:
                status = step_match.group(1)
                content = step_match.group(2).strip()
                steps.append(PlanStep(content=content, status=status))
                continue
            findings_match = re.match(r"^\s+findings:\s*(.+)$", line)
            if findings_match and steps:
                steps[-1].findings = findings_match.group(1).strip()
        return cls(goal=goal, steps=steps)

    def to_dict(self) -> dict:
        """
        函数名：to_dict
        入参：无
        功能：将整个计划序列化为可 JSON 化的字典
        运行逻辑：goal 直接取值，steps 逐个调用 PlanStep.to_dict() 后组成列表
        出参：dict - 包含 goal 和 steps（字典列表）两个键的字典
        """
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
        }

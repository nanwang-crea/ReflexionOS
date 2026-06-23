"""Working Memory 数据模型 — 活跃上下文层

生命周期：绑定到 Turn（非 Run），同一 Turn 内的多次 Run（重试/反思循环）
共享同一个 WorkingMemory 实例。Turn 结束时销毁，不持久化到数据库。

职责分离：
- SessionTracker（系统托管）：跟踪"发生了什么"——文件访问、工具调用（元数据）
- WorkingMemory（模型管理）：存储"意味着什么"——决策、发现、变量（语义内容）

注入位置：LoopMessageBuilder.build() 中，SessionTracker 之后
Token 预算：~2000 tokens（约 3000 中文字符）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MemoryEntryType(str, Enum):
    """Working Memory 条目类型"""
    KEY_DECISION = "key_decision"       # 关键决策
    VARIABLE = "variable"               # 配置/变量工作集
    ERROR_ENCOUNTERED = "error"         # 遇到的错误


@dataclass
class MemoryEntry:
    """Working Memory 中的一条记录"""
    id: str                                     # 唯一标识
    entry_type: MemoryEntryType                 # 类型
    key: str                                    # 主键（如文件路径、决策名）
    value: str                                  # 值（摘要、决策内容等）
    source: str = "auto"                        # 来源: "auto" | "model"


@dataclass
class WorkingMemory:
    """
    结构化工作记忆 — 在对话历史之外维护关键信息

    生命周期：绑定到 Turn（非 Run），同一 Turn 内的多次 Run（重试/反思循环）
    共享同一个 WorkingMemory 实例。Turn 结束时销毁，不持久化到数据库。

    为什么是 Turn 而不是 Session：
    - 同一 Session 内不同 Turn 可能处理完全不同的任务，之前的文件摘要、
      决策记录会成为脏数据（文件已修改、决策被推翻、错误已修复）
    - 跨 Turn 的上下文传递由对话历史（ConversationService）负责，
      不需要 Working Memory 重复承担
    - 同一 Turn 内的反思循环共享 WorkingMemory 是合理的——在做同一件事

    注入位置：LoopMessageBuilder.build() 中，system prompt 之后、Tier 3 之前
    Token 预算：~2000 tokens（约 3000 中文字符）
    """

    # 关键决策记录
    decisions: list[MemoryEntry] = field(default_factory=list)

    # 变量/配置工作集
    # key = 变量名, value = 值
    variables: dict[str, MemoryEntry] = field(default_factory=dict)

    # 错误记录
    errors: list[MemoryEntry] = field(default_factory=list)

    # Token 预算
    max_tokens: int = 2000

    # ---- 写入接口 ----

    def add_decision(self, decision: str, rationale: str = "", source: str = "model") -> None:
        """记录关键决策"""
        self.decisions.append(MemoryEntry(
            id=f"decision:{len(self.decisions)}",
            entry_type=MemoryEntryType.KEY_DECISION,
            key=decision,
            value=rationale,
            source=source,
        ))

    def set_variable(self, name: str, value: str, source: str = "auto") -> None:
        """设置变量/配置"""
        self.variables[name] = MemoryEntry(
            id=f"var:{name}",
            entry_type=MemoryEntryType.VARIABLE,
            key=name,
            value=value,
            source=source,
        )

    def add_error(self, error_type: str, detail: str, source: str = "auto") -> None:
        """记录遇到的错误"""
        self.errors.append(MemoryEntry(
            id=f"error:{len(self.errors)}",
            entry_type=MemoryEntryType.ERROR_ENCOUNTERED,
            key=error_type,
            value=detail,
            source=source,
        ))

    # ---- 读取接口 ----

    def to_prompt_section(self) -> str:
        """
        将 Working Memory 格式化为 system prompt 注入段

        格式紧凑、信息密度高，控制在 ~2000 tokens 以内
        如果超过预算，按优先级淘汰：errors > variables > decisions

        注入时包含行为指令，提醒模型利用已有信息、避免重复工作。
        """
        sections = []

        # 1. 关键决策
        if self.decisions:
            lines = ["🎯 Key decisions:"]
            for d in self.decisions:
                rationale = f" — {d.value}" if d.value else ""
                lines.append(f"  • {d.key}{rationale}")
            sections.append("\n".join(lines))

        # 3. 变量工作集
        if self.variables:
            lines = ["⚙️ Current state:"]
            for name, entry in self.variables.items():
                lines.append(f"  {name} = {entry.value}")
            sections.append("\n".join(lines))

        # 4. 错误记录
        if self.errors:
            lines = ["⚠️ Errors encountered:"]
            for e in self.errors[-5:]:  # 只保留最近 5 个
                lines.append(f"  • [{e.key}] {e.value}")
            sections.append("\n".join(lines))

        if not sections:
            return ""

        content = "\n\n".join(sections)

        # Token 预算检查（粗估：1 token ≈ 1.5 字符）
        max_chars = self.max_tokens * 1.5
        if len(content) > max_chars:
            content = self._evict_to_fit(content, max_chars)

        header = (
            "[Working Memory — key facts from this session]\n"
            "Use the information below to avoid redundant work.\n"
            "DO NOT re-read files listed in [Session Tracking] — "
            "use session_recall if you need full content."
        )
        return f"{header}\n\n{content}"

    def _evict_to_fit(self, content: str, max_chars: int) -> str:
        """超预算时按优先级淘汰"""
        # 淘汰顺序：errors → variables → decisions
        if self.errors and len(content) > max_chars:
            self.errors = self.errors[-2:]  # 只保留最近 2 个
            content = self._rebuild_content()

        if len(content) > max_chars and self.variables:
            # 只保留最近 10 个变量
            items = list(self.variables.items())
            self.variables = dict(items[-10:])
            content = self._rebuild_content()

        # 最终兜底：硬截断
        if len(content) > max_chars:
            content = content[:int(max_chars)] + "\n...[truncated]"

        return content

    def _rebuild_content(self) -> str:
        """淘汰后重建内容"""
        sections = []
        if self.decisions:
            lines = ["🎯 Key decisions:"]
            for d in self.decisions:
                rationale = f" — {d.value}" if d.value else ""
                lines.append(f"  • {d.key}{rationale}")
            sections.append("\n".join(lines))
        if self.variables:
            lines = ["⚙️ Current state:"]
            for name, entry in self.variables.items():
                lines.append(f"  {name} = {entry.value}")
            sections.append("\n".join(lines))
        if self.errors:
            lines = ["⚠️ Errors encountered:"]
            for e in self.errors[-2:]:
                lines.append(f"  • [{e.key}] {e.value}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def is_empty(self) -> bool:
        """Working Memory 是否为空"""
        return not self.decisions and not self.variables and not self.errors

    def clear(self) -> None:
        """清空所有数据（Turn 结束时调用）"""
        self.decisions.clear()
        self.variables.clear()
        self.errors.clear()

    def to_dict(self) -> dict:
        """序列化为 dict"""
        return {
            "decisions": [
                {"key": d.key, "value": d.value, "source": d.source}
                for d in self.decisions
            ],
            "variables": {
                k: {"value": v.value, "source": v.source}
                for k, v in self.variables.items()
            },
            "errors": [
                {"key": e.key, "value": e.value, "source": e.source}
                for e in self.errors
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkingMemory":
        """从 dict 反序列化"""
        wm = cls()
        for d in data.get("decisions", []):
            wm.add_decision(d["key"], d.get("value", ""), d.get("source", "model"))
        for name, v in data.get("variables", {}).items():
            wm.set_variable(name, v["value"], v.get("source", "auto"))
        for e in data.get("errors", []):
            wm.add_error(e["key"], e["value"], e.get("source", "auto"))
        return wm

"""Working Memory 数据模型 — 在对话历史之外维护关键信息

生命周期：绑定到 Turn（非 Run），同一 Turn 内的多次 Run（重试/反思循环）
共享同一个 WorkingMemory 实例。Turn 结束时销毁，不持久化到数据库。

注入位置：LoopMessageBuilder.build() 中，system prompt 之后、Tier 3 之前
Token 预算：~2000 tokens（约 3000 中文字符）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class MemoryEntryType(str, Enum):
    """Working Memory 条目类型"""
    FILE_SUMMARY = "file_summary"       # 读过的文件摘要
    KEY_DECISION = "key_decision"       # 关键决策
    VARIABLE = "variable"               # 配置/变量工作集
    ERROR_ENCOUNTERED = "error"         # 遇到的错误
    PATTERN_FOUND = "pattern"           # 发现的模式/规律


@dataclass
class MemoryEntry:
    """Working Memory 中的一条记录"""
    id: str                                     # 唯一标识
    entry_type: MemoryEntryType                 # 类型
    key: str                                    # 主键（如文件路径、决策名）
    value: str                                  # 值（摘要、决策内容等）
    source: str = "auto"                        # 来源: "auto" | "model"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0                       # 被引用次数（用于淘汰）


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

    # 文件索引：agent 读过的每个文件的精炼摘要
    # key = 文件路径, value = 摘要
    file_index: dict[str, MemoryEntry] = field(default_factory=dict)

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

    def upsert_file(self, path: str, summary: str, source: str = "auto") -> None:
        """新增或更新文件摘要"""
        if path in self.file_index:
            entry = self.file_index[path]
            entry.value = summary
            entry.updated_at = datetime.now()
            entry.source = source
        else:
            self.file_index[path] = MemoryEntry(
                id=f"file:{path}",
                entry_type=MemoryEntryType.FILE_SUMMARY,
                key=path,
                value=summary,
                source=source,
            )

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
        如果超过预算，按优先级淘汰：errors > variables > file_index(最旧的) > decisions
        """
        sections = []

        # 1. 文件索引（最高优先级之一）
        if self.file_index:
            lines = ["📂 Files read:"]
            for path, entry in self.file_index.items():
                lines.append(f"  {path}: {entry.value}")
            sections.append("\n".join(lines))

        # 2. 关键决策
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

        return f"[Working Memory — key facts from this session]\n{content}"

    def _evict_to_fit(self, content: str, max_chars: int) -> str:
        """超预算时按优先级淘汰"""
        # 淘汰顺序：errors → variables → file_index(最旧的) → decisions
        if self.errors and len(content) > max_chars:
            self.errors = self.errors[-2:]  # 只保留最近 2 个
            content = self._rebuild_content()

        if len(content) > max_chars and self.variables:
            # 只保留最近 10 个变量
            items = list(self.variables.items())
            self.variables = dict(items[-10:])
            content = self._rebuild_content()

        if len(content) > max_chars and self.file_index:
            # 只保留最近读过的 15 个文件
            items = list(self.file_index.items())
            self.file_index = dict(items[-15:])
            content = self._rebuild_content()

        # 最终兜底：硬截断
        if len(content) > max_chars:
            content = content[:int(max_chars)] + "\n...[truncated]"

        return content

    def _rebuild_content(self) -> str:
        """淘汰后重建内容"""
        sections = []
        if self.file_index:
            lines = ["📂 Files read:"]
            for path, entry in self.file_index.items():
                lines.append(f"  {path}: {entry.value}")
            sections.append("\n".join(lines))
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
        return not self.file_index and not self.decisions and not self.variables and not self.errors

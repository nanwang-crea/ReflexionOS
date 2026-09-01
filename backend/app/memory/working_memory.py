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

    # 单调递增 ID 计数器，避免删除后 ID 冲突
    _id_counter: int = field(default=0, repr=False)

    # ---- 写入接口 ----

    def _next_id(self, prefix: str) -> str:
        """
        生成唯一 ID（单调递增，不受删除影响）

        参数：prefix - ID 前缀（如 "decision"、"error"）
        逻辑：内部计数器自增 1，与前缀拼接
        返回：形如 "prefix:序号" 的字符串
        """
        self._id_counter += 1
        return f"{prefix}:{self._id_counter}"

    def add_decision(self, decision: str, rationale: str = "", source: str = "model") -> None:
        """
        记录关键决策（upsert：相同 key 的决策会被更新，而非重复追加）

        参数：
            decision: 决策内容，作为去重 key。
            rationale: 决策理由/说明，作为条目的 value。
            source: 来源标记，"model"（模型主动记录）或 "auto"（系统自动记录）。
        逻辑：先遍历已有 decisions 查找同 key 条目，命中则原地更新 value/source；
              未命中则追加一条新的 MemoryEntry。
        返回：无（原地修改 self.decisions）。
        """
        for entry in self.decisions:
            if entry.key == decision:
                # 同 key 已存在，更新 rationale 和 source
                entry.value = rationale
                entry.source = source
                return
        self.decisions.append(MemoryEntry(
            id=self._next_id("decision"),
            entry_type=MemoryEntryType.KEY_DECISION,
            key=decision,
            value=rationale,
            source=source,
        ))

    def set_variable(self, name: str, value: str, source: str = "auto") -> None:
        """
        设置变量/配置

        参数：
            name: 变量名，作为 variables 字典的 key，同时决定 MemoryEntry.id（"var:name"）。
            value: 变量值（字符串形式）。
            source: 来源标记，默认 "auto"。
        逻辑：直接覆盖写入 self.variables[name]（天然 upsert，无需查重）。
        返回：无。
        """
        self.variables[name] = MemoryEntry(
            id=f"var:{name}",
            entry_type=MemoryEntryType.VARIABLE,
            key=name,
            value=value,
            source=source,
        )

    def add_error(self, error_type: str, detail: str, source: str = "auto") -> None:
        """
        记录遇到的错误（upsert：相同 key 的错误会被更新，而非重复追加）

        参数：
            error_type: 错误类型/标识，作为去重 key。
            detail: 错误详情描述，作为条目的 value。
            source: 来源标记，默认 "auto"。
        逻辑：先遍历已有 errors 查找同 key 条目，命中则原地更新 value/source；
              未命中则追加一条新的 MemoryEntry。
        返回：无（原地修改 self.errors）。
        """
        for entry in self.errors:
            if entry.key == error_type:
                # 同 key 已存在，更新 detail 和 source
                entry.value = detail
                entry.source = source
                return
        self.errors.append(MemoryEntry(
            id=self._next_id("error"),
            entry_type=MemoryEntryType.ERROR_ENCOUNTERED,
            key=error_type,
            value=detail,
            source=source,
        ))

    # ---- 读取接口 ----

    def to_prompt_section(self) -> str:
        """
        将 Working Memory 格式化为 system prompt 注入段

        参数：无（读取 self.decisions/variables/errors）。
        逻辑：
            按"决策 → 变量 → 错误（仅最近5条）"顺序拼接为带 emoji 标题的分段文本；
            全部为空则返回空字符串；
            格式紧凑、信息密度高，控制在 ~2000 tokens 以内，若超过预算（按
            max_tokens*1.5 估算的字符数上限）则调用 _evict_to_fit 按优先级
            （errors > variables > decisions）淘汰内容；
            最终附加固定的行为指令 header，提醒模型利用已有信息、避免重复工作。
        返回：拼接好的 prompt 文本；无内容时返回空字符串 ""。
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
        """
        超预算时按优先级淘汰（只作用于副本，不修改 self）

        参数：
            content: 当前已拼接好的完整 prompt 内容。
            max_chars: 允许的最大字符数上限。
        逻辑：
            淘汰顺序：errors → variables（decisions 不淘汰，始终保留）；
            每步淘汰后用副本重建内容（_rebuild_content），重新检查是否超预算；
            errors 只保留最近 2 条，variables 只保留最近 10 个；
            仍超预算则最终硬截断并附加 "...[truncated]" 标记。
        返回：裁剪后不超过 max_chars 的内容字符串。
        """
        # 使用副本做截断，避免修改原始数据
        errors_copy = list(self.errors)
        variables_copy = dict(self.variables)

        if errors_copy and len(content) > max_chars:
            errors_copy = errors_copy[-2:]  # 只保留最近 2 个
            content = self._rebuild_content(errors_copy, variables_copy)

        if len(content) > max_chars and variables_copy:
            items = list(variables_copy.items())
            variables_copy = dict(items[-10:])  # 只保留最近 10 个变量
            content = self._rebuild_content(errors_copy, variables_copy)

        # 最终兜底：硬截断（纯字符串操作，不影响数据）
        if len(content) > max_chars:
            content = content[:int(max_chars)] + "\n...[truncated]"

        return content

    def _rebuild_content(
        self,
        errors: list[MemoryEntry] | None = None,
        variables: dict[str, MemoryEntry] | None = None,
    ) -> str:
        """
        用指定数据重建 prompt 内容（不影响 self 原始数据）

        参数：
            errors: 用于重建的错误列表；为 None 时回退到 self.errors。
            variables: 用于重建的变量字典；为 None 时回退到 self.variables。
        逻辑：decisions 始终用 self.decisions（不参与淘汰）；errors 展示时只取最后 2 条；
              按 决策/变量/错误 顺序拼接非空分段。
        返回：拼接后的文本（可能为空字符串）。
        """
        errors = errors if errors is not None else self.errors
        variables = variables if variables is not None else self.variables

        sections = []
        if self.decisions:
            lines = ["🎯 Key decisions:"]
            for d in self.decisions:
                rationale = f" — {d.value}" if d.value else ""
                lines.append(f"  • {d.key}{rationale}")
            sections.append("\n".join(lines))
        if variables:
            lines = ["⚙️ Current state:"]
            for name, entry in variables.items():
                lines.append(f"  {name} = {entry.value}")
            sections.append("\n".join(lines))
        if errors:
            lines = ["⚠️ Errors encountered:"]
            for e in errors[-2:]:
                lines.append(f"  • [{e.key}] {e.value}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def is_empty(self) -> bool:
        """Working Memory 是否为空。参数：无；返回：decisions/variables/errors 全为空时 True。"""
        return not self.decisions and not self.variables and not self.errors

    def clear(self) -> None:
        """清空所有数据（Turn 结束时调用）。参数：无；返回：无（原地清空三个容器）。"""
        self.decisions.clear()
        self.variables.clear()
        self.errors.clear()

    def to_dict(self) -> dict:
        """
        序列化为 dict

        参数：无。
        逻辑：将 decisions/variables/errors 分别转换为可 JSON 化的基础类型
              （list/dict 嵌套 str），丢弃各条目的 id/entry_type，只保留 key/value/source。
        返回：形如 {"decisions": [...], "variables": {...}, "errors": [...]} 的 dict。
        """
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
        """
        从 dict 反序列化

        参数：data - 与 to_dict() 输出结构一致的 dict（decisions/variables/errors）。
        逻辑：新建空 WorkingMemory 实例，依次调用 add_decision/set_variable/add_error
              回填数据（复用写入接口的 upsert 逻辑，而非直接构造 MemoryEntry）。
        返回：还原后的 WorkingMemory 实例。
        """
        wm = cls()
        for d in data.get("decisions", []):
            wm.add_decision(d["key"], d.get("value", ""), d.get("source", "model"))
        for name, v in data.get("variables", {}).items():
            wm.set_variable(name, v["value"], v.get("source", "auto"))
        for e in data.get("errors", []):
            wm.add_error(e["key"], e["value"], e.get("source", "auto"))
        return wm

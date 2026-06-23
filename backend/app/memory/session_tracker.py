"""SessionTracker — 轻量会话跟踪器

自动跟踪模型在一次 Run 中的文件访问和工具调用。
纯元数据，无语义摘要，成本极低（~10 tokens/文件），永不淘汰。

设计原则：
- 只存路径 + 步骤号 + 操作类型，不做语义摘要
- 永不淘汰，成本极低（~200 tokens for 20 files）
- 系统自动管理，模型不可直接写入（只读查询）
- 注入位置：LoopMessageBuilder 中 system prompt 最前面，高注意力权重

与 WorkingMemory 的分工：
- SessionTracker = "发生了什么"（元数据，自动）
- WorkingMemory = "意味着什么"（语义，模型管理）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AccessType(Enum):
    """文件访问类型"""
    READ = "read"    # 读取文件
    WRITE = "write"  # 写入/编辑/创建/删除文件


@dataclass
class FileAccessRecord:
    """单个文件的访问记录"""
    path: str
    access_type: AccessType
    last_step: int      # 最近一次访问的步骤号
    count: int = 1      # 访问次数


class SessionTracker:
    """
    轻量会话跟踪器 — 记录"发生了什么"

    生命周期：绑定到 Turn（与 WorkingMemory 一致），Turn 结束时销毁。
    由系统自动管理，模型可通过 working_memory_update 工具查询但不可写入。
    """

    def __init__(self) -> None:
        # 文件读取记录: path → FileAccessRecord
        self._read_files: dict[str, FileAccessRecord] = {}
        # 文件变更记录: path → FileAccessRecord
        self._modified_files: dict[str, FileAccessRecord] = {}
        # 工具调用计数: tool_name → count
        self._tool_calls: dict[str, int] = {}

    @property
    def read_files(self) -> dict[str, FileAccessRecord]:
        """所有读取过的文件记录"""
        return self._read_files

    @property
    def modified_files(self) -> dict[str, FileAccessRecord]:
        """所有变更过的文件记录"""
        return self._modified_files

    @property
    def tool_call_summary(self) -> dict[str, int]:
        """工具调用统计（只读副本）"""
        return dict(self._tool_calls)

    # ---- 写入接口（系统自动调用） ----

    def record_file_access(
        self, path: str, access_type: AccessType, step: int
    ) -> None:
        """
        记录文件访问（读取或变更）

        同一文件同一类型多次访问时，合并记录，更新 last_step 和 count。
        """
        target = (
            self._read_files if access_type == AccessType.READ
            else self._modified_files
        )
        if path in target:
            existing = target[path]
            existing.last_step = max(existing.last_step, step)
            existing.count += 1
        else:
            target[path] = FileAccessRecord(
                path=path,
                access_type=access_type,
                last_step=step,
                count=1,
            )

    def record_from_tool(self, tool_name: str, tool_args: dict, step: int) -> None:
        """
        根据工具调用自动记录到 tracker（file→READ, edit→WRITE）

        集成点：MemoryExtractor.extract() 中调用，将工具调用与文件跟踪解耦。
        """
        self.record_tool_call(tool_name, step)

        # 文件读取: file(action=read)
        if tool_name == "file" and tool_args.get("action") == "read":
            path = tool_args.get("path")
            if path:
                self.record_file_access(path, AccessType.READ, step)

        # 文件写入: edit
        elif tool_name == "edit":
            path = tool_args.get("path")
            if path:
                self.record_file_access(path, AccessType.WRITE, step)

    def record_tool_call(self, tool_name: str, step: int) -> None:
        """记录工具调用（仅计数，不存参数）"""
        self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1

    # ---- 查询接口 ----

    def is_empty(self) -> bool:
        """是否没有任何跟踪数据"""
        return (
            not self._read_files
            and not self._modified_files
            and not self._tool_calls
        )

    def to_prompt_section(self) -> str:
        """
        渲染为极简的跟踪列表，注入 system prompt 最前面。

        输出格式示例:
        [Session Tracking]
        Files read (3): a.py, b.py, c.py
        Files modified (1): a.py
        Tools: file(5x), edit(2x), grep(1x)
        """
        if self.is_empty():
            return ""

        lines: list[str] = ["[Session Tracking]"]

        # 文件读取列表（按最近访问排序）
        if self._read_files:
            sorted_reads = sorted(
                self._read_files.values(),
                key=lambda r: r.last_step,
                reverse=True,
            )
            paths = [r.path for r in sorted_reads]
            lines.append(f"Files read ({len(paths)}): {', '.join(paths)}")

        # 文件变更列表
        if self._modified_files:
            sorted_mods = sorted(
                self._modified_files.values(),
                key=lambda r: r.last_step,
                reverse=True,
            )
            paths = [r.path for r in sorted_mods]
            lines.append(f"Files modified ({len(paths)}): {', '.join(paths)}")

        # 工具调用统计（按使用次数降序）
        if self._tool_calls:
            sorted_tools = sorted(
                self._tool_calls.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            tool_strs = [f"{name}({count}x)" for name, count in sorted_tools]
            lines.append(f"Tools: {', '.join(tool_strs)}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """序列化为 dict（用于调试/日志/持久化）"""
        return {
            "read_files": {
                p: {"step": r.last_step, "count": r.count}
                for p, r in self._read_files.items()
            },
            "modified_files": {
                p: {"step": r.last_step, "count": r.count}
                for p, r in self._modified_files.items()
            },
            "tool_calls": dict(self._tool_calls),
        }

    def clear(self) -> None:
        """清空所有跟踪数据（Turn 结束或 Run 重置时调用）"""
        self._read_files.clear()
        self._modified_files.clear()
        self._tool_calls.clear()

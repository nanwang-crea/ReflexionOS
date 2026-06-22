"""MemoryExtractor — 从 tool 调用结果中自动提取关键信息，写入 Working Memory

集成点：tool_call_executor 中 tool 执行完成后
设计原则：纯规则提取，不调用 LLM，避免延迟和成本

实际 tool 名称映射（基于 ToolRegistry 注册名）：
- file (action=read)   → 读文件摘要
- file (action=search) → 搜索结果提取文件路径
- file (action=list)   → 目录结构概览
- edit (action=*)      → 写文件标记 [MODIFIED]
- shell                → 命令执行结果提取变量/错误
- grep                 → 全局搜索结果提取文件路径
- session_recall       → recall 结果提取关键信息
- explore              → 探索结果提取结构信息
"""

from __future__ import annotations

import re
import logging
from datetime import datetime
from app.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    从 tool 调用结果中自动提取关键信息，写入 Working Memory

    集成点：tool_call_executor 中 tool 执行完成后
    设计原则：纯规则提取，不调用 LLM，避免延迟和成本
    """

    def __init__(self, memory: WorkingMemory):
        self.memory = memory

    def extract(self, tool_name: str, tool_args: dict, tool_result: str) -> None:
        """
        根据 tool 类型自动提取信息

        Args:
            tool_name: 工具名称（与 ToolRegistry 注册名一致）
            tool_args: 工具调用参数
            tool_result: 工具执行结果（字符串形式）
        """
        try:
            if tool_name == "file":
                action = tool_args.get("action", "")
                if action == "read":
                    self._extract_from_file_read(tool_args, tool_result)
                elif action == "search":
                    self._extract_from_file_search(tool_args, tool_result)
                elif action == "list":
                    self._extract_from_file_list(tool_args, tool_result)
            elif tool_name == "edit":
                self._extract_from_edit(tool_args, tool_result)
            elif tool_name == "shell":
                self._extract_from_shell(tool_args, tool_result)
            elif tool_name == "grep":
                self._extract_from_grep(tool_args, tool_result)
            elif tool_name == "session_recall":
                self._extract_from_recall(tool_args, tool_result)
            elif tool_name == "explore":
                self._extract_from_explore(tool_args, tool_result)
        except Exception as e:
            # 提取失败不应影响主流程
            logger.debug(f"Memory extraction failed for {tool_name}: {e}")

    def _extract_from_file_read(self, args: dict, result: str) -> None:
        """读文件后自动记录文件摘要"""
        path = args.get("path", "")
        if not path or not result or result.startswith("Error") or "文件不存在" in result:
            return

        summary = self._summarize_file_content(path, result)
        self.memory.upsert_file(path, summary, source="auto")

    def _extract_from_file_search(self, args: dict, result: str) -> None:
        """文件内搜索结果中提取匹配信息"""
        path = args.get("path", "")
        query = args.get("query", "")
        if not result or "未找到" in result:
            return

        # 如果已有文件摘要，追加搜索关键词
        if path and path in self.memory.file_index:
            existing = self.memory.file_index[path]
            if query and query not in existing.value:
                # 追加搜索关键词到摘要
                existing.value = f"{existing.value}; search: {query}"
                existing.updated_at = datetime.now()

    def _extract_from_file_list(self, args: dict, result: str) -> None:
        """目录列表记录结构概览"""
        path = args.get("path", "")
        if not path or not result:
            return
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        summary = f"directory with {len(lines)} items"
        self.memory.upsert_file(path, summary, source="auto")

    def _extract_from_edit(self, args: dict, result: str) -> None:
        """编辑文件后更新摘要"""
        path = args.get("path", "")
        if not path:
            return

        # 编辑成功 → 标记文件为"已修改"
        if "success" in result.lower() or "wrote" in result.lower() or "replaced" in result.lower():
            existing = self.memory.file_index.get(path)
            if existing:
                # 在已有摘要前加 [MODIFIED] 标记
                if not existing.value.startswith("[MODIFIED]"):
                    existing.value = f"[MODIFIED] {existing.value}"
                existing.updated_at = datetime.now()
            else:
                self.memory.upsert_file(path, "[MODIFIED] newly created file", source="auto")

    def _extract_from_shell(self, args: dict, result: str) -> None:
        """命令执行结果中提取变量/错误"""
        command = args.get("command", "")

        # 检测错误
        if "error" in result.lower() or "failed" in result.lower():
            error_snippet = result[:200] if len(result) > 200 else result
            self.memory.add_error("command_error", f"`{command[:50]}` → {error_snippet}", source="auto")

        # 检测环境变量/配置
        # 从命令或结果中检测变量赋值
        if "export " in command or "=" in command or "=" in result:
            for match in re.finditer(r'(\w+)=(\S+)', result):
                key, value = match.group(1), match.group(2)
                if len(key) < 30 and len(value) < 100:  # 过滤掉文件内容
                    self.memory.set_variable(key, value, source="auto")

    def _extract_from_grep(self, args: dict, result: str) -> None:
        """全局搜索结果中提取文件路径"""
        paths = set()
        for line in result.split("\n")[:20]:  # 只看前 20 行
            # 匹配 "path:line:content" 格式
            match = re.match(r'^([^\s:]+\.\w+)[:\d]', line)
            if match:
                paths.add(match.group(1))

        for path in sorted(paths)[:10]:
            if path not in self.memory.file_index:
                self.memory.upsert_file(path, "found in search (not yet read)", source="auto")

    def _extract_from_recall(self, args: dict, result: str) -> None:
        """recall 结果中提取关键信息"""
        query = args.get("query", "")
        if result and len(result) > 50:
            self.memory.set_variable(f"recall:{query[:30]}", result[:200], source="auto")

    def _extract_from_explore(self, args: dict, result: str) -> None:
        """探索结果中提取结构信息"""
        # explore 工具返回代码库结构概览，提取关键模块名
        if not result:
            return
        # 简单提取：记录探索查询和结果摘要
        query = args.get("query", "")
        if query:
            summary = result[:150].replace("\n", " ").strip()
            self.memory.set_variable(f"explore:{query[:30]}", summary, source="auto")

    # ---- 纯规则文件摘要（不调用 LLM） ----

    def _summarize_file_content(self, path: str, content: str) -> str:
        """
        纯规则提取文件摘要，不调用 LLM

        提取：类名、函数名、导入、关键注释
        控制在 ~100 字符以内
        """
        lines = content.split("\n")
        parts = []

        # 提取 class/function/struct 定义
        symbols = []
        for line in lines:
            stripped = line.strip()
            # Python
            if stripped.startswith("class ") or stripped.startswith("def "):
                name = stripped.split("(")[0].split(":")[0].strip()
                symbols.append(name)
            # JS/TS
            elif stripped.startswith("export ") or stripped.startswith("function "):
                name = stripped.split("{")[0].strip()
                symbols.append(name)
            # Go
            elif stripped.startswith("func ") or stripped.startswith("type "):
                symbols.append(stripped.split("{")[0].strip())
            # Rust
            elif stripped.startswith("pub fn ") or stripped.startswith("fn ") or stripped.startswith("struct "):
                symbols.append(stripped.split("{")[0].strip())

        if symbols:
            symbol_str = ", ".join(symbols[:6])  # 最多 6 个
            if len(symbols) > 6:
                symbol_str += f" (+{len(symbols)-6} more)"
            parts.append(symbol_str)

        # 提取关键注释（TODO, FIXME, HACK, NOTE）
        key_comments = []
        for line in lines:
            stripped = line.strip().upper()
            for marker in ["TODO", "FIXME", "HACK", "NOTE", "IMPORTANT"]:
                if marker in stripped:
                    key_comments.append(line.strip()[:80])
                    break
        if key_comments:
            parts.append("; ".join(key_comments[:2]))

        # 行数
        line_count = len(lines)
        if parts:
            return f"{line_count} lines: {' | '.join(parts)}"
        else:
            # 兜底：首行 + 行数
            first_meaningful = next(
                (l.strip() for l in lines if l.strip() and not l.strip().startswith("#")),
                ""
            )
            if first_meaningful:
                return f"{line_count} lines: {first_meaningful[:80]}"
            return f"{line_count} lines"

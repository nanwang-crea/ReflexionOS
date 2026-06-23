"""MemoryExtractor — 从 tool 调用结果中自动提取关键信息，写入 Working Memory

集成点：tool_call_executor 中 tool 执行完成后
设计原则：纯规则提取，不调用 LLM，避免延迟和成本

职责分工：
- MemoryExtractor: 从工具结果中提取语义信息（错误、变量、决策）→ WorkingMemory
- SessionTracker.record_from_tool(): 从工具调用中提取元数据（文件访问）→ SessionTracker

实际提取的工具：
- shell          → 命令执行结果提取变量/错误
- session_recall → recall 结果提取关键信息
- explore        → 探索结果提取结构信息
"""

from __future__ import annotations

import re
import logging

from app.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    从 tool 调用结果中自动提取关键信息，写入 Working Memory

    集成点：tool_call_executor 中 tool 执行完成后
    设计原则：纯规则提取，不调用 LLM，避免延迟和成本
    """

    def __init__(self, memory: WorkingMemory, session_tracker: "SessionTracker | None" = None):
        self.memory = memory
        self.session_tracker = session_tracker

    def extract(self, tool_name: str, tool_args: dict, tool_result: str, step: int = 0) -> None:
        """
        根据 tool 类型自动提取信息

        Args:
            tool_name: 工具名称（与 ToolRegistry 注册名一致）
            tool_args: 工具调用参数
            tool_result: 工具执行结果（字符串形式）
        """
        try:
            # file 和 edit 的语义提取已废弃，文件跟踪由 SessionTracker 处理
            if tool_name == "shell":
                self._extract_from_shell(tool_args, tool_result)
            elif tool_name == "session_recall":
                self._extract_from_recall(tool_args, tool_result)
            elif tool_name == "explore":
                self._extract_from_explore(tool_args, tool_result)

            # 记录到 SessionTracker（跟踪"发生了什么"）
            if tool_name and self.session_tracker:
                self.session_tracker.record_from_tool(tool_name, tool_args, step)
        except Exception as e:
            # 提取失败不应影响主流程
            logger.debug(f"Memory extraction failed for {tool_name}: {e}")

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

    def extract_from_response(self, model_output: str) -> None:
        """从模型输出中提取决策和关键信息（由 extract() 自动调用）"""
        if not model_output:
            return
        # 提取决策模式："I'll use X because Y" / "I decided to X"
        # 这是一个轻量级的规则提取，不调用 LLM
        decision_patterns = [
            r"(?:I'?ll|I will|let me|I decided to|I choose to|going with)\s+(.{20,100})",
            r"(?:using|using the|adopting|choosing|selecting)\s+(.{10,80})\s+(?:because|since|as)",
        ]
        for pattern in decision_patterns:
            match = re.search(pattern, model_output, re.IGNORECASE)
            if match:
                decision = match.group(0).strip()
                if len(decision) > 10:
                    self.memory.add_decision(decision[:100], source="model")
                    break  # 只提取第一个



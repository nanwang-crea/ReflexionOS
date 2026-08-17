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
from typing import TYPE_CHECKING

from app.memory.working_memory import WorkingMemory

if TYPE_CHECKING:
    # 仅用于类型注解，运行时不导入；补上后类型检查器/IDE 能正确
    # 解析 __init__ 中 "SessionTracker | None" 这个前向引用注解
    from app.memory.session_tracker import SessionTracker

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    从 tool 调用结果中自动提取关键信息，写入 Working Memory

    集成点：tool_call_executor 中 tool 执行完成后
    设计原则：纯规则提取，不调用 LLM，避免延迟和成本
    """

    def __init__(self, memory: WorkingMemory, session_tracker: "SessionTracker | None" = None):
        """
        参数：
            memory: 待写入的 WorkingMemory 实例，提取出的信息会调用其 add_decision/
                    set_variable/add_error 等接口写入。
            session_tracker: 可选的 SessionTracker，用于同步记录"发生了什么"（文件访问等
                    元数据）；为 None 时跳过该记录。
        逻辑：仅做字段赋值，不做其他初始化。
        返回：无。
        """
        self.memory = memory
        self.session_tracker = session_tracker

    def extract(self, tool_name: str, tool_args: dict, tool_result: str, step: int = 0) -> None:
        """
        根据 tool 类型自动提取信息

        Args:
            tool_name: 工具名称（与 ToolRegistry 注册名一致）
            tool_args: 工具调用参数
            tool_result: 工具执行结果（字符串形式）
            step: 当前所处的执行步数，透传给 SessionTracker.record_from_tool 用于定位。
        逻辑：
            按 tool_name 分派到对应的 _extract_from_* 规则提取方法（写入 WorkingMemory）；
            随后若配置了 session_tracker，则额外调用其 record_from_tool 记录工具调用元数据；
            整个过程包裹在 try/except 中，提取失败只记 debug 日志，不向上抛出（不影响主流程）。
        返回：无（副作用是写入 self.memory / self.session_tracker）。
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
        """
        命令执行结果中提取变量/错误

        参数：
            args: shell 工具调用参数，取其中的 "command" 字段。
            result: shell 命令执行的输出文本。
        逻辑：
            1. 若结果文本包含 "error"/"failed"（不区分大小写），截取前 200 字符作为
               错误摘要，写入一条 command_error 错误记录；
            2. 若命令或结果中出现 "export "/"=" 迹象，用正则"单词=非空白"扫描结果中的
               键值对，过滤掉过长的 key/value（疑似文件内容），把疑似环境变量/配置的
               键值写入 WorkingMemory 变量集。
        返回：无（副作用写入 self.memory）。
        """
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
        """
        recall 结果中提取关键信息

        参数：
            args: session_recall 工具调用参数，取其中的 "query" 字段。
            result: recall 返回的文本结果。
        逻辑：结果非空且长度 > 50 时，以 "recall:<query前30字符>" 为 key，
              截取结果前 200 字符作为 value 写入 WorkingMemory 变量集。
        返回：无。
        """
        query = args.get("query", "")
        if result and len(result) > 50:
            self.memory.set_variable(f"recall:{query[:30]}", result[:200], source="auto")

    def _extract_from_explore(self, args: dict, result: str) -> None:
        """
        探索结果中提取结构信息

        参数：
            args: explore 工具调用参数，取其中的 "query" 字段。
            result: explore 返回的代码库结构概览文本。
        逻辑：结果为空则直接返回；否则将结果前 150 字符去换行、去首尾空白后作为摘要，
              以 "explore:<query前30字符>" 为 key 写入 WorkingMemory 变量集。
        返回：无。
        """
        # explore 工具返回代码库结构概览，提取关键模块名
        if not result:
            return
        # 简单提取：记录探索查询和结果摘要
        query = args.get("query", "")
        if query:
            summary = result[:150].replace("\n", " ").strip()
            self.memory.set_variable(f"explore:{query[:30]}", summary, source="auto")

    def extract_from_response(self, model_output: str) -> None:
        """
        从模型输出中提取决策和关键信息（由 extract() 自动调用）

        参数：model_output - 模型生成的自然语言文本。
        逻辑：
            用两条正则模式匹配"决策语气"的句子（如 "I'll use X because Y"、
            "I decided to X"），这是轻量级规则提取，不调用 LLM；
            按顺序尝试各 pattern，命中且长度 > 10 则截取前 100 字符作为决策内容
            写入 WorkingMemory（source="model"），只取第一个匹配就停止。
        返回：无（为空输入直接返回）。
        """
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



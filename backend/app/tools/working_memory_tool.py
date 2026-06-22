"""
WorkingMemory 工具：允许模型主动读写工作记忆。

模型通过 working_memory_update 工具向工作记忆写入信息，
系统在每轮对话开始时自动注入当前工作记忆内容。

WorkingMemory 数据结构：
- file_index: 文件摘要字典（key=路径, value=摘要）
- decisions: 关键决策列表
- variables: 变量/配置字典（key=变量名, value=值）
- errors: 错误记录列表
"""

import logging
from typing import Any

from app.memory.working_memory import WorkingMemory
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# 有效的 slot 名称
VALID_SLOTS = frozenset({
    "file_index",   # 文件摘要：upsert_file(path, summary, source)
    "decisions",    # 关键决策：add_decision(decision, rationale, source)
    "variables",    # 变量/配置：set_variable(name, value, source)
    "errors",       # 错误记录：add_error(error_type, detail, source)
})

VALID_ACTIONS = frozenset({"add", "update", "remove", "clear"})


class WorkingMemoryTool(BaseTool):
    """模型主动更新工作记忆的工具。

    通过 set_working_memory() 注入 LoopContext 中的 WorkingMemory 实例，
    然后 execute() 直接操作该实例，无需 executor 中的特殊拦截。
    """

    def __init__(self):
        self._working_memory: WorkingMemory | None = None

    @property
    def name(self) -> str:
        return "working_memory_update"

    @property
    def description(self) -> str:
        return (
            "更新工作记忆（Working Memory）。"
            "工作记忆在每轮对话中自动注入到上下文，用于维护跨步骤的关键信息。"
            "支持的操作：add（添加/更新）、update（同 add，upsert 语义）、remove（移除）、clear（清空）。"
            "可用 slot："
            "file_index（文件摘要，需提供 key=文件路径, content=摘要）、"
            "decisions（关键决策，content=决策内容, rationale=理由）、"
            "variables（变量/配置，key=变量名, content=值）、"
            "errors（错误记录，key=错误类型, content=详情）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "update", "remove", "clear"],
                    "description": (
                        "操作类型：add=添加/更新，update=同add（upsert语义），"
                        "remove=移除指定项，clear=清空整个slot"
                    ),
                },
                "slot": {
                    "type": "string",
                    "enum": ["file_index", "decisions", "variables", "errors"],
                    "description": "要操作的slot名称",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容（remove/clear时可省略）",
                },
                "key": {
                    "type": "string",
                    "description": "dict类型slot的键名（file_index的路径、variables的变量名、errors的错误类型）",
                },
                "rationale": {
                    "type": "string",
                    "description": "decisions的理由（可选）",
                },
                "source": {
                    "type": "string",
                    "enum": ["model", "auto"],
                    "description": "来源标识，默认为model",
                },
            },
            "required": ["action", "slot"],
        }

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def set_working_memory(self, working_memory: WorkingMemory | None):
        """注入 WorkingMemory 实例，在 execute 前由 executor 调用。"""
        self._working_memory = working_memory

    def get_working_memory(self) -> WorkingMemory | None:
        """获取当前 WorkingMemory 实例。"""
        return self._working_memory

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行工作记忆更新操作。"""
        if self._working_memory is None:
            return ToolResult(
                output="错误: 工作记忆不可用",
                success=False,
            )

        action = args.get("action", "")
        slot = args.get("slot", "")

        # 验证 action
        if action not in VALID_ACTIONS:
            return ToolResult(
                output=f"错误: 无效的 action '{action}'，有效值为 {VALID_ACTIONS}",
                success=False,
            )

        # 验证 slot
        if slot not in VALID_SLOTS:
            return ToolResult(
                output=f"错误: 无效的 slot '{slot}'，有效值为 {VALID_SLOTS}",
                success=False,
            )

        source = args.get("source", "model")

        try:
            if action == "clear":
                result = self._handle_clear(slot)
            elif action in ("add", "update"):
                # update 等同于 add（upsert 语义）
                result = self._handle_add(slot, args, source)
            elif action == "remove":
                result = self._handle_remove(slot, args)
            else:
                result = f"错误: 未知操作 '{action}'"

            success = not result.startswith("错误")
            return ToolResult(output=result, success=success)

        except Exception as e:
            logger.warning("working_memory_update 处理失败: %s", e, exc_info=True)
            return ToolResult(
                output=f"错误: 处理失败 - {e}",
                success=False,
            )

    # -- slot 操作方法 -------------------------------------------------------

    def _handle_clear(self, slot: str) -> str:
        """清空指定 slot"""
        wm = self._working_memory
        if slot == "file_index":
            wm.file_index.clear()
        elif slot == "decisions":
            wm.decisions.clear()
        elif slot == "variables":
            wm.variables.clear()
        elif slot == "errors":
            wm.errors.clear()
        return f"已清空 {slot}"

    def _handle_add(self, slot: str, args: dict[str, Any], source: str) -> str:
        """向 slot 添加内容（upsert 语义）"""
        wm = self._working_memory

        if slot == "file_index":
            key = args.get("key", "")
            content = args.get("content", "")
            if not key:
                return "错误: file_index 的 add 操作需要提供 key（文件路径）"
            wm.upsert_file(path=key, summary=str(content), source=source)
            return f"已添加文件摘要: {key}"

        if slot == "decisions":
            content = args.get("content", "")
            if not content:
                return "错误: decisions 的 add 操作需要提供 content（决策内容）"
            rationale = args.get("rationale", "")
            wm.add_decision(decision=str(content), rationale=str(rationale), source=source)
            return f"已记录决策: {str(content)[:50]}"

        if slot == "variables":
            key = args.get("key", "")
            content = args.get("content", "")
            if not key:
                return "错误: variables 的 add 操作需要提供 key（变量名）"
            wm.set_variable(name=key, value=str(content), source=source)
            return f"已设置变量: {key} = {str(content)[:50]}"

        if slot == "errors":
            key = args.get("key", "")
            content = args.get("content", "")
            if not key:
                return "错误: errors 的 add 操作需要提供 key（错误类型）"
            wm.add_error(error_type=str(key), detail=str(content), source=source)
            return f"已记录错误: [{key}] {str(content)[:50]}"

        return f"错误: 未知的 slot {slot}"

    def _handle_remove(self, slot: str, args: dict[str, Any]) -> str:
        """从 slot 移除内容"""
        wm = self._working_memory
        key = args.get("key", "")
        content = args.get("content", "")

        if slot == "file_index":
            if key and key in wm.file_index:
                del wm.file_index[key]
                return f"已移除文件摘要: {key}"
            return f"错误: 文件 '{key}' 不在 file_index 中"

        if slot == "decisions":
            if not wm.decisions:
                return "错误: decisions 为空"
            target = str(content) if content else str(key)
            for i, entry in enumerate(wm.decisions):
                if target in entry.key:
                    wm.decisions.pop(i)
                    return f"已移除决策: {entry.key[:50]}"
            return f"错误: decisions 中未找到匹配 '{target}' 的项"

        if slot == "variables":
            target = key if key else str(content)
            if target in wm.variables:
                del wm.variables[target]
                return f"已移除变量: {target}"
            return f"错误: variables 中不存在 '{target}'"

        if slot == "errors":
            if not wm.errors:
                return "错误: errors 为空"
            target = str(content) if content else str(key)
            for i, entry in enumerate(wm.errors):
                if target in entry.key:
                    wm.errors.pop(i)
                    return f"已移除错误: [{entry.key}]"
            return f"错误: errors 中未找到匹配 '{target}' 的项"

        return f"错误: 未知的 slot {slot}"

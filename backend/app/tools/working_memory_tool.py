"""
WorkingMemory 工具：允许模型主动读写工作记忆。

模型通过 working_memory_update 工具向工作记忆写入信息，
系统在每轮对话开始时自动注入当前工作记忆内容。

WorkingMemory 数据结构：
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
        """初始化 WorkingMemoryTool，工作记忆实例初始为空，需在执行前通过 set_working_memory 注入。"""
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
                    "enum": ["decisions", "variables", "errors"],
                    "description": "要操作的slot名称",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容（remove/clear时可省略）",
                },
                "key": {
                    "type": "string",
                    "description": "dict类型slot的键名（variables的变量名、errors的错误类型）",
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
        """返回本工具的 JSON Schema 定义（供 LLM 函数调用使用）。

        入参：无
        功能：拼装 name/description/parameters 为标准 tool schema 结构。
        出参：dict - OpenAI/Anthropic 兼容的 tool schema 字典。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def set_working_memory(self, working_memory: WorkingMemory | None):
        """注入 WorkingMemory 实例，在 execute 前由 executor 调用。

        入参：working_memory (WorkingMemory | None) - 当前 LoopContext 关联的工作记忆实例，
        传 None 表示暂无可用的工作记忆（此时 execute 会返回失败）。
        出参：无。
        """
        self._working_memory = working_memory

    def get_working_memory(self) -> WorkingMemory | None:
        """获取当前 WorkingMemory 实例。

        入参：无。
        出参：WorkingMemory | None - 当前注入的工作记忆实例，未注入时为 None。
        """
        return self._working_memory

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行工作记忆更新操作。

        入参：args (dict) - 包含 action（必填，add/update/remove/clear）、
        slot（必填，decisions/variables/errors）、content（写入内容，remove/clear 可省略）、
        key（dict 类slot的键名）、rationale（decisions 专用，决策理由）、
        source（来源标识，默认 model）。
        功能：
          1. 校验工作记忆实例已注入、action/slot 合法；
          2. 按 action 分发到对应 handler：clear 清空整个 slot；add/update（等价，upsert 语义）
             写入/更新一项；remove 按 key 精确匹配并移除一项；
          3. 捕获 handler 抛出的异常，转换为失败结果。
        出参：ToolResult - success + 操作结果说明文本（成功放 output，失败放 error）。
        """
        if self._working_memory is None:
            return ToolResult(
                error="工作记忆不可用",
                success=False,
            )

        action = args.get("action", "")
        slot = args.get("slot", "")

        # 验证 action
        if action not in VALID_ACTIONS:
            return ToolResult(
                error=f"无效的 action '{action}'，有效值为 {VALID_ACTIONS}",
                success=False,
            )

        # 验证 slot
        if slot not in VALID_SLOTS:
            return ToolResult(
                error=f"无效的 slot '{slot}'，有效值为 {VALID_SLOTS}",
                success=False,
            )

        source = args.get("source", "model")

        try:
            # 每个 handler 返回 (success: bool, message: str) 元组
            if action == "clear":
                ok, msg = self._handle_clear(slot)
            elif action in ("add", "update"):
                # update 等同于 add（upsert 语义）
                ok, msg = self._handle_add(slot, args, source)
            elif action == "remove":
                ok, msg = self._handle_remove(slot, args)
            else:
                ok, msg = False, f"未知操作 '{action}'"

            return ToolResult(
                success=ok,
                output=msg if ok else None,
                error=msg if not ok else None,
            )

        except Exception as e:
            logger.warning("working_memory_update 处理失败: %s", e, exc_info=True)
            return ToolResult(
                error=f"处理失败 - {e}",
                success=False,
            )

    # -- slot 操作方法 -------------------------------------------------------

    def _handle_clear(self, slot: str) -> tuple[bool, str]:
        """清空指定 slot。

        入参：slot (str) - 目标 slot 名称（decisions/variables/errors）。
        出参：tuple[bool, str] - (是否成功, 结果说明文本)。
        """
        wm = self._working_memory
        if slot == "decisions":
            wm.decisions.clear()
        elif slot == "variables":
            wm.variables.clear()
        elif slot == "errors":
            wm.errors.clear()
        else:
            return False, f"未知的 slot: {slot}"
        return True, f"已清空 {slot}"

    def _handle_add(self, slot: str, args: dict[str, Any], source: str) -> tuple[bool, str]:
        """向 slot 添加内容（upsert 语义）。

        入参：
          - slot (str): 目标 slot 名称
          - args (dict): execute 透传的原始参数，用于取 content/key/rationale
          - source (str): 来源标识（"model" 或 "auto"），写入记录时一并保存
        功能：按 slot 类型分别校验必填字段并调用 WorkingMemory 对应的写入方法——
        decisions 需要 content；variables 需要 key；errors 需要 key。
        出参：tuple[bool, str] - (是否成功, 结果说明文本，含内容截断预览)。
        """
        wm = self._working_memory

        if slot == "decisions":
            content = args.get("content", "")
            if not content:
                return False, "decisions 的 add 操作需要提供 content（决策内容）"
            rationale = args.get("rationale", "")
            wm.add_decision(decision=str(content), rationale=str(rationale), source=source)
            return True, f"已记录决策: {str(content)[:50]}"

        if slot == "variables":
            key = args.get("key", "")
            content = args.get("content", "")
            if not key:
                return False, "variables 的 add 操作需要提供 key（变量名）"
            wm.set_variable(name=key, value=str(content), source=source)
            return True, f"已设置变量: {key} = {str(content)[:50]}"

        if slot == "errors":
            key = args.get("key", "")
            content = args.get("content", "")
            if not key:
                return False, "errors 的 add 操作需要提供 key（错误类型）"
            wm.add_error(error_type=str(key), detail=str(content), source=source)
            return True, f"已记录错误: [{key}] {str(content)[:50]}"

        # slot 已在 execute() 中验证，理论上不会走到这里
        return False, f"未知的 slot: {slot}"

    def _handle_remove(self, slot: str, args: dict[str, Any]) -> tuple[bool, str]:
        """从 slot 移除内容（精确 key 匹配）。

        入参：
          - slot (str): 目标 slot 名称
          - args (dict): execute 透传的原始参数，用于取 key/content 作为匹配目标
        功能：decisions/errors 是列表结构，按 entry.key 精确匹配后 pop；
        variables 是 dict 结构，按 key 直接 del。未提供 key 时退化用 content 作匹配目标。
        出参：tuple[bool, str] - (是否成功, 结果说明文本；未命中或 slot 为空时返回失败)。
        """
        wm = self._working_memory
        key = args.get("key", "")
        content = args.get("content", "")

        if slot == "decisions":
            if not wm.decisions:
                return False, "decisions 为空"
            # decisions 的匹配键是 content（即决策内容，存储在 entry.key 中）
            target = str(content) if content else str(key)
            for i, entry in enumerate(wm.decisions):
                if entry.key == target:
                    wm.decisions.pop(i)
                    return True, f"已移除决策: {entry.key[:50]}"
            return False, f"decisions 中未找到匹配 '{target}' 的项"

        if slot == "variables":
            target = key if key else str(content)
            if target in wm.variables:
                del wm.variables[target]
                return True, f"已移除变量: {target}"
            return False, f"variables 中不存在 '{target}'"

        if slot == "errors":
            if not wm.errors:
                return False, "errors 为空"
            # errors 的匹配键是 key（即错误类型，存储在 entry.key 中）
            target = str(key) if key else str(content)
            for i, entry in enumerate(wm.errors):
                if entry.key == target:
                    wm.errors.pop(i)
                    return True, f"已移除错误: [{entry.key}]"
            return False, f"errors 中未找到匹配 '{target}' 的项"

        # slot 已在 execute() 中验证，理论上不会走到这里
        return False, f"未知的 slot: {slot}"

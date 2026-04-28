import logging
from typing import Any

from app.memory.curated_store import CuratedEntry, CuratedMemoryStore
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MemoryTool(BaseTool):
    """
    Curated memory tool (project-level): add / replace / remove entries that render to USER.md / MEMORY.md.

    This tool is intentionally scoped to curated memory foundation only; it does not do prompt assembly or syncing.
    """

    def __init__(self, store: CuratedMemoryStore | None = None):
        self.store = store or CuratedMemoryStore()

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "项目级 curated memory 管理工具：add / replace / remove (渲染 USER.md / MEMORY.md)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "replace", "remove"],
                        "description": "操作类型",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "项目 ID",
                    },
                    "target": {
                        "type": "string",
                        "enum": ["user", "memory"],
                        "description": "目标视图（replace/remove 需要）",
                    },
                    "entry": {
                        "type": "object",
                        "description": "CuratedEntry 对象（add/replace 需要）",
                    },
                    "old_summary": {
                        "type": "string",
                        "description": "被替换条目的 summary（replace 需要）",
                    },
                    "summary": {
                        "type": "string",
                        "description": "要移除条目的 summary（remove 需要）",
                    },
                },
                "required": ["action", "project_id"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action")
        project_id = args.get("project_id")

        if not action:
            return ToolResult(success=False, error="缺少 action 参数")
        if not project_id:
            return ToolResult(success=False, error="缺少 project_id 参数")

        try:
            if action == "add":
                entry_dict = args.get("entry")
                if not isinstance(entry_dict, dict):
                    return ToolResult(success=False, error="缺少 entry 参数")

                result = self.store.add_entry(
                    project_id=project_id,
                    entry=CuratedEntry(**entry_dict),
                )
                return ToolResult(success=result.success, data=result.model_dump(mode="json"))

            if action == "replace":
                target = args.get("target")
                old_summary = args.get("old_summary")
                entry_dict = args.get("entry")
                if target not in ("user", "memory"):
                    return ToolResult(success=False, error="replace 需要 target='user'|'memory'")
                if not old_summary:
                    return ToolResult(success=False, error="replace 需要 old_summary 参数")
                if not isinstance(entry_dict, dict):
                    return ToolResult(success=False, error="replace 需要 entry 参数")

                result = self.store.replace_entry(
                    project_id=project_id,
                    target=target,
                    old_summary=old_summary,
                    entry=CuratedEntry(**entry_dict),
                )
                return ToolResult(success=result.success, data=result.model_dump(mode="json"))

            if action == "remove":
                target = args.get("target")
                summary = args.get("summary")
                if target not in ("user", "memory"):
                    return ToolResult(success=False, error="remove 需要 target='user'|'memory'")
                if not summary:
                    return ToolResult(success=False, error="remove 需要 summary 参数")

                removed = self.store.remove_entry(project_id=project_id, target=target, summary=summary)
                return ToolResult(success=removed, data={"removed": removed})

            return ToolResult(success=False, error=f"unsupported memory action: {action}")
        except Exception as exc:
            logger.error("memory tool execute failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


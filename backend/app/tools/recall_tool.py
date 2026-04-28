import logging
from typing import Any

from app.memory.recall_service import RecallService
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class RecallTool(BaseTool):
    def __init__(self, *, recall_service: RecallService | None = None):
        self.recall_service = recall_service or RecallService()

    @property
    def name(self) -> str:
        return "recall"

    @property
    def description(self) -> str:
        return "基于 message_search_documents 的确定性 recall（project-scoped），返回 summary + evidence"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "项目 ID"},
                    "query": {"type": "string", "description": "搜索查询"},
                    "limit": {
                        "type": "integer",
                        "description": "返回条数（默认 3）",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["project_id", "query"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        project_id = args.get("project_id")
        query = args.get("query")
        limit = args.get("limit", 3)

        if not project_id:
            return ToolResult(success=False, error="缺少 project_id 参数")
        if not query:
            return ToolResult(success=False, error="缺少 query 参数")

        try:
            resolved_limit = int(limit) if limit is not None else 3
            results = self.recall_service.search(
                project_id=str(project_id),
                query=str(query),
                limit=max(1, min(resolved_limit, 20)),
            )
            return ToolResult(
                success=True,
                data={"results": [result.model_dump(mode="json") for result in results]},
                output="\n\n".join(result.summary for result in results),
            )
        except Exception as exc:
            logger.exception("recall tool execute failed")
            return ToolResult(success=False, error=str(exc))


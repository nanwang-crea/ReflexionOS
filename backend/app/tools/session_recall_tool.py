from typing import Any

from app.memory.recall_service import RecallService
from app.tools.base import BaseTool, ToolResult


class SessionRecallTool(BaseTool):
    """
    Session 内 Recall Tool：从 DB 按需取回当前 session 的历史消息完整内容。
    当 Tier 2/3 压缩截断或摘要中标记 [可 session_recall 取回] 时，agent 可调用此工具回溯细节。
    与跨 session 的 RecallService 共享搜索排序逻辑，但限定 session_id 作用域并返回完整内容。
    """

    def __init__(
        self,
        *,
        session_id: str,
        project_id: str,
        recall_service: RecallService | None = None,
    ):
        self._session_id = session_id
        self._project_id = project_id
        self._recall_service = recall_service or RecallService()

    @property
    def name(self) -> str:
        return "session_recall"

    @property
    def description(self) -> str:
        return (
            "在当前会话历史中搜索之前的对话、文件读取、工具输出等完整内容。"
            "当压缩摘要中标记 [可 session_recall 取回] 时可使用此工具取回完整内容。"
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要查找的内容关键词",
                    },
                    "message_type": {
                        "type": "string",
                        "enum": ["tool_trace", "user_message", "assistant_message", "all"],
                        "description": "筛选消息类型（默认 all）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量（默认 3）",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        if not query:
            return ToolResult(success=True, data={"results": [], "message": "空查询，无结果"})

        limit = args.get("limit", 3)
        results = self._recall_service.search(
            project_id=self._project_id,
            query=query,
            limit=limit,
        )

        message_type_filter = args.get("message_type", "all")
        if message_type_filter != "all":
            results = [r for r in results if message_type_filter in r.summary]

        if not results:
            return ToolResult(
                success=True,
                data={"results": [], "message": f"未找到与 '{query}' 相关的内容"},
            )

        formatted = []
        for r in results:
            formatted.append({
                "score": round(r.score, 3),
                "summary": r.summary,
                "evidence": r.evidence,
            })

        return ToolResult(success=True, data={"results": formatted})

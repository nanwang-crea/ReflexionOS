# Session 内历史回溯工具：当上下文压缩（Tier 2/3）把早期消息截断/摘要后，
# Agent 可通过本工具按关键词从数据库检索回当前 session 内被压缩前的完整原文内容。
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
        """初始化 SessionRecallTool。

        入参：
          - session_id (str): 当前会话 ID，检索范围限定在该会话内
          - project_id (str): 所属项目 ID
          - recall_service (RecallService | None): 底层检索服务，不传则新建默认实例
        """
        self._session_id = session_id
        self._project_id = project_id
        self._recall_service = recall_service or RecallService()

    @property
    def name(self) -> str:
        return "session_recall"

    @property
    def description(self) -> str:
        # 面向 LLM 的工具功能说明，保留英文原文
        return (
            "Search the current session history for previous conversations, file reads, tool outputs, etc. "
            "When a compressed summary is marked with [session_recall can retrieve], use this tool to retrieve the full content."
        )

    def get_schema(self) -> dict[str, Any]:
        """返回本工具的 JSON Schema 定义（供 LLM 函数调用使用）。

        入参：无
        功能：声明 session_recall 工具的参数结构——query（必填，检索关键词）、
        message_type（可选，按消息类型过滤）、limit（可选，返回条数，默认 3）。
        出参：dict - OpenAI/Anthropic 兼容的 tool schema 字典。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Content keyword to search for",
                    },
                    "message_type": {
                        "type": "string",
                        "enum": ["tool_trace", "user_message", "assistant_message", "all"],
                        "description": "Filter by message type (default: all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return (default: 3)",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """按关键词检索当前 session 历史，返回完整原文内容。

        入参：args (dict) - 包含 query（必填，检索关键词）、
        message_type（可选，tool_trace/user_message/assistant_message/all，默认 all）、
        limit（可选，返回条数，默认 3）。
        功能：
          1. 校验 query 非空；
          2. 调用 RecallService.search 在 project_id+session_id 范围内做相关性检索；
          3. 若指定了 message_type 且非 all，按摘要文本中是否包含该类型关键字做二次过滤；
          4. 组装带相关性分数(score)、摘要(summary)、证据片段(evidence)的展示文本。
        出参：ToolResult - success 恒为 True；output 为格式化文本；data.results 为结构化结果列表。
        """
        query = args.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="query is required and cannot be empty")

        limit = args.get("limit", 3)
        results = self._recall_service.search(
            project_id=self._project_id,
            session_id=self._session_id,
            query=query,
            limit=limit,
        )

        message_type_filter = args.get("message_type", "all")
        if message_type_filter != "all":
            results = [r for r in results if message_type_filter in r.summary]

        if not results:
            return ToolResult(
                success=True,
                output=f"No results found for '{query}'",
                data={"results": [], "message": f"No results found for '{query}'"},
            )

        formatted = []
        for r in results:
            formatted.append({
                "score": round(r.score, 3),
                "summary": r.summary,
                "evidence": r.evidence,
            })

        output_parts: list[str] = []
        for r in results:
            output_parts.append(f"[score={round(r.score, 3)}] {r.summary}")
            for ev in r.evidence:
                output_parts.append(f"  {ev}")
        output_text = "\n".join(output_parts)

        return ToolResult(success=True, output=output_text, data={"results": formatted})

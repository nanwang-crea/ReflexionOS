# 工具注册中心：集中管理所有 BaseTool 实例，供 Agent 执行循环按名称查找、
# 获取 Schema 并转换为 LLM 可用的工具定义格式。
import logging

from app.errors import ToolNotFoundError
from app.llm.base import LLMToolDefinition
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册和管理中心"""

    def __init__(self):
        """初始化空的工具注册表。"""
        self.tools: dict[str, BaseTool] = {}
        logger.info("工具注册中心初始化完成")

    def register(self, tool: BaseTool) -> None:
        """注册工具。

        入参：tool (BaseTool) - 待注册的工具实例，以其 tool.name 为键存入注册表。
        功能：同名工具会被直接覆盖（后注册的生效）。
        出参：无。
        """
        self.tools[tool.name] = tool
        logger.info("注册工具: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        """获取工具。

        入参：name (str) - 工具名称。
        出参：BaseTool | None - 已注册的工具实例，未找到返回 None。
        """
        return self.tools.get(name)

    def get_tool_schema(self, name: str) -> dict:
        """获取工具的 JSON Schema。

        入参：name (str) - 工具名称。
        功能：查找对应工具并调用其 get_schema()；未注册的工具名会抛出 ToolNotFoundError。
        出参：dict - 该工具的 JSON Schema 定义。
        """
        tool = self.get(name)
        if not tool:
            raise ToolNotFoundError(tool_name=name)
        return tool.get_schema()

    @staticmethod
    def definition_from_schema(schema: dict) -> LLMToolDefinition:
        """将工具的原始 JSON Schema 转换为统一的 LLMToolDefinition 结构。

        入参：schema (dict) - 工具的 get_schema() 返回值，需含 name/description，
        参数结构可能是 "parameters"（OpenAI 风格）或 "input_schema"（Anthropic 风格）字段。
        功能：兼容两种上游命名习惯，统一取出参数结构字段。
        出参：LLMToolDefinition - 标准化后的工具定义对象。
        """
        parameters = schema.get("parameters") or schema.get("input_schema", {})
        return LLMToolDefinition(
            name=schema["name"],
            description=schema["description"],
            parameters=parameters,
        )

    def get_all_schemas(self) -> list[dict]:
        """获取所有工具的 Schema。

        入参：无。
        功能：按工具名排序遍历，保证多次调用返回顺序一致（便于测试/调用方缓存比对）。
        出参：list[dict] - 所有已注册工具的 Schema 列表。
        """
        # Keep ordering deterministic for callers/tests.
        return [self.tools[name].get_schema() for name in sorted(self.tools.keys())]

    def get_tool_definitions(self) -> list[LLMToolDefinition]:
        """
        获取所有工具的定义（统一格式）

        用于传递给 LLM 的 tools 参数

        入参：无。
        功能：按工具名排序遍历所有已注册工具，逐个转换为 LLMToolDefinition。

        Returns:
            List[LLMToolDefinition]: 工具定义列表
        """
        definitions = []
        # Keep ordering deterministic for callers/tests.
        for name in sorted(self.tools.keys()):
            tool = self.tools[name]
            schema = tool.get_schema()
            definitions.append(self.definition_from_schema(schema))
        return definitions

    def list_tools(self) -> list[str]:
        """列出所有注册的工具名称。

        入参：无。
        出参：list[str] - 按字母排序的工具名列表。
        """
        return sorted(self.tools.keys())

    def list_tools_excluding(self, exclude: frozenset[str]) -> list[str]:
        """返回排除指定工具名后的所有工具名列表（保持排序）。

        入参：exclude (frozenset[str]) - 需要排除的工具名集合。
        出参：list[str] - 排除后剩余的工具名，按字母排序。
        """
        return sorted(name for name in self.tools if name not in exclude)

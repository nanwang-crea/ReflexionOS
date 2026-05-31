import logging
from typing import Any

from app.orchestration.skill_registry import SkillRegistry
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    @property
    def name(self) -> str:
        return "skill"

    @property
    def description(self) -> str:
        return "Discover and load skill guides. Use 'list' to see available skills, 'load' to read a skill's full content, 'search' to find skills by keyword."

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "load", "search"],
                        "description": "Action: 'list' all skills, 'load' a skill's content, 'search' by keyword",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (required for 'load' action)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search keyword (required for 'search' action)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action", "list")

        if action == "list":
            skills = self._registry.list_enabled_skills()
            lines = []
            for s in skills:
                req = f" (requires: {', '.join(s.required_skills)})" if s.required_skills else ""
                lines.append(f"- {s.name}: {s.description}{req}")
            output = "Available skills:\n" + "\n".join(lines) if lines else "No skills available."
            return ToolResult(success=True, output=output)

        if action == "load":
            skill_name = args.get("name", "")
            content = self._registry.get_skill_content(skill_name)
            if content is None:
                return ToolResult(success=False, error=f"Skill not found: {skill_name}")
            skill = self._registry.get_skill(skill_name)
            header = f"# {skill.name}\n\n> {skill.description}\n\n"
            return ToolResult(success=True, output=header + content)

        if action == "search":
            query = (args.get("query") or "").lower()
            if not query:
                return ToolResult(success=False, error="Search query is required")
            matches = []
            for s in self._registry.list_enabled_skills():
                searchable = f"{s.name} {s.description} {s.category}".lower()
                if query in searchable:
                    matches.append(f"- {s.name}: {s.description}")
            output = "Matching skills:\n" + "\n".join(matches) if matches else "No skills match the query."
            return ToolResult(success=True, output=output)

        return ToolResult(success=False, error=f"Unknown action: {action}")

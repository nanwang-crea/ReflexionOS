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
        return ("Discover, install, and manage skill guides. "
                "Use 'list' to see skills, 'load' to read content, "
                "'search' by keyword, 'install' from Git URL, "
                "'uninstall' a skill.")

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "load", "search", "install", "uninstall"],
                        "description": ("Action: 'list' all skills, 'load' a "
                                        "skill's content, 'search' by keyword, "
                                        "'install' from Git URL, "
                                        "'uninstall' a skill"),
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (required for 'load' action)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search keyword (required for 'search' action)",
                    },
                    "url": {
                        "type": "string",
                        "description": "Git repository URL (required for 'install')",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": ("Skill name (required for 'install' and "
                                        "'uninstall')"),
                    },
                    "subdir": {
                        "type": "string",
                        "description": ("Subdirectory path within repo (optional "
                                        "for 'install')"),
                    },
                    "branch": {
                        "type": "string",
                        "description": "Git branch (optional for 'install', default main)",
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
                req_str = ", ".join(s.required_skills)
                req = f" (requires: {req_str})" if s.required_skills else ""
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
            if matches:
                output = "Matching skills:\n" + "\n".join(matches)
            else:
                output = "No skills match the query."
            return ToolResult(success=True, output=output)

        if action == "install":
            url = args.get("url", "")
            s_name = args.get("skill_name") or args.get("name", "")
            if not url or not s_name:
                return ToolResult(
                    success=False,
                    error="url and skill_name required for install",
                )
            subdir = args.get("subdir", "")
            branch = args.get("branch", "main")
            result = self._registry.install_skill(url, s_name, subdir, branch)
            if result.success:
                return ToolResult(
                    success=True,
                    output=f"Installed skill '{s_name}' to "
                           f"{result.install_path}",
                )
            return ToolResult(success=False, error=result.error)

        if action == "uninstall":
            s_name = args.get("skill_name") or args.get("name", "")
            if not s_name:
                return ToolResult(
                    success=False,
                    error="skill_name required for uninstall",
                )
            result = self._registry.uninstall_skill(s_name)
            if result.success:
                return ToolResult(
                    success=True,
                    output=f"Uninstalled skill '{s_name}'",
                )
            return ToolResult(success=False, error=result.error)

        return ToolResult(success=False, error=f"Unknown action: {action}")

import logging
from typing import Any

from app.orchestration.skill_registry import SkillRegistry
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    def __init__(self, registry: SkillRegistry, resolver=None):
        self._registry = registry
        self._resolver = resolver

    @property
    def name(self) -> str:
        return "skill"

    @property
    def description(self) -> str:
        return ("Discover and load skill guides. "
                "Use 'list' to see skills, 'load' to read content, "
                "'search' by keyword, 'update' to check for plugin updates.")

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "load", "search", "update"],
                        "description": ("Action: 'list' all skills, "
                                        "'load' a skill's content, "
                                        "'search' by keyword, "
                                        "'update' check for plugin updates"),
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
                req_str = ", ".join(s.required_skills)
                req = f" (requires: {req_str})" if s.required_skills else ""
                source = f" [{s.source_type}]" if s.source_type and s.source_type.value != "project" else ""
                lines.append(f"- {s.name}: {s.description}{req}{source}")
            output = "Available skills:\n" + "\n".join(lines) if lines else "No skills available."
            return ToolResult(success=True, output=output)

        if action == "load":
            skill_name = args.get("name", "")
            content = self._registry.get_skill_content(skill_name)
            if content is None:
                return ToolResult(success=False, error=f"Skill not found: {skill_name}")
            skill = self._registry.get_skill(skill_name)
            header = f"# {skill.name}\n\n> {skill.description}\n\n"
            if skill.install_path:
                header = f"**Skill directory:** `{skill.install_path}`\n\n{header}"
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

        if action == "update":
            if self._resolver is None:
                return ToolResult(success=False, error="No package resolver configured")
            from app.config.settings import config_manager
            plugin_settings = config_manager.settings.plugin
            if not plugin_settings.plugins:
                return ToolResult(success=True, output="No plugins configured.")
            results = []
            for spec_str in plugin_settings.plugins:
                from app.orchestration.package_resolver import PackageSpecifier
                spec = PackageSpecifier.parse(spec_str)
                try:
                    has_update = self._resolver.is_update_available(spec)
                    if has_update:
                        self._resolver.update(spec)
                        results.append(f"Updated: {spec.name}")
                    else:
                        results.append(f"Up to date: {spec.name}")
                except Exception as e:
                    results.append(f"Error checking {spec.name}: {e}")
            return ToolResult(success=True, output="\n".join(results))

        return ToolResult(success=False, error=f"Unknown action: {action}")

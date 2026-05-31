import pytest
from unittest.mock import patch

from app.orchestration.skill_installer import InstallResult
from app.orchestration.skill_registry import SkillMetadata, SkillRegistry
from app.tools.skill_tool import SkillTool


@pytest.fixture
def registry():
    r = SkillRegistry()
    r.register_skill(
        SkillMetadata(
            name="brainstorming",
            description="Use when exploring ideas.",
            category="discipline",
            file_path="/fake/SKILL.md",
        )
    )
    r._content_cache["brainstorming"] = "# Brainstorming\n\nHelp turn ideas into designs."
    r.register_skill(
        SkillMetadata(
            name="tdd",
            description="Use when implementing features.",
            category="discipline",
            enabled=False,
            file_path="/fake2/SKILL.md",
        )
    )
    r._content_cache["tdd"] = "# TDD\n\nWrite test first."
    return r


class TestSkillTool:
    def test_schema(self, registry):
        tool = SkillTool(registry)
        schema = tool.get_schema()
        assert schema["name"] == "skill"
        assert "action" in schema["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_list(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "list"})
        assert result.success
        assert "brainstorming" in result.output
        assert "tdd" not in result.output

    @pytest.mark.asyncio
    async def test_execute_load(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "load", "name": "brainstorming"})
        assert result.success
        assert "Help turn ideas into designs" in result.output

    @pytest.mark.asyncio
    async def test_execute_load_not_found(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "load", "name": "nonexistent"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_search(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "search", "query": "exploring"})
        assert result.success
        assert "brainstorming" in result.output

    @pytest.mark.asyncio
    async def test_execute_search_empty_query(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "search", "query": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "delete"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_install(self, registry):
        tool = SkillTool(registry)
        with patch.object(registry, "install_skill") as mock:
            mock.return_value = InstallResult(
                success=True, install_path="/tmp/new-skill"
            )
            result = await tool.execute({
                "action": "install",
                "url": "https://github.com/x/skills.git",
                "skill_name": "new-skill",
            })
        assert result.success
        assert "Installed" in result.output

    @pytest.mark.asyncio
    async def test_execute_install_missing_params(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "install"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_uninstall(self, registry):
        tool = SkillTool(registry)
        with patch.object(registry, "uninstall_skill") as mock:
            mock.return_value = InstallResult(success=True)
            result = await tool.execute({
                "action": "uninstall",
                "skill_name": "brainstorming",
            })
        assert result.success
        assert "Uninstalled" in result.output

    @pytest.mark.asyncio
    async def test_execute_uninstall_missing_name(self, registry):
        tool = SkillTool(registry)
        result = await tool.execute({"action": "uninstall"})
        assert result.success is False

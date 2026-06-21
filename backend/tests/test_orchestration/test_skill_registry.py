from pathlib import Path
from unittest.mock import MagicMock, patch

from app.orchestration.skill_registry import SkillMetadata, SkillRegistry, SkillSource


class TestSkillSource:
    def test_enum_values(self):
        assert SkillSource.PROJECT.value == "project"
        assert SkillSource.PROJECT_REFLEXION.value == "project_reflexion"
        assert SkillSource.GLOBAL.value == "global"
        assert SkillSource.PLUGIN.value == "plugin"
        assert SkillSource.COMPAT.value == "compat"
        assert SkillSource.CONFIG.value == "config"


class TestSkillMetadata:
    def test_default_values(self):
        meta = SkillMetadata(name="test", description="A test skill")
        assert meta.source_type == SkillSource.PROJECT
        assert meta.plugin_name == ""
        assert meta.version == ""

    def test_all_fields(self):
        meta = SkillMetadata(
            name="full",
            description="Full skill",
            category="development",
            required_skills=["code_edit", "debug"],
            file_path="/skills/full/SKILL.md",
            source_type=SkillSource.PLUGIN,
            plugin_name="superpowers",
            version="abc123",
            enabled=False,
            content_loaded=True,
        )
        assert meta.source_type == SkillSource.PLUGIN
        assert meta.plugin_name == "superpowers"
        assert meta.version == "abc123"


def _create_skill_dir(base: Path, name: str, frontmatter_lines: list[str], body: str = "Body content\n") -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    fm = "\n".join(frontmatter_lines)
    skill_file.write_text(f"---\n{fm}\n---\n{body}")
    return skill_file


class TestSkillRegistryScan:
    def test_scan_skills_dir(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "brainstorming", ["name: Brainstorm", "description: Ideation skill"])
        registry = SkillRegistry()
        count = registry.scan_directory(tmp_path, SkillSource.GLOBAL)
        assert count == 1
        skill = registry.get_skill("Brainstorm")
        assert skill is not None
        assert skill.source_type == SkillSource.GLOBAL

    def test_scan_with_plugin_name(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "tdd", ["name: TDD", "description: Test driven"])
        registry = SkillRegistry()
        registry.scan_directory(tmp_path, SkillSource.PLUGIN, plugin_name="superpowers")
        skill = registry.get_skill("TDD")
        assert skill.plugin_name == "superpowers"

    def test_scan_recursive(self, tmp_path: Path):
        nested = tmp_path / "skills" / "brainstorming"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text(
            "---\nname: brainstorming\ndescription: Deep think\n---\n\n# Brain\n"
        )
        nested2 = tmp_path / "skills" / "tdd"
        nested2.mkdir(parents=True)
        (nested2 / "SKILL.md").write_text(
            "---\nname: tdd\ndescription: Test first\n---\n\n# TDD\n"
        )
        registry = SkillRegistry()
        count = registry.scan_recursive(tmp_path, SkillSource.PLUGIN, "superpowers")
        assert count == 2
        assert registry.get_skill("brainstorming") is not None
        assert registry.get_skill("tdd") is not None
        assert registry.get_skill("brainstorming").plugin_name == "superpowers"

    def test_scan_recursive_skips_non_skill_dirs(self, tmp_path: Path):
        nested = tmp_path / "skills" / "brainstorming"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text(
            "---\nname: brainstorming\ndescription: Deep think\n---\n\n# Brain\n"
        )
        other = tmp_path / "docs"
        other.mkdir()
        (other / "README.md").write_text("Not a skill")
        registry = SkillRegistry()
        count = registry.scan_recursive(tmp_path)
        assert count == 1

    def test_scan_all_with_plugin_dirs(self, tmp_path: Path):
        project_skills = tmp_path / "skills"
        _create_skill_dir(
            project_skills, "local-skill",
            ["name: LocalSkill", "description: Local"],
        )
        plugin_dir = tmp_path / "plugin-skills"
        nested = plugin_dir / "deep" / "plugged"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text(
            "---\nname: plugged\ndescription: From plugin\n---\n\n# Plug\n"
        )
        global_dir = tmp_path / "global-skills"
        _create_skill_dir(global_dir, "global1", ["name: Global1", "description: Global skill"])

        mock_settings = MagicMock()
        mock_settings.skill.install_dir = str(global_dir)
        mock_settings.skill.compat_dirs = []
        mock_settings.skill.scan_dirs = []
        with patch(
            "app.config.settings.config_manager",
            MagicMock(settings=mock_settings),
        ):
            registry = SkillRegistry()
            count = registry.scan_all(
                plugin_skill_dirs=[("test-plugin", str(plugin_dir))],
                project_path=str(tmp_path),
            )
        assert count == 3

    def test_get_skill_content_lazy(self, tmp_path: Path):
        skill_file = _create_skill_dir(tmp_path, "lazy-skill", ["name: LazySkill", "description: Lazy\n"])
        registry = SkillRegistry()
        meta = SkillMetadata(
            name="LazySkill",
            description="Lazy",
            file_path=str(skill_file),
            content_loaded=False,
        )
        registry.register_skill(meta)
        assert registry.get_skill("LazySkill").content_loaded is False
        content = registry.get_skill_content("LazySkill")
        assert content is not None
        assert "Body content" in content
        assert registry.get_skill("LazySkill").content_loaded is True

    def test_scan_skips_invalid_dirs(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "valid-skill", ["name: Valid", "description: OK"])
        no_skill_dir = tmp_path / "no-skill-here"
        no_skill_dir.mkdir()
        (no_skill_dir / "README.md").write_text("Not a skill")
        registry = SkillRegistry()
        count = registry.scan_directory(tmp_path)
        assert count == 1

    def test_skill_metadata_source_type(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "categorized", ["name: Cat", "description: Has metadata", "category: planning"])
        registry = SkillRegistry()
        registry.scan_directory(tmp_path, SkillSource.COMPAT)
        skill = registry.get_skill("Cat")
        assert skill.source_type == SkillSource.COMPAT


class TestSkillRegistryBasicOps:
    def test_register_and_unregister(self):
        registry = SkillRegistry()
        meta = SkillMetadata(name="temp", description="Temporary")
        registry.register_skill(meta)
        assert registry.get_skill("temp") is not None
        registry.unregister_skill("temp")
        assert registry.get_skill("temp") is None

    def test_unregister_clears_content_cache(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "cache-skill", ["name: CacheSkill", "description: Cached"])
        registry = SkillRegistry()
        registry.scan_directory(tmp_path)
        assert registry.get_skill_content("CacheSkill") is not None
        registry.unregister_skill("CacheSkill")
        assert registry.get_skill_content("CacheSkill") is None

    def test_enable_disable(self):
        registry = SkillRegistry()
        meta = SkillMetadata(name="toggle", description="Toggle me")
        registry.register_skill(meta)
        assert registry.get_skill("toggle").enabled is True
        registry.disable_skill("toggle")
        assert registry.get_skill("toggle").enabled is False
        registry.enable_skill("toggle")
        assert registry.get_skill("toggle").enabled is True

    def test_list_enabled_skills(self):
        registry = SkillRegistry()
        registry.register_skill(SkillMetadata(name="a", description="A"))
        registry.register_skill(SkillMetadata(name="b", description="B", enabled=False))
        enabled = registry.list_enabled_skills()
        assert len(enabled) == 1
        assert enabled[0].name == "a"

    def test_list_skills_by_category(self):
        registry = SkillRegistry()
        registry.register_skill(SkillMetadata(name="x", description="X", category="dev"))
        registry.register_skill(SkillMetadata(name="y", description="Y", category="planning"))
        registry.register_skill(SkillMetadata(name="z", description="Z", category="dev"))
        dev_skills = registry.list_skills_by_category("dev")
        assert len(dev_skills) == 2

    def test_scan_nonexistent_directory(self):
        registry = SkillRegistry()
        count = registry.scan_directory("/nonexistent/path")
        assert count == 0
        count = registry.scan_recursive("/nonexistent/path")
        assert count == 0

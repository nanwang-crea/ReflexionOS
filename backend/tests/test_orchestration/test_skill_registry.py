from pathlib import Path

from app.orchestration.skill_registry import SkillMetadata, SkillRegistry


class TestSkillMetadata:
    def test_default_values(self):
        meta = SkillMetadata(name="test", description="A test skill")

        assert meta.name == "test"
        assert meta.description == "A test skill"
        assert meta.category == ""
        assert meta.required_skills == []
        assert meta.file_path == ""
        assert meta.source == ""
        assert meta.install_path == ""
        assert meta.enabled is True
        assert meta.content_loaded is False

    def test_all_fields(self):
        meta = SkillMetadata(
            name="full",
            description="Full skill",
            category="development",
            required_skills=["code_edit", "debug"],
            file_path="/skills/full/SKILL.md",
            enabled=False,
            content_loaded=True,
        )

        assert meta.category == "development"
        assert meta.required_skills == ["code_edit", "debug"]
        assert meta.file_path == "/skills/full/SKILL.md"
        assert meta.enabled is False
        assert meta.content_loaded is True


def _create_skill_dir(base: Path, name: str, frontmatter_lines: list[str], body: str = "Body content\n") -> Path:
    skill_dir = base / name
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    fm = "\n".join(frontmatter_lines)
    skill_file.write_text(f"---\n{fm}\n---\n{body}")
    return skill_file


class TestSkillRegistryFileSystemScan:
    def test_scan_skills_dir(self, tmp_path: Path):
        _create_skill_dir(tmp_path, "brainstorming", ["name: Brainstorm", "description: Ideation skill"])

        registry = SkillRegistry()
        count = registry.scan_directory(tmp_path)

        assert count == 1
        skill = registry.get_skill("Brainstorm")
        assert skill is not None
        assert skill.description == "Ideation skill"
        assert skill.content_loaded is True
        assert registry.get_skill_content("Brainstorm") == "Body content\n"

    def test_scan_multiple_dirs(self, tmp_path: Path):
        dir_a = tmp_path / "group_a"
        dir_a.mkdir()
        dir_b = tmp_path / "group_b"
        dir_b.mkdir()
        _create_skill_dir(dir_a, "skill-a", ["name: SkillA", "description: From A"])
        _create_skill_dir(dir_b, "skill-b", ["name: SkillB", "description: From B"])

        registry = SkillRegistry()
        total = registry.scan_directory(dir_a) + registry.scan_directory(dir_b)

        assert total == 2
        assert registry.get_skill("SkillA") is not None
        assert registry.get_skill("SkillB") is not None

    def test_get_skill_content_lazy(self, tmp_path: Path):
        skill_file = _create_skill_dir(tmp_path, "lazy-skill", "name: LazySkill\n description: Lazy\n")

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
        assert registry.get_skill("Valid") is not None

    def test_skill_metadata_fields(self, tmp_path: Path):
        _create_skill_dir(
            tmp_path,
            "categorized",
            ["name: Categorized", "description: Has metadata", "category: planning", "required_skills:", "  - brainstorm"],
        )

        registry = SkillRegistry()
        registry.scan_directory(tmp_path)

        skill = registry.get_skill("Categorized")
        assert skill is not None
        assert skill.category == "planning"
        assert skill.required_skills == ["brainstorm"]
        assert skill.file_path != ""
        assert skill.enabled is True


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
        assert all(s.category == "dev" for s in dev_skills)

    def test_scan_sets_source_and_install_path(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test\nsource: https://github.com/x\n---\n\n# Test\n",
        )

        registry = SkillRegistry()
        registry.scan_directory(tmp_path)

        skill = registry.get_skill("my-skill")
        assert skill is not None
        assert skill.source == "https://github.com/x"
        assert skill.install_path == str(skill_dir)

    def test_scan_nonexistent_directory(self):
        registry = SkillRegistry()
        count = registry.scan_directory("/nonexistent/path")
        assert count == 0

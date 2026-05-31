from pathlib import Path

import pytest

from app.orchestration.skill_parser import ParsedSkill, SkillFrontmatter, parse_skill_md


class TestSkillFrontmatter:
    def test_default_fields(self):
        fm = SkillFrontmatter(name="test", description="desc", category="general", required_skills=[])
        assert fm.name == "test"
        assert fm.description == "desc"
        assert fm.category == "general"
        assert fm.required_skills == []


class TestParseSkillMd:
    def test_basic_skill_with_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: Code Review\n"
            "description: Reviews code for quality\n"
            "---\n"
            "# Code Review Skill\n"
            "\n"
            "This skill reviews code.\n"
        )

        result = parse_skill_md(skill_file)

        assert isinstance(result, ParsedSkill)
        assert result.frontmatter.name == "Code Review"
        assert result.frontmatter.description == "Reviews code for quality"
        assert result.body == "# Code Review Skill\n\nThis skill reviews code.\n"
        assert result.file_path == str(skill_file)

    def test_skill_without_frontmatter_uses_parent_dir_name(self, tmp_path: Path):
        skill_dir = tmp_path / "my-awesome-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# My Skill\n\nNo frontmatter here.\n")

        result = parse_skill_md(skill_file)

        assert result.frontmatter.name == "my-awesome-skill"
        assert result.frontmatter.description == ""

    def test_skill_with_category_field(self, tmp_path: Path):
        skill_dir = tmp_path / "categorized-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: Debug\n"
            "description: Debugging skill\n"
            "category: development\n"
            "---\n"
            "Debug content\n"
        )

        result = parse_skill_md(skill_file)

        assert result.frontmatter.category == "development"

    def test_skill_with_required_skills_list(self, tmp_path: Path):
        skill_dir = tmp_path / "composite-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: Full Stack\n"
            "description: Full stack dev\n"
            "required_skills:\n"
            "  - code_edit\n"
            "  - debug\n"
            "  - refactor\n"
            "---\n"
            "Full stack content\n"
        )

        result = parse_skill_md(skill_file)

        assert result.frontmatter.required_skills == ["code_edit", "debug", "refactor"]

    def test_nonexistent_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_skill_md("/nonexistent/path/SKILL.md")

    def test_empty_frontmatter_uses_parent_dir_name(self, tmp_path: Path):
        skill_dir = tmp_path / "empty-fm-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\n---\nSome body content\n")

        result = parse_skill_md(skill_file)

        assert result.frontmatter.name == "empty-fm-skill"
        assert result.frontmatter.description == ""
        assert result.body == "Some body content\n"

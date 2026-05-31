import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.orchestration.skill_installer import SkillInstaller, InstallResult


class TestInstallResult:
    def test_success(self):
        r = InstallResult(success=True, install_path="/some/path")
        assert r.success
        assert r.install_path == "/some/path"

    def test_failure(self):
        r = InstallResult(success=False, error="fail")
        assert r.success is False
        assert r.error == "fail"


class TestSkillInstaller:
    def test_install_from_git_url(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)

        with patch("app.orchestration.skill_installer.Repo") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.clone_from.return_value = mock_repo

            def fake_clone(url, dest, **kwargs):
                clone_dir = Path(dest)
                clone_dir.mkdir(parents=True, exist_ok=True)
                skill_dir = clone_dir / "brainstorming"
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    '---\nname: brainstorming\ndescription: test\n---\n\n# Test\n',
                    encoding="utf-8",
                )
                return mock_repo

            mock_repo_cls.clone_from.side_effect = fake_clone

            result = installer.install(
                url="https://github.com/example/skills.git",
                skill_name="brainstorming",
            )

        assert result.success
        assert (tmp_path / "brainstorming" / "SKILL.md").exists()

    def test_install_skill_already_exists(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)
        skill_dir = tmp_path / "brainstorming"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: brainstorming\ndescription: test\n---\n\n# Test\n',
            encoding="utf-8",
        )

        result = installer.install(
            url="https://github.com/example/skills.git",
            skill_name="brainstorming",
        )

        assert result.success is False
        assert "already exists" in result.error

    def test_uninstall_skill(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: my-skill\ndescription: test\n---\n\n# Test\n',
            encoding="utf-8",
        )

        result = installer.uninstall("my-skill")

        assert result.success
        assert not skill_dir.exists()

    def test_uninstall_nonexistent_skill(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)

        result = installer.uninstall("nonexistent")

        assert result.success is False
        assert "not found" in result.error

    def test_install_with_subdir(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)

        with patch("app.orchestration.skill_installer.Repo") as mock_repo_cls:
            mock_repo = MagicMock()

            def fake_clone(url, dest, **kwargs):
                clone_dir = Path(dest)
                clone_dir.mkdir(parents=True, exist_ok=True)
                skill_subdir = clone_dir / "skills" / "tdd"
                skill_subdir.mkdir(parents=True)
                (skill_subdir / "SKILL.md").write_text(
                    '---\nname: tdd\ndescription: test\n---\n\n# TDD\n',
                    encoding="utf-8",
                )
                return mock_repo

            mock_repo_cls.clone_from.side_effect = fake_clone

            result = installer.install(
                url="https://github.com/example/skills.git",
                skill_name="tdd",
                subdir="skills/tdd",
            )

        assert result.success
        assert (tmp_path / "tdd" / "SKILL.md").exists()

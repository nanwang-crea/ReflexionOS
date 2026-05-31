import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.orchestration.skill_registry import SkillMetadata, skill_registry
from app.orchestration.skill_installer import InstallResult


@pytest.fixture(autouse=True)
def _reset_registry():
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()
    skill_registry._installer = None
    yield
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()
    skill_registry._installer = None


client = TestClient(app)


class TestSkillsInstallAPI:
    def test_install_skill(self):
        with patch.object(skill_registry, "install_skill") as mock_install:
            mock_install.return_value = InstallResult(
                success=True, install_path="/tmp/skills/brainstorming"
            )
            skill_registry.register_skill(
                SkillMetadata(
                    name="brainstorming",
                    description="test",
                    install_path="/tmp/skills/brainstorming",
                )
            )
            resp = client.post("/api/skills/install", json={
                "url": "https://github.com/example/skills.git",
                "skill_name": "brainstorming",
            })
        assert resp.status_code == 200
        assert resp.json()["installed"] is True

    def test_install_skill_fails(self):
        with patch.object(skill_registry, "install_skill") as mock_install:
            mock_install.return_value = InstallResult(
                success=False, error="already exists"
            )
            resp = client.post("/api/skills/install", json={
                "url": "https://github.com/example/skills.git",
                "skill_name": "brainstorming",
            })
        assert resp.status_code == 400

    def test_uninstall_skill(self):
        skill_registry.register_skill(
            SkillMetadata(name="test-skill", description="test", install_path="/tmp/skills/test-skill")
        )
        with patch.object(skill_registry, "uninstall_skill") as mock_uninstall:
            mock_uninstall.return_value = InstallResult(success=True)
            resp = client.delete("/api/skills/test-skill")
        assert resp.status_code == 200
        assert resp.json()["uninstalled"] is True

    def test_uninstall_nonexistent(self):
        with patch.object(skill_registry, "uninstall_skill") as mock_uninstall:
            mock_uninstall.return_value = InstallResult(success=False, error="not found")
            resp = client.delete("/api/skills/nonexistent")
        assert resp.status_code == 400

    def test_refresh_skills(self):
        with patch.object(skill_registry, "refresh", return_value=5):
            resp = client.post("/api/skills/refresh")
        assert resp.status_code == 200
        assert resp.json()["total_skills"] == 5

    def test_list_skills_includes_source_and_install_path(self):
        skill_registry.register_skill(
            SkillMetadata(
                name="test-skill",
                description="test",
                source="https://github.com/x/skills",
                install_path="/tmp/skills/test-skill",
            )
        )
        resp = client.get("/api/skills/")
        data = resp.json()
        assert data[0]["source"] == "https://github.com/x/skills"
        assert data[0]["install_path"] == "/tmp/skills/test-skill"

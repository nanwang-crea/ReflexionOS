import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.skill_registry import SkillMetadata, skill_registry


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


class TestSkillsAPI:
    def test_list_skills_empty(self):
        resp = client.get("/api/skills/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_skills_with_data(self):
        skill_registry.register_skill(
            SkillMetadata(name="test-skill", description="A test skill", category="technique")
        )
        resp = client.get("/api/skills/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-skill"
        assert "content" not in data[0]

    def test_get_skill_detail(self):
        skill_registry.register_skill(
            SkillMetadata(name="detail-skill", description="Detail", file_path="/fake/SKILL.md")
        )
        skill_registry._content_cache["detail-skill"] = "# Detail Skill\n\nFull content here."
        resp = client.get("/api/skills/detail-skill")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "detail-skill"
        assert "Full content here" in data["content"]

    def test_get_skill_detail_not_found(self):
        resp = client.get("/api/skills/nonexistent")
        assert resp.status_code == 404

    def test_enable_skill(self):
        skill_registry.register_skill(
            SkillMetadata(name="toggle-skill", description="Toggle", enabled=False)
        )
        resp = client.post("/api/skills/toggle-skill/enable")
        assert resp.status_code == 200
        assert skill_registry.get_skill("toggle-skill").enabled is True

    def test_disable_skill(self):
        skill_registry.register_skill(
            SkillMetadata(name="toggle-skill", description="Toggle", enabled=True)
        )
        resp = client.post("/api/skills/toggle-skill/disable")
        assert resp.status_code == 200
        assert skill_registry.get_skill("toggle-skill").enabled is False

    def test_categories_endpoint(self):
        skill_registry.register_skill(SkillMetadata(name="a", description="A", category="discipline"))
        skill_registry.register_skill(SkillMetadata(name="b", description="B", category="technique"))
        skill_registry.register_skill(SkillMetadata(name="c", description="C", category="discipline"))
        resp = client.get("/api/skills/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert "discipline" in data
        assert "technique" in data
        assert len(data["discipline"]) == 2

    def test_enable_nonexistent_skill(self):
        resp = client.post("/api/skills/nonexistent/enable")
        assert resp.status_code == 404

    def test_disable_nonexistent_skill(self):
        resp = client.post("/api/skills/nonexistent/disable")
        assert resp.status_code == 404

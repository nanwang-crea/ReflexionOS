from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.package_resolver import PackageSpecifier, ResolvedPackage
from app.orchestration.plugin_loader import PluginRegistration
from app.orchestration.skill_registry import SkillMetadata, SkillSource, skill_registry


@pytest.fixture(autouse=True)
def _reset():
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()
    yield
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()


client = TestClient(app)


class TestPluginsAPI:
    def test_list_plugins_empty(self):
        with patch("app.api.routes.plugins._get_resolver_and_loader") as mock:
            resolver = MagicMock()
            loader = MagicMock()
            resolver.list_installed.return_value = []
            loader.list_registrations.return_value = []
            mock.return_value = (resolver, loader)
            resp = client.get("/api/plugins/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_plugins_with_data(self):
        with patch("app.api.routes.plugins._get_resolver_and_loader") as mock:
            resolver = MagicMock()
            loader = MagicMock()
            reg = PluginRegistration(plugin_name="superpowers", tools=[], skill_dirs=["/tmp/skills"])
            loader.list_registrations.return_value = [reg]
            pkg = ResolvedPackage(
                specifier=PackageSpecifier(raw="superpowers@git+https://x.git", name="superpowers", spec_type="git", url="https://x.git", ref="main"),
                install_path="/tmp/packages/superpowers",
                resolved_ref="abc",
                has_plugin_entry=False,
                skill_dirs=["/tmp/skills"],
            )
            resolver.list_installed.return_value = [pkg]
            mock.return_value = (resolver, loader)
            resp = client.get("/api/plugins/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "superpowers"

    def test_install_plugin(self):
        with patch("app.api.routes.plugins._get_resolver_and_loader") as mock_rl, \
             patch("app.api.routes.plugins.PackageSpecifier") as mock_spec:
            resolver = MagicMock()
            loader = MagicMock()
            mock_rl.return_value = (resolver, loader)

            spec = PackageSpecifier(raw="test@git+https://x.git", name="test", spec_type="git", url="https://x.git", ref="main")
            mock_spec.parse.return_value = spec

            pkg = ResolvedPackage(
                specifier=spec,
                install_path="/tmp/test",
                resolved_ref="abc",
                has_plugin_entry=False,
                skill_dirs=[],
            )
            resolver.resolve.return_value = pkg
            reg = PluginRegistration(plugin_name="test", tools=[], skill_dirs=[])
            loader.load_plugin.return_value = reg

            resp = client.post("/api/plugins/install", json={"specifier": "test@git+https://x.git"})
        assert resp.status_code == 200
        assert resp.json()["installed"] is True

    def test_install_invalid_specifier(self):
        with patch("app.api.routes.plugins.PackageSpecifier") as mock_spec:
            mock_spec.parse.side_effect = ValueError("bad spec")
            resp = client.post("/api/plugins/install", json={"specifier": "invalid"})
        assert resp.status_code == 400

    def test_uninstall_plugin_not_found(self):
        with patch("app.api.routes.plugins._get_resolver_and_loader") as mock:
            resolver = MagicMock()
            loader = MagicMock()
            resolver.remove.return_value = False
            loader.get_registration.return_value = None
            mock.return_value = (resolver, loader)
            resp = client.delete("/api/plugins/nonexistent")
        assert resp.status_code == 404

    def test_plugin_skills(self):
        skill_registry.register_skill(
            SkillMetadata(name="brain", description="brain skill", plugin_name="sp", source_type=SkillSource.PLUGIN)
        )
        skill_registry.register_skill(
            SkillMetadata(name="other", description="other skill", plugin_name="", source_type=SkillSource.PROJECT)
        )
        with patch("app.api.routes.plugins._get_resolver_and_loader") as mock:
            resolver = MagicMock()
            loader = MagicMock()
            loader.get_registration.return_value = PluginRegistration(plugin_name="sp", tools=[], skill_dirs=[])
            mock.return_value = (resolver, loader)
            resp = client.get("/api/plugins/sp/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "brain"

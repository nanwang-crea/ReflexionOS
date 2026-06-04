import pytest
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.effect_category import EffectCategory


@pytest.fixture
def registry():
    return CommandEffectRegistry()


class TestOftenNeedsNetwork:
    @pytest.mark.parametrize("command", [
        "pip", "pip3", "npm", "cargo", "go", "dotnet", "docker", "git",
    ])
    def test_base_commands_have_often_needs_network(self, registry, command):
        entry = registry.lookup(command)
        assert entry is not None, f"{command} not registered"
        assert entry.often_needs_network is True, f"{command} should have often_needs_network=True"

    def test_pre_commit_has_often_needs_network(self, registry):
        entry = registry.lookup("pre-commit")
        assert entry is not None
        assert entry.often_needs_network is True

    def test_ls_not_often_needs_network(self, registry):
        entry = registry.lookup("ls")
        assert entry is not None
        assert entry.often_needs_network is False

    def test_cat_not_often_needs_network(self, registry):
        entry = registry.lookup("cat")
        assert entry is not None
        assert entry.often_needs_network is False

    def test_mkdir_not_often_needs_network(self, registry):
        entry = registry.lookup("mkdir")
        assert entry is not None
        assert entry.often_needs_network is False

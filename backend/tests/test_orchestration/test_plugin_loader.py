from unittest.mock import MagicMock

from app.orchestration.package_resolver import PackageSpecifier, ResolvedPackage
from app.orchestration.plugin_loader import PluginLoader


def _make_resolved_package(name: str, install_path: str) -> ResolvedPackage:
    return ResolvedPackage(
        specifier=PackageSpecifier(
            raw=f"{name}@git+https://example.com/{name}.git",
            name=name,
            spec_type="git",
            url=f"https://example.com/{name}.git",
            ref="main",
        ),
        install_path=install_path,
        resolved_ref="abc123",
        has_plugin_entry=False,
        skill_dirs=[],
    )


class TestPluginLoaderAutoDiscover:
    def test_auto_discover_nested_skills(self, tmp_path):
        pkg_dir = tmp_path / "superpowers"
        skill_a = pkg_dir / "skills" / "brainstorming"
        skill_a.mkdir(parents=True)
        (skill_a / "SKILL.md").write_text("---\nname: brainstorming\ndescription: test\n---\n\n# Brain\n")
        skill_b = pkg_dir / "skills" / "tdd"
        skill_b.mkdir(parents=True)
        (skill_b / "SKILL.md").write_text("---\nname: tdd\ndescription: test\n---\n\n# TDD\n")

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("superpowers", str(pkg_dir))
        reg = loader.load_plugin(pkg)

        assert reg is not None
        assert reg.plugin_name == "superpowers"
        assert len(reg.skill_dirs) >= 1
        assert reg.tools == []

    def test_auto_discover_no_skills(self, tmp_path):
        pkg_dir = tmp_path / "empty-plugin"
        pkg_dir.mkdir()

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("empty-plugin", str(pkg_dir))
        reg = loader.load_plugin(pkg)

        assert reg is not None
        assert reg.skill_dirs == []

    def test_load_plugin_with_entry_point(self, tmp_path):
        pkg_dir = tmp_path / "my-plugin"
        pkg_dir.mkdir()

        entry_py = pkg_dir / "reflexion_plugin.py"
        entry_py.write_text(
            "def register():\n"
            "    return {\n"
            '        "tools": [{"name": "custom_tool"}],\n'
            '        "hooks": {},\n'
            '        "skill_dirs": [],\n'
            '        "config_schema": None,\n'
            "    }\n"
        )

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("my-plugin", str(pkg_dir))
        pkg.has_plugin_entry = True
        reg = loader.load_plugin(pkg)

        assert reg is not None
        assert reg.plugin_name == "my-plugin"
        assert len(reg.tools) == 1
        assert reg.tools[0]["name"] == "custom_tool"

    def test_load_plugin_entry_no_register(self, tmp_path):
        pkg_dir = tmp_path / "bad-plugin"
        pkg_dir.mkdir()

        entry_py = pkg_dir / "reflexion_plugin.py"
        entry_py.write_text("# no register function\npass\n")

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("bad-plugin", str(pkg_dir))
        reg = loader.load_plugin(pkg)

        assert reg is not None
        assert reg.plugin_name == "bad-plugin"

    def test_load_plugin_entry_bad_return(self, tmp_path):
        pkg_dir = tmp_path / "bad-ret"
        pkg_dir.mkdir()

        entry_py = pkg_dir / "reflexion_plugin.py"
        entry_py.write_text("def register():\n    return 'not a dict'\n")

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("bad-ret", str(pkg_dir))
        reg = loader.load_plugin(pkg)

        assert reg is not None

    def test_load_plugin_entry_exception(self, tmp_path):
        pkg_dir = tmp_path / "crash-plugin"
        pkg_dir.mkdir()

        entry_py = pkg_dir / "reflexion_plugin.py"
        entry_py.write_text("def register():\n    raise RuntimeError('boom')\n")

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("crash-plugin", str(pkg_dir))
        reg = loader.load_plugin(pkg)

        assert reg is not None

    def test_load_all(self, tmp_path):
        pkg_a = tmp_path / "plugin-a"
        pkg_a.mkdir()
        (pkg_a / "skills" / "sa").mkdir(parents=True)
        (pkg_a / "skills" / "sa" / "SKILL.md").write_text("---\nname: sa\ndescription: a\n---\n\n# A\n")

        pkg_b = tmp_path / "plugin-b"
        pkg_b.mkdir()
        (pkg_b / "skills" / "sb").mkdir(parents=True)
        (pkg_b / "skills" / "sb" / "SKILL.md").write_text("---\nname: sb\ndescription: b\n---\n\n# B\n")

        resolver = MagicMock()
        loader = PluginLoader(resolver)

        packages = [
            _make_resolved_package("plugin-a", str(pkg_a)),
            _make_resolved_package("plugin-b", str(pkg_b)),
        ]
        regs = loader.load_all(packages)

        assert len(regs) == 2

    def test_get_all_skill_dirs(self, tmp_path):
        pkg_dir = tmp_path / "sp"
        skill_dir = pkg_dir / "skills" / "brain"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: brain\ndescription: test\n---\n\n# B\n")

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("sp", str(pkg_dir))
        loader.load_plugin(pkg)

        all_dirs = loader.get_all_skill_dirs()
        assert len(all_dirs) >= 1

    def test_hooks_registered(self, tmp_path):
        pkg_dir = tmp_path / "hook-plugin"
        pkg_dir.mkdir()

        entry_py = pkg_dir / "reflexion_plugin.py"
        entry_py.write_text(
            "def before_turn(**kwargs): return True\n"
            "def register():\n"
            "    return {\n"
            '        "tools": [],\n'
            '        "hooks": {"before_turn": before_turn},\n'
            '        "skill_dirs": [],\n'
            "    }\n"
        )

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("hook-plugin", str(pkg_dir))
        loader.load_plugin(pkg)

        hooks = loader.get_hook("before_turn")
        assert len(hooks) == 1
        assert hooks[0]() is True

    def test_get_registration(self, tmp_path):
        pkg_dir = tmp_path / "reg-plugin"
        pkg_dir.mkdir()

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        pkg = _make_resolved_package("reg-plugin", str(pkg_dir))
        loader.load_plugin(pkg)

        reg = loader.get_registration("reg-plugin")
        assert reg is not None
        assert reg.plugin_name == "reg-plugin"

        assert loader.get_registration("nonexistent") is None

    def test_list_registrations(self, tmp_path):
        pkg_a = tmp_path / "a"
        pkg_a.mkdir()
        pkg_b = tmp_path / "b"
        pkg_b.mkdir()

        resolver = MagicMock()
        loader = PluginLoader(resolver)
        loader.load_plugin(_make_resolved_package("a", str(pkg_a)))
        loader.load_plugin(_make_resolved_package("b", str(pkg_b)))

        regs = loader.list_registrations()
        assert len(regs) == 2

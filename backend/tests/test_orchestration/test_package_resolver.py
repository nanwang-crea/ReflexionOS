from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.orchestration.package_resolver import (
    PackageResolver,
    PackageSpecifier,
)


class TestPackageSpecifierParse:
    def test_parse_git_specifier(self):
        spec = PackageSpecifier.parse(
            "superpowers@git+https://github.com/obra/superpowers.git"
        )
        assert spec.name == "superpowers"
        assert spec.spec_type == "git"
        assert spec.url == "https://github.com/obra/superpowers.git"
        assert spec.ref == "main"

    def test_parse_git_specifier_with_version(self):
        spec = PackageSpecifier.parse(
            "superpowers@git+https://github.com/obra/superpowers.git#v5.0.3"
        )
        assert spec.name == "superpowers"
        assert spec.spec_type == "git"
        assert spec.url == "https://github.com/obra/superpowers.git"
        assert spec.ref == "v5.0.3"

    def test_parse_local_specifier(self):
        spec = PackageSpecifier.parse("my-plugin@file:///local/path")
        assert spec.name == "my-plugin"
        assert spec.spec_type == "local"
        assert spec.url == "/local/path"

    def test_parse_pypi_specifier(self):
        spec = PackageSpecifier.parse("my-plugin")
        assert spec.name == "my-plugin"
        assert spec.spec_type == "pypi"
        assert spec.url == "my-plugin"
        assert spec.ref == "latest"

    @pytest.mark.parametrize(
        "raw",
        [
            "@git+https://example.com/repo.git",
            "name@",
            "name@git+",
            "name@git+not-a-url",
            "",
            "name@unknown+something",
        ],
    )
    def test_parse_invalid(self, raw):
        with pytest.raises(ValueError, match="Invalid package specifier"):
            PackageSpecifier.parse(raw)


class TestPackageResolverResolve:
    def test_resolve_git(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)
        spec = PackageSpecifier(
            raw="superpowers@git+https://github.com/obra/superpowers.git",
            name="superpowers",
            spec_type="git",
            url="https://github.com/obra/superpowers.git",
            ref="main",
        )

        mock_commit = MagicMock()
        mock_commit.__str__ = lambda self: "abc123def456"

        mock_repo = MagicMock()
        mock_repo.head.commit = mock_commit

        with patch("app.orchestration.package_resolver.Repo") as mock_repo_cls:
            def fake_clone(url, dest, **kwargs):
                Path(dest).mkdir(parents=True, exist_ok=True)
                return mock_repo

            mock_repo_cls.clone_from.side_effect = fake_clone
            mock_repo_cls.return_value = mock_repo

            result = resolver.resolve(spec)

        assert result.install_path == str(cache_dir / "superpowers")
        assert result.resolved_ref == "abc123def456"
        assert (cache_dir / "superpowers" / ".ref").read_text() == "main"
        assert (cache_dir / "superpowers" / ".commit").read_text() == "abc123def456"
        mock_repo_cls.clone_from.assert_called_once_with(
            "https://github.com/obra/superpowers.git",
            str(cache_dir / "superpowers"),
            branch="main",
            depth=1,
        )

    def test_resolve_git_cached(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)
        spec = PackageSpecifier(
            raw="superpowers@git+https://github.com/obra/superpowers.git",
            name="superpowers",
            spec_type="git",
            url="https://github.com/obra/superpowers.git",
            ref="main",
        )

        target_dir = cache_dir / "superpowers"
        target_dir.mkdir()
        (target_dir / ".ref").write_text("main")
        (target_dir / ".commit").write_text("existinghash")

        with patch("app.orchestration.package_resolver.Repo") as mock_repo_cls:
            result = resolver.resolve(spec)

        mock_repo_cls.clone_from.assert_not_called()
        assert result.resolved_ref == "existinghash"

    def test_resolve_git_ref_changed(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)
        spec = PackageSpecifier(
            raw="superpowers@git+https://github.com/obra/superpowers.git#v2.0",
            name="superpowers",
            spec_type="git",
            url="https://github.com/obra/superpowers.git",
            ref="v2.0",
        )

        target_dir = cache_dir / "superpowers"
        target_dir.mkdir()
        (target_dir / ".ref").write_text("main")
        (target_dir / ".commit").write_text("oldhash")

        mock_commit = MagicMock()
        mock_commit.__str__ = lambda self: "newhash123"

        mock_repo = MagicMock()
        mock_repo.head.commit = mock_commit

        with patch("app.orchestration.package_resolver.Repo") as mock_repo_cls:
            def fake_clone(url, dest, **kwargs):
                Path(dest).mkdir(parents=True, exist_ok=True)
                return mock_repo

            mock_repo_cls.clone_from.side_effect = fake_clone
            mock_repo_cls.return_value = mock_repo

            result = resolver.resolve(spec)

        mock_repo_cls.clone_from.assert_called_once()
        assert result.resolved_ref == "newhash123"
        assert (target_dir / ".ref").read_text() == "v2.0"

    def test_resolve_local(self, tmp_path):
        cache_dir = tmp_path / "packages"
        local_src = tmp_path / "local_src"
        local_src.mkdir()
        (local_src / "SKILL.md").write_text("# skill\n")

        resolver = PackageResolver(cache_dir=cache_dir)
        spec = PackageSpecifier(
            raw="my-plugin@file:///local/path",
            name="my-plugin",
            spec_type="local",
            url=str(local_src),
            ref="main",
        )

        result = resolver.resolve(spec)

        link = cache_dir / "my-plugin"
        assert link.is_symlink()
        assert result.install_path == str(link)

    def test_resolve_pypi_raises(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)
        spec = PackageSpecifier(
            raw="my-plugin",
            name="my-plugin",
            spec_type="pypi",
            url="my-plugin",
            ref="latest",
        )

        with pytest.raises(ValueError, match="PyPI packages not yet supported"):
            resolver.resolve(spec)


class TestPackageResolverRemove:
    def test_remove(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)
        target_dir = cache_dir / "my-plugin"
        target_dir.mkdir()
        (target_dir / "some_file.txt").write_text("data")

        assert resolver.remove("my-plugin") is True
        assert not target_dir.exists()

    def test_remove_nonexistent(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)

        assert resolver.remove("nonexistent") is False


class TestPackageResolverDiscoverSkillDirs:
    def test_discover_skill_dirs(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)

        root = tmp_path / "pkg"
        root.mkdir()
        (root / "skills" / "brainstorming").mkdir(parents=True)
        (root / "skills" / "brainstorming" / "SKILL.md").write_text("# brain")
        (root / "skills" / "tdd").mkdir(parents=True)
        (root / "skills" / "tdd" / "SKILL.md").write_text("# tdd")
        (root / "other").mkdir()
        (root / "other" / "no_skill.txt").write_text("nope")

        dirs = resolver._discover_skill_dirs(root)

        assert len(dirs) == 2
        assert str(root / "skills" / "brainstorming") in dirs
        assert str(root / "skills" / "tdd") in dirs


class TestPackageResolverListInstalled:
    def test_list_installed(self, tmp_path):
        cache_dir = tmp_path / "packages"
        cache_dir.mkdir()

        pkg1 = cache_dir / "pkg1"
        pkg1.mkdir()
        (pkg1 / ".ref").write_text("main")
        (pkg1 / ".commit").write_text("hash1")
        (pkg1 / "reflexion_plugin.py").write_text("plugin")

        pkg2 = cache_dir / "pkg2"
        local_src = tmp_path / "local_pkg"
        local_src.mkdir()
        pkg2.symlink_to(str(local_src))

        resolver = PackageResolver(cache_dir=cache_dir)
        installed = resolver.list_installed()

        assert len(installed) == 2
        names = [rp.specifier.name for rp in installed]
        assert "pkg1" in names
        assert "pkg2" in names

        pkg1_resolved = next(rp for rp in installed if rp.specifier.name == "pkg1")
        assert pkg1_resolved.has_plugin_entry is True
        assert pkg1_resolved.resolved_ref == "hash1"
        assert pkg1_resolved.specifier.spec_type == "git"

        pkg2_resolved = next(rp for rp in installed if rp.specifier.name == "pkg2")
        assert pkg2_resolved.specifier.spec_type == "local"


class TestPackageResolverUpdate:
    def test_update(self, tmp_path):
        cache_dir = tmp_path / "packages"
        resolver = PackageResolver(cache_dir=cache_dir)

        target_dir = cache_dir / "superpowers"
        target_dir.mkdir()
        (target_dir / ".ref").write_text("main")
        (target_dir / ".commit").write_text("oldhash")

        spec = PackageSpecifier(
            raw="superpowers@git+https://github.com/obra/superpowers.git",
            name="superpowers",
            spec_type="git",
            url="https://github.com/obra/superpowers.git",
            ref="main",
        )

        mock_commit = MagicMock()
        mock_commit.__str__ = lambda self: "updatedhash"

        mock_repo = MagicMock()
        mock_repo.head.commit = mock_commit

        with patch("app.orchestration.package_resolver.Repo") as mock_repo_cls:
            def fake_clone(url, dest, **kwargs):
                Path(dest).mkdir(parents=True, exist_ok=True)
                return mock_repo

            mock_repo_cls.clone_from.side_effect = fake_clone
            mock_repo_cls.return_value = mock_repo

            result = resolver.update(spec)

        mock_repo_cls.clone_from.assert_called_once()
        assert result.resolved_ref == "updatedhash"

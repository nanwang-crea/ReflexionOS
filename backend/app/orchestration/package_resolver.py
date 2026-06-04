import logging
import re
import shutil
from pathlib import Path
from typing import Literal

from git import Repo
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_GITHUB_SHORT_RE = re.compile(
    r"^(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo>[a-zA-Z0-9_.-]+?)(?:@(?P<ref>.+))?$"
)
_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo>[a-zA-Z0-9_.-]+?)(?:\.git)?(?:#(?P<ref>.+))?(?:/)?$"
)
_GIT_SPEC_RE = re.compile(
    r"^(?P<name>[^@]+)@git\+(?P<url>https?://.+?)(?:#(?P<ref>.+))?$"
)
_LOCAL_SPEC_RE = re.compile(
    r"^(?P<name>[^@]+)@file://(?P<path>.+)$"
)
_PLAIN_SPEC_RE = re.compile(
    r"^(?P<name>[a-zA-Z0-9_][a-zA-Z0-9_.-]*)$"
)


class PackageSpecifier(BaseModel):
    raw: str
    name: str
    spec_type: Literal["git", "local", "pypi"]
    url: str
    ref: str = "main"

    @classmethod
    def parse(cls, raw: str) -> "PackageSpecifier":
        m = _GITHUB_URL_RE.match(raw)
        if m:
            name = m.group("repo")
            url = f"https://github.com/{m.group('owner')}/{name}"
            ref = m.group("ref") or "main"
            return cls(raw=raw, name=name, spec_type="git", url=url, ref=ref)

        m = _GITHUB_SHORT_RE.match(raw)
        if m:
            name = m.group("repo")
            url = f"https://github.com/{m.group('owner')}/{name}"
            ref = m.group("ref") or "main"
            return cls(raw=raw, name=name, spec_type="git", url=url, ref=ref)

        m = _GIT_SPEC_RE.match(raw)
        if m:
            return cls(
                raw=raw,
                name=m.group("name"),
                spec_type="git",
                url=m.group("url"),
                ref=m.group("ref") or "main",
            )

        m = _LOCAL_SPEC_RE.match(raw)
        if m:
            return cls(
                raw=raw,
                name=m.group("name"),
                spec_type="local",
                url=m.group("path"),
                ref="main",
            )

        m = _PLAIN_SPEC_RE.match(raw)
        if m:
            return cls(
                raw=raw,
                name=m.group("name"),
                spec_type="pypi",
                url=m.group("name"),
                ref="latest",
            )

        raise ValueError(f"Invalid package specifier: {raw!r}")


class ResolvedPackage(BaseModel):
    specifier: PackageSpecifier
    install_path: str
    resolved_ref: str
    has_plugin_entry: bool
    skill_dirs: list[str]
    metadata: dict = {}


class PackageResolver:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, spec: PackageSpecifier) -> ResolvedPackage:
        if spec.spec_type == "pypi":
            raise ValueError("PyPI packages not yet supported")

        target_dir = self.cache_dir / spec.name

        if spec.spec_type == "git":
            if target_dir.exists():
                ref_file = target_dir / ".ref"
                if ref_file.exists():
                    stored_ref = ref_file.read_text().strip()
                    if stored_ref == spec.ref:
                        pass
                    else:
                        shutil.rmtree(target_dir)
                else:
                    shutil.rmtree(target_dir)

            if not target_dir.exists():
                Repo.clone_from(spec.url, str(target_dir), branch=spec.ref, depth=1)
                repo = Repo(str(target_dir))
                commit_hash = str(repo.head.commit)
                (target_dir / ".ref").write_text(spec.ref)
                (target_dir / ".commit").write_text(commit_hash)

        elif spec.spec_type == "local":
            if target_dir.exists() or target_dir.is_symlink():
                target_dir.unlink() if target_dir.is_symlink() else shutil.rmtree(target_dir)
            target_dir.symlink_to(spec.url)

        has_plugin_entry = (target_dir / "reflexion_plugin.py").exists()
        skill_dirs = self._discover_skill_dirs(target_dir)
        resolved_ref = ""
        commit_file = target_dir / ".commit"
        if commit_file.exists():
            resolved_ref = commit_file.read_text().strip()

        return ResolvedPackage(
            specifier=spec,
            install_path=str(target_dir),
            resolved_ref=resolved_ref,
            has_plugin_entry=has_plugin_entry,
            skill_dirs=skill_dirs,
        )

    def resolve_all(self, specs: list[str]) -> list[ResolvedPackage]:
        return [self.resolve(PackageSpecifier.parse(s)) for s in specs]

    def is_update_available(self, spec: PackageSpecifier) -> bool:
        if spec.spec_type != "git":
            return False
        target_dir = self.cache_dir / spec.name
        commit_file = target_dir / ".commit"
        if not commit_file.exists():
            return True
        local_commit = commit_file.read_text().strip()
        remote_refs = Repo(str(target_dir)).remotes.origin.fetch(spec.ref)
        if remote_refs:
            remote_commit = str(remote_refs[0].commit)
            return remote_commit != local_commit
        return False

    def update(self, spec: PackageSpecifier) -> ResolvedPackage:
        target_dir = self.cache_dir / spec.name
        if target_dir.exists() and not target_dir.is_symlink():
            shutil.rmtree(target_dir)
        elif target_dir.is_symlink():
            target_dir.unlink()
        return self.resolve(spec)

    def remove(self, name: str) -> bool:
        target_dir = self.cache_dir / name
        if not target_dir.exists() and not target_dir.is_symlink():
            return False
        if target_dir.is_symlink():
            target_dir.unlink()
        else:
            shutil.rmtree(target_dir)
        return True

    def _discover_skill_dirs(self, root: Path) -> list[str]:
        result = []
        for skill_file in root.rglob("SKILL.md"):
            parent = skill_file.parent
            result.append(str(parent))
        return result

    def list_installed(self) -> list[ResolvedPackage]:
        result = []
        if not self.cache_dir.exists():
            return result
        for child in sorted(self.cache_dir.iterdir()):
            if child.is_dir() or child.is_symlink():
                ref_file = child / ".ref"
                ref = ref_file.read_text().strip() if ref_file.exists() else "main"
                name = child.name
                if child.is_symlink():
                    spec = PackageSpecifier(
                        raw=name, name=name, spec_type="local",
                        url=str(child.resolve()), ref="main",
                    )
                else:
                    spec = PackageSpecifier(
                        raw=name, name=name, spec_type="git",
                        url="", ref=ref,
                    )

                has_plugin_entry = (child / "reflexion_plugin.py").exists()
                skill_dirs = self._discover_skill_dirs(child)
                commit_file = child / ".commit"
                resolved_ref = commit_file.read_text().strip() if commit_file.exists() else ""

                result.append(ResolvedPackage(
                    specifier=spec,
                    install_path=str(child),
                    resolved_ref=resolved_ref,
                    has_plugin_entry=has_plugin_entry,
                    skill_dirs=skill_dirs,
                ))
        return result

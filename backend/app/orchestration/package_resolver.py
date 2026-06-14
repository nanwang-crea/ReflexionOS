import logging
import re
import shutil
from pathlib import Path
from typing import Literal

import requests
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


def _get_github_default_branch(owner: str, repo: str, timeout: int = 5) -> str:
    """获取 GitHub 仓库的默认分支

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        timeout: 超时时间（秒）

    Returns:
        默认分支名，如果获取失败则返回 "main"
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            default_branch = data.get("default_branch", "main")
            logger.info("获取 %s/%s 的默认分支: %s", owner, repo, default_branch)
            return default_branch
        elif response.status_code == 403:
            # API 限流，尝试从 git ls-remote 获取（不消耗 API 配额）
            logger.warning("GitHub API 限流，尝试使用 git ls-remote 获取 %s/%s 的默认分支", owner, repo)
            try:
                import subprocess
                result = subprocess.run(
                    ['git', 'ls-remote', '--symref', f'https://github.com/{owner}/{repo}', 'HEAD'],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                if result.returncode == 0:
                    # 解析输出: "ref: refs/heads/master	HEAD"
                    for line in result.stdout.split('\n'):
                        if line.startswith('ref:'):
                            ref_path = line.split()[1]
                            branch = ref_path.split('/')[-1]
                            logger.info("通过 git ls-remote 获取 %s/%s 的默认分支: %s", owner, repo, branch)
                            return branch
            except Exception as e:
                logger.warning("git ls-remote 失败: %s", e)
            return "main"
        else:
            logger.warning("无法获取 %s/%s 的默认分支 (状态码: %d)，使用 main", owner, repo, response.status_code)
            return "main"
    except Exception as e:
        logger.warning("获取 %s/%s 的默认分支失败: %s，使用 main", owner, repo, e)
        return "main"


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
            owner = m.group("owner")
            url = f"https://github.com/{owner}/{name}"
            # 如果用户指定了分支，使用用户指定的；否则动态获取默认分支
            ref = m.group("ref") or _get_github_default_branch(owner, name)
            return cls(raw=raw, name=name, spec_type="git", url=url, ref=ref)

        m = _GITHUB_SHORT_RE.match(raw)
        if m:
            name = m.group("repo")
            owner = m.group("owner")
            url = f"https://github.com/{owner}/{name}"
            # 如果用户指定了分支，使用用户指定的；否则动态获取默认分支
            ref = m.group("ref") or _get_github_default_branch(owner, name)
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

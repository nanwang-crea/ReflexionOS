"""
外部插件包解析与安装模块。

解析用户提供的插件包标识符（GitHub 短名/URL、git+URL、本地路径），
将其克隆/链接到本地缓存目录，并发现其中的插件入口与技能目录，
供 PluginLoader 后续加载使用。支持增量更新与卸载。
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Literal

import requests
from git import Repo
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# owner/repo[@ref] 形式的 GitHub 简写
_GITHUB_SHORT_RE = re.compile(
    r"^(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo>[a-zA-Z0-9_.-]+?)(?:@(?P<ref>.+))?$"
)
# 完整 GitHub URL，可选 #ref 指定分支/tag
_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo>[a-zA-Z0-9_.-]+?)(?:\.git)?(?:#(?P<ref>.+))?(?:/)?$"
)
# name@git+URL[#ref] 形式的通用 git 仓库指定
_GIT_SPEC_RE = re.compile(
    r"^(?P<name>[^@]+)@git\+(?P<url>https?://.+?)(?:#(?P<ref>.+))?$"
)
# name@file://path 形式的本地路径指定
_LOCAL_SPEC_RE = re.compile(
    r"^(?P<name>[^@]+)@file://(?P<path>.+)$"
)
# 纯包名（不带任何前缀），当前仅用于识别并报错（不支持 PyPI 包）
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
    """插件包标识符：解析用户输入的原始字符串得到的结构化结果"""

    raw: str
    name: str
    spec_type: Literal["git", "local", "pypi"]
    url: str
    ref: str = "main"

    @classmethod
    def parse(cls, raw: str) -> "PackageSpecifier":
        """解析插件包标识符字符串

        依次尝试匹配以下格式（命中即返回）：
            1. 完整 GitHub URL（https://github.com/owner/repo[#ref]）
            2. GitHub 简写（owner/repo[@ref]）
            3. 通用 git 仓库（name@git+URL[#ref]）
            4. 本地路径（name@file://path）
            5. 纯包名 —— 视为不支持的 PyPI 包，直接抛错

        GitHub 类型若未显式指定 ref，会调用 `_get_github_default_branch`
        动态查询默认分支。

        Args:
            raw: 用户输入的原始标识符字符串

        Returns:
            PackageSpecifier: 解析后的结构化标识符

        Raises:
            ValueError: 格式不被任何规则匹配，或识别为不支持的 PyPI 包
        """
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
            # PyPI 包不支持，提供明确的错误信息
            raise ValueError(
                f"Invalid plugin specifier: '{raw}'. "
                "PyPI packages are not supported. "
                "Supported formats: "
                "GitHub short (owner/repo), "
                "GitHub URL (https://github.com/owner/repo), "
                "Git (name@git+https://...), "
                "Local (name@local:///absolute/path)"
            )

        raise ValueError(f"Invalid package specifier: {raw!r}")


class ResolvedPackage(BaseModel):
    """解析并安装完成后的插件包信息"""

    specifier: PackageSpecifier
    install_path: str
    resolved_ref: str
    has_plugin_entry: bool
    skill_dirs: list[str]
    metadata: dict = {}


class PackageResolver:
    """插件包解析器：负责克隆/链接、发现、更新、卸载插件包到本地缓存目录"""

    def __init__(self, cache_dir: Path):
        """初始化解析器

        Args:
            cache_dir: 插件包本地缓存根目录，不存在时自动创建
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, spec: PackageSpecifier) -> ResolvedPackage:
        """解析并安装单个插件包

        工作流程：
            - git 类型：若缓存目录已存在且 ref 未变则复用，否则清空重新
              clone（浅克隆，depth=1），并记录 `.ref`/`.commit` 文件；
            - local 类型：清理旧的软链接/目录后，重新创建指向源路径的软链接；
            - 安装完成后探测是否存在 `reflexion_plugin.py` 入口文件，
              并递归查找所有 `SKILL.md` 所在目录作为技能目录。

        Args:
            spec: 已解析的包标识符

        Returns:
            ResolvedPackage: 安装路径、已解析的 commit、插件入口与技能目录等信息

        Raises:
            ValueError: spec_type 为不支持的 "pypi"（parse 阶段的双重保险）
        """
        # PyPI 包类型应该在 parse 阶段就被拒绝了，这里是双重保险
        if spec.spec_type == "pypi":
            raise ValueError(
                f"PyPI packages are not supported. Invalid specifier: '{spec.raw}'"
            )

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
        """批量解析并安装多个插件包

        Args:
            specs: 原始标识符字符串列表

        Returns:
            list[ResolvedPackage]: 依次解析安装后的结果列表
        """
        return [self.resolve(PackageSpecifier.parse(s)) for s in specs]

    def is_update_available(self, spec: PackageSpecifier) -> bool:
        """检测 git 类型插件包是否有可用更新

        通过 `git fetch` 拉取远端 ref 对应的最新 commit，与本地记录的
        `.commit` 文件比对判断。非 git 类型或本地无 `.commit` 记录时
        视为需要更新/不适用。

        Args:
            spec: 已解析的包标识符

        Returns:
            bool: 是否存在可用更新
        """
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
        """强制更新插件包：删除本地缓存后重新 resolve 安装

        Args:
            spec: 已解析的包标识符

        Returns:
            ResolvedPackage: 更新后的安装结果
        """
        target_dir = self.cache_dir / spec.name
        if target_dir.exists() and not target_dir.is_symlink():
            shutil.rmtree(target_dir)
        elif target_dir.is_symlink():
            target_dir.unlink()
        return self.resolve(spec)

    def remove(self, name: str) -> bool:
        """卸载已安装的插件包（删除本地目录或软链接）

        Args:
            name: 插件包名称

        Returns:
            bool: 是否实际删除（目录/软链接原本不存在则返回 False）
        """
        target_dir = self.cache_dir / name
        if not target_dir.exists() and not target_dir.is_symlink():
            return False
        if target_dir.is_symlink():
            target_dir.unlink()
        else:
            shutil.rmtree(target_dir)
        return True

    def _discover_skill_dirs(self, root: Path) -> list[str]:
        """递归查找目录下所有包含 SKILL.md 的技能目录

        Args:
            root: 搜索根目录

        Returns:
            list[str]: 各技能目录（SKILL.md 所在父目录）的路径列表
        """
        result = []
        for skill_file in root.rglob("SKILL.md"):
            parent = skill_file.parent
            result.append(str(parent))
        return result

    def list_installed(self) -> list[ResolvedPackage]:
        """列出缓存目录下所有已安装的插件包

        遍历 cache_dir 下的子目录/软链接，按类型（本地软链接 -> local，
        普通目录 -> git）重建 PackageSpecifier，并读取 `.ref`/`.commit`
        文件补全版本信息。

        Returns:
            list[ResolvedPackage]: 已安装插件包信息列表，按名称排序
        """
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

"""
插件加载模块。

在 PackageResolver 完成插件包下载/链接后，负责实际加载插件：
优先执行插件自带的 `reflexion_plugin.py` 入口（调用其 register() 获取
工具/钩子/技能目录/配置schema），若无入口或加载失败则回退为自动发现
（扫描 SKILL.md 目录）。同时维护事件钩子注册表供其他模块触发。
"""

import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from app.orchestration.package_resolver import PackageResolver, ResolvedPackage

logger = logging.getLogger(__name__)


class PluginRegistration(BaseModel):
    """单个插件的注册结果：暴露的工具、技能目录、配置 schema"""

    plugin_name: str
    tools: list[dict]
    skill_dirs: list[str]
    config_schema: dict | None = None


class PluginLoader:
    """插件加载器：解析插件入口、注册工具/钩子/技能目录"""

    def __init__(self, resolver: PackageResolver):
        """初始化加载器

        Args:
            resolver: 用于定位已安装插件包的 PackageResolver 实例
        """
        self._resolver = resolver
        self._registrations: dict[str, PluginRegistration] = {}
        self._hook_registry: dict[str, list[Callable]] = {}

    def load_plugin(self, package: ResolvedPackage) -> PluginRegistration | None:
        """加载单个已安装的插件包

        工作流程：
            1. 检查安装目录下是否存在 `reflexion_plugin.py` 入口文件；
            2. 若存在，动态导入该模块并调用其 `register()` 函数获取
               tools/hooks/skill_dirs/config_schema；
            3. register() 返回的 hooks 按事件名注册进 `_hook_registry`；
            4. register() 未提供 skill_dirs 时，自动扫描安装目录发现技能目录；
            5. 若入口文件不存在、缺少 register()、返回值非法或加载异常，
               均回退到 `_auto_register`（纯目录扫描，不解析入口逻辑）。

        Args:
            package: 已由 PackageResolver 解析安装的包信息

        Returns:
            PluginRegistration | None: 加载得到的注册信息（当前实现恒返回非 None）
        """
        install_path = Path(package.install_path)
        entry_path = install_path / "reflexion_plugin.py"

        if entry_path.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"reflexion_plugin_{package.specifier.name}", str(entry_path)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if not hasattr(module, "register"):
                    logger.warning("Plugin %s has reflexion_plugin.py but no register() function", package.specifier.name)
                    return self._auto_register(package)

                reg_data = module.register()
                if not isinstance(reg_data, dict):
                    logger.warning("Plugin %s register() must return dict", package.specifier.name)
                    return self._auto_register(package)

                tools = reg_data.get("tools", [])
                hooks = reg_data.get("hooks", {})
                skill_dirs_rel = reg_data.get("skill_dirs", [])
                config_schema = reg_data.get("config_schema")

                skill_dirs_abs = [str(install_path / d) for d in skill_dirs_rel]
                if not skill_dirs_abs:
                    skill_dirs_abs = self._auto_discover_skills(str(install_path))

                for event_name, hook_fn in hooks.items():
                    if callable(hook_fn):
                        self._hook_registry.setdefault(event_name, []).append(hook_fn)

                registration = PluginRegistration(
                    plugin_name=package.specifier.name,
                    tools=tools if isinstance(tools, list) else [],
                    skill_dirs=skill_dirs_abs,
                    config_schema=config_schema,
                )
                self._registrations[package.specifier.name] = registration
                logger.info("Loaded plugin: %s (entry point)", package.specifier.name)
                return registration

            except Exception:
                logger.exception("Failed to load plugin entry point: %s", package.specifier.name)
                return self._auto_register(package)
        else:
            return self._auto_register(package)

    def _auto_register(self, package: ResolvedPackage) -> PluginRegistration:
        """无插件入口时的兜底注册：仅扫描技能目录，不提供 tools

        Args:
            package: 已安装的包信息

        Returns:
            PluginRegistration: 仅含 skill_dirs 的注册信息，并写入注册表
        """
        skill_dirs = self._auto_discover_skills(package.install_path)
        registration = PluginRegistration(
            plugin_name=package.specifier.name,
            tools=[],
            skill_dirs=skill_dirs,
        )
        self._registrations[package.specifier.name] = registration
        logger.info("Auto-registered plugin: %s (%d skill dirs)", package.specifier.name, len(skill_dirs))
        return registration

    def _auto_discover_skills(self, root: str) -> list[str]:
        """在给定目录下自动发现技能目录

        逻辑：递归查找所有 SKILL.md，仅保留"叶子"技能目录（即该目录的
        子目录中没有再包含 SKILL.md 的，避免父子技能目录重复收录）；
        若未发现任何技能目录，退回检查是否存在约定的 `skills/` 子目录。

        Args:
            root: 搜索根目录（插件安装路径）

        Returns:
            list[str]: 技能目录路径列表（已排序）
        """
        root_path = Path(root)
        if not root_path.is_dir():
            return []
        result = set()
        for skill_file in root_path.rglob("SKILL.md"):
            parent = skill_file.parent
            has_child_skills = any((parent / child).is_dir() and (parent / child / "SKILL.md").exists() for child in parent.iterdir() if child.is_dir())
            if not has_child_skills:
                result.add(str(parent))
        if not result:
            skills_dir = root_path / "skills"
            if skills_dir.is_dir():
                result.add(str(skills_dir))
        return sorted(result)

    def load_all(self, packages: list[ResolvedPackage]) -> list[PluginRegistration]:
        """批量加载多个已安装插件包

        Args:
            packages: 已安装的包信息列表

        Returns:
            list[PluginRegistration]: 依次加载成功的注册信息列表
        """
        results = []
        for p in packages:
            reg = self.load_plugin(p)
            if reg is not None:
                results.append(reg)
        return results

    def get_all_skill_dirs(self) -> list[tuple[str, str]]:
        """返回 (plugin_name, skill_dir) 元组列表"""
        result = []
        for plugin_name, reg in self._registrations.items():
            for skill_dir in reg.skill_dirs:
                result.append((plugin_name, skill_dir))
        return result

    def get_hook(self, event: str) -> list[Callable]:
        """获取指定事件名注册的所有钩子函数

        Args:
            event: 事件名称

        Returns:
            list[Callable]: 对应的钩子函数列表，无注册则返回空列表
        """
        return self._hook_registry.get(event, [])

    def get_registration(self, name: str) -> PluginRegistration | None:
        """按插件名获取其注册信息

        Args:
            name: 插件名称

        Returns:
            PluginRegistration | None: 对应的注册信息，不存在则返回 None
        """
        return self._registrations.get(name)

    def list_registrations(self) -> list[PluginRegistration]:
        """列出所有已注册插件的信息

        Returns:
            list[PluginRegistration]: 全部注册信息列表
        """
        return list(self._registrations.values())

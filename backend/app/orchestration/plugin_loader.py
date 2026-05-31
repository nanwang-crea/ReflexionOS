import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from app.orchestration.package_resolver import PackageResolver, ResolvedPackage

logger = logging.getLogger(__name__)


class PluginRegistration(BaseModel):
    plugin_name: str
    tools: list[dict]
    skill_dirs: list[str]
    config_schema: dict | None = None


class PluginLoader:
    def __init__(self, resolver: PackageResolver):
        self._resolver = resolver
        self._registrations: dict[str, PluginRegistration] = {}
        self._hook_registry: dict[str, list[Callable]] = {}

    def load_plugin(self, package: ResolvedPackage) -> PluginRegistration | None:
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
        results = []
        for p in packages:
            reg = self.load_plugin(p)
            if reg is not None:
                results.append(reg)
        return results

    def get_all_skill_dirs(self) -> list[str]:
        return [d for r in self._registrations.values() for d in r.skill_dirs]

    def get_hook(self, event: str) -> list[Callable]:
        return self._hook_registry.get(event, [])

    def get_registration(self, name: str) -> PluginRegistration | None:
        return self._registrations.get(name)

    def list_registrations(self) -> list[PluginRegistration]:
        return list(self._registrations.values())

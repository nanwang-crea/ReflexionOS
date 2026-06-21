import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.orchestration.package_resolver import PackageResolver, PackageSpecifier
from app.orchestration.plugin_loader import PluginLoader
from app.orchestration.skill_registry import skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class InstallPluginRequest(BaseModel):
    specifier: str


_module_loader: PluginLoader | None = None


def _get_resolver_and_loader():
    global _module_loader
    from app.config.settings import config_manager
    plugin_settings = config_manager.settings.plugin
    resolver = PackageResolver(Path(plugin_settings.package_cache_dir))
    if _module_loader is None:
        _module_loader = PluginLoader(resolver)
        try:
            installed = resolver.list_installed()
            if installed:
                _module_loader.load_all(installed)
                logger.info("Auto-loaded %d installed plugins into singleton loader", len(installed))
                # 注意：技能注册由 skill_registry.scan_all() 统一完成，
                # 不在这里 scan_recursive，避免被后续 scan_all 的 clear() 覆盖
        except Exception:
            logger.exception("Failed to auto-load installed plugins")
    return resolver, _module_loader


@router.get("/")
async def list_plugins():
    resolver, loader = _get_resolver_and_loader()
    installed = resolver.list_installed()

    result = []
    for pkg in installed:
        reg = loader.get_registration(pkg.specifier.name)
        entry = {
            "name": pkg.specifier.name,
            "specifier": pkg.specifier.raw,
            "resolved_ref": pkg.resolved_ref,
            "install_path": pkg.install_path,
            "has_tools": len(reg.tools) > 0 if reg else pkg.has_plugin_entry,
            "skill_dirs": reg.skill_dirs if reg else pkg.skill_dirs,
            "num_skills": len(reg.skill_dirs) if reg else len(pkg.skill_dirs),
        }
        result.append(entry)
    return result


@router.post("/install")
async def install_plugin(req: InstallPluginRequest):
    from app.config.settings import config_manager

    try:
        spec = PackageSpecifier.parse(req.specifier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # 双重检查：不应该出现 pypi 类型（parse 阶段已拒绝）
    if spec.spec_type == "pypi":
        raise HTTPException(
            status_code=400,
            detail="PyPI packages are not supported. Use GitHub (owner/repo) or Git (name@git+url) format"
        )

    resolver, loader = _get_resolver_and_loader()
    try:
        package = resolver.resolve(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    registration = loader.load_plugin(package)

    if registration and registration.skill_dirs:
        for d in registration.skill_dirs:
            skill_registry.scan_recursive(d, source_type="plugin", plugin_name=spec.name)

    # 写入配置文件 - 统一转换为 name@git+url#ref 格式
    plugin_settings = config_manager.settings.plugin
    # 检查是否已存在（按 name 匹配）
    exists = any(
        s.startswith(f"{spec.name}@") or s == spec.name
        for s in plugin_settings.plugins
    )
    if not exists:
        # 统一转换为 name@git+url#ref 格式
        if spec.spec_type == "git" and spec.url:
            normalized_specifier = f"{spec.name}@git+{spec.url}#{spec.ref}"
        else:
            normalized_specifier = req.specifier
        plugin_settings.plugins.append(normalized_specifier)
        config_manager.save()
        logger.info("Added plugin '%s' to config with normalized specifier: %s", spec.name, normalized_specifier)

    return {
        "name": spec.name,
        "install_path": package.install_path,
        "resolved_ref": package.resolved_ref,
        "skill_dirs": registration.skill_dirs if registration else [],
        "installed": True,
    }


@router.delete("/{plugin_name}")
async def uninstall_plugin(plugin_name: str):
    from app.config.settings import config_manager

    resolver, loader = _get_resolver_and_loader()
    registration = loader.get_registration(plugin_name)
    if registration:
        for _skill_dir in registration.skill_dirs:
            for skill in skill_registry.list_skills():
                if skill.plugin_name == plugin_name:
                    skill_registry.unregister_skill(skill.name)

    removed = resolver.remove(plugin_name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    loader._registrations.pop(plugin_name, None)

    # 从配置文件中移除
    plugin_settings = config_manager.settings.plugin
    original_count = len(plugin_settings.plugins)
    plugin_settings.plugins = [
        s for s in plugin_settings.plugins
        if not (s.startswith(f"{plugin_name}@") or s == plugin_name)
    ]
    if len(plugin_settings.plugins) < original_count:
        config_manager.save()
        logger.info("Removed plugin '%s' from config", plugin_name)

    return {"name": plugin_name, "uninstalled": True}


@router.post("/update/{plugin_name}")
async def update_plugin(plugin_name: str):
    from app.config.settings import config_manager
    plugin_settings = config_manager.settings.plugin

    matching = [s for s in plugin_settings.plugins if s.startswith(f"{plugin_name}@") or s == plugin_name]
    if not matching:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not in config")

    spec = PackageSpecifier.parse(matching[0])
    resolver, loader = _get_resolver_and_loader()

    try:
        package = resolver.update(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    loader._registrations.pop(plugin_name, None)
    registration = loader.load_plugin(package)

    if registration and registration.skill_dirs:
        for d in registration.skill_dirs:
            skill_registry.scan_recursive(d, source_type="plugin", plugin_name=spec.name)

    return {
        "name": spec.name,
        "install_path": package.install_path,
        "resolved_ref": package.resolved_ref,
        "updated": True,
    }


@router.post("/update")
async def update_all_plugins():
    from app.config.settings import config_manager
    plugin_settings = config_manager.settings.plugin

    if not plugin_settings.plugins:
        return {"updated": [], "errors": []}

    resolver, loader = _get_resolver_and_loader()
    updated = []
    errors = []

    for spec_str in plugin_settings.plugins:
        try:
            spec = PackageSpecifier.parse(spec_str)
            if resolver.is_update_available(spec):
                package = resolver.update(spec)
                loader._registrations.pop(spec.name, None)
                registration = loader.load_plugin(package)
                if registration and registration.skill_dirs:
                    for d in registration.skill_dirs:
                        skill_registry.scan_recursive(d, source_type="plugin", plugin_name=spec.name)
                updated.append(spec.name)
            else:
                pass
        except Exception as e:
            errors.append({"plugin": spec_str, "error": str(e)})

    return {"updated": updated, "errors": errors}


@router.get("/{plugin_name}/skills")
async def list_plugin_skills(plugin_name: str):
    resolver, loader = _get_resolver_and_loader()
    registration = loader.get_registration(plugin_name)
    if registration is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    skills = [s for s in skill_registry.list_skills() if s.plugin_name == plugin_name]
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "enabled": s.enabled,
        }
        for s in skills
    ]

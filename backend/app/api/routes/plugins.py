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


def _get_resolver_and_loader():
    from app.config.settings import config_manager
    plugin_settings = config_manager.settings.plugin
    resolver = PackageResolver(Path(plugin_settings.package_cache_dir))
    loader = PluginLoader(resolver)
    return resolver, loader


@router.get("/")
async def list_plugins():
    resolver, loader = _get_resolver_and_loader()
    registrations = loader.list_registrations()
    installed = resolver.list_installed()
    installed_map = {p.specifier.name: p for p in installed}

    result = []
    for reg in registrations:
        pkg = installed_map.get(reg.plugin_name)
        entry = {
            "name": reg.plugin_name,
            "has_tools": len(reg.tools) > 0,
            "skill_dirs": reg.skill_dirs,
            "num_skills": len(reg.skill_dirs),
        }
        if pkg:
            entry["specifier"] = pkg.specifier.raw
            entry["resolved_ref"] = pkg.resolved_ref
            entry["install_path"] = pkg.install_path
        result.append(entry)
    return result


@router.post("/install")
async def install_plugin(req: InstallPluginRequest):
    try:
        spec = PackageSpecifier.parse(req.specifier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    resolver, loader = _get_resolver_and_loader()
    try:
        package = resolver.resolve(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    registration = loader.load_plugin(package)

    if registration and registration.skill_dirs:
        for d in registration.skill_dirs:
            skill_registry.scan_recursive(d, source_type="plugin", plugin_name=spec.name)

    return {
        "name": spec.name,
        "install_path": package.install_path,
        "resolved_ref": package.resolved_ref,
        "skill_dirs": registration.skill_dirs if registration else [],
        "installed": True,
    }


@router.delete("/{plugin_name}")
async def uninstall_plugin(plugin_name: str):
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

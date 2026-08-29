# 文件功能：插件管理相关的 API 路由
# 文件描述：提供插件（Plugin）的查询、安装、卸载、更新接口，插件安装后会附带的技能目录
#   会被扫描并注册进 skill_registry，供 Agent 调用
# 核心逻辑：通过 PackageResolver 负责包的下载/解析/落盘，PluginLoader 负责加载插件模块
#   并维护插件-技能的注册关系；两者以进程内单例形式复用，避免重复加载
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config.settings import config_manager
from app.orchestration.package_resolver import PackageResolver, PackageSpecifier
from app.orchestration.plugin_loader import PluginLoader
from app.orchestration.skill_registry import skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class InstallPluginRequest(BaseModel):
    """安装插件请求体：specifier 为插件说明符（如 owner/repo 或 name@git+url#ref）"""
    specifier: str


_module_loader: PluginLoader | None = None


def _get_resolver_and_loader():
    """
    获取（或初始化）包解析器与插件加载器单例。
    入参：无
    逻辑：每次调用都基于当前配置新建 PackageResolver；PluginLoader 首次创建时会自动
      加载所有已安装插件到内存，方便后续查询注册信息（技能扫描由 skill_registry.scan_all()
      统一处理，此处不重复扫描，避免被其 clear() 覆盖）
    出参：(resolver, loader) 元组
    """
    global _module_loader
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
    """
    GET /api/plugins/：查询已安装插件列表。
    入参：无
    逻辑：读取已安装包列表，逐个关联其加载注册信息（工具数量、技能目录等）
    出参：list[dict]，每项包含 name/specifier/resolved_ref/install_path/has_tools/skill_dirs/num_skills
    """
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
    """
    POST /api/plugins/install：安装一个插件。
    入参：req.specifier —— 插件说明符，支持 GitHub（owner/repo）或 Git（name@git+url#ref）格式，不支持 PyPI
    逻辑：解析说明符 -> 用 resolver 拉取/解析包 -> 用 loader 加载插件模块 -> 若插件带技能目录，
      扫描注册进 skill_registry -> 若配置中尚未记录该插件，写入配置文件（统一转换为 name@git+url#ref 格式）
    出参：dict，包含 name/install_path/resolved_ref/skill_dirs/installed
    """
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
    """
    DELETE /api/plugins/{plugin_name}：卸载指定插件。
    入参：plugin_name —— 插件名
    逻辑：先从 skill_registry 中注销该插件下的所有技能 -> 删除本地已安装的包文件 ->
      清理内存中的插件注册信息 -> 从配置文件中移除该插件记录
    出参：dict，{"name": 插件名, "uninstalled": True}；插件不存在则 404
    """
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
    """
    POST /api/plugins/update/{plugin_name}：更新指定插件到最新版本。
    入参：plugin_name —— 插件名
    逻辑：从配置中找到该插件的说明符 -> resolver.update 拉取最新版本 -> 清除旧的加载注册信息
      并重新加载 -> 若有技能目录则重新扫描注册
    出参：dict，包含 name/install_path/resolved_ref/updated；插件未在配置中记录则 404
    """
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
    """
    POST /api/plugins/update：批量检查并更新所有已配置插件。
    入参：无
    逻辑：遍历配置中所有插件说明符，逐个判断是否有新版本可用，有则更新、重新加载并
      重新扫描技能目录；单个插件更新失败不影响其余插件，错误会被收集返回
    出参：dict，{"updated": [已更新插件名列表], "errors": [{"plugin":..., "error":...}, ...]}
    """
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
    """
    GET /api/plugins/{plugin_name}/skills：查询指定插件下的所有技能。
    入参：plugin_name —— 插件名
    逻辑：确认插件已加载注册后，从 skill_registry 中筛选出属于该插件的技能
    出参：list[dict]，每项包含 name/description/category/enabled；插件不存在则 404
    """
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

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.orchestration.package_resolver import PackageResolver, PackageSpecifier
from app.orchestration.skill_parser import parse_skill_md
from app.orchestration.skill_registry import SkillMetadata, SkillSource, skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])


class InstallSkillRequest(BaseModel):
    specifier: str


@router.get("/")
async def list_skills():
    metadata_list = skill_registry.list_skills()
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "required_skills": s.required_skills,
            "enabled": s.enabled,
            "source": s.source,
            "source_type": s.source_type.value if s.source_type else "",
            "install_path": s.install_path,
            "plugin_name": s.plugin_name,
            "version": s.version,
        }
        for s in metadata_list
    ]


@router.get("/categories")
async def list_categories():
    result: dict[str, list[dict]] = {}
    for skill in skill_registry.list_skills():
        cat = skill.category or "uncategorized"
        result.setdefault(cat, []).append({
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
        })
    return result


@router.post("/refresh")
async def refresh_skills():
    count = skill_registry.refresh()
    return {"total_skills": count}


@router.post("/install")
async def install_skill(req: InstallSkillRequest):
    try:
        spec = PackageSpecifier.parse(req.specifier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if spec.spec_type == "pypi":
        raise HTTPException(status_code=400, detail="PyPI packages not yet supported")

    from app.config.settings import config_manager
    skill_install_dir = Path(config_manager.settings.skill.install_dir)
    target_dir = skill_install_dir / spec.name
    target_dir.mkdir(parents=True, exist_ok=True)

    resolver = PackageResolver(skill_install_dir)
    try:
        package = resolver.resolve(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    count = 0
    skill_dirs = package.skill_dirs
    if not skill_dirs:
        skill_dirs = [str(package.install_path)]

    for d in skill_dirs:
        count += skill_registry.scan_recursive(d, source_type=SkillSource.GLOBAL, plugin_name="")

    if count == 0:
        raise HTTPException(status_code=400, detail=f"未在 {req.specifier} 中发现技能（缺少 SKILL.md）")

    return {"specifier": req.specifier, "installed_skills": count, "install_path": str(target_dir)}


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str):
    skill = skill_registry.get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")

    install_path = skill.install_path
    source_type = skill.source_type

    skill_registry.unregister_skill(skill_name)

    if source_type == SkillSource.GLOBAL and install_path:
        from app.config.settings import config_manager
        skill_install_dir = Path(config_manager.settings.skill.install_dir)
        for child in skill_install_dir.iterdir():
            if child.is_dir() and install_path.startswith(str(child)):
                import shutil
                shutil.rmtree(child, ignore_errors=True)
                break

    return {"name": skill_name, "deleted": True}


@router.get("/{skill_name}")
async def get_skill_detail(skill_name: str):
    skill = skill_registry.get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")

    content = skill_registry.get_skill_content(skill_name)
    return {
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "required_skills": skill.required_skills,
        "enabled": skill.enabled,
        "source": skill.source,
        "source_type": skill.source_type.value if skill.source_type else "",
        "install_path": skill.install_path,
        "plugin_name": skill.plugin_name,
        "version": skill.version,
        "content": content or "",
    }


@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str):
    ok = skill_registry.enable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": True}


@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str):
    ok = skill_registry.disable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": False}

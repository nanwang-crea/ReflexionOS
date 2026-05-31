from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.orchestration.skill_registry import skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


class InstallRequest(BaseModel):
    url: str
    skill_name: str
    subdir: str = ""
    branch: str = "main"


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
            "install_path": s.install_path,
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


@router.post("/install")
async def install_skill(req: InstallRequest):
    result = skill_registry.install_skill(
        url=req.url,
        skill_name=req.skill_name,
        subdir=req.subdir,
        branch=req.branch,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    skill = skill_registry.get_skill(req.skill_name)
    return {
        "name": skill.name if skill else req.skill_name,
        "install_path": result.install_path,
        "installed": True,
    }


@router.post("/refresh")
async def refresh_skills():
    count = skill_registry.refresh()
    return {"total_skills": count}


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
        "install_path": skill.install_path,
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


@router.delete("/{skill_name}")
async def uninstall_skill(skill_name: str):
    result = skill_registry.uninstall_skill(skill_name)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"name": skill_name, "uninstalled": True}

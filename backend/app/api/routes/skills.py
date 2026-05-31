from fastapi import APIRouter, HTTPException

from app.orchestration.skill_registry import skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/")
async def list_skills():
    """列出所有技能（仅元数据，不含内容）"""
    metadata_list = skill_registry.list_skills()
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "required_skills": s.required_skills,
            "enabled": s.enabled,
        }
        for s in metadata_list
    ]


@router.get("/categories")
async def list_categories():
    """按分类列出技能"""
    result: dict[str, list[dict]] = {}
    for skill in skill_registry.list_skills():
        cat = skill.category or "uncategorized"
        result.setdefault(cat, []).append({
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
        })
    return result


@router.get("/{skill_name}")
async def get_skill_detail(skill_name: str):
    """获取技能详情（含完整内容）"""
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
        "content": content or "",
    }


@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str):
    """启用技能"""
    ok = skill_registry.enable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": True}


@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str):
    """禁用技能"""
    ok = skill_registry.disable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": False}

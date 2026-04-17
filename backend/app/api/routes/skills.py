from typing import List

from fastapi import APIRouter

from app.orchestration.skill_registry import Skill, skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/", response_model=List[Skill])
async def list_skills():
    """列出当前可用技能"""
    return skill_registry.list_skills()

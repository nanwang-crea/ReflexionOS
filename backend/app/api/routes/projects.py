
from fastapi import APIRouter, HTTPException

from app.models.project import Project, ProjectCreate
from app.services.project_service import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    """创建项目"""
    return project_service.create_project(project)


@router.get("/", response_model=list[Project])
async def list_projects():
    """获取项目列表"""
    return project_service.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    """获取项目详情"""
    project = project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """删除项目"""
    if not project_service.delete_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"message": "项目已删除"}


@router.get("/{project_id}/structure")
async def get_project_structure(project_id: str):
    """获取项目结构"""
    structure = project_service.get_project_structure(project_id)
    if not structure:
        raise HTTPException(status_code=404, detail="项目不存在或路径无效")
    return structure

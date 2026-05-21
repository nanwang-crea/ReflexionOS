from fastapi import APIRouter

from app.errors import NotFoundError
from app.models.project import Project, ProjectCreate
from app.services.project_service import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    return project_service.create_project(project)


@router.get("/", response_model=list[Project])
async def list_projects():
    return project_service.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    project = project_service.get_project(project_id)
    if not project:
        raise NotFoundError(resource="项目", resource_id=project_id)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    if not project_service.delete_project(project_id):
        raise NotFoundError(resource="项目", resource_id=project_id)
    return {"message": "项目已删除"}


@router.get("/{project_id}/structure")
async def get_project_structure(project_id: str):
    structure = project_service.get_project_structure(project_id)
    if not structure:
        raise NotFoundError(resource="项目", resource_id=project_id, message="项目不存在或路径无效")
    return structure

from fastapi import APIRouter

from app.errors import value_error_to_app_error
from app.models.project import Project, ProjectCreate
from app.services.project_service import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    return project_service.create_project(project)


@router.get("/", response_model=list[Project])
async def list_projects():
    return project_service.list_projects()


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    try:
        project_service.delete_project_or_raise(project_id)
        return {"message": "项目已删除"}
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

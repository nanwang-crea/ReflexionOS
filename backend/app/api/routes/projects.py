"""
projects — 项目（Project）的增删查 API 路由。

提供创建项目、列出所有项目、删除项目的接口，实际业务逻辑委托给 project_service。
"""

from fastapi import APIRouter

from app.errors import value_error_to_app_error
from app.models.project import Project, ProjectCreate
from app.services.project_service import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    """
    POST /api/projects/：创建一个新项目。

    入参（Body）：project - ProjectCreate，包含 name、path、language、config
    运行逻辑：直接调用 project_service.create_project 完成创建
    出参：Project - 创建后的项目对象（含自动生成的 id、created_at、updated_at）
    """
    return project_service.create_project(project)


@router.get("/", response_model=list[Project])
async def list_projects():
    """
    GET /api/projects/：获取所有项目列表。

    入参：无
    运行逻辑：调用 project_service.list_projects 读取全部项目
    出参：list[Project] - 项目对象列表
    """
    return project_service.list_projects()


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """
    DELETE /api/projects/{project_id}：删除指定项目。

    入参（Path）：project_id - 待删除的项目 ID
    运行逻辑：调用 project_service.delete_project_or_raise 执行删除；
        项目不存在时抛出的 ValueError 会转换为标准的 AppError（404 类）
    出参：dict - 删除成功时返回 {"message": "项目已删除"}
    """
    try:
        project_service.delete_project_or_raise(project_id)
        return {"message": "项目已删除"}
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

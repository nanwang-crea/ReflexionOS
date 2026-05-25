from fastapi import APIRouter, Query

from app.errors import value_error_to_app_error
from app.models.file_content import (
    FileContentResponse,
    FileDiffContentResponse,
    FileWriteRequest,
    FileWriteResponse,
)
from app.models.file_tree import FileTreeResponse
from app.services.file_content_service import file_content_service

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/content", response_model=FileContentResponse)
async def get_file_content(
    project_id: str = Query(..., description="项目 ID"),
    path: str = Query(..., description="文件路径"),
):
    try:
        return await file_content_service.get_file_content(project_id, path)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/diff-content", response_model=FileDiffContentResponse)
async def get_diff_content(
    project_id: str = Query(..., description="项目 ID"),
    path: str = Query(..., description="文件路径"),
):
    try:
        return await file_content_service.get_diff_content(project_id, path)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/tree", response_model=FileTreeResponse)
async def get_file_tree(
    project_id: str = Query(..., description="项目 ID"),
):
    try:
        return await file_content_service.get_file_tree(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/write", response_model=FileWriteResponse)
async def write_file_content(request: FileWriteRequest):
    try:
        return await file_content_service.write_file_content(
            request.project_id, request.path, request.content
        )
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

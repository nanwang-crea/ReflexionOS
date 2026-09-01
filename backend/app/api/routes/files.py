"""
files — 项目文件读写相关的 API 路由。

提供文件内容查看、diff 内容查看、文件树查询、文件内容写入等接口，
均基于 project_id 定位项目，实际读写逻辑委托给 file_content_service。
"""

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
    """
    GET /api/files/content：获取指定项目下某个文件的当前内容。

    入参（Query）：project_id - 项目 ID；path - 文件相对路径
    运行逻辑：调用 file_content_service.get_file_content 读取文件；
        项目不存在等场景抛出的 ValueError 会转换为标准的 404 类 AppError
    出参：FileContentResponse - 包含文件内容、语言类型、是否存在
    """
    try:
        return await file_content_service.get_file_content(project_id, path)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/diff-content", response_model=FileDiffContentResponse)
async def get_diff_content(
    project_id: str = Query(..., description="项目 ID"),
    path: str = Query(..., description="文件路径"),
):
    """
    GET /api/files/diff-content：获取指定文件的原始内容与修改后内容，用于前端 diff 展示。

    入参（Query）：project_id - 项目 ID；path - 文件相对路径
    运行逻辑：调用 file_content_service.get_diff_content 获取原始/修改后内容；
        ValueError 转换为标准 AppError
    出参：FileDiffContentResponse - 包含 original、modified、language
    """
    try:
        return await file_content_service.get_diff_content(project_id, path)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/tree", response_model=FileTreeResponse)
async def get_file_tree(
    project_id: str = Query(..., description="项目 ID"),
):
    """
    GET /api/files/tree：获取指定项目的文件目录树。

    入参（Query）：project_id - 项目 ID
    运行逻辑：调用 file_content_service.get_file_tree 构建目录树；
        ValueError 转换为标准 AppError
    出参：FileTreeResponse - 项目的文件树结构
    """
    try:
        return await file_content_service.get_file_tree(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/write", response_model=FileWriteResponse)
async def write_file_content(request: FileWriteRequest):
    """
    POST /api/files/write：将内容写入指定项目下的文件。

    入参（Body）：request - FileWriteRequest，包含 project_id、path、content
    运行逻辑：调用 file_content_service.write_file_content 执行写入；
        ValueError 转换为标准 AppError
    出参：FileWriteResponse - 包含 success 标志和可能的 error 信息
    """
    try:
        return await file_content_service.write_file_content(
            request.project_id, request.path, request.content
        )
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

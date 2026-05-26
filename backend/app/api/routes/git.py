from fastapi import APIRouter

from app.errors import value_error_to_app_error
from app.models.git import (
    GitBranchCreateRequest,
    GitBranchDeleteRequest,
    GitBranchListResponse,
    GitBranchSwitchRequest,
    GitCommitRequest,
    GitDiscardRequest,
    GitLogRequest,
    GitLogResponse,
    GitProjectRequest,
    GitSimpleResponse,
    GitStageRequest,
    GitStashRequest,
    GitStatusResponse,
    GitUnstageRequest,
)
from app.services.git_service import git_service

router = APIRouter(prefix="/api/git", tags=["git"])


@router.get("/status", response_model=GitStatusResponse)
async def get_git_status(project_id: str):
    try:
        return await git_service.get_status(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/stage", response_model=GitSimpleResponse)
async def stage_files(request: GitStageRequest):
    try:
        return await git_service.stage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/stage-all", response_model=GitSimpleResponse)
async def stage_all(request: GitProjectRequest):
    try:
        return await git_service.stage_all(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/unstage", response_model=GitSimpleResponse)
async def unstage_files(request: GitUnstageRequest):
    try:
        return await git_service.unstage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/unstage-all", response_model=GitSimpleResponse)
async def unstage_all(request: GitProjectRequest):
    try:
        return await git_service.unstage_all(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/commit", response_model=GitSimpleResponse)
async def commit(request: GitCommitRequest):
    try:
        return await git_service.commit(request.project_id, request.message, request.amend)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/push", response_model=GitSimpleResponse)
async def push(request: GitProjectRequest):
    return await git_service.push(request.project_id)


@router.post("/pull", response_model=GitSimpleResponse)
async def pull(request: GitProjectRequest):
    return await git_service.pull(request.project_id)


@router.post("/fetch", response_model=GitSimpleResponse)
async def fetch(request: GitProjectRequest):
    return await git_service.fetch(request.project_id)


@router.post("/stash", response_model=GitSimpleResponse)
async def stash(request: GitStashRequest):
    return await git_service.stash(request.project_id, request.action)


@router.post("/discard", response_model=GitSimpleResponse)
async def discard_changes(request: GitDiscardRequest):
    try:
        return await git_service.discard_changes(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/discard-all", response_model=GitSimpleResponse)
async def discard_all(request: GitProjectRequest):
    try:
        return await git_service.discard_all(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/branches", response_model=GitBranchListResponse)
async def list_branches(project_id: str):
    try:
        return await git_service.list_branches(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/branch/create", response_model=GitSimpleResponse)
async def create_branch(request: GitBranchCreateRequest):
    try:
        return await git_service.create_branch(request.project_id, request.name, request.checkout)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/branch/delete", response_model=GitSimpleResponse)
async def delete_branch(request: GitBranchDeleteRequest):
    try:
        return await git_service.delete_branch(request.project_id, request.name, request.force)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/branch/switch", response_model=GitSimpleResponse)
async def switch_branch(request: GitBranchSwitchRequest):
    try:
        return await git_service.switch_branch(request.project_id, request.name)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/log", response_model=GitLogResponse)
async def git_log(request: GitLogRequest):
    try:
        return await git_service.log(request.project_id, request.max_count)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

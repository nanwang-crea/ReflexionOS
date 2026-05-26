from fastapi import APIRouter

from app.errors import value_error_to_app_error
from app.models.git import (
    GitCommitRequest,
    GitDiscardRequest,
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


@router.post("/unstage", response_model=GitSimpleResponse)
async def unstage_files(request: GitUnstageRequest):
    try:
        return await git_service.unstage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/commit", response_model=GitSimpleResponse)
async def commit(request: GitCommitRequest):
    try:
        return await git_service.commit(request.project_id, request.message)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/push", response_model=GitSimpleResponse)
async def push(request: GitProjectRequest):
    return await git_service.push(request.project_id)


@router.post("/pull", response_model=GitSimpleResponse)
async def pull(request: GitProjectRequest):
    return await git_service.pull(request.project_id)


@router.post("/stash", response_model=GitSimpleResponse)
async def stash(request: GitStashRequest):
    return await git_service.stash(request.project_id, request.action)


@router.post("/discard", response_model=GitSimpleResponse)
async def discard_changes(request: GitDiscardRequest):
    try:
        return await git_service.discard_changes(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

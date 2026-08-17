# 文件功能：Git 操作相关的 API 路由
# 文件描述：封装项目的 Git 常用操作（状态查询、暂存/取消暂存、提交、推拉、
#           stash、丢弃改动、分支管理、提交日志），供前端调用；
#           实际 Git 命令执行委托给 git_service。
# 核心逻辑：每个路由都是对 git_service 对应方法的薄包装，统一捕获
#           ValueError 并转换为标准的应用层错误（资源标记为"项目"）。
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
    """
    GET /api/git/status：查询项目当前 Git 状态。
    入参：project_id（查询参数，项目 ID）。
    逻辑：调用 git_service.get_status 获取工作区/暂存区变更情况。
    出参：GitStatusResponse（Git 状态信息）；project_id 不存在时抛出 404 类错误。
    """
    try:
        return await git_service.get_status(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/stage", response_model=GitSimpleResponse)
async def stage_files(request: GitStageRequest):
    """
    POST /api/git/stage：将指定文件加入暂存区。
    入参：request（含 project_id 和待暂存的文件路径列表 paths）。
    逻辑：调用 git_service.stage_files 执行 git add。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.stage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/stage-all", response_model=GitSimpleResponse)
async def stage_all(request: GitProjectRequest):
    """
    POST /api/git/stage-all：将当前项目所有变更文件加入暂存区。
    入参：request（含 project_id）。
    逻辑：调用 git_service.stage_all 执行全量 git add。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.stage_all(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/unstage", response_model=GitSimpleResponse)
async def unstage_files(request: GitUnstageRequest):
    """
    POST /api/git/unstage：将指定文件移出暂存区。
    入参：request（含 project_id 和待取消暂存的文件路径列表 paths）。
    逻辑：调用 git_service.unstage_files 执行 git restore --staged。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.unstage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/unstage-all", response_model=GitSimpleResponse)
async def unstage_all(request: GitProjectRequest):
    """
    POST /api/git/unstage-all：取消所有文件的暂存状态。
    入参：request（含 project_id）。
    逻辑：调用 git_service.unstage_all 执行全量取消暂存。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.unstage_all(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/commit", response_model=GitSimpleResponse)
async def commit(request: GitCommitRequest):
    """
    POST /api/git/commit：提交暂存区改动。
    入参：request（含 project_id、提交信息 message、是否 amend 修改上次提交 amend）。
    逻辑：调用 git_service.commit 执行 git commit。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.commit(request.project_id, request.message, request.amend)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/push", response_model=GitSimpleResponse)
async def push(request: GitProjectRequest):
    """
    POST /api/git/push：推送本地提交到远程仓库。
    入参：request（含 project_id）。
    逻辑：调用 git_service.push 执行 git push。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.push(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/pull", response_model=GitSimpleResponse)
async def pull(request: GitProjectRequest):
    """
    POST /api/git/pull：从远程仓库拉取并合并最新改动。
    入参：request（含 project_id）。
    逻辑：调用 git_service.pull 执行 git pull。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.pull(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/fetch", response_model=GitSimpleResponse)
async def fetch(request: GitProjectRequest):
    """
    POST /api/git/fetch：从远程仓库拉取更新但不合并。
    入参：request（含 project_id）。
    逻辑：调用 git_service.fetch 执行 git fetch。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.fetch(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/stash", response_model=GitSimpleResponse)
async def stash(request: GitStashRequest):
    """
    POST /api/git/stash：执行 stash 相关操作（保存/弹出等，由 action 指定）。
    入参：request（含 project_id 和操作类型 action）。
    逻辑：调用 git_service.stash 执行对应的 git stash 子命令。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.stash(request.project_id, request.action)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/discard", response_model=GitSimpleResponse)
async def discard_changes(request: GitDiscardRequest):
    """
    POST /api/git/discard：丢弃指定文件的未提交改动。
    入参：request（含 project_id 和待丢弃改动的文件路径列表 paths）。
    逻辑：调用 git_service.discard_changes 执行 git checkout/restore。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.discard_changes(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/discard-all", response_model=GitSimpleResponse)
async def discard_all(request: GitProjectRequest):
    """
    POST /api/git/discard-all：丢弃所有未提交的改动。
    入参：request（含 project_id）。
    逻辑：调用 git_service.discard_all 执行全量丢弃改动。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.discard_all(request.project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/branches", response_model=GitBranchListResponse)
async def list_branches(project_id: str):
    """
    GET /api/git/branches：列出项目的所有分支。
    入参：project_id（查询参数，项目 ID）。
    逻辑：调用 git_service.list_branches 获取分支列表。
    出参：GitBranchListResponse（分支列表信息）。
    """
    try:
        return await git_service.list_branches(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/branch/create", response_model=GitSimpleResponse)
async def create_branch(request: GitBranchCreateRequest):
    """
    POST /api/git/branch/create：创建新分支。
    入参：request（含 project_id、分支名 name、创建后是否切换 checkout）。
    逻辑：调用 git_service.create_branch 创建分支，按需切换。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.create_branch(request.project_id, request.name, request.checkout)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/branch/delete", response_model=GitSimpleResponse)
async def delete_branch(request: GitBranchDeleteRequest):
    """
    POST /api/git/branch/delete：删除分支。
    入参：request（含 project_id、分支名 name、是否强制删除 force）。
    逻辑：调用 git_service.delete_branch 执行分支删除。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.delete_branch(request.project_id, request.name, request.force)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/branch/switch", response_model=GitSimpleResponse)
async def switch_branch(request: GitBranchSwitchRequest):
    """
    POST /api/git/branch/switch：切换到指定分支。
    入参：request（含 project_id、目标分支名 name）。
    逻辑：调用 git_service.switch_branch 执行 git checkout/switch。
    出参：GitSimpleResponse（操作结果）。
    """
    try:
        return await git_service.switch_branch(request.project_id, request.name)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/log", response_model=GitLogResponse)
async def git_log(request: GitLogRequest):
    """
    POST /api/git/log：查询提交历史记录。
    入参：request（含 project_id、返回的最大提交条数 max_count）。
    逻辑：调用 git_service.log 获取提交日志列表。
    出参：GitLogResponse（提交日志列表）。
    """
    try:
        return await git_service.log(request.project_id, request.max_count)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc

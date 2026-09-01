# Git 操作相关的请求/响应模型：涵盖状态查询、暂存/取消暂存、提交、分支管理、
# 贮藏（stash）、丢弃变更、提交历史等 Git 面板功能所需的数据结构。
from pydantic import BaseModel


class GitFileChange(BaseModel):
    """单个文件的变更信息：路径、变更状态（如 M/A/D 等），以及可选的增删行数统计。"""

    path: str
    status: str
    insertions: int | None = None
    deletions: int | None = None


class GitStatusResponse(BaseModel):
    """Git 仓库状态：当前分支、领先/落后远程的提交数，以及已暂存/未暂存/未跟踪的文件变更列表。"""

    branch: str
    ahead: int
    behind: int
    staged: list[GitFileChange]
    unstaged: list[GitFileChange]
    untracked: list[GitFileChange]


class GitStageRequest(BaseModel):
    """暂存文件请求：指定项目及要暂存（git add）的文件路径列表。"""

    project_id: str
    paths: list[str]


class GitUnstageRequest(BaseModel):
    """取消暂存请求：指定项目及要取消暂存（git reset）的文件路径列表。"""

    project_id: str
    paths: list[str]


class GitCommitRequest(BaseModel):
    """提交请求：项目、提交信息，以及是否为修订上一次提交（amend）。"""

    project_id: str
    message: str
    amend: bool = False


class GitProjectRequest(BaseModel):
    """仅需项目标识的通用 Git 请求（如拉取/推送等无额外参数的操作）。"""

    project_id: str


class GitStashRequest(BaseModel):
    """贮藏操作请求：action 指定具体动作（如 push/pop 等），默认为贮藏当前变更。"""

    project_id: str
    action: str = "push"


class GitDiscardRequest(BaseModel):
    """丢弃变更请求：指定项目及要放弃修改（还原为最近提交状态）的文件路径列表。"""

    project_id: str
    paths: list[str]


class GitSimpleResponse(BaseModel):
    """通用的简单操作结果响应：是否成功，失败时附带错误信息。"""

    success: bool
    error: str | None = None


class GitBranchItem(BaseModel):
    """单个分支信息：名称、是否为当前所在分支、是否为远程分支。"""

    name: str
    is_current: bool
    is_remote: bool


class GitBranchListResponse(BaseModel):
    """分支列表响应：所有分支及当前所在分支名称。"""

    branches: list[GitBranchItem]
    current: str


class GitBranchCreateRequest(BaseModel):
    """创建分支请求：分支名称，checkout 指定创建后是否立即切换到该分支。"""

    project_id: str
    name: str
    checkout: bool = True


class GitBranchDeleteRequest(BaseModel):
    """删除分支请求：force 指定是否强制删除（忽略未合并的变更）。"""

    project_id: str
    name: str
    force: bool = False


class GitBranchSwitchRequest(BaseModel):
    """切换分支请求：切换到指定名称的分支。"""

    project_id: str
    name: str


class GitLogCommit(BaseModel):
    """单条提交记录：完整哈希、短哈希、作者、提交日期、提交信息。"""

    hash: str
    short_hash: str
    author: str
    date: str
    message: str


class GitLogResponse(BaseModel):
    """提交历史查询响应：提交记录列表。"""

    commits: list[GitLogCommit]


class GitLogRequest(BaseModel):
    """提交历史查询请求：max_count 限制返回的最大提交条数。"""

    project_id: str
    max_count: int = 50

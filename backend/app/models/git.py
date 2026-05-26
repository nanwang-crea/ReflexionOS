from pydantic import BaseModel


class GitFileChange(BaseModel):
    path: str
    status: str
    insertions: int | None = None
    deletions: int | None = None


class GitStatusResponse(BaseModel):
    branch: str
    ahead: int
    behind: int
    staged: list[GitFileChange]
    unstaged: list[GitFileChange]
    untracked: list[GitFileChange]


class GitStageRequest(BaseModel):
    project_id: str
    paths: list[str]


class GitUnstageRequest(BaseModel):
    project_id: str
    paths: list[str]


class GitCommitRequest(BaseModel):
    project_id: str
    message: str
    amend: bool = False


class GitProjectRequest(BaseModel):
    project_id: str


class GitStashRequest(BaseModel):
    project_id: str
    action: str = "push"


class GitDiscardRequest(BaseModel):
    project_id: str
    paths: list[str]


class GitSimpleResponse(BaseModel):
    success: bool
    error: str | None = None


class GitBranchItem(BaseModel):
    name: str
    is_current: bool
    is_remote: bool


class GitBranchListResponse(BaseModel):
    branches: list[GitBranchItem]
    current: str


class GitBranchCreateRequest(BaseModel):
    project_id: str
    name: str
    checkout: bool = True


class GitBranchDeleteRequest(BaseModel):
    project_id: str
    name: str
    force: bool = False


class GitBranchSwitchRequest(BaseModel):
    project_id: str
    name: str


class GitLogCommit(BaseModel):
    hash: str
    short_hash: str
    author: str
    date: str
    message: str


class GitLogResponse(BaseModel):
    commits: list[GitLogCommit]


class GitLogRequest(BaseModel):
    project_id: str
    max_count: int = 50

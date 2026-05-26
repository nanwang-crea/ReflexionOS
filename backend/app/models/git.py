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

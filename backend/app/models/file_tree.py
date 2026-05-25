from pydantic import BaseModel


class FileTreeNode(BaseModel):
    name: str
    type: str
    path: str
    git_status: str | None = None
    children: list["FileTreeNode"] | None = None


class FileTreeResponse(BaseModel):
    tree: list[FileTreeNode]

# 项目文件树相关的数据模型：用于前端文件浏览器展示项目目录结构及各文件的 Git 状态。
from pydantic import BaseModel


class FileTreeNode(BaseModel):
    """文件树节点：可以是文件或目录（type 区分），目录节点通过 children 递归嵌套子节点。"""

    name: str
    type: str  # "file" 或 "dir"
    path: str
    git_status: str | None = None  # 该文件的 Git 状态（如新增/修改/未跟踪），非 Git 项目或无变更时为 None
    children: list["FileTreeNode"] | None = None  # 仅目录节点使用，文件节点为 None


class FileTreeResponse(BaseModel):
    """文件树查询接口的响应：顶层节点列表。"""

    tree: list[FileTreeNode]

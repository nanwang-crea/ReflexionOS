# 文件内容读写相关的请求/响应模型：用于前端读取单个文件内容、对比 diff、以及写入文件内容的接口。
from pydantic import BaseModel


class FileContentResponse(BaseModel):
    """单个文件内容的响应：文件文本内容、用于前端语法高亮的语言类型、文件是否存在。"""

    content: str
    language: str
    exists: bool


class FileDiffContentResponse(BaseModel):
    """文件差异对比内容：原始版本与修改后版本的文本，供前端渲染 diff 视图。"""

    original: str
    modified: str
    language: str


class FileWriteRequest(BaseModel):
    """写入文件内容的请求：指定所属项目、文件路径（相对项目根目录）及要写入的内容。"""

    project_id: str
    path: str
    content: str


class FileWriteResponse(BaseModel):
    """写入文件的结果：是否成功，失败时附带错误信息。"""

    success: bool
    error: str | None = None

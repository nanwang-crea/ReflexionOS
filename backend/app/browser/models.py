"""
BrowserActionResult — 浏览器操作统一返回模型。

所有 BrowserManager 的公开方法都返回此模型，提供统一的结果结构。
被 BrowserTool.execute() 转换为 ToolResult 返回给 Agent 执行循环。

依赖：pydantic
"""

from typing import Any

from pydantic import BaseModel, Field


class BrowserActionResult(BaseModel):
    """浏览器操作结果。

    属性：
        success: 操作是否成功
        action: 操作名称（如 navigate、click、screenshot）
        message: 成功时的描述信息
        data: 附加数据（如截图路径、页面标题、JS 执行结果等）
        error: 失败时的错误信息
    """

    success: bool
    action: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

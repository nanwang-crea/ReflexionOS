"""
browser_screenshot — 浏览器截图 API 端点。

提供 GET /api/browser/screenshot 接口，返回浏览器截图的 PNG 图片。
被前端 ActionReceipt 组件通过 <img> 标签请求渲染截图。

安全设计：
    - 路径遍历防护：通过 Path.resolve() + 白名单目录前缀校验
    - 只允许访问 {tempdir}/browser-screenshots/ 目录下的文件

依赖：fastapi, pathlib, tempfile
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/browser", tags=["browser"])

# 截图文件的合法根目录，所有截图都在此目录的子目录中
SCREENSHOT_BASE = Path(tempfile.gettempdir()) / "browser-screenshots"


@router.get("/screenshot")
async def get_screenshot(path: str = Query(..., description="Path to screenshot file")):
    """返回浏览器截图 PNG 图片。

    入参（Query）：
        path: 截图文件的绝对路径

    执行逻辑：
        1. 将传入路径规范化为绝对路径（Path.resolve），消除 ../ 遍历
        2. 校验路径是否在合法截图目录白名单内
        3. 校验文件是否存在
        4. 返回 FileResponse（PNG 图片流）

    出参：
        FileResponse: PNG 图片

    异常：
        403: 路径在合法目录之外（路径遍历攻击）
        404: 文件不存在
    """
    real_path = Path(path).resolve()
    screenshot_base_real = SCREENSHOT_BASE.resolve()

    # 路径遍历防护：必须在合法截图目录内
    if not str(real_path).startswith(str(screenshot_base_real)):
        raise HTTPException(status_code=403, detail="Path outside allowed directory")

    if not real_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(real_path, media_type="image/png")

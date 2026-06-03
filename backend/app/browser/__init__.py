"""
app.browser — 浏览器自动化模块。

提供 Playwright 浏览器生命周期管理和安全配置。
被 BrowserTool 通过 BrowserManager 控制浏览器。

导出：
    BrowserSecurityConfig: 安全策略配置
    BrowserManager: 浏览器管理器（惰性导入）
    BrowserActionResult: 操作结果模型
"""

from app.browser.config import BrowserSecurityConfig
from app.browser.models import BrowserActionResult

# BrowserManager 使用惰性导入，因为模块可能尚未完全初始化
try:
    from app.browser.manager import BrowserManager
except ImportError:
    BrowserManager = None  # type: ignore[assignment,misc]

__all__ = [
    "BrowserSecurityConfig",
    "BrowserManager",
    "BrowserActionResult",
]

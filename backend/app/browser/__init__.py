from app.browser.config import BrowserSecurityConfig
from app.browser.models import BrowserActionResult

# BrowserManager will be available after Task 2
try:
    from app.browser.manager import BrowserManager
except ImportError:
    BrowserManager = None  # type: ignore[assignment,misc]

__all__ = [
    "BrowserSecurityConfig",
    "BrowserManager",
    "BrowserActionResult",
]

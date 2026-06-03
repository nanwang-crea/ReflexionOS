# Browser Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 ReflexionOS Agent 增加一个 `browser` 工具，基于 Playwright 实现完整的浏览器自动化能力（导航、点击、填写、截图、JS 执行等 13 个 action）。

**Architecture:** 单工具 + Action 分发模式。BrowserTool（BaseTool 子类）内部持有 BrowserManager，管理 Playwright 生命周期。扁平化 Schema 避免 LLM 兼容问题。截图存为临时文件，通过后端 API 渲染。并发安全由 asyncio.Lock 保障。

**Tech Stack:** Python 3.12, Playwright, FastAPI, React, TypeScript, Zustand

**Design Spec:** `docs/superpowers/specs/2026-06-01-browser-tool-design.md`

---

## File Structure

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/browser/__init__.py` | 包导出 |
| `backend/app/browser/config.py` | BrowserSecurityConfig + BrowserRunConfig 模型 |
| `backend/app/browser/models.py` | BrowserActionResult 等数据模型 |
| `backend/app/browser/manager.py` | BrowserManager — Playwright 生命周期管理 |
| `backend/app/tools/browser_tool.py` | BrowserTool (BaseTool 子类 + 13 action 分发) |
| `backend/app/api/routes/browser_screenshot.py` | 截图 API 端点 |
| `backend/tests/test_tools/test_browser_tool.py` | BrowserTool 单元测试 |
| `backend/tests/test_browser/__init__.py` | 测试包 |
| `backend/tests/test_browser/test_browser_manager.py` | BrowserManager 单元测试 |
| `backend/tests/test_browser/test_browser_integration.py` | 集成测试 |
| `backend/tests/test_browser/fixtures/test_page.html` | 集成测试用静态 HTML |
| `frontend/src/pages/settings/BrowserPanel.tsx` | 浏览器配置面板组件 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/requirements.txt` | 新增 `playwright>=1.40.0` |
| `backend/app/config/settings.py` | 新增 `BrowserSettings` 模型，嵌入 `AppSettings` |
| `backend/app/services/agent_service.py:114-147` | `_build_run_tool_registry()` 注册 BrowserTool |
| `backend/app/api/routes/ui_settings.py` | UISettings 响应包含 browser 配置 |
| `frontend/src/pages/SettingsPage.tsx` | 新增 "浏览器" tab |
| `frontend/src/components/execution/ActionReceipt.tsx` | 截图渲染逻辑 |

---

### Task 1: 数据模型与配置

**Files:**
- Create: `backend/app/browser/__init__.py`
- Create: `backend/app/browser/config.py`
- Create: `backend/app/browser/models.py`
- Modify: `backend/app/config/settings.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加 playwright 依赖**

在 `backend/requirements.txt` 末尾添加：

```
playwright>=1.40.0
```

- [ ] **Step 2: 创建 browser 包**

`backend/app/browser/__init__.py`:

```python
from app.browser.config import BrowserSecurityConfig, BrowserRunConfig
from app.browser.manager import BrowserManager
from app.browser.models import BrowserActionResult

__all__ = [
    "BrowserSecurityConfig",
    "BrowserRunConfig",
    "BrowserManager",
    "BrowserActionResult",
]
```

- [ ] **Step 3: 创建配置模型**

`backend/app/browser/config.py`:

```python
from pydantic import BaseModel, Field


class BrowserSecurityConfig(BaseModel):
    blocked_url_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns for URLs to block",
    )
    block_private_ips: bool = Field(
        default=False,
        description="Block access to private/reserved IP ranges",
    )
    allowed_schemes: list[str] = Field(
        default_factory=lambda: ["http", "https"],
        description="Allowed URL schemes",
    )
    max_navigation_depth: int = Field(
        default=10,
        description="Max consecutive navigations to prevent redirect loops",
    )


class BrowserRunConfig(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    browser_engine: str = Field(
        default="chromium",
        description="Browser engine: chromium, firefox, or webkit",
    )
    default_timeout: int = Field(
        default=30000,
        description="Default navigation/wait timeout in milliseconds",
    )
    default_wait_until: str = Field(
        default="load",
        description="Default wait_until for navigation: load, domcontentloaded, networkidle",
    )
    security: BrowserSecurityConfig = Field(default_factory=BrowserSecurityConfig)
```

- [ ] **Step 4: 创建数据模型**

`backend/app/browser/models.py`:

```python
from pydantic import BaseModel, Field


class BrowserActionResult(BaseModel):
    success: bool
    action: str
    message: str = ""
    data: dict = Field(default_factory=dict)
    error: str | None = None
```

- [ ] **Step 5: 在 AppSettings 中嵌入 BrowserSettings**

修改 `backend/app/config/settings.py`，在 `UISettings` 之后添加 `BrowserSettings`：

```python
class BrowserSettings(BaseModel):
    headless: bool = True
    default_browser: str = "chromium"
    default_timeout: int = 30000
    default_wait_until: str = "load"
    block_private_ips: bool = False
    blocked_url_patterns: list[str] = Field(default_factory=list)
```

然后在 `AppSettings` 类中添加 `browser: BrowserSettings = Field(default_factory=BrowserSettings)`。

同时在 `ConfigManager` 中添加 `update_browser()` 方法：

```python
def update_browser(self, browser_settings: BrowserSettings) -> None:
    self.settings.browser = browser_settings
    self.save()
```

- [ ] **Step 6: 运行测试确认无破坏**

```bash
cd backend && python -m pytest tests/ -x -q
```

Expected: 所有现有测试通过

- [ ] **Step 7: 提交**

```bash
git add backend/app/browser/ backend/app/config/settings.py backend/requirements.txt
git commit -m "feat(browser): add data models, config, and playwright dependency"
```

---

### Task 2: BrowserManager 核心实现

**Files:**
- Create: `backend/app/browser/manager.py`

- [ ] **Step 1: 编写 BrowserManager 骨架**

`backend/app/browser/manager.py`:

```python
from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.browser.config import BrowserRunConfig

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages a Playwright browser instance with lifecycle, concurrency, and security."""

    def __init__(self, config: BrowserRunConfig | None = None):
        self._config = config or BrowserRunConfig()
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._pages: dict[str, Any] = {}
        self._active_page_id: str | None = None
        self._lock = asyncio.Lock()
        self._screenshot_dir: Path | None = None
        self._navigation_depth: int = 0
        self._started: bool = False

    @property
    def is_running(self) -> bool:
        return self._started and self._browser is not None and self._browser.is_connected()

    def _new_tab_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def _ensure_screenshot_dir(self) -> Path:
        if self._screenshot_dir is None:
            run_id = uuid.uuid4().hex[:8]
            self._screenshot_dir = Path(tempfile.gettempdir()) / "browser-screenshots" / f"run-{run_id}"
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        return self._screenshot_dir

    async def start(self, headless: bool | None = None, browser_engine: str | None = None) -> str:
        async with self._lock:
            return await self._start_locked(headless, browser_engine)

    async def _start_locked(self, headless: bool | None, browser_engine: str | None) -> str:
        raise NotImplementedError("Step 2 will implement this")

    async def navigate(self, url: str, wait_until: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def click(self, selector: str | None = None, text: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def fill(self, selector: str, value: str) -> dict[str, Any]:
        raise NotImplementedError

    async def select(self, selector: str, value: str) -> dict[str, Any]:
        raise NotImplementedError

    async def screenshot(self, selector: str | None = None, full_page: bool = False) -> dict[str, Any]:
        raise NotImplementedError

    async def read(self, selector: str | None = None, fmt: str = "text") -> dict[str, Any]:
        raise NotImplementedError

    async def wait_for(self, selector: str, timeout: int | None = None, state: str = "visible") -> dict[str, Any]:
        raise NotImplementedError

    async def execute_js(self, script: str) -> dict[str, Any]:
        raise NotImplementedError

    async def new_tab(self, url: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def switch_tab(self, tab_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def close_tab(self, tab_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def _close_locked(self) -> None:
        raise NotImplementedError

    def cleanup_screenshots(self) -> None:
        if self._screenshot_dir and self._screenshot_dir.exists():
            shutil.rmtree(self._screenshot_dir, ignore_errors=True)
            self._screenshot_dir = None

    def _on_disconnected(self) -> None:
        logger.warning("Browser disconnected unexpectedly")
        self._started = False

    @staticmethod
    async def kill_orphan_browsers() -> None:
        logger.info("Scanning for orphan browser processes (placeholder)")
```

- [ ] **Step 2: 实现 start 方法**

替换 `_start_locked`:

```python
async def _start_locked(self, headless: bool | None, browser_engine: str | None) -> str:
    if self.is_running:
        return "Browser already running"

    use_headless = headless if headless is not None else self._config.headless
    engine = browser_engine or self._config.browser_engine

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    self._playwright = await async_playwright().start()

    launcher = getattr(self._playwright, engine, None)
    if launcher is None:
        raise ValueError(f"Unknown browser engine: {engine}. Use chromium, firefox, or webkit")

    self._browser = await launcher.launch(headless=use_headless)
    self._browser.on("disconnected", self._on_disconnected)

    self._context = await self._browser.new_context()
    self._context.on("page", lambda page: asyncio.ensure_future(self._handle_new_page(page)))

    page = await self._context.new_page()
    tab_id = self._new_tab_id()
    self._pages[tab_id] = page
    self._active_page_id = tab_id

    self._started = True
    self._navigation_depth = 0
    return f"Browser started ({engine}, headless={use_headless}), tab: {tab_id}"
```

添加 `_handle_new_page`:

```python
async def _handle_new_page(self, page: Any) -> None:
    """Handle popups/new pages opened by the website."""
    tab_id = self._new_tab_id()
    self._pages[tab_id] = page
    logger.info(f"New tab opened: {tab_id}")
```

- [ ] **Step 3: 实现 close 方法**

替换 `_close_locked`:

```python
async def _close_locked(self) -> None:
    self._started = False
    self._pages.clear()
    self._active_page_id = None

    if self._context:
        try:
            await self._context.close()
        except Exception:
            pass
        self._context = None

    if self._browser:
        try:
            await self._browser.close()
        except Exception:
            pass
        self._browser = None

    if self._playwright:
        try:
            await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    self.cleanup_screenshots()
```

- [ ] **Step 4: 实现 _get_active_page 辅助方法**

```python
def _get_active_page(self) -> Any:
    if not self._active_page_id or self._active_page_id not in self._pages:
        raise RuntimeError("No active page. Call 'launch' first.")
    return self._pages[self._active_page_id]

async def _ensure_browser(self) -> None:
    """Auto-start browser if not running."""
    if not self.is_running:
        await self._start_locked(None, None)
```

- [ ] **Step 5: 实现 navigate**

```python
async def navigate(self, url: str, wait_until: str | None = None) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()

        self._navigation_depth += 1
        if self._navigation_depth > self._config.security.max_navigation_depth:
            return {"success": False, "error": f"Max navigation depth ({self._config.security.max_navigation_depth}) exceeded"}

        wu = wait_until or self._config.default_wait_until
        timeout = self._config.default_timeout

        try:
            response = await page.goto(url, wait_until=wu, timeout=timeout)
            title = await page.title()
            self._navigation_depth = 0  # Reset on successful navigation
            status = response.status if response else "unknown"
            return {
                "success": True,
                "message": f"Navigated to {url} (status={status}) - Title: {title}",
                "data": {"url": url, "title": title, "status": status},
            }
        except Exception as e:
            return {"success": False, "error": f"Navigation failed: {type(e).__name__}: {e}"}
```

- [ ] **Step 6: 实现 click, fill, select**

```python
async def click(self, selector: str | None = None, text: str | None = None) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            if text:
                await page.get_by_text(text, exact=True).click(timeout=self._config.default_timeout)
            elif selector:
                await page.click(selector, timeout=self._config.default_timeout)
            else:
                return {"success": False, "error": "click requires 'selector' or 'text'"}
            return {"success": True, "message": f"Clicked: {selector or text}"}
        except Exception as e:
            return {"success": False, "error": f"Click failed: {type(e).__name__}: {e}"}

async def fill(self, selector: str, value: str) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            await page.fill(selector, value, timeout=self._config.default_timeout)
            return {"success": True, "message": f"Filled '{selector}' with value"}
        except Exception as e:
            return {"success": False, "error": f"Fill failed: {type(e).__name__}: {e}"}

async def select(self, selector: str, value: str) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            await page.select_option(selector, value, timeout=self._config.default_timeout)
            return {"success": True, "message": f"Selected '{value}' in '{selector}'"}
        except Exception as e:
            return {"success": False, "error": f"Select failed: {type(e).__name__}: {e}"}
```

- [ ] **Step 7: 实现 screenshot, read, wait_for**

```python
async def screenshot(self, selector: str | None = None, full_page: bool = False) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            ss_dir = self._ensure_screenshot_dir()
            count = len(list(ss_dir.glob("screenshot-*.png")))
            path = ss_dir / f"screenshot-{count + 1:03d}.png"

            if selector:
                element = page.locator(selector)
                await element.screenshot(path=str(path))
            else:
                await page.screenshot(path=str(path), full_page=full_page)

            from PIL import Image
            img = Image.open(path)
            width, height = img.size
            img.close()

            return {
                "success": True,
                "message": f"Screenshot saved: {path.name} ({width}x{height})",
                "data": {"screenshot_path": str(path), "width": width, "height": height},
            }
        except Exception as e:
            return {"success": False, "error": f"Screenshot failed: {type(e).__name__}: {e}"}

async def read(self, selector: str | None = None, fmt: str = "text") -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            if selector:
                locator = page.locator(selector)
            else:
                locator = page.locator("body")

            if fmt == "html":
                content = await locator.inner_html(timeout=self._config.default_timeout)
            else:
                content = await locator.inner_text(timeout=self._config.default_timeout)

            preview = content[:500] + ("..." if len(content) > 500 else "")
            return {
                "success": True,
                "message": f"Read {len(content)} chars ({fmt})",
                "data": {"content": content, "format": fmt, "length": len(content)},
            }
        except Exception as e:
            return {"success": False, "error": f"Read failed: {type(e).__name__}: {e}"}

async def wait_for(self, selector: str, timeout: int | None = None, state: str = "visible") -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            t = timeout or self._config.default_timeout
            await page.wait_for_selector(selector, state=state, timeout=t)
            return {"success": True, "message": f"Element '{selector}' is now {state}"}
        except Exception as e:
            return {"success": False, "error": f"Wait failed: {type(e).__name__}: {e}"}
```

- [ ] **Step 8: 实现 execute_js**

```python
async def execute_js(self, script: str) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = self._get_active_page()
        try:
            result = await page.evaluate(script)
            script_hash = hashlib.sha256(script.encode()).hexdigest()
            logger.info(f"execute_js hash={script_hash} preview={script[:200]}")
            return {
                "success": True,
                "message": f"JS executed, result: {str(result)[:200]}",
                "data": {"result": result, "script_hash": script_hash},
            }
        except Exception as e:
            return {"success": False, "error": f"JS execution failed: {type(e).__name__}: {e}"}
```

- [ ] **Step 9: 实现 new_tab, switch_tab, close_tab**

```python
async def new_tab(self, url: str | None = None) -> dict[str, Any]:
    async with self._lock:
        await self._ensure_browser()
        page = await self._context.new_page()
        tab_id = self._new_tab_id()
        self._pages[tab_id] = page
        self._active_page_id = tab_id
        if url:
            await page.goto(url, wait_until=self._config.default_wait_until, timeout=self._config.default_timeout)
        return {"success": True, "message": f"New tab created: {tab_id}", "data": {"tab_id": tab_id}}

async def switch_tab(self, tab_id: str) -> dict[str, Any]:
    async with self._lock:
        if tab_id not in self._pages:
            return {"success": False, "error": f"Tab '{tab_id}' not found. Available: {list(self._pages.keys())}"}
        self._active_page_id = tab_id
        return {"success": True, "message": f"Switched to tab: {tab_id}"}

async def close_tab(self, tab_id: str) -> dict[str, Any]:
    async with self._lock:
        if tab_id not in self._pages:
            return {"success": False, "error": f"Tab '{tab_id}' not found"}
        page = self._pages.pop(tab_id)
        try:
            await page.close()
        except Exception:
            pass

        if not self._pages:
            new_page = await self._context.new_page()
            new_id = self._new_tab_id()
            self._pages[new_id] = new_page
            self._active_page_id = new_id
            return {"success": True, "message": f"Tab {tab_id} closed. New blank tab created: {new_id}"}

        if self._active_page_id == tab_id:
            self._active_page_id = next(iter(self._pages))

        return {"success": True, "message": f"Tab {tab_id} closed. Active: {self._active_page_id}"}
```

- [ ] **Step 10: 验证模块可导入**

```bash
cd backend && python -c "from app.browser import BrowserManager, BrowserRunConfig; print('OK')"
```

Expected: `OK`

- [ ] **Step 11: 提交**

```bash
git add backend/app/browser/
git commit -m "feat(browser): implement BrowserManager with full lifecycle"
```

---

### Task 3: BrowserTool 实现

**Files:**
- Create: `backend/app/tools/browser_tool.py`

- [ ] **Step 1: 实现 BrowserTool**

`backend/app/tools/browser_tool.py`:

```python
from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult
from app.browser.manager import BrowserManager
from app.browser.config import BrowserRunConfig

logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):
    VALID_ACTIONS = frozenset({
        "launch", "navigate", "click", "fill", "select",
        "screenshot", "read", "wait", "execute_js",
        "new_tab", "switch_tab", "close_tab", "close",
    })

    def __init__(self, config: BrowserRunConfig | None = None):
        self._config = config or BrowserRunConfig()
        self._manager = BrowserManager(self._config)

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Control a web browser. Actions: launch (start browser), navigate (open URL), "
            "click (click element by selector or text), fill (fill input field), "
            "select (select dropdown option), screenshot (capture image), "
            "read (get text/HTML), wait (wait for element), execute_js (run JavaScript), "
            "new_tab (open new tab), switch_tab (switch to tab), close_tab (close a tab), "
            "close (shut down browser)."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": sorted(self.VALID_ACTIONS),
                        "description": "The browser action to perform",
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to (used by: navigate, new_tab)",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector of the target element (used by: click, fill, select, screenshot, read, wait)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text content to find and click (alternative to selector, used by: click)",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to fill or select (used by: fill, select)",
                    },
                    "script": {
                        "type": "string",
                        "description": "JavaScript code to execute. Use 'return' to return a value. (used by: execute_js)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "html"],
                        "description": "Content format to return (used by: read, default: text)",
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "When navigation is complete (used by: navigate, default: load)",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["visible", "hidden", "attached", "detached"],
                        "description": "State to wait for (used by: wait, default: visible)",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in milliseconds (used by: wait, navigate)",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page (used by: screenshot, default: false)",
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Run in headless mode (used by: launch, default: true)",
                    },
                    "browser": {
                        "type": "string",
                        "enum": ["chromium", "firefox", "webkit"],
                        "description": "Browser engine (used by: launch, default: chromium)",
                    },
                    "tab_id": {
                        "type": "string",
                        "description": "Tab ID to switch to or close (used by: switch_tab, close_tab)",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action")
        if not action:
            return ToolResult(success=False, error="Missing required parameter: 'action'")
        if action not in self.VALID_ACTIONS:
            return ToolResult(success=False, error=f"Unknown action: '{action}'. Valid: {sorted(self.VALID_ACTIONS)}")

        try:
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                return ToolResult(success=False, error=f"Handler not implemented: {action}")
            result = await handler(args)
            return ToolResult(
                success=result.get("success", False),
                output=result.get("message"),
                error=result.get("error"),
                data=result.get("data"),
            )
        except Exception as e:
            logger.exception(f"Browser action '{action}' failed")
            return ToolResult(success=False, error=f"Browser error: {type(e).__name__}: {e}")

    async def _action_launch(self, args: dict[str, Any]) -> dict[str, Any]:
        headless = args.get("headless")
        engine = args.get("browser")
        return await self._manager.start(headless=headless, browser_engine=engine)

    async def _action_navigate(self, args: dict[str, Any]) -> dict[str, Any]:
        url = args.get("url")
        if not url:
            return {"success": False, "error": "navigate requires 'url'"}
        return await self._manager.navigate(url, wait_until=args.get("wait_until"))

    async def _action_click(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._manager.click(selector=args.get("selector"), text=args.get("text"))

    async def _action_fill(self, args: dict[str, Any]) -> dict[str, Any]:
        selector = args.get("selector")
        value = args.get("value")
        if not selector or value is None:
            return {"success": False, "error": "fill requires 'selector' and 'value'"}
        return await self._manager.fill(selector, value)

    async def _action_select(self, args: dict[str, Any]) -> dict[str, Any]:
        selector = args.get("selector")
        value = args.get("value")
        if not selector or value is None:
            return {"success": False, "error": "select requires 'selector' and 'value'"}
        return await self._manager.select(selector, value)

    async def _action_screenshot(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._manager.screenshot(
            selector=args.get("selector"),
            full_page=args.get("full_page", False),
        )

    async def _action_read(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._manager.read(
            selector=args.get("selector"),
            fmt=args.get("format", "text"),
        )

    async def _action_wait(self, args: dict[str, Any]) -> dict[str, Any]:
        selector = args.get("selector")
        if not selector:
            return {"success": False, "error": "wait requires 'selector'"}
        return await self._manager.wait_for(
            selector,
            timeout=args.get("timeout"),
            state=args.get("state", "visible"),
        )

    async def _action_execute_js(self, args: dict[str, Any]) -> dict[str, Any]:
        script = args.get("script")
        if not script:
            return {"success": False, "error": "execute_js requires 'script'"}
        return await self._manager.execute_js(script)

    async def _action_new_tab(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._manager.new_tab(url=args.get("url"))

    async def _action_switch_tab(self, args: dict[str, Any]) -> dict[str, Any]:
        tab_id = args.get("tab_id")
        if not tab_id:
            return {"success": False, "error": "switch_tab requires 'tab_id'"}
        return await self._manager.switch_tab(tab_id)

    async def _action_close_tab(self, args: dict[str, Any]) -> dict[str, Any]:
        tab_id = args.get("tab_id")
        if not tab_id:
            return {"success": False, "error": "close_tab requires 'tab_id'"}
        return await self._manager.close_tab(tab_id)

    async def _action_close(self, args: dict[str, Any]) -> dict[str, Any]:
        await self._manager.close()
        return {"success": True, "message": "Browser closed"}

    async def cleanup(self) -> None:
        await self._manager.close()
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd backend && python -c "from app.tools.browser_tool import BrowserTool; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/tools/browser_tool.py
git commit -m "feat(browser): implement BrowserTool with 13 actions"
```

---

### Task 4: AgentService 集成

**Files:**
- Modify: `backend/app/services/agent_service.py:114-147`

- [ ] **Step 1: 在 _build_run_tool_registry 中注册 BrowserTool**

在 `agent_service.py` 的 `_build_run_tool_registry` 方法中，`registry.register(SkillTool(...))` 之后添加：

```python
from app.tools.browser_tool import BrowserTool
from app.config.settings import config_manager as _cfg
_browser_cfg = BrowserRunConfig(
    headless=_cfg.settings.browser.headless,
    browser_engine=_cfg.settings.browser.default_browser,
    default_timeout=_cfg.settings.browser.default_timeout,
    default_wait_until=_cfg.settings.browser.default_wait_until,
)
registry.register(BrowserTool(config=_browser_cfg))
```

- [ ] **Step 2: 确认 import 正确**

在文件顶部或合适位置添加 import（如果需要）。

- [ ] **Step 3: 运行现有测试确认无破坏**

```bash
cd backend && python -m pytest tests/ -x -q
```

Expected: 所有现有测试通过

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/agent_service.py
git commit -m "feat(browser): register BrowserTool in AgentService"
```

---

### Task 5: 截图 API 端点

**Files:**
- Create: `backend/app/api/routes/browser_screenshot.py`
- Modify: `backend/app/main.py` (注册路由)

- [ ] **Step 1: 创建截图 API**

`backend/app/api/routes/browser_screenshot.py`:

```python
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/browser", tags=["browser"])

SCREENSHOT_BASE = Path(__file__).resolve().parents[3] / "tmp" / "browser-screenshots"


@router.get("/screenshot")
async def get_screenshot(path: str = Query(..., description="Path to screenshot file")):
    real_path = Path(path).resolve()
    screenshot_base_real = SCREENSHOT_BASE.resolve()

    if not str(real_path).startswith(str(screenshot_base_real)):
        temp_base = Path(__file__).resolve().parents[2] / "browser-screenshots"
        if not str(real_path).startswith(str(temp_base.resolve())):
            raise HTTPException(status_code=403, detail="Path outside allowed directory")

    if not real_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(real_path, media_type="image/png")
```

- [ ] **Step 2: 在 main.py 注册路由**

在 `backend/app/main.py` 中找到路由注册位置，添加：

```python
from app.api.routes.browser_screenshot import router as browser_screenshot_router
app.include_router(browser_screenshot_router)
```

- [ ] **Step 3: 测试 API 启动**

```bash
cd backend && python -c "from app.api.routes.browser_screenshot import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add backend/app/api/routes/browser_screenshot.py backend/app/main.py
git commit -m "feat(browser): add screenshot API endpoint with path validation"
```

---

### Task 6: 前端 Settings 浏览器配置面板

**Files:**
- Create: `frontend/src/pages/settings/BrowserPanel.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: 创建 BrowserPanel 组件**

`frontend/src/pages/settings/BrowserPanel.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Globe, Monitor, Shield, Clock } from 'lucide-react'

interface BrowserSettings {
  headless: boolean
  default_browser: 'chromium' | 'firefox' | 'webkit'
  default_timeout: number
  default_wait_until: 'load' | 'domcontentloaded' | 'networkidle'
  block_private_ips: boolean
  blocked_url_patterns: string[]
}

export function BrowserPanel() {
  const [settings, setSettings] = useState<BrowserSettings>({
    headless: true,
    default_browser: 'chromium',
    default_timeout: 30000,
    default_wait_until: 'load',
    block_private_ips: false,
    blocked_url_patterns: [],
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/ui-settings')
      .then(r => r.json())
      .then(data => {
        if (data.browser) setSettings(data.browser)
      })
      .catch(console.error)
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const current = await fetch('/api/ui-settings').then(r => r.json())
      await fetch('/api/ui-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...current, browser: settings }),
      })
    } catch (e) {
      console.error('Failed to save browser settings', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-content-primary">浏览器配置</h3>

      <div className="space-y-4 rounded-lg border border-edge bg-surface-secondary p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Monitor className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">无头模式</span>
          </div>
          <button
            onClick={() => setSettings(s => ({ ...s, headless: !s.headless }))}
            className={`relative h-6 w-11 rounded-full transition-colors ${settings.headless ? 'bg-accent' : 'bg-surface-tertiary'}`}
          >
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${settings.headless ? 'left-[22px]' : 'left-0.5'}`} />
          </button>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">浏览器引擎</span>
          </div>
          <select
            value={settings.default_browser}
            onChange={e => setSettings(s => ({ ...s, default_browser: e.target.value as BrowserSettings['default_browser'] }))}
            className="rounded border border-edge bg-surface-primary px-2 py-1 text-sm text-content-primary"
          >
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit</option>
          </select>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">导航超时 (ms)</span>
          </div>
          <input
            type="number"
            value={settings.default_timeout}
            onChange={e => setSettings(s => ({ ...s, default_timeout: Number(e.target.value) }))}
            className="w-24 rounded border border-edge bg-surface-primary px-2 py-1 text-sm text-content-primary"
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-content-secondary" />
            <span className="text-sm text-content-primary">禁止私有 IP</span>
          </div>
          <button
            onClick={() => setSettings(s => ({ ...s, block_private_ips: !s.block_private_ips }))}
            className={`relative h-6 w-11 rounded-full transition-colors ${settings.block_private_ips ? 'bg-accent' : 'bg-surface-tertiary'}`}
          >
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${settings.block_private_ips ? 'left-[22px]' : 'left-0.5'}`} />
          </button>
        </div>
      </div>

      <button
        onClick={save}
        disabled={saving}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
      >
        {saving ? '保存中...' : '保存配置'}
      </button>
    </div>
  )
}
```

- [ ] **Step 2: 在 SettingsPage 中添加浏览器 tab**

修改 `frontend/src/pages/SettingsPage.tsx`：

1. 添加 import: `import { Globe } from 'lucide-react'` 和 `import { BrowserPanel } from './settings/BrowserPanel'`
2. 在 tabs 数组中添加: `{ key: 'browser', label: '浏览器', icon: Globe }`
3. 在 SettingsTab 类型中添加: `'browser'`
4. 在渲染区域添加: `{activeTab === 'browser' && <BrowserPanel />}`

- [ ] **Step 3: 前端构建验证**

```bash
cd frontend && pnpm build
```

Expected: 构建成功

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/settings/BrowserPanel.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(browser): add Browser settings panel to Settings page"
```

---

### Task 7: ActionReceipt 截图渲染

**Files:**
- Modify: `frontend/src/components/execution/ActionReceipt.tsx`

- [ ] **Step 1: 在 ActionReceipt 中添加截图渲染逻辑**

在 `ActionReceipt.tsx` 的 detail 渲染逻辑中，添加截图检测和渲染：

1. 在文件顶部 import: `import { Image } from 'lucide-react'`
2. 添加一个辅助函数检测截图数据：

```tsx
function isScreenshotDetail(detail: ActionReceiptDetail): boolean {
  return detail.data?.screenshot_path !== undefined
}
```

3. 在 detail 渲染区域添加截图分支：

```tsx
{isScreenshotDetail(detail) && (
  <div className="mt-2">
    <img
      src={`/api/browser/screenshot?path=${encodeURIComponent(detail.data.screenshot_path)}`}
      alt="Browser screenshot"
      className="max-w-sm rounded border border-edge cursor-pointer hover:opacity-80"
      onClick={() => window.open(`/api/browser/screenshot?path=${encodeURIComponent(detail.data.screenshot_path)}`, '_blank')}
    />
    <p className="mt-1 text-xs text-content-tertiary">
      {detail.data.width}x{detail.data.height} — 点击查看原图
    </p>
  </div>
)}
```

- [ ] **Step 2: 前端构建验证**

```bash
cd frontend && pnpm build
```

Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/execution/ActionReceipt.tsx
git commit -m "feat(browser): add screenshot rendering in ActionReceipt"
```

---

### Task 8: 单元测试 — BrowserTool

**Files:**
- Create: `backend/tests/test_tools/test_browser_tool.py`

- [ ] **Step 1: 编写 BrowserTool 单元测试**

`backend/tests/test_tools/test_browser_tool.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.browser_tool import BrowserTool
from app.tools.base import ToolResult


@pytest.fixture
def browser_tool():
    return BrowserTool()


@pytest.mark.asyncio
async def test_missing_action_returns_error(browser_tool):
    result = await browser_tool.execute({})
    assert not result.success
    assert "action" in result.error.lower()


@pytest.mark.asyncio
async def test_unknown_action_returns_error(browser_tool):
    result = await browser_tool.execute({"action": "nonexistent"})
    assert not result.success
    assert "Unknown action" in result.error


@pytest.mark.asyncio
async def test_navigate_requires_url(browser_tool):
    result = await browser_tool.execute({"action": "navigate"})
    assert not result.success
    assert "url" in result.error.lower()


@pytest.mark.asyncio
async def test_fill_requires_selector_and_value(browser_tool):
    result = await browser_tool.execute({"action": "fill", "selector": "#x"})
    assert not result.success
    assert "value" in result.error.lower()


@pytest.mark.asyncio
async def test_click_requires_selector_or_text(browser_tool):
    result = await browser_tool.execute({"action": "click"})
    assert not result.success
    assert "selector" in result.error.lower() or "text" in result.error.lower()


@pytest.mark.asyncio
async def test_wait_requires_selector(browser_tool):
    result = await browser_tool.execute({"action": "wait"})
    assert not result.success
    assert "selector" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_js_requires_script(browser_tool):
    result = await browser_tool.execute({"action": "execute_js"})
    assert not result.success
    assert "script" in result.error.lower()


@pytest.mark.asyncio
async def test_switch_tab_requires_tab_id(browser_tool):
    result = await browser_tool.execute({"action": "switch_tab"})
    assert not result.success
    assert "tab_id" in result.error.lower()


@pytest.mark.asyncio
async def test_close_tab_requires_tab_id(browser_tool):
    result = await browser_tool.execute({"action": "close_tab"})
    assert not result.success
    assert "tab_id" in result.error.lower()


@pytest.mark.asyncio
async def test_schema_structure(browser_tool):
    schema = browser_tool.get_schema()
    assert schema["name"] == "browser"
    assert "action" in schema["parameters"]["properties"]
    assert "url" in schema["parameters"]["properties"]
    assert schema["parameters"]["required"] == ["action"]


@pytest.mark.asyncio
@patch("app.tools.browser_tool.BrowserManager")
async def test_launch_delegates_to_manager(mock_manager_cls, browser_tool):
    mock_manager = AsyncMock()
    mock_manager.start.return_value = {"success": True, "message": "Browser started"}
    browser_tool._manager = mock_manager

    result = await browser_tool.execute({"action": "launch"})
    assert result.success
    mock_manager.start.assert_called_once()
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && python -m pytest tests/test_tools/test_browser_tool.py -v
```

Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_tools/test_browser_tool.py
git commit -m "test(browser): add BrowserTool unit tests"
```

---

### Task 9: 单元测试 — BrowserManager

**Files:**
- Create: `backend/tests/test_browser/__init__.py`
- Create: `backend/tests/test_browser/test_browser_manager.py`

- [ ] **Step 1: 编写 BrowserManager 单元测试**

`backend/tests/test_browser/__init__.py`: 空文件

`backend/tests/test_browser/test_browser_manager.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.browser.manager import BrowserManager
from app.browser.config import BrowserRunConfig


@pytest.fixture
def manager():
    return BrowserManager(BrowserRunConfig(headless=True))


def test_initial_state(manager):
    assert not manager.is_running
    assert manager._pages == {}
    assert manager._active_page_id is None


def test_new_tab_id_format(manager):
    tid = manager._new_tab_id()
    assert len(tid) == 8
    assert tid.isalnum()


@pytest.mark.asyncio
async def test_start_requires_playwright(manager):
    with patch.dict("sys.modules", {"playwright.async_api": None}):
        with pytest.raises(RuntimeError, match="Playwright not installed"):
            await manager.start()


@pytest.mark.asyncio
async def test_navigate_not_started_auto_starts(manager):
    mock_page = AsyncMock()
    mock_page.goto.return_value = AsyncMock(status=200)
    mock_page.title.return_value = "Test"

    with patch.object(manager, "_ensure_browser") as mock_ensure:
        with patch.object(manager, "_get_active_page", return_value=mock_page):
            mock_ensure.return_value = None
            manager._started = True
            manager._config.default_wait_until = "load"
            manager._config.default_timeout = 30000
            result = await manager.navigate("https://example.com")
            assert result["success"] is True


def test_cleanup_screenshots(manager, tmp_path):
    manager._screenshot_dir = tmp_path / "test-screenshots"
    manager._screenshot_dir.mkdir()
    (manager._screenshot_dir / "test.png").write_bytes(b"fake")
    manager.cleanup_screenshots()
    assert not manager._screenshot_dir.exists()
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && python -m pytest tests/test_browser/test_browser_manager.py -v
```

Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_browser/
git commit -m "test(browser): add BrowserManager unit tests"
```

---

### Task 10: 集成测试 — 真实浏览器

**Files:**
- Create: `backend/tests/test_browser/fixtures/test_page.html`
- Create: `backend/tests/test_browser/test_browser_integration.py`

- [ ] **Step 1: 创建测试用 HTML 页面**

`backend/tests/test_browser/fixtures/test_page.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><title>Test Page</title></head>
<body>
  <h1 id="title">Hello ReflexionOS</h1>
  <form id="test-form">
    <input type="text" id="name-input" name="name" placeholder="Enter name" />
    <select id="color-select" name="color">
      <option value="red">Red</option>
      <option value="blue">Blue</option>
      <option value="green">Green</option>
    </select>
    <button type="button" id="submit-btn" onclick="handleSubmit()">Submit</button>
  </form>
  <div id="result" style="display:none;">Form submitted!</div>
  <script>
    function handleSubmit() {
      document.getElementById('result').style.display = 'block';
    }
    document.title = 'Test Page';
  </script>
</body>
</html>
```

- [ ] **Step 2: 编写集成测试**

`backend/tests/test_browser/test_browser_integration.py`:

```python
import pytest
from pathlib import Path
from app.browser.manager import BrowserManager
from app.browser.config import BrowserRunConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_PAGE = FIXTURES_DIR / "test_page.html"


@pytest.fixture
async def browser():
    mgr = BrowserManager(BrowserRunConfig(headless=True, default_timeout=10000))
    yield mgr
    await mgr.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"),
    reason="playwright not available"
)
async def test_navigate_and_read(browser):
    url = TEST_PAGE.as_uri()
    result = await browser.navigate(url)
    assert result["success"]

    content = await browser.read(selector="#title")
    assert content["success"]
    assert "Hello ReflexionOS" in content["data"]["content"]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"),
    reason="playwright not available"
)
async def test_fill_and_click(browser):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)

    fill_result = await browser.fill("#name-input", "Agent")
    assert fill_result["success"]

    click_result = await browser.click("#submit-btn")
    assert click_result["success"]

    result_div = await browser.read(selector="#result")
    assert result_div["success"]
    assert "Form submitted" in result_div["data"]["content"]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"),
    reason="playwright not available"
)
async def test_select(browser):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)

    result = await browser.select("#color-select", "blue")
    assert result["success"]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"),
    reason="playwright not available"
)
async def test_execute_js(browser):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)

    result = await browser.execute_js("return document.title")
    assert result["success"]
    assert result["data"]["result"] == "Test Page"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"),
    reason="playwright not available"
)
async def test_screenshot(browser, tmp_path):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)

    browser._screenshot_dir = tmp_path
    result = await browser.screenshot()
    assert result["success"]
    assert Path(result["data"]["screenshot_path"]).exists()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"),
    reason="playwright not available"
)
async def test_multi_tab(browser):
    await browser.start()

    tab1 = await browser.new_tab(TEST_PAGE.as_uri())
    assert tab1["success"]

    tab2 = await browser.new_tab()
    assert tab2["success"]

    switch = await browser.switch_tab(tab1["data"]["tab_id"])
    assert switch["success"]

    close = await browser.close_tab(tab2["data"]["tab_id"])
    assert close["success"]
```

- [ ] **Step 3: 运行集成测试（需先安装 playwright）**

```bash
cd backend && pip install playwright && playwright install chromium
cd backend && python -m pytest tests/test_browser/test_browser_integration.py -v
```

Expected: 所有测试通过（如果 playwright 已安装）

- [ ] **Step 4: 提交**

```bash
git add backend/tests/test_browser/
git commit -m "test(browser): add integration tests with local HTML fixtures"
```

---

### Task 11: 最终验证

- [ ] **Step 1: 运行全部后端测试**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: 所有测试通过（包括新增的 browser 测试和所有现有测试）

- [ ] **Step 2: 前端构建**

```bash
cd frontend && pnpm build
```

Expected: 构建成功

- [ ] **Step 3: 类型检查（如果有）**

```bash
cd frontend && pnpm typecheck
```

Expected: 无类型错误

- [ ] **Step 4: Lint 检查（如果有）**

```bash
cd frontend && pnpm lint
```

Expected: 无 lint 错误

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat(browser): complete browser tool implementation"
```

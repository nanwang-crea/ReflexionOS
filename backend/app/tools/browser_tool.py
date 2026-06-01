from __future__ import annotations

import logging
from typing import Any

from app.browser.manager import BrowserManager
from app.browser.models import BrowserActionResult
from app.config.settings import BrowserSettings
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):
    VALID_ACTIONS = frozenset({
        "launch", "navigate", "click", "fill", "select",
        "screenshot", "read", "wait", "execute_js",
        "new_tab", "switch_tab", "close_tab", "close",
    })

    def __init__(self, config: BrowserSettings | None = None):
        self._config = config or BrowserSettings()
        self._manager = BrowserManager(self._config)

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Control a web browser. Actions: launch (start browser), "
            "navigate (open URL), click (click element by selector or text), "
            "fill (fill input field), select (select dropdown option), "
            "screenshot (capture image), read (get text/HTML), "
            "wait (wait for element), execute_js (run JavaScript), "
            "new_tab (open new tab), switch_tab (switch to tab), "
            "close_tab (close a tab), close (shut down browser)."
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
                        "description": "URL to navigate to",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to find and click",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to fill or select",
                    },
                    "script": {
                        "type": "string",
                        "description": "JavaScript to execute",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "html"],
                        "description": "Content format (default: text)",
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": [
                            "load",
                            "domcontentloaded",
                            "networkidle",
                        ],
                        "description": "Navigation wait strategy",
                    },
                    "state": {
                        "type": "string",
                        "enum": [
                            "visible",
                            "hidden",
                            "attached",
                            "detached",
                        ],
                        "description": "Wait state",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in ms",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Full page screenshot",
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Headless mode",
                    },
                    "browser": {
                        "type": "string",
                        "enum": [
                            "chromium",
                            "firefox",
                            "webkit",
                        ],
                        "description": "Browser engine",
                    },
                    "tab_id": {
                        "type": "string",
                        "description": "Tab ID",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action")
        if not action:
            return ToolResult(
                success=False,
                error="Missing required parameter: 'action'",
            )
        if action not in self.VALID_ACTIONS:
            valid = sorted(self.VALID_ACTIONS)
            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Valid: {valid}",
            )

        try:
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                return ToolResult(
                    success=False,
                    error=f"Handler not implemented: {action}",
                )
            result = await handler(args)
            return ToolResult(
                success=result.success,
                output=result.message,
                error=result.error,
                data=result.data,
            )
        except Exception as e:
            logger.exception(f"Browser action '{action}' failed")
            err = f"Browser error: {type(e).__name__}: {e}"
            return ToolResult(success=False, error=err)

    async def _action_launch(self, args):
        return await self._manager.start(
            headless=args.get("headless"),
            browser_engine=args.get("browser"),
        )

    async def _action_navigate(self, args):
        url = args.get("url")
        if not url:
            return BrowserActionResult(
                success=False,
                action="navigate",
                error="navigate requires 'url'",
            )
        return await self._manager.navigate(
            url, wait_until=args.get("wait_until"),
        )

    async def _action_click(self, args):
        return await self._manager.click(
            selector=args.get("selector"),
            text=args.get("text"),
        )

    async def _action_fill(self, args):
        selector = args.get("selector")
        value = args.get("value")
        if not selector or value is None:
            return BrowserActionResult(
                success=False,
                action="fill",
                error="fill requires 'selector' and 'value'",
            )
        return await self._manager.fill(selector, value)

    async def _action_select(self, args):
        selector = args.get("selector")
        value = args.get("value")
        if not selector or value is None:
            return BrowserActionResult(
                success=False,
                action="select",
                error="select requires 'selector' and 'value'",
            )
        return await self._manager.select(selector, value)

    async def _action_screenshot(self, args):
        return await self._manager.screenshot(
            selector=args.get("selector"),
            full_page=args.get("full_page", False),
        )

    async def _action_read(self, args):
        return await self._manager.read(
            selector=args.get("selector"),
            fmt=args.get("format", "text"),
        )

    async def _action_wait(self, args):
        selector = args.get("selector")
        if not selector:
            return BrowserActionResult(
                success=False,
                action="wait",
                error="wait requires 'selector'",
            )
        return await self._manager.wait_for(
            selector,
            timeout=args.get("timeout"),
            state=args.get("state", "visible"),
        )

    async def _action_execute_js(self, args):
        script = args.get("script")
        if not script:
            return BrowserActionResult(
                success=False,
                action="execute_js",
                error="execute_js requires 'script'",
            )
        return await self._manager.execute_js(script)

    async def _action_new_tab(self, args):
        return await self._manager.new_tab(url=args.get("url"))

    async def _action_switch_tab(self, args):
        tab_id = args.get("tab_id")
        if not tab_id:
            return BrowserActionResult(
                success=False,
                action="switch_tab",
                error="switch_tab requires 'tab_id'",
            )
        return await self._manager.switch_tab(tab_id)

    async def _action_close_tab(self, args):
        tab_id = args.get("tab_id")
        if not tab_id:
            return BrowserActionResult(
                success=False,
                action="close_tab",
                error="close_tab requires 'tab_id'",
            )
        return await self._manager.close_tab(tab_id)

    async def _action_close(self, args):
        await self._manager.close()
        return BrowserActionResult(
            success=True,
            action="close",
            message="Browser closed",
        )

    async def cleanup(self) -> None:
        await self._manager.close()

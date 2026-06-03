"""
BrowserTool — 浏览器自动化工具（BaseTool 子类）。

通过 Action 分发模式提供 13 种浏览器操作能力：启动/关闭浏览器、
导航、点击、填写表单、截图、读取内容、执行 JS、多标签管理等。
被 AgentService 注册到 ToolRegistry，由 RapidExecutionLoop 在
TOOL_EXECUTION 阶段调用。

架构：
    BrowserTool (BaseTool)
        └── BrowserManager (Playwright 生命周期管理)

依赖：app.tools.base, app.browser.manager, app.config.settings
"""

from __future__ import annotations

import logging
from typing import Any

from app.browser.manager import BrowserManager
from app.browser.models import BrowserActionResult
from app.config.settings import BrowserSettings
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):
    """浏览器自动化工具，通过 action 参数分发不同操作。

    职责：
        - 接收 Agent 的工具调用请求
        - 校验参数（action 是否有效、必填参数是否存在）
        - 将请求委托给 BrowserManager 对应方法
        - 将 BrowserActionResult 转换为 ToolResult 返回给执行循环

    使用方式：
        tool = BrowserTool(config=BrowserSettings(headless=True))
        result = await tool.execute({"action": "navigate", "url": "https://example.com"})
    """

    # 所有合法的 action 名称集合
    VALID_ACTIONS = frozenset({
        "launch", "navigate", "click", "fill", "select",
        "screenshot", "read", "wait", "execute_js",
        "new_tab", "switch_tab", "close_tab", "close",
    })

    def __init__(self, config: BrowserSettings | None = None):
        """初始化浏览器工具。

        入参：
            config: 浏览器配置，为 None 时使用默认配置

        执行逻辑：
            保存配置并创建 BrowserManager 实例（惰性，不立即启动浏览器）
        """
        self._config = config or BrowserSettings()
        self._manager = BrowserManager(self._config)

    @property
    def name(self) -> str:
        """工具名称，用于 LLM 的 tool_calls 识别。"""
        return "browser"

    @property
    def description(self) -> str:
        """工具描述，告诉 LLM 此工具的功能和可用 action。"""
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
        """返回工具的 JSON Schema，传递给 LLM 的 tools 参数。

        采用扁平化 Schema 设计：所有参数平铺在 properties 中，通过
        description 注明每个参数适用于哪些 action。避免部分 LLM 对
        oneOf + anyOf 嵌套支持不稳定的问题。

        出参：
            dict: 符合 OpenAI function calling 格式的 Schema
        """
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
        """执行浏览器操作的主入口。

        入参：
            args: 工具调用参数，必须包含 "action" 字段

        执行逻辑：
            1. 校验 action 参数存在且合法
            2. 通过 getattr 查找对应的 _action_{name} 处理方法
            3. 调用处理方法获取 BrowserActionResult
            4. 转换为 ToolResult（message → output, error → error, data → data）

        出参：
            ToolResult: Agent 执行循环期望的统一结果格式
        """
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
            # 动态分发到对应的 _action_{name} 方法
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                return ToolResult(
                    success=False,
                    error=f"Handler not implemented: {action}",
                )
            result = await handler(args)
            # BrowserActionResult → ToolResult 转换
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

    # ------------------------------------------------------------------
    # Action Handlers — 每个 action 对应一个处理方法
    # ------------------------------------------------------------------

    async def _action_launch(self, args: dict[str, Any]) -> BrowserActionResult:
        """启动浏览器。可选参数：headless, browser (引擎)。"""
        return await self._manager.start(
            headless=args.get("headless"),
            browser_engine=args.get("browser"),
        )

    async def _action_navigate(self, args: dict[str, Any]) -> BrowserActionResult:
        """导航到 URL。必填：url。可选：wait_until。"""
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

    async def _action_click(self, args: dict[str, Any]) -> BrowserActionResult:
        """点击元素。二选一：selector 或 text。"""
        return await self._manager.click(
            selector=args.get("selector"),
            text=args.get("text"),
        )

    async def _action_fill(self, args: dict[str, Any]) -> BrowserActionResult:
        """填写输入框。必填：selector, value。"""
        selector = args.get("selector")
        value = args.get("value")
        if not selector or value is None:
            return BrowserActionResult(
                success=False,
                action="fill",
                error="fill requires 'selector' and 'value'",
            )
        return await self._manager.fill(selector, value)

    async def _action_select(self, args: dict[str, Any]) -> BrowserActionResult:
        """选择下拉框选项。必填：selector, value。"""
        selector = args.get("selector")
        value = args.get("value")
        if not selector or value is None:
            return BrowserActionResult(
                success=False,
                action="select",
                error="select requires 'selector' and 'value'",
            )
        return await self._manager.select(selector, value)

    async def _action_screenshot(self, args: dict[str, Any]) -> BrowserActionResult:
        """截图。可选：selector (元素), full_page (全页)。"""
        return await self._manager.screenshot(
            selector=args.get("selector"),
            full_page=args.get("full_page", False),
        )

    async def _action_read(self, args: dict[str, Any]) -> BrowserActionResult:
        """读取内容。可选：selector, format (text/html)。"""
        return await self._manager.read(
            selector=args.get("selector"),
            fmt=args.get("format", "text"),
        )

    async def _action_wait(self, args: dict[str, Any]) -> BrowserActionResult:
        """等待元素。必填：selector。可选：timeout, state。"""
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

    async def _action_execute_js(self, args: dict[str, Any]) -> BrowserActionResult:
        """执行 JavaScript。必填：script。"""
        script = args.get("script")
        if not script:
            return BrowserActionResult(
                success=False,
                action="execute_js",
                error="execute_js requires 'script'",
            )
        return await self._manager.execute_js(script)

    async def _action_new_tab(self, args: dict[str, Any]) -> BrowserActionResult:
        """新建标签页。可选：url。"""
        return await self._manager.new_tab(url=args.get("url"))

    async def _action_switch_tab(self, args: dict[str, Any]) -> BrowserActionResult:
        """切换标签页。必填：tab_id。"""
        tab_id = args.get("tab_id")
        if not tab_id:
            return BrowserActionResult(
                success=False,
                action="switch_tab",
                error="switch_tab requires 'tab_id'",
            )
        return await self._manager.switch_tab(tab_id)

    async def _action_close_tab(self, args: dict[str, Any]) -> BrowserActionResult:
        """关闭标签页。必填：tab_id。"""
        tab_id = args.get("tab_id")
        if not tab_id:
            return BrowserActionResult(
                success=False,
                action="close_tab",
                error="close_tab requires 'tab_id'",
            )
        return await self._manager.close_tab(tab_id)

    async def _action_close(self, args: dict[str, Any]) -> BrowserActionResult:
        """关闭浏览器。无参数。"""
        await self._manager.close()
        return BrowserActionResult(
            success=True,
            action="close",
            message="Browser closed",
        )

    async def cleanup(self) -> None:
        """清理资源，在 Run 结束时由 AgentService 调用。

        委托给 BrowserManager.close() 关闭浏览器并清理临时文件。
        """
        await self._manager.close()

"""
test_browser_tool — BrowserTool 单元测试。

覆盖 BrowserTool 的参数校验、Schema 结构和 action 分发逻辑。
使用 Mock 隔离 BrowserManager，不依赖真实浏览器。

依赖：pytest, pytest-asyncio, app.tools.browser_tool
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.browser.models import BrowserActionResult
from app.tools.browser_tool import BrowserTool


@pytest.fixture
def browser_tool():
    """创建 BrowserTool 实例，使用默认配置。"""
    return BrowserTool()


class TestBrowserToolExecute:
    """测试 execute() 方法的参数校验逻辑。"""

    @pytest.mark.asyncio
    async def test_missing_action(self, browser_tool):
        """缺少 action 参数时应返回错误。"""
        result = await browser_tool.execute({})
        assert result.success is False
        assert "action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unknown_action(self, browser_tool):
        """未知 action 名称时应返回错误。"""
        result = await browser_tool.execute({"action": "nonexistent"})
        assert result.success is False
        assert "unknown action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_navigate_without_url(self, browser_tool):
        """navigate 缺少 url 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "navigate"})
        assert result.success is False
        assert "url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fill_without_selector(self, browser_tool):
        """fill 缺少 selector 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "fill", "value": "hello"})
        assert result.success is False
        assert "selector" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fill_without_value(self, browser_tool):
        """fill 缺少 value 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "fill", "selector": "#input"})
        assert result.success is False
        assert "value" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_without_selector_or_text(self, browser_tool):
        """click 既无 selector 也无 text 时应返回错误。"""
        with patch.object(
            browser_tool._manager, "click", new_callable=AsyncMock,
            return_value=BrowserActionResult(
                success=False, action="click", error="click requires 'selector' or 'text'",
            ),
        ):
            result = await browser_tool.execute({"action": "click"})
            assert result.success is False

    @pytest.mark.asyncio
    async def test_wait_without_selector(self, browser_tool):
        """wait 缺少 selector 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "wait"})
        assert result.success is False
        assert "selector" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_js_without_script(self, browser_tool):
        """execute_js 缺少 script 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "execute_js"})
        assert result.success is False
        assert "script" in result.error.lower()

    @pytest.mark.asyncio
    async def test_switch_tab_without_tab_id(self, browser_tool):
        """switch_tab 缺少 tab_id 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "switch_tab"})
        assert result.success is False
        assert "tab_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_close_tab_without_tab_id(self, browser_tool):
        """close_tab 缺少 tab_id 参数时应返回错误。"""
        result = await browser_tool.execute({"action": "close_tab"})
        assert result.success is False
        assert "tab_id" in result.error.lower()


class TestBrowserToolSchema:
    """测试 get_schema() 返回的 JSON Schema 结构。"""

    def test_schema_has_name(self, browser_tool):
        """Schema 的 name 应为 'browser'。"""
        schema = browser_tool.get_schema()
        assert schema["name"] == "browser"

    def test_schema_has_description(self, browser_tool):
        """Schema 应有非空的 description。"""
        schema = browser_tool.get_schema()
        assert isinstance(schema["description"], str)
        assert len(schema["description"]) > 0

    def test_schema_parameters_structure(self, browser_tool):
        """Schema parameters 应包含 type/properties/required。"""
        schema = browser_tool.get_schema()
        params = schema["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params

    def test_schema_requires_action(self, browser_tool):
        """Schema 的 required 列表应包含 'action'。"""
        schema = browser_tool.get_schema()
        assert "action" in schema["parameters"]["required"]

    def test_schema_action_property(self, browser_tool):
        """Schema 的 action 属性应为 string 类型，enum 包含所有合法 action。"""
        schema = browser_tool.get_schema()
        action_prop = schema["parameters"]["properties"]["action"]
        assert action_prop["type"] == "string"
        assert set(action_prop["enum"]) == BrowserTool.VALID_ACTIONS


class TestBrowserToolLaunch:
    """测试 launch action 的委托逻辑。"""

    @pytest.mark.asyncio
    async def test_launch_delegates_to_manager_start(self, browser_tool):
        """launch action 应委托给 BrowserManager.start() 并传递参数。"""
        mock_result = BrowserActionResult(
            success=True, action="launch", message="Browser started",
        )
        with patch.object(
            browser_tool._manager, "start", new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_start:
            result = await browser_tool.execute({"action": "launch", "headless": True})
            mock_start.assert_awaited_once_with(headless=True, browser_engine=None)
            assert result.success is True
            assert result.output == "Browser started"

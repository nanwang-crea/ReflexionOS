import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.browser.models import BrowserActionResult
from app.tools.browser_tool import BrowserTool


@pytest.fixture
def browser_tool():
    return BrowserTool()


class TestBrowserToolExecute:
    @pytest.mark.asyncio
    async def test_missing_action(self, browser_tool):
        result = await browser_tool.execute({})
        assert result.success is False
        assert "action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unknown_action(self, browser_tool):
        result = await browser_tool.execute({"action": "nonexistent"})
        assert result.success is False
        assert "unknown action" in result.error.lower()

    @pytest.mark.asyncio
    async def test_navigate_without_url(self, browser_tool):
        result = await browser_tool.execute({"action": "navigate"})
        assert result.success is False
        assert "url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fill_without_selector(self, browser_tool):
        result = await browser_tool.execute({"action": "fill", "value": "hello"})
        assert result.success is False
        assert "selector" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fill_without_value(self, browser_tool):
        result = await browser_tool.execute({"action": "fill", "selector": "#input"})
        assert result.success is False
        assert "value" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_without_selector_or_text(self, browser_tool):
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
        result = await browser_tool.execute({"action": "wait"})
        assert result.success is False
        assert "selector" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_js_without_script(self, browser_tool):
        result = await browser_tool.execute({"action": "execute_js"})
        assert result.success is False
        assert "script" in result.error.lower()

    @pytest.mark.asyncio
    async def test_switch_tab_without_tab_id(self, browser_tool):
        result = await browser_tool.execute({"action": "switch_tab"})
        assert result.success is False
        assert "tab_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_close_tab_without_tab_id(self, browser_tool):
        result = await browser_tool.execute({"action": "close_tab"})
        assert result.success is False
        assert "tab_id" in result.error.lower()


class TestBrowserToolSchema:
    def test_schema_has_name(self, browser_tool):
        schema = browser_tool.get_schema()
        assert schema["name"] == "browser"

    def test_schema_has_description(self, browser_tool):
        schema = browser_tool.get_schema()
        assert isinstance(schema["description"], str)
        assert len(schema["description"]) > 0

    def test_schema_parameters_structure(self, browser_tool):
        schema = browser_tool.get_schema()
        params = schema["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params

    def test_schema_requires_action(self, browser_tool):
        schema = browser_tool.get_schema()
        assert "action" in schema["parameters"]["required"]

    def test_schema_action_property(self, browser_tool):
        schema = browser_tool.get_schema()
        action_prop = schema["parameters"]["properties"]["action"]
        assert action_prop["type"] == "string"
        assert set(action_prop["enum"]) == BrowserTool.VALID_ACTIONS


class TestBrowserToolLaunch:
    @pytest.mark.asyncio
    async def test_launch_delegates_to_manager_start(self, browser_tool):
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

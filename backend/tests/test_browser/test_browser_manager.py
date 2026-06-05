"""
test_browser_manager — BrowserManager 单元测试。

覆盖浏览器生命周期、页面交互、标签管理和资源清理。
通过 Mock Playwright 对象隔离测试，不依赖真实浏览器。

依赖：pytest, pytest-asyncio, app.browser.manager
"""

import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.browser.manager import BrowserManager, MAX_TABS
from app.config.settings import BrowserSettings


@pytest.fixture
def manager():
    """创建 BrowserManager 实例，使用 headless=True 配置。"""
    return BrowserManager(BrowserSettings(headless=True))


# ------------------------------------------------------------------
# Mock 辅助函数 — 创建模拟的 Playwright 对象
# ------------------------------------------------------------------

def _mock_page():
    """创建模拟的 Playwright Page 对象，所有方法都是 AsyncMock。"""
    page = MagicMock()
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.close = AsyncMock()
    page.bring_to_front = AsyncMock()
    page.title = AsyncMock(return_value="Test Title")
    page.inner_text = AsyncMock(return_value="hello world")
    page.inner_html = AsyncMock(return_value="<p>hello</p>")
    page.evaluate = AsyncMock(return_value=42)
    page.select_option = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock()
    page.url = "about:blank"
    locator = MagicMock()
    locator.inner_text = AsyncMock(return_value="hello world")
    locator.inner_html = AsyncMock(return_value="<p>hello</p>")
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    page.on = MagicMock()
    return page


def _mock_context(page):
    """创建模拟的 BrowserContext 对象。"""
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.set_default_timeout = MagicMock()
    return ctx


def _mock_browser(ctx):
    """创建模拟的 Browser 对象。"""
    browser = MagicMock()
    browser.is_connected = MagicMock(return_value=True)
    browser.new_context = AsyncMock(return_value=ctx)
    browser.close = AsyncMock()
    browser.on = MagicMock()
    return browser


def _mock_playwright(browser):
    """创建模拟的 Playwright 运行时对象。"""
    pw = MagicMock()
    pw.chromium = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.stop = AsyncMock()
    return pw


def _inject_running(manager, page=None):
    """直接将 manager 状态设置为"运行中"，跳过 start() 流程。

    入参：
        manager: BrowserManager 实例
        page: 可选的 mock Page，为 None 时自动创建

    出参：
        MagicMock: 注入的 mock Page 对象
    """
    if page is None:
        page = _mock_page()
    ctx = _mock_context(page)
    browser = _mock_browser(ctx)

    manager._playwright = MagicMock()
    manager._browser = browser
    manager._context = ctx
    tab_id = manager._new_tab_id()
    manager._tabs[tab_id] = page
    manager._active_tab_id = tab_id
    return page


async def _start_with_mocks(manager, page=None):
    """调用 start() 并注入 mock 的 async_playwright。

    入参：
        manager: BrowserManager 实例
        page: 可选的 mock Page

    出参：
        BrowserActionResult: start() 的返回结果
    """
    if page is None:
        page = _mock_page()
    ctx = _mock_context(page)
    browser = _mock_browser(ctx)
    pw = _mock_playwright(browser)

    async_pw_cm = MagicMock()
    async_pw_cm.start = AsyncMock(return_value=pw)

    with patch("app.browser.manager.async_playwright", return_value=async_pw_cm):
        result = await manager.start()

    return result


# ------------------------------------------------------------------
# 测试用例
# ------------------------------------------------------------------

# 1. 初始状态
async def test_initial_state(manager):
    """新建的 BrowserManager 应处于未运行状态。"""
    assert manager.is_running is False
    assert manager._tabs == {}
    assert manager._active_tab_id is None


# 2. _new_tab_id 格式
def test_new_tab_id_format(manager):
    """_new_tab_id 应返回 12 位十六进制字符串。"""
    tid = manager._new_tab_id()
    assert len(tid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", tid)


# 3. start() 成功启动
async def test_start_succeeds(manager):
    """start() 应成功启动浏览器并创建初始标签页。"""
    result = await _start_with_mocks(manager)
    assert result.success is True
    assert result.action == "start"
    assert manager.is_running is True
    assert len(manager._tabs) == 1
    assert manager._active_tab_id is not None


# 4. close() 清理状态
async def test_close_cleans_up(manager):
    """close() 应清空所有运行时状态。"""
    _inject_running(manager)
    result = await manager.close()
    assert result.success is True
    assert manager._browser is None
    assert manager._playwright is None
    assert manager._context is None
    assert manager._tabs == {}
    assert manager._active_tab_id is None


# 5. cleanup_screenshots 删除临时目录
def test_cleanup_screenshots(tmp_path, manager):
    """cleanup_screenshots 应删除截图临时目录及其内容。"""
    ss_dir = tmp_path / "screenshots"
    ss_dir.mkdir()
    (ss_dir / "img.png").write_bytes(b"fake")
    manager._screenshot_dir = ss_dir

    manager.cleanup_screenshots()

    assert not ss_dir.exists()
    assert manager._screenshot_dir is None


# 6. navigate 调用 page.goto
async def test_navigate_calls_goto(manager):
    """navigate 应调用 page.goto() 并传递正确的 URL 和 wait_until。"""
    page = _inject_running(manager)
    result = await manager.navigate("https://example.com")
    assert result.success is True
    page.goto.assert_awaited_once_with("https://example.com", wait_until="load")


# 7. click 使用 selector
async def test_click_selector(manager):
    """click(selector=...) 应调用 page.click()。"""
    page = _inject_running(manager)
    result = await manager.click(selector="button#submit")
    assert result.success is True
    page.click.assert_awaited_once_with("button#submit", timeout=manager._config.action_timeout)


# 8. fill 调用 page.fill
async def test_fill(manager):
    """fill 应调用 page.fill() 传入选择器和值。"""
    page = _inject_running(manager)
    result = await manager.fill("input[name=email]", "test@example.com")
    assert result.success is True
    page.fill.assert_awaited_once_with("input[name=email]", "test@example.com", timeout=manager._config.action_timeout)


# 9. read 返回内容
async def test_read_returns_content(manager):
    """read 应返回元素的 innerText 内容。"""
    _inject_running(manager)
    result = await manager.read()
    assert result.success is True
    assert result.data["content"] == "hello world"


# 10. close_tab 关闭最后一个标签时自动创建空白页
async def test_close_tab_creates_blank(manager):
    """关闭最后一个标签页时应自动创建新的空白标签页。"""
    page = _mock_page()
    blank_page = _mock_page()
    ctx = _mock_context(page)
    ctx.new_page = AsyncMock(return_value=blank_page)
    browser = _mock_browser(ctx)

    manager._playwright = MagicMock()
    manager._browser = browser
    manager._context = ctx
    tab_id = manager._new_tab_id()
    manager._tabs[tab_id] = page
    manager._active_tab_id = tab_id

    assert len(manager._tabs) == 1

    result = await manager.close_tab(tab_id)
    assert result.success is True
    assert len(manager._tabs) == 1  # 关闭后自动创建了新标签
    assert manager._active_tab_id != tab_id  # 活跃标签已切换
    assert manager._active_tab_id in manager._tabs


# 11. MAX_TABS 限制
async def test_max_tabs_limit(manager):
    """标签页数量达到 MAX_TABS 后，new_tab 应返回错误。"""
    first_page = _mock_page()
    extra_pages = [_mock_page() for _ in range(MAX_TABS - 1)]
    all_pages = [first_page] + extra_pages

    ctx = _mock_context(first_page)
    ctx.new_page = AsyncMock(side_effect=extra_pages)
    browser = _mock_browser(ctx)

    manager._playwright = MagicMock()
    manager._browser = browser
    manager._context = ctx
    tab_id = manager._new_tab_id()
    manager._tabs[tab_id] = first_page
    manager._active_tab_id = tab_id

    # 创建到上限
    for _ in range(MAX_TABS - 1):
        res = await manager.new_tab()
        assert res.success is True

    assert len(manager._tabs) == MAX_TABS

    # 超出上限应失败
    result = await manager.new_tab()
    assert result.success is False
    assert "Maximum" in result.error


async def test_list_tabs(manager):
    """list_tabs 应返回所有标签页的 ID 和 URL。"""
    page = _mock_page()
    page.url = "https://example.com"
    _inject_running(manager, page)

    result = await manager.list_tabs()
    assert result.success is True
    assert len(result.data["tabs"]) == 1
    assert result.data["tabs"][0]["tab_id"] == manager._active_tab_id
    assert result.data["tabs"][0]["url"] == "https://example.com"
    assert result.data["active_tab_id"] == manager._active_tab_id


async def test_start_missing_engine_friendly_error():
    """When browser binary is missing, return friendly install instruction."""
    browser = _mock_browser(_mock_context(_mock_page()))
    pw = _mock_playwright(browser)
    pw.firefox = MagicMock()
    pw.firefox.launch = AsyncMock(side_effect=Exception("Executable doesn't exist at /usr/bin/firefox"))

    async_pw_cm = MagicMock()
    async_pw_cm.start = AsyncMock(return_value=pw)

    mgr = BrowserManager(BrowserSettings(browser_engine="firefox"))
    with patch("app.browser.manager.async_playwright", return_value=async_pw_cm):
        result = await mgr.start()

    assert result.success is False
    assert "playwright install firefox" in result.error


async def test_close_kills_disconnected_browser_process():
    """When browser is disconnected, _close_impl should still kill the process."""
    page = _mock_page()
    ctx = _mock_context(page)
    browser = _mock_browser(ctx)
    browser.is_connected = MagicMock(return_value=False)
    browser.process = MagicMock()
    browser.process.kill = MagicMock()

    mgr = BrowserManager(BrowserSettings(headless=True))
    mgr._playwright = MagicMock()
    mgr._browser = browser
    mgr._context = ctx
    tab_id = mgr._new_tab_id()
    mgr._tabs[tab_id] = page
    mgr._active_tab_id = tab_id

    result = await mgr.close()
    assert result.success is True
    browser.process.kill.assert_called_once()

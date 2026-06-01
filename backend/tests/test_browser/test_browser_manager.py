import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app.browser.manager import BrowserManager, MAX_TABS
from app.config.settings import BrowserSettings


@pytest.fixture
def manager():
    return BrowserManager(BrowserSettings(headless=True))


def _mock_page():
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
    page.url = "about:blank"
    locator = MagicMock()
    locator.inner_text = AsyncMock(return_value="hello world")
    locator.inner_html = AsyncMock(return_value="<p>hello</p>")
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    page.on = MagicMock()
    return page


def _mock_context(page):
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.set_default_timeout = MagicMock()
    return ctx


def _mock_browser(ctx):
    browser = MagicMock()
    browser.is_connected = MagicMock(return_value=True)
    browser.new_context = AsyncMock(return_value=ctx)
    browser.close = AsyncMock()
    browser.on = MagicMock()
    return browser


def _mock_playwright(browser):
    pw = MagicMock()
    pw.chromium = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.stop = AsyncMock()
    return pw


async def _start_manager(manager, page=None):
    """Helper: wire mocks and call start()."""
    if page is None:
        page = _mock_page()
    ctx = _mock_context(page)
    browser = _mock_browser(ctx)
    pw = _mock_playwright(browser)

    with patch("app.browser.manager.async_playwright", return_value=pw):
        result = await manager.start()

    return result, pw, browser, ctx, page


# ------------------------------------------------------------------
# 1. Initial state
# ------------------------------------------------------------------
async def test_initial_state(manager):
    assert manager.is_running is False
    assert manager._tabs == {}
    assert manager._active_tab_id is None


# ------------------------------------------------------------------
# 2. _new_tab_id returns 12-char hex
# ------------------------------------------------------------------
def test_new_tab_id_format(manager):
    tid = manager._new_tab_id()
    assert len(tid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", tid)


# ------------------------------------------------------------------
# 3. start() with mock Playwright succeeds
# ------------------------------------------------------------------
async def test_start_succeeds(manager):
    result, *_ = await _start_manager(manager)
    assert result.success is True
    assert result.action == "start"
    assert manager.is_running is True
    assert len(manager._tabs) == 1
    assert manager._active_tab_id is not None


# ------------------------------------------------------------------
# 4. close() cleans up state
# ------------------------------------------------------------------
async def test_close_cleans_up(manager):
    await _start_manager(manager)
    result = await manager.close()
    assert result.success is True
    assert manager._browser is None
    assert manager._playwright is None
    assert manager._context is None
    assert manager._tabs == {}
    assert manager._active_tab_id is None


# ------------------------------------------------------------------
# 5. cleanup_screenshots removes temp directory
# ------------------------------------------------------------------
def test_cleanup_screenshots(tmp_path, manager):
    ss_dir = tmp_path / "screenshots"
    ss_dir.mkdir()
    (ss_dir / "img.png").write_bytes(b"fake")
    manager._screenshot_dir = ss_dir

    manager.cleanup_screenshots()

    assert not ss_dir.exists()
    assert manager._screenshot_dir is None


# ------------------------------------------------------------------
# 6. navigate calls page.goto
# ------------------------------------------------------------------
async def test_navigate_calls_goto(manager):
    page = _mock_page()
    await _start_manager(manager, page)
    result = await manager.navigate("https://example.com")
    assert result.success is True
    page.goto.assert_awaited_once_with("https://example.com", wait_until="load")


# ------------------------------------------------------------------
# 7. click with selector calls page.click
# ------------------------------------------------------------------
async def test_click_selector(manager):
    page = _mock_page()
    await _start_manager(manager, page)
    result = await manager.click(selector="button#submit")
    assert result.success is True
    page.click.assert_awaited_once_with("button#submit")


# ------------------------------------------------------------------
# 8. fill calls page.fill
# ------------------------------------------------------------------
async def test_fill(manager):
    page = _mock_page()
    await _start_manager(manager, page)
    result = await manager.fill("input[name=email]", "test@example.com")
    assert result.success is True
    page.fill.assert_awaited_once_with("input[name=email]", "test@example.com")


# ------------------------------------------------------------------
# 9. read returns content
# ------------------------------------------------------------------
async def test_read_returns_content(manager):
    page = _mock_page()
    await _start_manager(manager, page)
    result = await manager.read()
    assert result.success is True
    assert result.data["content"] == "hello world"


# ------------------------------------------------------------------
# 10. close_tab auto-creates blank tab when closing last
# ------------------------------------------------------------------
async def test_close_tab_creates_blank(manager):
    page = _mock_page()
    ctx = _mock_context(page)
    blank_page = _mock_page()
    ctx.new_page = AsyncMock(side_effect=[page, blank_page])

    browser = _mock_browser(ctx)
    pw = _mock_playwright(browser)

    with patch("app.browser.manager.async_playwright", return_value=pw):
        await manager.start()

    first_tab_id = manager._active_tab_id
    assert len(manager._tabs) == 1

    result = await manager.close_tab(first_tab_id)
    assert result.success is True
    assert len(manager._tabs) == 1
    assert manager._active_tab_id != first_tab_id
    assert manager._active_tab_id in manager._tabs


# ------------------------------------------------------------------
# 11. MAX_TABS limit on new_tab
# ------------------------------------------------------------------
async def test_max_tabs_limit(manager):
    page = _mock_page()
    ctx = _mock_context(page)
    browser = _mock_browser(ctx)
    pw = _mock_playwright(browser)

    pages = [_mock_page() for _ in range(MAX_TABS)]
    ctx.new_page = AsyncMock(side_effect=pages)

    with patch("app.browser.manager.async_playwright", return_value=pw):
        await manager.start()

    # Fill up to MAX_TABS (1 already created by start)
    for _ in range(MAX_TABS - 1):
        res = await manager.new_tab()
        assert res.success is True

    assert len(manager._tabs) == MAX_TABS

    # Next one should fail
    result = await manager.new_tab()
    assert result.success is False
    assert "Maximum" in result.error

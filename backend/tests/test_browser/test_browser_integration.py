import pytest
from pathlib import Path

from app.browser.manager import BrowserManager
from app.config.settings import BrowserSettings

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_PAGE = FIXTURES_DIR / "test_page.html"


@pytest.fixture
async def browser():
    mgr = BrowserManager(
        BrowserSettings(headless=True, default_timeout=10000, allowed_schemes=["http", "https", "file"])
    )
    yield mgr
    await mgr.close()


@pytest.mark.asyncio
async def test_navigate_and_read(browser):
    url = TEST_PAGE.as_uri()
    result = await browser.navigate(url)
    assert result.success

    content = await browser.read(selector="#title")
    assert content.success
    assert "Hello ReflexionOS" in content.data["content"]


@pytest.mark.asyncio
async def test_fill_and_click(browser):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)

    fill_result = await browser.fill("#name-input", "Agent")
    assert fill_result.success

    click_result = await browser.click(selector="#submit-btn")
    assert click_result.success

    result_div = await browser.read(selector="#result")
    assert result_div.success
    assert "Form submitted" in result_div.data["content"]


@pytest.mark.asyncio
async def test_select(browser):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)
    result = await browser.select("#color-select", "blue")
    assert result.success


@pytest.mark.asyncio
async def test_execute_js(browser):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)
    result = await browser.execute_js("return document.title")
    assert result.success
    assert result.data["result"] == "Test Page"


@pytest.mark.asyncio
async def test_screenshot(browser, tmp_path):
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)
    browser._screenshot_dir = tmp_path
    result = await browser.screenshot()
    assert result.success
    assert Path(result.data["path"]).exists()


@pytest.mark.asyncio
async def test_multi_tab(browser):
    await browser.start()
    tab1 = await browser.new_tab(TEST_PAGE.as_uri())
    assert tab1.success
    tab2 = await browser.new_tab()
    assert tab2.success
    switch = await browser.switch_tab(tab1.data["tab_id"])
    assert switch.success
    close = await browser.close_tab(tab2.data["tab_id"])
    assert close.success

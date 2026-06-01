"""
test_browser_integration — 浏览器集成测试。

使用真实 Playwright 浏览器对本地静态 HTML 页面执行端到端操作。
需要安装 playwright 和浏览器二进制：
    pip install playwright && playwright install chromium

测试页面：tests/test_browser/fixtures/test_page.html

依赖：pytest, pytest-asyncio, playwright, app.browser.manager
"""

import pytest
from pathlib import Path

from app.browser.manager import BrowserManager
from app.config.settings import BrowserSettings

# 测试 HTML 文件所在目录
FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_PAGE = FIXTURES_DIR / "test_page.html"


@pytest.fixture
async def browser():
    """创建 BrowserManager 实例，测试结束后自动关闭浏览器。

    配置说明：
        - headless=True: 无头模式，CI 友好
        - default_timeout=10000: 10 秒超时，避免测试挂起
        - allowed_schemes 含 file: 允许访问本地 HTML 文件
    """
    mgr = BrowserManager(
        BrowserSettings(headless=True, default_timeout=10000, allowed_schemes=["http", "https", "file"])
    )
    yield mgr
    await mgr.close()


@pytest.mark.asyncio
async def test_navigate_and_read(browser):
    """导航到本地 HTML 并读取元素文本内容。"""
    url = TEST_PAGE.as_uri()
    result = await browser.navigate(url)
    assert result.success

    content = await browser.read(selector="#title")
    assert content.success
    assert "Hello ReflexionOS" in content.data["content"]


@pytest.mark.asyncio
async def test_fill_and_click(browser):
    """填写表单输入框、点击按钮、验证结果。"""
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)

    # 填写输入框
    fill_result = await browser.fill("#name-input", "Agent")
    assert fill_result.success

    # 点击提交按钮（触发 JS 显示结果区域）
    click_result = await browser.click(selector="#submit-btn")
    assert click_result.success

    # 验证结果区域变为可见
    result_div = await browser.read(selector="#result")
    assert result_div.success
    assert "Form submitted" in result_div.data["content"]


@pytest.mark.asyncio
async def test_select(browser):
    """选择下拉框选项。"""
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)
    result = await browser.select("#color-select", "blue")
    assert result.success


@pytest.mark.asyncio
async def test_execute_js(browser):
    """执行 JavaScript 并获取返回值。"""
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)
    result = await browser.execute_js("return document.title")
    assert result.success
    assert result.data["result"] == "Test Page"


@pytest.mark.asyncio
async def test_screenshot(browser, tmp_path):
    """截图并验证文件已生成。"""
    url = TEST_PAGE.as_uri()
    await browser.navigate(url)
    # 重定向截图目录到临时目录，便于测试清理
    browser._screenshot_dir = tmp_path
    result = await browser.screenshot()
    assert result.success
    assert Path(result.data["path"]).exists()


@pytest.mark.asyncio
async def test_multi_tab(browser):
    """多标签页操作：创建、切换、关闭。"""
    await browser.start()

    # 创建两个标签页
    tab1 = await browser.new_tab(TEST_PAGE.as_uri())
    assert tab1.success
    tab2 = await browser.new_tab()
    assert tab2.success

    # 切换到第一个标签页
    switch = await browser.switch_tab(tab1.data["tab_id"])
    assert switch.success

    # 关闭第二个标签页
    close = await browser.close_tab(tab2.data["tab_id"])
    assert close.success

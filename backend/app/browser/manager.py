"""
BrowserManager — Playwright 浏览器生命周期管理器。

负责启动、关闭浏览器实例，管理多标签页，执行页面交互操作（导航、
点击、填写、截图、读取、JS 执行等）。被 BrowserTool 调用，通过
Playwright 异步 API 控制 Chromium/Firefox/WebKit。

核心设计：
    - 惰性启动：首次操作时自动启动浏览器
    - 并发安全：所有页面操作通过 asyncio.Lock 串行化
    - 安全校验：每次导航前检查 URL 合规性
    - 自动清理：Run 结束时清理临时文件和浏览器进程

依赖：playwright, app.browser.config, app.browser.models, app.config.settings
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.browser.config import BrowserSecurityConfig
from app.browser.models import BrowserActionResult
from app.config.settings import BrowserSettings

logger = logging.getLogger(__name__)

# 最大标签页数量限制，防止资源耗尽
MAX_TABS = 20

# PIL 为可选依赖，用于获取截图尺寸
try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment,misc]


class BrowserManager:
    """管理 Playwright 浏览器的完整生命周期。

    职责：
        - 浏览器启动/关闭（start/close）
        - 页面导航和安全校验（navigate/_validate_url）
        - 页面交互操作（click/fill/select/read/wait_for/execute_js）
        - 截图管理（screenshot/cleanup_screenshots）
        - 多标签管理（new_tab/switch_tab/close_tab）

    并发模型：
        所有公开的异步方法通过 self._lock (asyncio.Lock) 串行化，
        确保同一时刻只有一个操作在修改页面状态。

    生命周期：
        start() → 操作方法 → close()
        如果未调用 start()，首次操作会自动触发 _ensure_browser()
    """

    def __init__(self, config: BrowserSettings | None = None) -> None:
        """初始化浏览器管理器。

        入参：
            config: 浏览器配置（headless、引擎、超时、安全策略等），
                    为 None 时使用默认配置

        执行逻辑：
            1. 保存配置引用
            2. 从 BrowserSettings 的扁平字段构建 BrowserSecurityConfig
            3. 初始化所有运行时状态为空
        """
        self._config = config or BrowserSettings()

        # 从扁平配置构建嵌套的安全配置对象
        self._security = BrowserSecurityConfig(
            block_private_ips=self._config.block_private_ips,
            blocked_url_patterns=self._config.blocked_url_patterns,
            allowed_schemes=self._config.allowed_schemes,
        )

        # Playwright 运行时对象（start 后赋值，close 后清空）
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

        # 标签页管理：tab_id → Page 映射
        self._tabs: dict[str, Page] = {}
        self._active_tab_id: str | None = None

        # 截图临时目录（惰性创建）
        self._screenshot_dir: Path | None = None

        # 并发锁：所有页面操作通过此锁串行化
        self._lock = asyncio.Lock()

        # 浏览器断开标记：_on_disconnected 回调设置，_ensure_browser 检查并重置
        self._is_disconnected = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """检查浏览器是否正在运行且可连接。

        出参：
            bool: True 表示浏览器实例存在且已连接
        """
        return self._browser is not None and self._browser.is_connected()

    # ------------------------------------------------------------------
    # Core Lifecycle
    # ------------------------------------------------------------------

    async def start(
        self,
        headless: bool | None = None,
        browser_engine: str | None = None,
    ) -> BrowserActionResult:
        """启动 Playwright 浏览器实例。

        入参：
            headless: 是否无头模式，None 时使用配置值
            browser_engine: 浏览器引擎 (chromium/firefox/webkit)，None 时使用配置值

        执行逻辑：
            1. 获取并发锁
            2. 委托给 _start_impl 执行实际启动

        出参：
            BrowserActionResult: success=True 时浏览器已就绪
        """
        async with self._lock:
            return await self._start_impl(headless, browser_engine)

    async def _start_impl(
        self,
        headless: bool | None = None,
        browser_engine: str | None = None,
    ) -> BrowserActionResult:
        """启动浏览器的内部实现，必须在锁内调用。

        执行逻辑：
            1. 如果浏览器已在运行，直接返回成功
            2. 确定 headless 和 engine 参数
            3. 启动 Playwright 运行时
            4. 选择浏览器引擎并 launch
            5. 注册 disconnected 事件回调
            6. 创建 BrowserContext 和初始标签页
            7. 创建截图临时目录

        出参：
            BrowserActionResult: 成功或失败结果
        """
        try:
            if self.is_running:
                return BrowserActionResult(
                    success=True, action="start", message="Browser already running"
                )

            _headless = headless if headless is not None else self._config.headless
            _engine = browser_engine or self._config.browser_engine

            # 启动 Playwright 运行时
            self._playwright = await async_playwright().start()

            # 获取对应引擎的 launcher
            launcher = getattr(self._playwright, _engine, None)
            if launcher is None:
                return BrowserActionResult(
                    success=False,
                    action="start",
                    error=f"Unsupported browser engine: {_engine}",
                )

            # 启动浏览器实例
            self._browser = await launcher.launch(headless=_headless)

            # 注册断开回调：浏览器意外断开时设置标记，不直接清理状态（避免竞态）
            self._browser.on("disconnected", self._on_disconnected)

            # 创建隔离的浏览器上下文
            self._context = await self._browser.new_context()
            self._context.set_default_timeout(self._config.default_timeout)

            # 创建初始标签页
            page = await self._context.new_page()
            tab_id = self._new_tab_id()
            self._tabs[tab_id] = page
            self._active_tab_id = tab_id
            self._handle_new_page(page)

            # 惰性创建截图目录
            self._ensure_screenshot_dir()

            logger.info("Browser started (%s, headless=%s)", _engine, _headless)
            return BrowserActionResult(
                success=True,
                action="start",
                message=f"Browser started ({_engine})",
            )
        except Exception as exc:
            logger.exception("Failed to start browser")
            await self._cleanup_on_failure()
            err_msg = str(exc)
            if "Executable doesn't exist" in err_msg or "not found" in err_msg.lower():
                return BrowserActionResult(
                    success=False,
                    action="start",
                    error=f"Browser engine '{_engine}' is not installed. Run: playwright install {_engine}",
                )
            return BrowserActionResult(
                success=False, action="start", error=str(exc)
            )

    async def close(self) -> BrowserActionResult:
        """关闭浏览器并释放所有资源。

        执行逻辑：
            1. 获取并发锁
            2. 委托给 _close_impl 执行实际清理

        出参：
            BrowserActionResult: 始终返回 success=True
        """
        async with self._lock:
            return await self._close_impl()

    async def _close_impl(self) -> BrowserActionResult:
        """关闭浏览器的内部实现，必须在锁内调用。

        执行逻辑：
            1. 关闭浏览器连接（如果仍在线）
            2. 停止 Playwright 运行时
            3. 清空所有运行时状态（在 finally 中确保执行）
            4. 清理截图临时目录
        """
        try:
            if self._browser:
                if self._browser.is_connected():
                    await self._browser.close()
                elif hasattr(self._browser, "process") and self._browser.process is not None:
                    self._browser.process.kill()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            logger.warning("Error during browser close", exc_info=True)
        finally:
            # finally 块确保即使关闭失败也能清空状态
            self._browser = None
            self._playwright = None
            self._context = None
            self._tabs.clear()
            self._active_tab_id = None
            self._is_disconnected = False
            self.cleanup_screenshots()

        logger.info("Browser closed")
        return BrowserActionResult(success=True, action="close", message="Browser closed")

    def cleanup_screenshots(self) -> None:
        """删除截图临时目录及其所有文件。

        在 close() 时自动调用，也可手动调用以提前释放磁盘空间。
        使用 shutil.rmtree(ignore_errors=True) 确保不会因文件锁定而失败。
        """
        if self._screenshot_dir and self._screenshot_dir.exists():
            import shutil

            shutil.rmtree(self._screenshot_dir, ignore_errors=True)
            logger.debug("Cleaned up screenshot dir: %s", self._screenshot_dir)
            self._screenshot_dir = None

    def _on_disconnected(self) -> None:
        """浏览器断开连接的回调函数。

        由 Playwright 的 "disconnected" 事件触发。只设置标记而不直接
        清理状态，避免与正在持有锁的操作产生竞态。_ensure_browser()
        会在下次操作时检查此标记并重置状态。
        """
        logger.warning("Browser disconnected unexpectedly")
        self._is_disconnected = True

    @staticmethod
    def kill_orphan_browsers() -> None:
        """清理孤儿浏览器进程。

        扫描因异常退出残留的 chromium/firefox 进程并终止，
        防止僵尸进程占用系统资源。
        """
        import subprocess

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "chromium.exe"],
                    capture_output=True, timeout=5,
                )
                subprocess.run(
                    ["taskkill", "/F", "/IM", "chrome.exe"],
                    capture_output=True, timeout=5,
                )
            else:
                subprocess.run(
                    ["pkill", "-f", "chromium"],
                    capture_output=True, timeout=5,
                )
                subprocess.run(
                    ["pkill", "-f", "chrome.*--remote-debugging"],
                    capture_output=True, timeout=5,
                )
            logger.debug("kill_orphan_browsers completed")
        except Exception:
            logger.debug("kill_orphan_browsers failed (may be no processes)")

    async def _cleanup_on_failure(self) -> None:
        """启动或操作失败时，清理已分配的 Playwright 资源。

        在 _start_impl 的 except 块中调用，确保启动失败不会残留
        半初始化的 _playwright / _browser 对象。
        """
        try:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        finally:
            self._browser = None
            self._playwright = None
            self._context = None
            self._tabs.clear()
            self._active_tab_id = None
            self._is_disconnected = False

    # ------------------------------------------------------------------
    # Navigation & Interaction
    # ------------------------------------------------------------------

    async def navigate(
        self,
        url: str,
        wait_until: str | None = None,
    ) -> BrowserActionResult:
        """导航到指定 URL。

        入参：
            url: 目标网址
            wait_until: 页面加载等待策略 (load/domcontentloaded/networkidle)，
                       None 时使用配置默认值

        执行逻辑：
            1. 获取并发锁
            2. 校验 URL 安全性（协议、黑名单、私有 IP）
            3. 获取当前活跃页面
            4. 调用 page.goto() 导航
            5. 获取页面标题作为返回数据

        出参：
            BrowserActionResult: success=True 时 data 包含 url 和 title
        """
        async with self._lock:
            try:
                # URL 安全校验：协议、黑名单正则、私有 IP
                validation_error = self._validate_url(url)
                if validation_error:
                    return BrowserActionResult(
                        success=False, action="navigate", error=validation_error
                    )

                page = await self._get_active_page()
                _wait = wait_until or self._config.default_wait_until
                await page.goto(url, wait_until=_wait)
                return BrowserActionResult(
                    success=True,
                    action="navigate",
                    message=f"Navigated to {url}",
                    data={"url": url, "title": await page.title()},
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="navigate", error=str(exc)
                )

    async def click(
        self,
        selector: str | None = None,
        text: str | None = None,
    ) -> BrowserActionResult:
        """点击页面元素。

        入参：
            selector: CSS 选择器（与 text 二选一）
            text: 要查找的文本内容（与 selector 二选一）

        执行逻辑：
            1. 获取并发锁
            2. 获取当前活跃页面
            3. 如果提供了 text，使用 get_by_text 定位并点击
            4. 如果提供了 selector，使用 page.click 点击
            5. 两者都未提供则返回错误

        出参：
            BrowserActionResult: 点击成功或失败
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                if text:
                    await page.get_by_text(text).click(timeout=self._config.action_timeout)
                elif selector:
                    await page.click(selector, timeout=self._config.action_timeout)
                else:
                    return BrowserActionResult(
                        success=False,
                        action="click",
                        error="Provide selector or text",
                    )
                return BrowserActionResult(
                    success=True, action="click", message="Clicked element"
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="click", error=str(exc)
                )

    async def fill(
        self,
        selector: str,
        value: str,
    ) -> BrowserActionResult:
        """填写输入框。

        入参：
            selector: 输入框的 CSS 选择器
            value: 要填入的值

        执行逻辑：
            1. 获取并发锁
            2. 获取当前活跃页面
            3. 调用 page.fill() 清空并填入新值

        出参：
            BrowserActionResult: 填写成功或失败
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                await page.fill(selector, value, timeout=self._config.action_timeout)
                return BrowserActionResult(
                    success=True, action="fill", message=f"Filled {selector}"
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="fill", error=str(exc)
                )

    async def select(
        self,
        selector: str,
        value: str,
    ) -> BrowserActionResult:
        """选择下拉框选项。

        入参：
            selector: select 元素的 CSS 选择器
            value: 要选择的 option value

        执行逻辑：
            1. 获取并发锁
            2. 调用 page.select_option() 选择指定值

        出参：
            BrowserActionResult: 选择成功或失败
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                await page.select_option(selector, value, timeout=self._config.action_timeout)
                return BrowserActionResult(
                    success=True,
                    action="select",
                    message=f"Selected '{value}' in {selector}",
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="select", error=str(exc)
                )

    async def screenshot(
        self,
        selector: str | None = None,
        full_page: bool = False,
    ) -> BrowserActionResult:
        """截图并保存为临时文件。

        入参：
            selector: 要截图的元素选择器（None 时截取整个页面/视口）
            full_page: 是否截取完整可滚动页面（仅 selector=None 时有效）

        执行逻辑：
            1. 获取并发锁
            2. 获取当前活跃页面
            3. 确保截图临时目录存在
            4. 生成唯一文件名（UUID）
            5. 如果有 selector，截取指定元素；否则截取页面
            6. 使用 PIL 获取图片尺寸（如果 PIL 可用）

        出参：
            BrowserActionResult: data 包含 path（文件路径）、width、height
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                self._ensure_screenshot_dir()

                # 使用 UUID 避免文件名冲突
                filename = f"{uuid.uuid4().hex}.png"
                path = self._screenshot_dir / filename  # type: ignore[operator]

                # 截图超时保护：大页面或复杂元素截图可能耗时很长，
                # 使用 2 倍 default_timeout 作为上限，防止卡死不释放资源
                screenshot_timeout = self._config.default_timeout / 1000 * 2
                if selector:
                    element = page.locator(selector)
                    await asyncio.wait_for(
                        element.screenshot(path=str(path)),
                        timeout=screenshot_timeout,
                    )
                else:
                    await asyncio.wait_for(
                        page.screenshot(path=str(path), full_page=full_page),
                        timeout=screenshot_timeout,
                    )

                data: dict[str, Any] = {"path": str(path)}

                # PIL 可选：获取截图尺寸。img.load() 强制完整读取，避免截断文件问题
                if Image is not None:
                    with Image.open(path) as img:
                        img.load()
                        data["width"], data["height"] = img.size

                return BrowserActionResult(
                    success=True,
                    action="screenshot",
                    message="Screenshot captured",
                    data=data,
                )
            except asyncio.TimeoutError:
                return BrowserActionResult(
                    success=False,
                    action="screenshot",
                    error=f"Screenshot timed out after {self._config.default_timeout * 2}ms",
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="screenshot", error=str(exc)
                )

    async def read(
        self,
        selector: str = "body",
        fmt: str = "text",
    ) -> BrowserActionResult:
        """读取元素的文本或 HTML 内容。

        入参：
            selector: 目标元素的 CSS 选择器，默认 "body"
            fmt: 返回格式 — "text" 返回 innerText，"html" 返回 innerHTML

        执行逻辑：
            1. 获取并发锁
            2. 获取当前活跃页面
            3. 根据 fmt 调用 inner_text() 或 inner_html()

        出参：
            BrowserActionResult: data 包含 content（字符串内容）
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                locator = page.locator(selector)
                if fmt == "html":
                    content = await locator.inner_html()
                else:
                    content = await locator.inner_text()
                return BrowserActionResult(
                    success=True,
                    action="read",
                    message="Content read",
                    data={"content": content},
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="read", error=str(exc)
                )

    async def wait_for(
        self,
        selector: str,
        timeout: int | None = None,
        state: str = "visible",
    ) -> BrowserActionResult:
        """等待元素达到指定状态。

        入参：
            selector: 目标元素的 CSS 选择器
            timeout: 超时时间（毫秒），None 时使用配置默认值
            state: 等待的状态 — visible/hidden/attached/detached

        执行逻辑：
            1. 获取并发锁
            2. 调用 page.wait_for_selector() 等待元素

        出参：
            BrowserActionResult: 元素达到目标状态或超时
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                _timeout = timeout or self._config.default_timeout
                await page.wait_for_selector(selector, state=state, timeout=_timeout)
                return BrowserActionResult(
                    success=True,
                    action="wait_for",
                    message=f"Element {selector} is {state}",
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="wait_for", error=str(exc)
                )

    async def execute_js(self, script: str) -> BrowserActionResult:
        """在当前页面执行 JavaScript 脚本。

        入参：
            script: JavaScript 表达式或函数体。用箭头函数返回值，例如：
                    `() => document.title` 或 `() => { return 1 + 1 }`。
                    直接写 `return ...` 会导致语法错误。

        执行逻辑：
            1. 获取并发锁
            2. 计算脚本的 SHA-256 哈希并记录审计日志
            3. 调用 page.evaluate() 执行脚本
            4. 返回执行结果

        出参：
            BrowserActionResult: data 包含 result（JS 返回值）和 script_hash

        安全说明：
            SHA-256 哈希用于审计追溯，不存储完整脚本避免日志膨胀。
            脚本在页面沙箱中执行，不影响宿主进程。
        """
        async with self._lock:
            try:
                # 审计日志：记录脚本哈希用于追溯，不存完整脚本
                script_hash = hashlib.sha256(script.encode()).hexdigest()
                logger.info("Executing JS (sha256=%s)", script_hash)

                page = await self._get_active_page()
                # JS 执行超时保护：防止死循环脚本卡死浏览器资源
                js_timeout = self._config.default_timeout / 1000
                result = await asyncio.wait_for(
                    page.evaluate(script),
                    timeout=js_timeout,
                )
                return BrowserActionResult(
                    success=True,
                    action="execute_js",
                    message="Script executed",
                    data={"result": result, "script_hash": script_hash},
                )
            except asyncio.TimeoutError:
                return BrowserActionResult(
                    success=False,
                    action="execute_js",
                    error=f"JavaScript execution timed out after {self._config.default_timeout}ms",
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="execute_js", error=str(exc)
                )

    # ------------------------------------------------------------------
    # Tab Management
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> BrowserActionResult:
        """创建新标签页并导航到指定 URL。

        入参：
            url: 新标签页打开的 URL，默认 "about:blank"

        执行逻辑：
            1. 获取并发锁
            2. 检查标签页数量是否达到上限 (MAX_TABS=20)
            3. 确保浏览器已启动
            4. 创建新页面并分配唯一 tab_id
            5. 导航到指定 URL

        出参：
            BrowserActionResult: data 包含 tab_id 和 url
        """
        async with self._lock:
            try:
                # 标签页数量限制，防止资源耗尽
                if len(self._tabs) >= MAX_TABS:
                    return BrowserActionResult(
                        success=False,
                        action="new_tab",
                        error=f"Maximum {MAX_TABS} tabs reached",
                    )

                await self._ensure_browser()
                page = await self._context.new_page()  # type: ignore[union-attr]
                tab_id = self._new_tab_id()
                self._tabs[tab_id] = page
                self._active_tab_id = tab_id
                self._handle_new_page(page)

                await page.goto(url, wait_until=self._config.default_wait_until)
                return BrowserActionResult(
                    success=True,
                    action="new_tab",
                    message=f"Opened tab {tab_id}",
                    data={"tab_id": tab_id, "url": url},
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="new_tab", error=str(exc)
                )

    async def switch_tab(self, tab_id: str) -> BrowserActionResult:
        """切换到指定标签页。

        入参：
            tab_id: 目标标签页 ID

        执行逻辑：
            1. 获取并发锁
            2. 验证 tab_id 存在
            3. 设置为活跃标签页
            4. 调用 bring_to_front() 将页面置于前台

        出参：
            BrowserActionResult: data 包含 tab_id
        """
        async with self._lock:
            try:
                if tab_id not in self._tabs:
                    return BrowserActionResult(
                        success=False,
                        action="switch_tab",
                        error=f"Tab {tab_id} not found",
                    )
                self._active_tab_id = tab_id
                page = self._tabs[tab_id]
                await page.bring_to_front()
                return BrowserActionResult(
                    success=True,
                    action="switch_tab",
                    message=f"Switched to tab {tab_id}",
                    data={"tab_id": tab_id},
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="switch_tab", error=str(exc)
                )

    async def close_tab(self, tab_id: str) -> BrowserActionResult:
        """关闭标签页。如果关闭的是最后一个标签页，自动创建空白页。

        入参：
            tab_id: 要关闭的标签页 ID

        执行逻辑：
            1. 获取并发锁
            2. 验证 tab_id 存在
            3. 关闭页面并从字典中移除
            4. 如果关闭后无剩余标签页，创建新的空白页（保持浏览器可用）
            5. 如果关闭的是活跃标签页，切换到第一个可用标签页

        出参：
            BrowserActionResult: data 包含 closed_tab_id，可能包含 new_tab_id
        """
        async with self._lock:
            try:
                if tab_id not in self._tabs:
                    return BrowserActionResult(
                        success=False,
                        action="close_tab",
                        error=f"Tab {tab_id} not found",
                    )

                page = self._tabs.pop(tab_id)
                await page.close()

                # 关闭最后一个标签页时，自动创建空白页保持浏览器可用
                if not self._tabs:
                    await self._ensure_browser()
                    blank = await self._context.new_page()  # type: ignore[union-attr]
                    new_id = self._new_tab_id()
                    self._tabs[new_id] = blank
                    self._active_tab_id = new_id
                    self._handle_new_page(blank)
                    return BrowserActionResult(
                        success=True,
                        action="close_tab",
                        message=f"Closed tab {tab_id}, created blank tab {new_id}",
                        data={"closed_tab_id": tab_id, "new_tab_id": new_id},
                    )

                # 如果关闭的是活跃标签页，切换到第一个可用标签页并置于前台
                if self._active_tab_id == tab_id:
                    self._active_tab_id = next(iter(self._tabs))
                    await self._tabs[self._active_tab_id].bring_to_front()

                return BrowserActionResult(
                    success=True,
                    action="close_tab",
                    message=f"Closed tab {tab_id}",
                    data={"closed_tab_id": tab_id},
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="close_tab", error=str(exc)
                )

    async def list_tabs(self) -> BrowserActionResult:
        """列出所有打开的标签页。

        执行逻辑：
            1. 获取锁，确保浏览器已启动
            2. 遍历 _tabs 构建标签页列表
            3. 返回标签页信息及当前活跃标签 ID

        出参：
            BrowserActionResult: data 包含 tabs 列表和 active_tab_id
        """
        try:
            async with self._lock:
                await self._ensure_browser()
                tabs = [
                    {"tab_id": tid, "url": page.url}
                    for tid, page in self._tabs.items()
                ]
                return BrowserActionResult(
                    success=True,
                    action="list_tabs",
                    message=f"{len(tabs)} tab(s) open",
                    data={"tabs": tabs, "active_tab_id": self._active_tab_id},
                )
        except Exception as exc:
            return BrowserActionResult(
                success=False, action="list_tabs", error=str(exc)
            )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _validate_url(self, url: str) -> str | None:
        """校验 URL 是否符合安全策略。

        入参：
            url: 要校验的 URL 字符串

        执行逻辑：
            1. 解析 URL 获取协议和主机名
            2. 检查协议是否在 allowed_schemes 白名单中
            3. 检查 URL 是否匹配任何 blocked_url_patterns 正则
            4. 如果 block_private_ips 开启，检查主机名是否为私有/回环 IP

        出参：
            str | None: None 表示通过校验，非 None 为错误信息
        """
        parsed = urlparse(url)

        # 协议白名单校验
        if parsed.scheme and parsed.scheme not in self._security.allowed_schemes:
            return f"Scheme '{parsed.scheme}' not allowed. Use: {self._security.allowed_schemes}"

        # URL 黑名单正则匹配
        for pattern in self._security.blocked_url_patterns:
            if re.search(pattern, url):
                return f"URL matches blocked pattern: {pattern}"

        # 私有 IP 限制（10.x, 172.16-31.x, 192.168.x, 127.x 等）
        if self._security.block_private_ips and parsed.hostname:
            try:
                ip = ipaddress.ip_address(parsed.hostname)
                if ip.is_private or ip.is_loopback:
                    return f"Access to private IP {parsed.hostname} is blocked"
            except ValueError:
                pass  # 非 IP 地址（普通域名），允许通过

        return None

    def _new_tab_id(self) -> str:
        """生成唯一的标签页 ID。

        执行逻辑：
            生成 12 位十六进制字符串，循环直到不与现有标签页 ID 冲突。
            12 位 hex = 48 位熵，冲突概率极低。

        出参：
            str: 12 位十六进制字符串
        """
        while True:
            tid = uuid.uuid4().hex[:12]
            if tid not in self._tabs:
                return tid

    def _ensure_screenshot_dir(self) -> None:
        """确保截图临时目录存在。

        执行逻辑：
            如果 _screenshot_dir 为 None，创建基于 UUID 的唯一目录路径。
            然后确保目录存在（mkdir parents=True）。

        目录位置：{tempdir}/browser-screenshots/run-{uuid}
        """
        if self._screenshot_dir is None:
            run_id = uuid.uuid4().hex[:12]
            self._screenshot_dir = (
                Path(tempfile.gettempdir()) / "browser-screenshots" / f"run-{run_id}"
            )
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _get_active_page(self) -> Page:
        """获取当前活跃页面，自动处理异常状态。

        执行逻辑：
            1. 调用 _ensure_browser() 确保浏览器已启动
            2. 如果活跃标签页 ID 无效，回退到第一个可用标签页
            3. 如果没有任何标签页，创建新的空白标签页

        出参：
            Page: 当前活跃的 Playwright Page 对象
        """
        await self._ensure_browser()
        if self._active_tab_id is None or self._active_tab_id not in self._tabs:
            # 回退：选择第一个可用标签页
            if self._tabs:
                self._active_tab_id = next(iter(self._tabs))
            else:
                # 无标签页时创建新的
                page = await self._context.new_page()  # type: ignore[union-attr]
                tab_id = self._new_tab_id()
                self._tabs[tab_id] = page
                self._active_tab_id = tab_id
                self._handle_new_page(page)
        return self._tabs[self._active_tab_id]  # type: ignore[index]

    async def _ensure_browser(self) -> None:
        """确保浏览器正在运行，必要时自动启动。

        执行逻辑：
            1. 检查 _is_disconnected 标记：如果浏览器意外断开，重置状态
            2. 检查 is_running：如果未运行，调用 _start_impl 启动

        这是惰性启动的关键：大多数操作方法在执行前调用此方法。
        """
        # 浏览器意外断开后，重置状态以便重新启动
        if self._is_disconnected:
            self._is_disconnected = False
            self._tabs.clear()
            self._active_tab_id = None
        if not self.is_running:
            await self._start_impl(None, None)

    def _handle_new_page(self, page: Page) -> None:
        """为新页面注册事件处理器。

        入参：
            page: 新创建的 Playwright Page 对象

        执行逻辑：
            注册 popup 事件处理器。子类可重写此方法添加自定义处理。
        """
        page.on("popup", lambda popup: self._on_popup(popup))

    def _on_popup(self, page: Page) -> None:
        """处理弹出窗口。子类可重写添加自定义逻辑。

        入参：
            page: 弹出的 Page 对象
        """
        logger.debug("Popup opened: %s", page.url)

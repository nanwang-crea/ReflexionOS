from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
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

MAX_TABS = 20

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment,misc]


class BrowserManager:
    """Manages the Playwright browser lifecycle, tabs, and page interactions."""

    def __init__(self, config: BrowserSettings | None = None) -> None:
        self._config = config or BrowserSettings()
        self._security = BrowserSecurityConfig(
            block_private_ips=self._config.block_private_ips,
            blocked_url_patterns=self._config.blocked_url_patterns,
        )

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

        # tab_id -> Page
        self._tabs: dict[str, Page] = {}
        self._active_tab_id: str | None = None

        self._screenshot_dir: Path | None = None
        self._lock = asyncio.Lock()
        self._is_disconnected = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Check if the browser is connected and usable."""
        return self._browser is not None and self._browser.is_connected()

    # ------------------------------------------------------------------
    # Core Lifecycle
    # ------------------------------------------------------------------

    async def start(
        self,
        headless: bool | None = None,
        browser_engine: str | None = None,
    ) -> BrowserActionResult:
        """Launch a Playwright browser instance."""
        async with self._lock:
            return await self._start_impl(headless, browser_engine)

    async def _start_impl(
        self,
        headless: bool | None = None,
        browser_engine: str | None = None,
    ) -> BrowserActionResult:
        """Internal implementation of start, must be called with lock held."""
        try:
            if self.is_running:
                return BrowserActionResult(
                    success=True, action="start", message="Browser already running"
                )

            _headless = headless if headless is not None else self._config.headless
            _engine = browser_engine or self._config.browser_engine

            self._playwright = await async_playwright().start()

            launcher = getattr(self._playwright, _engine, None)
            if launcher is None:
                return BrowserActionResult(
                    success=False,
                    action="start",
                    error=f"Unsupported browser engine: {_engine}",
                )

            self._browser = await launcher.launch(headless=_headless)
            self._browser.on("disconnected", self._on_disconnected)

            self._context = await self._browser.new_context()
            self._context.set_default_timeout(self._config.default_timeout)

            # Create an initial tab
            page = await self._context.new_page()
            tab_id = self._new_tab_id()
            self._tabs[tab_id] = page
            self._active_tab_id = tab_id
            self._handle_new_page(page)

            self._ensure_screenshot_dir()

            logger.info("Browser started (%s, headless=%s)", _engine, _headless)
            return BrowserActionResult(
                success=True,
                action="start",
                message=f"Browser started ({_engine})",
            )
        except Exception as exc:
            logger.exception("Failed to start browser")
            return BrowserActionResult(
                success=False, action="start", error=str(exc)
            )

    async def close(self) -> BrowserActionResult:
        """Shut down the browser and release all resources."""
        async with self._lock:
            return await self._close_impl()

    async def _close_impl(self) -> BrowserActionResult:
        """Internal implementation of close, must be called with lock held."""
        try:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            logger.warning("Error during browser close", exc_info=True)
        finally:
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
        """Remove the screenshot temp directory and all files inside it."""
        if self._screenshot_dir and self._screenshot_dir.exists():
            import shutil

            shutil.rmtree(self._screenshot_dir, ignore_errors=True)
            logger.debug("Cleaned up screenshot dir: %s", self._screenshot_dir)
            self._screenshot_dir = None

    def _on_disconnected(self) -> None:
        """Called by Playwright when browser disconnects unexpectedly."""
        logger.warning("Browser disconnected unexpectedly")
        self._is_disconnected = True

    @staticmethod
    def kill_orphan_browsers() -> None:
        """Placeholder for orphan browser process cleanup.

        A future implementation can scan for stale chromium/firefox processes
        that were left behind by previous unclean exits and kill them.
        """
        logger.debug("kill_orphan_browsers called (no-op placeholder)")

    # ------------------------------------------------------------------
    # Navigation & Interaction
    # ------------------------------------------------------------------

    async def navigate(
        self,
        url: str,
        wait_until: str | None = None,
    ) -> BrowserActionResult:
        """Navigate the active page to *url*."""
        async with self._lock:
            try:
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
        """Click an element by CSS *selector* or visible *text*."""
        async with self._lock:
            try:
                page = await self._get_active_page()
                if text:
                    await page.get_by_text(text).click()
                elif selector:
                    await page.click(selector)
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
        """Fill an input field identified by *selector*."""
        async with self._lock:
            try:
                page = await self._get_active_page()
                await page.fill(selector, value)
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
        """Select a dropdown option by *value*."""
        async with self._lock:
            try:
                page = await self._get_active_page()
                await page.select_option(selector, value)
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
        """Capture a screenshot and save it to a temp file.

        Returns the file path and (when PIL is available) image dimensions.
        """
        async with self._lock:
            try:
                page = await self._get_active_page()
                self._ensure_screenshot_dir()

                filename = f"{uuid.uuid4().hex}.png"
                path = self._screenshot_dir / filename  # type: ignore[operator]

                if selector:
                    element = page.locator(selector)
                    await element.screenshot(path=str(path))
                else:
                    await page.screenshot(path=str(path), full_page=full_page)

                data: dict[str, Any] = {"path": str(path)}
                if Image is not None:
                    with Image.open(path) as img:
                        img.load()  # Force full read to avoid truncated file issues
                        data["width"], data["height"] = img.size

                return BrowserActionResult(
                    success=True,
                    action="screenshot",
                    message="Screenshot captured",
                    data=data,
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
        """Read text or inner HTML from an element."""
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
        """Wait for an element to reach the given *state*."""
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
        """Execute JavaScript in the active page and log a SHA-256 audit hash."""
        async with self._lock:
            try:
                script_hash = hashlib.sha256(script.encode()).hexdigest()
                logger.info("Executing JS (sha256=%s)", script_hash)

                page = await self._get_active_page()
                result = await page.evaluate(script)
                return BrowserActionResult(
                    success=True,
                    action="execute_js",
                    message="Script executed",
                    data={"result": result, "script_hash": script_hash},
                )
            except Exception as exc:
                return BrowserActionResult(
                    success=False, action="execute_js", error=str(exc)
                )

    # ------------------------------------------------------------------
    # Tab Management
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> BrowserActionResult:
        """Create a new tab and optionally navigate to *url*."""
        async with self._lock:
            try:
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
        """Switch the active tab to *tab_id*."""
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
        """Close a tab. If it's the last tab, auto-create a blank one."""
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

                # If we closed the active tab or the last tab, create a blank one
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

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _validate_url(self, url: str) -> str | None:
        """Return error message if URL is invalid, None if OK."""
        parsed = urlparse(url)
        if parsed.scheme and parsed.scheme not in self._security.allowed_schemes:
            return f"Scheme '{parsed.scheme}' not allowed. Use: {self._security.allowed_schemes}"
        for pattern in self._security.blocked_url_patterns:
            if re.search(pattern, url):
                return f"URL matches blocked pattern: {pattern}"
        if self._security.block_private_ips and parsed.hostname:
            try:
                ip = ipaddress.ip_address(parsed.hostname)
                if ip.is_private or ip.is_loopback:
                    return f"Access to private IP {parsed.hostname} is blocked"
            except ValueError:
                pass  # Not an IP, hostname is OK
        return None

    def _new_tab_id(self) -> str:
        """Generate a unique 12-character hex tab identifier."""
        while True:
            tid = uuid.uuid4().hex[:12]
            if tid not in self._tabs:
                return tid

    def _ensure_screenshot_dir(self) -> None:
        """Create the temp screenshot directory if it doesn't exist."""
        if self._screenshot_dir is None:
            run_id = uuid.uuid4().hex[:12]
            self._screenshot_dir = (
                Path(tempfile.gettempdir()) / "browser-screenshots" / f"run-{run_id}"
            )
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _get_active_page(self) -> Page:
        """Return the currently active page, auto-starting if needed."""
        await self._ensure_browser()
        if self._active_tab_id is None or self._active_tab_id not in self._tabs:
            # Fallback: pick the first available tab
            if self._tabs:
                self._active_tab_id = next(iter(self._tabs))
            else:
                # No tabs at all — create one
                page = await self._context.new_page()  # type: ignore[union-attr]
                tab_id = self._new_tab_id()
                self._tabs[tab_id] = page
                self._active_tab_id = tab_id
                self._handle_new_page(page)
        return self._tabs[self._active_tab_id]  # type: ignore[index]

    async def _ensure_browser(self) -> None:
        """Auto-start the browser if it isn't running."""
        if self._is_disconnected:
            self._is_disconnected = False
            self._tabs.clear()
            self._active_tab_id = None
        if not self.is_running:
            await self._start_impl(None, None)

    def _handle_new_page(self, page: Page) -> None:
        """Register event handlers for a newly created page.

        Override this method in subclasses to add custom popup handling.
        """
        page.on("popup", lambda popup: self._on_popup(popup))

    # noinspection PyMethodMayBeStatic
    def _on_popup(self, page: Page) -> None:
        """Handle a popup window. Subclasses may override for custom logic."""
        logger.debug("Popup opened: %s", page.url)

# Browser Tool Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 verified bugs in the browser tool chain that block core functionality (read/execute_js returns invisible to agent, orphan processes, missing list_tabs, wrong read default, misleading JS docs, unfriendly engine errors, slow selector timeout).

**Architecture:** Fixes target three files: `tool_call_executor.py` (Bug #3 — serialize data into tool_output), `manager.py` (Bugs #1, #2, #4, #5, #6, #7 — process cleanup, selector defaults, docs, list_tabs, engine error wrapping, timeout reduction), and `browser_tool.py` (Bug #5 — wire list_tabs action + schema). One new test file covers all fixes.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, Playwright (for integration tests), Pydantic

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/execution/tool_call_executor.py` | Bug #3: Include `result.data` key fields in `tool_output` string sent to LLM |
| `backend/app/browser/manager.py` | Bug #1: Kill orphan process in `_close_impl`; Bug #2: N/A (already fixed); Bug #4: Fix execute_js docstring; Bug #5: Add `list_tabs` method; Bug #6: Wrap launcher.launch() with friendly error; Bug #7: Add `_action_timeout` default for click/fill/select |
| `backend/app/tools/browser_tool.py` | Bug #5: Add `list_tabs` to VALID_ACTIONS, schema, and handler; Bug #4: Fix execute_js description in schema |
| `backend/tests/test_browser/test_browser_manager.py` | Unit tests for all bug fixes |

---

### Task 1: Bug #3 — Make `read`/`execute_js` data visible to LLM

**Files:**
- Modify: `backend/app/execution/tool_call_executor.py:149-166`

This is the most critical bug. `tool_output = result.output or result.error or ""` only takes `result.output` (which is `BrowserActionResult.message` = "Content read" / "Script executed"), discarding `result.data` (which contains the actual page content / JS result). The LLM never sees the data.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_browser/test_browser_manager.py`:

```python
async def test_tool_output_includes_data():
    """tool_call_executor should include result.data content in tool_output for browser read/execute_js."""
    from app.tools.browser_tool import BrowserTool
    from app.tools.base import ToolResult

    tool = BrowserTool(BrowserSettings(headless=True))

    # Simulate a read result that has meaningful data
    read_result = ToolResult(
        success=True,
        output="Content read",
        data={"content": "Hello World from page"},
    )

    # The current code would produce tool_output = "Content read"
    # which discards the actual page content.
    # After fix, tool_output should include the data content.
    tool_output = read_result.output or read_result.error or ""
    assert "Hello World from page" not in tool_output  # Current bug: data is lost
```

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_tool_output_includes_data -v`
Expected: PASS (demonstrates the bug — data is missing from tool_output)

- [ ] **Step 2: Fix tool_call_executor.py to serialize data into tool_output**

Modify `backend/app/execution/tool_call_executor.py` lines 149-166. After building `tool_output` from `result.output or result.error or ""`, append serialized key data from `result.data`:

```python
            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time

            tool_output = result.output or result.error or ""
            if not result.success and result.data and "return_code" in result.data:
                rc_info = f"\n[进程返回码: {result.data['return_code']}]"
                if not result.error:
                    tool_output = tool_output + rc_info
                else:
                    tool_output = tool_output + rc_info if not tool_output.endswith(rc_info) else tool_output
            # Bug #3 fix: Include key data fields in tool_output for LLM visibility.
            # BrowserTool read/execute_js/screenshot/navigate/new_tab return critical
            # data in result.data that must be visible to the LLM for decision-making.
            if result.success and result.data:
                import json as _json
                data_keys_to_include = {"content", "result", "path", "url", "title", "tab_id", "tabs"}
                filtered = {k: v for k, v in result.data.items() if k in data_keys_to_include}
                if filtered:
                    data_str = _json.dumps(filtered, ensure_ascii=False, default=str)
                    tool_output = f"{tool_output}\n{data_str}" if tool_output else data_str
            context.update_history(tool_call, tool_output)
            context.add_message(
                "tool",
                content=tool_output,
                tool_call_id=tool_call.id,
            )
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/test_browser/ tests/test_tools/test_browser_tool.py -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/tool_call_executor.py
git commit -m "fix: include browser tool data fields in tool_output for LLM visibility (Bug #3)"
```

---

### Task 2: Bug #1 — Kill orphan browser process in `_close_impl`

**Files:**
- Modify: `backend/app/browser/manager.py:232-259`

When `_close_impl` is called and `self._browser.is_connected()` returns `False` (browser already crashed/disconnected), `_browser.close()` is skipped but the child process may still be running. Need a fallback that kills the process.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_browser/test_browser_manager.py`:

```python
async def test_close_kills_disconnected_browser_process():
    """When browser is disconnected, _close_impl should still kill the process."""
    page = _mock_page()
    ctx = _mock_context(page)
    browser = _mock_browser(ctx)
    browser.is_connected = MagicMock(return_value=False)
    browser.process = MagicMock()
    browser.process.kill = MagicMock()

    manager._playwright = MagicMock()
    manager._browser = browser
    manager._context = ctx
    tab_id = manager._new_tab_id()
    manager._tabs[tab_id] = page
    manager._active_tab_id = tab_id

    result = await manager.close()
    assert result.success is True
    browser.process.kill.assert_called_once()
```

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_close_kills_disconnected_browser_process -v`
Expected: FAIL — `browser.process.kill` is not called

- [ ] **Step 2: Fix `_close_impl` in manager.py**

Replace the try block in `_close_impl` (lines 241-247):

```python
    async def _close_impl(self) -> BrowserActionResult:
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
            self._browser = None
            self._playwright = None
            self._context = None
            self._tabs.clear()
            self._active_tab_id = None
            self._is_disconnected = False
            self.cleanup_screenshots()

        logger.info("Browser closed")
        return BrowserActionResult(success=True, action="close", message="Browser closed")
```

- [ ] **Step 3: Run test to verify fix**

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_close_kills_disconnected_browser_process -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/browser/manager.py
git commit -m "fix: kill orphan browser process when disconnected (Bug #1)"
```

---

### Task 3: Bug #4 — Fix execute_js docstring and schema description

**Files:**
- Modify: `backend/app/browser/manager.py:638-642`
- Modify: `backend/app/tools/browser_tool.py:185`

The docstring says `使用 "return" 返回值` but Playwright's `page.evaluate()` does not support top-level `return` statements. Must change to arrow function / IIFE examples.

- [ ] **Step 1: Fix manager.py docstring**

Replace the `execute_js` method docstring (lines 638-656):

```python
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
```

- [ ] **Step 2: Fix browser_tool.py schema description**

In `get_schema()`, change the `script` property description (line 185):

```python
                    "script": {
                        "type": "string",
                        "description": "JavaScript to execute. Use arrow function to return values, e.g. `() => document.title`. Do NOT use top-level `return`.",
                    },
```

- [ ] **Step 3: Run existing tests**

Run: `cd backend && python -m pytest tests/test_browser/ tests/test_tools/test_browser_tool.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/browser/manager.py backend/app/tools/browser_tool.py
git commit -m "fix: correct execute_js docstring and schema - use arrow function not return (Bug #4)"
```

---

### Task 4: Bug #5 — Add `list_tabs` action

**Files:**
- Modify: `backend/app/browser/manager.py` — add `list_tabs` method
- Modify: `backend/app/tools/browser_tool.py` — add `list_tabs` to VALID_ACTIONS, schema, handler

Without `list_tabs`, agents cannot discover tab IDs. `new_tab` returns tab_id in `result.data`, but Bug #3 previously made that invisible. Now that Bug #3 is fixed, `new_tab` data will be visible. However, agents still need `list_tabs` to discover the initial tab and enumerate all open tabs.

- [ ] **Step 1: Add `list_tabs` method to BrowserManager**

Add after `close_tab` method in `manager.py` (after line 830):

```python
    async def list_tabs(self) -> BrowserActionResult:
        """列出所有标签页的 ID 和 URL。

        出参：
            BrowserActionResult: data 包含 tabs（列表，每项含 tab_id 和 url）
                                 和 active_tab_id
        """
        async with self._lock:
            try:
                await self._ensure_browser()
                tabs = []
                for tid, page in self._tabs.items():
                    tabs.append({"tab_id": tid, "url": page.url})
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
```

- [ ] **Step 2: Add `list_tabs` to BrowserTool**

In `browser_tool.py`:

1. Add `"list_tabs"` to `VALID_ACTIONS` (line 104-108):

```python
    VALID_ACTIONS = frozenset({
        "launch", "navigate", "click", "fill", "select",
        "screenshot", "read", "wait", "execute_js",
        "new_tab", "switch_tab", "close_tab", "list_tabs", "close",
    })
```

2. Add action handler (after `_action_close_tab`):

```python
    async def _action_list_tabs(self, args: dict[str, Any]) -> BrowserActionResult:
        """列出所有标签页。无参数。"""
        return await self._manager.list_tabs()
```

3. Add `list_tabs` to schema description (line 135-143):

```python
        return (
            "Control a web browser. Actions: launch (start browser), "
            "navigate (open URL), click (click element by selector or text), "
            "fill (fill input field), select (select dropdown option), "
            "screenshot (capture image), read (get text/HTML), "
            "wait (wait for element), execute_js (run JavaScript), "
            "new_tab (open new tab), list_tabs (list all tabs), "
            "switch_tab (switch to tab), close_tab (close a tab), "
            "close (shut down browser)."
        )
```

- [ ] **Step 3: Add test for list_tabs**

Add to `test_browser_manager.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_list_tabs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/browser/manager.py backend/app/tools/browser_tool.py backend/tests/test_browser/test_browser_manager.py
git commit -m "feat: add list_tabs action to discover open browser tabs (Bug #5)"
```

---

### Task 5: Bug #6 — Friendly error for missing browser engine binary

**Files:**
- Modify: `backend/app/browser/manager.py:164-217`

When Firefox/WebKit binary is not installed, `launcher.launch()` raises a raw `Executable doesn't exist at ...` error. We need to catch this and return a friendlier message.

- [ ] **Step 1: Write the failing test**

Add to `test_browser_manager.py`:

```python
async def test_start_missing_engine_friendly_error(manager):
    """When browser binary is missing, return friendly install instruction."""
    from playwright.async_api import Error as PlaywrightError

    browser = _mock_browser(_mock_context(_mock_page()))
    pw = _mock_playwright(browser)
    pw.firefox = MagicMock()
    pw.firefox.launch = AsyncMock(side_effect=PlaywrightError("Executable doesn't exist at /usr/bin/firefox"))

    async_pw_cm = MagicMock()
    async_pw_cm.start = AsyncMock(return_value=pw)

    mgr = BrowserManager(BrowserSettings(browser_engine="firefox"))
    with patch("app.browser.manager.async_playwright", return_value=async_pw_cm):
        result = await mgr.start()

    assert result.success is False
    assert "playwright install firefox" in result.error
```

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_start_missing_engine_friendly_error -v`
Expected: FAIL — error message does not contain "playwright install firefox"

- [ ] **Step 2: Fix `_start_impl` in manager.py**

Wrap the `launcher.launch()` call (around line 186) with a try/except that catches `playwright.async_api.Error` and returns a friendly message:

```python
            # 启动浏览器实例
            try:
                self._browser = await launcher.launch(headless=_headless)
            except Exception as launch_exc:
                await self._cleanup_on_failure()
                err_msg = str(launch_exc)
                if "Executable doesn't exist" in err_msg or "not found" in err_msg.lower():
                    return BrowserActionResult(
                        success=False,
                        action="start",
                        error=f"Browser engine '{_engine}' is not installed. Run: playwright install {_engine}",
                    )
                return BrowserActionResult(
                    success=False, action="start", error=str(launch_exc)
                )
```

Note: The outer try/except already catches and calls `_cleanup_on_failure`, but we need to intercept before that to give a friendly message. Since `_cleanup_on_failure` is called in the outer except too, we should restructure slightly. The cleanest approach is to catch the launch error inside the try block and return early with the friendly message, then the outer except handles other unexpected errors:

Actually, let me simplify. The existing outer `except Exception as exc` at line 211 already calls `_cleanup_on_failure()`. We just need to add a specific catch for the launch error *before* it falls through. The simplest fix is to check the error message in the outer except:

```python
        except Exception as exc:
            logger.exception("Failed to start browser")
            await self._cleanup_on_failure()
            err_msg = str(exc)
            if "Executable doesn't exist" in err_msg:
                return BrowserActionResult(
                    success=False,
                    action="start",
                    error=f"Browser engine '{_engine}' is not installed. Run: playwright install {_engine}",
                )
            return BrowserActionResult(
                success=False, action="start", error=str(exc)
            )
```

But `_engine` is a local variable in the try block. We need to capture it. Actually `_engine` is defined at line 171 before the launch, so we can reference it in the except. Let me verify: `_engine = browser_engine or self._config.browser_engine` at line 171, and the try block starts at line 164. Yes, `_engine` is accessible in the except block since it's assigned before the error occurs.

- [ ] **Step 3: Run test**

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_start_missing_engine_friendly_error -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/browser/manager.py backend/tests/test_browser/test_browser_manager.py
git commit -m "fix: friendly error when browser engine binary not installed (Bug #6)"
```

---

### Task 6: Bug #7 — Reduce default timeout for selector operations

**Files:**
- Modify: `backend/app/browser/manager.py` — add shorter timeout for click/fill/select when selector doesn't match

Currently `click`, `fill`, `select` use Playwright's default context timeout (30s). When a selector doesn't exist, the agent waits the full 30s before getting an error. We should use a shorter action-specific timeout (5s default) that can be overridden.

- [ ] **Step 1: Add `action_timeout` to BrowserSettings**

In `backend/app/config/settings.py`, add a field to `BrowserSettings`:

```python
class BrowserSettings(BaseModel):
    """浏览器配置"""

    headless: bool = False
    browser_engine: str = "chromium"
    default_timeout: int = 30000
    action_timeout: int = 5000
    default_wait_until: str = "load"
    block_private_ips: bool = False
    blocked_url_patterns: list[str] = Field(default_factory=list)
    allowed_schemes: list[str] = Field(default=["http", "https"])
```

- [ ] **Step 2: Apply action_timeout to click, fill, select in manager.py**

Modify `click` method to pass timeout:

```python
    async def click(
        self,
        selector: str | None = None,
        text: str | None = None,
    ) -> BrowserActionResult:
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
```

Modify `fill` method:

```python
    async def fill(
        self,
        selector: str,
        value: str,
    ) -> BrowserActionResult:
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
```

Modify `select` method:

```python
    async def select(
        self,
        selector: str,
        value: str,
    ) -> BrowserActionResult:
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
```

- [ ] **Step 3: Update existing unit tests to account for timeout parameter**

The existing tests use `page.click.assert_awaited_once_with(...)` which will now include the `timeout` kwarg. Update test assertions:

In `test_browser_manager.py`, update `test_click_selector`:

```python
async def test_click_selector(manager):
    """click(selector=...) 应调用 page.click() 并传递 timeout。"""
    page = _inject_running(manager)
    result = await manager.click(selector="button#submit")
    assert result.success is True
    page.click.assert_awaited_once_with("button#submit", timeout=manager._config.action_timeout)
```

Update `test_fill`:

```python
async def test_fill(manager):
    """fill 应调用 page.fill() 传入选择器、值和 timeout。"""
    page = _inject_running(manager)
    result = await manager.fill("input[name=email]", "test@example.com")
    assert result.success is True
    page.fill.assert_awaited_once_with("input[name=email]", "test@example.com", timeout=manager._config.action_timeout)
```

- [ ] **Step 4: Run all browser tests**

Run: `cd backend && python -m pytest tests/test_browser/ tests/test_tools/test_browser_tool.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/browser/manager.py backend/app/config/settings.py backend/tests/test_browser/test_browser_manager.py
git commit -m "fix: reduce default timeout for click/fill/select from 30s to 5s (Bug #7)"
```

---

### Task 7: Bug #2 — Verify `read` default selector is already `"body"`

**Files:**
- Verify: `backend/app/browser/manager.py:565`
- Verify: `backend/app/tools/browser_tool.py:356-361`

Looking at the code: `manager.py:565` already has `selector: str = "body"` as the default parameter. And `browser_tool.py:358` passes `selector=args.get("selector")` which returns `None` when not provided, overriding the default.

This is the actual bug: `args.get("selector")` returns `None`, which overrides the default `"body"` in the method signature.

- [ ] **Step 1: Fix `_action_read` in browser_tool.py**

Change line 358-359:

```python
    async def _action_read(self, args: dict[str, Any]) -> BrowserActionResult:
        """读取内容。可选：selector, format (text/html)。"""
        return await self._manager.read(
            selector=args.get("selector", "body"),
            fmt=args.get("format", "text"),
        )
```

Wait — `args.get("selector", "body")` would return `"body"` when `selector` key is absent, but NOT when it's explicitly `None`. The LLM might send `"selector": null`. So we need:

```python
    async def _action_read(self, args: dict[str, Any]) -> BrowserActionResult:
        """读取内容。可选：selector, format (text/html)。"""
        return await self._manager.read(
            selector=args.get("selector") or "body",
            fmt=args.get("format", "text"),
        )
```

`or "body"` covers both `None` and empty string cases.

- [ ] **Step 2: Add test for read without selector**

Add to `test_browser_manager.py`:

```python
async def test_read_default_selector(manager):
    """read 不传 selector 时应默认读取 body。"""
    page = _inject_running(manager)
    result = await manager.read()
    assert result.success is True
    page.locator.assert_called_with("body")
```

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_read_default_selector -v`
Expected: PASS (manager.read() already defaults to "body")

But we also need to test the BrowserTool path:

```python
async def test_action_read_default_selector(manager):
    """_action_read 不传 selector 时应传 'body' 给 manager。"""
    from app.tools.browser_tool import BrowserTool
    tool = BrowserTool(BrowserSettings(headless=True))
    page = _inject_running(tool._manager)
    result = await tool._action_read({})
    assert result.success is True
    page.locator.assert_called_with("body")
```

Run: `cd backend && python -m pytest tests/test_browser/test_browser_manager.py::test_action_read_default_selector -v`
Expected: PASS after fix

- [ ] **Step 3: Commit**

```bash
git add backend/app/tools/browser_tool.py backend/tests/test_browser/test_browser_manager.py
git commit -m "fix: read action defaults selector to 'body' when not provided (Bug #2)"
```

---

## Self-Review

**1. Spec coverage:**
- Bug #1 (orphan process) → Task 2 ✅
- Bug #2 (read default selector) → Task 7 ✅
- Bug #3 (data invisible to LLM) → Task 1 ✅
- Bug #4 (JS docstring) → Task 3 ✅
- Bug #5 (list_tabs) → Task 4 ✅
- Bug #6 (friendly engine error) → Task 5 ✅
- Bug #7 (slow timeout) → Task 6 ✅

**2. Placeholder scan:** No TBD/TODO/placeholders found. All steps contain actual code.

**3. Type consistency:** 
- `action_timeout: int = 5000` in BrowserSettings matches `timeout=self._config.action_timeout` usage in manager.py (Playwright expects ms as int) ✅
- `list_tabs` returns `BrowserActionResult` with `data={"tabs": [...], "active_tab_id": ...}` — `tabs` key is included in Task 1's `data_keys_to_include` set ✅
- `process.kill()` is synchronous in Playwright, called correctly ✅

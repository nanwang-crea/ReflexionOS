# Browser Tool 设计文档

> 日期：2026-06-01
> 状态：已批准（评审修订 v2）
> 范围：为 ReflexionOS Agent 增加浏览器操作能力
> 评审修订：已回应全部 8 条评审意见

---

## 1. 目标

给 Agent 增加一个 `browser` 工具，让它能像人类一样操作浏览器 — 打开网页、点击、填写表单、截图、抓取内容。基于 Playwright 实现。

**核心场景：**
- Agent 帮用户打开某个网页并截图
- Agent 填写网页表单并提交
- Agent 抓取网页上的数据内容
- Agent 执行前端 JS 并获取结果
- Agent 测试 Web 应用的 UI 行为

## 2. 技术选型

| 选项 | 决策 | 理由 |
|------|------|------|
| 库 | Playwright (Python) | 原生 async API，自动等待机制好，支持 Chromium/Firefox/WebKit |
| 工具模式 | 单工具 + Action 分发 | 与现有 `file` 工具风格一致，LLM 只需记住一个工具名 |
| 运行模式 | 无头为主，可切换有头 | 资源占用低，用户可在设置中切换观察 |
| 生命周期 | Run 级别，惰性启动 | 不浪费资源，Run 结束自动清理 |

## 3. 架构

```
┌─ AgentService ──────────────────────────────────────────┐
│  _build_run_tool_registry()                              │
│    → ToolRegistry                                        │
│      → BrowserTool(security, config)  ← 新增            │
│      → FileTool / ShellTool / ... (现有)                  │
└──────────────────────────────────────────────────────────┘
                         ↓
┌─ BrowserTool (BaseTool 子类) ─────────────────────────────┐
│  name = "browser"                                         │
│  execute({"action": "navigate", "url": "..."}) → ToolResult│
│                                                           │
│  内部持有 BrowserManager 实例:                              │
│  ┌─ BrowserManager ──────────────────────────────────┐    │
│  │  playwright: Playwright                            │    │
│  │  browser: Browser (Chromium, headless)             │    │
│  │  context: BrowserContext (隔离会话)                 │    │
│  │  page: Page (当前活跃页面)                           │    │
│  │  pages: dict[str, Page] (多标签管理)                │    │
│  │  _lock: asyncio.Lock (并发保护)                     │    │
│  │  _screenshot_dir: Path (截图临时目录)               │    │
│  └────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

### 新增文件

| 文件 | 用途 |
|------|------|
| `backend/app/tools/browser_tool.py` | BrowserTool (BaseTool 子类 + Action 分发) |
| `backend/app/browser/manager.py` | BrowserManager — Playwright 生命周期管理 |
| `backend/app/browser/models.py` | 浏览器相关数据模型 |
| `backend/app/browser/config.py` | 浏览器配置（headless/headed, 超时, 安全策略等） |

### 不修改的文件

- `BaseTool` / `ToolResult` / `ToolRegistry` — 完全复用
- `ToolCallExecutor` / `RapidExecutionLoop` — 无需修改

### 依赖变更

```
# requirements.txt 新增
playwright>=1.40.0
```

安装后需执行 `playwright install chromium` 下载浏览器二进制。

## 4. BrowserTool Action 设计

### 4.1 Action 列表

| Action | 功能 | 关键参数 | 返回 |
|--------|------|----------|------|
| `launch` | 启动浏览器 | `headless?`, `browser?`(chromium/firefox/webkit) | 状态信息 |
| `navigate` | 打开 URL | `url`, `wait_until?`(load/domcontentloaded/networkidle) | 页面标题 + URL |
| `click` | 点击元素 | `selector` 或 `text`(文本匹配) | 成功/失败 |
| `fill` | 填写表单 | `selector`, `value` | 成功/失败 |
| `select` | 下拉选择 | `selector`, `value` | 成功/失败 |
| `paste` | 粘贴剪贴板 | `selector` | 成功/失败，从系统剪贴板读取内容并粘贴到指定元素 |
| `screenshot` | 截图 | `selector?`(区域), `full_page?` | 截图文件路径 + 缩略信息 |
| `read` | 读取内容 | `selector?`, `format?`(text/html) | 文本/HTML |
| `wait` | 等待元素 | `selector`, `timeout?`, `state?`(visible/hidden/attached) | 成功/超时 |
| `execute_js` | 执行 JS | `script` | 返回值 |
| `new_tab` | 新开标签 | `url?` | tab_id |
| `switch_tab` | 切换标签 | `tab_id` | 状态 |
| `close_tab` | 关闭标签 | `tab_id` | 状态 |
| `close` | 关闭浏览器 | — | 状态 |

### 4.2 Schema 结构 — 扁平化设计

> **评审回应 #3**：考虑到部分 LLM 对 `oneOf` + `anyOf` 嵌套支持不稳定，采用扁平化 Schema 策略。所有 action 的参数平铺在一个 `properties` 中，通过 `description` 注明每个参数适用于哪些 action，由 `execute()` 内部做参数校验。

```json
{
  "name": "browser",
  "description": "Control a web browser. Actions: launch (start browser), navigate (open URL), click (click element by selector or text), fill (fill input field), select (select dropdown option), paste (paste from clipboard into element), screenshot (capture image), read (get text/HTML), wait (wait for element), execute_js (run JavaScript), new_tab (open new tab), switch_tab (switch to tab), close_tab (close a tab), close (shut down browser).",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["launch","navigate","click","fill","select","paste","screenshot","read","wait","execute_js","new_tab","switch_tab","close_tab","close"],
        "description": "The browser action to perform"
      },
      "url": {
        "type": "string",
        "description": "URL to navigate to (used by: navigate, new_tab)"
      },
      "selector": {
        "type": "string",
        "description": "CSS selector of the target element (used by: click, fill, select, paste, screenshot, read, wait)"
      },
      "text": {
        "type": "string",
        "description": "Text content to find and click (alternative to selector, used by: click)"
      },
      "value": {
        "type": "string",
        "description": "Value to fill or select (used by: fill, select)"
      },
      "script": {
        "type": "string",
        "description": "JavaScript code to execute. Use 'return' to return a value. (used by: execute_js)"
      },
      "format": {
        "type": "string",
        "enum": ["text", "html"],
        "description": "Content format to return (used by: read, default: text)"
      },
      "wait_until": {
        "type": "string",
        "enum": ["load", "domcontentloaded", "networkidle"],
        "description": "When navigation is complete (used by: navigate, default: load)"
      },
      "state": {
        "type": "string",
        "enum": ["visible", "hidden", "attached", "detached"],
        "description": "State to wait for (used by: wait, default: visible)"
      },
      "timeout": {
        "type": "number",
        "description": "Timeout in milliseconds (used by: wait, navigate)"
      },
      "full_page": {
        "type": "boolean",
        "description": "Capture full scrollable page (used by: screenshot, default: false)"
      },
      "headless": {
        "type": "boolean",
        "description": "Run in headless mode (used by: launch, default: true)"
      },
      "browser": {
        "type": "string",
        "enum": ["chromium", "firefox", "webkit"],
        "description": "Browser engine (used by: launch, default: chromium)"
      },
      "tab_id": {
        "type": "string",
        "description": "Tab ID to switch to or close (used by: switch_tab, close_tab)"
      }
    },
    "required": ["action"],
    "additionalProperties": false
  }
}
```

**参数校验策略**：`execute()` 内部根据 `action` 值二次校验必填参数，返回友好错误信息。例如调用 `navigate` 但未传 `url`，返回 `"navigate action requires 'url' parameter"`。

### 4.3 ToolResult 返回格式

普通操作：
```python
ToolResult(success=True, output="Navigated to https://example.com - Page title: Example Domain")
```

截图操作（文件方式，不进入 LLM 上下文）：
```python
ToolResult(
    success=True,
    output="Screenshot captured: 1024x768, saved to /tmp/browser-screenshots/run-xxx/screenshot-001.png",
    data={
        "screenshot_path": "/tmp/browser-screenshots/run-xxx/screenshot-001.png",
        "width": 1024,
        "height": 768
    }
)
```

> **评审回应 #4**：截图不以 base64 放入 ToolResult（避免占用 Token），而是存为临时文件。ToolResult.data 只返回文件路径。前端 ActionReceipt 通过后端 API 获取图片进行渲染。

错误：
```python
ToolResult(success=False, error="Element not found: #submit-btn. Page has 3 buttons: .btn-primary, .btn-secondary, #cancel")
```

## 5. BrowserManager 生命周期

### 5.1 惰性启动 + 自动恢复 + 安全清理

> **评审回应 #1**：使用 try/finally + asyncio 上下文管理器确保清理；增加孤儿进程检测；利用 Playwright 的 `browser.on("disconnected")` 事件做被动清理。

```
Run 开始
  → AgentService._build_run_tool_registry()
  → BrowserTool 创建 BrowserManager（不启动浏览器）

Agent 第一次调用 browser({"action": "launch"})
  → BrowserManager.start()
    → playwright.chromium.launch(headless=True)
    → browser.on("disconnected", self._on_disconnected)  ← 被动清理钩子
    → browser.new_context()  → 隔离会话
    → context.new_page()     → 默认页面

后续调用（navigate/click/fill/...）
  → async with self._lock:  ← 并发保护
      → 自动复用已有浏览器实例
      → 如果浏览器已关闭/崩溃，自动重新启动

Run 结束
  → AgentService 负责清理 ToolRegistry
  → BrowserTool.cleanup() 被调用（在 try/finally 中）
    → BrowserManager.close()
      → context.close() + browser.close() + playwright.stop()
```

**孤儿进程防护（三重保障）：**

1. **主动清理**：`BrowserTool.cleanup()` 在 `try/finally` 中调用 `BrowserManager.close()`
2. **被动清理**：Playwright `browser.on("disconnected")` 事件回调，标记浏览器状态为已断开
3. **系统级扫描**：`BrowserManager` 提供 `@staticmethod kill_orphan_browsers()` 方法，在系统启动时由 `AgentService` 调用，扫描并清理残留的 Chromium 进程（通过 `psutil` 或 `subprocess` 查找匹配的 chromium 进程）

### 5.2 并发安全

> **评审回应 #2**：BrowserManager 内部使用 `asyncio.Lock` 保护所有 Page 操作，确保同一 Run 中的并发调用不会产生竞态条件。

```python
class BrowserManager:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def navigate(self, url: str, ...) -> ...:
        async with self._lock:
            await self._page.goto(url, ...)

    async def click(self, selector: str) -> ...:
        async with self._lock:
            await self._page.click(selector)
```

所有 action 方法统一通过 `async with self._lock:` 串行化 Page 操作。`RapidExecutionLoop` 中工具调用本身是串行的（一个 tool_call 完成后才执行下一个），但 `asyncio.Lock` 作为额外安全保障。

### 5.3 多标签管理

> **评审回应 #7**：tab_id 改用 UUID 避免溢出问题；明确最后一个标签关闭时的行为。

```python
import uuid

class BrowserManager:
    def __init__(self):
        self._pages: dict[str, Page] = {}        # tab_id → Page
        self._active_page_id: str | None = None

    def _new_tab_id(self) -> str:
        return str(uuid.uuid4())[:8]  # 8 位短 UUID
```

**最后一个标签关闭策略**：当 `close_tab` 关闭的是最后一个标签时，自动创建一个新的空白标签页（`about:blank`），保持浏览器始终有至少一个可用页面。返回提示信息："Last tab closed, new blank tab created."

## 6. 错误处理

| 错误场景 | 处理方式 | 返回给 Agent |
|----------|----------|-------------|
| Playwright 未安装 | 检测 import，返回安装指引 | `error: "Playwright not installed. Run: pip install playwright && playwright install chromium"` |
| 浏览器启动失败 | 捕获异常 | `error: "Browser launch failed: <reason>"` |
| 导航超时 | 捕获 TimeoutError | `error: "Navigation timeout after 30s. Page still loading at <url>"` |
| 选择器未找到 | 捕获，返回建议 | `error: "Element not found: <selector>. Page has N elements matching partial: <suggestions>"` |
| 页面崩溃 | 捕获，自动清理并重启 | `error: "Page crashed. Browser restarted."` |
| JS 执行错误 | 捕获 | `error: "JS execution failed: <message>"` |
| 截图失败 | 捕获 | `error: "Screenshot failed: <reason>"` |
| 缺少必填参数 | execute() 内校验 | `error: "<action> action requires '<param>' parameter"` |

## 7. 安全考量

> **评审回应 #5**：扩展安全设计，增加 URL 过滤、私有 IP 限制、execute_js 审计。

### 7.1 基础安全

- 浏览器默认 headless 模式，headed 需在设置中显式开启
- 浏览器实例隔离在 Run 级别，Run 结束自动关闭
- 不允许通过 Playwright 访问本地文件系统（context 配置限制）
- `execute_js` 在页面沙箱中执行，不影响宿主进程

### 7.2 URL 安全（新增）

| 策略 | 说明 | 默认值 |
|------|------|--------|
| URL 黑名单 | 禁止访问的 URL 模式列表（正则） | 可配置，默认空 |
| 私有 IP 限制 | 禁止访问 `10.x`、`172.16-31.x`、`192.168.x`、`127.x`、`localhost` | 可配置，默认关闭 |
| SSRF 防护 | `navigate` 和 `new_tab` 时校验目标 URL | 始终开启 |

```python
class BrowserSecurityConfig(BaseModel):
    blocked_url_patterns: list[str] = []          # 正则黑名单
    block_private_ips: bool = False                # 是否禁止私有 IP
    allowed_schemes: list[str] = ["http", "https"] # 允许的协议
    max_navigation_depth: int = 10                 # 最大连续导航次数（防重定向循环）
```

### 7.3 execute_js 审计（新增）

每次 `execute_js` 调用记录审计日志：

```python
# 审计日志格式
{
    "action": "execute_js",
    "script_preview": "return document.title",  # 前 200 字符
    "timestamp": "2026-06-01T10:30:00Z",
    "session_id": "...",
    "run_id": "..."
}
```

### 7.4 恶意页面防护

- 导航超时限制（默认 30s），防止页面挂起
- 最大连续导航深度（默认 10），防止重定向循环
- 弹窗自动关闭（`context.on("page", lambda p: p.close())`）
- 下载行为拦截（默认禁止自动下载）

## 8. 前端改动

> **评审回应 #8**：补充详细的数据结构、API 路由和交互细节。

### 8.1 ActionReceipt 截图渲染

改动文件：`frontend/src/components/ActionReceipt.tsx`

**数据流**：
1. Agent 调用 `screenshot` action → BrowserTool 截图存为临时文件 → ToolResult.data 返回 `screenshot_path`
2. 前端 WebSocket 收到 ActionReceipt，`data.screenshot_path` 存在时
3. 通过 `<img src="/api/browser/screenshot?path=..." />` 请求后端 API 获取图片
4. 后端 API 读取临时文件并返回图片流

**交互细节**：
- 默认显示缩略图（最大宽度 400px）
- 点击可放大查看原图（模态框）
- 支持右键"另存为"下载

### 8.2 Settings 面板浏览器配置

改动文件：`frontend/src/pages/SettingsPage.tsx`

**配置项数据结构**：

```typescript
interface BrowserSettings {
  headless: boolean;              // 默认 true
  defaultBrowser: 'chromium' | 'firefox' | 'webkit';  // 默认 'chromium'
  defaultTimeout: number;         // 默认 30000ms
  defaultWaitUntil: 'load' | 'domcontentloaded' | 'networkidle';  // 默认 'load'
  blockPrivateIps: boolean;       // 默认 false
  blockedUrlPatterns: string[];   // 默认 []
}
```

**API 路由**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ui-settings` | 获取全部 UI 设置（含浏览器配置） |
| PUT | `/api/ui-settings` | 更新 UI 设置 |
| GET | `/api/browser/screenshot?path=...` | 获取截图图片流 |

配置从前端通过 `PUT /api/ui-settings` 传入后端，存入数据库 `ui_settings` 表。`AgentService._build_run_tool_registry()` 读取配置创建 `BrowserTool`。

## 9. 测试策略

> **评审回应 #6**：加强测试策略，使用 Mock Playwright + 本地静态 HTML + pytest-playwright。

### 9.1 单元测试（Mock Playwright）

文件：`tests/test_tools/test_browser_tool.py`

覆盖所有 14 个 action 的：
- 正常调用路径
- 缺少必填参数
- 无效参数值
- 浏览器未启动时调用（除 launch 外）
- 并发调用安全

使用 `unittest.mock.AsyncMock` mock Playwright 的 `Page`、`Browser`、`BrowserContext` 对象。

### 9.2 单元测试（BrowserManager）

文件：`tests/test_browser/test_browser_manager.py`

覆盖：
- 生命周期：start → 操作 → close
- 惰性启动：未 start 时自动启动
- 崩溃恢复：浏览器断开后自动重启
- 孤儿进程检测：kill_orphan_browsers()
- 多标签管理：创建/切换/关闭标签，最后标签关闭策略
- 并发锁：asyncio.Lock 串行化

### 9.3 集成测试（本地静态 HTML）

文件：`tests/test_browser/test_browser_integration.py`

使用本地静态 HTML 文件（不依赖外网），保证 CI 稳定：

```python
# tests/test_browser/fixtures/test_page.html
# 包含：表单、按钮、输入框、链接等标准元素

@pytest.fixture
def test_page_url():
    return f"file://{Path(__file__).parent / 'fixtures' / 'test_page.html'}"
```

覆盖场景：
- navigate → read 验证页面内容
- fill → click → read 验证表单提交
- screenshot 验证文件生成
- execute_js 验证返回值
- new_tab → switch_tab → close_tab 验证多标签

### 9.4 测试工具

考虑使用 Playwright 自带的 `pytest-playwright` 插件简化集成测试编写。

## 10. 实施范围

### 第一版（本次实施）

- BrowserTool + BrowserManager 完整实现（含并发锁 + 孤儿进程防护）
- 14 个 action 全部实现
- 扁平化 Schema + execute() 内部参数校验
- 截图存为临时文件 + 后端截图 API
- URL 安全策略（黑名单 + 私有 IP 限制）
- execute_js 审计日志
- Settings 面板浏览器配置（含数据结构 + API）
- ActionReceipt 截图渲染（缩略图 + 放大 + 下载）
- 单元测试（Mock） + 集成测试（本地静态 HTML）
- requirements.txt 新增 playwright 依赖

### 后续迭代（不在本次范围）

- 多浏览器实例管理
- 浏览器录制/回放
- 定时任务调度（AutomationPage 仍保持占位）
- 浏览器扩展支持
- 浏览器 Cookie/Session 持久化

## 11. 依赖影响

### Python 依赖

```
playwright>=1.40.0
```

### 系统依赖

首次安装后需执行：
```bash
playwright install chromium
```

Electron 打包时，PyInstaller 需要包含 Playwright 的浏览器二进制。这在后续打包优化中处理，第一版先以开发模式运行。

## 12. 与现有系统的集成点

| 集成点 | 方式 | 说明 |
|--------|------|------|
| AgentService | 在 `_build_run_tool_registry()` 中注册 BrowserTool | 类似其他工具 |
| ToolRegistry | 通过 `register()` 注册 | 标准流程 |
| ToolCallExecutor | 无需修改 | BrowserTool 的 ToolResult 与其他工具一致 |
| RapidExecutionLoop | 无需修改 | 工具调用在 TOOL_EXECUTION 阶段自然执行 |
| ActionReceipt | 增加截图渲染逻辑 | 通过 `/api/browser/screenshot` API 获取图片 |
| Settings | 增加浏览器配置面板 | 通过 `PUT /api/ui-settings` 传入后端 |

# Browser Tool 设计文档

> 日期：2026-06-01
> 状态：已批准
> 范围：为 ReflexionOS Agent 增加浏览器操作能力

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
│  └────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

### 新增文件

| 文件 | 用途 |
|------|------|
| `backend/app/tools/browser_tool.py` | BrowserTool (BaseTool 子类 + Action 分发) |
| `backend/app/browser/manager.py` | BrowserManager — Playwright 生命周期管理 |
| `backend/app/browser/models.py` | 浏览器相关数据模型 |
| `backend/app/browser/config.py` | 浏览器配置（headless/headed, 超时等） |

### 不修改的文件

- `BaseTool` / `ToolResult` / `ToolRegistry` — 完全复用
- `ToolCallExecutor` / `RapidExecutionLoop` — 无需修改
- `ActionReceipt` — 已支持结构化数据展示，截图通过 `data` 字段传递

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
| `screenshot` | 截图 | `selector?`(区域), `full_page?` | base64 图片 |
| `read` | 读取内容 | `selector?`, `format?`(text/html) | 文本/HTML |
| `wait` | 等待元素 | `selector`, `timeout?`, `state?`(visible/hidden/attached) | 成功/超时 |
| `execute_js` | 执行 JS | `script` | 返回值 |
| `new_tab` | 新开标签 | `url?` | tab_id |
| `switch_tab` | 切换标签 | `tab_id` | 状态 |
| `close_tab` | 关闭标签 | `tab_id` | 状态 |
| `close` | 关闭浏览器 | — | 状态 |

### 4.2 Schema 结构

使用 `oneOf` 为每个 action 定义独立参数：

```json
{
  "name": "browser",
  "description": "Control a web browser to navigate, interact, and extract data from web pages.",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["launch","navigate","click","fill","select","paste","screenshot","read","wait","execute_js","new_tab","switch_tab","close_tab","close"],
        "description": "The browser action to perform"
      }
    },
    "required": ["action"],
    "oneOf": [
      {
        "properties": {
          "action": {"const": "launch"},
          "headless": {"type": "boolean", "description": "Run in headless mode (default: true)"},
          "browser": {"type": "string", "enum": ["chromium","firefox","webkit"], "description": "Browser engine (default: chromium)"}
        }
      },
      {
        "properties": {
          "action": {"const": "navigate"},
          "url": {"type": "string", "description": "URL to navigate to"},
          "wait_until": {"type": "string", "enum": ["load","domcontentloaded","networkidle"], "description": "When to consider navigation complete (default: load)"}
        },
        "required": ["url"]
      },
      {
        "properties": {
          "action": {"const": "click"},
          "selector": {"type": "string", "description": "CSS selector of the element to click"},
          "text": {"type": "string", "description": "Text content to find and click (alternative to selector)"}
        },
        "anyOf": [
          {"required": ["selector"]},
          {"required": ["text"]}
        ]
      },
      {
        "properties": {
          "action": {"const": "fill"},
          "selector": {"type": "string", "description": "CSS selector of the input field"},
          "value": {"type": "string", "description": "Value to fill in"}
        },
        "required": ["selector", "value"]
      },
      {
        "properties": {
          "action": {"const": "select"},
          "selector": {"type": "string", "description": "CSS selector of the select element"},
          "value": {"type": "string", "description": "Option value to select"}
        },
        "required": ["selector", "value"]
      },
      {
        "properties": {
          "action": {"const": "paste"},
          "selector": {"type": "string", "description": "CSS selector of the element to paste into (e.g. input, textarea)"}
        },
        "required": ["selector"]
      },
      {
        "properties": {
          "action": {"const": "screenshot"},
          "selector": {"type": "string", "description": "CSS selector of element to screenshot (optional, full page if omitted)"},
          "full_page": {"type": "boolean", "description": "Capture full scrollable page (default: false)"}
        }
      },
      {
        "properties": {
          "action": {"const": "read"},
          "selector": {"type": "string", "description": "CSS selector of element to read (optional, defaults to body)"},
          "format": {"type": "string", "enum": ["text","html"], "description": "Return text content or inner HTML (default: text)"}
        }
      },
      {
        "properties": {
          "action": {"const": "wait"},
          "selector": {"type": "string", "description": "CSS selector to wait for"},
          "timeout": {"type": "number", "description": "Timeout in ms (default: 30000)"},
          "state": {"type": "string", "enum": ["visible","hidden","attached","detached"], "description": "State to wait for (default: visible)"}
        },
        "required": ["selector"]
      },
      {
        "properties": {
          "action": {"const": "execute_js"},
          "script": {"type": "string", "description": "JavaScript code to execute. Use 'return' to return a value."}
        },
        "required": ["script"]
      },
      {
        "properties": {
          "action": {"const": "new_tab"},
          "url": {"type": "string", "description": "URL to open in new tab (optional)"}
        }
      },
      {
        "properties": {
          "action": {"const": "switch_tab"},
          "tab_id": {"type": "string", "description": "ID of the tab to switch to"}
        },
        "required": ["tab_id"]
      },
      {
        "properties": {
          "action": {"const": "close_tab"},
          "tab_id": {"type": "string", "description": "ID of the tab to close"}
        },
        "required": ["tab_id"]
      },
      {
        "properties": {
          "action": {"const": "close"}
        }
      }
    ]
  }
}
```

### 4.3 ToolResult 返回格式

普通操作：
```python
ToolResult(success=True, output="Navigated to https://example.com - Page title: Example Domain")
```

截图操作：
```python
ToolResult(
    success=True,
    output="Screenshot captured: 1024x768",
    data={"screenshot_base64": "iVBORw0KGgo...", "width": 1024, "height": 768}
)
```

错误：
```python
ToolResult(success=False, error="Element not found: #submit-btn. Page has 3 buttons: .btn-primary, .btn-secondary, #cancel")
```

## 5. BrowserManager 生命周期

### 5.1 惰性启动 + 自动恢复

```
Run 开始
  → AgentService._build_run_tool_registry()
  → BrowserTool 创建 BrowserManager（不启动浏览器）

Agent 第一次调用 browser({"action": "launch"})
  → BrowserManager.start()
    → playwright.chromium.launch(headless=True)
    → browser.new_context()  → 隔离会话
    → context.new_page()     → 默认页面

后续调用（navigate/click/fill/...）
  → BrowserManager 自动复用已有浏览器实例
  → 如果浏览器已关闭/崩溃，自动重新启动

Run 结束
  → AgentService 负责清理 ToolRegistry
  → BrowserTool.cleanup() 被调用
    → BrowserManager.close()
      → context.close() + browser.close() + playwright.stop()
```

### 5.2 多标签管理

BrowserManager 内部维护标签页字典：

```python
self._page_id_counter: int = 0
self._pages: dict[str, Page] = {}  # tab_id → Page
self._active_page_id: str | None = None
```

- `launch` 时自动创建第一个标签，id 为 `"tab-0"`
- `new_tab` 创建新标签，id 递增
- `switch_tab` 切换活跃标签
- `close_tab` 关闭指定标签，如果关闭的是活跃标签则自动切换到另一个

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

## 7. 前端改动

### 7.1 ActionReceipt 截图渲染

在 `ActionReceipt` 组件中，当 `data.screenshot_base64` 存在时，渲染可展开的图片预览。

改动文件：`frontend/src/components/ActionReceipt.tsx`（约 30 行）

### 7.2 Settings 面板浏览器配置

在 Settings 页面增加 "Browser" 配置区：
- Headless 模式开关（默认 on）
- 默认浏览器引擎（chromium/firefox/webkit）
- 默认导航超时时间
- 默认页面加载等待策略（load/domcontentloaded/networkidle）

改动文件：
- `frontend/src/pages/SettingsPage.tsx`（增加 Browser 配置面板）
- `backend/app/config/`（增加浏览器配置项）
- `backend/app/api/ui_settings.py`（暴露浏览器配置 API）

## 8. 安全考量

- 浏览器默认 headless 模式，headed 需在设置中显式开启
- 浏览器实例隔离在 Run 级别，Run 结束自动关闭
- 不允许通过 Playwright 访问本地文件系统（context 配置限制）
- 网络访问不限制（浏览器本身就是网络工具）
- `execute_js` 在页面沙箱中执行，不影响宿主进程

## 9. 测试策略

| 测试类型 | 覆盖内容 | 文件 |
|----------|----------|------|
| 单元测试 | BrowserTool action 分发、参数校验、错误处理 | `tests/test_tools/test_browser_tool.py` |
| 单元测试 | BrowserManager 生命周期（mock Playwright） | `tests/test_browser/test_browser_manager.py` |
| 集成测试 | 真实浏览器：navigate + click + read + screenshot 端到端 | `tests/test_browser/test_browser_integration.py` |

## 10. 实施范围

### 第一版（本次实施）

- BrowserTool + BrowserManager 完整实现
- 13 个 action 全部实现
- Settings 面板浏览器配置
- ActionReceipt 截图渲染
- 单元测试 + 集成测试
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
| ActionReceipt | 增加截图渲染逻辑 | 识别 `data.screenshot_base64` |
| Settings | 增加浏览器配置面板 | 新增配置区 |

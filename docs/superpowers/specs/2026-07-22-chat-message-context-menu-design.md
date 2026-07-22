# 聊天消息右键复制菜单 设计文档

日期：2026-07-22

## 背景

桌面版对话区域的消息文本，右键点击时没有可用的"复制"选项。根因调研（详见对应调研记录）：

- Electron 主进程（`frontend/electron/main.cjs`）没有注册任何 `context-menu` 拦截或 `Menu.buildFromTemplate`，右键行为完全交给 Chromium 默认逻辑。
- 项目现有的"复制"交互统一走的是**显式按钮**模式（`navigator.clipboard.writeText()`），例如 `MarkdownRenderer.tsx` 代码块复制按钮、`MessageActions.tsx` 消息复制按钮 —— 都是 hover 才出现的图标按钮，不是右键菜单。
- 用户希望聊天消息区域能有一个真正的、自定义的右键菜单（类似 VSCode/浏览器原生右键菜单的体验），而不是继续依赖悬浮按钮。

## 目标与范围

**本次要做：**
- 聊天消息区域（用户消息 + 助手消息）支持右键弹出自定义菜单
- 菜单目前只包含一项："复制"
- 复制语义：有文本选区时复制选区内容；无选区时复制整条消息全文
- 助手消息（Markdown 渲染）复制的是**原始 Markdown 源码**，不是渲染后的纯文本
- 关闭方式：点击菜单外区域关闭、Esc 关闭；菜单靠近窗口边缘时自动反弹避免被裁剪
- 复制成功后 toast 提示，与现有复制按钮行为一致

**本次不做：**
- 不把"编辑""重新生成"等操作塞进右键菜单（保留现状，仍用现有悬浮按钮）
- 不做"复制为纯文本"这类额外菜单项
- 不做子菜单/多级菜单
- 不改动 Electron 主进程（`main.cjs`/`preload.cjs`），纯渲染层实现
- 不重构现有 `MessageActions.tsx` 和 `UserMessageItem.tsx` 内联的悬浮复制按钮逻辑——两者与新右键菜单并存，作为两条独立的复制入口

## 现状调研摘要

- 用户消息：`frontend/src/components/workspace/UserMessageItem.tsx`，消息文本是纯文本 `<div>`（第 103-105 行附近，`whitespace-pre-wrap`），不经过 Markdown 渲染。组件内部（第 107-133 行）自行实现了一份 hover 复制/编辑按钮。
- 助手消息：`frontend/src/components/workspace/AssistantMessageItem.tsx`，文本通过 `frontend/src/components/chat/MarkdownRenderer.tsx` 渲染（`variant="plain"`）。复制按钮来自独立组件 `frontend/src/components/workspace/MessageActions.tsx`，仅用于助手消息。
- 项目 UI 组件库现状：`frontend/src/components/ui/` 目录不存在，未引入 Radix UI / Headless UI / floating-ui 等弹层库。项目里唯一的全局浮层先例是 `frontend/src/components/common/ConfirmDialog.tsx`（居中模态，`framer-motion` 动画 + Esc 关闭 + 焦点陷阱）配合 `frontend/src/shared/stores/confirmDialog.store.ts`（zustand 单例 + Promise resolve 桥接），并在 `App.tsx` 顶层挂载 Host 组件。
- 消息文本容器目前没有 `user-select: none`，天然支持鼠标拖拽选中，右键菜单可以直接依赖 `window.getSelection()` 判断选区。

## 架构设计

沿用项目已有的"全局单例浮层"模式（对齐 `ConfirmDialog.tsx` / `confirmDialog.store.ts`），新增三个文件：

### 1. `frontend/src/shared/stores/contextMenu.store.ts`（新建）

zustand store，管理菜单的开关状态与内容：

```ts
interface ContextMenuItem {
  label: string
  onClick: () => void
}

interface ContextMenuState {
  isOpen: boolean
  x: number
  y: number
  items: ContextMenuItem[]
  open: (x: number, y: number, items: ContextMenuItem[]) => void
  close: () => void
}
```

同一时刻只允许一个菜单实例打开，`open()` 直接覆盖上一次的状态（对齐 `confirmDialog.store.ts` 的单例约束）。

### 2. `frontend/src/components/common/ContextMenu.tsx`（新建）

全局 Host 组件，挂载在 `App.tsx` 顶层（与 `ConfirmDialogHost`、`ToastContainer` 并列）。

- 订阅 `contextMenu.store`，`isOpen` 为 true 时渲染 `fixed` 定位面板，初始坐标为鼠标点击处 `(x, y)`
- 用 `framer-motion` 的 `AnimatePresence` + `motion.div` 做进出场动画，视觉风格对齐 `ConfirmDialog.tsx`（轻微缩放/淡入淡出）
- 渲染后测量菜单实际尺寸（`getBoundingClientRect`），若超出窗口右边界则以 `x` 为右边界反向定位，若超出下边界则以 `y` 为下边界反向定位
- 关闭逻辑：
  - 监听 `mousedown`，点击落在菜单容器外时关闭（用 ref 判断，避免和触发右键的 `contextmenu` 事件冲突）
  - 监听 `keydown` 的 Esc，关闭（对齐 `ConfirmDialog.tsx` 现有键盘处理模式）
- 菜单项直接渲染 `items` 数组，每项点击后先执行 `onClick()` 再关闭菜单

### 3. `frontend/src/shared/hooks/useMessageContextMenu.ts`（新建）

供两种消息组件复用的公共 hook，封装"取复制文本 + 打开菜单"的逻辑：

```ts
function useMessageContextMenu(getFullText: () => string) {
  return (e: React.MouseEvent) => {
    e.preventDefault()
    const selection = window.getSelection()
    const selectedText = selection && !selection.isCollapsed ? selection.toString() : ''
    const textToCopy = selectedText || getFullText()

    contextMenuStore.getState().open(e.clientX, e.clientY, [
      {
        label: '复制',
        onClick: () => {
          navigator.clipboard.writeText(textToCopy).catch(() => {})
          toast.success('已复制到剪贴板') // 具体调用方式对齐项目现有 toast 用法
        },
      },
    ])
  }
}
```

选区判断只看 `selection.isCollapsed`，不额外校验选区是否落在当前消息容器内——跨消息选中并右键时，直接复制浏览器给出的选区文本，行为等同原生右键菜单，符合"有选区复制选区"的直觉。

### 4. 接入两处消息组件

- `UserMessageItem.tsx`：给消息文本容器 div 加 `onContextMenu={useMessageContextMenu(() => contentText)}`
- `AssistantMessageItem.tsx`：给包裹 `MarkdownRenderer` 的外层容器加 `onContextMenu={useMessageContextMenu(() => contentText)}`，`contentText` 取的是传给 `MarkdownRenderer` 的原始 Markdown 字符串（与现有 `MessageActions.tsx` 复制按钮用的是同一个变量，保证两个复制入口结果一致）

不修改 `MarkdownRenderer.tsx` 内部代码块的独立复制按钮逻辑——那是更细粒度的"只复制这个代码块"，与整条消息右键复制是两个不冲突的功能。

## 数据流

```
用户右键点击消息文本
  → onContextMenu handler (useMessageContextMenu)
    → 读取 window.getSelection()
    → 决定复制内容（选区 or 整条消息 contentText）
    → contextMenu.store.open(x, y, [{ label: '复制', onClick }])
      → ContextMenu.tsx 检测到 isOpen=true，渲染菜单
用户点击"复制"菜单项
  → 执行 onClick：navigator.clipboard.writeText + toast 提示
  → 菜单关闭
用户点击菜单外 / 按 Esc
  → contextMenu.store.close()
  → 菜单关闭，不执行任何复制
```

## 兼容性

- Electron 主进程/预加载脚本不涉及改动，纯渲染层 React 组件 + zustand store，天然跨 Windows/macOS 一致。
- `navigator.clipboard.writeText` 是标准 Web API，在 Electron 的 `BrowserWindow`（`nodeIntegration: false`, `contextIsolation: true`）环境下可直接使用，与现有 `MessageActions.tsx`/`MarkdownRenderer.tsx` 的用法一致，无需额外权限配置。

## 测试要点

- 用户消息、助手消息分别右键，菜单能正常弹出且定位在鼠标处
- 有选区时右键 → 复制的是选区文本；无选区时右键 → 复制整条消息全文
- 助手消息复制结果应为原始 Markdown 源码（含 `` ``` `` 代码块标记、`**` 加粗符号等），不是渲染后剥离标记的纯文本
- 点击菜单外区域、按 Esc，两种方式都能关闭菜单且不触发复制
- 菜单在窗口右侧/下侧边缘弹出时不被裁剪，能正确反弹方向
- 复制成功后出现 toast 提示
- 跨平台（Windows + macOS）验证右键事件触发和剪贴板写入均正常

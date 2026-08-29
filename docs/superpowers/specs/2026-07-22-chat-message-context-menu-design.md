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
- 复制语义（消除歧义，明确写死）：
  - 有文本选区时：复制**用户当前选中的可见文本**（即 `window.getSelection().toString()`），不区分用户消息/助手消息，也不尝试从渲染结果反推 Markdown 子串
  - 无选区时：用户消息复制整条消息全文；助手消息复制**传给 `MarkdownRenderer` 的原始 Markdown 字符串**（含 `` ``` `` 代码块标记、`**` 加粗符号等原始标记）
- 右键点在 Markdown 链接等交互子元素（如 `<a>`）上时，同样弹出自定义菜单，不保留浏览器原生的"复制链接地址"等能力（Phase 1 统一按消息内容区域处理，不区分子元素类型）
- 关闭方式：点击菜单外区域关闭、Esc 关闭；菜单靠近窗口边缘时自动反弹避免被裁剪
- 复制成功后 toast 提示，复制失败也需提示，行为与现有复制按钮一致（见下方"复制成功/失败反馈"）

**本次不做：**
- 不把"编辑""重新生成"等操作塞进右键菜单（保留现状，仍用现有悬浮按钮）
- 不做"复制为纯文本"这类额外菜单项
- 不做子菜单/多级菜单
- 不改动 Electron 主进程（`main.cjs`/`preload.cjs`），纯渲染层实现
- 不重构现有 `MessageActions.tsx` 和 `UserMessageItem.tsx` 内联的悬浮复制按钮逻辑——两者与新右键菜单并存，作为两条独立的复制入口
- 不为 Markdown 链接等子元素保留原生右键菜单（见上方"Phase 1 统一"决策），如后续有需求可在 Phase 2 单独评估

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
import { useToastStore } from '@/shared/stores/toast.store' // 路径以实际项目结构为准

function useMessageContextMenu(getFullText: () => string) {
  return (e: React.MouseEvent) => {
    e.preventDefault()
    const selection = window.getSelection()
    const selectedText = selection && !selection.isCollapsed ? selection.toString() : ''
    const textToCopy = selectedText || getFullText()

    contextMenuStore.getState().open(e.clientX, e.clientY, [
      {
        label: '复制',
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(textToCopy)
            useToastStore.getState().addToast('info', '已复制到剪贴板', 2000)
          } catch {
            useToastStore.getState().addToast('error', '复制失败')
          }
        },
      },
    ])
  }
}
```

接口对齐项目现有实现（`MessageActions.tsx` 第 22-30 行、`UserMessageItem.tsx` 第 113-119 行）：`useToastStore.getState().addToast(type, message, duration?)`。成功 toast 必须在 `writeText` 的 Promise resolve 之后才触发，失败时提示 `error` toast，不能像早期草稿那样无论成败都提示成功。

选区判断只看 `selection.isCollapsed`，不额外校验选区是否落在当前消息容器内——跨消息选中并右键时，直接复制浏览器给出的选区文本，行为等同原生右键菜单，符合"有选区复制选区"的直觉。**注意**：这意味着有选区时，无论是用户消息还是助手消息，复制的都是"可见文本"而非"原始 Markdown"——"复制原始 Markdown"这条规则只在助手消息**无选区**（复制整条消息）时生效。这是本设计刻意的取舍，实现和测试都必须按此执行，不能理解为"助手消息任何情况下复制都拿原始 Markdown"。

### 4. 接入两处消息组件

- `UserMessageItem.tsx`：给消息文本容器 div 加 `onContextMenu={useMessageContextMenu(() => contentText)}`
- `AssistantMessageItem.tsx`：给包裹 `MarkdownRenderer` 的外层容器加 `onContextMenu={useMessageContextMenu(() => contentText)}`，`contentText` 取的是传给 `MarkdownRenderer` 的原始 Markdown 字符串（与现有 `MessageActions.tsx` 复制按钮用的是同一个变量，保证两个复制入口结果一致）

不修改 `MarkdownRenderer.tsx` 内部代码块的独立复制按钮逻辑——那是更细粒度的"只复制这个代码块"，与整条消息右键复制是两个不冲突的功能。

**链接等交互子元素的右键行为（产品取舍，已定案）**：`onContextMenu` 挂在消息外层容器上，事件冒泡到容器时统一弹出自定义菜单，不对 `e.target` 做类型判断。这意味着右键点在 Markdown 链接（`MarkdownRenderer.tsx` 第 85-93 行的 `<a>` 渲染）上时，同样弹出"复制"菜单，而不是 Chromium 原生的"复制链接地址"菜单。Phase 1 明确采用这种统一最小化处理；如果后续用户反馈需要链接专属的"复制链接地址"，作为 Phase 2 需求单独评估（需要在 handler 里判断 `e.target instanceof HTMLAnchorElement` 并分流到不同菜单项）。

## 数据流

```
用户右键点击消息文本
  → onContextMenu handler (useMessageContextMenu)
    → 读取 window.getSelection()
    → 决定复制内容（选区 or 整条消息 contentText）
    → contextMenu.store.open(x, y, [{ label: '复制', onClick }])
      → ContextMenu.tsx 检测到 isOpen=true，渲染菜单
用户点击"复制"菜单项
  → 执行 onClick：await navigator.clipboard.writeText
    → 成功 → toast 'info' 已复制到剪贴板
    → 失败 → toast 'error' 复制失败
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
- 助手消息右键点在 Markdown 链接文字上，同样弹出自定义"复制"菜单，不出现浏览器原生的"复制链接地址"选项
- 无选区时右键：用户消息复制整条消息全文；助手消息复制结果应为**原始 Markdown 源码**（含 `` ``` `` 代码块标记、`**` 加粗符号等），不是渲染后剥离标记的纯文本
- 有选区时右键（用户消息、助手消息均适用）：复制的是**选中的可见文本**，即使选区落在助手消息里，也不会拿到原始 Markdown 标记——这是与"无选区"分支不同的独立行为，需要单独测试用例覆盖，防止和上一条混淆
- 点击菜单外区域、按 Esc，两种方式都能关闭菜单且不触发复制
- 菜单在窗口右侧/下侧边缘弹出时不被裁剪，能正确反弹方向
- 复制成功后出现 'info' toast 提示；模拟 `navigator.clipboard.writeText` 抛错时，出现 'error' toast 且不误报成功
- 跨平台（Windows + macOS）验证右键事件触发和剪贴板写入均正常

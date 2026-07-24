# 代码面板改为右侧可折叠侧栏 设计文档

日期：2026-07-24

## 背景

当前"对话"与"代码"是主区里互斥的两个 tab（`AgentWorkspace.tsx` 用 `hidden` class 切换显隐），点击"代码"tab 后对话完全被顶替，看不到对话内容；且存在 Windows 下文件树接口报错导致代码 tab 打不开的 bug（已单独修复，见 [devlog-2026-06-23_to_present.md](../devlog/devlog-2026-06-23_to_present.md) 2026-07-24 记录）。

用户希望改成类似 Codex 客户端的布局：对话始终是主区内容，代码作为右侧可展开/收起的面板，两者同时可见，不用切换。

## 目标与范围

**本次要做：**
- 移除"对话/代码"tab 切换，对话（`WorkspaceTranscript` + `ChatInput`）始终占据主区
- 代码面板（`CodeTab` + `FileSidebar` + `TerminalPanel`）改为固定在右侧、可展开/收起的面板
- 面板默认**收起**
- 面板展开时宽度**固定**（非按比例），默认 480px，可拖拽调整，调整后的宽度持久化保存（跨会话/重启记忆）
- Header 上的"对话/代码"切换按钮替换为一个"展开/收起代码面板"的图标按钮
- 收起时不卸载代码面板内部状态（已打开的文件、编辑内容、终端会话保留），仅隐藏显示
- 跨平台（Windows + macOS）验证拖拽调宽、面板展开/收起动画、持久化状态读写一致

**本次不做：**
- 不改变代码面板内部结构（`CodeTab`/`FileSidebar`/`CodeEditor`/`EditableDiffViewer`/`TerminalPanel` 内部逻辑不动）
- 不做按比例宽度模式（用户已明确选择固定宽度）
- 不做面板浮层/drawer 模式（用户已明确选择两者同时可见的分栏模式）
- 不新增拖拽分隔条的多面板嵌套（代码面板与文件树侧边栏的宽度调整逻辑分别独立，不做联动限制之外的新交互）

## 现状调研摘要

- `frontend/src/pages/AgentWorkspace.tsx`（第 192-243 行）：对话区块和代码区块是两个独立的 flex 子元素，通过 `workspaceTab === 'code' ? '' : 'hidden'` 互斥显隐，`FileSidebar` 只在 `workspaceTab === 'code'` 时额外挂载在最右侧。
- `frontend/src/components/workspace/WorkspaceHeader.tsx`（第 64-79 行）：渲染"对话/代码" tab 切换按钮组，点击调用 `setWorkspaceTab`。
- `frontend/src/features/code/stores/codeTab.store.ts`：`workspaceTab: 'chat' | 'code'` 字段身兼两职——既是当前显示的 tab，又在 `openFile`/`setActiveFile`（第 67-91、164-188 行）里被当作"打开文件后自动跳转到代码 tab"的副作用触发字段。`sidebarOpen`/`sidebarWidth` 已有独立的开关和宽度状态（用于文件树侧边栏，`MIN_SIDEBAR_WIDTH=180`/`MAX_SIDEBAR_WIDTH=480`），但**没有 `persist` 中间件**，刷新页面后宽度和展开状态会丢失。
- `AgentWorkspace.tsx`（第 100-106 行）有一个 `useEffect`，把 `sidebarOpen` 与 `workspaceTab === 'code'` 强制同步（进代码 tab 自动展开文件树，退出自动收起）——这个耦合是本次设计需要理清的点。
- 项目里已有 `persist` + `localStorage` 的先例：`frontend/src/features/terminal/stores/terminal.store.ts`（第 49、125-126 行），用 `zustand/middleware` 的 `persist` + `createJSONStorage(() => localStorage)`。
- `FileSidebar.tsx` 的拖拽调宽逻辑（第 50-74 行）用原生 `mousedown`/`mousemove`/`mouseup` 事件 + `document.body.style.cursor` 控制光标，是可以直接复用的既有模式。

## 架构设计

### 1. 语义拆分：`workspaceTab` → `codePanelOpen`

`codeTab.store.ts` 中：
- 移除 `WorkspaceTab` 类型和 `workspaceTab` 字段、`setWorkspaceTab` action
- 新增 `codePanelOpen: boolean`（默认 `false`）+ `setCodePanelOpen(open: boolean)` + `toggleCodePanel()`
- 新增 `codePanelWidth: number`（默认 480，复用 `MIN_SIDEBAR_WIDTH`/新增 `MAX_CODE_PANEL_WIDTH` 做 clamp，具体范围见下）+ `setCodePanelWidth(width: number)`
- `openFile`/`setActiveFile` 里原来 `workspaceTab: 'code'` 的赋值，改为 `codePanelOpen: true`（打开文件即展开面板，语义不变，只是字段改名）

整个 store 用 `persist` 包裹，`name: 'reflexion-code-panel'`，只持久化 `codePanelOpen` 和 `codePanelWidth`（`partialize`），不持久化 `openFiles`/`activeFileId` 等会话态数据（这些应随会话/项目切换重新加载，不应跨重启残留）。

### 2. `FileSidebar` 联动关系解耦

`AgentWorkspace.tsx` 现有的"进代码 tab 自动展开/收起文件树"`useEffect`（第 100-106 行）改为跟随 `codePanelOpen`：代码面板展开时文件树侧边栏跟随展开，收起代码面板时文件树侧边栏也收起。这保留现状行为语义（文件树是代码面板的从属 UI），只是触发条件从"tab 切换"改为"面板展开状态"。

### 3. 布局重构：`AgentWorkspace.tsx`

新布局结构（从上到下即从左到右）：

```
<div className="flex h-full">
  {/* 对话区：始终渲染，占据剩余空间 */}
  <div className="flex h-full flex-col bg-surface-primary flex-1 min-w-0">
    <WorkspaceHeader {...viewModel.headerProps} />
    <WorkspaceTranscript ... />
    <ChatInput 区块 .../>
  </div>

  {/* 代码面板：固定宽度，展开/收起用 width + overflow 控制，不卸载 */}
  <div
    className="flex h-full shrink-0 overflow-hidden border-l border-edge transition-[width] duration-200"
    style={{ width: codePanelOpen ? codePanelWidth : 0 }}
  >
    <div className="flex h-full flex-col bg-surface-primary" style={{ width: codePanelWidth }}>
      {/* 面板内自己的小 header：文件名/终端切换按钮，从原 WorkspaceHeader 里代码相关按钮迁移过来 */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <CodeTab />
      </div>
      <TerminalPanel />
    </div>
    {/* 拖拽调宽手柄，贴在面板左边缘 */}
    <div onMouseDown={handleResizeMouseDown} className="... cursor-col-resize" />
  </div>

  {/* 文件树侧边栏：保持在最右侧，逻辑不变，仅联动条件改为 codePanelOpen */}
  {codePanelOpen && <FileSidebar />}
</div>
```

关键点：
- 代码面板容器宽度收起时设为 `0`（配合 `overflow-hidden`），而不是加 `hidden` class——这样 CSS transition 才能对 `width` 生效，产生展开/收起的滑动动画；内部 `CodeTab`/`TerminalPanel` 组件树始终挂载，状态不丢失。
- 内层多包一层固定宽度的 `div`（`style={{ width: codePanelWidth }}`），是为了让内容在收起过程中不被压缩换行，只是被外层 `overflow-hidden` 裁掉——避免动画过程中出现内容挤压的跳动。
- 原来 `WorkspaceHeader` 里"展开/收起文件栏""显示/隐藏终端"两个按钮（第 29-56 行，条件 `workspaceTab === 'code'`）保留在同一个 Header 里即可，改判断条件为 `codePanelOpen`；不需要为代码面板单独再造一个 header 组件（YAGNI，现有结构已经够用，只是判断条件换掉）。

### 4. `WorkspaceHeader.tsx` 改动

- 移除"对话/代码" tab 按钮组（第 64-79 行整块）
- 新增一个图标按钮（用 `PanelRight`/`PanelRightOpen` 之类 lucide 图标，参考截图里红框位置），点击调用 `toggleCodePanel()`，图标依据 `codePanelOpen` 状态切换开合样式（对齐现有"展开/收起文件栏"按钮的 active 态样式写法，第 33-37 行）
- 原本条件 `workspaceTab === 'code'` 的两个按钮（文件栏/终端开关）改判断条件为 `codePanelOpen`

### 5. 拖拽调宽

新增 `handleResizeMouseDown`，逻辑与 `FileSidebar.tsx`（第 50-74 行）拖拽调宽完全一致的模式：`mousedown` 记录起始坐标和宽度，`mousemove` 计算 delta 更新宽度（**注意拖拽方向**：代码面板在右侧，手柄贴左边缘，鼠标左移应该增宽——delta 计算方向与 `FileSidebar` 相反，需要显式验证，不能直接照抄符号），`mouseup` 清理监听器和 `document.body.style.cursor`。宽度范围 clamp：`MIN_CODE_PANEL_WIDTH = 320`，`MAX_CODE_PANEL_WIDTH` 取窗口宽度的 80%（避免在小窗口/单显示器全屏时把对话区挤没，Windows/macOS 窗口初始尺寸不同，用相对窗口宽度的动态上限比写死像素值更稳）。

## 数据流

```
用户点击 Header 的代码面板 toggle 按钮
  → toggleCodePanel()
    → codePanelOpen 翻转（persist 中间件自动写入 localStorage）
    → AgentWorkspace 的 useEffect 联动 FileSidebar 的 sidebarOpen
    → 代码面板容器 width 在 0 与 codePanelWidth 间过渡动画

用户在对话中点击某条 ActionReceipt 详情（handleDetailClick）
  → openFile(path, viewMode) / setActiveFile(path, language)
    → codePanelOpen 设为 true（如果原本是收起的，自动展开）
    → CodeTab 内部 useEffect 检测 activeFileId 变化，加载文件内容

用户拖拽面板左边缘手柄
  → handleResizeMouseDown → mousemove 计算 delta → setCodePanelWidth(clamp(width))
    → persist 中间件写入 localStorage，下次打开应用记住宽度
```

## 兼容性（跨平台）

- 布局改动是纯 CSS flex + inline style + Tailwind transition，不涉及 Electron 主进程或任何平台特定 API，Windows/macOS 渲染行为一致。
- 拖拽调宽复用 `FileSidebar.tsx` 已验证过的原生鼠标事件模式（非某个仅在单一平台测试过的库），Windows/macOS 都已有该模式的实际使用先例。
- `MAX_CODE_PANEL_WIDTH` 用窗口宽度百分比而非固定像素上限，避免 Windows/macOS 默认窗口尺寸不同导致的体验差异（例如 macOS 上某些机型默认窗口更小，固定像素上限可能占满全部对话区）。
- `localStorage` 持久化在 Electron 渲染进程中跨平台行为一致（底层走 Chromium 标准 Web Storage，不依赖文件系统路径），不需要额外处理路径分隔符等平台差异。
- CSS `transition` 动画在两平台的 Chromium 渲染内核一致，不需要做平台判断分支；但需要实测 Windows 下 `width` transition 是否有明显掉帧（如有，可考虑降级为 `transform: scaleX` 或直接去掉动画，本设计暂定先用 `width` transition，测试阶段验证性能）。

## 测试要点

- 默认打开应用：对话始终可见，代码面板默认收起（宽度 0，不占对话区空间）
- 点击 Header 的展开按钮：代码面板从右侧滑出，宽度为上次记住的值（或默认 480px 首次使用）
- 从对话里点击文件/diff 详情（`handleDetailClick`）：代码面板自动展开并加载对应文件，即使之前是收起状态
- 收起代码面板后再展开：之前打开的文件列表、编辑内容（包括未保存的 dirty 状态）、终端会话都还在，没有被卸载重置
- 拖拽面板左边缘手柄调整宽度：宽度实时跟随鼠标，松开后保持；刷新页面/重启应用后宽度保持一致（验证 `persist` 生效）
- 拖拽到最小值/最大值：分别验证 clamp 生效，不能拖到负数或超过窗口宽度把对话区挤没
- 缩小窗口后 `MAX_CODE_PANEL_WIDTH` 跟随窗口宽度百分比重新计算，不会出现代码面板宽度超过当前窗口宽度的情况
- Windows + macOS 双平台分别验证：展开/收起动画流畅度、拖拽调宽手感、`localStorage` 持久化的宽度和展开状态在重启应用后正确恢复
- 原有"展开/收起文件栏""显示/隐藏终端"两个 Header 按钮功能不受影响，判断条件从 `workspaceTab === 'code'` 改为 `codePanelOpen` 后行为等价

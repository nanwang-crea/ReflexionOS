# 代码面板改为右侧可折叠侧栏 设计文档

日期：2026-07-24

## 背景

当前"对话"与"代码"是主区里互斥的两个 tab（`AgentWorkspace.tsx` 用 `hidden` class 切换显隐），点击"代码"tab 后对话完全被顶替，看不到对话内容；且存在 Windows 下文件树接口报错导致代码 tab 打不开的 bug（已单独修复，见 [devlog-2026-06-23_to_present.md](../devlog/devlog-2026-06-23_to_present.md) 2026-07-24 记录）。

用户希望改成类似 Codex 客户端的布局：对话始终是主区内容，代码作为右侧可展开/收起的面板，两者同时可见，不用切换。

## 目标与范围

**本次要做：**
- 移除"对话/代码"tab 切换，对话（`WorkspaceTranscript` + `ChatInput`）始终占据主区
- 代码面板（`CodeTab` + `FileSidebar` + `TerminalPanel`）改为固定在右侧、可展开/收起的面板
- 面板**每次启动默认收起**（`codePanelOpen` 不持久化，固定初始值 `false`）
- 面板展开时宽度**固定**（非按比例），**480px 是编辑区宽度，不含 `FileSidebar`**；实际右侧总占宽 = `codePanelWidth + sidebarWidth`（文件树侧边栏展开时）；默认 480px，可拖拽调整，调整后的宽度持久化保存
- 最大宽度公式：`effectiveMax = viewportWidth - (sidebarOpen ? sidebarWidth : 0) - MIN_CHAT_WIDTH`（`MIN_CHAT_WIDTH` 定为 400px），clamp 在以下时机均需执行：拖拽中、窗口 resize、persist rehydrate 后
- Header 上的"对话/代码"切换按钮替换为一个"展开/收起代码面板"的图标按钮
- 收起时不卸载代码面板内部状态（已打开的文件、编辑内容、终端会话保留），仅用 CSS 隐藏；隐藏态需设置 `inert` + `aria-hidden` + `pointer-events-none`，防止不可见内容被键盘 Tab 焦点访问
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
- 新增 `codePanelOpen: boolean`（默认 `false`，**不持久化**）+ `setCodePanelOpen(open: boolean)` + `toggleCodePanel()`
- 新增 `codePanelWidth: number`（默认 480）+ `setCodePanelWidth(width: number)`；宽度 clamp 规则：`MIN_CODE_PANEL_WIDTH = 320`，`MAX = viewportWidth - (sidebarOpen ? sidebarWidth : 0) - MIN_CHAT_WIDTH`（`MIN_CHAT_WIDTH = 400`）。**clamp 必须在三处执行**：① `setCodePanelWidth` 调用时（拖拽中）；② `window` resize 事件触发时（监听 resize，宽度超出则收敛）；③ store 初始化/rehydrate 时（`persist` 的 `onRehydrateStorage` 钩子里执行一次 clamp）
- `openFile`/`setActiveFile` 里原来 `workspaceTab: 'code'` 的赋值，改为 `codePanelOpen: true`（打开文件即展开面板，语义不变，只是字段改名）

store 用 `persist` 包裹，`name: 'reflexion-code-panel'`，`partialize` **只持久化 `codePanelWidth`**，不持久化 `codePanelOpen`（每次启动固定初始值 `false`）和 `openFiles`/`activeFileId` 等会话态数据。

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
  {/* 收起态同时设置 inert + aria-hidden + pointer-events-none，防止焦点跑进不可见区域 */}
  <div
    className="flex h-full shrink-0 overflow-hidden border-l border-edge transition-[width] duration-200"
    style={{ width: codePanelOpen ? codePanelWidth : 0 }}
    inert={!codePanelOpen ? '' : undefined}
    aria-hidden={!codePanelOpen}
  >
    <div
      className={`flex h-full flex-col bg-surface-primary ${!codePanelOpen ? 'pointer-events-none' : ''}`}
      style={{ width: codePanelWidth }}
    >
      {/* WorkspaceHeader 里的文件栏/终端按钮仍留在顶部 Header，不新建面板内 header */}
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
- 收起态同时加 `inert`（HTML 属性，阻止所有键盘/鼠标事件和焦点穿透）+ `aria-hidden={true}`（对屏幕阅读器隐藏）+ `pointer-events-none`（冗余保险，覆盖不支持 `inert` 的旧 Chromium 版本）。`inert` 在 React 中以字符串空值传递（`inert=""`），TypeScript 类型声明须确认（Electron 内嵌 Chromium 已支持 `inert`，无需 polyfill）。
- 代码面板**不新建自己的 header 组件**。文件栏/终端开关按钮继续放在同一个 `WorkspaceHeader` 里，仅把 `workspaceTab === 'code'` 的判断条件改为 `codePanelOpen`。

### 4. `WorkspaceHeader.tsx` 改动

- 移除"对话/代码" tab 按钮组（第 64-79 行整块）
- 新增一个图标按钮（用 `PanelRight`/`PanelRightOpen` 之类 lucide 图标，参考截图里红框位置），点击调用 `toggleCodePanel()`，图标依据 `codePanelOpen` 状态切换开合样式（对齐现有"展开/收起文件栏"按钮的 active 态样式写法，第 33-37 行）
- 原本条件 `workspaceTab === 'code'` 的两个按钮（文件栏/终端开关）改判断条件为 `codePanelOpen`

### 5. 拖拽调宽

新增 `handleResizeMouseDown`，逻辑与 `FileSidebar.tsx`（第 50-74 行）拖拽调宽完全一致的模式：`mousedown` 记录起始坐标和宽度，`mousemove` 计算 delta 调用 `setCodePanelWidth`（**注意拖拽方向**：代码面板在右侧，手柄贴左边缘，鼠标左移应该增宽——delta 计算方向与 `FileSidebar` 相反，需要显式验证，不能直接照抄符号），`mouseup` 清理监听器和 `document.body.style.cursor`。

宽度 clamp 统一由 `setCodePanelWidth` 内部执行，公式：
```
min = MIN_CODE_PANEL_WIDTH (320)
max = window.innerWidth - (sidebarOpen ? sidebarWidth : 0) - MIN_CHAT_WIDTH (400)
codePanelWidth = Math.max(min, Math.min(max, requestedWidth))
```
`setCodePanelWidth` 需读取 store 里的 `sidebarOpen`/`sidebarWidth` 当前值计算 max，而不是在组件层硬编码。拖拽以外的两个 clamp 时机（window resize、rehydrate）也调用同一个 `setCodePanelWidth`，保证规则统一。

### 约束冲突决策（方案 B）

三项宽度约束的最坏情况：`MIN_CODE_PANEL_WIDTH(320) + MAX_SIDEBAR_WIDTH(480) + MIN_CHAT_WIDTH(400) = 1200px`，超出原主窗口 `minWidth: 1180`。

采用**方案 B**：提高应用主窗口最小宽度。

由于代码面板宽度约束使用的是渲染进程 `window.innerWidth`，而 Electron `BrowserWindow.minWidth` 约束的是窗口外框宽度，二者之间存在系统边框占用差异（Windows 下 resize border 约 8-12px）。为保证最坏情况下渲染区 `window.innerWidth` 仍满足 1200px 的内容区预算，将主窗口 `minWidth` 从 `1180` 提高到 **`1220`**，预留约 20px 的非内容区余量。

本次**不引入**"空间不足时自动收起 FileSidebar"的额外联动逻辑（方案 D）。

## 数据流

```
用户点击 Header 的代码面板 toggle 按钮
  → toggleCodePanel()
    → codePanelOpen 翻转（仅内存态，不写 localStorage）
    → AgentWorkspace 的 useEffect 联动 FileSidebar 的 sidebarOpen
    → 代码面板容器 width 在 0 与 codePanelWidth 间过渡动画
    → 收起时：面板设置 inert / aria-hidden / pointer-events-none，键盘焦点无法进入

用户在对话中点击某条 ActionReceipt 详情（handleDetailClick）
  → openFile(path, viewMode) / setActiveFile(path, language)
    → codePanelOpen 设为 true（如果原本是收起的，自动展开）
    → CodeTab 内部 useEffect 检测 activeFileId 变化，加载文件内容

用户拖拽面板左边缘手柄
  → handleResizeMouseDown → mousemove 计算 delta → setCodePanelWidth(clamp(width))
    → clamp 公式：max(320, min(viewportWidth - sidebarWidth? - 400, requested))
    → persist 中间件写入 localStorage（只存宽度），下次打开应用记住宽度

应用启动/刷新
  → persist rehydrate 恢复 codePanelWidth
  → onRehydrateStorage 钩子调用 setCodePanelWidth(rehydratedWidth) 触发一次 clamp
  → codePanelOpen 固定为初始值 false，不受 persist 影响

窗口缩小
  → window resize 事件 → 若 codePanelWidth 超出新 effectiveMax → setCodePanelWidth(effectiveMax)
```

## 兼容性（跨平台）

- 布局改动是纯 CSS flex + inline style + Tailwind transition，不涉及 Electron 主进程或任何平台特定 API，Windows/macOS 渲染行为一致。
- 拖拽调宽复用 `FileSidebar.tsx` 已验证过的原生鼠标事件模式（非某个仅在单一平台测试过的库），Windows/macOS 都已有该模式的实际使用先例。
- `effectiveMax` 用 `window.innerWidth - sidebarWidth? - MIN_CHAT_WIDTH` 而非固定像素，避免 Windows/macOS 默认窗口尺寸不同以及文件树侧边栏展开宽度不同导致的对话区被挤压。
- `localStorage` 持久化在 Electron 渲染进程中跨平台行为一致（底层走 Chromium 标准 Web Storage，不依赖文件系统路径），不需要额外处理路径分隔符等平台差异。
- CSS `transition` 动画在两平台的 Chromium 渲染内核一致，不需要做平台判断分支；但需要实测 Windows 下 `width` transition 是否有明显掉帧（如有，可考虑降级为 `transform: scaleX` 或直接去掉动画，本设计暂定先用 `width` transition，测试阶段验证性能）。

## 测试要点

- **启动行为**：每次启动/刷新，代码面板固定收起（`codePanelOpen = false`），与上次退出时的状态无关；宽度恢复为上次记住的值（或默认 480px）
- **展开/收起**：点击 Header toggle 按钮，面板从右侧滑出/收回，宽度为 persist 的值
- **自动展开**：从对话中点击文件/diff 详情，代码面板自动展开并加载对应文件，即使之前是收起状态
- **状态保留**：收起后再展开，已打开的文件列表、未保存的编辑内容、终端会话全部保留（DOM 未卸载）
- **收起态隔离**：面板收起时键盘 Tab 焦点不能进入（`inert`），屏幕阅读器不读取（`aria-hidden`），鼠标事件不响应（`pointer-events-none`）
- **拖拽调宽**：宽度实时跟随鼠标，clamp 在 MIN(320) / effectiveMax 边界生效；松开后宽度持久化到 localStorage
- **窗口缩小 clamp**：缩小窗口时，若 codePanelWidth 超出当前 effectiveMax，自动收敛到 effectiveMax；验证对话区始终保留 MIN_CHAT_WIDTH(400px) 空间
- **rehydrate clamp**：持久化的宽度在 rehydrate 时经过一次 clamp，不会因在大窗口上记录的宽度在小窗口重开后溢出
- **文件树展开时 clamp**：打开 FileSidebar 后，若 codePanelWidth + sidebarWidth 导致 effectiveMax 降低，codePanelWidth 需同步收敛
- **持久化验证**：重启应用后宽度与退出前一致；`codePanelOpen` 不被持久化，重启后固定为 false
- Windows + macOS 双平台分别验证：展开/收起动画流畅度、拖拽调宽手感、各 clamp 时机均正常触发
- 原有"展开/收起文件栏""显示/隐藏终端"两个 Header 按钮功能不受影响，判断条件从 `workspaceTab === 'code'` 改为 `codePanelOpen` 后行为等价
- **最小窗口宽度验证**：将窗口缩到最小宽度（1220px），打开代码面板并将 FileSidebar 拉至最大宽度（480px），验证此时渲染区 `window.innerWidth` 仍足以容纳 320 + 480 + 400 的内容预算，聊天区不会被压穿 `MIN_CHAT_WIDTH`

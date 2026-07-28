# ReflexionOS 应用内确认弹框设计

## 1. 背景

应用里所有"危险操作的二次确认"目前都走 `nativeDialogService.confirmAction`，其实现是浏览器原生的 `window.confirm()`（`frontend/src/services/dialogService.ts`）。

这带来三个问题：

1. **跨平台外观不统一**：在 Electron 里由 Chromium 渲染系统弹框，macOS / Linux / Windows 各自风格不同（圆角/方角、按钮顺序、配色都不一样），三端长得不一样，且完全无法套用应用主题。
2. **与应用设计语言割裂**：应用已有成熟的设计 token（`bg-surface-*`、`border-edge`、`text-accent`、`status-error-*` 等）和 framer-motion 动画（见 `Toast.tsx`），而系统弹框是默认灰框，显得突兀、廉价。
3. **阻塞渲染进程**：`window.confirm` 是同步阻塞的，会冻结整个 UI 线程，对实时流式输出的 agent 应用尤其不友好。

当前 `confirmAction` 有 5 个调用方，**全部是破坏性操作的二次确认**：

| 调用处 | 操作 |
|---|---|
| `pages/AgentWorkspace.tsx` | 重置对话（清空记录） |
| `hooks/useCurrentSessionViewModel.ts:75` | 重新生成消息 |
| `components/layout/useSidebarProjectActions.ts:131` | 删除项目 |
| `components/layout/useSidebarSessionActions.ts:121` | 删除会话 |
| `features/llm/useSettingsPageController.ts:195` | 删除供应商 |

应用当前**没有任何自绘的 Modal / Dialog 组件**，所有确认都依赖系统弹框。

## 2. 目标

- 提供一个应用内自绘的居中确认弹框组件 `ConfirmDialog`，风格与现有 UI 一致（设计 token + framer-motion），macOS / Linux / Windows 三平台表现完全一致。
- 将 `confirmAction` 从同步 `boolean` 改为异步 `Promise<boolean>`，并支持 `variant`（`danger` / `default`）以区分危险操作的视觉强调。
- 打通现有 5 个 `confirmAction` 调用方，全部改用新弹框；因 5 处均为删除/重置类操作，统一使用 `variant: 'danger'`。
- 键盘交互**安全优先**（5 处全是删除/重置类危险操作）：默认焦点落在「取消」按钮，Esc / 点遮罩 = 取消，Enter **跟随焦点**（默认即取消），要执行危险操作必须主动 Tab / 点到「确认」或鼠标点击。不做"Enter 全局映射确认"，避免误触。

## 3. 非目标

- **不改 `promptText`**：经排查它没有任何调用方（重命名走的是 sidebar 内联编辑，不是弹框），属于死代码，本次保留不动，继续指向 `window.prompt`，不在范围内。
- **不改 `notifyError`**：它走 Toast，本来就用应用主题渲染，不丑，不动。
- 不做"输入型"弹框（PromptDialog）、不做多按钮（>2）弹框、不做可堆叠的多层弹框——当前 5 个场景都是"确认/取消"二选一，YAGNI。
- 不引入第三方弹框库（如 Radix Dialog）——已有 framer-motion 与设计 token，自绘成本低且风格可控。
- 不改弹框文案内容本身（沿用各调用方现有提示语）。

## 4. 用户故事 / 行为

### 4.1 危险操作弹出统一弹框

作为用户，当我点"删除会话""删除项目""删除供应商""重置对话""重新生成"时，屏幕中央弹出一个带半透明遮罩的确认框，外观与应用一致：标题 + 说明文字 + 「取消」「确认」两个按钮，确认按钮为红色（危险强调）。

### 4.2 多种方式取消 / 确认（安全优先）

- 点「取消」、按 Esc、点击遮罩空白处 → 关闭弹框，**不执行**操作。
- 点「确认」、或鼠标 / 键盘把焦点移到「确认」后按 Enter → 关闭弹框，**执行**操作。
- 弹框打开时焦点默认在「取消」按钮上。**Enter 跟随当前焦点**，不做全局映射——所以默认敲 Enter 等于取消，要执行危险操作必须先主动 Tab / 点到「确认」。这样焦点策略与 Enter 行为自洽，避免连续敲 Enter 误触发危险操作，且 Mac / Windows / Linux 标准焦点模型下语义一致。

### 4.3 跨平台一致

无论 macOS、Linux 还是 Windows，弹框外观、动画、交互完全一致。

## 5. 方案

### 5.1 组件与挂载

- 新增 `frontend/src/components/common/ConfirmDialog.tsx`：纯展示组件，居中布局 + backdrop 遮罩，复用 Toast 的设计 token 与 framer-motion（`AnimatePresence` 进出场动画）。
- 新增一个轻量全局 store `frontend/src/shared/stores/confirmDialog.store.ts`（zustand），保存当前待确认请求的状态：`{ open, title?, message, variant, resolve }`。这与 `toast.store` 的全局单例模式对齐。
- 在根组件（与 `ToastContainer` 同一挂载点，`AgentWorkspace`/`App` 已挂 Toast）挂一个 `ConfirmDialogHost`，订阅 store 渲染弹框。

### 5.2 接口（dialogService）

`confirmAction` 由同步改为异步，并接受可选配置：

```ts
// 旧：confirmAction: (message: string) => boolean
// 新：
confirmAction: (
  message: string,
  options?: { title?: string; variant?: 'danger' | 'default' }
) => Promise<boolean>
```

实现：`confirmAction` 调用 store 的 `requestConfirm(...)`，后者把请求写入 store 并返回一个 Promise；用户点确认/取消时 `resolve(true/false)` 并关闭弹框。`DialogService` 接口的 `confirmAction` 返回类型相应改为 `Promise<boolean>`。

### 5.3 数据流

```
调用方 await confirmAction(msg, {variant:'danger'})
  → dialogService.confirmAction
  → confirmDialog.store.requestConfirm() 写入 {open:true, message, variant, resolve}
  → ConfirmDialogHost 渲染 ConfirmDialog（带动画）
  → 用户点按钮 / Esc / Enter / 点遮罩
  → store.resolve(true|false) + open:false
  → await 处的 Promise 兑现，调用方据此决定是否执行操作
```

### 5.4 调用方改造（5 处）

全部从同步早返回改为异步等待。典型改法：

```ts
// 旧
if (!nativeDialogService.confirmAction(MSG)) return
// 新
if (!(await nativeDialogService.confirmAction(MSG, { variant: 'danger' }))) return
```

涉及的函数若尚非 `async`，需改为 `async`。逐一确认每个调用方的外层签名与依赖数组。各调用方现状如下：

| 调用处 | 现状 | 改造 |
|---|---|---|
| `pages/AgentWorkspace.tsx` `handleReset` | 同步 `useCallback` | 改 `async`，`await confirmAction`；`onReset` 透传链（`useCurrentSessionViewModel` → `WorkspaceHeader`）的类型放宽到 `() => void \| Promise<void>` |
| `hooks/useCurrentSessionViewModel.ts` `handleRegenerateMessage` | 同步 `useCallback` | 改 `async`，`await confirmAction`；`onRegenerateMessage` 透传链（`WorkspaceTranscript`）类型同上放宽 |
| `components/layout/useSidebarProjectActions.ts` `handleDeleteProject` | 已是 `async` | 仅在 `confirmAction` 前加 `await` |
| `components/layout/useSidebarSessionActions.ts` `handleDeleteSession` | 已是 `async` | 仅在 `confirmAction` 前加 `await` |
| `features/llm/useSettingsPageController.ts` `handleDeleteProvider` | 已是 `async`，但确认走**回调下传**，见下方专项 | 见 5.4.1 |

#### 5.4.1 LLM 删除供应商：确认是回调下传，需连改两层（重点）

这条链路与其它 4 处不同，不是"在本函数里直接 await confirmAction"就完事。当前结构是：

- `useSettingsPageController.handleDeleteProvider` 把一个**同步**确认回调下传给 action：
  ```ts
  // useSettingsPageController.ts 现状
  confirmDelete: (provider) => dialogService.confirmAction(`确定删除供应商"${provider.name}"吗？`)
  ```
- 真正消费它的是 `features/llm/provider.actions.ts` 的 `deleteProvider`，其参数类型与调用都是**同步**的：
  ```ts
  // provider.actions.ts 现状
  confirmDelete: (provider: ProviderInstance) => boolean   // 类型
  if (!confirmDelete(selectedSavedProvider)) { return }    // 同步消费
  ```

`confirmAction` 改成 `Promise<boolean>` 后，若只改 controller 而不改 action 这一层，`confirmDelete()` 会返回一个 Promise 对象——**永远 truthy**，二次确认形同虚设，会变成**无提示静默删除**。因此本次必须同时改 `provider.actions.ts`：

1. `deleteProvider` 参数类型：`confirmDelete: (provider: ProviderInstance) => boolean` → `=> Promise<boolean>`。
2. 消费处：`if (!confirmDelete(...))` → `if (!(await confirmDelete(...)))`。`deleteProvider` 本就是 `async`，无需改签名。
3. controller 侧 `confirmDelete` 回调返回值自然变为 `Promise<boolean>`（因 `confirmAction` 已返回 Promise），无需额外 `async` 包装。

> 这是本次唯一一处"确认逻辑跨文件回调下传"的调用方，最容易在实现时漏掉 action 层，单独列出。

### 5.5 危险变体样式

- `variant: 'danger'`：确认按钮使用 `status-error` 系列 token（红底/红字），标题区可选红色图标（复用 lucide `AlertTriangle`，与 Toast 一致）。
- `variant: 'default'`：确认按钮使用 `accent` 系列 token。本次 5 处都传 `danger`，`default` 作为组件能力保留给未来普通确认场景。

## 6. 边界与降级

- **同一时刻只允许一个确认弹框**：store 为单例。若在弹框已打开时再次 `requestConfirm`，直接 `resolve(false)` 拒绝新请求（或忽略），避免堆叠/竞态。具体取拒绝新请求，保证语义简单。
- **Promise 不泄漏**：任何关闭路径（按钮/Esc/遮罩）都必须 `resolve` 恰好一次；关闭后清空 `resolve` 引用。
- **焦点管理**：打开时把焦点移到取消按钮；关闭后焦点应回到触发元素（尽力而为，不强求）。
- **Esc/Enter 仅在弹框打开时生效**，通过弹框自身的事件监听，避免与全局快捷键（如 `AgentWorkspace` 里的 Tab/Ctrl+` ）冲突。
- **测试影响**：现有 `dialogService.test.ts` 断言 `window.confirm` 同步返回，需改为断言异步走 store。已有调用方测试（sidebar actions、viewModel、settings）中对 `confirmAction` / `confirmDelete` 的 mock 需从返回 `boolean` 改为返回 `Promise<boolean>`（`mockReturnValue(true)` → `mockResolvedValue(true)`）。LLM 链路因新增 action 层 `await`，相关 settings/loader 测试中 `confirmDelete` 的 mock 也要一并改为 resolved Promise，否则断言会失真。

## 7. 影响面小结

- 新增：`ConfirmDialog.tsx`、`ConfirmDialogHost`（可并入同文件）、`confirmDialog.store.ts`。
- 修改：`dialogService.ts`（接口+实现）、5 个调用方、`provider.actions.ts`（LLM 删除链路 action 层 async 化）、`onReset`/`onRegenerateMessage` 透传链类型放宽、根挂载点、相关测试。
- 不动：`promptText`、`notifyError`、各调用方的文案。

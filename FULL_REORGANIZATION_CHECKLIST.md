# ReflexionOS 全面重组清单

## 📊 项目现状扫描

| 类别 | 文件数 | 当前位置 | 问题 |
|------|--------|----------|------|
| Stores | 11 | `/stores/` + `/features/*/` | 散落两处，无后缀区分 |
| Tests | 30 | 散布于所有源文件旁 | 测试与源码混放，目录杂乱 |
| APIs | 9 | `/features/*/` 根目录 | 与 stores 混在一起 |
| Reducers | 1 | `/features/conversation/` | 只有一个，但命名不统一 |
| Actions | 6 | 散布于 3 个目录 | 位置不一致 |
| Loaders | 2 | `/features/*/` 根目录 | 无子目录归类 |
| Hooks | 13 | `/hooks/` + 5 个错放 | 5 个 hook 不在 hooks 目录 |
| Services | 6 | `/services/` | ✅ 结构合理 |
| Types | 12 | `/types/` | ✅ 结构合理 |
| Utils | 2 | `/utils/` | ✅ 结构合理 |
| Components | 36 | `/components/` | ✅ 结构合理 |
| Pages | 10 | `/pages/` | ✅ 结构合理 |

---

## 🎯 重组目标

### 命名规范

| 文件类型 | 当前命名 | 目标命名 | 示例 |
|----------|----------|----------|------|
| Store | `projectStore.ts` | `project.store.ts` | ✅ 业界标准 |
| API | `projectApi.ts` | `project.api.ts` | ✅ 与 store 对称 |
| Test | `projectStore.test.ts` | `project.store.test.ts` | ✅ 跟随源文件名 |
| Reducer | `conversationReducer.ts` | `conversation.reducer.ts` | ✅ 与 store 对称 |
| Actions | `sessionActions.ts` | `session.actions.ts` | ✅ 与 store 对称 |
| Loader | `projectLoader.ts` | `project.loader.ts` | ✅ 与 store 对称 |
| Hook | `useSessionData.ts` | `useSessionData.ts` | ⬜ 保持不变（React 约定） |
| Service | `dialogService.ts` | `dialogService.ts` | ⬜ 保持不变（已有约定） |
| Component | `ChatInput.tsx` | `ChatInput.tsx` | ⬜ 保持不变 |
| Type | `conversation.ts` | `conversation.ts` | ⬜ 保持不变 |

### 目录规范

```
frontend/src/
├── features/{domain}/
│   ├── stores/           ← 所有 store 文件
│   ├── api/              ← 所有 API 文件
│   ├── hooks/            ← feature 级别的 hooks
│   ├── __tests__/        ← feature 级别的测试
│   └── ...               ← reducer, actions, loader 等留在根目录
│
├── shared/
│   └── stores/           ← 跨 feature 共享的 store
│
├── hooks/                ← 全局 hooks
├── services/             ← 全局 services
├── types/                ← 全局 types
├── utils/                ← 全局 utils
├── components/           ← 全局 components
└── pages/                ← 页面组件
```

---

## 🔴 优先级 P0：Stores 重组（11 文件 + 4 测试）

### 移动 + 重命名

| # | 原路径 | 新路径 | 类型 |
|---|--------|--------|------|
| 1 | `stores/animationStore.ts` | `shared/stores/animation.store.ts` | shared |
| 2 | `stores/themeStore.ts` | `shared/stores/theme.store.ts` | shared |
| 3 | `stores/toastStore.ts` | `shared/stores/toast.store.ts` | shared |
| 4 | `stores/projectStore.ts` | `features/projects/stores/project.store.ts` | feature |
| 5 | `stores/settingsStore.ts` | `features/settings/stores/settings.store.ts` | feature |
| 6 | `stores/workspaceStore.ts` | `features/workspace/stores/workspace.store.ts` | feature |
| 7 | `features/code/codeTabStore.ts` | `features/code/stores/codeTab.store.ts` | feature |
| 8 | `features/conversation/conversationStore.ts` | `features/conversation/stores/conversation.store.ts` | feature |
| 9 | `features/git/gitStore.ts` | `features/git/stores/git.store.ts` | feature |
| 10 | `features/sessions/sessionStore.ts` | `features/sessions/stores/session.store.ts` | feature |
| 11 | `features/terminal/terminalStore.ts` | `features/terminal/stores/terminal.store.ts` | feature |

### 对应测试文件

| # | 原路径 | 新路径 |
|---|--------|--------|
| 12 | `features/code/codeTabStore.test.ts` | `features/code/__tests__/codeTab.store.test.ts` |
| 13 | `features/conversation/conversationStore.test.ts` | `features/conversation/__tests__/conversation.store.test.ts` |
| 14 | `features/sessions/sessionStore.test.ts` | `features/sessions/__tests__/session.store.test.ts` |
| 15 | `features/terminal/terminalStore.test.ts` | `features/terminal/__tests__/terminal.store.test.ts` |

### 导入路径映射

| 旧导入 | 新导入 |
|--------|--------|
| `@/stores/animationStore` | `@/shared/stores/animation.store` |
| `@/stores/themeStore` | `@/shared/stores/theme.store` |
| `@/stores/toastStore` | `@/shared/stores/toast.store` |
| `@/stores/projectStore` | `@/features/projects/stores/project.store` |
| `@/stores/settingsStore` | `@/features/settings/stores/settings.store` |
| `@/stores/workspaceStore` | `@/features/workspace/stores/workspace.store` |
| `@/features/code/codeTabStore` | `@/features/code/stores/codeTab.store` |
| `@/features/conversation/conversationStore` | `@/features/conversation/stores/conversation.store` |
| `@/features/git/gitStore` | `@/features/git/stores/git.store` |
| `@/features/sessions/sessionStore` | `@/features/sessions/stores/session.store` |
| `@/features/terminal/terminalStore` | `@/features/terminal/stores/terminal.store` |

---

## 🔴 优先级 P0：Tests 重组（30 文件）

### 当前问题

30 个测试文件散布在 8 个目录中，与源文件混放：

```
components/chat/ChatInput.test.ts        ← 测试混在组件目录
components/layout/sidebarBusy.test.ts    ← 同上
features/code/codeTabStore.test.ts       ← 测试混在 feature 根目录
hooks/useConversationData.test.ts        ← 测试混在 hooks 目录
services/dialogService.test.ts           ← 测试混在 services 目录
...
```

### 目标结构：`__tests__/` 子目录

每个有测试的目录下创建 `__tests__/`，将测试文件移入并跟随源文件重命名。

### features/ 下的测试（18 个）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 1 | `features/code/codeTabStore.test.ts` | `features/code/__tests__/codeTab.store.test.ts` |
| 2 | `features/conversation/conversationApi.test.ts` | `features/conversation/__tests__/conversation.api.test.ts` |
| 3 | `features/conversation/conversationReducer.test.ts` | `features/conversation/__tests__/conversation.reducer.test.ts` |
| 4 | `features/conversation/conversationStore.test.ts` | `features/conversation/__tests__/conversation.store.test.ts` |
| 5 | `features/llm/llmSettingsLoader.test.ts` | `features/llm/__tests__/llmSettings.loader.test.ts` |
| 6 | `features/projects/projectLoader.test.ts` | `features/projects/__tests__/project.loader.test.ts` |
| 7 | `features/sessions/sessionActions.test.ts` | `features/sessions/__tests__/session.actions.test.ts` |
| 8 | `features/sessions/sessionStore.test.ts` | `features/sessions/__tests__/session.store.test.ts` |
| 9 | `features/terminal/terminalStore.test.ts` | `features/terminal/__tests__/terminal.store.test.ts` |
| 10 | `features/workspace/autoScroll.test.ts` | `features/workspace/__tests__/autoScroll.test.ts` |
| 11 | `features/workspace/sessionSelection.test.ts` | `features/workspace/__tests__/sessionSelection.test.ts` |

### components/ 下的测试（7 个）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 12 | `components/chat/ChatInput.test.ts` | `components/chat/__tests__/ChatInput.test.ts` |
| 13 | `components/layout/sidebarBusy.test.ts` | `components/layout/__tests__/sidebarBusy.test.ts` |
| 14 | `components/layout/useSidebarFilteredProjects.test.ts` | `components/layout/__tests__/useSidebarFilteredProjects.test.ts` |
| 15 | `components/layout/useSidebarProjectActions.test.ts` | `components/layout/__tests__/useSidebarProjectActions.test.ts` |
| 16 | `components/layout/useSidebarSessionActions.test.ts` | `components/layout/__tests__/useSidebarSessionActions.test.ts` |
| 17 | `components/workspace/ToolTraceCard.test.tsx` | `components/workspace/__tests__/ToolTraceCard.test.tsx` |
| 18 | `components/workspace/transcriptItems.test.ts` | `components/workspace/__tests__/transcriptItems.test.ts` |

### hooks/ 下的测试（6 个）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 19 | `hooks/useConversationData.test.ts` | `hooks/__tests__/useConversationData.test.ts` |
| 20 | `hooks/useConversationRuntime.test.ts` | `hooks/__tests__/useConversationRuntime.test.ts` |
| 21 | `hooks/useCurrentSessionViewModel.test.ts` | `hooks/__tests__/useCurrentSessionViewModel.test.ts` |
| 22 | `hooks/useSendMessage.test.ts` | `hooks/__tests__/useSendMessage.test.ts` |
| 23 | `hooks/useSessionData.test.ts` | `hooks/__tests__/useSessionData.test.ts` |
| 24 | `hooks/useSessionSelection.test.ts` | `hooks/__tests__/useSessionSelection.test.ts` |

### services/ 下的测试（5 个）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 25 | `services/backendManagerPackaging.test.ts` | `services/__tests__/backendManagerPackaging.test.ts` |
| 26 | `services/backendRuntimeRequirements.test.ts` | `services/__tests__/backendRuntimeRequirements.test.ts` |
| 27 | `services/dialogService.test.ts` | `services/__tests__/dialogService.test.ts` |
| 28 | `services/runtimeConfig.test.ts` | `services/__tests__/runtimeConfig.test.ts` |
| 29 | `services/sessionConversationWebSocket.test.ts` | `services/__tests__/sessionConversationWebSocket.test.ts` |

### pages/ 下的测试（1 个）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 30 | `pages/AgentWorkspace.test.tsx` | `pages/__tests__/AgentWorkspace.test.tsx` |

---

## 🟡 优先级 P1：APIs 重组（9 文件）

### 移动 + 重命名

| # | 原路径 | 新路径 |
|---|--------|--------|
| 1 | `features/code/fileApi.ts` | `features/code/api/file.api.ts` |
| 2 | `features/conversation/conversationApi.ts` | `features/conversation/api/conversation.api.ts` |
| 3 | `features/git/gitApi.ts` | `features/git/api/git.api.ts` |
| 4 | `features/llm/llmApi.ts` | `features/llm/api/llm.api.ts` |
| 5 | `features/plugins/pluginApi.ts` | `features/plugins/api/plugin.api.ts` |
| 6 | `features/projects/projectApi.ts` | `features/projects/api/project.api.ts` |
| 7 | `features/sessions/sessionApi.ts` | `features/sessions/api/session.api.ts` |
| 8 | `features/skills/skillApi.ts` | `features/skills/api/skill.api.ts` |
| 9 | `features/uiSettings/uiSettingsApi.ts` | `features/settings/api/uiSettings.api.ts` |

### 导入路径映射

| 旧导入 | 新导入 |
|--------|--------|
| `@/features/code/fileApi` | `@/features/code/api/file.api` |
| `@/features/conversation/conversationApi` | `@/features/conversation/api/conversation.api` |
| `@/features/git/gitApi` | `@/features/git/api/git.api` |
| `@/features/llm/llmApi` | `@/features/llm/api/llm.api` |
| `@/features/plugins/pluginApi` | `@/features/plugins/api/plugin.api` |
| `@/features/projects/projectApi` | `@/features/projects/api/project.api` |
| `@/features/sessions/sessionApi` | `@/features/sessions/api/session.api` |
| `@/features/skills/skillApi` | `@/features/skills/api/skill.api` |
| `@/features/uiSettings/uiSettingsApi` | `@/features/settings/api/uiSettings.api` |

---

## 🟡 优先级 P1：Reducers & Actions & Loaders 重命名（9 文件）

### Reducers（1 文件）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 1 | `features/conversation/conversationReducer.ts` | `features/conversation/conversation.reducer.ts` |

### Actions（3 文件在 features/ 下）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 2 | `features/llm/providerActions.ts` | `features/llm/provider.actions.ts` |
| 3 | `features/sessions/sessionActions.ts` | `features/sessions/session.actions.ts` |

> 注：`components/execution/approvalActions.ts` 和 `components/layout/useSidebar*.ts` 是组件局部逻辑，暂不移动。

### Loaders（2 文件）

| # | 原路径 | 新路径 |
|---|--------|--------|
| 4 | `features/llm/llmSettingsLoader.ts` | `features/llm/llmSettings.loader.ts` |
| 5 | `features/projects/projectLoader.ts` | `features/projects/project.loader.ts` |

### 对应测试文件

| # | 原路径 | 新路径 |
|---|--------|--------|
| 6 | `features/conversation/conversationReducer.test.ts` | `features/conversation/__tests__/conversation.reducer.test.ts` |
| 7 | `features/llm/llmSettingsLoader.test.ts` | `features/llm/__tests__/llmSettings.loader.test.ts` |
| 8 | `features/projects/projectLoader.test.ts` | `features/projects/__tests__/project.loader.test.ts` |
| 9 | `features/sessions/sessionActions.test.ts` | `features/sessions/__tests__/session.actions.test.ts` |

---

## 🟢 优先级 P2：Hooks 归位（5 文件）

当前有 5 个 hook 文件不在 `/hooks/` 目录中，而是散落在 `components/` 和 `features/` 中：

| # | 原路径 | 新路径 | 说明 |
|---|--------|--------|------|
| 1 | `components/layout/useSidebarFilteredProjects.ts` | `hooks/useSidebarFilteredProjects.ts` | 全局 hook |
| 2 | `components/layout/useSidebarProjectActions.ts` | `hooks/useSidebarProjectActions.ts` | 全局 hook |
| 3 | `components/layout/useSidebarSessionActions.ts` | `hooks/useSidebarSessionActions.ts` | 全局 hook |
| 4 | `features/llm/useSettingsPageController.ts` | `hooks/useSettingsPageController.ts` | 全局 hook |
| 5 | `hooks/useSessionActions.ts` | `features/sessions/hooks/useSessionActions.ts` | feature 级 hook |

> ⚠️ 需要确认：前 4 个 hook 是否确实被多处使用。如果只被同目录组件使用，可以保留原位。

### 对应测试文件

| # | 原路径 | 新路径 |
|---|--------|--------|
| 6 | `components/layout/useSidebarFilteredProjects.test.ts` | `hooks/__tests__/useSidebarFilteredProjects.test.ts` |
| 7 | `components/layout/useSidebarProjectActions.test.ts` | `hooks/__tests__/useSidebarProjectActions.test.ts` |
| 8 | `components/layout/useSidebarSessionActions.test.ts` | `hooks/__tests__/useSidebarSessionActions.test.ts` |

---

## 🟢 优先级 P2：Feature 目录重命名（1 个）

| # | 原路径 | 新路径 | 说明 |
|---|--------|--------|------|
| 1 | `features/uiSettings/` | `features/settings/` | 与 settingsStore 对齐 |

### 涉及文件

- `features/uiSettings/uiSettingsApi.ts` → `features/settings/api/uiSettings.api.ts`
- 所有导入 `@/features/uiSettings/` 的文件需更新

---

## 🟢 优先级 P2：清理空目录

重组完成后需要删除的空目录：

| # | 目录 | 前提 |
|---|------|------|
| 1 | `stores/` | 所有 store 文件移走后 |
| 2 | `test/` | 当前已为空 |
| 3 | `features/uiSettings/` | 重命名为 settings 后 |

---

## ✅ 无需修改的目录

以下目录结构已经合理，不需要重组：

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `types/` | 12 | 全局类型定义，结构清晰 |
| `utils/` | 2 | 工具函数，结构清晰 |
| `services/` | 6 | 全局服务，结构清晰 |
| `components/` | 36 | UI 组件按功能分组，结构清晰 |
| `pages/` | 10 | 页面组件，结构清晰 |

---

## 📊 总工作量统计

| 优先级 | 类别 | 文件移动 | 文件重命名 | 导入更新 | 测试文件 |
|--------|------|----------|-----------|----------|----------|
| **P0** | Stores | 11 | 11 | ~50-70 | 4 |
| **P0** | Tests | 30 | ~15（跟随源文件） | ~30（测试内导入） | — |
| **P1** | APIs | 9 | 9 | ~20-30 | 1 |
| **P1** | Reducers/Actions/Loaders | 0 | 5 | ~10-15 | 4 |
| **P2** | Hooks 归位 | 5 | 0 | ~10-15 | 3 |
| **P2** | Feature 重命名 | 1 目录 | 1 | ~5 | 0 |
| **合计** | — | **56** | **~41** | **~125-165** | **12** |

---

## 🔄 推荐执行顺序

### 阶段 1：P0 - Stores + Tests（核心重组）

1. 创建所有 `__tests__/` 和 `stores/` 子目录
2. 移动 + 重命名 11 个 store 文件
3. 移动 30 个测试文件到 `__tests__/`
4. 更新所有导入路径
5. 运行 `npm run typecheck` + `npm test` 验证

### 阶段 2：P1 - APIs + Reducers/Actions/Loaders

1. 创建所有 `api/` 子目录
2. 移动 + 重命名 9 个 API 文件
3. 重命名 5 个 reducer/actions/loader 文件
4. 移动对应测试文件
5. 更新所有导入路径
6. 运行验证

### 阶段 3：P2 - Hooks 归位 + Feature 重命名

1. 移动 5 个 hook 文件
2. 重命名 `uiSettings/` → `settings/`
3. 清理空目录
4. 更新所有导入路径
5. 最终验证

---

## 🎯 最终目标结构

```
frontend/src/
├── App.tsx
├── main.tsx
├── vite-env.d.ts
│
├── shared/
│   └── stores/
│       ├── animation.store.ts
│       ├── theme.store.ts
│       └── toast.store.ts
│
├── features/
│   ├── code/
│   │   ├── api/
│   │   │   └── file.api.ts
│   │   ├── stores/
│   │   │   └── codeTab.store.ts
│   │   └── __tests__/
│   │       └── codeTab.store.test.ts
│   │
│   ├── conversation/
│   │   ├── api/
│   │   │   └── conversation.api.ts
│   │   ├── stores/
│   │   │   └── conversation.store.ts
│   │   ├── conversation.reducer.ts
│   │   └── __tests__/
│   │       ├── conversation.api.test.ts
│   │       ├── conversation.reducer.test.ts
│   │       └── conversation.store.test.ts
│   │
│   ├── git/
│   │   ├── api/
│   │   │   └── git.api.ts
│   │   └── stores/
│   │       └── git.store.ts
│   │
│   ├── llm/
│   │   ├── api/
│   │   │   └── llm.api.ts
│   │   ├── provider.actions.ts
│   │   ├── providerDraft.ts
│   │   ├── llmSettings.loader.ts
│   │   ├── useSettingsPageController.ts
│   │   └── __tests__/
│   │       └── llmSettings.loader.test.ts
│   │
│   ├── plugins/
│   │   └── api/
│   │       └── plugin.api.ts
│   │
│   ├── projects/
│   │   ├── api/
│   │   │   └── project.api.ts
│   │   ├── stores/
│   │   │   └── project.store.ts
│   │   ├── project.loader.ts
│   │   └── __tests__/
│   │       └── project.loader.test.ts
│   │
│   ├── sessions/
│   │   ├── api/
│   │   │   └── session.api.ts
│   │   ├── stores/
│   │   │   └── session.store.ts
│   │   ├── session.actions.ts
│   │   └── __tests__/
│   │       ├── session.actions.test.ts
│   │       └── session.store.test.ts
│   │
│   ├── settings/                    ← 原 uiSettings
│   │   ├── api/
│   │   │   └── uiSettings.api.ts
│   │   └── stores/
│   │       └── settings.store.ts
│   │
│   ├── skills/
│   │   └── api/
│   │       └── skill.api.ts
│   │
│   ├── terminal/
│   │   └── stores/
│   │       └── terminal.store.ts
│   │
│   └── workspace/
│       ├── stores/
│       │   └── workspace.store.ts
│       ├── autoScroll.ts
│       ├── sessionSelection.ts
│       ├── types.ts
│       └── __tests__/
│           ├── autoScroll.test.ts
│           └── sessionSelection.test.ts
│
├── hooks/
│   ├── useConversationData.ts
│   ├── useConversationRuntime.ts
│   ├── useCurrentSessionViewModel.ts
│   ├── useSendMessage.ts
│   ├── useSessionData.ts
│   ├── useSessionSelection.ts
│   ├── useStreamingMessage.ts
│   ├── useToast.ts
│   ├── useSidebarFilteredProjects.ts      ← 从 components 移入
│   ├── useSidebarProjectActions.ts         ← 从 components 移入
│   ├── useSidebarSessionActions.ts         ← 从 components 移入
│   ├── useSettingsPageController.ts        ← 从 features 移入
│   └── __tests__/
│       ├── useConversationData.test.ts
│       ├── useConversationRuntime.test.ts
│       ├── useCurrentSessionViewModel.test.ts
│       ├── useSendMessage.test.ts
│       ├── useSessionData.test.ts
│       ├── useSessionSelection.test.ts
│       ├── useSidebarFilteredProjects.test.ts
│       ├── useSidebarProjectActions.test.ts
│       └── useSidebarSessionActions.test.ts
│
├── services/
│   ├── apiClient.ts
│   ├── desktopClient.ts
│   ├── dialogService.ts
│   ├── runtimeConfig.ts
│   ├── sessionConversationWebSocket.ts
│   ├── terminalIpc.ts
│   └── __tests__/
│       ├── backendManagerPackaging.test.ts
│       ├── backendRuntimeRequirements.test.ts
│       ├── dialogService.test.ts
│       ├── runtimeConfig.test.ts
│       └── sessionConversationWebSocket.test.ts
│
├── types/
│   ├── animation.ts
│   ├── conversation.ts
│   ├── electron.d.ts
│   ├── file.ts
│   ├── fileTree.ts
│   ├── git.ts
│   ├── llm.ts
│   ├── plan.ts
│   ├── plugin.ts
│   ├── project.ts
│   ├── skill.ts
│   └── workspace.ts
│
├── utils/
│   ├── activeRun.ts
│   └── llmHelpers.ts
│
├── components/
│   ├── animations/
│   ├── chat/
│   │   ├── ChatInput.tsx
│   │   ├── MarkdownRenderer.tsx
│   │   └── __tests__/
│   │       └── ChatInput.test.ts
│   ├── common/
│   ├── execution/
│   ├── layout/
│   │   ├── WorkspaceSidebar.tsx
│   │   ├── sidebarBusy.ts
│   │   └── __tests__/
│   │       ├── sidebarBusy.test.ts
│   │       ├── useSidebarFilteredProjects.test.ts  ← 如果 hook 不移走
│   │       ├── useSidebarProjectActions.test.ts
│   │       └── useSidebarSessionActions.test.ts
│   ├── terminal/
│   └── workspace/
│       ├── ... (组件文件)
│       └── __tests__/
│           ├── ToolTraceCard.test.tsx
│           └── transcriptItems.test.ts
│
└── pages/
    ├── AgentWorkspace.tsx
    ├── AutomationPage.tsx
    ├── PluginsPage.tsx
    ├── SettingsPage.tsx
    ├── SkillsPage.tsx
    ├── settings/
    │   ├── AboutPanel.tsx
    │   ├── BrowserPanel.tsx
    │   ├── DefaultModelPanel.tsx
    │   ├── DisplayOptionsPanel.tsx
    │   └── ProviderPanel.tsx
    └── __tests__/
        └── AgentWorkspace.test.tsx
```

---

## 📝 每阶段验证清单

### 通用验证（每个阶段完成后）

```bash
# 1. TypeScript 类型检查
cd frontend && npm run typecheck

# 2. 运行测试
npm test

# 3. 构建验证
npm run build

# 4. 开发服务器启动
npm run dev
```

### 阶段 1 额外验证

- [ ] `stores/` 目录已删除
- [ ] `test/` 空目录已删除
- [ ] 所有 `__tests__/` 目录已创建
- [ ] 所有 `.store.ts` 文件可被 `*.store.ts` glob 搜索到
- [ ] 所有测试文件在 `__tests__/` 下

### 阶段 2 额外验证

- [ ] 所有 API 文件在 `api/` 子目录下
- [ ] 所有 `.api.ts` / `.reducer.ts` / `.actions.ts` / `.loader.ts` 后缀正确
- [ ] 对应测试文件跟随重命名

### 阶段 3 额外验证

- [ ] 所有 hook 文件在正确位置
- [ ] `features/uiSettings/` 已重命名为 `features/settings/`
- [ ] 无残留空目录

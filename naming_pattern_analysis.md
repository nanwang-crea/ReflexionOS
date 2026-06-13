# ReflexionOS 命名模式分析报告

## 📊 当前命名模式统计

### Store 文件 (15 个)

| 位置 | 文件名 | 当前命名模式 | 一致性 |
|------|--------|-------------|--------|
| `/stores/` | `animationStore.ts` | camelCase + Store | ✓ |
| `/stores/` | `projectStore.ts` | camelCase + Store | ✓ |
| `/stores/` | `settingsStore.ts` | camelCase + Store | ✓ |
| `/stores/` | `themeStore.ts` | camelCase + Store | ✓ |
| `/stores/` | `toastStore.ts` | camelCase + Store | ✓ |
| `/stores/` | `workspaceStore.ts` | camelCase + Store | ✓ |
| `/features/code/` | `codeTabStore.ts` | camelCase + Store | ✓ |
| `/features/conversation/` | `conversationStore.ts` | camelCase + Store | ✓ |
| `/features/git/` | `gitStore.ts` | camelCase + Store | ✓ |
| `/features/sessions/` | `sessionStore.ts` | camelCase + Store | ✓ |
| `/features/terminal/` | `terminalStore.ts` | camelCase + Store | ✓ |

**当前模式**: `{entity}Store.ts`（camelCase）
**一致性**: ✅ 100% 一致

---

### API 文件 (9 个)

| 位置 | 文件名 | 当前命名模式 | 一致性 |
|------|--------|-------------|--------|
| `/features/code/` | `fileApi.ts` | camelCase + Api | ✓ |
| `/features/conversation/` | `conversationApi.ts` | camelCase + Api | ✓ |
| `/features/git/` | `gitApi.ts` | camelCase + Api | ✓ |
| `/features/llm/` | `llmApi.ts` | camelCase + Api | ✓ |
| `/features/plugins/` | `pluginApi.ts` | camelCase + Api | ✓ |
| `/features/projects/` | `projectApi.ts` | camelCase + Api | ✓ |
| `/features/sessions/` | `sessionApi.ts` | camelCase + Api | ✓ |
| `/features/skills/` | `skillApi.ts` | camelCase + Api | ✓ |
| `/features/uiSettings/` | `uiSettingsApi.ts` | camelCase + Api | ✓ |

**当前模式**: `{entity}Api.ts`（camelCase）
**一致性**: ✅ 100% 一致

---

### Service 文件 (7 个)

| 位置 | 文件名 | 当前命名模式 | 一致性 |
|------|--------|-------------|--------|
| `/services/` | `apiClient.ts` | camelCase + Client | ✓ |
| `/services/` | `desktopClient.ts` | camelCase + Client | ✓ |
| `/services/` | `dialogService.ts` | camelCase + Service | ✓ |
| `/services/` | `runtimeConfig.ts` | camelCase + Config | ✓ |
| `/services/` | `sessionConversationWebSocket.ts` | camelCase + WebSocket | ✓ |
| `/services/` | `terminalIpc.ts` | camelCase + Ipc | ✓ |

**当前模式**: `{entity}ype}.ts`（camelCase + 类型后缀）
**一致性**: ✅ 100% 一致，但后缀多样化（Client, Service, Config, WebSocket, Ipc）

---

### Actions 文件 (4 个)

| 位置 | 文件名 | 当前命名模式 | 一致性 |
|------|--------|-------------|--------|
| `/components/execution/` | `approvalActions.ts` | camelCase + Actions | ✓ |
| `/features/llm/` | `providerActions.ts` | camelCase + Actions | ✓ |
| `/features/sessions/` | `sessionActions.ts` | camelCase + Actions | ✓ |
| `/hooks/` | `useSessionActions.ts` | use + camelCase + Actions | ⚠️ |

**当前模式**: `{entity}Actions.ts`（camelCase）
**特例**: `useSessionActions.ts` 是 React hook，不是纯 actions

---

### Hooks 文件 (11 个)

| 文件名 | 命名模式 |
|--------|---------|
| `useConversationData.ts` | use + Entity + Data |
| `useConversationRuntime.ts` | use + Entity + Runtime |
| `useCurrentSessionViewModel.ts` | use + ViewModel |
| `useSendMessage.ts` | use + Action |
| `useSessionActions.ts` | use + Entity + Actions |
| `useSessionData.ts` | use + Entity + Data |
| `useSessionSelection.ts` | use + Entity + Selection |
| `useStreamingMessage.ts` | use + Feature |
| `useToast.ts` | use + Entity |
| `useSidebarProjectActions.ts` | use + UI + Entity + Actions |
| `useSidebarSessionActions.ts` | use + UI + Entity + Actions |

**当前模式**: `use{Feature}.ts`（camelCase）
**一致性**: ✅ 符合 React hooks 约定

---

## 🔍 关键发现

### 1. **当前命名高度一致**
- ✅ Store: 100% 使用 `{entity}Store.ts`
- ✅ API: 100% 使用 `{entity}Api.ts`
- ✅ Hooks: 100% 使用 `use{Feature}.ts`
- ✅ 所有文件使用 camelCase

### 2. **问题：混淆与可识别性**
虽然命名一致，但 **文件角色不够明显**：
- ❌ `projectStore.ts` vs `projectApi.ts` - 需要看后缀才知道区别
- ❌ 在 IDE 文件列表中，很难一眼区分类型
- ❌ 搜索时需要精确匹配 camelCase

### 3. **行业对比**

| 项目 | Store 命名 | 特点 |
|------|-----------|------|
| **Plane.so** | `project.store.ts` | 使用 `.store.ts` 后缀 |
| **Excalidraw** | `StoreAction.ts` | PascalCase |
| **Redux Toolkit** | `projectSlice.ts` | 使用 `.slice.ts` 后缀 |
| **ReflexionOS（当前）** | `projectStore.ts` | camelCase + Store |

---

## 💡 推荐方案对比

### 方案 A：保持当前模式 + 重组目录

**不改文件名，只重组目录结构**

```
frontend/src/
├── features/
│   ├── projects/
│   │   ├── stores/
│   │   │   └── projectStore.ts      ← 保持现有命名
│   │   └── api/
│   │       └── projectApi.ts
└── shared/
    └── stores/
        └── themeStore.ts
```

**优点**：
- ✅ 最小改动，降低迁移风险
- ✅ 保持团队熟悉的命名习惯
- ✅ 不需要更新大量导入路径中的文件名

**缺点**：
- ❌ 不符合业界主流（`.store.ts` 后缀）
- ❌ IDE 搜索仍需精确 camelCase
- ❌ 文件类型不够明显

---

### 方案 B：采用业界标准 `.store.ts` 后缀

**改为 `.store.ts` 后缀 + 重组目录**

```
frontend/src/
├── features/
│   ├── projects/
│   │   ├── stores/
│   │   │   └── project.store.ts     ← 新命名
│   │   └── api/
│   │       └── project.api.ts       ← 新命名
└── shared/
    └── stores/
        └── theme.store.ts
```

**优点**：
- ✅ **符合业界标准**（Plane.so, MobX 社区）
- ✅ **文件类型明显**：`.store.ts` 一眼识别
- ✅ **IDE 友好**：搜索 `*.store.ts` 即可
- ✅ **更好的可读性**：`project.store.ts` vs `projectStore.ts`
- ✅ **统一后缀风格**：
  - `project.store.ts`
  - `project.api.ts`
  - `project.service.ts`
  - `project.actions.ts`

**缺点**：
- ⚠️ 需要重命名所有 store 和 API 文件
- ⚠️ 需要更新所有导入路径
- ⚠️ 迁移工作量较大

**迁移影响**：
- 需重命名：~24 个文件（11 stores + 9 APIs + actions）
- 需更新导入：预计 100+ 处

---

### 方案 C：混合方案（推荐）

**核心文件用 `.store.ts`，其他保持不变**

```
frontend/src/
├── features/
│   ├── projects/
│   │   ├── stores/
│   │   │   └── project.store.ts     ← 改
│   │   └── api/
│   │       └── projectApi.ts        ← 不改
└── shared/
    └── stores/
        └── theme.store.ts            ← 改
```

**规则**：
- ✅ Store 文件：改为 `.store.ts`（最重要的状态管理文件）
- ✅ API 文件：保持 `Api.ts`（已经够清晰）
- ✅ Hooks：保持 `use*.ts`（React 约定）
- ✅ Services：保持 `*Service.ts`（已经够清晰）

**优点**：
- ✅ 核心状态管理文件更专业（符合业界）
- ✅ 减少迁移工作量（只改 stores）
- ✅ 保持其他文件的稳定性

**缺点**：
- ⚠️ 命名风格不完全统一（但可以接受）

**迁移影响**：
- 需重命名：~11 个 store 文件
- 需更新导入：预计 50-70 处

---

## 📋 最终推荐

### 🎯 **推荐方案 C：混合方案**

**理由**：
1. **平衡专业性与实用性**：
   - Store 是状态管理的核心，值得采用业界标准
   - API/Service 已经足够清晰，不必改动

2. **最小化迁移风险**：
   - 只改 11 个文件，而非 24 个
   - 减少 50% 的导入更新工作

3. **渐进式改进**：
   - 先改 stores，未来可选择性改其他
   - 不影响现有开发节奏

---

## 🔄 实施步骤（方案 C）

### 阶段 1：目录重组
1. 创建 `/shared/stores/` 目录
2. 移动 UI 相关 stores（theme, toast, animation）
3. 在各 feature 下创建 `stores/` 子目录
4. 移动业务 stores 到对应 feature

### 阶段 2：重命名 Store 文件
```bash
# /stores
animationStore.ts → animation.store.ts
projectStore.ts → project.store.ts
settingsStore.ts → settings.store.ts
themeStore.ts → theme.store.ts
toastStore.ts → toast.store.ts
workspaceStore.ts → workspace.store.ts

# /features/*
codeTabStore.ts → codeTab.store.ts
conversationStore.ts → conversation.store.ts
gitStore.ts → git.store.ts
sessionStore.ts → session.store.ts
terminalStore.ts → terminal.store.ts
```

### 阶段 3：更新导入路径
- 使用 IDE 重构功能批量更新
- 或使用 find-and-replace 工具

### 阶段 4：验证
- 运行 TypeScript 类型检查
- 运行构建
- 运行测试套件

---

## 📊 命名规范总结（方案 C）

| 文件类型 | 命名模式 | 示例 |
|---------|---------|------|
| **Store** | `{entity}.store.ts` | `project.store.ts` |
| **API** | `{entity}Api.ts` | `projectApi.ts` |
| **Service** | `{entity}Service.ts` | `dialogService.ts` |
| **Actions** | `{entity}Actions.ts` | `sessionActions.ts` |
| **Hook** | `use{Feature}.ts` | `useSessionData.ts` |
| **Component** | `{Name}.tsx` | `ProjectList.tsx` |
| **Type** | `{entity}.ts` | `project.ts` |
| **Utils** | `{purpose}.ts` | `llmHelpers.ts` |

**关键规则**：
- ✅ Store 文件使用 `.store.ts` 后缀（kebab-case 之前的部分）
- ✅ 其他文件保持 camelCase + 类型后缀
- ✅ 组件使用 PascalCase
- ✅ Types 目录使用简单名词

---

## ✅ 决策建议

**建议采用方案 C**，原因：
1. 专业性：Store 采用业界标准 `.store.ts`
2. 实用性：减少 50% 迁移工作量
3. 可维护性：清晰的文件类型识别
4. 扩展性：未来可渐进式改进其他文件

**需要用户确认**：
- [ ] 是否采用方案 C（混合方案）
- [ ] 是否现在执行重构
- [ ] 是否需要调整方案细节

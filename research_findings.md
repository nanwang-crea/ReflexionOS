# React 项目 Store/State 组织方式研究报告

## 研究目标
了解中大型 React 项目如何组织 stores 和状态管理，特别是命名规范和目录结构。

## 研究来源

### 1. **Bulletproof React** (GitHub: alan2207/bulletproof-react)
这是一个广受认可的 React 架构指南，提出了基于功能的架构：

```
src/
├── features/
│   ├── auth/
│   │   ├── api/
│   │   ├── components/
│   │   ├── stores/          ← 每个功能有自己的 stores/
│   │   └── types/
│   ├── discussions/
│   │   ├── api/
│   │   ├── components/
│   │   ├── stores/
│   │   └── types/
│   └── users/
│       ├── api/
│       ├── components/
│       ├── stores/
│       └── types/
└── stores/                  ← 全局共享的 stores
    ├── notifications.ts
    └── theme.ts
```

**关键点**：
- 每个功能域（feature）内部有自己的 `stores/` 子目录
- 顶层 `stores/` 只放真正全局的状态（通知、主题等）
- **命名方式**：`notifications.ts`, `theme.ts`（单数或复数名词）

---

### 2. **Plane.so** (GitHub: makeplane/plane)
现代项目管理工具，使用 MobX：

```
web/
├── store/
│   ├── application/         ← 应用级状态
│   │   ├── theme.store.ts
│   │   └── router.store.ts
│   ├── issue/              ← 业务实体
│   │   ├── issue.store.ts
│   │   └── issue-detail.store.ts
│   ├── project/
│   │   ├── project.store.ts
│   │   └── project-view.store.ts
│   └── root.store.ts       ← 根 store
```

**关键点**：
- 统一的 `/store` 目录，但内部按功能域分组
- **命名规范**：`{entity}.store.ts`（明确的 `.store.ts` 后缀）
- 分层结构：`application/` vs 业务实体目录

---

### 3. **Excalidraw** (GitHub: excalidraw/excalidraw)
白板应用，使用自定义状态管理：

```
packages/excalidraw/
├── store/
│   ├── StoreAction.ts
│   └── types.ts
├── actions/
│   ├── actionHistory.ts
│   ├── actionCanvas.ts
│   └── ...
└── components/
```

**关键点**：
- 单一 `store/` 目录
- 更多使用 `actions/` 模式（类似 Redux）

---

### 4. **Redux Toolkit 官方示例**
Real-world example:

```
src/
├── features/
│   ├── users/
│   │   └── usersSlice.ts
│   ├── repos/
│   │   └── reposSlice.ts
│   └── ...
└── app/
    └── store.ts
```

**关键点**：
- **命名规范**：`{entity}Slice.ts`（Redux Toolkit 约定）
- 每个功能一个文件

---

### 5. **Cal.com** (GitHub: calcom/cal.com)
调度平台：

```
apps/web/
├── lib/
│   ├── hooks/
│   │   ├── useBooking.ts
│   │   └── useSchedule.ts
│   └── ...
└── server/
    └── lib/
```

**关键点**：
- 不使用集中的 store 目录
- 使用 React hooks + context
- **命名规范**：`use{Entity}.ts`

---

## 业界主流命名规范总结

### Store 文件命名

| 方式 | 示例 | 使用场景 |
|------|------|---------|
| `.store.ts` 后缀 | `project.store.ts` | MobX、自定义状态管理 |
| `Slice.ts` 后缀 | `projectSlice.ts` | Redux Toolkit |
| `Store.ts` 后缀 | `projectStore.ts` | Zustand、Jotai |
| `use` 前缀 | `useProject.ts` | React hooks + context |
| 简单名词 | `project.ts` | 小型项目 |

### 目录组织

**方式 A：集中式 + 分类**
```
src/
└── stores/
    ├── ui/              ← 明确分类
    │   ├── theme.store.ts
    │   └── toast.store.ts
    └── domain/
        ├── project.store.ts
        └── session.store.ts
```

**方式 B：功能域内嵌（推荐用于中大型项目）**
```
src/
├── features/
│   ├── projects/
│   │   ├── api/
│   │   ├── components/
│   │   └── stores/      ← store 在功能内部
│   │       └── project.store.ts
│   └── sessions/
│       └── stores/
│           └── session.store.ts
└── shared/
    └── stores/          ← 只有真正共享的
        ├── theme.store.ts
        └── toast.store.ts
```

**方式 C：平级式（扁平化）**
```
src/
├── stores/
│   ├── projectStore.ts
│   ├── sessionStore.ts
│   ├── themeStore.ts
│   └── toastStore.ts
└── features/
    └── ...
```

---

## 针对我们项目的建议

### 现状问题
1. `/stores` 和 `/features/*/` 混合，分类标准不清
2. 文件命名不统一：`projectStore.ts` vs `conversationStore.ts`
3. 新开发者不知道在哪里创建新 store

### 推荐方案：**方式 B（功能域内嵌）+ 统一命名**

```
frontend/src/
├── features/
│   ├── projects/
│   │   ├── api/
│   │   │   └── projectApi.ts
│   │   ├── components/
│   │   └── stores/
│   │       └── project.store.ts       ✓ 统一后缀
│   ├── workspace/
│   │   └── stores/
│   │       └── workspace.store.ts
│   ├── conversation/
│   │   ├── api/
│   │   └── stores/
│   │       └── conversation.store.ts
│   ├── sessions/
│   │   ├── api/
│   │   └── stores/
│   │       └── session.store.ts
│   ├── code/
│   │   ├── api/
│   │   └── stores/
│   │       └── codeTab.store.ts
│   ├── terminal/
│   │   └── stores/
│   │       └── terminal.store.ts
│   ├── git/
│   │   ├── api/
│   │   └── stores/
│   │       └── git.store.ts
│   └── settings/
│       ├── api/
│       └── stores/
│           └── settings.store.ts
│
└── shared/
    └── stores/
        ├── theme.store.ts          ✓ 纯 UI 状态
        ├── toast.store.ts
        └── animation.store.ts
```

### 命名规范

**文件命名**：`{entity}.store.ts`
- ✅ `project.store.ts`
- ✅ `session.store.ts`
- ✅ `theme.store.ts`
- ❌ `projectStore.ts`（旧方式）
- ❌ `useProject.ts`（这是 hook）

**Export 名称**：
```typescript
// project.store.ts
export const useProjectStore = create(...)
export type ProjectStore = ...
```

### 导入路径

使用 TypeScript path mapping：
```json
{
  "paths": {
    "@/features/*": ["./src/features/*"],
    "@/shared/*": ["./src/shared/*"]
  }
}
```

**导入示例**：
```typescript
// ✅ 清晰的路径
import { useProjectStore } from '@/features/projects/stores/project.store'
import { useThemeStore } from '@/shared/stores/theme.store'

// ❌ 旧方式（混乱）
import { useProjectStore } from '@/stores/projectStore'
import { useConversationStore } from '@/features/conversation/conversationStore'
```

---

## 优势

1. **清晰的分类标准**：
   - 业务逻辑 → `/features/{domain}/stores/`
   - 纯 UI 状态 → `/shared/stores/`

2. **统一的命名规范**：
   - 所有 store 文件都用 `.store.ts` 后缀
   - 一看就知道是状态管理文件

3. **可扩展性**：
   - 新功能在 `/features/` 下自成体系
   - 每个功能域的 `api/`, `components/`, `stores/` 并列

4. **避免循环依赖**：
   - 功能域之间不直接依赖
   - 只依赖 `/shared/`

5. **更好的 IDE 体验**：
   - 自动补全时路径更清晰
   - 文件搜索更精准（搜 `*.store.ts`）

---

## 迁移检查清单

- [ ] 创建 `/shared/stores/` 目录
- [ ] 移动 UI 相关 stores（theme, toast, animation）
- [ ] 在各 feature 下创建 `stores/` 子目录
- [ ] 移动业务 stores 到对应 feature
- [ ] 重命名所有文件为 `.store.ts` 后缀
- [ ] 更新所有导入路径
- [ ] 更新 TypeScript path mapping
- [ ] 运行构建验证
- [ ] 更新文档

---

## 参考资料

- [Bulletproof React](https://github.com/alan2207/bulletproof-react)
- [Plane Architecture](https://github.com/makeplane/plane)
- [Redux Style Guide](https://redux.js.org/style-guide/)
- [Zustand Best Practices](https://github.com/pmndrs/zustand)

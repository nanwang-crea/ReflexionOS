# ReflexionOS Store & API 重组方案

## 📋 执行摘要

**方案类型**：混合方案（方案 C）
**预计工作量**：中等（约 2-3 小时）
**文件变动**：移动 11 个 store 文件 + 重命名为 `.store.ts` 后缀
**导入更新**：预计 50-70 处
**风险等级**：低（TypeScript 会捕获所有断开的引用）

---

## 🎯 目标

1. **统一组织**：将 stores 按功能域和共享层分类
2. **专业命名**：Store 文件采用业界标准 `.store.ts` 后缀
3. **清晰结构**：路径即文档，一眼看出文件职责
4. **最小迁移**：只改 stores，保持其他文件稳定

---

## 📂 目标目录结构

```
frontend/src/
├── features/
│   ├── code/
│   │   ├── api/
│   │   │   └── fileApi.ts              ← 保持不变
│   │   └── stores/
│   │       └── codeTab.store.ts         ← 新：从 features/code/ 移入 + 重命名
│   │
│   ├── conversation/
│   │   ├── api/
│   │   │   └── conversationApi.ts      ← 保持不变
│   │   └── stores/
│   │       └── conversation.store.ts    ← 新：从 features/conversation/ 移入 + 重命名
│   │
│   ├── git/
│   │   ├── api/
│   │   │   └── gitApi.ts               ← 保持不变
│   │   └── stores/
│   │       └── git.store.ts             ← 新：从 features/git/ 移入 + 重命名
│   │
│   ├── projects/
│   │   ├── api/
│   │   │   └── projectApi.ts           ← 保持不变
│   │   └── stores/
│   │       └── project.store.ts         ← 新：从 /stores/ 移入 + 重命名
│   │
│   ├── sessions/
│   │   ├── api/
│   │   │   └── sessionApi.ts           ← 保持不变
│   │   └── stores/
│   │       └── session.store.ts         ← 新：从 features/sessions/ 移入 + 重命名
│   │
│   ├── settings/
│   │   ├── api/
│   │   │   └── uiSettingsApi.ts        ← 保持不变
│   │   └── stores/
│   │       └── settings.store.ts        ← 新：从 /stores/ 移入 + 重命名
│   │
│   ├── terminal/
│   │   └── stores/
│   │       └── terminal.store.ts        ← 新：从 features/terminal/ 移入 + 重命名
│   │
│   └── workspace/
│       └── stores/
│           └── workspace.store.ts       ← 新：从 /stores/ 移入 + 重命名
│
└── shared/
    └── stores/
        ├── animation.store.ts           ← 新：从 /stores/ 移入 + 重命名
        ├── theme.store.ts               ← 新：从 /stores/ 移入 + 重命名
        └── toast.store.ts               ← 新：从 /stores/ 移入 + 重命名
```

---

## 🔑 为什么 `.store.ts` 后缀解决了"难以区分"的问题

### 问题重述
你提到："按功能划分的只看名字也很难区分文件哪个是做什么的"

### 解决方案：后缀明确文件角色

**之前（混乱）**：
```
features/projects/
├── projectStore.ts      ← 是 store？还是其他？
├── projectApi.ts        ← 是 API？还是其他？
├── projectLoader.ts     ← 是什么？
└── projectActions.ts    ← 是什么？
```
👎 **问题**：需要看完整的 camelCase 单词才知道类型

**之后（清晰）**：
```
features/projects/
├── stores/
│   └── project.store.ts      ← 一眼看出：Store 文件
├── api/
│   └── projectApi.ts         ← 一眼看出：API 文件
├── projectLoader.ts          ← 业务逻辑
└── projectActions.ts         ← 业务逻辑
```
👍 **优势**：
1. **路径 = 角色**：`stores/` 目录明确是状态管理
2. **后缀 = 类型**：`.store.ts` 后缀是行业标准标识
3. **IDE 搜索**：搜 `*.store.ts` 找到所有 stores
4. **文件列表**：在 IDE 侧边栏，后缀排序清晰

---

### 真实对比：文件列表视图

**之前（VSCode 文件树）**：
```
📁 features/projects/
  📄 projectApi.ts
  📄 projectLoader.ts
  📄 projectStore.ts        ← 混在一起，需要逐个识别
  📄 project.test.ts
```

**之后（VSCode 文件树）**：
```
📁 features/projects/
  📁 api/
    📄 projectApi.ts        ← 清晰分组
  📁 stores/
    📄 project.store.ts     ← 清晰分组
  📄 projectLoader.ts
  📄 project.test.ts
```

---

### 业界案例：Plane.so 的实际文件列表

我研究的 Plane.so 项目就是这样组织的：

```
web/store/
├── application/
│   ├── theme.store.ts       ← 一眼看出是 store
│   └── router.store.ts
├── issue/
│   ├── issue.store.ts
│   └── issue-detail.store.ts
└── project/
    └── project.store.ts
```

**搜索体验**：
- 搜 `*.store.ts` → 找到所有 stores
- 搜 `theme` → 可能找到 `themeUtils.ts`, `ThemeProvider.tsx`, `theme.store.ts`
- 搜 `theme.store` → 精确定位到状态管理

---

## 📝 详细迁移清单

### A. 创建新目录

```bash
# Shared stores
mkdir -p frontend/src/shared/stores

# Feature stores subdirectories
mkdir -p frontend/src/features/code/stores
mkdir -p frontend/src/features/conversation/stores
mkdir -p frontend/src/features/git/stores
mkdir -p frontend/src/features/projects/stores
mkdir -p frontend/src/features/sessions/stores
mkdir -p frontend/src/features/settings/stores
mkdir -p frontend/src/features/terminal/stores
mkdir -p frontend/src/features/workspace/stores
```

---

### B. 移动 + 重命名文件

#### B1. Shared Stores（UI 层，3 个文件）

```bash
git mv frontend/src/stores/animationStore.ts frontend/src/shared/stores/animation.store.ts
git mv frontend/src/stores/themeStore.ts frontend/src/shared/stores/theme.store.ts
git mv frontend/src/stores/toastStore.ts frontend/src/shared/stores/toast.store.ts
```

#### B2. Feature Stores（业务层，8 个文件）

```bash
# From /stores
git mv frontend/src/stores/projectStore.ts frontend/src/features/projects/stores/project.store.ts
git mv frontend/src/stores/settingsStore.ts frontend/src/features/settings/stores/settings.store.ts
git mv frontend/src/stores/workspaceStore.ts frontend/src/features/workspace/stores/workspace.store.ts

# From features/*/ (within feature directory)
git mv frontend/src/features/code/codeTabStore.ts frontend/src/features/code/stores/codeTab.store.ts
git mv frontend/src/features/conversation/conversationStore.ts frontend/src/features/conversation/stores/conversation.store.ts
git mv frontend/src/features/git/gitStore.ts frontend/src/features/git/stores/git.store.ts
git mv frontend/src/features/sessions/sessionStore.ts frontend/src/features/sessions/stores/session.store.ts
git mv frontend/src/features/terminal/terminalStore.ts frontend/src/features/terminal/stores/terminal.store.ts
```

#### B3. 同时移动相关测试文件

```bash
git mv frontend/src/features/code/codeTabStore.test.ts frontend/src/features/code/stores/codeTab.store.test.ts
git mv frontend/src/features/conversation/conversationStore.test.ts frontend/src/features/conversation/stores/conversation.store.test.ts
git mv frontend/src/features/sessions/sessionStore.test.ts frontend/src/features/sessions/stores/session.store.test.ts
git mv frontend/src/features/terminal/terminalStore.test.ts frontend/src/features/terminal/stores/terminal.store.test.ts
```

#### B4. 删除空目录

```bash
rmdir frontend/src/stores
```

---

## 🔄 导入路径更新映射表

| 旧导入 | 新导入 |
|--------|--------|
| `@/stores/animationStore` | `@/shared/stores/animation.store` |
| `@/stores/projectStore` | `@/features/projects/stores/project.store` |
| `@/stores/settingsStore` | `@/features/settings/stores/settings.store` |
| `@/stores/themeStore` | `@/shared/stores/theme.store` |
| `@/stores/toastStore` | `@/shared/stores/toast.store` |
| `@/stores/workspaceStore` | `@/features/workspace/stores/workspace.store` |
| `@/features/code/codeTabStore` | `@/features/code/stores/codeTab.store` |
| `@/features/conversation/conversationStore` | `@/features/conversation/stores/conversation.store` |
| `@/features/git/gitStore` | `@/features/git/stores/git.store` |
| `@/features/sessions/sessionStore` | `@/features/sessions/stores/session.store` |
| `@/features/terminal/terminalStore` | `@/features/terminal/stores/terminal.store` |

---

## ✅ 验证步骤

```bash
# 1. TypeScript 类型检查
cd frontend && npm run typecheck

# 2. 构建测试
npm run build

# 3. 运行测试套件
npm test

# 4. 启动开发服务器
npm run dev
```

---

## 📊 工作量评估

| 阶段 | 预计时间 |
|------|---------|
| 创建新目录 + 移动文件 | 25 分钟 |
| 更新导入路径 | 30-45 分钟 |
| TypeScript 检查 + 修复 | 15-30 分钟 |
| 测试验证 | 30-45 分钟 |
| **总计** | **2-3 小时** |

---

## 🎯 成功标准

- [ ] 所有 11 个 store 文件移动到正确位置
- [ ] 所有文件使用 `.store.ts` 后缀
- [ ] `/stores` 目录已删除
- [ ] TypeScript 类型检查 0 错误
- [ ] 构建成功
- [ ] 所有测试通过
- [ ] 应用正常运行

---

## 🤝 需要确认

在执行前，请确认：

- [ ] **方案认可**：是否同意采用 `.store.ts` 后缀 + 目录重组
- [ ] **执行时机**：是否现在开始执行
- [ ] **分支策略**：是否在新分支执行

**准备好了吗？我可以立即开始执行重组。**

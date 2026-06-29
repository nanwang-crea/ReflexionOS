# ReflexionOS 文档导航地图

快速指南：根据你的需求，找到对应的文档位置。

---

## 🎯 按使用场景导航

### 1️⃣ 面试准备（求职、技术面）

**目的**：深度了解项目亮点、技术方案、为面试做准备

| 文档 | 位置 | 内容 |
|------|------|------|
| **项目整体介绍** | `docs/interview/project-features-overview.md` | 全景功能、技术栈、核心特性 |
| **简历项目稿** | `docs/interview/resume-project-intro.md` | 浓缩版项目介绍（1-2 分钟讲稿） |
| **面试备战指引** | `docs/interview/README.md` | 如何利用这些文档准备面试 |

**使用流程**：
1. 先读 `project-features-overview.md` 了解全景
2. 结合 `resume-project-intro.md` 准备讲稿
3. 根据面试官提问，补充对应功能的设计文档（见下面「功能文档」部分）

---

### 2️⃣ 功能说明与实现细节（理解某个功能如何做的）

**目的**：了解某个功能的设计方案、实现步骤、技术决策

**关键功能列表**：

#### 多会话并行（Multi-Session Parallel）
- **设计文档**：`docs/superpowers/specs/2026-06-22-multi-session-parallel-requirements.md`
  - 需求、架构、数据流、跨平台一致性
- **实现计划**：`docs/superpowers/plans/2026-06-22-multi-session-parallel-implementation-plan.md`
  - 分步任务、代码改动、测试验证

#### 工作记忆系统（Working Memory）
- **设计文档**：`docs/superpowers/specs/2026-06-21-working-memory-design.md`
  - 概念、数据结构、交互流程、边界条件
- **实现计划**：`docs/superpowers/plans/2026-06-23-working-memory-redesign.md`
  - 任务分解、测试策略

#### 子代理执行（Sub-Agent Execution）
- **设计文档**：`docs/superpowers/specs/2026-06-23-sub-agent-revised-design.md`
  - 子代理职责、通信协议、错误处理
- **实现计划**：`docs/superpowers/plans/2026-06-23-sub-agent-implementation.md`
  - 分步实现、测试覆盖

#### 应用内确认弹框（Confirm Dialog）
- **设计文档**：`docs/superpowers/specs/2026-06-24-confirm-dialog-design.md`
  - 需求、UI 设计、交互策略、跨平台一致性
- **实现计划**：`docs/superpowers/plans/2026-06-26-confirm-dialog-implementation-plan.md`
  - 任务拆分、代码示例、测试验证

#### 重置对话（Reset Conversation）
- **设计文档**：`docs/superpowers/specs/2026-06-23-reset-conversation-design.md`
  - 功能范围、状态管理、恢复策略
- **实现计划**：`docs/superpowers/plans/2026-06-24-reset-conversation-implementation-plan.md`

#### 文件附件（File Attachments）
- **设计文档**：`docs/superpowers/specs/2026-06-22-file-attachments-requirements.md`
  - 支持格式、大小限制、安全性、UI 流程

#### 上下文压缩器（Context Compressor Refactor）
- **设计文档**：`docs/superpowers/specs/2026-06-16-context-compressor-refactor-design.md`
- **实现计划**：`docs/superpowers/plans/2026-06-16-context-compressor-refactor.md`

**使用流程**：
1. 查找你感兴趣的功能
2. **先读设计文档**（specs）了解需求和方案
3. **再读实现计划**（plans）了解如何一步步做
4. 必要时查看对应的代码和 git commit

---

### 3️⃣ 项目研发进度与里程碑（了解项目发展历程）

**目的**：追踪项目从哪来、发展到哪、下一步去哪

| 文档 | 位置 | 内容 |
|------|------|------|
| **项目状态快照** | `docs/PROJECT_STATUS.md` | 当前功能完成度、已知问题、下一步计划 |
| **核心功能完成情况** | `docs/multimodal-integration-complete.md` | 多模态集成的阶段成果 |
| **代码目录树** | `docs/DIRECTORY_TREE.md` | 后端 + 前端代码结构说明 |
| **项目 README** | `docs/README.md` | 项目整体概况、快速开始 |

**关键时间线**：
- 2026-06-21 → 06-23：多会话并行 + 工作记忆系统
- 2026-06-23 → 06-24：子代理、重置对话、确认弹框
- 2026-06-24 → 现在：持续功能迭代

**使用流程**：
1. 先看 `PROJECT_STATUS.md` 了解当前全景
2. 查看 `DIRECTORY_TREE.md` 理解代码组织
3. 结合 `devlog/` 追踪具体改动（见下面「bug 修复记录」部分）

---

### 4️⃣ 开发过程与 Bug 修复记录（了解最近做了什么、修了哪些 bug）

**目的**：查看最近的开发活动、bug 修复、优化改进

| 文档位置 | 内容 | 更新频率 |
|---------|------|---------|
| `docs/devlog/devlog-2026-06-23_to_present.md` | 当前周期的日常开发记录 | 每次功能完成或 bug 修复后更新 |
| `docs/devlog/history-backfill.md` | 历史工作回填（较早的项目工作） | 不频繁更新 |
| `docs/devlog/README.md` | devlog 目录说明 | 不频繁更新 |

**什么记录在 devlog 里**：
- ✅ 功能实现完成
- ✅ Bug 修复与根因分析
- ✅ 性能优化
- ✅ 测试通过情况
- ✅ 跨平台兼容性验证

**什么不在 devlog 里**（在 git commit message 里）：
- 具体的代码行数改动
- 详细的实现代码
- 逐行的改动说明

**使用流程**：
1. 打开 `docs/devlog/devlog-2026-06-23_to_present.md`
2. 按时间向下浏览，找你关心的功能或 bug
3. 每条记录都有链接到对应的设计文档、PR、git commit
4. 需要代码细节时，跳转到 git commit 或代码仓库

---

### 5️⃣ Git 提交历史（代码级的改动细节）

**如何查看**：
```bash
# 查看最近 N 个 commit
git log --oneline -N

# 查看某个功能的所有 commit
git log --oneline --grep="应用内确认弹框"

# 查看某个文件的改动历史
git log -p frontend/src/services/dialogService.ts

# 查看某个 commit 的详细改动
git show <commit-hash>
```

**对应关系**：
- Commit message 通常格式：`feat/fix/refactor: 简短说明`
- 查看 PR 时可以看到整个功能的所有 commit
- 每个 commit 都有具体的代码 diff

---

## 📋 文档分类速查表

### 按来源分类

| 类型 | 文件夹 | 是否上库 | 用途 |
|------|--------|---------|------|
| **设计文档** | `docs/superpowers/specs/` | ✅ 上库 | 功能需求、方案设计、技术决策 |
| **实现计划** | `docs/superpowers/plans/` | ❌ 不上库* | 任务分解、开发步骤 |
| **开发日志** | `docs/devlog/` | ❌ 不上库* | 开发过程、bug 修复、优化记录 |
| **面试资料** | `docs/interview/` | ❌ 不上库* | 项目亮点、讲稿、素材 |
| **项目文档** | `docs/` 根目录 | ✅ 上库 | 项目整体概况、状态、结构 |
| **超能力配置** | `docs/superpowers/` | ✅ 上库 | 工作流工具说明 |

*注：实现计划、开发日志、面试资料这些是个人工作物，已通过 `.gitignore` 忽略，不会被上库。但你可以手动保留这些文件作为个人知识库。

---

## 🔍 常见查询场景

### 场景 1：准备技术面试，想讲某个功能

```
1. 打开：docs/interview/project-features-overview.md
   → 了解项目整体背景和这个功能的位置

2. 打开对应的设计文档，例如：
   docs/superpowers/specs/2026-06-22-multi-session-parallel-requirements.md
   → 理解功能需求、架构、技术决策

3. 打开对应的实现计划（如果需要讲实现细节）：
   docs/superpowers/plans/2026-06-22-multi-session-parallel-implementation-plan.md
   → 了解分步实现、关键技术点

4. 结合 git log 查看代码改动：
   git log --oneline --grep="multi-session"
   → 看具体实现
```

### 场景 2：想知道最近有什么新功能或 bug 修复

```
1. 打开：docs/devlog/devlog-2026-06-23_to_present.md
   → 按时间向下浏览，看最新的记录

2. 每条记录通常包含：
   - 功能名称 / bug 描述
   - 相关的设计文档链接
   - 相关的 PR / commit 链接
   - 验证情况（测试、跨平台等）

3. 需要代码细节时，点击 commit 链接或运行：
   git show <commit-hash>
```

### 场景 3：想深入了解项目的技术架构

```
1. 打开：docs/README.md
   → 快速了解项目是什么

2. 打开：docs/DIRECTORY_TREE.md
   → 了解代码目录结构和各模块职责

3. 打开：docs/PROJECT_STATUS.md
   → 了解当前功能完成度和技术栈

4. 逐个浏览 docs/superpowers/specs/ 下的设计文档
   → 深入理解核心功能的架构设计

5. 结合代码阅读：
   - 后端：backend/app/ 目录
   - 前端：frontend/src/ 目录
```

### 场景 4：想看某个功能是如何从零开始一步步实现的

```
1. 找到功能对应的设计文档（specs）和实现计划（plans）
   例：docs/superpowers/specs/2026-06-24-confirm-dialog-design.md
       docs/superpowers/plans/2026-06-26-confirm-dialog-implementation-plan.md

2. 设计文档告诉你：需求、为什么要做、方案是什么

3. 实现计划告诉你：分成哪些任务、每个任务怎么做、代码例子

4. 最后通过 git log 和代码仓库验证实现
```

---

## 📚 各文件夹的用途一览

### `docs/` 根目录
**公开文档**，已上库，所有人都应该看
- `README.md` — 项目整体说明
- `PROJECT_STATUS.md` — 项目状态、进度、已知问题
- `DIRECTORY_TREE.md` — 代码目录树结构
- `NAVIGATION.md` — 本文件，文档导航地图
- `INDEX.md` — 文档索引说明

### `docs/interview/`
**面试准备资料**，个人工作物，不上库
- `project-features-overview.md` — 项目全景、技术亮点
- `resume-project-intro.md` — 简历讲稿（浓缩版）
- `README.md` — 如何使用这些资料准备面试

### `docs/devlog/`
**开发日志**，个人工作物，不上库
- `devlog-2026-06-23_to_present.md` — 当前周期的日常记录
- `history-backfill.md` — 历史工作回填
- `README.md` — devlog 目录说明

### `docs/superpowers/`
**工作流与计划**
- `specs/` — 设计文档，**上库**
  - 每个新功能一个文件：`YYYY-MM-DD-<feature>-design.md`
  - 内容：需求、方案、技术决策、边界条件
  
- `plans/` — 实现计划，**不上库**
  - 每个功能一个文件：`YYYY-MM-DD-<feature>-implementation-plan.md`
  - 内容：分步任务、代码示例、测试验证
  
- `README.md` — 工作流说明
- `INSTALL.md` — 工具安装配置

---

## ⚡ 快速参考

### 我想...
- **了解项目是什么** → `docs/README.md`
- **准备面试讲项目** → `docs/interview/project-features-overview.md` + 对应功能的设计文档
- **看最近有什么改动** → `docs/devlog/devlog-2026-06-23_to_present.md`
- **深入理解某个功能** → `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md`
- **了解功能怎么实现的** → `docs/superpowers/plans/YYYY-MM-DD-<feature>-implementation-plan.md`
- **看项目进度** → `docs/PROJECT_STATUS.md`
- **查看代码改动** → `git log --oneline` + `git show <commit>`
- **理解代码结构** → `docs/DIRECTORY_TREE.md`

---

## 📝 维护说明

本导航地图每当新增重要文档时应更新，建议：
- 新功能完成后，更新 `docs/devlog/` 记录
- 新功能的设计文档添加到 `docs/superpowers/specs/`
- 面试准备素材添加到 `docs/interview/`
- 定期更新 `docs/PROJECT_STATUS.md` 反映项目最新进展

---

**最后更新**：2026-06-27

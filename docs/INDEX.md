# ReflexionOS 文档索引

本目录包含项目文档、开发日志、面试备战资料等。下面说明各个文件夹的作用。

## 目录结构

### 📋 项目文档（根目录）

- `README.md` — 项目整体说明
- `PROJECT_STATUS.md` — 项目当前状态、进度跟踪
- `DIRECTORY_TREE.md` — 代码目录树结构说明
- `multimodal-integration-complete.md` — 多模态集成完成情况

### 📝 开发日志（`devlog/`）

**用途**：记录开发过程、bug 修复、功能实现的细节。

- `README.md` — devlog 目录说明
- `devlog-2026-06-23_to_present.md` — 当前周期的开发日志
- `history-backfill.md` — 历史工作回填记录

**性质**：个人开发记录，不上库。可根据需要补充到 commit message 或项目 CHANGELOG。

### 🎯 面试备战（`interview/`）

**用途**：沉淀项目亮点、技术方案、设计决策，为面试准备素材。

- `README.md` — 面试备战指引
- `project-features-overview.md` — 项目功能全景
- `resume-project-intro.md` — 简历项目介绍稿

**性质**：个人资料，不上库。完成大功能后主动补充。

### ⚙️ 超能力计划与设计（`superpowers/`）

**用途**：存储项目开发过程中的 spec、plan、技能配置等。

#### `specs/` — 设计文档

每个新功能或大 bug 修复前，先写设计文档说明需求、方案、边界。

- `YYYY-MM-DD-<feature-name>-design.md` — 功能设计规格书

例：
- `2026-06-24-confirm-dialog-design.md` — 应用内确认弹框设计

**性质**：开发过程文档。与 plan、实现代码一起上库（或单独管理）。

#### `plans/` — 实现计划

基于设计文档，生成详细的任务分解与实现步骤。

- `YYYY-MM-DD-<feature-name>-implementation-plan.md` — 分步实现计划

例：
- `2026-06-26-confirm-dialog-implementation-plan.md` — 确认弹框实现计划
- `2026-06-23-sub-agent-implementation.md` — 子代理实现计划

**性质**：开发过程文档。通常不上库，或存放在 `.claude/` 私有目录。

#### `README.md` — 超能力说明

对项目使用的 superpowers 工作流的简要介绍。

#### `INSTALL.md` — 超能力安装

superpowers 插件的安装与配置指引。

---

## 文件提交策略

### ✅ 应该上库的

- 项目根级 `README.md`、`CHANGELOG.md` 等公开文档
- `docs/superpowers/specs/` 中的设计文档（重要设计决策的记录）
- `docs/interview/` 可选上库（若作为项目知识沉淀）

### ❌ 不上库的（个人记录）

- `docs/devlog/` — 开发过程日志
- `docs/superpowers/plans/` — 任务分解计划（临时工作物）
- 其他个人工作笔记、草稿

### 配置方案

在 `.gitignore` 中添加：

```gitignore
# 个人开发记录与工作计划（不上库）
docs/devlog/devlog-*.md
docs/devlog/history-backfill.md
docs/superpowers/plans/
```

或者使用全局 `.git/info/exclude`（仅本机生效，不影响他人）。

---

## 如何使用本文档

- **新手上路**：从 `README.md` 和 `PROJECT_STATUS.md` 开始
- **深入了解功能**：查看 `docs/superpowers/specs/` 中的设计文档
- **追踪开发进度**：查看 `docs/devlog/` 和项目 Git 提交历史
- **面试准备**：参考 `docs/interview/` 下的素材

---

**最后更新**：2026-06-27

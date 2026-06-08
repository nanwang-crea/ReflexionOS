# ReflexionOS 脏代码审查计划

> 创建日期：2026-06-08
> 状态：执行中
> 目标：系统性审查 ReflexionOS 全栈代码库（前端 + 后端），识别并分类所有脏代码

---

## 一、审查维度定义

| # | 维度 | 典型表现 |
|---|------|---------|
| 1 | **死代码** | 未被导入的模块、未调用的函数、被注释掉的代码块、未使用的变量/类型 |
| 2 | **重复代码** | 相同或高度相似的逻辑出现在 2+ 处，尤其是跨模块复制 |
| 3 | **职责不清** | 一个文件/函数做超过一件事；模块边界模糊，A 模块直接操作 B 模块的内部数据 |
| 4 | **注释违规** | 缺少文件级注释、函数级注释、复杂逻辑行内注释（对照 MEMORY.md 强制规范） |
| 5 | **类型安全缺陷** | 前端 `any` 类型滥用、缺失类型定义；后端缺少类型注解、返回值不明确 |
| 6 | **错误处理缺失** | 吞掉异常（bare `except`/`catch`）、错误信息不传播、降级策略缺失 |
| 7 | **硬编码与魔法值** | URL/端口/超时值直接写在业务代码中、状态字符串未提取常量 |

---

## 二、审查范围

### 后端（Python / FastAPI）

| 模块 | 路径 | 核心文件数 | 关注重点 |
|------|------|-----------|---------|
| api | `backend/app/api/` | routes + websocket_manager | 路由规范、WebSocket 管理职责单一性 |
| browser | `backend/app/browser/` | config, manager, models | Playwright 生命周期管理泄漏 |
| config | `backend/app/config/` | settings | 硬编码配置、未使用配置 |
| execution | `backend/app/execution/` | 15 个文件（最大模块） | 重复逻辑、职责交叉、死代码 |
| llm | `backend/app/llm/` | base, adapter, retry, token_counter | 重试逻辑与 orchestration 重复 |
| memory | `backend/app/memory/` | 10 个文件 | continuation/compaction/recall 边界清晰性 |
| models | `backend/app/models/` | 12 个数据模型 | 未使用字段、模型间冗余 |
| orchestration | `backend/app/orchestration/` | — | 与 execution 的职责边界 |
| 顶层 | `app_services.py`, `errors.py`, `ids.py`, `main.py`, `packaged_launcher.py` | — | 废弃逻辑 |

### 前端（React / TypeScript / Electron）

| 模块 | 路径 | 核心文件数 | 关注重点 |
|------|------|-----------|---------|
| components | `frontend/src/components/` | — | 职责单一性、未使用 props |
| features | `frontend/src/features/` | — | 功能模块间重复逻辑 |
| pages | `frontend/src/pages/` | — | 页面组件过重、拆分需求 |
| stores | `frontend/src/stores/` | 6 个 Zustand store | 状态重复、未使用 slice |
| services | `frontend/src/services/` | 11 个文件（含测试） | API 调用重复封装、WebSocket 集中度 |
| hooks | `frontend/src/hooks/` | 13 个文件（含测试） | 功能重叠 hook、未使用 hook |
| types | `frontend/src/types/` | 12 个类型文件 | `any` 滥用、重复定义、后端对齐 |
| utils | `frontend/src/utils/` | — | 未使用工具函数 |
| electron | `frontend/electron/` | — | 硬编码路径、安全漏洞 |

---

## 三、6 个审查任务

### 任务 1：死代码扫描（自动化 + 人工确认）

**目标**：找出所有未被引用的函数、类、变量、类型、导出。

**执行步骤**：
1. 后端：`vulture backend/app/ --min-confidence 80`
2. 前端：`npx ts-prune src/`
3. ESLint 未使用变量：`npx eslint src/ --rule 'no-unused-vars: error' --rule '@typescript-eslint/no-unused-vars: error'`
4. 人工确认：逐条确认自动工具输出，排除误报（动态调用等）

**产出**：`docs/superpowers/plans/audit-results/dead-code-inventory.md`

---

### 任务 2：重复代码检测

**目标**：找出语义重复的逻辑片段。

**执行步骤**：
1. 后端：`pylint backend/app/ --disable=all --enable=R0801`
2. 前端：`npx jscpd src/`
3. 人工重点审查区域：
   - `execution/` vs `orchestration/` 调度逻辑
   - `memory/continuation.py` vs `memory/continuation_builder.py`
   - `services/apiClient.ts` vs `services/desktopClient.ts`
   - `hooks/` 中 session 相关 hook 重叠
   - `stores/` error/loading 状态管理模式

**产出**：`docs/superpowers/plans/audit-results/duplicate-code-inventory.md`

---

### 任务 3：职责边界审查（依赖任务 1 & 2）

**目标**：识别职责不清、模块边界模糊的代码。

**执行步骤**：
1. 绘制模块依赖图（import 关系分析）
2. 逐模块审查：核心职责一句话？是否跨模块操作内部数据？是否包含应属别处的逻辑？
3. 重点审查：
   - `execution/`（15 文件）——编排逻辑是否越界到 `orchestration/`
   - `app_services.py`——是否承担过多"胶水"职责
   - `apiClient.ts` vs `desktopClient.ts`——是否应统一抽象层
   - `workspaceStore` vs `projectStore` 边界

**产出**：`docs/superpowers/plans/audit-results/responsibility-issues.md`

---

### 任务 4：注释合规性审查

**目标**：逐文件检查是否符合项目注释规范。

**执行步骤**：
1. 自动化脚本扫描：文件级注释、函数级注释、行内注释
2. 人工抽样复核（每模块 2-3 文件，检查注释质量）
3. 重点审查：
   - `execution/rapid_loop.py`——核心循环
   - `memory/context_assembly.py`——记忆组装
   - `llm/openai_adapter.py`——适配器逻辑
   - `services/sessionConversationWebSocket.ts`——WebSocket 逻辑

**产出**：`docs/superpowers/plans/audit-results/comment-compliance-report.md`

---

### 任务 5：类型安全与硬编码审查

**目标**：消除 `any`、补全类型注解、提取魔法值。

**执行步骤**：
1. 前端 `any` 扫描：`npx eslint src/ --rule '@typescript-eslint/no-explicit-any: error'`
2. 后端类型注解：`mypy backend/app/ --ignore-missing-imports`
3. 硬编码 grep：localhost、端口号、timeout 数值、http:// URL
4. 前后端类型对齐检查：`frontend/src/types/` vs `backend/app/models/`

**产出**：`docs/superpowers/plans/audit-results/type-safety-magic-values-report.md`

---

### 任务 6：错误处理审查

**目标**：找出异常吞没、错误不传播、降级缺失。

**执行步骤**：
1. 后端：`grep -rn "except:"` / `grep -rn "except Exception"` / `grep -rn "except.*:.*pass"`
2. 前端：`grep -rn "catch.*{}"` / `grep -rn "catch" -A 2`
3. 人工审查重点：
   - `execution/tool_call_executor.py`——工具执行失败处理链
   - `llm/retry.py`——重试耗尽后行为
   - `services/apiClient.ts`——HTTP 错误传播
   - `services/sessionConversationWebSocket.ts`——断连恢复

**产出**：`docs/superpowers/plans/audit-results/error-handling-issues.md`

---

## 四、汇总产出

6 个任务完成后合并为 **脏代码总报告**：

```
dirty-code-audit-report.md
├── 1. 执行摘要（脏代码总量、分布、严重度统计）
├── 2. 死代码清单（来自任务 1）
├── 3. 重复代码清单（来自任务 2）
├── 4. 职责边界问题（来自任务 3）
├── 5. 注释合规报告（来自任务 4）
├── 6. 类型安全与硬编码（来自任务 5）
├── 7. 错误处理缺陷（来自任务 6）
├── 8. 优先修复建议（按影响排序的 Top 10）
└── 9. 附录：各模块合规率评分
```

---

## 五、执行顺序与依赖关系

```
任务 1（死代码）──┐
任务 2（重复）──┤──→ 任务 3（职责边界，需依赖 1&2 结果）
任务 5（类型/硬编码）──┤
任务 6（错误处理）──┤──→ 汇总报告
任务 4（注释合规，独立可并行）──┘
```

- **任务 1、2、4、5、6** 可并行执行
- **任务 3** 在 1 和 2 完成后执行
- 每个任务产出独立文档，最终汇总

---

## 六、高风险区域

1. **`backend/app/execution/`**（15 文件）——职责交叉风险最高
2. **`frontend/src/services/`**（11 文件）——重复封装风险高
3. **`frontend/src/hooks/`**（13 文件）——功能重叠风险
4. **`backend/app/memory/`**（10 文件）——子模块边界模糊
5. **`execution/` vs `orchestration/`**——职责分界需验证

---

## 七、执行进度

| 任务 | 状态 | 产出文件 |
|------|------|---------|
| 保存计划 | ✅ 完成 | 本文件 |
| 任务 1：死代码扫描 | ⬜ 待执行 | dead-code-inventory.md |
| 任务 2：重复代码检测 | ⬜ 待执行 | duplicate-code-inventory.md |
| 任务 3：职责边界审查 | ⬜ 待执行 | responsibility-issues.md |
| 任务 4：注释合规审查 | ⬜ 待执行 | comment-compliance-report.md |
| 任务 5：类型安全与硬编码 | ⬜ 待执行 | type-safety-magic-values-report.md |
| 任务 6：错误处理审查 | ⬜ 待执行 | error-handling-issues.md |
| 汇总报告 | ⬜ 待执行 | dirty-code-audit-report.md |

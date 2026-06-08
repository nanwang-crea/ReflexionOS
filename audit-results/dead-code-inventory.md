# 任务 1：死代码清单

> 审查日期：2026-06-08
> 审查方法：vulture (后端 AST) + ts-prune (前端 export) + grep 交叉验证 + 人工确认
> 置信度分级：🔴 确认死代码（全项目零引用） / 🟡 可疑死代码（需人工确认）

---

## 一、后端确认死代码（🔴 3 项）

| # | 文件 | 名称 | 类型 | 置信度 | 说明 |
|---|------|------|------|--------|------|
| 1 | `app/errors.py` | `ExecutionError` | 类 | 100% | 定义后全项目无任何 import 或引用，与 `ExecutionCancelledError`/`ExecutionTimeoutError` 同文件但后者有实际使用 |
| 2 | `app/tools/patch_tool.py` | `PatchTool` | 类 | 100% | 完整的 tool 实现类，但未在工具注册表或任何其他模块中引用 |
| 3 | `app/execution/models.py` | `AgentMode` | 枚举 | 100% | 定义了 `RESEARCH`/`CODING`/`REVIEW` 三个枚举值，全项目无引用 |

---

## 二、后端可疑死代码（🟡 约 10 项）

### 2.1 AppSettings 子类（`app/config/settings.py`）

| 名称 | 说明 | 判断依据 |
|------|------|---------|
| `AppSettings` | 顶层应用配置 | 未在项目中被显式 import，可能通过 Pydantic `BaseSettings` 合并机制隐式使用 |
| `ExecutionSettings` | 执行配置 | 同上 |
| `MemorySettings` | 记忆配置 | 同上 |
| `PluginSettings` | 插件配置 | 同上 |
| `SkillSettings` | 技能配置 | 同上 |

> ⚠️ 这些 Settings 子类可能通过 Pydantic 的嵌套模型机制在 `Settings` 顶层类中作为字段类型使用，需人工确认 `Settings` 类是否引用了它们作为字段。

### 2.2 Git 数据模型（`app/models/git.py`）

| 名称 | 说明 | 判断依据 |
|------|------|---------|
| `GitBranchItem` | Git 分支数据模型 | 仅在 `git.py` 内部定义，未被 `git_service.py` 或其他模块引用 |
| `GitFileChange` | Git 文件变更模型 | 同上 |
| `GitLogCommit` | Git 日志提交模型 | 同上 |

> ⚠️ 可能是 API 响应模型，通过 FastAPI 的响应模型自动序列化机制使用，需确认路由层是否引用。

### 2.3 其他可疑项

| 名称 | 文件 | 说明 |
|------|------|------|
| `ProjectBase` | `app/models/project.py` | Pydantic 基础模型，未被任何模块 import |
| `BrowserTool` | `app/tools/browser_tool.py` | 工具类定义，未在工具注册表中出现 |
| `CodexPatch` | `app/tools/diff_parser.py` | 仅在 diff_parser 内部使用，可能是内部辅助类 |

---

## 三、前端确认死代码（🔴 4 项）

| # | 文件 | 名称 | 类型 | 置信度 | 说明 |
|---|------|------|------|--------|------|
| 1 | `components/animations/SlideIn.tsx` | `SlideIn` | 组件 | 100% | 无任何 import 或 JSX 引用，独立的动画组件文件 |
| 2 | `hooks/useToast.ts` | `showToast` | 函数导出 | 100% | 从 useToast 导出但全项目无调用，仅 `useToast` hook 本身被使用 |
| 3 | `hooks/useStreamingMessage.ts` | `useStreamingMessage` | Hook | 100% | 完整的 hook 实现，全项目无 import |
| 4 | `types/conversation.ts` | `ConversationTurnStatus` | 类型 | 100% | 仅在同文件的 `ConversationTurn` 接口字段定义处使用，无外部引用 |

---

## 四、前端可疑死代码（🟡 约 15 项）

### 4.1 WebSocket DTO 类型（仅测试引用）

以下类型在 `types/` 中定义，但仅在测试文件中被 import，生产代码未使用：

| 名称 | 文件 |
|------|------|
| `SessionConversationEventDto` | `types/websocket.ts` |
| `SessionModeChangedDto` | `types/websocket.ts` |
| `SessionTitleUpdatedDto` | `types/websocket.ts` |
| `SessionErrorDto` | `types/websocket.ts` |

> ⚠️ 可能是 WebSocket 消息处理函数的参数类型，通过类型推断隐式使用，需确认。

### 4.2 仅测试使用的辅助函数

| 名称 | 文件 | 说明 |
|------|------|------|
| `getNextFirstItemIndex` | `utils/pagination.ts` | 仅在分页测试中使用 |
| `getRetryCountdownSeconds` | `utils/retry.ts` | 仅在重试测试中使用 |

> ⚠️ 这些函数有独立导出且被测试覆盖，可能是为未来功能预留的 API，需确认是否计划在生产代码中使用。

### 4.3 其他可疑项

需进一步确认的导出项（来自 ts-prune 扫描，排除误报后剩余）：
- 部分 store 中的 selector 函数
- 部分 types 中的辅助类型别名

---

## 五、注释掉的代码块

### 后端

扫描 `backend/app/` 中以 `#` 开头且后跟代码关键字（`import`/`def`/`class`/`return`/`if`/`for`/`while`/`try`/`with`）的行，**未发现大量注释掉的代码块**。代码库在这方面较干净。

### 前端

扫描 `frontend/src/` 中以 `//` 开头且后跟代码关键字的行，**未发现注释掉的代码块**。

---

## 六、统计摘要

| 分类 | 数量 | 估计可删除行数 |
|------|------|---------------|
| 🔴 后端确认死代码 | 3 | ~150 行（含整个 patch_tool.py ~100行） |
| 🟡 后端可疑死代码 | ~10 | ~200 行（待确认） |
| 🔴 前端确认死代码 | 4 | ~120 行 |
| 🟡 前端可疑死代码 | ~15 | ~80 行（待确认） |
| 注释掉的代码块 | 0 | 0 行 |
| **合计** | **~32** | **~550 行** |

---

## 七、建议操作

1. **立即删除** 🔴 确认死代码（3 个后端 + 4 个前端项）
2. **人工确认** 🟡 可疑项后决定保留或删除
3. 重点确认 `AppSettings` 子类是否通过 Pydantic 嵌套使用
4. 重点确认 `BrowserTool` 是否为计划中的功能
5. 对仅测试使用的辅助函数，决定是否提升到生产代码或删除

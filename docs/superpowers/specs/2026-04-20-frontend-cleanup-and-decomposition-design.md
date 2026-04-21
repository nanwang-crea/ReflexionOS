# ReflexionOS 前端清理与职责继续拆分设计

> 状态：已确认进入设计文档阶段。
> 本文档针对 session/history 主线改造完成后的第二轮精修，目标是删除明确废弃代码，并继续拆分前端仍然职责过重的模块。

**版本**: v1.0  
**日期**: 2026-04-20  
**语言**: 中文

---

## 一、目标

本轮不再改动 session/history 主边界，也不继续推进后端 round-first 持久化。

本轮只做三件事：

1. 删除已经明确无效或废弃的前端代码路径
2. 继续拆分前端职责过重的模块
3. 保持当前行为不变，尤其保留现有 round 组装逻辑

本轮的目标不是重构所有结构，而是对当前主线完成后的“残余过重模块”和“明显遗留代码”做一次小步精修。

---

## 二、已确认约束

本轮必须遵守以下约束：

1. 删除废弃无效的代码
2. 对页面职责过重的地方继续拆分
3. round 组装逻辑可以保留，不强求本轮改动

因此本轮明确不做：

1. 不改后端 `TranscriptRecord -> build_session_history(rounds)` 的内部持久化模型
2. 不重写 session/history 协议
3. 不改 demo mode 的整体策略
4. 不做大规模 UI 组件重写

---

## 三、当前问题归纳

### 3.1 明确遗留的废弃代码

当前已确认的遗留项包括：

1. `frontend/src/services/apiClient.ts` 中的 `agentApi.getSessionHistory`
2. `frontend/src/features/workspace/messageFlow.ts` 中的 `deriveSessionTitle`
3. `frontend/src/features/workspace/messageFlow.ts` 中的 `trimRecentRounds`

这些路径来自旧本地 session/history 阶段，已经不再是当前运行链路的一部分。

### 3.2 `useCurrentSessionViewModel.ts` 仍然过重

它当前同时承担：

- 读取多个 store
- 拉 project sessions
- 拉 session history
- 推导 provider/model 选择
- 自动回写 session preference
- 组装 render items
- 组装页面 props

这使它既像数据加载层，又像 view model，又像 action orchestration 层。

### 3.3 `WorkspaceSidebar.tsx` 仍然过重

它当前同时承担：

- project CRUD
- session CRUD
- 项目与 session 的过滤/排序
- 当前 project / current session 同步
- demo mode 分支
- sidebar UI 组合

虽然 ownership 已经迁到 session feature layer，但组件职责仍然明显过载。

### 3.4 `useExecutionOverlay.ts` 仍然过重

这轮不改 round 组装逻辑，但 `useExecutionOverlay.ts` 仍然在同时承担：

- overlay item 生命周期
- streaming 文本拼装
- receipt 生命周期
- 多事件类型下的 transient 状态切换

它已经比旧版本清楚，但仍然是前端最重的 hook 之一。

---

## 四、设计原则

### 4.1 先删无效代码，再拆职责

本轮优先删除已明确不再需要的遗留路径，避免继续围绕兼容层拆分新结构。

### 4.2 拆分以“职责单一”为标准，不以“文件数量增加”为目标

每次拆分都要求：

- 新单元有明确单一职责
- 老文件因拆分而更容易理解
- 不能只是把代码机械地挪出去

### 4.3 保持当前行为稳定

本轮是精修，不是重构主线。所有拆分都应在不改变当前产品语义的前提下进行。

### 4.4 保留 round 组装逻辑

本轮允许继续保留当前 `flattenRoundsToItems / mergeRenderItems` 这一层，避免范围失控。

---

## 五、实施范围

### 5.1 删除废弃代码

本轮删除：

1. `agentApi.getSessionHistory`
2. `deriveSessionTitle`
3. `trimRecentRounds`

删除前需确认无生产代码引用；若仅剩测试引用，则连同测试一并收口。

### 5.2 拆 `useCurrentSessionViewModel.ts`

目标拆成三层：

1. `useSessionData`
职责：
- 当前 project/session 数据读取
- project sessions / session history 加载
- stale `currentSessionId` 处理

2. `useSessionSelection`
职责：
- provider/model selection 推导
- provider/model 变更
- session preference 回写

3. `useSessionRenderItems`
职责：
- persisted rounds + active round + overlay items -> render items
- 自动滚动

`useCurrentSessionViewModel` 自身变为组合层，只负责把以上三部分拼成页面需要的 props。

### 5.3 拆 `WorkspaceSidebar.tsx`

目标拆成以下层次：

1. `useSidebarProjectActions`
职责：
- 创建项目
- 删除项目
- 选择目录

2. `useSidebarSessionActions`
职责：
- 创建 session
- 重命名 session
- 删除 session

3. `useSidebarFilteredProjects`
职责：
- 搜索过滤
- project/session 排序
- 输出 sidebar 需要的列表结构

`WorkspaceSidebar.tsx` 保留 UI 组合和事件绑定，不再自己承担完整 orchestration。

### 5.4 适度收 `useExecutionOverlay.ts`

本轮不改核心 round 组装逻辑，只做轻量收口：

1. 把明显独立的 overlay item helper 再抽一层
2. 视情况把 receipt 生命周期处理拆成小型 helper
3. 目标是减少单文件认知负担，而不是改变执行语义

---

## 六、文件级预期变化

### 删除

- `agentApi.getSessionHistory` 所在代码片段
- `messageFlow.ts` 中废弃 helper

### 新增

- `frontend/src/hooks/useSessionData.ts`
- `frontend/src/hooks/useSessionSelection.ts`
- `frontend/src/hooks/useSessionRenderItems.ts`
- `frontend/src/components/layout/useSidebarProjectActions.ts`
- `frontend/src/components/layout/useSidebarSessionActions.ts`
- `frontend/src/components/layout/useSidebarFilteredProjects.ts`

说明：
如果现有目录结构更适合放在 `features/sessions/` 或 `features/projects/` 下，可以按实际模式放置，但职责边界必须保持一致。

### 修改

- `frontend/src/hooks/useCurrentSessionViewModel.ts`
- `frontend/src/components/layout/WorkspaceSidebar.tsx`
- `frontend/src/features/workspace/messageFlow.ts`
- `frontend/src/services/apiClient.ts`
- 相关测试文件

---

## 七、验收标准

本轮完成后应满足：

1. `agentApi.getSessionHistory` 已删除
2. `deriveSessionTitle` 已删除
3. `trimRecentRounds` 已删除
4. `useCurrentSessionViewModel.ts` 明显降重，职责拆分完成
5. `WorkspaceSidebar.tsx` 明显降重，project/session 操作与过滤逻辑拆出
6. `useExecutionOverlay.ts` 至少降低部分 helper 复杂度
7. 相关前端测试继续通过
8. 前端 build 继续通过

---

## 八、非目标

本轮明确不包含：

1. 后端 transcript 持久化模型改成 round-first
2. demo mode 架构统一
3. execution 协议重写
4. 全量组件拆分

---

## 九、结论

本轮是一次“小步结构精修”：

- 删除当前已经没有价值的遗留代码
- 继续拆掉最明显的前端重职责模块
- 保留当前已验证可用的 round 组装与 session/history 主链路

这样做可以在不打断现有稳定主线的前提下，继续提升代码结构清晰度和后续可维护性。

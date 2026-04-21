# ReflexionOS 前端残留路径收口与文档清理设计

> 状态：已确认进入设计文档阶段。
> 本文档针对上一轮 session/history 改造和前端 cleanup/decomposition 之后剩余的双路径、冗余接口和文档残留做最后一轮小步收口。

**版本**: v1.0  
**日期**: 2026-04-20  
**语言**: 中文

---

## 一、目标

本轮目标不是再做新一轮架构重构，而是把当前主线已经稳定后的残留问题继续收口：

1. 消除 session preference 的双路径持久化
2. 明确 project/session summary 与 session history 的加载边界
3. 去掉 draft round hook 中无差异重复 API
4. 收紧 session action 对外暴露面
5. 清理已经失效的中间 spec/plan 文档，但保留总体设计文档

---

## 二、已确认约束

本轮必须遵守以下约束：

1. session preference 只在发送前兜底写回
2. 软件启动时应预热所有项目及每个项目的 session summary 列表
3. 不预热 session history 内容
4. create/delete/rename session 后，只刷新对应 project 的 session summary 列表
5. round 组装逻辑继续保留，不作为本轮改动目标
6. 已无效的 spec/plan 可以清理，但总体设计文档不清理

---

## 三、当前问题归纳

### 3.1 session preference 持久化双路径

当前前端仍存在两条写回路径：

1. `useSessionSelection` 在 selection 推导/切换时自动持久化
2. `useSendMessage` 在真正发送前再次写回 session preferences

这会造成重复请求和 owner 模糊。

### 3.2 project/session summary 加载存在双策略

当前同时存在：

1. `projectLoader` 启动后预热所有项目下的 session summary
2. `useSessionData` 在当前项目变化时再次加载当前 project 的 session summary

这会形成“全量预热 + 当前项目再拉一次”的重复策略。

### 3.3 session history 加载语义不清

当前 `ensureSessionHistoryLoaded` 同时承担：

1. 首次确保有 history
2. execution 完成/失败后的刷新

虽然运行可用，但调用语义不够清晰。

### 3.4 draft round hook 暴露无差异重复 API

`useExecutionDraftRound` 当前对外暴露：

- `clearDraftRound`
- `completeDraftRound`
- `cancelDraftRound`
- `failDraftRound`

但实际语义已经统一为“清空 draft”。

### 3.5 session action 对外 API 偏宽

当前 `useSessionActions` 仍暴露类似 `updateSession` 这类偏泛的接口，而页面/运行链路实际需要的是更窄的业务动作。

### 3.6 中间设计文档已部分失效

在前几轮设计和实现过程中，已经存在一些阶段性 spec/plan，它们在当前代码状态下不再准确反映“下一步还要做什么”。

但同时，总体设计文档仍然有保留价值，不应一起删除。

---

## 四、设计原则

### 4.1 单一路径优先

当同一业务效果已经存在两条路径时，本轮优先收敛为一条主路径，而不是继续保留双轨。

### 4.2 预热 summary，不预热 history

符合产品体验的最小策略是：

- 启动时预热所有项目和各项目 session summary
- 仅在真正进入某个 session 时按需加载 history

### 4.3 action surface 应尽量窄

对外暴露的 hook/action API 应只保留真实业务需要的能力，不保留“理论上通用但当前无人该用”的泛接口。

### 4.4 文档清理遵循“阶段性文档可删，总体设计保留”

可清理：

- 已被后续实现和新文档替代的阶段性 spec/plan

保留：

- 仍然描述总体边界、总体架构、总体目标的设计文档

---

## 五、实施设计

### 5.1 session preference 单一路径

收敛方案：

- `useSessionSelection` 只负责本地 selection 状态推导与切换
- `useSessionSelection` 不再自动调用 `updateSessionPreferences`
- `useSendMessage` 成为唯一的 preference 兜底写回入口

行为：

- 用户改 provider/model，只更新本地 UI 选择
- 用户真正发送消息前，若当前 session 已存在，则把当前 selection 写回到 session preferences

### 5.2 project/session summary 加载边界

收敛方案：

- `projectLoader` 负责：
  - 加载 projects
  - 预热所有项目的 session summary 列表
- `useSessionData` 不再加载当前 project 的 session summary
- `useSessionData` 只负责当前 session history 的按需加载和 stale `currentSessionId` 处理

### 5.3 session history 加载语义拆分

保留两个不同语义的入口：

1. `ensureSessionHistoryLoaded(sessionId)`
用途：
- 当前 session 首次可见时，保证 history 已加载

2. `refreshSessionHistory(sessionId)`
用途：
- execution complete / failed 后主动刷新

即使内部实现早期仍可共享，也要在调用语义上拆清楚。

### 5.4 draft round API 收口

收敛方案：

- `useExecutionDraftRound` 对外只保留真正的清空接口
- 去掉无差异重复的：
  - `completeDraftRound`
  - `cancelDraftRound`
  - `failDraftRound`

调用处如需表达业务语义，应在调用侧表达“在 complete/fail/cancel 时 clear”。

### 5.5 sessionActions API 收口

收敛方案：

- 若 `updateSession` 无页面层真实使用，则不再作为公共 action 暴露
- 保留更窄的业务动作：
  - `createSession`
  - `renameSession`
  - `deleteSession`
  - `refreshProjectSessions`
- 偏好写回由 `useSendMessage` 走明确路径，不通过广义 `updateSession` 暴露给多个 UI 使用点

### 5.6 文档清理策略

本轮允许清理：

1. 已被当前实现状态替代、且后续不会再作为执行依据的阶段性 plan
2. 明显重复、内容已被新文档吸收的阶段性 spec

本轮明确保留：

1. session/history 总体边界设计文档
2. 前端 cleanup/decomposition 总体设计文档
3. 能帮助后续理解整体架构选择的高层设计文档

---

## 六、预期改动文件

### 主要修改

- `frontend/src/features/projects/projectLoader.ts`
- `frontend/src/hooks/useSessionData.ts`
- `frontend/src/hooks/useSessionSelection.ts`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/hooks/useExecutionDraftRound.ts`
- `frontend/src/hooks/useExecutionWebSocket.ts`
- `frontend/src/hooks/useExecutionRuntime.ts`
- `frontend/src/hooks/useSessionActions.ts`
- 相关测试文件

### 可能的轻量新增

- 一个命名更清晰的 history refresh helper，如已有 loader 文件内新增导出即可

### 文档清理

- `docs/superpowers/specs/` 下的阶段性文档
- `docs/superpowers/plans/` 下已完成且被本轮文档替代的细粒度计划

说明：
文档实际删除清单应基于当前目录逐个核对，不做盲删。

---

## 七、验收标准

本轮完成后应满足：

1. `useSessionSelection` 不再自动写回 session preference
2. `useSendMessage` 成为唯一 preference 兜底写回入口
3. `projectLoader` 继续负责预热所有项目的 session summary
4. `useSessionData` 不再重复加载当前 project 的 session summary
5. create/delete/rename 后只刷新对应 project 的 session summary
6. `ensureSessionHistoryLoaded` / `refreshSessionHistory` 语义分开
7. `useExecutionDraftRound` 不再暴露无差异重复 API
8. `useSessionActions` 不再对外暴露冗余泛 update
9. 失效的中间 spec/plan 已清理
10. 总体设计文档仍保留
11. 前端测试和 build 继续通过

---

## 八、非目标

本轮明确不包含：

1. 后端 transcript 持久化改为 round-first
2. demo mode 架构统一
3. `useExecutionOverlay` 大规模重构
4. `WorkspaceSidebar` 再次大拆分

---

## 九、结论

本轮是一次“最后一公里的残留路径收口”：

- 去掉还在并存的双路径
- 缩窄过宽的 action API
- 明确 summary 与 history 的加载边界
- 顺手清理已失效的中间文档

这样可以让当前 session/history 主线在不继续扩大改动面的前提下，达到更一致的结构状态。

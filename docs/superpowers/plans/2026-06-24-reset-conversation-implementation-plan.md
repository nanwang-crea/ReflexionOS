# ReflexionOS 重置对话功能实现计划

对应 spec：`docs/superpowers/specs/2026-06-23-reset-conversation-design.md`

语义回顾：**清空历史、保留会话**。先停后清；后端真实删库 + 重置 session 计数；前端成功后同步会话列表真值与未读基线，失败不动任何状态。

## 决策：冲突错误就用现有 400/ValidationError，不新增 409

现状 `value_error_to_app_error`（`backend/app/errors.py:86-91`）只把 `NotFoundValueError` 映射成 404，其余 `ValueError` 一律落 `ValidationError`（400）。项目没有 409/Conflict 基础设施。

本计划**不**引入新的 conflict error class 或全局映射：活跃 run 重校验失败时抛普通 `ValueError`，由现有通道映射为 **400 ValidationError**，前端按错误提示重试即可。理由：该冲突是极端竞态（取消后又被拉起）的兜底，不值得为它扩 error 体系（YAGNI）。下文凡提“冲突错误”均指此 400，不是 409。

## 已核实的现有原语（实现时直接复用）

- `ConversationService.acquire_session_write_lock(session_id)` — `conversation_service.py:110`
- `ConversationService.get_run(run_id)` — `:505`
- 级联删除原语（与 `truncate_after_message` 同源，`:366`）：`message_search_repo.delete_by_turn_ids` / `message_repo.delete_by_turn_ids` / `run_repo.delete_by_turn_ids` / `event_repo.delete_by_turn_ids` / `turn_repo.delete_by_session_after_index(session_id, 0)`
- `turn_repo.list_by_session(session_id)`
- session 计数重置范本：`truncate_after_message` 末尾（`:423-434`）已演示 `active_turn_id=None` + `last_event_seq` 重写
- `resolve_active_run_id_from_conversation(snapshot)` — `agent_service.py:78`
- `agent_service.cancel_run(run_id)`（写锁外异步取消并 await 真停）— `agent_service.py:610`
- `agent_service.edit_and_rerun`（先停后改的范式参照）— `agent_service.py:659`
- 前端：`session.store.upsertSession(projectId, session)`、`session.actions.ensureProjectSessionsLoaded`、`workspace.store.markSessionSeen`（单调）、`useConversationRuntime.resetConversationRuntime`（待改）

---

## 阶段 A：后端 Service 层 —— `ConversationService.reset_session`

### A1. 实现 `reset_session(session_id)`

**文件：** `backend/app/services/conversation_service.py`

在 `truncate_after_message` 之后新增方法。在 `acquire_session_write_lock(session_id)` 内：

1. 重读 session：`self.session_repo.get(session_id)`，为 None 抛 `NotFoundValueError("会话不存在")`。
2. **活跃 run 重校验**（spec 5.2「关于原子性」）：分步 guard，逐层短路，任一层缺失即视为「无活跃 run」继续往下删——**不要**把可能为 None 的值直接取属性（`turn_repo.get` 可能返回 None，见 `turn_repo.py:25`）：
   ```python
   active_run = None
   if session.active_turn_id is not None:
       turn = self.turn_repo.get(session.active_turn_id)
       if turn is not None and turn.active_run_id is not None:
           active_run = self.run_repo.get(turn.active_run_id)
   if active_run is not None and active_run.status in {RunStatus.RUNNING, RunStatus.WAITING_FOR_APPROVAL}:
       raise ValueError("会话仍有运行中的任务，无法重置")
   ```
   关系链：`session.active_turn_id` → `turn.active_run_id` → `run`（`Turn.active_run_id` 见 `models/conversation.py:72`；**不**新造「按 turn 找 active run」的 repo helper）。`turn` 为 None、`turn.active_run_id` 为 None、`run` 为 None 或已终态 → 视为无活跃 run，继续删。绝不在活跃 run 时往下删。
3. 取 `turn_ids = [t.id for t in self.turn_repo.list_by_session(session_id)]`。
4. 若 `turn_ids` 非空，按顺序级联删除（复制 `truncate_after_message` 的删除块）：
   - `message_search_repo.delete_by_turn_ids(turn_ids)`
   - `message_repo.delete_by_turn_ids(turn_ids)`
   - `run_repo.delete_by_turn_ids(turn_ids)`
   - `event_repo.delete_by_turn_ids(turn_ids)`
   - `turn_repo.delete_by_session_after_index(session_id, 0)`
5. 重置计数：重读 session，`session_repo.update(session.model_copy(update={"active_turn_id": None, "last_event_seq": 0}))`。
6. 返回重置后的 `Session`（`self.session_repo.get(session_id)`）。

空会话（`turn_ids` 为空）：跳过步骤 4，仍执行 5/6，幂等返回。

**验证：** 见 A2。

### A2. Service 层单测

**文件：** `backend/tests/test_services/test_conversation_service_reset.py`（新建；现有 conversation_service 测试在 `backend/tests/test_services/test_conversation_service.py`，也可并入）

- `test_reset_clears_all_and_resets_counters`：建 2~3 个 turn，各带 run/message/event/search 文档 → `reset_session` → 断言该 session 下 turn/run/message/event/search 全为 0；`active_turn_id is None`、`last_event_seq == 0`。
- `test_reset_empty_session_is_idempotent`：空会话直接 `reset_session` → 不抛错，返回 session，计数为 0。
- `test_reset_does_not_touch_other_sessions`：建两个 session 各有数据，reset 其一 → 另一 session 数据原样。
- `test_reset_conflict_when_active_run`：构造 `active_turn_id` → turn.`active_run_id` 指向 `RUNNING` run → `reset_session` 抛普通 `ValueError`（即上文决策的 400 路径）且**未删除任何数据**（reset 前后计数一致）。

运行：`cd backend && python -m pytest tests/test_services/test_conversation_service_reset.py -q`

---

## 阶段 B：后端 Agent 层 —— `agent_service.reset_session`

### B1. 实现 `reset_session(session_id)`

**文件：** `backend/app/services/agent_service.py`，参照 `edit_and_rerun`（`:659`）的先停范式。

1. `session = self.session_repo.get(session_id)`；为 None 抛 `NotFoundValueError("会话不存在")`。
2. **写锁外**先停：`conversation = self.conversation_service.get_snapshot(session_id)`；`active_run_id = resolve_active_run_id_from_conversation(conversation)`；若有则
   ```python
   try:
       await self.cancel_run(active_run_id)
   except Exception:
       logger.warning("重置前取消活跃运行失败: run_id=%s", active_run_id)
   ```
   （与 `edit_and_rerun` 一致：取消失败不阻断，交给 Service 层写锁内重校验兜底。）
3. `result = self.conversation_service.reset_session(session_id)`。
4. 返回 `result`（重置后的 Session）。

> cancel_run 必须在写锁外（spec 5.2）：它内部自取写锁并 await 任务结束，整段持锁会死锁。

### B2. Agent 层单测

**文件：** `backend/tests/test_services/test_agent_service_reset.py`（新建）

- `test_reset_cancels_active_run_then_clears`：mock `cancel_run` 与 `conversation_service.reset_session`，构造有 active run 的快照 → 断言**先**调 `cancel_run` **后**调 `reset_session`（用 mock 调用顺序断言，如 `Mock` 的 `mock_calls` 序列或共享 `call_order` 列表）。
- `test_reset_no_active_run_skips_cancel`：无 active run → 不调 `cancel_run`，直接调 `reset_session`。
- `test_reset_session_not_found`：session 不存在 → 抛 `NotFoundValueError`，不调 `cancel_run`。

运行：`cd backend && python -m pytest tests/test_services/test_agent_service_reset.py -q`

---

## 阶段 C：后端 API 路由

### C1. 新增 `POST /api/sessions/{session_id}/reset`

**文件：** `backend/app/api/routes/sessions.py`

仿 `delete_session`（`:54`）风格，但调用 agent 层（需先停 run）：

```python
@router.post("/sessions/{session_id}/reset", response_model=Session)
async def reset_session(session_id: str):
    try:
        return await agent_service.reset_session(session_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc
```

`agent_service` 已在文件顶部导入（`:3`）。`Session` 已导入（`:6`）。

### C2. API 测试

**文件：** `backend/tests/test_api/test_sessions_reset.py`（新建；现有 sessions 路由测试在 `backend/tests/test_api/test_sessions_api.py`，也可并入）

- `test_reset_returns_session_200`：建带数据的 session → `POST /api/sessions/{id}/reset` → 200，body 为重置后的 Session（`last_event_seq == 0`）；再 `GET .../conversation` 得空快照。
- `test_reset_unknown_session_errors`：未知 id → 走 `value_error_to_app_error`（404）。
- `test_reset_active_run_returns_400`：构造 `active_turn_id` → turn.`active_run_id` 指向 `RUNNING` run，**mock `agent_service.cancel_run` 为 no-op**（让它什么都不做地返回，使 Service 层重校验仍看到 RUNNING run），→ `POST /api/sessions/{id}/reset` → **400 validation_error**（验证「冲突=现有 400」决策在 API 层确实成立，而非只停在文档）。
  - 注意：不能靠「该 run 无对应 running task」来命中冲突——真实 `cancel_run` 即便没有 running task，仍会走 `handle_event("run:cancelled")` 把 run 落成 `CANCELLED`（`agent_service.py:650-677`），重校验就不再命中。必须 mock 掉 `cancel_run`。

运行：`cd backend && python -m pytest tests/test_api/test_sessions_reset.py -q`

---

## 阶段 D：前端 API client + store 动作

### D1. API client `resetSession`

**文件：** `frontend/src/features/sessions/api/session.api.ts`（与 `updateSession`/`deleteSession` 同处）

新增 `resetSession(sessionId)`：`POST /api/sessions/{sessionId}/reset`，返回 `{ data: SessionSummary }`（与现有 session 接口返回类型一致）。

### D2. `workspace.store.resetSessionSeen`

**文件：** `frontend/src/features/workspace/stores/workspace.store.ts`

- 在 `WorkspaceState` 接口加 `resetSessionSeen: (sessionId: string) => void`。
- 实现：从 `lastSeenEventSeqBySessionId` 删除该 key（删除即等价于基线 0，未读派生里 `?? 0`）。若 key 不存在则返回原 state（避免无谓写入）。
- 这是 `markSessionSeen` 单调性之外**唯一**允许 seen 回退的入口（spec 5.3）。`partialize` 已含 `lastSeenEventSeqBySessionId`，无需改持久化配置。

### D3. 前端 store 单测

**文件：** `frontend/src/features/workspace/stores/workspace.store.test.ts`（新建或并入）

- `resetSessionSeen` 把指定会话 seen 清除（后续 `hasUnreadActivity(1, seen)` 为 true）。
- 不影响其他会话的 seen。
- 不存在的 sessionId 调用是无害 no-op。

---

## 阶段 E：前端改造 `resetConversationRuntime`

### E1. 改 `resetConversationRuntime`

**文件：** `frontend/src/hooks/useConversationRuntime.ts`（当前 `:607-615`，纯前端三步）

改为 async，成功后才同步真值与显示（spec 5.3）：

1. `await resetSession(currentSessionId)` 取回 `session`。
2. 成功分支（顺序无强依赖）：
   - `clearConversation(currentSessionId)`
   - `useSessionStore.getState().upsertSession(session.projectId, session)`（同步列表真值）
   - `useWorkspaceStore.getState().resetSessionSeen(currentSessionId)`（回退未读基线）
   - `closeSessionConnection(currentSessionId)` + `setSessionCancelling(currentSessionId, false)`（原有行为）
3. 失败分支：捕获异常，**不**清任何状态，向上抛或经现有错误通道提示用户重试。

> spec 5.3 备选：也可用 `ensureProjectSessionsLoaded(projectId)` 全量补拉替代 `upsertSession`。本计划选 `upsertSession`（reset 已返回单个 Session，省一次往返）。若实现中拿不到可靠 `projectId`，回退到 `ensureProjectSessionsLoaded`。

### E2. 调用点二次确认

**文件：** `frontend/src/pages/AgentWorkspace.tsx`（`onReset` 接线处，`:119` 附近）/ 必要时 `WorkspaceHeader.tsx`

按钮点击先弹确认（"确定要清空当前会话的全部对话记录吗？此操作不可恢复。"），确认后才调 `resetConversationRuntime`。复用现有 `nativeDialogService.confirmAction`（`frontend/src/services/dialogService.ts:3`），不新造对话框组件。

### E3. 前端组件/hook 测试

**文件：** 对应现有前端测试目录

- `resetConversationRuntime` 成功路径：mock `resetSession` resolve → 断言调用了 `clearConversation` + `upsertSession` + `resetSessionSeen` + 关 WS。
- 失败路径：mock `resetSession` reject → 断言**未**调 `clearConversation` / `upsertSession` / `resetSessionSeen`，且抛错/提示。
- 二次确认：点击 reset 弹确认；取消则不调 `resetConversationRuntime`，确认才调。

---

## 阶段 F：端到端联调与回归

1. 启动后端 + 前端 dev server。
2. 手测金路径：会话里产生若干对话 → 点重置 → 确认 → 聊天区清空；切走切回仍空白；侧边栏该会话的标题保留、忙碌/未读状态清零。
3. 手测未读回退：重置后在该会话产生新事件（从别的会话视角看）→ 能正确显示未读（验证 1..旧高位 区间不被吞）。
4. 手测运行中重置：发起一个长任务运行中 → 点重置 → 先停后清，无报错、无孤儿 run。
5. 手测空会话重置：全新空会话点重置 → 幂等无害。
6. 跑后端测试套件：`cd backend && python -m pytest -q`。
7. 跑前端测试 + 类型检查（按项目脚本，如 `npm test` / `tsc --noEmit`）。

---

## 实现顺序与提交建议

后端自底向上、前端自底向上，可分两个提交：

1. **后端**：A → B → C，连同各自单测一起。
2. **前端**：D → E，连同单测；E2 二次确认随 E 一起。
3. **联调 F** 后整体收尾。

每阶段的测试在该阶段内就跑过再进下一阶段，避免攒到最后。

# 审批暂停/恢复场景回放测试 — 实现计划（Plan）

> 日期：2026-10-03
> 对应 Spec：[2026-10-03-approval-replay-testing-design.md](../specs/2026-10-03-approval-replay-testing-design.md)
> 原则：零业务代码改动；沿用上一期设施（replay_fixture / replay_harness）做增量扩展；不引入新依赖。

**环境**：系统 Python 3.12 可直接跑 backend pytest（2026-10-02 实测，见更新后的记忆 `broken-test-envs-this-machine`），每步验证本地即跑，CI 兜底。

---

## Step 1：夹具模型扩展 approval_decisions

**改动文件**：`backend/tests/support/replay_fixture.py`、`backend/tests/test_execution/test_replay_fixture.py`。

**做什么**：

1. `replay_fixture.py` 新增 `ApprovalDecision` 模型（字段：`tool_call_id: str`、`action: Literal["approve","reject"]`、`output: str|None`、`error: str|None`、`success: bool = True`），带中文字段注释。
2. `ReplayFixture` 增加 `approval_decisions: list[ApprovalDecision] = Field(default_factory=list)`。
3. 测试新增 3 条：
   - 带 `approval_decisions` 的夹具 save/load round-trip 全字段一致；
   - 旧格式 JSON（无 `approval_decisions` 字段）加载后默认为空列表（向后兼容）；
   - `action` 填非法值（如 `"maybe"`）时 ValidationError。

**验证**：`pytest tests/test_execution/test_replay_fixture.py -v` 全绿（含旧 4 条）。

---

## Step 2：自动审批决策器（回放底座扩展）

**改动文件**：`backend/tests/support/replay_harness.py`、`backend/tests/test_execution/test_replay_harness.py`。

**做什么**：

1. `build_loop` 增加可选参数 `approval_decisions: list[ApprovalDecision] | None = None`；返回值增加决策任务跟踪——签名调整为返回 `(loop, replay_llm, captured, decision_tasks)`（`run_scenario` 内部消化签名变化，对外仍是三元组 + 内部 gather）。
2. 捕获回调包装：命中 `approval:required` 时——
   - 决策队列空 → 立即 `AssertionError("决策脚本不足")`（通过 decision_tasks 传播，不在回调里静默 raise 丢给事件循环）；
   - 弹出下一条决策，校验 `tool_call_id` 与事件负载一致，不一致记为失败；
   - `asyncio.create_task(_inject_when_slot_ready(...))`：轮询 `loop.approval_flow._pending`（每 10ms、上限 2 秒），目标 `approval_id` 出现 → `set_approval_result`（approve 传 `{"output","error","success"}`，reject 传 `None`）；超时 → `AssertionError("审批槽位未注册")`。
   - **注意点**：事件负载里 `approval_id` 从 `approval:required` 的 payload 取（Mock 工具固定 `approval-1`），决策与槽位以 `approval_id` 关联。
3. `run_scenario` 签名增加 `approval_decisions` 透传；run 结束后 `await asyncio.gather(*decision_tasks)`（异常上抛）+ 校验决策队列耗尽。
4. 单测（3 条，用真实 `ApprovalFlow` + 手工槽位，不跑完整 loop）：
   - 槽位延迟注册时决策器轮询等待并成功注入（验证核心时序）；
   - 决策队列耗尽时再次触发 `approval:required` → 任务失败含"决策脚本不足"；
   - `tool_call_id` 不匹配 → 任务失败含两个 id。

**验证**：`pytest tests/test_execution/test_replay_harness.py -v` 全绿（含旧 7 条）。

---

## Step 3：两个审批场景夹具 + 端到端用例

**改动文件**：新建 `backend/tests/fixtures/replay/approval-approve-then-complete.json`、`backend/tests/fixtures/replay/approval-reject-then-recover.json`；改 `backend/tests/test_execution/test_replay.py`。

**做什么**：

1. `test_replay.py` 新增 Mock `ApprovalTool`（参照 `test_rapid_loop.py` 的同名 test double：`execute` 返回 `ToolResult(success=False, approval_required=True, approval=ToolApprovalRequest(approval_id="approval-1", tool_name="approval_tool", summary="需要审批", payload={...}))`）。
2. 两个夹具（各 2 条 stream 响应 + 1 条决策）：
   - approve：响应1 调用 `approval_tool`；决策 `{"tool_call_id":"call_appr_1","action":"approve","output":"审批通过后的工具输出","success":true}`；响应2 纯 content 总结。预期序列见 Spec §5.3。
   - reject：决策 `{"tool_call_id":"call_appr_1","action":"reject"}`；其余同上。预期序列见 Spec §5.3。
   - 夹具 description 写明推导依据（`_handle_approval` 行号级）作为人工核对记录。
3. `test_replay.py` 加 2 个用例（E-04/E-05）：
   - E-04 approve：除 `assert_replay` 外，断言捕获的 `tool:result` 负载 `success is True`、`output` 为决策脚本里的输出；
   - E-05 reject：断言 `tool:error` 负载 `error == "审批被拒绝"`；`run:resuming` 负载 `approval_rejected is True`。

**验证**：`pytest tests/test_execution/test_replay.py -v` 全绿（5 条：旧 3 + 新 2）。若实际序列与推导不一致，先读代码找原因，**只允许在确认推导遗漏（而非代码 bug）时修正基线**，并在夹具 description 补记。

---

## Step 4：收尾——回归 + 文档回填

**改动文件**：`docs/superpowers/plans/2026-10-02-session-replay-testing-test-plan.md`（追加附录）、`docs/devlog/devlog-2026-06-23_to_present.md`、`wikis/reflexion-project/`（llm-wiki 摄入）。

**做什么**：

1. 全量回归：`pytest tests/ --ignore=tests/test_browser`（预期 1153+新增条数，零回归）。
2. 测试计划附录：补 E-04/E-05 与决策器单测的用例表 + 执行记录（遵循既有格式）。
3. devlog 追加本次记录（走 project-devlog 流程）。
4. llm-wiki 摄入：把审批回放与"事件先于槽位注册"的时序发现沉淀进知识库（更新 `会话录制回放测试.md`，可新建 `审批流时序.md` 页面，更新 index.md）。

**验证**：全量回归绿；三处文档更新完毕；wiki lint 无断链/孤立/漂移。

---

## 步骤依赖

```
Step 1（夹具模型）→ Step 2（决策器）→ Step 3（场景端到端）→ Step 4（收尾）
```

严格串行，每步验证通过再进下一步。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 决策回填命中空槽位被静默丢弃（事件先于槽位注册） | 轮询等槽位（10ms×200 次），超时明确报错；Step 2 单测覆盖该时序 |
| 决策任务异常被事件循环吞掉（回调里 create_task 的通病） | decision_tasks 集中跟踪 + run_scenario 末尾 gather，异常必上抛 |
| 批准/拒绝路径实际事件与推导有出入（如多一个 plan:updated） | Step 3 先跑通拿实际序列，读代码定性后按基线纪律处理，夹具 description 记录 |
| `_pending` 私有访问未来失效 | 留 TODO 注释；届时 ApprovalFlow 若提供公共查询优先换用 |

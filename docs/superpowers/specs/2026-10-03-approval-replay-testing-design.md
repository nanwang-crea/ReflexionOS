# 审批暂停/恢复场景回放测试 — 设计文档（Spec）

> 日期：2026-10-03
> 前作：[2026-10-02-session-replay-testing-design.md](2026-10-02-session-replay-testing-design.md)（回放测试设施）
> 关联待办：devlog 2026-10-02 条目"审批暂停/恢复场景回放未覆盖，列为后续扩展"；dsh 借鉴清单 🟢5 前置

---

## 一、背景

上一期建成的回放测试覆盖了 3 个场景（纯问答 / 只读工具调用 / 工具异常恢复），但**时序最复杂的路径——审批暂停/恢复——仍是空白**。这条路径是状态机回归风险最高的地方：

- 主循环在 `_handle_approval`（`rapid_loop.py:695`）里挂起协程，等外部 `ApprovalFlow.set_approval_result` 回填决策；
- 批准与拒绝走两条不同事件序列（批准：`tool:result` + `run:resuming`；拒绝：`tool:error` + `run:resuming(approval_rejected)` + 注入换路提示词）；
- 审批流（`approval_flow.py`）恰是简历级核心功能，却没有端到端回归网。

调研确认注入点干净可用（无需改业务代码）：

- 触发侧：Mock 工具返回 `ToolResult(approval_required=True, approval=ToolApprovalRequest(...))`，executor 发 `approval:required` 并交出 WAITING 步骤（`tool_call_executor.py:257`）；
- 决策侧：`ApprovalFlow` 多槽位设计——`wait_for_approval` 在 `_pending[approval_id]` 注册 `(Event, result)` 槽位后阻塞（`approval_flow.py:87`），外部 `set_approval_result(result_dict|None, approval_id)` 唤醒；`result=None` 即拒绝；
- **时序约束**：`approval:required` 与 `run:waiting_for_approval` 两个事件都发射在槽位注册**之前**，因此"看到事件立刻回填"会命中空槽位被丢弃（`set_approval_result` 对无槽位只警告）——自动决策器必须**等槽位出现再回填**。

## 二、目标

1. 夹具格式扩展：新增可选字段 `approval_decisions`（审批决策脚本），向后兼容（缺省为空，旧夹具不受影响）。
2. 回放底座扩展：自动审批决策器——捕获到 `approval:required` 时取出下一条脚本决策，**等 `ApprovalFlow` 槽位注册后**调用 `set_approval_result` 回填。
3. 新增 2 个端到端回放场景：
   - `approval-approve-then-complete`：批准后继续，断言 `tool:result(success=true)` 与完整事件序列；
   - `approval-reject-then-recover`：拒绝后换路恢复，断言 `tool:error(error="审批被拒绝")` 与完整事件序列。
4. 全部新测试随既有回放套件在 CI 可跑（keyless、无新依赖）。

## 三、非目标

- ❌ 连续拒绝耗尽 `MAX_TURN_RETRIES` 转 `FINAL_SUMMARY` 的场景（多轮决策脚本，价值/成本比低，留后续）
- ❌ 并发多审批（delegate 并行子 agent）场景
- ❌ 真实前端审批 UI / WebSocket 链路
- ❌ 业务代码任何改动（含为"等槽位"给 ApprovalFlow 加钩子——测试侧轮询解决，不动生产代码）
- ❌ 录制脚本对审批场景的适配（审批需要人工在场，录制无意义；夹具手写构造即可）

## 四、用户故事 / 行为

**作为重构者**，我改动 `_handle_approval` 或 `ApprovalFlow` 后跑回放测试：批准路径若少发/错发 `tool:result`、`run:resuming`，或拒绝路径把 `tool:error` 发成了 `tool:result`，测试在第一个分叉点失败，不需要手动点一遍审批弹窗。

**决策脚本的确定性**：审批决策写在夹具里（批准带什么 output / 拒绝），回放 100% 确定性——这锁的是"主循环对审批结果的处理逻辑"，不是人的选择。

## 五、方案

### 5.1 夹具格式扩展（replay_fixture.py）

新增模型：

```python
class ApprovalDecision(BaseModel):
    """一条脚本的审批决策（按顺序消费，与 responses 同理）"""
    tool_call_id: str          # 目标工具调用（与 approval:required 负载关联校验）
    action: Literal["approve", "reject"]
    output: str | None = None  # 批准时回填的工具输出
    error: str | None = None   # 批准但执行失败时回填的错误
    success: bool = True       # 批准路径的 execution_success
```

`ReplayFixture` 增加 `approval_decisions: list[ApprovalDecision] = []`。旧夹具无此字段，`model_validate` 走默认值——向后兼容。

### 5.2 自动审批决策器（replay_harness.py）

`build_loop` 增加可选参数 `approval_decisions`；捕获回调包装一层：

1. 捕获到 `approval:required` 时：从决策队列弹出下一条，校验 `tool_call_id` 匹配（不匹配即失败——决策与场景错位）；
2. 启动后台任务：**轮询** `loop.approval_flow._pending`（测试设施访问私有槽位表，可接受——既有测试也有同类做法），每 10ms 一次、上限 2 秒，目标 `approval_id` 出现即调用 `set_approval_result`（批准传 `{"output","error","success"}`，拒绝传 `None`）；超时未出现 → 测试失败并注明"槽位未注册，审批路径可能已改"；
3. `run_scenario` 末尾 `asyncio.gather` 全部后台任务，确保决策任务中的异常不会静默丢失；
4. 收尾校验决策队列恰好消费完（与 `assert_fully_consumed` 对称）。

### 5.3 两个场景夹具与预期序列

`approval-approve-then-complete`（2 条 stream 响应 + 1 条 approve 决策）：

```
run:start → metrics:llm_call → tool:start → approval:required
→ run:waiting_for_approval → tool:result → run:resuming
→ llm:content → metrics:llm_call → run:complete
```

`approval-reject-then-recover`（2 条 stream 响应 + 1 条 reject 决策）：

```
run:start → metrics:llm_call → tool:start → approval:required
→ run:waiting_for_approval → tool:error → run:resuming
→ llm:content → metrics:llm_call → run:complete
```

（推导依据：`_handle_approval` 源码；批准分支 `rapid_loop.py:769` 发 `tool:result`、`:783` 发 `run:resuming`；拒绝分支 `:800` 发 `tool:error`、`:838` 发 `run:resuming`。基线纪律同上一期：先推导、首跑比对、核对要点写进夹具 description。）

审批触发工具：Mock `ApprovalTool`（参照 `test_rapid_loop.py` 既有同名 test double），固定 `approval_id="approval-1"`，保证夹具确定性。

### 5.4 测试布局

| 文件 | 内容 |
|---|---|
| `backend/tests/fixtures/replay/approval-approve-then-complete.json` | 新夹具 |
| `backend/tests/fixtures/replay/approval-reject-then-recover.json` | 新夹具 |
| `backend/tests/test_execution/test_replay.py` | 加 2 个场景用例（E-04/E-05） |
| `backend/tests/test_execution/test_replay_harness.py` | 加自动决策器单测（槽位等待/决策耗尽/tool_call_id 错位） |
| `backend/tests/test_execution/test_replay_fixture.py` | 加 approval_decisions 字段的 round-trip 与缺省兼容用例 |

## 六、边界与降级

- **向后兼容**：旧 3 个夹具无 `approval_decisions`，加载与回放行为不变（L7 全量回归确认）。
- **槽位等待超时**：2 秒上限是防御性的（正常路径 10ms 内槽位即注册）；超时失败消息明确指向"审批路径变更"，不产生假绿。
- **决策脚本耗尽**：审批事件多于决策条目时，捕获回调直接失败（注明"决策脚本不足"），不静默放行。
- **私有成员访问**：`_pending` 是测试设施对框架内部的合理窥探；若未来 ApprovalFlow 提供公共"有挂起审批"查询，优先换用（留 TODO 注释）。

## 七、自检

- 无 TBD：注入点、时序约束、决策器等待策略、预期序列均已具体到源码行号。
- 与上一期设计一致：基线纪律、归一化规则、消费量校验全部沿用；夹具格式只做增量扩展。
- 风险已列明并各有对策（§六），最大风险（事件先于槽位注册）在 §一 调研阶段已识别并给出轮询方案。

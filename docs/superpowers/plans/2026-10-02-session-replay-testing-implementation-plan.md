# 会话录制回放测试 + 执行事件地图 — 实现计划（Plan）

> 日期：2026-10-02
> 对应 Spec：[2026-10-02-session-replay-testing-design.md](../specs/2026-10-02-session-replay-testing-design.md)
> 原则：零业务代码改动（`app/` 不动）；每步独立可验证；全程不引入新第三方依赖。

**环境注意**：本机两个 `.venv` 已损坏（见记忆 `broken-test-envs-this-machine`），本地 pytest 可能跑不起来。每步验证命令照常给出；本地跑不通时以 CI 为准，不在本计划中修环境。

---

## Step 1：事件地图文档初版

**改动文件**：新建 `docs/event-map.md`；更新 `docs/INDEX.md` 登记。

**做什么**：

1. 用 grep 全量扫描 `app/execution/`、`app/agents/` 下的事件发射点（`self._emit("`、`emit("`、`await self._emit(` 三种形态）：
   ```bash
   grep -rn 'emit("' backend/app/execution/ backend/app/agents/
   ```
2. 逐个事件确认生产者函数、负载字段（从发射点代码读）、消费者（前端 WebSocket / 审批流 / 对话历史）、是否落盘（对照 `conversation_projection.py` 与 `conversation_service.py`，写入 `ConversationEvent` 的为持久，其余为瞬态）。
3. 落成表格：事件类型 | 生产者（文件:函数） | 消费者 | 负载字段 | 持久/瞬态。已粗扫到的 16 种：`run:start`、`run:complete`、`run:error`、`run:cancelled`、`run:resuming`、`run:waiting_for_approval`、`tool:start`、`tool:result`、`tool:error`、`approval:required`、`llm:content`、`llm:reasoning`、`summary:token`、`plan:updated`、`metrics:llm_call`、（`agents/` 内补充）。

**验证**：表格覆盖 grep 扫描结果中的全部事件类型；每条负载字段与代码发射点逐一核对无虚构。

---

## Step 2：测试支持包骨架 + 夹具模型

**改动文件**：新建 `backend/tests/support/__init__.py`、`backend/tests/support/replay_fixture.py`。

**做什么**：

1. `replay_fixture.py` 定义夹具的 pydantic 模型（对 Spec §5.2 的 JSON 结构）：
   - `RecordedToolCall`（id / name / arguments）
   - `RecordedResponse`（method: Literal["complete","stream"] / content / reasoning_content / tool_calls / finish_reason / usage 可选）
   - `ExpectedOutcome`（loop_status / event_sequence: list[str]）
   - `ReplayFixture`（scenario / description / recorded_at / model / responses / expected）
2. 提供 `load_fixture(path)` 与 `save_fixture(fixture, path)` 两个函数（`model_validate` / `model_dump` + JSON 读写）。
3. 新建 `backend/tests/fixtures/replay/` 目录（放 `.gitkeep`）。

> 说明：此文件是 Spec §5.1 模块表的细化补充（Spec 未单列），职责从 `replay_llm.py` 中拆出以保持单一职责。

**验证**：新建 `backend/tests/test_execution/test_replay_fixture.py`——构造一个夹具对象 → 保存到 `tmp_path` → 重新加载 → 断言字段完全一致（round-trip）。运行 `pytest backend/tests/test_execution/test_replay_fixture.py`。

---

## Step 3：ReplayLLM 假模型适配器

**改动文件**：新建 `backend/tests/support/replay_llm.py`、`backend/tests/test_execution/test_replay_llm.py`。

**做什么**：

1. 实现 `ReplayLLM(UniversalLLMInterface)`：
   - `__init__(fixture: ReplayFixture)`：内部维护响应队列（`collections.deque`）与消费游标。
   - `complete()`：弹出下一条；断言 `method == "complete"`，不匹配抛 `ReplayMismatchError`；转为 `LLMResponse` 返回。
   - `stream_complete()`：弹出下一条；断言 `method == "stream"`；将 `content` / `reasoning_content` 按定长 20 字符切块逐块 yield `StreamChunk(type="content"/"reasoning")`；末尾 yield 终止块（有 tool_calls → `type="tool_calls"`，否则 `type="done"`，带 `finish_reason`）。
   - `get_model_name()`：返回 `fixture.model`。
   - 队列空仍被调用 → 抛 `ReplayExhaustedError`（消息注明"实际 LLM 调用次数超过录制"）。
   - 提供 `assert_fully_consumed()`：队列非空则抛错（注明剩余条数），供测试收尾调用。
   - 自定义异常 `ReplayExhaustedError` / `ReplayMismatchError` 放同文件。
2. 单测覆盖：
   - 顺序播放（complete 路径与 stream 路径各一）；
   - method 不匹配抛 `ReplayMismatchError`；
   - 超量调用抛 `ReplayExhaustedError`；
   - `stream_collect`（基类方法）能正确聚合 ReplayLLM 的 chunk 流为 `LLMResponse`——这是与真实主循环调用路径的接口校验，必须测；
   - `assert_fully_consumed` 对"有剩余/无剩余"两种情况的断言行为。

**验证**：`pytest backend/tests/test_execution/test_replay_llm.py` 全绿。

---

## Step 4：回放底座 replay_harness

**改动文件**：新建 `backend/tests/support/replay_harness.py`、`backend/tests/test_execution/test_replay_harness.py`。

**做什么**：

1. `build_loop(fixture, tool_registry, **loop_kwargs) -> RapidExecutionLoop`：以 `ReplayLLM(fixture)` + 传入的工具注册表 + 事件捕获回调组装主循环（参照 `tests/test_execution/test_rapid_loop.py` 的组装方式，`max_steps` 等参数可覆盖）。
2. `run_scenario(fixture_path, tool_registry) -> tuple[LoopResult, list[tuple[str, dict]]]`：加载夹具 → 组 loop → `await loop.run(fixture 中记录的任务描述)` → 返回结果与捕获的 `(event_type, payload)` 列表；末尾自动调用 `assert_fully_consumed()`。
3. `normalize_event_types(events) -> list[str]`：连续同类型事件折叠为单条（`llm:content`×5 → `llm:content`×1）。
4. `assert_replay(result, events, fixture.expected)`：断言归一化序列 == `expected.event_sequence`、`LoopResult.status` 字符串 == `expected.loop_status`；失败时输出第一个分叉下标及前后各 3 条上下文。
5. 单测：`normalize_event_types` 的折叠规则；`assert_replay` 分叉定位输出格式。（loop 组装正确性由 Step 5 的端到端场景覆盖。）

**验证**：`pytest backend/tests/test_execution/test_replay_harness.py` 全绿。

---

## Step 5：三个回放场景夹具 + 端到端回放测试

**改动文件**：新建 3 个夹具 `backend/tests/fixtures/replay/{simple-completion,tool-call-then-complete,tool-error-recovery}.json`；新建 `backend/tests/test_execution/test_replay.py`。

**做什么**：

1. **手写构造 3 个夹具**（夹具只是 `LLMResponse` 的 JSON，无需真 key 即可构造；录制脚本 Step 6 是日后的再生成手段）：
   - `simple-completion`：单条 stream 响应（纯 content，finish_reason=stop）；期望序列 `run:start → llm:content → summary:token → run:complete`（实际序列以首次跑通的归一化结果为准，人工核对后回填 `expected`，防"照抄错误的实际值"——核对点：无 tool 事件、终态 complete）。
   - `tool-call-then-complete`：响应1=stream 携带一次 `grep` 工具调用；响应2=stream 纯 content 总结。工具：真 `GrepTool` 指向 `tmp_path` 准备的文件树。
   - `tool-error-recovery`：响应1=调用一个会抛异常的受控 Mock 工具（参照 test_rapid_loop.py 的 `ExplodingTool`）；响应2=收到错误后纯 content 完成。期望含 `tool:error`。
2. `test_replay.py`：参数化（`pytest.mark.parametrize` 遍历夹具目录），每个夹具走 `run_scenario` + `assert_replay`。

**验证**：`pytest backend/tests/test_execution/test_replay.py` 全绿；手动检查每个夹具的 `expected.event_sequence` 与事件地图文档一致（无文档外事件）。

---

## Step 6：RecordingLLM + 夹具重录脚本

**改动文件**：新建 `backend/tests/support/recording_llm.py`、`backend/tests/test_execution/test_recording_llm.py`；新建 `backend/scripts/record_replay_fixture.py`。

**做什么**：

1. `RecordingLLM(UniversalLLMInterface)`：`__init__(inner, sink_list)`；`complete` 委托 inner 后把响应 `model_dump` 追加到 `sink_list`（method="complete"）；`stream_complete` 逐块透传 inner 的 chunk 同时按 `stream_collect` 同逻辑聚合完整响应，结束后追加（method="stream"）；`get_model_name` 透传。
2. 单测：用 stub inner（返回固定 chunk 流）验证透传一致性 + 录制内容聚合正确 + method 标记正确。
3. `record_replay_fixture.py`：CLI 参数 `--scenario <name> --task "<任务描述>"`；从 `llm_provider_service` 读当前默认 provider 配置构造 `OpenAIAdapter`；无 key / 无默认 provider 时明确报错退出（退出码 2，提示先配置模型）；跑完把 sink 落盘为夹具 JSON，`expected` 由本次捕获事件自动归一化生成，**打印醒目提示要求人工 review 后再提交**。

**验证**：`pytest backend/tests/test_execution/test_recording_llm.py` 全绿；脚本无 key 时按预期报错（本地即可验证，不需 key）。真实录制由持 key 者另行手动执行，不阻塞本计划。

---

## Step 7：事件地图活性测试

**改动文件**：新建 `backend/tests/test_execution/test_event_map.py`。

**做什么**：

1. 用 `ast` 模块解析 `app/execution/`、`app/agents/` 全部 `.py` 文件，收集 `_emit("...")` / `emit("...")` 调用中的字符串字面量（跳过 f-string 与变量——这些不存在于当前代码，若未来出现则测试报错提示改为人工登记）。
2. 解析 `docs/event-map.md`：从表格首列提取已登记事件类型集合（约定表格格式为 `| \`event:type\` | ...`，用正则提取反引号内容）。
3. 双向比对：代码有而文档无 → 失败（列出漏登记事件）；文档有而代码无 → 失败（列出腐化条目）。
4. 自验证（一次性手动，不入库）：临时在某 execution 文件加一行 `_emit("test:fake", {})` → 确认测试失败 → 还原。

**验证**：`pytest backend/tests/test_execution/test_event_map.py` 全绿；自验证的负向用例确认有效。

---

## Step 8：收尾与文档回填

**改动文件**：`docs/INDEX.md`、`docs/dsh-reference-opportunities.md`、devlog（走 `project-devlog` 流程）。

**做什么**：

1. `docs/INDEX.md` 登记 `event-map.md` 与 spec/plan。
2. `docs/dsh-reference-opportunities.md`：把 🔴1（事件地图）、🔴2（录制回放测试）两条待办勾选为已完成，链接到本 plan。
3. 全量回归：`pytest backend/tests/`（本地跑不通则推 CI 验证，盯 CI 结果）。
4. devlog 追加本次工作记录。

**验证**：全量测试绿；两份文档更新完毕。

---

## 步骤依赖与顺序

```
Step 1（事件地图文档）──────────────┐
                                    ├──→ Step 7（活性测试）
Step 2（夹具模型）→ Step 3（ReplayLLM）→ Step 4（底座）→ Step 5（场景端到端）
Step 2 ──────────────→ Step 6（录制器+脚本）
全部 ────────────────────────────────→ Step 8（收尾）
```

建议执行顺序：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8。Step 1 与 2-5 互不阻塞，也可并行。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 主循环对同一响应路径产生的事件序列与预期有出入（如多了 `metrics:llm_call`） | Step 5 先跑通拿实际序列、人工核对合理性后回填 expected；归一化已折叠连续同类事件，降低脆弱性 |
| `run` 方法参数多（`agent_mode`、`task_content` 等）导致组装复杂 | 底座 `build_loop` 默认值对齐 `test_rapid_loop.py` 的既有用法，不为参数求全 |
| 活性测试把 prompt 文本里形如 `"a:b"` 的字符串误报为事件 | AST 只取 `emit(` 调用的第一个参数字面量，不做全文正则扫描 |
| 本机 venv 损坏跑不了测试 | 不引入新依赖，验证以 CI 为准；本地验证降级为 `python -m compileall` 语法检查 |

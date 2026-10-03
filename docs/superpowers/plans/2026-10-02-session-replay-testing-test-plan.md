# 会话录制回放测试 + 执行事件地图 — 测试计划

> 日期：2026-10-02
> 对应 Spec：[2026-10-02-session-replay-testing-design.md](../specs/2026-10-02-session-replay-testing-design.md)
> 对应 Plan：[2026-10-02-session-replay-testing-implementation-plan.md](2026-10-02-session-replay-testing-implementation-plan.md)
> 本文定位：回答"怎么验证这个功能本身做对了"——它测的是**测试基础设施**（回放设施 + 事件地图设施），不是被测的业务代码。

---

## 一、测试目标

1. 回放设施本身可信：ReplayLLM 播放准确、底座归一化规则正确、断言分叉定位可用——**假设施比没设施更危险，必须先自证**。
2. 三个回放场景端到端跑通，事件序列基线经人工核对确认合理（非照抄实际输出）。
3. 事件地图完整且活性测试双向有效（漏登记能拦住、腐化条目也能拦住）。
4. 录制链路（RecordingLLM + 脚本）逻辑正确，无 key 环境优雅降级。
5. 全部新测试不引入新第三方依赖，可在 CI 环境运行。

## 二、测试范围

**范围内**：

- `tests/support/` 下全部新模块（replay_fixture / replay_llm / replay_harness / recording_llm）
- `tests/test_execution/` 下 6 个新测试文件
- `docs/event-map.md` 的完整性与准确性
- `backend/scripts/record_replay_fixture.py` 的无 key 降级路径

**范围外**（及理由）：

- 真实 API 录制执行（需 key，由持 key 者手动验证，不纳入本次验收）
- 既有业务测试的覆盖率（本工作零业务代码改动，既有测试不应受影响——以全量回归确认）
- 前端 / WebSocket 层 / 服务层（非目标，见 Spec §三）

## 三、测试环境

| 环境 | 用途 | 现状与对策 |
|---|---|---|
| CI（GitHub Actions） | **权威验证环境**，全部测试以此为准 | 现有流水线，Python 3.12，无需改动 |
| 本机 | 语法级预检 | 两个 `.venv` 已损坏（记忆 `broken-test-envs-this-machine`），pytest 跑不起来；降级为 `python -m compileall` 语法检查 + import 冒烟，功能验证交给 CI |

**依赖约束**：新代码只用标准库（`json`/`ast`/`collections`/`pathlib`）+ 项目已有依赖（pydantic、pytest）。验收时检查 `requirements.txt` / `pyproject.toml` 零变更。

## 四、测试层次与用例设计

### L1 单元测试 — 夹具模型（test_replay_fixture.py）

| 用例 ID | 名称 | 步骤 | 预期 |
|---|---|---|---|
| F-01 | 夹具 round-trip | 构造 ReplayFixture → save 到 tmp_path → load | 全字段完全一致 |
| F-02 | 缺必填字段报错 | JSON 缺 `responses` 字段 → load | pydantic ValidationError |
| F-03 | method 枚举校验 | method 填 `"invalid"` → load | ValidationError |

### L2 单元测试 — ReplayLLM（test_replay_llm.py）

| 用例 ID | 名称 | 步骤 | 预期 |
|---|---|---|---|
| R-01 | complete 顺序播放 | 夹具含 2 条 method=complete，连续调 2 次 | 按序返回对应 LLMResponse |
| R-02 | stream 播放并切块 | 夹具含 1 条 method=stream、content 长 45 字符 | `stream_complete` 产出 3 个 content chunk（20+20+5）+ 1 个 done 终止块 |
| R-03 | stream 携带工具调用 | 响应含 tool_calls、finish_reason=tool_calls | 终止块 type="tool_calls" 且携带完整调用列表 |
| R-04 | **stream_collect 聚合**（关键） | 经基类 `stream_collect` 消费 ReplayLLM 的 chunk 流 | 聚合出的 LLMResponse 与夹具记录一致（content 拼接完整、tool_calls 完整）——校验与真实主循环的调用接口 |
| R-05 | method 不匹配 | 夹具记录 method=stream，调用 `complete()` | 抛 ReplayMismatchError |
| R-06 | 超量调用 | 夹具 1 条响应，调第 2 次 | 抛 ReplayExhaustedError，消息注明"超过录制" |
| R-07 | 消费未尽检测 | 夹具 2 条响应只消费 1 条，调 `assert_fully_consumed()` | 抛错并注明剩余 1 条 |
| R-08 | 恰好消费完 | 全消费后调 `assert_fully_consumed()` | 正常返回不抛错 |

### L3 单元测试 — 回放底座（test_replay_harness.py）

| 用例 ID | 名称 | 步骤 | 预期 |
|---|---|---|---|
| H-01 | 连续同类事件折叠 | 输入 `[a, a, a, b, b, a]` | 输出 `[a, b, a]`（注意首尾相同不合并） |
| H-02 | 无重复时原样 | 输入 `[a, b, c]` | 输出 `[a, b, c]` |
| H-03 | 分叉定位输出 | expected 与实际在第 3 条分叉 | 断言消息含分叉下标 2 及前后各 3 条上下文 |
| H-04 | 状态断言不匹配 | expected.loop_status=completed 实际 failed | 断言失败且消息含两个状态值 |

### L4 端到端回放（test_replay.py）— 核心验收

| 用例 ID | 场景 | 夹具内容 | 关键断言 |
|---|---|---|---|
| E-01 | simple-completion | 单条 stream 纯 content 响应 | ① 归一化序列 == expected；② 无 `tool:*` 事件；③ LoopStatus=completed；④ 夹具恰好消费完 |
| E-02 | tool-call-then-complete | 响应1 带一次 grep 调用，响应2 纯 content | ① 序列含 `tool:start → tool:result`；② 真 GrepTool 对 tmp_path 文件树实际执行；③ 终态 completed |
| E-03 | tool-error-recovery | 响应1 调用 ExplodingTool，响应2 纯 content | ① 序列含 `tool:error`；② 循环未崩溃、恢复后完成；③ 终态 completed |

**基线回填纪律**（防"照抄错误输出"）：每个场景首次跑通后，人工核对实际序列的**合理性**（对照事件地图：事件种类是否齐全、顺序是否符合状态机逻辑、有无多余事件），确认后才写入 `expected`。核对记录写在夹具的 `description` 字段。

### L5 事件地图活性（test_event_map.py）

| 用例 ID | 名称 | 步骤 | 预期 |
|---|---|---|---|
| M-01 | 当前代码与地图一致 | 跑活性测试 | 通过（Step 1 的文档已覆盖全部事件） |
| M-02 | 漏登记拦截（负向） | 手动在某 execution 文件临时加 `_emit("test:fake", {})` → 跑测试 → 还原 | 测试失败并列出 `test:fake` |
| M-03 | 腐化条目拦截（负向） | 手动在 event-map.md 加一行不存在的事件 → 跑测试 → 还原 | 测试失败并列出该条目 |

M-02 / M-03 为一次性手动验证，验证结果记录在本文件"执行记录"节，不写成自动化用例。

### L6 录制链路（test_recording_llm.py）

| 用例 ID | 名称 | 步骤 | 预期 |
|---|---|---|---|
| C-01 | complete 透传+录制 | stub inner 返回固定响应 | 返回值与 inner 一致；sink 记录 method="complete"、内容一致 |
| C-02 | stream 透传+聚合录制 | stub inner 返回 3 块 chunk 流 | 调用方收到的 chunk 序列与 inner 产出完全一致（透传无损）；sink 记录 method="stream"、聚合结果正确 |
| C-03 | 脚本无 key 降级 | 无默认 provider 配置下执行 `record_replay_fixture.py --scenario x --task y` | 退出码 2，报错信息明确提示先配置模型，不产生半成品夹具文件 |

### L7 全量回归

| 用例 ID | 名称 | 步骤 | 预期 |
|---|---|---|---|
| G-01 | 既有测试不回归 | CI 跑 `pytest backend/tests/` 全量 | 既有用例全部通过（本次零业务代码改动，任何既有失败都需追查是否环境/基线问题） |
| G-02 | 依赖零新增 | `git diff` 检查 requirements.txt / pyproject.toml | 无变更 |

## 五、通过标准（Exit Criteria）

全部满足才算本功能验收通过：

1. L1–L4、L6、L7 全部用例在 CI 通过；
2. L5 的 M-02、M-03 负向验证各执行一次并确认有效，结果记录于 §七；
3. 3 个回放夹具的 `expected` 均经人工核对（E-01/02/03 的核对记录填在夹具 description）；
4. `docs/event-map.md` 经抽查：任选 3 个事件，负载字段与代码发射点逐一相符。

## 六、执行方式

```bash
# 新增测试（本地 venv 可用时）
pytest backend/tests/test_execution/test_replay_fixture.py \
       backend/tests/test_execution/test_replay_llm.py \
       backend/tests/test_execution/test_replay_harness.py \
       backend/tests/test_execution/test_replay.py \
       backend/tests/test_execution/test_recording_llm.py \
       backend/tests/test_execution/test_event_map.py -v

# 本机降级预检（venv 损坏时）
python -m compileall backend/tests/support backend/tests/test_execution backend/scripts

# 全量回归（权威，CI 执行）
pytest backend/tests/
```

## 七、执行记录

> 验收时填写。

| 日期 | 环境 | 范围 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-10-02 | 本机系统 Python 3.12 + pytest 8.3.4（非 .venv） | L1–L6 全部新用例（34 条） | ✅ 34 passed / 1.48s | 本机 .venv 虽坏，系统 Python 依赖齐全可跑 |
| 2026-10-02 | 同上 | L7 全量回归 `pytest tests/ --ignore=tests/test_browser` | ✅ 1153 passed, 4 skipped / 176s | 浏览器测试因本机无 chromium 按既有约定排除 |
| 2026-10-02 | 同上 | G-02 依赖零新增 | ✅ | requirements.txt / pyproject.toml 零变更（仅新增测试与文档文件） |

- M-02 负向验证：2026-10-02 ✅ 在 `app/execution/` 临时放置含 `_emit("test:fake", {})` 的文件，`collect_code_events` 检出 `['test:fake']` 漏登记，验证后删除。
- M-03 负向验证：2026-10-02 ✅ 向 event-map.md 临时追加 `ghost:event` 表格行，腐化条目比对检出 `['ghost:event']`，验证后还原并复验双向一致。
- E-01/02/03 基线人工核对：2026-10-02 ✅ 基线非照抄实际输出——先从状态机源码推导预期序列（`_validate_stop_decision` 的 DONE/FINAL_SUMMARY 分支、`_call_llm` 中 llm:content 先于 metrics:llm_call、异常路径 executor 不发 tool:result 而由主循环发 tool:error），三个场景首跑即与推导完全一致；核对要点已写入各夹具 description 字段。
- 修复记录：① `test_assert_fully_consumed_with_remainder_raises` 原断言剩余 1 条实际剩 2 条（改为先消费 1 条）；② `record_replay_fixture.py` 括号笔误（`[work_dir)]` → `[work_dir])`）。均为实现期笔误，已修并复验。

## 八、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 本机跑不了 pytest，问题暴露晚 | 缺陷到 CI 才发现，往返成本高 | 小步提交、每步推 CI；compileall 预检语法；import 冒烟提前抓循环导入 |
| 事件序列含不可控波动（如 metrics 事件时有时无） | E-01/02/03  flaky | 首次跑通用 3 次重复运行确认序列稳定后再回填 expected；不稳定事件在归一化中剔除并记录理由 |
| 活性测试误伤（prompt 文本含 `"a:b"` 字面量） | M-01 误报 | AST 只取 `emit(` 调用首参数字面量；误报出现时以白名单机制处理并记录 |
| 夹具与真实模型行为脱节（模型升级） | 无影响——回放锁的是"循环对给定响应的处理"，非模型行为 | 需要时由持 key 者用录制脚本重录 + review |

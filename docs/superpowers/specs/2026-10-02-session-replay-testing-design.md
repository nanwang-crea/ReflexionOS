# 会话录制回放测试 + 执行事件地图 — 设计文档（Spec）

> 日期：2026-10-02
> 来源：`docs/dsh-reference-opportunities.md` 优先级 🔴1（事件地图）与 🔴2（录制回放测试）的落地
> 参照：DeepSeek Harness 的 `test:snapshot`（keyless 录制会话回放）与 `event-producer-consumer.md`（事件地图）

---

## 一、背景

`app/execution/rapid_loop.py` 是 1000+ 行的显式状态机主循环，协调工具执行、审批流、上下文压缩、重试与错误恢复。当前它的回归保障有两个缺口：

1. **事件契约不可见**：执行层向外发射约 16 种事件（`run:start`、`tool:start`、`tool:result`、`run:waiting_for_approval`、`llm:content`、`plan:updated`、`metrics:llm_call` 等），以字符串字面量散落在各文件中，没有权威清单。前端 WebSocket 依赖这些事件渲染，改字段、改事件名不会编译报错，属于隐性契约。
2. **没有会话级回归测试**：`tests/test_execution/test_rapid_loop.py` 已有 Mock 工具 + Mock LLM 的单测，但每个用例的 LLM 响应是手写脚本，只覆盖局部分支；"审批暂停 → 恢复 → 继续执行"这类跨模块时序缺少端到端回归网。重构状态机、改提示词、改工具编排时只能靠单测 + 手测。

DeepSeek Harness 用 `test:snapshot`（录制真实会话 → keyless 回放 → 断言输出）解决这个问题。本项目具备落地同款能力的全部条件：

- `RapidExecutionLoop.__init__` 的 `llm` 与 `event_callback` 均为注入参数（`rapid_loop.py:77-112`），天然可替换、可观测；
- `UniversalLLMInterface` 只有 3 个抽象方法（`complete` / `stream_complete` / `get_model_name`，`base.py:135-176`），`stream_collect` 是基类具体方法，假实现自动获得；
- `LLMResponse` / `LLMToolCall` / `StreamChunk` 均为 pydantic 模型，`model_dump` / `model_validate` 天然支持 JSON 序列化做夹具文件。

## 二、目标

1. **事件地图**：产出 `docs/event-map.md`，列出执行层全部事件类型、生产者、消费者、负载字段、是否落盘（持久/瞬态区分）。
2. **地图活性保障**：新增一个测试，扫描源码中 `_emit("...")` 字面量，与事件地图比对——代码新增/删除事件而文档未更新时测试失败，防止地图腐烂。
3. **ReplayLLM**：实现一个按夹具文件顺序播放预录 `LLMResponse` 的假模型适配器，实现 `UniversalLLMInterface`，供测试驱动完整 `RapidExecutionLoop`。
4. **回放测试套件**：基于 ReplayLLM + 受控工具注册表 + 事件捕获，跑完整任务回合，断言归一化后的事件序列与 LoopResult 终态。首批覆盖 3 个核心场景（见 §四）。
5. **录制工具**：实现 RecordingLLM（包装真实适配器、透传调用并落盘响应），供有 API key 的环境重新录制夹具。

## 三、非目标

- ❌ 生产环境录制/埋点（录制器仅供开发期录制夹具，不进生产链路）
- ❌ 需要真实 API key 的 CI e2e 测试（回放测试全程 keyless）
- ❌ 多会话并行、子 Agent（`sub_agent_runner.py`）、桌面/SDK 多形态的回放
- ❌ WebSocket 层、服务层（`services/`）事件的地图收录——本期只做执行层（`execution/`、`agents/`）
- ❌ 三类事件域重构（dsh 的 Session/Agent/Capability 划分）——属架构大改，另立窗口
- ❌ 前端任何改动

## 四、用户故事 / 行为

**作为重构者**，我改完 `rapid_loop.py` 的状态转移逻辑后，运行回放测试；若事件序列或 LoopResult 与基线不一致，测试失败并给出第一个分叉点，我不需要手动跑真实任务确认。

**作为新功能开发者**，我给执行层加了一个新事件类型，运行测试时被事件地图活性测试拦下，提示我先把新事件登记进 `docs/event-map.md`。

**作为夹具维护者**（持有 API key），模型行为漂移导致基线过时后，我运行录制脚本重录指定场景的夹具文件，提交更新。

**首批 3 个回放场景**：

1. `simple-completion`：模型直接回答（无工具调用）→ run 正常完成，断言 `run:start → llm:content* → summary:token* → run:complete` 序列与 `LoopStatus.COMPLETED`。
2. `tool-call-then-complete`：模型发起一次只读工具调用 → 工具执行 → 模型总结完成，断言含 `tool:start → tool:result` 的完整序列。
3. `tool-error-recovery`：工具抛异常 → `tool:error` → 模型收到错误后恢复并完成，断言错误恢复路径的事件序列。

（审批暂停/恢复场景依赖 `ApprovalFlow` 的外部决策注入，作为后续扩展场景，不在首批。）

## 五、方案

### 5.1 模块布局（全部落在测试基础设施与文档，零业务代码改动）

| 文件 | 职责 |
|---|---|
| `docs/event-map.md` | 事件地图文档：事件类型 / 生产者 / 消费者 / 负载字段 / 持久或瞬态 |
| `backend/tests/support/__init__.py` | 测试支持包 |
| `backend/tests/support/replay_llm.py` | ReplayLLM：按夹具顺序播放响应的假适配器 |
| `backend/tests/support/recording_llm.py` | RecordingLLM：包装真实适配器透传并落盘 |
| `backend/tests/support/replay_harness.py` | 回放测试底座：组装 loop、捕获事件、归一化比对 |
| `backend/tests/fixtures/replay/<scenario>.json` | 夹具文件（每场景一个） |
| `backend/tests/test_execution/test_replay.py` | 回放测试用例（3 场景） |
| `backend/tests/test_execution/test_event_map.py` | 事件地图活性测试 |
| `backend/scripts/record_replay_fixture.py` | 夹具重录脚本（需 API key，手动执行） |

放 `tests/support/` 而非 `app/llm/` 的理由：回放/录制是测试设施，不进生产依赖；`app/` 保持零改动，风险最低。若日后生产侧需要（如调试导出会话），再提升为正式适配器，届时另走 spec。

### 5.2 夹具文件格式

每个场景一个 JSON 文件：

```json
{
  "scenario": "tool-call-then-complete",
  "description": "一次只读工具调用后总结完成",
  "recorded_at": "2026-10-02",
  "model": "deepseek-chat",
  "responses": [
    {
      "method": "stream",
      "content": null,
      "reasoning_content": null,
      "tool_calls": [{"id": "call_1", "name": "grep", "arguments": {"pattern": "class"}}],
      "finish_reason": "tool_calls"
    },
    {
      "method": "stream",
      "content": "这个仓库的主循环在 rapid_loop.py …",
      "reasoning_content": null,
      "tool_calls": [],
      "finish_reason": "stop"
    }
  ],
  "expected": {
    "loop_status": "completed",
    "event_sequence": ["run:start", "llm:content", "tool:start", "tool:result", "..."]
  }
}
```

要点：

- `method` 字段标记该响应录制自 `complete` 还是 `stream`（`stream_collect`）调用；回放时 ReplayLLM 校验"被调用的方法"与记录一致——这能抓住"主循环改用了另一个 LLM 入口"这类行为漂移。
- `usage`（token 统计）录制但**不参与断言**（每次运行都不同，属易变字段）。
- `expected.event_sequence` 存归一化后的事件类型序列（同类连续事件折叠，见 5.4）。

### 5.3 ReplayLLM 设计

```python
class ReplayLLM(UniversalLLMInterface):
    """按夹具文件顺序播放预录响应的假模型，用于 keyless 回放测试。"""

    def __init__(self, fixture: ReplayFixture): ...
    # complete()      → 弹出下一条响应，断言 method == "complete"，直接返回 LLMResponse
    # stream_complete() → 弹出下一条响应，断言 method == "stream"，
    #                     将 content/reasoning 切成定长小块逐个 yield StreamChunk，
    #                     最后 yield 终止块（tool_calls 或 done）
    # get_model_name()  → 返回夹具中的 model 字段
```

- 响应弹尽仍被调用 → 抛 `ReplayExhaustedError`，测试失败并提示"实际调用次数超过录制"。
- 测试结束校验夹具恰好消费完（不多不少）——少了说明主循环提前退出，多了说明产生了多余 LLM 调用。
- 切小块（如每 20 字符一个 content chunk）是为了让 `llm:content` 事件真实触发多次，覆盖流式推送路径；块大小为夹具无关的固定常量，保证确定性。

### 5.4 回放底座与断言归一化

`replay_harness.py` 提供：

- `build_loop(fixture, tools)`：组装 `RapidExecutionLoop`（ReplayLLM + 受控 ToolRegistry + 事件捕获回调），工具集与场景匹配（只读场景用真 `grep`/`glob` 指向 `tmp_path` 准备的文件树；写操作场景用受控 Mock 工具，避免副作用）。
- `run_scenario(fixture_path)`：执行 `loop.run(task)`，返回 `(LoopResult, captured_events)`。
- `normalize(events)`：归一化——连续同类型事件折叠为单条（`llm:content` × 5 → 1 条），剥离易变负载字段（`run_id`、时间戳、token 数、耗时），只保留事件类型序列。
- 断言：归一化序列 == `expected.event_sequence`；`LoopResult.status` == `expected.loop_status`；夹具消费恰好用尽。失败时输出第一个分叉下标及两侧上下文，便于定位。

### 5.5 录制器设计

```python
class RecordingLLM(UniversalLLMInterface):
    """包装真实适配器：透传所有调用，每次响应追加到录制缓冲区，结束时落盘为夹具 JSON。"""

    def __init__(self, inner: UniversalLLMInterface, sink: FixtureSink): ...
    # complete / stream_complete 委托 inner 执行；
    # stream_complete 在逐块透传的同时聚合完整 LLMResponse（与 stream_collect 同逻辑），
    # 调用结束后连同 method 标记一并写入 sink。
```

`record_replay_fixture.py` 脚本：用真实 `OpenAIAdapter`（从现有 `llm_provider_service` 配置取 key）+ RecordingLLM 组装 loop，对指定场景跑一次真实任务，生成/覆盖夹具文件；`expected.event_sequence` 由本次捕获的事件自动归一化生成，人工 review 后提交。

### 5.6 事件地图与活性测试

`docs/event-map.md` 表格列：事件类型 | 生产者（文件:函数） | 消费者 | 负载字段 | 持久/瞬态。初版内容从 §一 扫描结果整理（16 种执行层事件 + `agents/` 内事件）。

`test_event_map.py` 活性测试：

1. 用 AST（或正则兜底）扫描 `app/execution/`、`app/agents/` 下所有 `_emit("..."）` 与 `emit("..."）` 字符串字面量；
2. 从 `docs/event-map.md` 解析已登记事件类型集合；
3. 双向比对：代码有而文档无 → 失败（漏登记）；文档有而代码无 → 失败（腐化条目）。

## 六、边界与降级

- **无 API key 环境**：回放测试与活性测试全程 keyless，正常跑；只有录制脚本需要 key，无 key 时明确报错退出，不影响其他测试。
- **本机测试环境损坏**（两个 `.venv` 指向他人路径，见记忆 `broken-test-envs-this-machine`）：新代码只依赖标准库 + 项目现有依赖（pydantic、pytest），不引入任何新第三方包，保证 CI 环境可跑。
- **审批场景**：`ApprovalFlow` 需要外部决策注入，首批不覆盖；后续扩展时通过注入"自动批准"决策回调实现，本设计的事件捕获与归一化机制无需改动即可兼容。
- **跨平台**：夹具与底座不触碰路径分隔符差异（工具参数内的路径用 `tmp_path` 动态生成，不硬编码进夹具）；Windows/macOS 均可运行。
- **夹具腐化**：模型升级导致真实行为变化时，回放测试不受影响（它锁的是"循环对给定响应的处理逻辑"，不是模型行为本身）；需要更新基线时走录制脚本重录 + review。

## 七、自检

- 无 TBD/占位：模块布局、夹具格式、断言策略、降级路径均已具体化。
- 无自相矛盾：首批场景（3 个）与"审批不覆盖"的边界一致；非目标与目标无重叠。
- 歧义点已消除：`method` 校验语义、"恰好消费完"的定义、归一化规则（连续折叠 + 剥易变字段）均已写明。

# 多 Worker 并行执行 · 实施计划

> **版本**: V4 — 修复评审意见（3 必须修改 + 7 建议改进 + 3 小问题）
> **设计文档**: `docs/superpowers/specs/2026-06-19-multi-worker-parallel-execution-design.md`
> **执行顺序**: 严格遵循设计文档 §12 的 5-Phase 顺序
> **日期**: 2026-06-20

## 评审修复记录

| # | 问题 | 级别 | 修复方式 | 影响 Task |
|---|------|------|----------|-----------|
| 1 | 文件路径冲突 | 🔴 必须 | 已统一为 `backend/app/execution/orchestrator.py`（V3 已修复） | T1.1 |
| 2 | LLMClient 创建方式 | 🔴 必须 | 改用 `LLMAdapterFactory.create(resolved_llm)` 模式 | T3.1, T4.1 |
| 3 | `_tool_semaphore` 传递路径 | 🔴 必须 | 通过 `RapidExecutionLoop` 的 `tool_executor_factory` 参数注入 | T1.3, T3.1 |
| 4 | `worker_max_tool_calls` 实现 | 🟡 建议 | `max_steps` 对应 `worker_max_iterations`；`worker_max_tool_calls` 在 `_run_worker` 层面计数限制 | T3.1 |
| 5 | `project_id` 传递链 | 🟡 建议 | `ContextSnapshot` 新增 `project_id` 字段，透传到 `SessionRecallTool` | T1.1, T3.1 |
| 6 | `_decompose()` 文件冲突重试策略 | 🟡 建议 | 重试 prompt 包含冲突文件列表；二次失败回退单循环 | T2.1 |
| 7 | `_decompose()` JSON schema 校验 | 🟡 建议 | 明确 4 条校验规则 | T2.1 |
| 8 | 测试 import 路径 | 🟡 建议 | 统一为 `from app.execution.orchestrator import ...` | T5.1 |
| 9 | Worker 事件 metadata 注入 | 🟡 建议 | `_run_worker` 中 wrap `event_callback` 注入 `worker_id` + `orchestrated` | T3.1 |
| 10 | ContextSnapshot 拍摄时机 | 🟡 建议 | 明确：`_decompose` 完成后、创建 worker task 之前统一拍摄 | T3.1 |
| 11 | 测试文件命名 | 🔵 小 | `test_context_snapshot.py` → `test_orchestrator_dataclasses.py` | T5.4 |
| 12 | 重试退避公式 | 🔵 小 | 明确为线性退避：`delay = worker_retry_delay_s * (attempt + 1)` | T3.2 |
| 13 | 超时机制 | 🔵 小 | 明确为 `asyncio.wait_for()` 包装整个 Worker 执行 | T3.1 |

## 概览

### Phase 总览（严格对齐 §12）

| Phase | 内容 | 新增/修改 |
|-------|------|-----------|
| **Phase 1** | 数据结构与配置（基础层） | 新增 `orchestrator.py`；修改 `context_manager.py`；修改 `rapid_loop.py` |
| **Phase 2** | 分解、编排判断与合成逻辑 | 扩展 `orchestrator.py`（decompose/synthesis/should_orchestrate） |
| **Phase 3** | OrchestratorLoop 并发执行核心 | 扩展 `orchestrator.py`（run/fan-out/retry/semaphore） |
| **Phase 4** | AgentService 集成入口 | 修改 `agent_service.py`、`config.py` |
| **Phase 5** | 集成测试 | 新增 4 个测试文件 |

### 核心设计约束（来自设计文档 + 评审修复）

1. **Worker 失败策略**: best-effort（收集可用结果继续合成）→ 单次失败抛异常 → LLM 临时错误重试（最多 3 次，线性退避 `delay * (attempt + 1)`）
2. **ContextSnapshot 不可变**: 所有 Worker 共享同一份只读上下文快照，不传可变对象。**拍摄时机：`_decompose` 完成后、创建 worker task 之前**（评审 #10）
3. **ToolRegistry 隔离**: 每个 Worker 创建独立 ToolRegistry，通过 `WorkerSpec.files` 硬边界限制可访问文件
4. **DB 连接池约束**: `DB_POOL_SIZE >= max_concurrent_workers + 2`
5. **decompose/synthesis 必须记录 token**: 通过 custom_id 前缀 (`orch-decompose-`/`orch-synthesis-`) 确保被 TokenTracker 记录
6. **LLM 创建统一使用 LLMAdapterFactory**: 禁止直接 `LLMClient(provider=..., model=...)`，必须通过 `LLMAdapterFactory.create(resolved_llm)` 模式（评审 #2）
7. **Semaphore 通过 tool_executor_factory 注入**: Worker 的 `_tool_semaphore` 通过 `RapidExecutionLoop(tool_executor_factory=...)` 参数传递（评审 #3）

### 测试矩阵

#### should_orchestrate 测试矩阵（设计文档 §5.1）

| # | 测试用例 | 输入 | 预期 | 类别 |
|---|---------|------|------|------|
| T1 | 普通段落不触发 | 普通文本 | False | 负例 |
| T2 | Markdown 标题不触发 | `# 标题格式` | False | 负例 |
| T3 | 单项列表不触发 | 仅 1 个编号项 | False | 负例 |
| T4 | 两项以上触发 | 多个编号项 | True | 正例 |
| T5 | 短内容不触发 | 每项 < 10 字符 | False | 负例 |
| T6 | 中文顿号触发 | `1、格式` | True | 正例 |
| T7 | 括号编号触发 | `1) 格式` | True | 正例 |
| T8 | disable 优先 | `disable_orchestration=True` | False | 配置覆盖 |
| T9 | force 优先 | `force_orchestration=True` | True | 配置覆盖 |
| T10 | 空字符串 | 空 | False | 边界 |
| T11 | 混合标题+编号 | `# 标题` + 编号列表 | True | 正例 |

#### Worker 失败策略测试矩阵（设计文档 §7）

| # | 测试场景 | 预期行为 |
|---|---------|---------|
| F1 | 单个 Worker 超时 | 超时标记 timeout，其余成功，synthesis 整合 |
| F2 | 单个 Worker 抛异常 | 异常标记 failed，synthesis 整合其余 |
| F3 | 部分成功部分失败 | status=partial，synthesis 整合并说明失败项 |
| F4 | 全部失败 | status=failed，返回错误结果 |
| F5 | 临时故障自动重试 | RateLimitError 重试后成功 |
| F6 | 重试耗尽仍失败 | 标记 failed |
| F7 | 合成 LLM 失败 | 回退到 worker 结果拼接 |
| F8 | 分解 LLM 失败 | 回退到单循环 |

---

## Phase 1: 数据结构与配置（基础层）

> **目标**: 定义所有核心数据结构，不包含执行逻辑
> **设计文档引用**: §3.1, §3.2, §3.3, §3.4, §3.6, §12 Phase 1
> **评审修复**: #1(文件路径), #5(project_id)

### T1.1 — 新增 orchestrator.py 数据结构

**文件**: `backend/app/execution/orchestrator.py` (新增)

> ✅ 文件路径已统一为 `backend/app/execution/orchestrator.py`，与设计文档 §6 一致（评审 #1）

创建以下 `@dataclass`（设计文档推荐 @dataclass 而非 BaseModel）：

| 类 | 字段 | 说明 |
|----|------|------|
| **WorkerSpec** | `worker_id`, `task`, `context_hint`, `allowed_tools`, `files`, `priority` | Worker 任务规格 |
| **WorkerResult** | `worker_id`, `status`, `result`, `events`, `steps`, `duration_s`, `tokens` | Worker 执行结果 |
| **OrchestrationResult** | `status`, `final_output`, `worker_results`, `synthesis_events`, `duration_s`, `total_tokens`, `decompose_tokens`, `synthesis_tokens` | 编排总结果 |
| **OrchestratorConfig** | `max_workers`, `worker_timeout_s`, `worker_retry_delay_s`, `worker_max_iterations`, `worker_max_tool_calls`, `worker_max_concurrent_tools`, `model`, `model_fallback` 等 | 编排器配置，含 `from_settings()` 工厂方法 |
| **ContextSnapshot** | `conversation_id`, **`project_id`** ⬅新增, `workspace_dir`, `tool_definitions`, `max_iterations`, `system_prompt`, `metadata` | 不可变上下文快照，含 `to_loop_context()` 方法 |

**关键设计点**:
- `WorkerSpec.files` 绑定权限边界（§3.6 评审新增）
- `OrchestratorConfig.from_settings()` 从 `app_settings` 映射环境变量（§3.4），包含以下映射：

| 设置字段 | 环境变量 | 默认值 |
|----------|----------|--------|
| `max_workers` | `ORCHESTRATOR_MAX_WORKERS` | 4 |
| `worker_timeout_s` | `ORCHESTRATOR_WORKER_TIMEOUT_S` | 300 |
| `worker_retry_delay_s` | `ORCHESTRATOR_WORKER_RETRY_DELAY_S` | 2.0 |
| `worker_max_iterations` | `ORCHESTRATOR_WORKER_MAX_ITERATIONS` | 15 |
| `worker_max_tool_calls` | `ORCHESTRATOR_WORKER_MAX_TOOL_CALLS` | 30 |
| `worker_max_concurrent_tools` | `ORCHESTRATOR_WORKER_MAX_CONCURRENT_TOOLS` | 5 |

- `ContextSnapshot.to_loop_context()` 设置 `LoopContext.orchestrated=True`, `LoopContext.worker_id`
- `ContextSnapshot.project_id` 透传到 `SessionRecallTool`（评审 #5）
- `OrchestrationResult` 必须包含 `decompose_tokens` 和 `synthesis_tokens` 字段

### T1.2 — 修改 LoopContext 增加编排字段

**文件**: `backend/app/execution/context_manager.py` (修改)

`LoopContext.__init__()` 新增两个参数：
- `orchestrated: bool = False` — 标记是否在编排模式下运行
- `worker_id: str | None = None` — Worker 标识，用于日志和事件元数据

**兼容性**: 两个字段均有默认值，不影响现有代码。

---

## Phase 2: 分解、编排判断与合成逻辑

> **目标**: 实现 decompose/synthesis 纯函数 + should_orchestrate + DB 连接池约束
> **设计文档引用**: §4.1, §4.4, §5.1, §5.4 评审新增
> **评审修复**: #6(decompose 重试策略), #7(JSON schema 校验)

### T2.1 — decompose 纯函数

**文件**: `backend/app/execution/orchestrator.py` (在 Phase 1 基础上扩展)

- **函数签名**: `async def _decompose(task: str, config: OrchestratorConfig) -> list[WorkerSpec]`
- **LLM 调用**: 使用 `LLMAdapterFactory.create(resolved_llm)` 模式（评审 #2），通过 custom_id `orch-decompose-{conversation_id}` 记录 token
- **JSON 解析**: 解析 LLM 返回的 JSON，提取 `workers` 数组

**JSON Schema 校验规则**（评审 #7）：

| # | 校验项 | 规则 | 失败处理 |
|---|--------|------|----------|
| V1 | `files` 非空 | 每个 worker 的 `files` 必须是非空列表 | 拒绝，触发重试 |
| V2 | `task` 非空 | 每个 worker 的 `task` 必须是非空字符串 | 拒绝，触发重试 |
| V3 | 数量限制 | `len(workers) <= config.max_workers` | 拒绝，触发重试 |
| V4 | 文件无交集 | 任意两个 worker 的 `files` 集合无交集 | 拒绝，触发重试（附冲突文件列表） |

**重试策略**（评审 #6）：

```
第 1 次尝试 → 校验失败 → 记录冲突原因
第 2 次尝试 → prompt 中追加冲突文件列表和具体违规项 → 校验失败
            → 回退到单循环模式（不抛异常，记录 WARNING 日志）
```

- **重试 prompt 模板**:
  ```
  上次分解失败，原因：{conflict_reason}
  冲突文件列表：{conflict_files}
  请重新分解，确保每个 worker 的文件集合互不重叠。
  ```
- **二次失败处理**: 回退到单循环（`RapidExecutionLoop`），不抛异常，`OrchestrationResult.status = "single_loop_fallback"`

### T2.2 — synthesis 纯函数

**文件**: `backend/app/execution/orchestrator.py`

- **函数签名**: `async def _synthesize(task: str, worker_results: list[WorkerResult], config: OrchestratorConfig) -> tuple[str, dict]`
- **LLM 调用**: 使用 `LLMAdapterFactory.create(resolved_llm)` 模式（评审 #2），通过 custom_id `orch-synthesis-{conversation_id}` 记录 token
- **失败策略**: 失败时回退到 worker 结果文本拼接（best-effort），抛异常不吞

### T2.3 — should_orchestrate 函数

**文件**: `backend/app/execution/orchestrator.py`

- 仅对明确编号列表触发（>=2 个编号项，每项 >=10 字符）
- `disable_orchestration` > `force_orchestration` > 正则检测
- 必须覆盖 T1-T11 全部 11 个测试用例（见测试矩阵）

### T2.4 — DB 连接池约束检查

**文件**: `backend/app/execution/orchestrator.py`

- `OrchestratorConfig.__post_init__()` 中检查 `DB_POOL_SIZE >= max_concurrent_workers + 2`
- 不满足时记录 WARNING 日志

---

## Phase 3: OrchestratorLoop 并发执行核心

> **目标**: 实现 `run()` 方法，包含 fan-out/gather/Semaphore/retry 全流程
> **设计文档引用**: §4.1, §4.2, §5.2, §5.3, §5.4, §7
> **评审修复**: #3(semaphore 传递), #4(worker_max_tool_calls), #9(事件 metadata), #10(ContextSnapshot 时机), #12(重试公式), #13(超时机制)

### T3.1 — OrchestratorLoop 核心

**文件**: `backend/app/execution/orchestrator.py` (扩展)

#### `run()` 方法总流程

```
1. DECOMPOSE  → _decompose(task, config)
2. SNAPSHOT   → ContextSnapshot 拍摄（评审 #10：decompose 后、worker 创建前）
3. FAN-OUT    → asyncio.gather(*[_run_worker(ws, snapshot) for ws in specs])
4. COLLECT    → 收集 WorkerResult 列表
5. SYNTHESIZE → _synthesize(task, results, config)
```

#### ContextSnapshot 拍摄时机（评审 #10）

```python
async def run(self, task: str) -> OrchestrationResult:
    # 1. DECOMPOSE
    worker_specs = await self._decompose(task, self.config)

    # 2. SNAPSHOT — 统一拍摄一次，所有 worker 共享只读快照
    snapshot = ContextSnapshot(
        conversation_id=self.context.session_id,
        project_id=self.context.project_id,  # 评审 #5
        workspace_dir=str(self.context.workspace_dir),
        tool_definitions=...,  # 从 tool_registry 获取
        max_iterations=self.config.worker_max_iterations,
        system_prompt=self.system_prompt,
        metadata={},
    )

    # 3. FAN-OUT — 所有 worker 共享同一 snapshot
    results = await asyncio.gather(
        *[self._run_worker(spec, snapshot) for spec in worker_specs]
    )
    # ...
```

#### Worker 事件 metadata 注入（评审 #9）

在 `_run_worker` 中 wrap `event_callback`，为每个事件注入 Worker 标识：

```python
async def _run_worker(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
    # Wrap event callback，注入 metadata
    original_callback = self.event_callback
    async def wrapped_emit(event):
        event.metadata = {
            **(event.metadata or {}),
            "worker_id": spec.worker_id,
            "orchestrated": True,
        }
        await original_callback(event)

    # 创建独立 ToolRegistry（WorkerSpec.files 硬边界）
    worker_registry = self._create_worker_registry(spec)

    # 创建 semaphore-aware ToolCallExecutor（评审 #3）
    def make_semphored_executor():
        executor = ToolCallExecutor(tool_registry=worker_registry, emit=wrapped_emit)
        original_execute = executor.execute
        async def semaphored_execute(tool_call, context, step_number):
            async with self._tool_semaphore:
                return await original_execute(tool_call, context, step_number)
        executor.execute = semaphored_execute
        return executor

    # 创建 Worker LLM（评审 #2：使用 LLMAdapterFactory）
    resolved_llm = app_settings.resolve_llm_config(self.config.model)
    worker_llm = LLMAdapterFactory.create(resolved_llm, on_retry=..., cancel_event=...)

    # 创建 Worker Loop
    loop = RapidExecutionLoop(
        llm=worker_llm,
        tool_registry=worker_registry,
        max_steps=self.config.worker_max_iterations,
        event_callback=wrapped_emit,
        tool_executor_factory=make_semphored_executor,  # 评审 #3
    )
```

#### worker_max_tool_calls 实现机制（评审 #4）

`RapidExecutionLoop` 的 `max_steps` 对应 `worker_max_iterations`（控制循环迭代次数）。`worker_max_tool_calls` 需要在 `_run_worker` 层面做额外计数限制：

```python
async def _run_worker(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
    tool_call_count = 0

    # 在 wrapped_emit 中计数 tool:result 事件
    async def wrapped_emit_with_count(event):
        nonlocal tool_call_count
        if event.event_type == "tool:result":
            tool_call_count += 1
            if tool_call_count > self.config.worker_max_tool_calls:
                raise ToolCallLimitExceeded(
                    f"Worker {spec.worker_id} 超过最大工具调用次数 {self.config.worker_max_tool_calls}"
                )
        # ... 注入 metadata（评审 #9）
        await original_callback(event)
```

#### 超时机制（评审 #13）

使用 `asyncio.wait_for()` 包装整个 Worker 执行：

```python
async def _run_worker(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
    try:
        result = await asyncio.wait_for(
            self._execute_worker(spec, snapshot),
            timeout=self.config.worker_timeout_s,
        )
    except asyncio.TimeoutError:
        return WorkerResult(
            worker_id=spec.worker_id,
            status="timeout",
            result=f"Worker {spec.worker_id} 执行超时 ({self.config.worker_timeout_s}s)",
            ...
        )
```

### T3.2 — Worker 失败策略与重试

**文件**: `backend/app/execution/orchestrator.py` (扩展)

#### 重试退避公式（评审 #12）

明确为**线性退避**（非指数退避），与设计文档 §5.4 代码示例一致：

```python
# 线性退避公式
delay = config.worker_retry_delay_s * (attempt + 1)
# attempt=0 → delay=2s, attempt=1 → delay=4s, attempt=2 → delay=6s
```

#### 完整重试逻辑

```python
async def _run_worker_with_retry(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await self._run_worker(spec, snapshot)
        except (RateLimitError, TimeoutError, APIStatusError) as e:
            if attempt < max_retries - 1:
                delay = self.config.worker_retry_delay_s * (attempt + 1)
                logger.warning(f"Worker {spec.worker_id} 第 {attempt+1} 次失败，{delay}s 后重试: {e}")
                await asyncio.sleep(delay)
            else:
                return WorkerResult(worker_id=spec.worker_id, status="failed", result=str(e), ...)
```

#### 失败策略总结（来自设计文档 §7，补充测试矩阵）

| 场景 | 行为 | 测试用例 |
|------|------|----------|
| 多 Worker 部分成功 | best-effort，合成整合可用结果 | F3 |
| 单任务失败 | 抛 `OrchestratorError` | F4 |
| LLM 临时错误 | 线性退避重试（`delay * (attempt + 1)`），最多 3 次 | F5, F6 |
| 合成 LLM 失败 | 回退到 worker 结果拼接 | F7 |
| 分解 LLM 失败 | 回退到单循环 | F8 |

---

## Phase 4: AgentService 集成入口

> **目标**: `should_orchestrate` 分支 + 配置加载 + 事件流集成 + LLM 创建修正
> **设计文档引用**: §5.1, §5.2, §5.3, §8
> **评审修复**: #2(LLM 创建方式)

### T4.1 — AgentService 修改

**文件**: `backend/app/services/agent_service.py` (修改)

`create_and_start_run()` 新增编排分支:

```python
# 评审 #2 修复：统一使用 LLMAdapterFactory.create() 模式
resolved_llm = app_settings.resolve_llm_config()
llm = LLMAdapterFactory.create(resolved_llm, on_retry=..., cancel_event=...)

if orchestration_enabled and should_orchestrate(task, config):
    # OrchestratorLoop 路径
    orchestrator = OrchestratorLoop(
        llm=llm,  # 主 LLM（decompose/synthesis 用）
        config=OrchestratorConfig.from_settings(),
        context=ctx,
        # ...
    )
    result = await orchestrator.run(task)
else:
    # 现有单循环路径（不变）
    loop = RapidExecutionLoop(llm=llm, tool_registry=registry, ...)
```

**Worker LLM 创建**（在 OrchestratorLoop 内部）:
```python
# 评审 #2：Worker 也使用 LLMAdapterFactory，不直接构造 LLMClient
worker_model = self.config.model  # 或 config.model_fallback
resolved_worker_llm = app_settings.resolve_llm_config(worker_model)
worker_llm = LLMAdapterFactory.create(resolved_worker_llm, on_retry=..., cancel_event=...)
```

### T4.2 — 环境变量配置

**文件**: `backend/app/core/config.py` (修改)

新增 `ORCHESTRATOR_*` 系列环境变量（共 14 个，见设计文档 §8）

| 环境变量 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `ORCHESTRATION_ENABLED` | bool | true | 是否启用编排 |
| `ORCHESTRATION_DISABLE` | str | "" | 禁用编排的关键词 |
| `ORCHESTRATION_FORCE` | str | "" | 强制编排的关键词 |
| `ORCHESTRATOR_MAX_WORKERS` | int | 4 | 最大 Worker 数 |
| `ORCHESTRATOR_WORKER_TIMEOUT_S` | int | 300 | Worker 超时秒数 |
| `ORCHESTRATOR_WORKER_RETRY_DELAY_S` | float | 2.0 | Worker 重试延迟（线性退避基数） |
| `ORCHESTRATOR_WORKER_MAX_ITERATIONS` | int | 15 | Worker 最大循环步数 |
| `ORCHESTRATOR_WORKER_MAX_TOOL_CALLS` | int | 30 | Worker 最大工具调用次数 |
| `ORCHESTRATOR_WORKER_MAX_CONCURRENT_TOOLS` | int | 5 | Worker 内并发工具数 |
| `ORCHESTRATOR_MODEL` | str | "" | 编排器模型（空=使用主模型） |
| `ORCHESTRATOR_MODEL_FALLBACK` | str | "" | 编排器备选模型 |
| `ORCHESTRATION_DECOMPOSE_MAX_RETRIES` | int | 2 | 分解最大重试次数 |
| `ORCHESTRATION_FAILURE_STRATEGY` | str | "best_effort" | 失败策略 |
| `ORCHESTRATION_TIMEOUT_STRATEGY` | str | "cancel" | 超时策略 |

---

## Phase 5: 集成测试

> **目标**: 覆盖两个测试矩阵 + 并发正确性验证 + 数据结构验证
> **设计文档引用**: §5.1 测试矩阵, §7 失败策略测试矩阵, §5.4 DB 连接池约束
> **评审修复**: #8(import 路径), #11(测试文件命名)

### T5.1 — should_orchestrate 单元测试

**文件**: `tests/unit/test_should_orchestrate.py` (新增)

> ✅ import 路径已统一（评审 #8）

```python
# 正确的 import 路径
from app.execution.orchestrator import should_orchestrate, OrchestratorConfig
```

覆盖 T1-T11 共 11 个测试用例（见上方测试矩阵）

### T5.2 — Worker 失败策略集成测试

**文件**: `tests/integration/test_orchestrator_failure.py` (新增)

覆盖 F1-F8 共 8 个失败场景（见上方测试矩阵）

### T5.3 — 并发正确性测试

**文件**: `tests/integration/test_orchestrator_concurrency.py` (新增)

- 多 Worker 并发执行无竞争条件
- DB 连接池约束验证（`max_concurrent_workers=3` 时 `pool_size >= 5`）
- Semaphore 正确限制并发数
- `worker_max_tool_calls` 计数器正确触发限制（评审 #4）

### T5.4 — 数据结构与配置单元测试 ⬅新增（评审 #11）

**文件**: `tests/unit/test_orchestrator_dataclasses.py` (新增)

> ✅ 命名已修正：不使用 `test_context_snapshot.py`，改用更准确的 `test_orchestrator_dataclasses.py`（评审 #11）

验证内容：
- `OrchestratorConfig.from_settings()` 正确映射环境变量
- `ContextSnapshot.to_loop_context()` 正确设置 `orchestrated`、`worker_id`、`project_id`
- `ContextSnapshot` 不可变性（frozen dataclass 或属性保护）
- `WorkerSpec.files` 非空校验
- `OrchestratorConfig.__post_init__()` DB 连接池约束检查

---

## 文件变更汇总（对齐设计文档 §6 + 评审修复）

| 文件 | 变更类型 | Phase | 评审关联 |
|------|----------|-------|----------|
| `backend/app/execution/orchestrator.py` | **新增** | Phase 1, 2, 3 | #1, #5, #6, #7 |
| `backend/app/execution/context_manager.py` | **修改** (LoopContext + orchestrated/worker_id) | Phase 1 | — |
| `backend/app/services/agent_service.py` | **修改** (编排分支 + LLMAdapterFactory) | Phase 4 | #2 |
| `backend/app/core/config.py` | **修改** (ORCHESTRATOR_* 配置) | Phase 4 | — |
| `tests/unit/test_should_orchestrate.py` | **新增** | Phase 5 | #8 |
| `tests/unit/test_orchestrator_dataclasses.py` | **新增** ⬅评审 #11 | Phase 5 | #11 |
| `tests/integration/test_orchestrator_failure.py` | **新增** | Phase 5 | — |
| `tests/integration/test_orchestrator_concurrency.py` | **新增** | Phase 5 | — |
| `backend/app/execution/rapid_loop.py` | **不变**（已有 `tool_executor_factory` 参数，无需修改） | — | #3 |
| `backend/app/llm/base.py` | 不变 | — | — |
| `backend/app/tools/registry.py` | 不变 | — | — |

---

## 延后项（V3 评审明确标记）

| 项目 | 原因 | 目标版本 |
|------|------|----------|
| 实时事件流（Worker 事件实时流入对话） | 需 ConversationRuntimeAdapter 多处改动 | V2 |
| Worker 事件排序（VectorClock） | 当前 Phase 1 无并发事件写入 | V2 |
| Worker 结果缓存（相同子任务跳过） | 优化项，V1 可工作 | V2 |
| 合成模型动态选择（按复杂度） | 需要实验数据 | V2 |
| 完整 OrchestratorMetrics Prometheus 导出 | 可后续叠加 | V2 |

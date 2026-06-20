> **日期**: 2026-06-19
> **状态**: 已评审 — V3 设计已更新（V3 评审日期: 2026-06-20）
> **范围**: 第一阶段 — OrchestratorLoop + 扇出 Worker 执行
> **方案**: 混合方案（编排器优先分解 + 动态派发）
> **V1 评审采纳**: ContextSnapshot、并发控制、文件冲突避免、Worker独立配置、明确列表触发策略
> **V2 评审采纳**: ToolRegistry 每 Worker 独立实例、WorkerApproval 自动批准策略、SessionRecallTool 绑定父 session_id、Worker 历史消息截断策略、Semaphore 粒度修正（Worker 级）、ContextSnapshot 字段对齐
> **V3 评审采纳**: ToolRegistry 表述统一、Worker 工具权限硬边界（白名单+文件访问边界）、WorkerSpec.files 绑定权限边界、DB 连接池容量约束、should_orchestrate() 测试矩阵、decompose/synthesis token 记录、Worker 失败策略测试矩阵、实现顺序建议（5 Phase）

---

## 1. 问题描述

ReflexionOS 的 `RapidExecutionLoop` 是**串行执行**的 —— 每次只能执行一个工具调用，单线程运行。当一个复杂任务包含多个独立子任务时（例如"重构认证模块、写测试、更新文档"），无法并行化执行。在子任务之间没有数据依赖的情况下，这会导致不必要的延迟。

**目标**: 将单个用户任务分解为多个并发的子代理（Worker），它们共享对话上下文、并行执行、最后合并结果 —— 类似 Claude Code 的 sub-agent 和 OpenAI Codex 的并行 Worker 模式。

## 2. 架构概览

```
用户消息 ──→ AgentService.create_and_start_run()
                 │
                 └─→ OrchestratorLoop.run(task, context)
                       │
                       ├─ 阶段 1: DECOMPOSE（LLM 调用）
                       │    └─ 输出: WorkerSpec[]（结构化 JSON）
                       │
                       ├─ 阶段 2: FAN-OUT（asyncio.gather）
                       │    ├─ WorkerLoop A ─→ RapidExecutionLoop(子任务A)
                       │    ├─ WorkerLoop B ─→ RapidExecutionLoop(子任务B)
                       │    └─ WorkerLoop C ─→ RapidExecutionLoop(子任务C)
                       │    （每个 worker 有独立的 LoopContext，
                       │     对话历史的只读快照）
                       │
                       ├─ 阶段 3: COLLECT
                       │    └─ 收集所有 worker 的 WorkerResult[]
                       │       （处理超时、部分失败）
                       │
                       └─ 阶段 4: SYNTHESIZE（LLM 调用）
                            └─ 合并所有 worker 结果为最终回复
```

### 关键设计决策

1. **OrchestratorLoop 在 RapidExecutionLoop 之上** —— 它是一个新层，不是对现有循环的修改。`RapidExecutionLoop` 保持不变（向后兼容）。
2. **每个 worker 是完整的 RapidExecutionLoop** —— worker 复用所有现有的工具执行、计划、总结和反思能力。
3. **Worker 获得对话历史的只读快照** —— 执行期间 worker 之间没有共享的可变状态。所有 worker 共享同一个 `ContextSnapshot`（见 §3.5），在 DECOMPOSE 阶段完成后、FAN-OUT 之前统一拍摄。
4. **嵌套深度受限** —— worker 可以选择性地派发子 worker（第二阶段），但最大深度可配置（默认: 2）。
5. **V1 触发策略：仅明确列表触发** —— `should_orchestrate()` 不使用启发式规则（避免假阳性），仅在用户输入包含明确编号列表或 `force_orchestration` 为 true 时触发编排（见 §5.1）。
6. **Worker 并发受 Semaphore 控制** —— 防止 LLM API Rate Limit（见 §5.3）。

---

## 3. 核心数据结构

### 3.1 WorkerSpec

描述分配给单个 worker 的子任务。

```python
@dataclass
class WorkerSpec:
    worker_id: str           # 唯一 ID，例如 "w_abc123"
    task: str                # 自然语言子任务描述
    files: list[str]         # 必填，该 Worker 将操作的文件路径列表（用于冲突检测）
    context_hint: str = ""   # 相关文件、模块或约束
    priority: int = 0        # 执行优先级（数值越高越重要）
    depends_on: list[str] = field(default_factory=list)  # 保留用于 DAG 调度
```

> **V2 评审修正**：`files` 从可选改为**必填**。缺少 `files` 时文件冲突检测完全失效，WorkerSpec 校验会拒绝空列表。
>
> **V3 评审修正**：`files` 同时作为**上下文输入范围**和**文件访问边界**。Worker 的 `file_read` / `file_write` / `file_edit` 工具会被路径校验层包装，只能操作 `files` 列表中的文件或其子路径（见 §3.6.3 权限硬边界）。

### 3.2 WorkerResult

单个 worker 的执行结果。

```python
@dataclass
class WorkerResult:
    worker_id: str
    status: Literal["success", "failed", "timeout"]
    result: str                          # LLM 最终输出文本
    loop_result: LoopResult | None       # 完整的 LoopResult（步骤、计划、总结）
    events: list[dict]                   # 该 worker 产生的对话事件
    duration_ms: int
    tokens_used: int
```

### 3.3 OrchestrationResult

整个编排的聚合结果。

```python
@dataclass
class OrchestrationResult:
    status: Literal["success", "partial", "failed"]
    final_output: str                    # 合成后的最终回复
    worker_results: list[WorkerResult]
    total_duration_ms: int
    total_tokens: int
    synthesis_events: list[dict]         # 合成阶段的事件

    # ── 阶段级 token 成本分解（V3 评审新增）──
    decompose_tokens: int = 0            # DECOMPOSE 阶段消耗的 token（分解 prompt + LLM 响应）
    synthesis_tokens: int = 0            # SYNTHESIZE 阶段消耗的 token（合成 prompt + LLM 响应）
    # total_tokens = decompose_tokens + sum(worker.tokens_used) + synthesis_tokens
    # 日志中也应输出各阶段 token 明细，便于成本归因分析
```

### 3.4 OrchestratorConfig

```python
@dataclass
class OrchestratorConfig:
    # ── 基础配置 ──
    max_workers: int = 5                 # 最大并发 worker 数
    worker_timeout_s: int = 300          # 单个 worker 超时时间（5 分钟）
    max_nesting_depth: int = 2           # worker→子 worker 的最大嵌套深度

    # ── 模型配置 ──
    worker_model: str | None = None      # worker 使用的模型（默认与主模型相同）
    synthesis_model: str | None = None   # 合成阶段使用的模型（默认与主模型相同）

    # ── Worker 行为配置（评审新增）──
    enable_reflection: bool = False      # worker 是否执行反思阶段
    enable_plan_persistence: bool = True # worker 计划是否持久化到对话
    worker_max_iterations: int = 5       # worker 独立最大迭代轮数（比主循环小，节省 75% token）
    worker_max_tool_calls: int = 10      # 每个 worker 最大工具调用数

    # ── Worker 工具权限（V3 评审新增，§3.6.3）──
    worker_allowed_tools: list[str] = field(default_factory=lambda: [
        "file_read", "file_write", "file_edit", "session_recall", "task_complete"
    ])  # Worker 工具白名单，白名单外的工具不注册到 Worker 的 ToolRegistry

    # ── 并发控制（评审新增，§5.3）──
    max_concurrent_workers: int = 3     # Worker 级并发数（Semaphore），限制同时运行的 Worker 数
    max_concurrent_tools: int = 5       # 工具执行最大并发数（Semaphore）

    # ── 容错配置（评审新增）──
    worker_retry_count: int = 1         # worker 失败后重试次数（仅对临时故障生效）
    worker_retry_delay_s: int = 5       # 重试间隔（秒），指数退避基础

    # ── 决策控制（评审新增，§5.1）──
    force_orchestration: bool = False   # 强制编排，忽略 should_orchestrate() 判断
    disable_orchestration: bool = False # 完全禁用编排（调试用）
```

### 3.5 ContextSnapshot

Worker 执行上下文的**只读快照**。在 DECOMPOSE 阶段完成后、FAN-OUT 之前统一拍摄一次，所有 worker 共享同一个快照实例。

> **V2 评审修正**：字段类型对齐真实 `LoopContext`（非伪类型），`to_loop_context()` 改用 `LoopContext.from_run_input()` 工厂方法。

```python
@dataclass
class ContextSnapshot:
    """Worker 执行上下文的只读快照"""

    # ── 包含的内容（对齐 LoopContext 真实字段）──
    seed_messages: list[dict[str, Any]]    # 对话历史消息（dict 格式，深度拷贝）
    system_sections: list[str]             # 系统提示词各段
    project_path: str | None               # 项目路径
    session_id: str                        # 对话 session ID（用于 SessionRecallTool）
    supplemental_context: str | None       # 补充上下文

    # ── 元数据 ──
    snapshot_timestamp: datetime           # 快照拍摄时间
    parent_run_id: str                     # 编排器运行的 ID
    depth: int = 0                         # 当前嵌套深度

    # ── 明确排除的内容 ──
    # - 其他 worker 的执行结果（Worker 之间完全隔离）
    # - 编排器内部状态（DECOMPOSE 的 LLM 原始响应等）
    # - 正在执行的工具状态
    # - 其他 worker 的中间产物
    # - LoopContext.steps / history / plan 等运行时状态

    def to_loop_context(self, worker_id: str, task: str) -> LoopContext:
        """
        为指定 Worker 创建独立的 LoopContext（V2 修正）。
        使用 LoopContext.from_run_input() 工厂方法，保证消息格式校验、
        token 计数、group_count 等内部状态正确初始化。
        seed_messages 会经 from_run_input 的过滤逻辑处理（跳过空消息、
        缺 tool_call_id 的 tool 消息等）。
        """
        return LoopContext.from_run_input(
            task=task,
            project_path=self.project_path,
            run_id=f"{self.parent_run_id}-worker-{worker_id}",
            session_id=self.session_id,           # 共享父 session，SessionRecallTool 可用
            agent_mode="build",
            seed_messages=copy.deepcopy(self.seed_messages),
            system_sections=list(self.system_sections),
            supplemental_context=self.supplemental_context,
        )
        # 注：from_run_input 末尾会自动追加 task 作为 user 消息，
        # 因此无需手动添加。worker_id / depth / orchestrated 标记
        # 通过 metadata 或 WorkerLoopConfig 注入。
```

**字段映射对照**（旧伪类型 → 真实类型）：

| 旧字段（伪类型） | 新字段（真实类型） | 来源 |
|-----------------|-------------------|------|
| `messages: list[Message]` | `seed_messages: list[dict]` | `LoopContext.messages` |
| `system_prompt: str` | `system_sections: list[str]` | `LoopContext.system_sections` |
| `available_tools: list[ToolSpec]` | （移除，由 ToolRegistry 管理） | Worker 独立注册 |
| `conversation_id: str` | `session_id: str` | `LoopContext.session_id` |

**快照时机**（见 §4.2 FAN-OUT 阶段详解）：
```
DECOMPOSE 完成 → ContextSnapshot 拍摄 → 所有 worker 共享同一快照 → FAN-OUT 启动
```

### 3.6 ToolRegistry 隔离与 SessionRecallTool 行为

> **V2 评审新增**：明确 Worker 间的工具实例隔离策略。

#### 3.6.1 ToolRegistry 隔离方案：每个 Worker 独立实例

每个 Worker 启动时，由 `WorkerLoopConfig` 创建一个**全新的 `ToolRegistry` 实例**，不与父编排器或其他 Worker 共享。

```python
def create_worker_tools(worker_id: str, session_id: str, project_path: str | None) -> ToolRegistry:
    """为每个 Worker 创建独立的工具注册表"""
    registry = ToolRegistry()

    # 注册标准工具（只读工具，可安全共享逻辑）
    registry.register(BashTool())
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(EditTool())
    registry.register(WebSearchTool())

    # 注册会话级工具（关键：绑定到父 session_id）
    registry.register(SessionRecallTool(session_id=session_id))

    return registry
```

**选择独立实例的原因**：
1. `ToolRegistry` 内部是简单 dict 结构（`_tools: dict[str, Tool]`），无锁保护
2. `BashTool` 持有 `_active_sessions` dict 和 `subprocess.Popen` 引用，共享会导致进程管理混乱
3. 独立实例零协调开销，完全避免竞态条件

#### 3.6.2 SessionRecallTool 行为定义

`SessionRecallTool(session_id)` 绑定到**父会话的 session_id**（非 Worker 临时 ID），因此：

| 场景 | 行为 |
|------|------|
| Worker A 调用 `session_recall` | 读取父会话的共享记忆（包括 DECOMPOSE 之前的消息） |
| Worker B 调用 `session_recall` | 读取同一父会话的共享记忆（与 A 看到的相同） |
| Worker 执行期间的消息 | **不会**被其他正在执行的 Worker 看到（隔离在各自 LoopContext 中） |
| 所有 Worker 完成后 | Worker 消息由 MergeResult 合并到父 LoopContext |

> **注意**：由于 Worker 共享 `session_id` 且消息可能异步写入，`session_recall` 在 Worker 执行期间返回的结果是**快照级别一致**的（基于 DECOMPOSE 时的上下文），不保证包含其他 Worker 的实时进度。

#### 3.6.3 Worker 内 Approval 流程与权限硬边界

> **V2 评审新增**：明确 Worker 执行工具时的审批策略。
> **V3 评审修正**：补充工具权限硬边界，Worker 工具权限受**工具白名单**和**文件访问边界**两层约束。

Worker 运行在**无交互环境**中（由编排器通过 `asyncio.create_task` 启动），无法等待用户审批。V1 采用如下策略：

| 工具类型 | Approval 策略 | 理由 |
|---------|-------------|------|
| 只读工具（Read/Glob/Grep/SessionRecall） | **自动批准** | 无副作用，无需审批 |
| 写入工具（Write/Edit） | **自动批准** | 受文件访问边界约束（见下文） |
| WebSearchTool | **自动批准** | 只读网络查询 |
| Bash | **默认不暴露** | 安全敏感，V1 不对 Worker 开放 |

**实现方式**：Worker 的 `RapidExecutionLoop` 使用 `AgentMode.BUILD`（等同于现有非交互模式），该模式下所有工具调用无需 approval。编排器在创建 WorkerLoop 时通过 `WorkerLoopConfig` 注入：

```python
class WorkerLoopConfig:
    agent_mode: AgentMode = AgentMode.BUILD    # 非交互模式，自动批准所有工具
    approval_callback: None = None              # 不注入审批回调
```

##### 权限硬边界（V3 评审新增）

Worker 工具权限必须**同时受两层约束**，任何一层不通过即拒绝执行：

| 约束层 | 机制 | 说明 |
|--------|------|------|
| **工具白名单** | `worker_allowed_tools` 配置 | Worker 只能使用白名单内的工具，白名单外的工具在 registry 构建时即不注册 |
| **文件访问边界** | `WorkerSpec.files` 字段 | `file_read` / `file_write` / `file_edit` 的路径必须匹配 `files` 列表中的路径（或其子路径），超出范围的操作返回 `PermissionDenied` |

**默认白名单**（可通过环境变量扩展）：

| 工具 | 是否默认暴露 | 说明 |
|------|------------|------|
| `file_read` | ✅ | 读取 `files` 范围内的文件 |
| `file_write` | ✅ | 写入 `files` 范围内的文件 |
| `file_edit` | ✅ | 编辑 `files` 范围内的文件 |
| `session_recall` | ✅ | 访问父会话记忆（绑定父 session_id） |
| `task_complete` | ✅ | 标记任务完成 |
| `shell` | ❌ | 安全敏感，V1 不暴露给 Worker |
| `search` | ❌ | V1 Worker 不需要 |
| `image` / `audio` | ❌ | V1 Worker 不需要 |

**扩展方式**：
```env
# 通过环境变量扩展 Worker 工具白名单（逗号分隔）
ORCHESTRATOR_WORKER_ALLOWED_TOOLS=file_read,file_write,file_edit,session_recall,task_complete,search
```

**实现方式**：
```python
class OrchestratorLoop:
    async def _create_worker_tool_registry(self, spec: WorkerSpec) -> ToolRegistry:
        """
        为 Worker 创建独立的工具注册表，带权限边界。

        运行过程:
            1. 从主运行的工具定义中，过滤出 worker_allowed_tools 白名单内的工具
            2. 为 file_read / file_write / file_edit 包装路径校验层：
               路径必须属于 spec.files 中的文件或其子路径
            3. 返回独立的 ToolRegistry 实例
        """
        allowed = self.config.worker_allowed_tools
        worker_registry = ToolRegistry()

        for tool_name in allowed:
            original_tool = self.tool_registry.get(tool_name)
            if original_tool is None:
                continue

            # 为文件操作工具包装路径边界校验
            if tool_name in ("file_read", "file_write", "file_edit"):
                wrapped = self._wrap_with_path_boundary(original_tool, spec.files)
                worker_registry.register(wrapped)
            else:
                worker_registry.register(original_tool)

        return worker_registry

    def _wrap_with_path_boundary(self, tool, allowed_files: list[str]):
        """
        包装文件操作工具，拦截路径不在 allowed_files 范围内的调用。

        运行过程:
            1. 提取工具调用参数中的文件路径
            2. 检查路径是否属于 allowed_files 中的任何文件或其子路径
            3. 不在范围内则返回 PermissionDenied 错误，不执行原工具
        """
        allowed_set = set(allowed_files)

        @wraps(tool)
        async def bounded_tool(**kwargs):
            target_path = kwargs.get("file_path") or kwargs.get("path")
            if target_path:
                resolved = os.path.normpath(target_path)
                if not any(
                    resolved == f or resolved.startswith(f + os.sep)
                    for f in allowed_set
                ):
                    return ToolResult(
                        status="error",
                        content=f"权限不足：文件 {target_path} 不在 Worker 任务范围内",
                    )
            return await tool(**kwargs)

        return bounded_tool
```

**风险缓解**：
- 文件写入冲突：由 DECOMPOSE 阶段的文件分配约束（§4.1）预检 + 文件访问边界双重保障
- 工具越权：白名单外的工具在 registry 构建时即不注册，Worker 无法调用
- 文件越界：路径校验层在工具执行前拦截，超出 `files` 范围的操作返回错误
- Bash 安全：V1 默认不对 Worker 暴露 shell，需要时通过环境变量显式添加

#### 3.6.4 Worker 历史消息截断策略

> **V2 评审新增**：防止长对话历史撑爆 Worker 上下文窗口。

Worker 通过 `ContextSnapshot.seed_messages` 继承父会话的完整对话历史。长对话（数十轮）可能导致 Worker 启动时即接近上下文上限，留给实际工作的 token 空间不足。

**V1 截断策略**（两层防护）：

```python
class OrchestratorLoop:
    # Worker 上下文预算占主模型 context_window 的比例
    WORKER_CONTEXT_BUDGET_RATIO = 0.6  # 默认 60%，留 40% 给 Worker 执行期间新增内容

    def _prepare_worker_snapshot(self, snapshot: ContextSnapshot, model: str) -> ContextSnapshot:
        """为 Worker 准备截断后的快照"""
        budget = int(get_context_window(model) * self.WORKER_CONTEXT_BUDGET_RATIO)

        # 第 1 层：压缩旧的 tool 输出（LoopContext 已有能力）
        ctx = LoopContext.from_run_input(
            task="", project_path=snapshot.project_path, run_id="temp",
            session_id=snapshot.session_id, agent_mode="build",
            seed_messages=list(snapshot.seed_messages),
        )
        ctx.prune_tool_outputs(keep_recent=N, max_output_tokens=4000)
        trimmed_messages = list(ctx.messages)

        # 第 2 层：按 token 预算截断最旧的消息（保留 system + 最近 N 条）
        token_count = count_tokens(trimmed_messages, model)
        while token_count > budget and len(trimmed_messages) > 3:
            # 移除第 2 条（保留 system prompt 和最新 user 消息）
            trimmed_messages.pop(1)
            token_count = count_tokens(trimmed_messages, model)

        return ContextSnapshot(
            seed_messages=trimmed_messages,
            system_sections=list(snapshot.system_sections),
            project_path=snapshot.project_path,
            session_id=snapshot.session_id,
            supplemental_context=snapshot.supplemental_context,
            snapshot_timestamp=snapshot.snapshot_timestamp,
            parent_run_id=snapshot.parent_run_id,
            depth=snapshot.depth,
        )
```

**截断优先级**（从先删除到后删除）：
1. 最早的 tool 输出结果（大文本，信息密度低）
2. 最早的对话轮次（user/assistant 消息）
3. 始终保留：system prompt、最近 3 条消息、当前 task

**可选配置**（§8 环境变量）：
```env
ORCHESTRATOR_WORKER_CONTEXT_RATIO=0.6  # Worker 上下文预算占 context_window 的比例
```

## 4. 执行流程详解

### 阶段 1: DECOMPOSE（分解）

编排器使用分解 prompt 调用 LLM：

```
System: 你是一个编排器。将以下任务分解为可由独立 worker 并行执行的独立子任务。

任务: {user_task}
对话上下文: {recent_messages_snapshot}

文件分配约束（关键）：
- 每个子任务必须明确列出将读取或修改的文件路径
- 不同子任务的文件列表不能有交集（一个文件只能被一个 worker 操作）
- 如果多个子任务需要操作同一文件，将它们合并为一个子任务
- 如果无法避免文件交集，在 context_hint 中标注预期冲突

输出 JSON:
{
  "workers": [
    {"worker_id": "w_1", "task": "...", "context_hint": "...", "files": ["path/a.py", "path/b.py"], "priority": 0},
    ...
  ]
}
```

> **关于模型选择的说明**: 编排器的分解调用使用 `OrchestratorConfig.synthesis_model`（如果已设置），否则回退到主 `RunConfig.model`。Worker 的模型选择通过 `WorkerLoopConfig.model_override` 实现，构建每个 worker 的 `LLMClient` 时，它优先于 `RunConfig.model`。

**验证规则**:
- `len(workers) <= config.max_workers`
- 每个 `task` 必须非空
- 每个 `task` 必须可独立执行（第一阶段无循环依赖）
- **不同 worker 的 `files` 列表不能有交集**（文件冲突检测，评审新增）

### 阶段 2: FAN-OUT（扇出）

对每个 `WorkerSpec`：

1. **拍摄 ContextSnapshot**: 在 DECOMPOSE 完成后、创建任何 Worker 之前，统一拍摄一次上下文快照（见 §3.5）：
   ```python
   snapshot = ContextSnapshot(
       messages=context.messages,
       system_prompt=context.system_prompt,
       available_tools=context.available_tools,
       conversation_id=context.conversation_id,
       snapshot_timestamp=datetime.now(),
       parent_run_id=context.run_id,
       depth=current_depth + 1
   )
   ```
   所有 Worker 共享同一个 `ContextSnapshot` 实例。`to_loop_context()` 内部会做深拷贝，保证 Worker 之间无共享可变状态。

2. **创建 WorkerContext**: 从快照构建独立的 `LoopContext`：
   ```python
   worker_context = snapshot.to_loop_context(worker_spec.worker_id, worker_spec.task)
   # 将 context_hint 注入为第一条用户消息
   worker_context.messages.append(Message(role="user", content=worker_spec.context_hint))
   ```
   - `config` = WorkerLoopConfig（继承自主 RunConfig，如果 `OrchestratorConfig.worker_model` 已设置则覆盖模型）
   - `max_iterations` = `config.worker_max_iterations`（默认 5，比主循环小，节省 75% token）

   `WorkerLoopConfig` 是 `RunConfig` 的薄包装：
   ```python
   @dataclass
   class WorkerLoopConfig(RunConfig):
       worker_id: str = ""
       parent_run_id: str = ""        # 编排器运行的 ID
       enable_plan_persistence: bool = True
       # 模型覆盖：如果设置，优先于 RunConfig.model
       model_override: str | None = None
   ```

2. **运行 WorkerLoop**: 使用 worker 的上下文执行 `RapidExecutionLoop`。每个 worker：
   - 有自己的事件回调（事件被缓冲，暂不流入主对话）
   - 运行独立的 PLANNING → TOOL_EXECUTION → SUMMARIZING → REFLECTING → DONE 循环
   - 产出一个 `LoopResult`

3. **并发执行**: 所有 worker 通过 `asyncio.gather(*worker_tasks, return_exceptions=True)` 运行。注意：由于 ReflexionOS 使用 asyncio（单线程事件循环），这里的"并行"指的是并发的 I/O 密集型执行。LLM 调用通过 httpx 实现非阻塞。真正的并行需要对 CPU 密集型工具执行使用 `loop.run_in_executor()`。

### 阶段 3: COLLECT（收集）

收集所有 worker 的结果：

```python
worker_results: list[WorkerResult] = []
for task_result in gather_results:
    if isinstance(task_result, Exception):
        worker_results.append(WorkerResult(
            worker_id=..., status="failed", result=str(task_result), ...
        ))
    else:
        worker_results.append(task_result)
```

**部分失败处理**: 如果某些 worker 失败，编排器仍会继续执行 SYNTHESIZE 阶段，使用可用结果。合成 prompt 会包含失败信息。

### 阶段 4: SYNTHESIZE（合成）

编排器调用 LLM 合并所有 worker 结果：

```
System: 你是一个编排器。多个 worker 已并行完成了子任务。
将它们的结果合成为单一连贯的回复。

原始任务: {user_task}

Worker 结果:
--- Worker w_1 (成功) ---
{worker_1_result}

--- Worker w_2 (失败: 超时) ---
{error_details}

--- Worker w_3 (成功) ---
{worker_3_result}

请提供一个统一的回复，整合所有成功的结果并说明任何失败。
```

合成输出成为最终的 `OrchestrationResult.final_output`。

## 5. 与现有架构的集成

### 5.1 AgentService 变更

`AgentService.create_and_start_run()` 需要新增一个分支：

```python
if orchestration_enabled and should_orchestrate(task, config):
    # 使用 OrchestratorLoop
    orchestrator = OrchestratorLoop(config=orchestrator_config)
    result = await orchestrator.run(task, conversation_id, ...)
else:
    # 现有的单循环路径（不变）
    loop = RapidExecutionLoop(...)
    result = await loop.run(context)
```

**`should_orchestrate()` —— V1 仅明确列表触发**（评审修正，§2 决策 #5）：

> **设计原则**：宁可漏触发（用户可通过 `force_orchestration` 手动启用），不误触发（避免浪费 token 和增加延迟）。

```python
import re

def should_orchestrate(task: str, config: OrchestratorConfig) -> bool:
    """
    V1 策略：仅对明确编号列表触发编排。
    不使用启发式规则（长度、关键词），避免假阳性误判。
    后续版本可引入 LLM 二分类器（V2 规划）。
    """
    # 配置开关优先
    if config.disable_orchestration:
        return False
    if config.force_orchestration:
        return True

    # 检测明确编号列表：至少 2 个编号项
    # 匹配: "1. xxx 2. yyy" 或 "1、xxx 2、yyy" 或 "1) xxx 2) yyy"
    # 排除: Markdown 标题（行首有 #）、短内容（<10 字符，如 "1. 标题"）
    numbered_pattern = re.compile(
        r'(?:^|\n)\s*(?!#)\d+[\.\、\)]\s*\S.{9,}',  # 至少 10 字符内容，排除 # 开头
        re.MULTILINE
    )
    matches = numbered_pattern.findall(task)
    if len(matches) >= 2:
        return True

    # 默认不触发
    return False
```

**触发示例**：

| 用户输入 | 触发？ | 原因 |
|---------|--------|------|
| "1. 重构 auth.py 2. 写单元测试 3. 更新 README" | ✅ | 包含 3 个编号项 |
| "读取 config.yaml 并且检查依赖" | ❌ | 无编号列表 |
| "重构 auth 模块，然后部署" | ❌ | 无编号列表（避免假阳性） |
| `force_orchestration=True` | ✅ | 强制触发 |

**`should_orchestrate()` 测试矩阵（V3 评审新增）**：

单元测试必须覆盖以下场景：

| # | 测试用例 | 输入 | 预期 | 类别 |
|---|---------|------|------|------|
| T1 | 普通段落不触发 | `"请帮我看看这个文件有什么问题"` | `False` | 负例 |
| T2 | Markdown 标题不触发 | `"# 任务一\n## 子任务\n### 步骤"` | `False` | 负例（排除 # 开头） |
| T3 | 单项列表不触发 | `"1. 重构 auth.py 使其支持 JWT 认证"` | `False` | 负例（仅 1 项） |
| T4 | 两项以上编号列表触发 | `"1. 重构 auth.py 2. 写单元测试 3. 更新 README"` | `True` | 正例 |
| T5 | 每项少于 10 字符不触发 | `"1. 改代码\n2. 写测试\n3. 更新文档"` | `False` | 负例（内容过短） |
| T6 | 中文顿号编号触发 | `"1、重构认证模块使其支持 OAuth\n2、添加单元测试覆盖边界情况"` | `True` | 正例（中文格式） |
| T7 | 括号编号触发 | `"1) 修复登录 bug 并添加错误处理\n2) 编写回归测试用例"` | `True` | 正例（括号格式） |
| T8 | disable_orchestration 优先 | 任意输入 + `disable_orchestration=True` | `False` | 配置覆盖 |
| T9 | force_orchestration 优先 | 任意输入 + `force_orchestration=True` | `True` | 配置覆盖 |
| T10 | 空字符串 | `""` | `False` | 边界条件 |
| T11 | 混合 Markdown 标题和编号 | `"# 标题\n1. 子任务一需要完成认证重构\n2. 子任务二需要编写测试用例"` | `True` | 正例（标题被排除，编号项保留） |

```python
# tests/unit/test_should_orchestrate.py
import pytest
from app.orchestrator.loop import should_orchestrate
from app.orchestrator.config import OrchestratorConfig

@pytest.mark.parametrize("task,expected", [
    ("请帮我看看这个文件有什么问题", False),                          # T1
    ("# 任务一\n## 子任务\n### 步骤", False),                         # T2
    ("1. 重构 auth.py 使其支持 JWT 认证", False),                     # T3
    ("1. 重构 auth.py 2. 写单元测试 3. 更新 README", True),           # T4
    ("1. 改代码\n2. 写测试\n3. 更新文档", False),                      # T5
    ("1、重构认证模块使其支持 OAuth\n2、添加单元测试覆盖边界情况", True),  # T6
    ("1) 修复登录 bug 并添加错误处理\n2) 编写回归测试用例", True),       # T7
    ("", False),                                                      # T10
    ("# 标题\n1. 子任务一需要完成认证重构\n2. 子任务二需要编写测试用例", True),  # T11
])
def test_should_orchestrate_default(task, expected):
    config = OrchestratorConfig()
    assert should_orchestrate(task, config) == expected

def test_disable_overrides_all():  # T8
    config = OrchestratorConfig(disable_orchestration=True)
    assert should_orchestrate("1. 任务一需要完成重构 2. 任务二需要编写测试", config) is False

def test_force_overrides_all():  # T9
    config = OrchestratorConfig(force_orchestration=True)
    assert should_orchestrate("随便什么内容", config) is True
```

### 5.2 对话模型影响

每个 worker 的事件都带有 `worker_id` 元数据标签：

```python
# 在 worker 事件回调中
event["metadata"] = {"worker_id": worker_spec.worker_id, "orchestrated": True}
```

这使得对话 UI 可以显示哪个 worker 产出了哪些消息。

### 5.3 运行时适配器变更

`ConversationRuntimeAdapter` 需要感知编排运行：

- Worker 事件在执行期间缓冲，合成后批量提交到对话
- 或者：worker 事件实时流入并带有 worker_id 标签（UX 体验更好，优先选择）

### 5.4 并发控制（评审新增）

> **V2 评审修正**：Semaphore 粒度是 **Worker 级**（整个 `_run_worker()` 循环），而非单次 LLM 调用级。变量命名已同步修正。
>
> **设计理由**：Worker 内部的 LLM 调用由 `RapidExecutionLoop.max_iterations` 控制总次数。Semaphore 控制的是**同时运行的 Worker 数**（即同时占用 LLM API 并发 slot 的 Worker 数），两者互补。

多个 Worker 同时运行会触发 LLM API Rate Limit（尤其 OpenAI/Anthropic 的并发限制）。使用 `asyncio.Semaphore` 控制 Worker 级并发数：

```python
class OrchestratorLoop:
    def __init__(self, config: OrchestratorConfig):
        # Worker 级并发：限制同时运行的 Worker 数（= 同时占用 LLM API 的 Worker 数）
        self._worker_semaphore = asyncio.Semaphore(config.max_concurrent_workers)  # 默认 3
        # 工具级并发：限制同时执行的工具调用数（跨所有 Worker 共享）
        self._tool_semaphore = asyncio.Semaphore(config.max_concurrent_tools)      # 默认 5

    async def _run_worker(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
        """运行单个 Worker，受 Worker 级 Semaphore 控制"""
        for attempt in range(1 + self.config.worker_retry_count):
            try:
                async with self._worker_semaphore:  # 整个 Worker 生命周期持锁
                    context = snapshot.to_loop_context(spec.worker_id, spec.task)
                    context.max_iterations = self.config.worker_max_iterations
                    result = await self._worker_loop.run(context)
                    if result.status == "success":
                        return result
                    if attempt < self.config.worker_retry_count:
                        await asyncio.sleep(self.config.worker_retry_delay_s * (attempt + 1))
                        continue
                    return result
            except (TimeoutError, RateLimitError) as e:
                if attempt < self.config.worker_retry_count:
                    await asyncio.sleep(self.config.worker_retry_delay_s * (attempt + 1))
                    continue
                return WorkerResult(worker_id=spec.worker_id, status="failed", result=str(e), ...)

    async def _execute_tool(self, worker_id: str, tool_call: ToolCall):
        """工具执行受独立 Semaphore 控制"""
        async with self._tool_semaphore:
            return await tool_registry.execute(tool_call)
```

**并发控制策略**：
- `max_concurrent_workers=3`：最多 3 个 Worker 同时运行（每个 Worker 持续占用 1 个 slot 直到完成或超时）
- `max_concurrent_tools=5`：最多 5 个工具同时执行（跨所有 Worker 共享，防止文件系统/网络资源争用）
- 剩余 Worker 在 Semaphore 上排队等待，不阻塞已成功的 Worker
- `max_workers`（Worker 总数）≥ `max_concurrent_workers`（同时运行数）：总任务多但并发可控

## 6. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/execution/orchestrator.py` | **新增** | OrchestratorLoop、WorkerSpec、WorkerResult、OrchestrationResult、OrchestratorConfig |
| `backend/app/execution/worker_loop.py` | **新增** | WorkerLoop，包装 RapidExecutionLoop 并添加 worker 特有行为 |
| `backend/app/execution/models.py` | 修改 | LoopContext 增加 `orchestrated` 标志、`worker_id` 字段 |
| `backend/app/execution/rapid_loop.py` | 不变 | 保持不变 —— worker 就是完整的 RapidExecutionLoop 实例 |
| `backend/app/services/agent_service.py` | 修改 | `create_and_start_run()` 增加编排分支 |
| `backend/app/llm/base.py` | 不变 | LLMClient 被编排器原样使用 |
| `backend/app/tools/registry.py` | 不变 | Worker 从主运行复制工具定义，并为每个 Worker 构建独立 ToolRegistry（见 §3.6.1），确保工具隔离 |

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| 分解 LLM 调用失败 | 回退到单个 RapidExecutionLoop（非编排模式） |
| 分解返回无效 JSON | 重试一次，然后回退到单循环 |
| 单个 worker 超时 | 标记为 `timeout`，包含在合成中 |
| 单个 worker 异常 | 标记为 `failed`，错误信息包含在合成中 |
| 单个 worker 临时故障（RateLimit/网络超时） | 自动重试 1 次（`worker_retry_count=1`），指数退避后仍失败则标记 `failed`（评审新增，§5.4） |
| 所有 worker 全部失败 | 返回包含所有失败详情的错误 OrchestrationResult |
| 合成 LLM 调用失败 | 返回原始 worker 结果的拼接 |

**Worker 失败策略测试矩阵（V3 评审新增）**：

集成测试必须覆盖以下失败场景：

| # | 测试场景 | 设置 | 预期行为 |
|---|---------|------|---------|
| F1 | 单个 Worker 超时 | 3 个 Worker，其中 1 个超时（模拟耗时 > `worker_timeout_s`） | 超时 Worker 标记 `timeout`，其余 2 个成功；synthesis 整合 2 个成功结果并说明 1 个超时项 |
| F2 | 单个 Worker 抛异常 | 3 个 Worker，其中 1 个抛出未捕获异常 | 异常 Worker 标记 `failed`，`result` 包含错误信息；synthesis 整合其余结果 |
| F3 | 部分成功、部分失败 | 5 个 Worker，2 个成功、2 个失败、1 个超时 | OrchestrationResult.status = `"partial"`，synthesis 整合 2 个成功结果并**明确说明** 3 个失败项的原因 |
| F4 | 所有 Worker 全部失败 | 3 个 Worker，全部超时或异常 | OrchestrationResult.status = `"failed"`，返回包含所有失败详情的错误结果 |
| F5 | Worker 临时故障自动重试 | 1 个 Worker 首次触发 RateLimitError，重试后成功 | Worker 最终标记 `success`，重试日志中可见 1 次退避重试 |
| F6 | Worker 重试耗尽仍失败 | 1 个 Worker 连续 2 次 RateLimitError（`worker_retry_count=1`） | Worker 标记 `failed`，重试日志中可见 2 次尝试 |
| F7 | 合成 LLM 调用失败 | 所有 Worker 成功，但 synthesis 调用抛异常 | 回退到原始 worker 结果的文本拼接，OrchestrationResult.status = `"partial"` |
| F8 | 分解 LLM 调用失败 | DECOMPOSE 阶段 LLM 返回错误 | 回退到单个 RapidExecutionLoop（非编排模式），用户无感知 |

```python
# tests/integration/test_orchestrator_failure.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_single_worker_timeout(orchestrator, mock_workers):
    """F1: 单个 Worker 超时，其余成功"""
    mock_workers[1].side_effect = TimeoutError("Worker 超时")
    result = await orchestrator.run(task="1. 任务一... 2. 任务二... 3. 任务三...")
    assert result.status == "partial"
    assert result.worker_results[1].status == "timeout"
    assert "超时" in result.final_output or "timeout" in result.final_output.lower()

@pytest.mark.asyncio
async def test_single_worker_exception(orchestrator, mock_workers):
    """F2: 单个 Worker 抛异常"""
    mock_workers[1].side_effect = RuntimeError("意外错误")
    result = await orchestrator.run(task="1. 任务一... 2. 任务二... 3. 任务三...")
    assert result.worker_results[1].status == "failed"
    assert "意外错误" in result.worker_results[1].result

@pytest.mark.asyncio
async def test_partial_success_synthesis_mentions_failures(orchestrator, mock_workers):
    """F3: 部分成功，合成明确说明失败项"""
    mock_workers[0].return_value = success_result("任务一完成")
    mock_workers[1].side_effect = RuntimeError("失败")
    mock_workers[2].side_effect = TimeoutError("超时")
    result = await orchestrator.run(task="1. 任务一... 2. 任务二... 3. 任务三...")
    assert result.status == "partial"
    # 合成结果必须提及失败项
    assert "失败" in result.final_output or "超时" in result.final_output

@pytest.mark.asyncio
async def test_all_workers_fail(orchestrator, mock_workers):
    """F4: 所有 Worker 全部失败"""
    for mock_w in mock_workers:
        mock_w.side_effect = RuntimeError("全部失败")
    result = await orchestrator.run(task="1. 任务一... 2. 任务二...")
    assert result.status == "failed"

@pytest.mark.asyncio
async def test_worker_retry_on_rate_limit(orchestrator):
    """F5: Worker 临时故障自动重试后成功"""
    call_count = 0
    async def flaky_worker(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("限流")
        return success_result("重试成功")
    # ... 验证 call_count == 2，Worker 最终 status == "success"

@pytest.mark.asyncio
async def test_synthesis_failure_fallback(orchestrator, mock_synthesis_llm):
    """F7: 合成失败，回退到 worker 结果拼接"""
    mock_synthesis_llm.side_effect = RuntimeError("合成 LLM 失败")
    result = await orchestrator.run(task="1. 任务一... 2. 任务二...")
    assert result.status == "partial"
    # 回退结果应包含各 worker 的原始输出
    assert "任务一" in result.final_output
```

## 8. 配置

### 环境变量

```env
ORCHESTRATOR_ENABLED=true
ORCHESTRATOR_MAX_WORKERS=5
ORCHESTRATOR_WORKER_TIMEOUT_S=300
ORCHESTRATOR_MAX_NESTING_DEPTH=2
ORCHESTRATOR_WORKER_MODEL=""          # 空 = 与主模型相同
ORCHESTRATOR_SYNTHESIS_MODEL=""       # 空 = 与主模型相同

# ── Worker 行为（评审新增）──
ORCHESTRATOR_WORKER_MAX_ITERATIONS=5  # Worker 独立最大迭代轮数
ORCHESTRATOR_WORKER_MAX_TOOL_CALLS=10 # 每个 Worker 最大工具调用数

# ── 并发控制（评审新增）──
ORCHESTRATOR_MAX_CONCURRENT_WORKERS=3    # Worker 级并发数（Semaphore）
ORCHESTRATOR_MAX_CONCURRENT_TOOLS=5      # 工具执行最大并发数（Semaphore）

# ── 容错配置（评审新增）──
ORCHESTRATOR_WORKER_RETRY_COUNT=1    # Worker 失败后重试次数
ORCHESTRATOR_WORKER_RETRY_DELAY_S=5  # 重试间隔（秒）

# ── 决策控制（评审新增）──
ORCHESTRATOR_FORCE=false             # 强制编排，忽略 should_orchestrate() 判断
ORCHESTRATOR_DISABLED=false          # 完全禁用编排（调试用）

# ── Worker 工具权限（V3 评审新增）──
ORCHESTRATOR_WORKER_ALLOWED_TOOLS=file_read,file_write,file_edit,session_recall,task_complete
```

### 数据库连接池约束（V3 评审新增）

> 并发 Worker 可能同时调用 `session_recall`（读取 DB）或写入对话事件。如果连接池容量不足，会导致排队、超时或吞吐下降。

**约束**：`DB_POOL_SIZE >= ORCHESTRATOR_MAX_CONCURRENT_WORKERS + 2`（+2 留给编排器主进程和合成阶段）

```env
# 示例：如果 max_concurrent_workers=3，则 pool_size 至少为 5
DB_POOL_SIZE=10  # 推荐值，留有余量
```

**并发测试要求**：集成测试中必须验证以下场景不出现连接池耗尽：
- `max_concurrent_workers=3` 时，3 个 Worker 同时调用 `session_recall`
- `max_concurrent_workers=5` 时，5 个 Worker 同时写入对话事件

### 运行时配置（按请求）

```python
# 在 RunConfig 或新的 OrchestratorConfig 中
orchestrator: OrchestratorConfig | None = None  # None = 不启用编排
```

## 9. 第二阶段后续工作（动态派发）

第一阶段稳定后，将 `spawn_subagent` 添加为内置工具：

```python
@tool(name="spawn_subagent", description="派发子代理并行执行任务")
async def spawn_subagent(task: str, context_hint: str = "") -> str:
    """编排器和 worker 均可使用。允许动态嵌套。"""
    ...
```

这使得：
- Worker 可以派发自己的子 worker（深度受限）
- 编排器可以在执行中途动态添加 worker
- 实现真正的 Codex/Claude Code 风格的自适应并行

## 10. 非目标（第一阶段）

- ❌ 基于 DAG 的 worker 调度（depends_on 字段已保留但未实现）
- ❌ 执行期间 worker 之间的通信
- ❌ 实时事件流 / SSE 推送（V1 缓冲模式，后续版本引入实时事件流，评审明确排除）
- ❌ 不依赖 LLM 的自动任务分解（V1 仅对明确编号列表触发，见 §5.1）
- ❌ 跨对话编排（每次编排在一个对话内进行）
- ❌ Worker 结果缓存（V1 任务不会重复，后续版本引入，评审明确排除）
- ❌ 执行进度实时可视化（依赖实时事件流，后续版本引入，评审明确排除）
- ❌ 合成阶段模型动态选择（过度工程，后续版本引入，评审明确排除）

## 11. 成功标准

1. "读取 auth.py、为其编写测试、更新 README" 这样的任务能被分解为 3 个并行运行的 worker
2. 总执行时间 < 各 worker 时间之和（真正的并行效果）
3. 现有的单任务行为完全不受影响（向后兼容）
4. 失败的 worker 不会阻塞成功的 worker —— 部分结果会被合成
5. 所有现有测试无需修改即可通过
6. 分解和合成的 LLM 调用能正确选择配置的模型（worker_model / synthesis_model）

## 12. 实现顺序建议（V3 评审新增）

> 评审建议按以下 5 个 Phase 逐步实现，每个 Phase 完成后可独立验证，降低集成风险。

### Phase 1：数据结构与配置（基础层）

**目标**：定义所有核心数据结构，无执行逻辑。

**文件**：
- `backend/app/execution/orchestrator.py` — 新建，定义 `WorkerSpec`、`WorkerResult`、`OrchestrationResult`、`OrchestratorConfig`、`ContextSnapshot`
- `backend/app/execution/models.py` — 修改，LoopContext 增加 `orchestrated` 和 `worker_id` 字段

**验证**：单元测试通过，数据结构可序列化/反序列化，`ContextSnapshot.to_loop_context()` 正确。

### Phase 2：分解与合成（核心 LLM 逻辑）

**目标**：实现 `_decompose()` 和 `_synthesize()`，可独立测试。

**文件**：
- `backend/app/execution/orchestrator.py` — 实现 `OrchestratorLoop._decompose()` 和 `_synthesize()`

**验证**：
- `_decompose()` 能将编号任务解析为合法的 `WorkerSpec` 列表（含文件冲突检测）
- `_synthesize()` 能合并多个 `WorkerResult` 为连贯文本
- 分解/合成阶段 token 正确记录到 `decompose_tokens` / `synthesis_tokens`

### Phase 3：Worker 执行与扇出（并发层）

**目标**：实现 `_run_worker()` 和 `_fan_out()`，Worker 可并发执行。

**文件**：
- `backend/app/execution/orchestrator.py` — 实现 `_run_worker()`、`_fan_out()`、`_create_worker_tool_registry()`
- `backend/app/execution/worker_loop.py` — 新建，WorkerLoop 包装

**验证**：
- 单个 Worker 可独立运行并返回 `WorkerResult`
- 多个 Worker 通过 `asyncio.gather` 并发执行
- 工具白名单 + 文件访问边界生效（§3.6.3 权限硬边界）
- Semaphore 并发控制正确（§5.4）

### Phase 4：AgentService 集成（入口层）

**目标**：在 `AgentService.create_and_start_run()` 中接入编排分支。

**文件**：
- `backend/app/services/agent_service.py` — 修改，增加 `should_orchestrate()` 判断和编排分支

**验证**：
- `should_orchestrate()` 测试矩阵全部通过（11 个用例，§5.1）
- 普通任务走原有单循环路径，编号任务走编排路径
- `force_orchestration` / `disable_orchestration` 配置生效

### Phase 5：集成测试与失败路径测试

**目标**：端到端验证 + 失败场景覆盖。

**测试矩阵**：
- 成功路径：3 个 Worker 并行完成，合成结果正确
- 失败路径：8 个场景全部通过（§7 测试矩阵 F1-F8）
- 并发控制：连接池不耗尽（§8 DB 约束）
- 向后兼容：所有现有测试无需修改即可通过

**验收标准**：§11 成功标准 6 条全部满足。

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
数据结构      分解/合成     并发执行      集成入口      集成测试
(可验证)     (可验证)     (可验证)     (可验证)     (验收)
```


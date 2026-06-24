# Sub-Agent 多代理系统 — 修订设计文档

> **日期**: 2026-06-23
> **基于**: 对现有代码库的全面审查 + OpenCode 架构模式分析
> **前身文档**: `2026-06-15-sub-agent-and-multimodal-design.md`（已废弃，多模态部分已实现，sub-agent 部分被本文档取代）
> **状态**: 待审批

---

## 1. 现状评估

### 1.1 已实现能力

经过对代码库的全面审查，以下能力**已经完整实现**，无需重新设计：

| 模块 | 位置 | 状态 |
|------|------|------|
| `MessageAttachment` 模型 | `backend/app/models/conversation.py:95` | ✅ 完整 |
| DB `attachments_json` 列 | `backend/app/storage/models.py:109` | ✅ 完整 |
| `AttachmentService` | `backend/app/services/attachment_service.py` | ✅ 上传/清理/转换 |
| `supports_vision` 探测 | `backend/app/services/llm_provider_service.py:314` | ✅ 完整 |
| OpenAI image_url 适配 | `backend/app/llm/openai_adapter.py:298-301` | ✅ 完整 |
| 对话历史多模态加载 | `backend/app/execution/conversation_history_loader.py:9-28` | ✅ 完整 |
| 上传 API | `backend/app/api/routes/upload.py:59` | ✅ 完整 |
| `RapidExecutionLoop` | `backend/app/execution/rapid_loop.py` | ✅ 全阶段完整 |
| `LoopContext` + `from_run_input()` | `backend/app/execution/context_manager.py` | ✅ 完整 |
| `ToolRegistry` + `BaseTool` | `backend/app/tools/registry.py` | ✅ 完整 |
| `ToolCallExecutor` | `backend/app/execution/tool_call_executor.py` | ✅ 完整 |
| `ToolSetConfig`（工具可见性） | `backend/app/execution/runtime_tool_definitions.py:15` | ✅ exploration/plan 两套 |
| `AgentService`（turn 生命周期） | `backend/app/services/agent_service.py` | ✅ 完整 |
| `SessionService`（基础 CRUD） | `backend/app/services/session_service.py` | ✅ 完整 |
| SSE 事件流 | `backend/app/api/routes/sse.py` | ✅ 完整 |

### 1.2 未实现能力（Sub-Agent 核心缺失）

| 缺失模块 | 说明 |
|----------|------|
| `DelegateTool` | 主 Agent 委托子任务的工具，不存在 |
| `SubAgentRunner` | Sub-agent 独立执行循环，不存在 |
| Sub-agent 受限工具集配置 | 无 sub-agent 专用的工具子集 |
| 前端 sub-agent UI | delegate 工具调用/结果无专属展示组件 |

> **关于持久化**: Sub-agent 本质上是一个"重型 tool call"——同步阻塞执行完成后返回结果。
> 与 shell 命令、file edit 同理，中间过程不需要 DB 持久化。最终结果已作为 `tool_result`
> 存在 parent 的对话历史中。调试需求靠应用日志满足。如未来有"执行过程回放"等明确需求再加。

---

## 2. 设计方案

### 2.1 核心模式：Hierarchical Delegation（分层委托）

```
┌─────────────────────────────────────────────┐
│              Main Agent Loop                 │
│  (RapidExecutionLoop with full tools)        │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │         DelegateTool                  │   │
│  │  LLM 决定是否 delegate 子任务         │   │
│  └──────────┬───────────────────────────┘   │
│             │                                │
│    ┌────────┴────────┐                       │
│    ▼                 ▼                       │
│ ┌─────────┐   ┌─────────┐                   │
│ │SubAgent1│   │SubAgent2│  ← 独立执行循环   │
│ │(隔离ctx) │   │(隔离ctx) │  ← 受限工具集    │
│ └────┬────┘   └────┬────┘                   │
│      │              │                        │
│      ▼              ▼                        │
│   Result1       Result2                      │
│      │              │                        │
│      └──────┬───────┘                        │
│             ▼                                │
│     主 Agent 继续执行                         │
└─────────────────────────────────────────────┘
```

**关键原则**：
- Sub-Agent 通过 **Tool** 暴露给主 Agent（`DelegateTool`）
- Sub-Agent 拥有**独立的 message history**（内存模式，V1 不持久化到 DB）
- 主 Agent **只看到 Sub-Agent 的最终结果**，不看到中间过程
- Sub-Agent 拥有**受限工具集**（不能 delegate、不能 plan、不能 browser）

### 2.2 与 OpenCode 模式的对比

| 维度 | OpenCode 风格 | 本设计方案 |
|------|--------------|-----------|
| 调度方式 | `task` tool 同步调用 | `DelegateTool` 同步调用 |
| Sub-Agent 载体 | 内存中的独立执行上下文 | 内存模式（不持久化，与 tool call 同级） |
| Context 策略 | 隔离 context + 结果摘要 | 隔离 context + 最终结果返回 |
| 工具集裁剪 | 受限工具集 | 受限工具集（`sub_agent_tools`） |
| 取消机制 | 超时取消 | 步数限制 + 超时取消 |
| 递归防护 | 不允许递归 delegate | `delegate` 不在 `sub_agent_tools` 中 |

---

## 3. 架构决策

### 3.1 工具注册：共享 ToolRegistry + 工具子集屏蔽

**决策**: Sub-agent 复用主 agent 的 `ToolRegistry`，通过 `ToolSetConfig.sub_agent_tools` frozenset 屏蔽工具。

**理由**:
- 现有 `ToolSetConfig` 已有 `exploration_tools` 和 `plan_mode_tools` 两个 frozenset
- `RuntimeToolDefinitions._allowed_tool_names()` 已实现按 context 过滤工具的逻辑
- 只需新增 `sub_agent_tools` frozenset 即可复用整个机制

**实现方式**:
```python
@dataclass(frozen=True)
class ToolSetConfig:
    # ... 现有字段 ...
    sub_agent_tools: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "file", "grep", "glob", "edit", "shell",
            "session_recall", "working_memory_update",
        })
    )
```

### 3.2 执行模型：同步阻塞

**决策**: Parent turn 在 `DelegateTool.execute()` 中同步等待 sub-agent 完成。

**理由**:
- `RapidExecutionLoop` 是同步阻塞的 while 循环
- `AgentService._run_turn()` 在线程中运行，同步等待不会阻塞事件循环
- 最简实现，避免引入异步编排复杂度

**限制**: Parent agent 在等待期间无法做其他工作。这是 V1 的有意简化。

### 3.3 Context 隔离策略（V1 内存模式）

**决策**: Sub-agent 拥有独立的 message history（内存），不写入 DB。

**实现**:
```
Sub-Agent 内存中的 messages:
├── [system]  sub-agent 专用 system prompt（含 task 描述）
├── [user]    task + context
├── [assistant/tool_calls] ... 中间执行过程 ...
└── [assistant] 最终结果
```

**优势**:
- 不需要 DB schema 变更
- Sub-agent 的中间过程完全隔离，主 Agent 只看到结果
- 实现最简，可快速验证核心逻辑
- 与 shell/file edit 等工具同级——中间过程不持久化，结果存在 parent 历史中

### 3.4 工具集对比

| 工具 | Parent Agent | Sub-Agent (默认) | 说明 |
|------|-------------|-----------------|------|
| file | ✅ | ✅ | 读写文件 |
| grep | ✅ | ✅ | 搜索 |
| glob | ✅ | ✅ | 文件匹配 |
| edit | ✅ | ✅ | 编辑文件 |
| shell | ✅ | ✅ | 执行命令 |
| session_recall | ✅ | ✅ | 会话记忆 |
| working_memory_update | ✅ | ✅ | 工作记忆 |
| skill | ✅ | ❌ | Sub-agent 不需要 |
| plan | ✅ | ❌ | Sub-agent 不需要 |
| memory | ✅ | ❌ | Sub-agent 不需要 |
| delegate | ✅ | ❌ | **防递归** |
| browser | ✅ | ❌ | V2 再开放 |

### 3.5 错误处理

- Sub-agent 执行失败 → `ToolResult(success=False, output=error_msg)`
- Parent agent 收到失败的 tool result，可自行决定重试或换策略
- 不自动重试——由 parent agent 的 LLM 推理决定
- 超步限制：默认 max_steps=10，超步自动 fail

---

## 4. 分阶段实施计划

### Phase 1: 核心 Sub-Agent 机制 + 前端 UI

**目标**: 实现完整的 Sub-Agent 能力——后端核心机制 + 前端展示，无 DB schema 变更。

#### 4.1.1 SubAgentRunner

**文件**: `backend/app/execution/sub_agent_runner.py`（新建）

```python
class SubAgentRunner:
    """在当前进程内运行一个隔离的 sub-agent 执行循环（内存模式）"""

    def __init__(
        self,
        llm_service: LLMProviderService,
        tool_registry: ToolRegistry,
        tool_set_config: ToolSetConfig,
    ):
        self.llm_service = llm_service
        self.tool_registry = tool_registry
        self.tool_set_config = tool_set_config

    def run(
        self,
        task: str,
        context: str = "",
        parent_context: str = "",
        max_steps: int = 10,
        session_id: str | None = None,
        project_id: str | None = None,
        preferred_provider_id: str | None = None,
        preferred_model_id: str | None = None,
    ) -> SubAgentResult:
        """
        同步执行 sub-agent turn（纯内存，不写 DB）。

        1. 构建受限 ToolRegistry（从 sub_agent_tools 过滤）
        2. 构建 sub-agent messages（system + user）
        3. 构建 LoopContext
        4. 运行 RapidExecutionLoop（最多 max_steps 轮）
        5. 收集最终 assistant message 作为输出
        6. 返回 SubAgentResult
        """
```

**核心实现逻辑**:
```python
def run(self, task, context, max_steps, ...):
    # 1. 构建受限工具集
    allowed_tools = self._build_restricted_tool_set()

    # 2. 构建隔离的 messages
    system_prompt = self._build_system_prompt(task, context, max_steps)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    # 3. 构建 LoopContext（使用隔离的 messages）
    loop_context = LoopContext(
        session_id=session_id,
        project_id=project_id,
        messages=messages,
        working_memory={},  # 隔离，不继承 parent
        tool_definitions=allowed_tools,
    )

    # 4. 运行 RapidExecutionLoop
    result = self._run_rapid_loop(loop_context, max_steps)

    # 5. 提取最终输出
    return SubAgentResult(
        success=result.success,
        output=self._extract_final_output(result),
        steps_taken=result.steps_taken,
        duration_ms=result.duration_ms,
    )
```

#### 4.1.2 SubAgentResult

```python
@dataclass
class SubAgentResult:
    success: bool
    output: str           # 最终文本输出
    steps_taken: int      # 执行步数
    error: str | None = None
    duration_ms: int = 0
```

#### 4.1.3 DelegateTool

**文件**: `backend/app/tools/delegate_tool.py`（新建）

```python
class DelegateTool(BaseTool):
    name = "delegate"
    description = (
        "将子任务委托给独立的 sub-agent 执行。"
        "Sub-agent 在隔离上下文中运行，完成后将结果返回给你。"
        "适用于需要深度专注的子任务。"
    )

    def get_schema(self) -> dict:
        return {
            "name": "delegate",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "要委托给子代理的任务描述",
                    },
                    "context": {
                        "type": "string",
                        "description": "传递给子代理的额外上下文信息（可选）",
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "子代理最大执行步数（默认 10）",
                        "default": 10,
                    },
                },
                "required": ["task"],
            },
        }

    def execute(
        self,
        task: str,
        context: str = "",
        max_steps: int = 10,
        **kwargs,
    ) -> ToolResult:
        """
        1. 构建 SubAgentRunner
        2. 同步运行 sub-agent
        3. 返回 ToolResult（包含 sub-agent 最终输出）
        """
        runner = SubAgentRunner(
            llm_service=self.llm_service,
            tool_registry=self.tool_registry,
            tool_set_config=self.tool_set_config,
        )

        result = runner.run(
            task=task,
            context=context,
            max_steps=max_steps,
            session_id=self.session_id,
            project_id=self.project_id,
            preferred_provider_id=self.preferred_provider_id,
            preferred_model_id=self.preferred_model_id,
        )

        if result.success:
            return ToolResult(
                output=f"[Sub-Agent 完成] {result.output}",
                success=True,
            )
        else:
            return ToolResult(
                output=f"[Sub-Agent 失败] {result.error}",
                success=False,
            )
```

#### 4.1.4 ToolSetConfig 扩展

**文件**: `backend/app/execution/runtime_tool_definitions.py`

```python
@dataclass(frozen=True)
class ToolSetConfig:
    # ... 现有字段 ...
    sub_agent_tools: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "file", "grep", "glob", "edit", "shell",
            "session_recall", "working_memory_update",
        })
    )
```

#### 4.1.5 AgentService 集成

**文件**: `backend/app/services/agent_service.py`

在 turn 初始化时注册 `DelegateTool`：

```python
def _ensure_delegate_tool(self, session: Session) -> None:
    """注册 delegate tool（如果 session 允许 sub-agent）"""
    if self.tool_registry.get("delegate") is None:
        delegate_tool = DelegateTool(
            llm_service=self.llm_provider_service,
            tool_registry=self.tool_registry,
            tool_set_config=self.tool_set_config,
            session_id=session.id,
            project_id=session.project_id,
            preferred_provider_id=session.preferred_provider_id,
            preferred_model_id=session.preferred_model_id,
        )
        self.tool_registry.register(delegate_tool)
```

#### 4.1.6 Sub-agent System Prompt 模板

```
你是 ReflexionOS 的子代理（Sub-Agent），由主代理委托执行特定任务。

## 你的任务
{task}

{context_section}

## 约束
- 你只能使用提供的工具完成任务
- 完成后，在最终回复中清晰总结结果
- 不要执行任务范围之外的操作
- 最大执行步数：{max_steps}
```

#### 4.1.7 前端 Delegate UI

**文件**: `frontend/src/components/` 下新增相关组件

**设计思路**: Sub-agent 的执行通过主 Agent 的 `tool_call`/`tool_result` SSE 事件传递到前端，前端只需识别 `delegate` 工具调用并以专属 UI 展示。

**核心组件**:
- `DelegateToolCall` — 当消息中 tool_call 的 toolName 为 `delegate` 时，以折叠卡片形式展示：
  - 📋 **Task**: 委托任务描述（始终可见）
  - ⏳ 执行中状态指示器（tool_result 未返回时显示 spinner）
  - ✅/❌ **Result**: 执行结果（默认折叠，可展开查看完整输出）
- 通过 `delegate` tool_call 后是否有对应的 `tool_result` 判断执行状态
- 结果卡片支持代码高亮（sub-agent 输出可能包含代码）

**展示规则**:
- delegate tool_call 无对应 result → 显示 "正在执行子任务: {task}" + spinner
- delegate tool_call 有 result → 显示 "子任务完成" / "子任务失败" + 可展开结果
- 默认折叠中间过程，用户可手动展开查看

---

### Phase 2: 高级能力

**目标**: 并行 sub-agent、超时取消等高级特性。

#### 4.2.1 并行 Sub-Agent

当主 Agent 一次性调用多个 `delegate` tool call 时（LLM 返回多个 tool_calls），支持并行执行：

```python
# 在 ToolCallExecutor 中
if multiple_delegate_calls:
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(delegate_tool.execute, **args) for args in calls]
        results = [f.result() for f in futures]
```

#### 4.2.2 Sub-Agent 超时取消

- 全局超时：单个 sub-agent 最大执行时间（如 120s），超时自动中断
- 用户取消：前端取消按钮 → 后端设置 cancel flag → SubAgentRunner 在下一 step 检查并退出

#### 4.2.3 DAG 依赖（可选）

允许 sub-agent 之间声明依赖关系，支持拓扑排序并行执行。这是高级特性，按需实现。

---

## 5. 实施顺序与依赖

```
Phase 1 (核心机制 + 前端 UI) ─────────────────────→ 可独立交付，完整可用
  │
  ├── SubAgentRunner (内存模式)
  ├── DelegateTool
  ├── ToolSetConfig.sub_agent_tools
  ├── AgentService 集成
  └── 前端 DelegateToolCall 组件
  │
  ▼
Phase 2 (高级能力) ──────────────────────────────→ 按需扩展
  │
  ├── 并行 Sub-Agent
  ├── 超时取消
  └── DAG 依赖（可选）
```

**预计工作量**:
- **Phase 1**: ~3-4 天（后端核心 + 前端 UI，完整交付）
- **Phase 2**: ~2-3 天（高级特性，按需实现）
- **总计**: ~5-7 天

---

## 6. 测试策略

### 6.1 Phase 1 单元测试
- `SubAgentRunner` — mock LLM，验证隔离执行流程
- `DelegateTool` — mock runner，验证参数传递和结果处理
- 工具集屏蔽验证 — sub-agent 中不出现 `delegate`、`plan` 等工具

### 6.2 Phase 1 集成测试
- Parent agent 调用 `delegate` → sub-agent 执行 → 结果返回 parent
- Sub-agent 工具集屏蔽验证（delegate tool 不出现在 sub-agent 中）
- Sub-agent 超步限制验证

### 6.3 Phase 1 前端测试
- DelegateToolCall 组件：spinner 状态 → 完成/失败状态切换
- 折叠/展开交互
- 长输出截断与代码高亮

---

## 7. 与原 Spec 的差异

| 原 Spec 设计 (2026-06-15) | 本设计方案 | 原因 |
|--------------------------|-----------|------|
| Sub-agent 拥有独立 DB conversation | 内存模式，不持久化 | Sub-agent 本质是重型 tool call，中间过程无需 DB |
| Session parent/child + depth 字段 | 不需要 | 内存模式不依赖 DB 关系 |
| `SubAgentToolSetConfig` 独立类 | 复用 `ToolSetConfig` + `sub_agent_tools` frozenset | 与现有 exploration/plan 模式一致 |
| 完整的 delegate SSE 事件流 | 通过 tool_call/tool_result 间接可见 | 同步执行模型下，中间事件价值有限 |
| 前端并行执行面板 | Phase 2 再做 | V1 同步执行，无并行场景 |
| 三阶段实施（核心→持久化→高级） | 两阶段（核心+UI→高级） | 持久化非必要，减少实施周期 |
| 多模态需独立实现 | 已完成 | 代码库已完整实现 |
| 拓扑排序并行 delegate | Phase 2 可选 | 高级特性，按需实现 |

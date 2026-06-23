# Sub-Agent 实现计划

> **设计文档**: `docs/superpowers/specs/2026-06-23-sub-agent-revised-design.md`
> **状态**: 🚧 进行中
> **开始时间**: 2026-06-23

## 总体架构

将 sub-agent 实现为 **重型 tool call**：主 Agent 通过 `delegate` 工具调用 SubAgentRunner，Runner 在内存中执行独立 Agent Loop，返回结果后主 Agent 继续执行。

**核心文件结构**:
```
backend/app/
├── agents/
│   └── sub_agent_runner.py        # NEW — SubAgentRunner 内存执行引擎
├── tools/
│   ├── delegate_tool.py           # NEW — DelegateTool 工具定义
│   └── registry.py                # MODIFY — 添加 list_tools_excluding 方法
├── execution/
│   ├── runtime_tool_definitions.py # MODIFY — ToolSetConfig 添加 sub_agent_tools 字段
│   └── tool_call_executor.py      # MODIFY — 注入 DelegateTool
├── services/
│   └── agent_service.py           # MODIFY — 传递 ToolSetConfig 到执行链路

frontend/src/components/
└── workspace/
    └── DelegateToolCall.tsx        # NEW — delegate 专属 UI 组件
```

---

## Phase 1: 核心机制 + 前端 UI

### Step 1: SubAgentRunner 内存执行引擎

**文件**: `backend/app/agents/sub_agent_runner.py` (新建)

**职责**: 在内存中运行一个完整的 Agent Loop（不走 Task → Execution → SSE 链路），复用 `run_agent_loop_sync()` 实现。

**关键设计**:
```python
class SubAgentResult:
    output: str
    steps_taken: int
    tool_calls: list[dict]
    total_usage: LLMUsage

class SubAgentRunner:
    def __init__(
        self,
        db_session: AsyncSession,
        user_id: str,
        project_id: str,
        task: str,
        input_data: dict | None = None,
        expected_output: str | None = None,
        preferred_provider_id: str | None = None,
        preferred_model_id: str | None = None,
        parent_step_budget: int = 100,
        parent_llm_config: LLMModelConfig | None = None,
        parent_provider_id: str | None = None,
    ): ...

    async def run(self) -> SubAgentResult:
        # 1. 查询 db 获取 provider/model（若未提供则用 project 默认）
        # 2. 构建 ToolSetConfig(mode="sub_agent", sub_agent_tools=frozenset({"delegate"}))
        # 3. 构建 tool_set + system_prompt
        # 4. 构建 initial messages（system + user task）
        # 5. 调用 run_agent_loop_sync(
        #       messages, tools, tool_set, config, step_budget,
        #       llm_config, provider, db_session, session_id, logger,
        #       temperature=parent.temperature * 0.6,
        #       stream=False
        #     )
        # 6. 提取最后一条 assistant 消息作为 output
        # 7. 返回 SubAgentResult
```

**依赖**:
- `backend/app/llm/run_loop.py` — `run_agent_loop_sync()`
- `backend/app/execution/runtime_tool_definitions.py` — `RuntimeToolDefinitions`, `ToolSetConfig`
- `backend/app/execution/loop_message_builder.py` — `LoopContext`, `MessageBuilder`, `EventSink`
- `backend/app/llm/types.py` — `LLMModelConfig`, `LLMUsage`

**注意事项**:
- 需要创建一个 `NoOpEventSink` 替代 SSE EventSink（sub-agent 不广播事件）
- 需要创建一个简单的 `InMemoryLoopContext` 替代 `DBLoopContext`
- temperature 设为 parent 的 60%（更确定性）
- tool_set 中包含 `sub_agent_tools=frozenset({"delegate"})` 防止递归

**验证**: 单元测试 mock LLM，验证执行流程、工具集屏蔽、超步限制

---

### Step 2: ToolSetConfig 扩展 + ToolRegistry 方法

#### 2a: ToolSetConfig 添加 sub_agent_tools 字段

**文件**: `backend/app/execution/runtime_tool_definitions.py`

**修改**: `ToolSetConfig` dataclass 添加：
```python
sub_agent_tools: frozenset[str] = field(default_factory=frozenset)
```

#### 2b: ToolRegistry.list_tools_excluding 方法

**文件**: `backend/app/tools/registry.py`

**修改**: 新增方法：
```python
def list_tools_excluding(self, exclude: frozenset[str]) -> list[BaseTool]:
    """返回排除指定工具名后的所有工具列表"""
    return [t for t in self._tools.values() if t.name not in exclude]
```

**验证**: 单元测试验证工具过滤

---

### Step 3: DelegateTool 工具定义

**文件**: `backend/app/tools/delegate_tool.py` (新建)

**职责**: 主 Agent 调用 sub-agent 的入口工具。

```python
class DelegateTool(BaseTool):
    name = "delegate"
    description = "委托一个独立子 Agent 执行子任务..."
    category = ToolCategory.AUTOMATION
    requirements = ToolRequirements(approval=ToolApprovalLevel.NEVER)
    parameters = ParametersSchema(
        properties={
            "task": {"type": "string", "description": "委托任务描述"},
            "input": {"type": "object", "description": "附加输入数据（可选）"},
            "expected_output": {"type": "string", "description": "预期输出描述（可选）"},
        },
        required=["task"],
    )

    def __init__(self, runner_factory: Callable[..., SubAgentRunner]):
        super().__init__()
        self._runner_factory = runner_factory

    async def execute(self, task, input=None, expected_output=None, **kwargs) -> ToolResult:
        runner = self._runner_factory(task=task, input_data=input, expected_output=expected_output)
        result = await runner.run()
        # 构建 ToolResult：output 包含 sub-agent 输出
```

**关键**: runner_factory 在 RuntimeToolDefinitions 中创建，注入当前 execution 的 user_id、project_id、db_session、llm_config 等上下文。

**验证**: 单元测试 mock runner，验证参数传递和结果处理

---

### Step 4: RuntimeToolDefinitions 注入 DelegateTool

**文件**: `backend/app/execution/runtime_tool_definitions.py`

**修改**: `_collect_tools_for_mode()` 方法中：

```python
# 现有逻辑：根据 mode 获取工具列表
if config.mode == "sub_agent":
    tools = self._registry.list_tools_excluding(config.sub_agent_tools)
else:
    tools = self._registry.list_tools_for_mode(config)

# 新增：非 sub_agent 模式注入 delegate tool
if config.mode != "sub_agent" and delegate_tool is not None:
    tools.append(delegate_tool)
```

**Runner Factory 创建**:
- 在 `ToolCallExecutor` 中创建 `SubAgentRunner` 的 factory 闭包
- 闭包捕获：`db_session`, `user_id`, `project_id`, `parent_llm_config`, `parent_provider_id`
- 传递到 `RuntimeToolDefinitions.create_tools()` 作为可选参数

**验证**: 集成测试验证 delegate 工具出现在主 Agent 工具集中，不出现在 sub-agent 中

---

### Step 5: ToolCallExecutor 接收 ToolSetConfig

**文件**: `backend/app/execution/tool_call_executor.py`

**修改**:
```python
class ToolCallExecutor:
    def __init__(
        self,
        db_session: AsyncSession,
        tool_set: ToolSet,
        approval_manager: ApprovalManager | None = None,
        tool_set_config: ToolSetConfig | None = None,  # NEW
    ):
        self._runtime_defs = RuntimeToolDefinitions()
        # 创建 delegate_tool factory（如果 tool_set_config 不是 sub_agent 模式）
        delegate_tool = self._build_delegate_tool(tool_set_config, db_session)
        self._tools_by_name = self._runtime_defs.create_tools(
            tool_set, tool_set_config, delegate_tool=delegate_tool
        )
```

**验证**: 现有测试不回归

---

### Step 6: AgentService 传递 ToolSetConfig

**文件**: `backend/app/services/agent_service.py`

**修改**:

#### 6a: `execute_agent_background()` 和 `resume_after_approval()`

在构建 `tool_set` 后，构建 `ToolSetConfig`：
```python
tool_set_config = ToolSetConfig.from_json(
    {
        "mode": tool_set.mode,
        "enabled": list(tool_set.enabled),
        "disabled": list(tool_set.disabled),
    },
    default_exploration=RuntimeToolDefinitions.EXPLORATION_TOOL_NAMES,
    default_plan=RuntimeToolDefinitions.PLAN_TOOL_NAMES,
)
```

传递到 `_run_agent_loop()`。

#### 6b: `_run_agent_loop()` 签名扩展

```python
async def _run_agent_loop(
    self,
    ...,
    tool_set_config: ToolSetConfig | None = None,  # NEW
) -> None:
    tool_executor = ToolCallExecutor(
        db_session=self._db,
        tool_set=tool_set,
        approval_manager=approval_manager,
        tool_set_config=tool_set_config,  # NEW
    )
```

**验证**: 现有 E2E 测试不回归

---

### Step 7: 前端 DelegateToolCall 组件

**文件**: `frontend/src/components/workspace/DelegateToolCall.tsx` (新建)

**职责**: 当 tool_call 的 toolName 为 `delegate` 时，以折叠卡片形式展示。

**设计**:
```tsx
export function DelegateToolCall({
  toolCall,
  toolResult,
}: {
  toolCall: ToolCall
  toolResult?: ToolResult
}) {
  // 解析 task/input/expected_output 从 toolCall.arguments
  // 无 toolResult → "正在执行子任务: {task}" + spinner
  // 有 toolResult 且 isError → "子任务失败" + 可展开错误
  // 有 toolResult 且非 error → "子任务完成" + 可展开输出
}
```

**集成点**: 在 `ToolTraceCard.tsx` 或 `transcriptItems.ts` 的 `buildToolTraceDetail()` 中，
当 `toolName === "delegate"` 时返回自定义 detail，前端使用 `DelegateToolCall` 组件渲染。

**验证**: 组件测试、E2E 测试

---

## Phase 2: 高级能力

### Step 8: 并行 Sub-Agent

**前置条件**: Phase 1 完成

**修改文件**: `backend/app/execution/tool_call_executor.py`

**设计**: 当 LLM 返回多个 delegate tool_calls 时，使用 `asyncio.gather()` 并行执行：
```python
async def _process_delegate_calls_in_parallel(self, delegate_calls):
    tasks = [self._execute_delegate(call) for call in delegate_calls]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### Step 9: 超时取消

**修改文件**: `backend/app/agents/sub_agent_runner.py`

**设计**:
- 全局超时：`asyncio.wait_for(runner.run(), timeout=120)`
- 用户取消：通过 `ToolCallCancelled` 异常传播

### Step 10: DAG 依赖（可选）

允许 sub-agent 之间声明依赖关系，支持拓扑排序并行执行。

---

## 验证方案

### 后端验证
1. **SubAgentRunner 单元测试**: mock LLM，验证隔离执行流程、工具集屏蔽、超步限制
2. **DelegateTool 单元测试**: mock runner，验证参数传递和结果处理
3. **集成测试**: parent agent 调用 delegate → sub-agent 执行 → 结果返回 parent
4. **递归防护测试**: 验证 sub-agent 工具集中不包含 delegate
5. **Step 预算测试**: 验证 sub-agent 不超过 parent 的 step_budget

### 前端验证
1. **DelegateToolCall 组件测试**: spinner → 完成/失败状态切换、折叠/展开
2. **E2E 测试**: 完整 delegate 工具调用流程

### 回归验证
- 所有现有 backend 测试通过
- 所有现有 frontend 测试通过
- 现有 tool 调用行为不变（exploration/plan 模式不受影响）

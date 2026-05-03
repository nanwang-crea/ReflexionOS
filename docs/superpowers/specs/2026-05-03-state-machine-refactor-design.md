# RapidExecutionLoop 状态机重构设计

## 问题

`RapidExecutionLoop.run()` 当前存在三个结构性问题：

1. **隐式状态散落**：`has_executed_tools`、`consecutive_failures` 在 `self` 上（跨 run 污染），`turn_retries`、`step_num`、`state`、`response` 在局部变量上（生命周期不明确）。并发 run 会互相覆盖，debug 需要在 self 和局部变量之间跳。

2. **305 行单方法**：`run()` 包含 4 个状态阶段的全部逻辑，TOOL_EXECUTION 的审批子流程占 ~90 行全部内联。无法独立测试任何阶段。

3. **无扩展点**：if/elif 分支 + 局部变量，加新阶段需要在大方法里插入新分支，改动影响面大。

## 设计

### 文件结构

```
execution/
├── models.py              # +LoopPhase(str, Enum) +RuntimeState
├── approval_flow.py       # 新文件：ApprovalFlow + ApprovalResult
├── rapid_loop.py          # 重写：4 个 handler + 主循环
├── context_manager.py     # 不变
├── tool_call_executor.py  # 不变
├── ...其他不变
```

### 数据层

#### LoopPhase — 升级为 str, Enum

```python
from enum import Enum

class LoopPhase(str, Enum):
    """继承 str 保持与现有字符串比较兼容"""
    PLANNING = "planning"
    TOOL_EXECUTION = "tool_execution"
    ERROR_RECOVERY = "error_recovery"
    FINAL_SUMMARY = "final_summary"
    DONE = "done"
```

#### RuntimeState — 单次 run 的全部可变状态

```python
from dataclasses import dataclass, field
import asyncio

@dataclass
class RuntimeState:
    """单次 run 的可变状态快照 — handler 只操作这个对象"""

    phase: LoopPhase = LoopPhase.PLANNING
    step_num: int = 0
    turn_retries: int = 0
    consecutive_failures: int = 0
    has_executed_tools: bool = False

    # 跨阶段传递的 LLM 响应（PLANNING 写 → TOOL_EXECUTION 读）
    response: LLMResponse | None = None

    # 审批流（外部通过 ApprovalFlow.set_approval_result 写入）
    approval_resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_result: dict | None = None
```

`loop_result` 和 `context` 不收入 RuntimeState——它们是 handler 的入参，不是状态机内部状态。

### ApprovalFlow — 独立子模块

```python
# approval_flow.py

@dataclass
class ApprovalResult:
    approved: bool
    output: str | None = None
    error: str | None = None
    success: bool = False


class ApprovalFlow:
    """
    审批流 — 只负责等待/接收审批结果，返回结构化 ApprovalResult。

    不负责：tool 执行、状态转移、事件发送。
    """

    def __init__(self, emit: Callable[[str, dict], Awaitable[None]]):
        self._emit = emit
        self._resume_event: asyncio.Event = asyncio.Event()
        self._pending_result: dict | None = None

    def set_approval_result(self, result: dict | None) -> None:
        self._pending_result = result
        self._resume_event.set()

    async def wait_for_approval(self, step: LoopStep, run_id: str) -> ApprovalResult:
        await self._resume_event.wait()
        result = self._pending_result
        self._pending_result = None
        self._resume_event = asyncio.Event()

        if result is not None:
            return ApprovalResult(
                approved=True,
                output=result.get("output"),
                error=result.get("error"),
                success=result.get("success", False),
            )
        else:
            return ApprovalResult(approved=False)
```

### Phase Handler — 统一签名

```python
from typing import Protocol

class PhaseHandler(Protocol):
    """阶段处理器协议"""
    async def __call__(
        self,
        context: LoopContext,
        result: LoopResult,
        rt: RuntimeState,
    ) -> LoopPhase:
        """执行当前阶段逻辑，返回下一阶段"""
        ...
```

#### _handle_planning

```python
async def _handle_planning(
    self, context: LoopContext, result: LoopResult, rt: RuntimeState
) -> LoopPhase:
    rt.response = await self._call_llm(context)

    if rt.response.has_tool_calls:
        rt.turn_retries = 0
        return LoopPhase.TOOL_EXECUTION

    if rt.has_executed_tools:
        if rt.response.has_content:
            result.status = LoopStatus.COMPLETED
            result.result = rt.response.content
            return LoopPhase.DONE
        else:
            return LoopPhase.FINAL_SUMMARY
    else:
        if rt.response.has_content:
            result.status = LoopStatus.COMPLETED
            result.result = rt.response.content
            return LoopPhase.DONE
        else:
            raise RuntimeError("模型未返回任何内容，也未发起工具调用")
```

#### _handle_tool_execution

```python
async def _handle_tool_execution(
    self, context: LoopContext, result: LoopResult, rt: RuntimeState
) -> LoopPhase:
    rt.step_num += 1

    for tool_call in rt.response.tool_calls:
        step = await self.tool_executor.execute(tool_call, context, rt.step_num)
        result.steps.append(step)
        context.add_step(step)

        if step.status == StepStatus.WAITING_FOR_APPROVAL:
            return await self._handle_approval(step, context, result, rt)

        if step.status == StepStatus.FAILED:
            rt.consecutive_failures += 1
            await self._emit("tool:error", {
                "tool_name": tool_call.name,
                "step_number": step.step_number,
                "tool_call_id": step.tool_call_id,
                "error": step.error,
                "duration": step.duration,
                "arguments": step.args,
            })
            if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                return LoopPhase.ERROR_RECOVERY
        else:
            rt.consecutive_failures = 0
            rt.has_executed_tools = True

    return LoopPhase.PLANNING
```

#### _handle_approval（审批子流程）

```python
async def _handle_approval(
    self,
    step: LoopStep,
    context: LoopContext,
    result: LoopResult,
    rt: RuntimeState,
) -> LoopPhase:
    # 1. 标记等待 + 发事件
    result.status = LoopStatus.WAITING_FOR_APPROVAL
    result.result = step.output
    await self._emit("run:waiting_for_approval", {
        "run_id": result.id,
        "approval_id": step.approval_id,
        "step_number": step.step_number,
        "tool_name": step.tool,
    })

    # 2. 等待审批（委托 ApprovalFlow）
    approval = await self.approval_flow.wait_for_approval(step, result.id)

    # 3. 根据结果做状态转移
    if approval.approved:
        result.status = LoopStatus.RESUMING
        tool_output = approval.output or approval.error or ""
        context.add_message("tool", content=tool_output, tool_call_id=step.tool_call_id)
        context.update_history(step, tool_output)
        step.status = StepStatus.SUCCESS if approval.success else StepStatus.FAILED
        step.output = approval.output
        step.error = approval.error
        step.duration = 0.0

        await self._emit("tool:result", {
            "tool_name": step.tool,
            "tool_call_id": step.tool_call_id,
            "step_number": step.step_number,
            "success": approval.success,
            "output": approval.output,
            "error": approval.error,
            "duration": 0.0,
        })
        await self._emit("run:resuming", {
            "run_id": result.id,
            "approval_id": step.approval_id,
            "execution_success": approval.success,
        })

        rt.has_executed_tools = True
        return LoopPhase.PLANNING
    else:
        step.status = StepStatus.FAILED
        step.error = "审批被拒绝"

        await self._emit("tool:error", {
            "tool_name": step.tool,
            "tool_call_id": step.tool_call_id,
            "step_number": step.step_number,
            "error": "审批被拒绝",
            "duration": 0.0,
            "arguments": step.args,
        })
        await self._emit("run:cancelled", {
            "status": LoopStatus.CANCELLED.value,
            "result": "审批被拒绝",
            "total_steps": len(result.steps),
        })

        result.status = LoopStatus.CANCELLED
        result.result = "审批被拒绝"
        return LoopPhase.DONE
```

#### _handle_error_recovery

```python
async def _handle_error_recovery(
    self, context: LoopContext, result: LoopResult, rt: RuntimeState
) -> LoopPhase:
    last_step = result.steps[-1] if result.steps else None
    if not last_step:
        return LoopPhase.FINAL_SUMMARY

    error_prompt = self.prompt_manager.get_error_prompt(
        error=last_step.error or "Unknown error",
        tool=last_step.tool,
        code_snippet="",
    )
    context.add_message("user", error_prompt)
    rt.consecutive_failures = 0
    rt.turn_retries += 1

    if rt.turn_retries > self.MAX_TURN_RETRIES:
        return LoopPhase.FINAL_SUMMARY
    return LoopPhase.PLANNING
```

#### _handle_final_summary

```python
async def _handle_final_summary(
    self, context: LoopContext, result: LoopResult, rt: RuntimeState
) -> LoopPhase:
    summary = await self._get_final_summary(context)
    result.result = summary
    result.status = LoopStatus.COMPLETED
    return LoopPhase.DONE
```

### run() 主循环

```python
async def run(self, task, project_path=None, run_id=None, created_at=None,
              seed_messages=None, supplemental_context=None, system_sections=None):
    start_time = time.time()
    loop_result = LoopResult(...)
    context = LoopContext.from_run_input(...)
    rt = RuntimeState()
    self._runtime = rt

    await self._emit("run:start", {"run_id": loop_result.id, "task": task})

    try:
        await self.initial_plan_bootstrapper.bootstrap(context)

        handlers: dict[LoopPhase, PhaseHandler] = {
            LoopPhase.PLANNING: self._handle_planning,
            LoopPhase.TOOL_EXECUTION: self._handle_tool_execution,
            LoopPhase.ERROR_RECOVERY: self._handle_error_recovery,
            LoopPhase.FINAL_SUMMARY: self._handle_final_summary,
        }

        while rt.phase != LoopPhase.DONE and rt.step_num < self.max_steps:
            handler = handlers[rt.phase]
            rt.phase = await handler(context, loop_result, rt)

        if rt.step_num >= self.max_steps and loop_result.status != LoopStatus.WAITING_FOR_APPROVAL:
            loop_result.status = LoopStatus.COMPLETED
            loop_result.result = loop_result.result or "执行完成（达到最大步数）"

    except asyncio.CancelledError:
        loop_result.status = LoopStatus.CANCELLED
        loop_result.result = loop_result.result or "执行已取消"
        await self._emit("run:cancelled", {...})

    except RetryExhaustedError as e:
        loop_result.status = LoopStatus.CANCELLED
        loop_result.result = "执行已取消：LLM 重试次数已达上限"
        await self._emit("run:cancelled", {...})

    except Exception as e:
        loop_result.status = LoopStatus.FAILED
        loop_result.result = f"执行异常: {str(e)}"
        await self._emit("run:error", {"error": str(e)})

    finally:
        self._runtime = None
        loop_result.total_duration = time.time() - start_time
        loop_result.completed_at = datetime.now()
        if loop_result.status not in {LoopStatus.CANCELLED, LoopStatus.WAITING_FOR_APPROVAL}:
            await self._emit("run:complete", {...})

    return loop_result
```

### 外部接口变更

```python
# set_approval_result 委托给 ApprovalFlow
def set_approval_result(self, result):
    if self._runtime is not None:
        self.approval_flow.set_approval_result(result)

# get_approval_resume_event 委托
def get_approval_resume_event(self):
    return self.approval_flow._resume_event
```

## 架构预留

当前实现为"handler 是普通 async 方法 + dict dispatch"。预留的扩展点（现在不实现）：

| 预留点 | 当前 | 未来 |
|--------|------|------|
| on_enter / on_exit 钩子 | 不实现 | Phase 类加 on_enter/on_exit 方法 |
| Guard condition | 不实现 | Phase 类加 can_enter(rt) 方法 |
| Transition table | dict dispatch | TransitionTable 类，注册 from→to→guard |
| 新 Phase 注册 | 加方法 + 加 dict entry | 继承 Phase 基类，自动注册 |

## 变量对照

| 之前 | 之后 |
|------|------|
| `state` 局部变量 | `rt.phase` |
| `step_num` 局部变量 | `rt.step_num` |
| `turn_retries` 局部变量 | `rt.turn_retries` |
| `self.has_executed_tools` | `rt.has_executed_tools` |
| `self.consecutive_failures` | `rt.consecutive_failures` |
| `self._approval_*` | `self.approval_flow.*` |
| `response` 局部变量（跨阶段隐式传递） | `rt.response`（显式） |
| 305 行 run() | ~50 行 run() + 4 个 handler + ApprovalFlow |

## 测试策略

- 现有 test_rapid_loop.py (979 行) 允许小幅调整 import
- ApprovalFlow 新增独立单测
- RuntimeState 新增独立单测
- Handler 可独立 mock 测试

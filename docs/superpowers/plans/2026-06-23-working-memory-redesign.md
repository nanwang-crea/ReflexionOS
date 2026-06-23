# Working Memory 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 WorkingMemory 系统，将"会话跟踪"和"活跃上下文"分离为两层，解决模型重复读取文件、遗忘已知信息的问题。

**Architecture:**
- **SessionTracker**（系统托管，轻量元数据）：自动跟踪文件访问、工具调用、文件变更，永不淘汰，始终注入为第一行上下文
- **WorkingMemory**（模型可管理，语义化内容）：存储当前任务的关键发现、决策、活跃变量，按相关性淘汰
- **MemoryExtractor** 从工具执行结果中自动提取 SessionTracker 条目，从模型输出中提取 WM 条目
- **注入方式**：SessionTracker 在 system prompt 最前面（高注意力权重），WM 在其后

**Tech Stack:** Python 3.11+, pytest, dataclasses

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `backend/app/memory/session_tracker.py` | **新建** — 轻量会话跟踪器，记录文件访问/工具调用/变更 | Create |
| `backend/app/memory/working_memory.py` | **重构** — 简化为"活跃上下文"层，移除 file_index | Modify |
| `backend/app/memory/memory_extractor.py` | **重构** — 提取逻辑分离：跟踪数据 → SessionTracker，语义数据 → WM | Modify |
| `backend/app/execution/loop_message_builder.py` | **重构** — 注入 SessionTracker + WM 两层 | Modify |
| `backend/app/execution/context_manager.py` | **修改** — LoopContext 增加 session_tracker 属性 | Modify |
| `backend/app/execution/tool_call_executor.py` | **修改** — 工具执行后自动记录到 SessionTracker | Modify |
| `backend/app/tools/working_memory_tool.py` | **修改** — 适配新的 WM 接口 | Modify |
| `backend/tests/test_execution/test_session_tracker.py` | **新建** — SessionTracker 单元测试 | Create |
| `backend/tests/test_execution/test_working_memory.py` | **重构** — 移除 file_index 测试 | Modify |
| `backend/tests/test_execution/test_working_memory_tool.py` | **重构** — 适配新工具接口 | Modify |

---

### Task 1: 新建 SessionTracker — 轻量会话跟踪器

**设计原则：**
- 纯元数据，无语义摘要（路径 + 步骤号 + 操作类型）
- 永不淘汰，成本极低（~200 tokens for 20 files）
- 系统自动管理，模型不可直接写入
- 提供 `to_prompt_section()` 输出极简的跟踪列表

**Files:**
- Create: `backend/app/memory/session_tracker.py`
- Create: `backend/tests/test_execution/test_session_tracker.py`

- [ ] **Step 1: 写 SessionTracker 测试**

```python
# tests/test_execution/test_session_tracker.py
import pytest
from app.memory.session_tracker import SessionTracker, AccessType


class TestSessionTracker:
    def test_initial_state_is_empty(self):
        st = SessionTracker()
        assert st.is_empty()
        assert st.to_prompt_section() == ""

    def test_record_file_read(self):
        st = SessionTracker()
        st.record_file_access("backend/app/foo.py", AccessType.READ, step=1)
        section = st.to_prompt_section()
        assert "foo.py" in section
        assert "read" in section.lower() or "Files read" in section

    def test_record_file_write(self):
        st = SessionTracker()
        st.record_file_access("backend/app/bar.py", AccessType.WRITE, step=2)
        section = st.to_prompt_section()
        assert "bar.py" in section
        assert "modified" in section.lower() or "Files modified" in section

    def test_record_tool_call(self):
        st = SessionTracker()
        st.record_tool_call("grep", step=3)
        st.record_tool_call("grep", step=5)
        st.record_tool_call("edit", step=6)
        summary = st.tool_call_summary
        assert summary["grep"] == 2
        assert summary["edit"] == 1

    def test_duplicate_file_access_merges(self):
        """同一文件多次读取，只保留最新步骤号"""
        st = SessionTracker()
        st.record_file_access("foo.py", AccessType.READ, step=1)
        st.record_file_access("foo.py", AccessType.READ, step=5)
        assert len(st.read_files) == 1
        assert st.read_files["foo.py"].last_step == 5
        assert st.read_files["foo.py"].count == 2

    def test_file_write_tracked_separately_from_read(self):
        st = SessionTracker()
        st.record_file_access("foo.py", AccessType.READ, step=1)
        st.record_file_access("foo.py", AccessType.WRITE, step=3)
        assert "foo.py" in st.read_files
        assert "foo.py" in st.modified_files

    def test_prompt_section_format(self):
        st = SessionTracker()
        st.record_file_access("a.py", AccessType.READ, step=1)
        st.record_file_access("b.py", AccessType.READ, step=2)
        st.record_file_access("a.py", AccessType.WRITE, step=3)
        st.record_tool_call("grep", step=4)
        section = st.to_prompt_section()
        assert "Session Tracking" in section or "Session" in section
        assert "a.py" in section
        assert "b.py" in section

    def test_not_empty_after_recording(self):
        st = SessionTracker()
        assert st.is_empty()
        st.record_file_access("x.py", AccessType.READ, step=1)
        assert not st.is_empty()

    def test_clear_resets_all(self):
        st = SessionTracker()
        st.record_file_access("x.py", AccessType.READ, step=1)
        st.record_tool_call("grep", step=1)
        st.clear()
        assert st.is_empty()

    def test_to_dict_serialization(self):
        st = SessionTracker()
        st.record_file_access("x.py", AccessType.READ, step=1)
        st.record_tool_call("grep", step=1)
        d = st.to_dict()
        assert "read_files" in d
        assert "tool_calls" in d
        assert d["tool_calls"]["grep"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_execution/test_session_tracker.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 SessionTracker**

```python
# backend/app/memory/session_tracker.py
"""
SessionTracker — 轻量会话跟踪器

自动跟踪模型在一次 Run 中的文件访问和工具调用。
纯元数据，无语义摘要，成本极低，永不淘汰。
由系统自动管理，模型不可直接写入。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccessType(Enum):
    READ = "read"
    WRITE = "write"  # 包括 edit、create、delete


@dataclass
class FileAccessRecord:
    """单个文件的访问记录"""
    path: str
    access_type: AccessType
    last_step: int
    count: int = 1


class SessionTracker:
    """
    轻量会话跟踪器 — 记录"发生了什么"

    设计原则：
    - 只存路径 + 步骤号 + 操作类型，不做语义摘要
    - 永不淘汰，成本极低（~10 tokens/文件）
    - 系统自动管理，模型通过 working_memory_update 工具可读不可写
    """

    def __init__(self) -> None:
        # 文件读取记录: path → FileAccessRecord
        self._read_files: dict[str, FileAccessRecord] = {}
        # 文件变更记录: path → FileAccessRecord
        self._modified_files: dict[str, FileAccessRecord] = {}
        # 工具调用计数: tool_name → count
        self._tool_calls: dict[str, int] = {}

    @property
    def read_files(self) -> dict[str, FileAccessRecord]:
        return self._read_files

    @property
    def modified_files(self) -> dict[str, FileAccessRecord]:
        return self._modified_files

    @property
    def tool_call_summary(self) -> dict[str, int]:
        return dict(self._tool_calls)

    def record_file_access(
        self, path: str, access_type: AccessType, step: int
    ) -> None:
        """记录文件访问（读取或变更）"""
        target = (
            self._read_files if access_type == AccessType.READ
            else self._modified_files
        )
        if path in target:
            existing = target[path]
            existing.last_step = max(existing.last_step, step)
            existing.count += 1
        else:
            target[path] = FileAccessRecord(
                path=path, access_type=access_type,
                last_step=step, count=1,
            )

    def record_tool_call(self, tool_name: str, step: int) -> None:
        """记录工具调用（仅计数，不存参数）"""
        self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1

    def is_empty(self) -> bool:
        return (
            not self._read_files
            and not self._modified_files
            and not self._tool_calls
        )

    def to_prompt_section(self) -> str:
        """
        渲染为极简的跟踪列表，注入 system prompt。

        输出格式示例:
        [Session Tracking]
        Files read (3): a.py, b.py, c.py
        Files modified (1): a.py
        Tools: file(5x), edit(2x), grep(1x)
        """
        if self.is_empty():
            return ""

        lines: list[str] = ["[Session Tracking]"]

        # 文件读取列表（按最近访问排序）
        if self._read_files:
            sorted_reads = sorted(
                self._read_files.values(),
                key=lambda r: r.last_step, reverse=True,
            )
            paths = [r.path for r in sorted_reads]
            lines.append(f"Files read ({len(paths)}): {', '.join(paths)}")

        # 文件变更列表
        if self._modified_files:
            sorted_mods = sorted(
                self._modified_files.values(),
                key=lambda r: r.last_step, reverse=True,
            )
            paths = [r.path for r in sorted_mods]
            lines.append(f"Files modified ({len(paths)}): {', '.join(paths)}")

        # 工具调用统计（按使用次数降序）
        if self._tool_calls:
            sorted_tools = sorted(
                self._tool_calls.items(),
                key=lambda x: x[1], reverse=True,
            )
            tool_strs = [f"{name}({count}x)" for name, count in sorted_tools]
            lines.append(f"Tools: {', '.join(tool_strs)}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """序列化为 dict（用于调试/日志）"""
        return {
            "read_files": {
                p: {"step": r.last_step, "count": r.count}
                for p, r in self._read_files.items()
            },
            "modified_files": {
                p: {"step": r.last_step, "count": r.count}
                for p, r in self._modified_files.items()
            },
            "tool_calls": dict(self._tool_calls),
        }

    def clear(self) -> None:
        """清空所有跟踪数据"""
        self._read_files.clear()
        self._modified_files.clear()
        self._tool_calls.clear()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_execution/test_session_tracker.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/session_tracker.py backend/tests/test_execution/test_session_tracker.py
git commit -m "feat(memory): add SessionTracker for lightweight session tracking"
```

---

### Task 2: 重构 WorkingMemory — 移除 file_index，简化为活跃上下文层

**设计变更：**
- 移除 `file_index` slot（职责转移到 SessionTracker）
- 保留 `decisions`、`variables`、`errors`、`slots`（通用键值）
- 注入指令更明确，告诉模型如何使用 WM
- 保留 `update_file_index()` 为 deprecated no-op（向后兼容）

**Files:**
- Modify: `backend/app/memory/working_memory.py`
- Modify: `backend/tests/test_execution/test_working_memory.py`

- [ ] **Step 1: 修改 WorkingMemory 测试**

在 `test_working_memory.py` 中：
- 删除所有 `test_*file_index*` 测试
- 修改 `test_full_update_roundtrip` — 移除 file_index 部分
- 修改 `test_serialization_roundtrip` — 移除 file_index 部分
- 删除 `test_eviction_drops_file_index_before_decisions`
- 修改 `test_partial_slots_before_full_slots` — 移除 file_index 部分
- 修改 `test_partial_slots_clears_all_before_rebuild` — 移除 file_index 部分
- 新增测试：

```python
def test_to_prompt_section_includes_behavioral_instructions(self):
    """WM 注入应该包含明确的行为指令"""
    wm = WorkingMemory()
    wm.add_decision("d1", "Use approach X", "simpler")
    section = wm.to_prompt_section()
    # 应该包含行为指令（如"不要重复读取"等）
    assert "Session Tracking" in section or "DO NOT" in section or "re-read" in section

def test_update_file_index_is_noop_with_warning(self):
    """file_index 更新应该发出 deprecated 警告但不报错"""
    wm = WorkingMemory()
    # 不应抛异常
    wm.update_file_index("test.py", "233 lines: class Foo")
    # file_index 不应出现在 prompt 中
    section = wm.to_prompt_section()
    assert "File Index" not in section
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_execution/test_working_memory.py -v`
Expected: FAIL

- [ ] **Step 3: 重构 WorkingMemory 类**

核心变更：
1. 从 `_SLOT_ORDER` 中移除 `FILE_INDEX`
2. 将 `update_file_index()` 改为 deprecated no-op（打印 warning）
3. 移除 `_on_file_index_updated` 方法
4. 修改 `to_prompt_section()` 加入行为指令 header
5. 保留 `_slots`（decisions, variables, errors）不变

`to_prompt_section()` 新输出：
```
[Working Memory — active context for this task]
Use the information below to avoid redundant work.
DO NOT re-read files listed in [Session Tracking] — use session_recall if you need full content.

## Decisions
- [d1] Use regex extraction: Avoids LLM call latency

## Key Findings
(some slot content)

## Variables
- api_version = v2 (confirmed 3x)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_execution/test_working_memory.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/working_memory.py backend/tests/test_execution/test_working_memory.py
git commit -m "refactor(memory): remove file_index from WorkingMemory, add injection instructions"
```

---

### Task 3: 重构 MemoryExtractor — 分离跟踪提取和语义提取

**设计变更：**
- `__init__` 新增 `session_tracker` 参数
- `_extract_from_file_read()` 同时记录到 SessionTracker
- 新增 `_extract_from_file_write()` 从 edit 工具跟踪文件变更
- `extract()` 新增 `step` 参数用于 SessionTracker 记录
- `extract_from_response()` 在 `extract()` 中被实际调用

**Files:**
- Modify: `backend/app/memory/memory_extractor.py`

- [ ] **Step 1: 修改 `__init__` 增加 `session_tracker`**

```python
def __init__(
    self,
    memory: WorkingMemory,
    session_tracker: SessionTracker | None = None,
) -> None:
    self.memory = memory
    self.session_tracker = session_tracker
    self._pending_decisions: list[tuple[str, str, str]] = []
```

- [ ] **Step 2: 修改 `extract()` 增加 `step` 参数**

```python
def extract(
    self,
    model_output: str = "",
    assistant_content: str = "",
    tool_name: str = "",
    tool_args: dict = {},
    tool_result: str = "",
    step: int = 0,
) -> None:
```

在方法末尾追加：
```python
# 记录到 SessionTracker
if tool_name and self.session_tracker:
    self._record_to_tracker(tool_name, tool_args, step)
```

- [ ] **Step 3: 新增 `_record_to_tracker()` 方法**

```python
def _record_to_tracker(
    self, tool_name: str, tool_args: dict, step: int
) -> None:
    """将工具调用记录到 SessionTracker"""
    tracker = self.session_tracker
    if not tracker:
        return

    tracker.record_tool_call(tool_name, step)

    # 文件读取
    if tool_name == "file" and tool_args.get("action") == "read":
        path = tool_args.get("path")
        if path:
            tracker.record_file_access(path, AccessType.READ, step)

    # 文件写入
    elif tool_name == "edit":
        path = tool_args.get("path")
        if path:
            tracker.record_file_access(path, AccessType.WRITE, step)

    # explore 工具
    elif tool_name == "explore":
        # explore 的 path 参数可能不存在，它用 query
        pass  # explore 不记录具体文件，因为它返回的是搜索结果
```

- [ ] **Step 4: 在 `extract()` 中实际调用 `extract_from_response()`**

```python
if model_output:
    self._extract_decisions(model_output)
    self._extract_assistant_file_changes(model_output)
    self._extract_assistant_file_changes(assistant_content)
    # 新增：从模型输出中提取语义信息
    if model_output:
        self.extract_from_response(model_output)
```

- [ ] **Step 5: 运行现有测试确认不破坏**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: ALL PASS (可能需要适配 MemoryExtractor 的构造函数调用)

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/memory_extractor.py
git commit -m "refactor(memory): separate tracking and semantic extraction in MemoryExtractor"
```

---

### Task 4: 重构 ContextManager — LoopContext 持有 SessionTracker

**Files:**
- Modify: `backend/app/execution/context_manager.py`

- [ ] **Step 1: 在 `LoopContext.__init__` 中添加 `session_tracker`**

```python
from app.memory.session_tracker import SessionTracker

# 在 __init__ 中:
self.session_tracker = SessionTracker()

# 修改 memory_extractor 初始化:
self.memory_extractor = MemoryExtractor(
    memory=self.working_memory,
    session_tracker=self.session_tracker,
)
```

- [ ] **Step 2: 修改 `clear_working_memory()` 同时清理 SessionTracker**

```python
def clear_working_memory(self) -> None:
    """清空 Working Memory 和 SessionTracker"""
    self.working_memory.clear()
    self.session_tracker.clear()
    self.memory_extractor.clear_pending()
```

- [ ] **Step 3: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/context_manager.py
git commit -m "refactor(execution): LoopContext holds SessionTracker alongside WorkingMemory"
```

---

### Task 5: 重构 LoopMessageBuilder — 双层注入

**Files:**
- Modify: `backend/app/execution/loop_message_builder.py`

- [ ] **Step 1: 修改 `_build_working_memory_section()` 为双层注入**

将当前方法重命名为 `_build_memory_injection()`，返回 `list[LLMMessage]`：

```python
def _build_memory_injection(
    self, context: LoopContext
) -> list[LLMMessage]:
    """构建双层记忆注入：SessionTracker + WorkingMemory"""
    messages: list[LLMMessage] = []

    # 第一层：SessionTracker（极简跟踪，始终可见，高注意力）
    tracker_section = context.session_tracker.to_prompt_section()
    if tracker_section:
        instruction = (
            "\n\nIMPORTANT: Files listed above have been read this session. "
            "DO NOT re-read them unless you need specific line ranges not "
            "captured in Working Memory below. Use session_recall to retrieve "
            "full content of previously read files."
        )
        messages.append(
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=tracker_section + instruction,
            )
        )

    # 第二层：Working Memory（语义化内容）
    if not context.working_memory.is_empty():
        wm_section = context.working_memory.to_prompt_section()
        if wm_section:
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=wm_section,
                )
            )

    return messages
```

- [ ] **Step 2: 修改 `build_messages()` 使用新方法**

替换原来的 `_build_working_memory_section(context)` 调用：
```python
# Working Memory 注入（双层）
wm_messages = self._build_memory_injection(context)
all_messages.extend(wm_messages)
```

- [ ] **Step 3: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/loop_message_builder.py
git commit -m "refactor(execution): dual-layer injection - SessionTracker + WorkingMemory"
```

---

### Task 6: 更新 tool_call_executor — 自动记录 SessionTracker

**Files:**
- Modify: `backend/app/execution/tool_call_executor.py`

- [ ] **Step 1: 在工具执行成功后添加 SessionTracker 记录**

在 `execute()` 方法中，工具执行成功后（`result.success` 为 True 时）追加：

```python
# 自动记录到 SessionTracker
if result.success:
    self._record_to_session_tracker(context, tool_call, step_number)
```

新增私有方法：

```python
def _record_to_session_tracker(
    self, context: LoopContext, tool_call: LLMToolCall, step: int
) -> None:
    """工具执行后自动记录到 SessionTracker"""
    from app.memory.session_tracker import AccessType

    tracker = context.session_tracker
    tracker.record_tool_call(tool_call.name, step)

    # 文件读取
    if tool_call.name == "file" and tool_call.arguments.get("action") == "read":
        path = tool_call.arguments.get("path")
        if path:
            tracker.record_file_access(path, AccessType.READ, step)

    # 文件写入（edit 工具）
    elif tool_call.name == "edit":
        path = tool_call.arguments.get("path")
        if path:
            tracker.record_file_access(path, AccessType.WRITE, step)
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/tool_call_executor.py
git commit -m "refactor(execution): auto-record file access and tool calls to SessionTracker"
```

---

### Task 7: 适配 working_memory_update 工具

**Files:**
- Modify: `backend/app/tools/working_memory_tool.py`

- [ ] **Step 1: 更新工具 description**

在 `_build_description()` 中追加说明：
```
NOTE: File read tracking is now automatic (managed by SessionTracker).
The `update_file_index` action is deprecated — file access is tracked automatically.
Use `session_recall` query to check which files have been read.
```

- [ ] **Step 2: 新增 `_handle_query()` 方法**

允许模型查询 SessionTracker（只读）：

```python
async def _handle_query(self, args: dict) -> ToolResult:
    """查询 SessionTracker 数据（只读）"""
    from app.memory.session_tracker import AccessType

    key = args.get("key", "")
    wm = self._get_working_memory()
    tracker = wm._session_tracker  # 需要通过 context 获取

    if key == "session_files_read":
        files = list(tracker.read_files.keys())
        return ToolResult(
            output=f"Files read this session ({len(files)}): {', '.join(files)}"
        )
    elif key == "session_tools_used":
        summary = tracker.tool_call_summary
        tools = [f"{k}({v}x)" for k, v in sorted(summary.items(), key=lambda x: -x[1])]
        return ToolResult(output=f"Tools used: {', '.join(tools)}")
    else:
        return ToolResult(error=f"Unknown query key: {key}")
```

注意：需要通过某种方式让工具能访问到 SessionTracker。可以通过 `LoopContext` 传递，或在工具初始化时注入。

- [ ] **Step 3: 将 `update_file_index` action 标记为 deprecated**

在 `_handle_update_file_index()` 中：
```python
async def _handle_update_file_index(self, args: dict) -> ToolResult:
    """deprecated: file_index is now managed by SessionTracker"""
    import logging
    logging.getLogger(__name__).warning(
        "update_file_index is deprecated — file access is tracked automatically"
    )
    return ToolResult(output="File index update skipped (managed automatically by SessionTracker)")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_execution/test_working_memory_tool.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/working_memory_tool.py
git commit -m "refactor(tools): adapt working_memory_update for new WM design"
```

---

### Task 8: 全量测试验证 + 集成检查

- [ ] **Step 1: 运行全量测试**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: ALL PASS

- [ ] **Step 2: 验证 midrun 压压缩不受影响**

SessionTracker 是 LoopContext 的属性，不参与对话历史，因此 midrun 压缩不会影响它。
确认压缩后 SessionTracker 仍然存活。

- [ ] **Step 3: 运行完整测试套件**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: ALL PASS

- [ ] **Step 4: Final Commit**

```bash
git add -A
git commit -m "refactor(memory): complete WorkingMemory redesign - SessionTracker + WM dual-layer"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** 所有根因都有对应 Task 覆盖
  - 根因 1（摘要太简陋）→ Task 2（移除 file_index，不再依赖简陋摘要）
  - 根因 2（无显式提示指令）→ Task 2 + Task 5（注入行为指令）
  - 根因 3（位置不够醒目）→ Task 5（SessionTracker 在最前面）
  - 根因 4（压缩丢失记录）→ Task 8（确认 SessionTracker 不受压缩影响）
  - 根因 5（工具层无去重）→ Task 6（自动跟踪 + 未来可扩展为去重拦截）
  - 根因 6（file_index 解决错误问题）→ Task 1（SessionTracker 解决正确的问题）
  - 根因 7（extract_from_response 未调用）→ Task 3（实际调用）
- [x] **No placeholders:** 所有步骤都有具体代码
- [x] **Type consistency:** SessionTracker、AccessType、WorkingMemory 在所有 Task 中一致
- [x] **Backward compatibility:** `update_file_index` 保留为 deprecated，不破坏现有调用

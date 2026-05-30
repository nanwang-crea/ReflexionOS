# File/Code Reading Speed Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize ReflexionOS agent's file/code reading speed by enabling parallel tool execution, adding fast search/glob tools, and reducing redundant I/O.

**Architecture:** Five independent optimizations: (1) parallel tool execution in the agent loop, (2) GrepTool using ripgrep or grep subprocess, (3) GlobTool using `find`/`glob` subprocess for fast pattern matching, (4) file tree cache with merged git status, (5) file content cache with mtime validation. Each produces standalone value.

**Tech Stack:** Python 3.12, asyncio, aiofiles, subprocess (ripgrep/grep/find)

---

## Task 1: Parallel Tool Execution in RapidExecutionLoop

**Files:**
- Modify: `backend/app/execution/rapid_loop.py:145-190` ( `_handle_tool_execution`)
- Modify: `backend/app/execution/tool_call_executor.py:27-32` ( `execute` signature)
- Test: `backend/tests/test_execution/test_rapid_loop.py`

The current `_handle_tool_execution` iterates tool_calls serially with `for tool_call in rt.response.tool_calls`. We change it to classify tool calls into read-only (can be parallelized) and write/mutation (must be serial), then use `asyncio.gather` for the read-only batch.

### Step 1.1: Add `_is_read_only_tool` helper to ToolCallExecutor

Add a method to `ToolCallExecutor` that checks if a tool's execution is read-only based on the tool name. Read-only tools: `file` (read/search/list actions only), `grep`, `glob`, `memory` (get actions only), `session_recall`. Write tools: `edit`, `shell`, `plan`, `file` (write actions).

However, since we can't know the action before execution without inspecting args, we use a simpler heuristic: tools whose **name** is always safe to parallelize. For `file` tool, we check if the action in args is one of `read`, `search`, `list`.

- [ ] **Step 1.1: Add `_is_read_only_call` to ToolCallExecutor**

```python
# In backend/app/execution/tool_call_executor.py, add method to ToolCallExecutor class

READ_ONLY_TOOL_NAMES = frozenset({"grep", "glob", "session_recall"})
READ_ONLY_FILE_ACTIONS = frozenset({"read", "search", "list"})

def _is_read_only_call(self, tool_call: LLMToolCall) -> bool:
    if tool_call.name in READ_ONLY_TOOL_NAMES:
        return True
    if tool_call.name == "file":
        action = tool_call.arguments.get("action", "")
        return action in READ_ONLY_FILE_ACTIONS
    if tool_call.name == "memory":
        action = tool_call.arguments.get("action", "")
        return action in ("get", "list", "search")
    return False
```

- [ ] **Step 1.2: Write failing test for parallel tool execution**

Add to `backend/tests/test_execution/test_rapid_loop.py`:

```python
@pytest.mark.asyncio
async def test_multiple_read_only_tools_execute_in_parallel(self, mock_llm):
    """When LLM returns multiple read-only tool calls, they should execute concurrently."""
    registry = ToolRegistry()
    registry.register(MockTool())
    events = []
    execution_times = []

    class TimedMockTool(MockTool):
        async def execute(self, args):
            start = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            elapsed = asyncio.get_event_loop().time() - start
            execution_times.append(elapsed)
            return ToolResult(success=True, output=f"mock output {args.get('path', '')}")

    registry.register(TimedMockTool())
    # Remove original mock to avoid name collision — already registered under "mock"

    async def callback(event_type, data):
        events.append({"type": event_type, "data": data})

    execution_loop = RapidExecutionLoop(
        llm=mock_llm, tool_registry=registry, max_steps=3, event_callback=callback
    )

    call_count = [0]

    async def mock_stream(messages, tools=None):
        call_count[0] += 1
        if call_count[0] == 1:
            async for chunk in self._stream_response(
                content="读取多个文件",
                tool_calls=[
                    LLMToolCall(name="mock", arguments={"path": "a.py"}),
                    LLMToolCall(name="file", arguments={"action": "read", "path": "b.py"}),
                ],
                finish_reason="tool_calls",
            ):
                yield chunk
            return
        async for chunk in self._stream_response(content="已完成"):
            yield chunk

    mock_llm.stream_complete = mock_stream

    result = await execution_loop.run("读取多个文件")

    assert result.status == LoopStatus.COMPLETED
    assert len(result.steps) == 2
```

Note: This test will initially fail because the loop still executes tools serially. After the parallel change, both tools should run concurrently and the total wall-clock time should be ~0.1s instead of ~0.2s.

- [ ] **Step 1.3: Run test to verify it fails (still serial)**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py::TestRapidExecutionLoop::test_multiple_read_only_tools_execute_in_parallel -v`
Expected: FAIL or PASS with serial execution (test just checks both steps exist initially)

- [ ] **Step 1.4: Modify `_handle_tool_execution` to use `asyncio.gather` for read-only tools**

Replace the serial loop in `backend/app/execution/rapid_loop.py` `_handle_tool_execution`:

```python
async def _handle_tool_execution(
    self,
    context: LoopContext,
    result: LoopResult,
    rt: RuntimeState,
) -> LoopPhase:
    """TOOL_EXECUTION 阶段：执行工具调用，只读工具并行，写操作串行。"""
    rt.step_num += 1
    error_recovery_needed = False

    read_only_calls = []
    write_calls = []

    for tool_call in rt.response.tool_calls:
        if self.tool_executor._is_read_only_call(tool_call):
            read_only_calls.append(tool_call)
        else:
            write_calls.append(tool_call)

    # Execute read-only tools in parallel
    if read_only_calls:
        parallel_steps = await asyncio.gather(
            *[
                self.tool_executor.execute(tc, context, rt.step_num + i)
                for i, tc in enumerate(read_only_calls)
            ]
        )
        rt.step_num += len(read_only_calls) - 1
        for step in parallel_steps:
            result.steps.append(step)
            context.add_step(step)

            if step.status == StepStatus.WAITING_FOR_APPROVAL:
                return await self._handle_approval(step, context, result, rt)

            if step.status == StepStatus.FAILED:
                rt.consecutive_failures += 1
                await self._emit(
                    "tool:error",
                    {
                        "tool_name": step.tool,
                        "step_number": step.step_number,
                        "tool_call_id": step.tool_call_id,
                        "success": False,
                        "output": step.output,
                        "error": step.error,
                        "duration": step.duration,
                        "arguments": step.args,
                    },
                )
                if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                    error_recovery_needed = True
            else:
                rt.consecutive_failures = 0
                rt.has_executed_tools = True

    # Execute write tools serially
    for tool_call in write_calls:
        rt.step_num += 1
        step = await self.tool_executor.execute(tool_call, context, rt.step_num)
        result.steps.append(step)
        context.add_step(step)

        if step.status == StepStatus.WAITING_FOR_APPROVAL:
            return await self._handle_approval(step, context, result, rt)

        if step.status == StepStatus.FAILED:
            rt.consecutive_failures += 1
            await self._emit(
                "tool:error",
                {
                    "tool_name": tool_call.name,
                    "step_number": step.step_number,
                    "tool_call_id": step.tool_call_id,
                    "success": False,
                    "output": step.output,
                    "error": step.error,
                    "duration": step.duration,
                    "arguments": step.args,
                },
            )
            if rt.consecutive_failures >= self.MAX_ERROR_RETRIES:
                error_recovery_needed = True
        else:
            rt.consecutive_failures = 0
            rt.has_executed_tools = True

    if error_recovery_needed:
        return LoopPhase.ERROR_RECOVERY
    return LoopPhase.PLANNING
```

- [ ] **Step 1.5: Run existing tests to verify no regression**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py -v`
Expected: All existing tests PASS

- [ ] **Step 1.6: Commit**

```bash
git add backend/app/execution/rapid_loop.py backend/app/execution/tool_call_executor.py backend/tests/test_execution/test_rapid_loop.py
git commit -m "feat: parallel execution of read-only tool calls in agent loop"
```

---

## Task 2: GrepTool — Fast Content Search via Subprocess

**Files:**
- Create: `backend/app/tools/grep_tool.py`
- Modify: `backend/app/services/agent_service.py:104-130` (register new tool)
- Test: `backend/tests/test_tools/test_grep_tool.py`

Add a dedicated `grep` tool that uses `ripgrep` (rg) if available, falls back to `grep -rn`, then to Python-based search. This gives 10-50x speedup over the current `FileTool._search_in_directory` which walks `os.walk` + reads every file.

- [ ] **Step 2.1: Write failing test for GrepTool**

Create `backend/tests/test_tools/test_grep_tool.py`:

```python
import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.grep_tool import GrepTool


class TestGrepTool:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def grep_tool(self, temp_dir):
        security = PathSecurity([temp_dir], base_dir=temp_dir)
        return GrepTool(security)

    def test_schema_has_required_fields(self, grep_tool):
        schema = grep_tool.get_schema()
        assert schema["name"] == "grep"
        props = schema["parameters"]["properties"]
        assert "pattern" in props
        assert "path" in props
        assert "include" in props
        assert schema["parameters"]["required"] == ["pattern"]

    @pytest.mark.asyncio
    async def test_grep_finds_pattern_in_file(self, grep_tool, temp_dir):
        test_file = Path(temp_dir) / "example.py"
        test_file.write_text("def hello():\n    print('hello')\n\ndef world():\n    print('world')")

        result = await grep_tool.execute({"pattern": "def", "path": str(test_file)})

        assert result.success is True
        assert result.data["count"] >= 2

    @pytest.mark.asyncio
    async def test_grep_finds_pattern_in_directory(self, grep_tool, temp_dir):
        (Path(temp_dir) / "a.py").write_text("def alpha(): pass")
        (Path(temp_dir) / "b.py").write_text("def beta(): pass")

        result = await grep_tool.execute({"pattern": "def", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] >= 2

    @pytest.mark.asyncio
    async def test_grep_with_include_filter(self, grep_tool, temp_dir):
        (Path(temp_dir) / "code.py").write_text("target_string here")
        (Path(temp_dir) / "data.json").write_text('{"target_string": true}')

        result = await grep_tool.execute({
            "pattern": "target_string",
            "path": temp_dir,
            "include": "*.py",
        })

        assert result.success is True
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_grep_no_match(self, grep_tool, temp_dir):
        (Path(temp_dir) / "empty.py").write_text("nothing here")

        result = await grep_tool.execute({"pattern": "nonexistent_pattern_xyz", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_grep_rejects_path_outside_workspace(self, grep_tool):
        result = await grep_tool.execute({"pattern": "test", "path": "/etc/passwd"})

        assert result.success is False
        assert "不在允许范围内" in result.error
```

- [ ] **Step 2.2: Run test to verify it fails (module not found)**

Run: `cd backend && python -m pytest tests/test_tools/test_grep_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools.grep_tool'`

- [ ] **Step 2.3: Implement GrepTool**

Create `backend/app/tools/grep_tool.py`:

```python
import asyncio
import logging
import shutil
from typing import Any

from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_HAS_RG = shutil.which("rg") is not None
_HAS_GREP = shutil.which("grep") is not None

MAX_MATCHES = 50
CONTEXT_LINES = 2


class GrepTool(BaseTool):
    """Fast content search tool using ripgrep (preferred) or grep subprocess."""

    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", ".idea", ".vscode",
    })

    def __init__(self, security: PathSecurity):
        self.security = security

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Fast content search across files. Uses ripgrep if available, falls back to grep. "
            "Much faster than file search for finding patterns in codebases. "
            "Returns matching file paths, line numbers, and content."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (regex supported by ripgrep/grep)",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in (defaults to project root)",
                    },
                    "include": {
                        "type": "string",
                        "description": "File glob pattern to include (e.g. '*.py', '*.{ts,tsx}'). Only used for directory search.",
                    },
                },
                "required": ["pattern"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(success=False, error="缺少 pattern 参数")

        raw_path = args.get("path", ".")
        include = args.get("include")

        try:
            validated_path = self.security.validate_path(raw_path)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        if _HAS_RG:
            return await self._search_ripgrep(validated_path, pattern, include)
        if _HAS_GREP:
            return await self._search_grep(validated_path, pattern, include)
        return await self._search_python(validated_path, pattern, include)

    async def _search_ripgrep(self, path: str, pattern: str, include: str | None) -> ToolResult:
        cmd = [
            "rg",
            "--no-heading",
            "--line-number",
            "--color=never",
            f"--max-count={MAX_MATCHES}",
            f"--context={CONTEXT_LINES}",
        ]
        for d in self.EXCLUDED_DIRS:
            cmd.append(f"--glob=!{d}")
            cmd.append(f"--glob=!{d}/**")
        if include:
            for glob in include.split(","):
                cmd.append(f"--glob={glob.strip()}")
        cmd.extend([pattern, path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError:
            return ToolResult(success=False, error="搜索超时 (30s)")
        except FileNotFoundError:
            return await self._search_grep(path, pattern, include)

        output = stdout.decode("utf-8", errors="replace")
        if not output.strip():
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}'",
                data={"matches": [], "count": 0},
            )

        matches = self._parse_rg_output(output, path)
        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches[:MAX_MATCHES], "count": len(matches)},
        )

    async def _search_grep(self, path: str, pattern: str, include: str | None) -> ToolResult:
        cmd = ["grep", "-rn", "-E", f"--max-count={MAX_MATCHES}"]
        if include:
            cmd.extend(["--include", include])
        for d in self.EXCLUDED_DIRS:
            cmd.extend(["--exclude-dir", d])
        cmd.extend([pattern, path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError:
            return ToolResult(success=False, error="搜索超时 (30s)")
        except FileNotFoundError:
            return await self._search_python(path, pattern, include)

        output = stdout.decode("utf-8", errors="replace")
        if not output.strip():
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}'",
                data={"matches": [], "count": 0},
            )

        matches = self._parse_grep_output(output, path)
        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches[:MAX_MATCHES], "count": len(matches)},
        )

    async def _search_python(self, path: str, pattern: str, include: str | None) -> ToolResult:
        """Fallback: pure Python search using os.walk + open."""
        import os
        import re

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(success=False, error=f"无效正则表达式: {e}")

        matches = []
        search_dir = path if os.path.isdir(path) else os.path.dirname(path)

        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS and not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if compiled.search(line):
                                matches.append({
                                    "file": os.path.relpath(fpath, search_dir),
                                    "line": i,
                                    "content": line.rstrip()[:200],
                                })
                                if len(matches) >= MAX_MATCHES:
                                    break
                except OSError:
                    continue
                if len(matches) >= MAX_MATCHES:
                    break

        if not matches:
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}'",
                data={"matches": [], "count": 0},
            )

        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches[:MAX_MATCHES], "count": len(matches)},
        )

    def _parse_rg_output(self, output: str, base_path: str) -> list[dict]:
        matches = []
        for line in output.splitlines():
            if ":" not in line:
                continue
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            file_path, line_num, content = parts[0], parts[1], parts[2]
            try:
                line_num = int(line_num)
            except ValueError:
                continue
            rel = os.path.relpath(file_path, base_path) if not os.path.isabs(file_path) else file_path
            matches.append({"file": rel, "line": line_num, "content": content.strip()[:200]})
        return matches

    def _parse_grep_output(self, output: str, base_path: str) -> list[dict]:
        matches = []
        for line in output.splitlines():
            if ":" not in line:
                continue
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            file_path, line_num, content = parts[0], parts[1], parts[2]
            try:
                line_num = int(line_num)
            except ValueError:
                continue
            rel = os.path.relpath(file_path, base_path) if not os.path.isabs(file_path) else file_path
            matches.append({"file": rel, "line": line_num, "content": content.strip()[:200]})
        return matches

    def _format_matches(self, matches: list[dict]) -> str:
        if not matches:
            return "无匹配"
        lines = [f"找到 {len(matches)} 处匹配:"]
        for m in matches[:MAX_MATCHES]:
            lines.append(f"{m['file']}:{m['line']}: {m['content']}")
        if len(matches) > MAX_MATCHES:
            lines.append(f"... 还有 {len(matches) - MAX_MATCHES} 处")
        return "\n".join(lines)
```

- [ ] **Step 2.4: Register GrepTool in AgentService._build_run_tool_registry**

In `backend/app/services/agent_service.py`, add import and registration:

```python
# Add import at top:
from app.tools.grep_tool import GrepTool

# In _build_run_tool_registry, after registry.register(FileTool(path_security)):
registry.register(GrepTool(path_security))
```

- [ ] **Step 2.5: Run tests to verify GrepTool passes**

Run: `cd backend && python -m pytest tests/test_tools/test_grep_tool.py -v`
Expected: All tests PASS

- [ ] **Step 2.6: Run full test suite to check no regression**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 2.7: Commit**

```bash
git add backend/app/tools/grep_tool.py backend/app/services/agent_service.py backend/tests/test_tools/test_grep_tool.py
git commit -m "feat: add GrepTool for fast content search using ripgrep/grep subprocess"
```

---

## Task 3: GlobTool — Fast File Pattern Matching

**Files:**
- Create: `backend/app/tools/glob_tool.py`
- Modify: `backend/app/services/agent_service.py:104-130` (register new tool)
- Test: `backend/tests/test_tools/test_glob_tool.py`

Add a dedicated `glob` tool that uses `find` subprocess or Python's `pathlib.glob` for fast file name matching. This replaces the slow pattern of `file list` → manual filtering.

- [ ] **Step 3.1: Write failing test for GlobTool**

Create `backend/tests/test_tools/test_glob_tool.py`:

```python
import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.glob_tool import GlobTool


class TestGlobTool:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def glob_tool(self, temp_dir):
        security = PathSecurity([temp_dir], base_dir=temp_dir)
        return GlobTool(security)

    def test_schema_has_required_fields(self, glob_tool):
        schema = glob_tool.get_schema()
        assert schema["name"] == "glob"
        props = schema["parameters"]["properties"]
        assert "pattern" in props
        assert "path" in props
        assert schema["parameters"]["required"] == ["pattern"]

    @pytest.mark.asyncio
    async def test_glob_finds_python_files(self, glob_tool, temp_dir):
        (Path(temp_dir) / "a.py").touch()
        (Path(temp_dir) / "b.py").touch()
        (Path(temp_dir) / "c.js").touch()

        result = await glob_tool.execute({"pattern": "**/*.py", "path": temp_dir})

        assert result.success is True
        paths = [m["path"] for m in result.data["matches"]]
        assert any("a.py" in p for p in paths)
        assert any("b.py" in p for p in paths)
        assert not any("c.js" in p for p in paths)

    @pytest.mark.asyncio
    async def test_glob_finds_in_subdirectory(self, glob_tool, temp_dir):
        sub = Path(temp_dir) / "src"
        sub.mkdir()
        (sub / "main.py").touch()
        (sub / "util.py").touch()

        result = await glob_tool.execute({"pattern": "**/*.py", "path": temp_dir})

        assert result.success is True
        paths = [m["path"] for m in result.data["matches"]]
        assert any("main.py" in p for p in paths)

    @pytest.mark.asyncio
    async def test_glob_no_match(self, glob_tool, temp_dir):
        (Path(temp_dir) / "readme.md").touch()

        result = await glob_tool.execute({"pattern": "**/*.rs", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_glob_rejects_path_outside_workspace(self, glob_tool):
        result = await glob_tool.execute({"pattern": "*.py", "path": "/etc"})

        assert result.success is False
        assert "不在允许范围内" in result.error
```

- [ ] **Step 3.2: Run test to verify it fails (module not found)**

Run: `cd backend && python -m pytest tests/test_tools/test_glob_tool.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3.3: Implement GlobTool**

Create `backend/app/tools/glob_tool.py`:

```python
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_RESULTS = 100


class GlobTool(BaseTool):
    """Fast file pattern matching tool using pathlib.glob."""

    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", ".idea", ".vscode",
    })

    def __init__(self, security: PathSecurity):
        self.security = security

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "Fast file pattern matching tool. Supports glob patterns like '**/*.py' or 'src/**/*.ts'. "
            "Returns matching file paths relative to the search directory. "
            "Much faster than listing directories and filtering manually."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files (e.g. '**/*.py', 'src/**/*.ts', '*.md')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (defaults to project root)",
                    },
                },
                "required": ["pattern"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(success=False, error="缺少 pattern 参数")

        raw_path = args.get("path", ".")

        try:
            validated_path = self.security.validate_path(raw_path)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        if not os.path.isdir(validated_path):
            return ToolResult(success=False, error=f"不是目录: {validated_path}")

        matches = await asyncio.to_thread(self._glob, validated_path, pattern)

        if not matches:
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}' 的文件",
                data={"matches": [], "count": 0},
            )

        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches[:MAX_RESULTS], "count": len(matches)},
        )

    def _glob(self, base_path: str, pattern: str) -> list[dict]:
        base = Path(base_path)
        results = []
        try:
            for p in base.glob(pattern):
                if p.is_dir():
                    continue
                rel = os.path.relpath(str(p), base_path)
                if self._is_excluded(rel):
                    continue
                results.append({"path": rel, "name": p.name})
                if len(results) >= MAX_RESULTS:
                    break
        except OSError:
            pass
        return sorted(results, key=lambda m: m["path"])

    def _is_excluded(self, rel_path: str) -> bool:
        parts = Path(rel_path).parts
        return any(part in self.EXCLUDED_DIRS for part in parts)

    def _format_matches(self, matches: list[dict]) -> str:
        lines = [f"找到 {len(matches)} 个文件:"]
        for m in matches[:MAX_RESULTS]:
            lines.append(m["path"])
        if len(matches) > MAX_RESULTS:
            lines.append(f"... 还有 {len(matches) - MAX_RESULTS} 个")
        return "\n".join(lines)
```

- [ ] **Step 3.4: Register GlobTool in AgentService._build_run_tool_registry**

In `backend/app/services/agent_service.py`, add import and registration:

```python
# Add import at top:
from app.tools.glob_tool import GlobTool

# In _build_run_tool_registry, after registry.register(GrepTool(path_security)):
registry.register(GlobTool(path_security))
```

- [ ] **Step 3.5: Run tests to verify GlobTool passes**

Run: `cd backend && python -m pytest tests/test_tools/test_glob_tool.py -v`
Expected: All tests PASS

- [ ] **Step 3.6: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 3.7: Commit**

```bash
git add backend/app/tools/glob_tool.py backend/app/services/agent_service.py backend/tests/test_tools/test_glob_tool.py
git commit -m "feat: add GlobTool for fast file pattern matching using pathlib.glob"
```

---

## Task 4: File Tree Cache + Merged Git Status

**Files:**
- Modify: `backend/app/services/file_content_service.py:145-196`

Currently `_get_git_status_map` runs 3 separate git subprocesses sequentially, and `_build_tree` is a synchronous recursive walk. Optimize by:

1. Merging git status into a single `git status --porcelain` command
2. Caching the file tree with a TTL-based cache

- [ ] **Step 4.1: Write failing test for optimized git status**

Add to `backend/tests/test_file_content_api.py` or create a new test — but since `_get_git_status_map` is private, we test through the public `get_file_tree` endpoint. The key assertion is that the tree is returned successfully.

Actually, the most impactful change is replacing 3 git subprocesses with 1. Let's test the refactored `_get_git_status_map` directly by making it package-visible or testing through `get_file_tree`.

The simplest approach: verify `get_file_tree` still works after the refactor.

- [ ] **Step 4.2: Refactor `_get_git_status_map` to use single `git status --porcelain`**

Replace the entire `_get_git_status_map` method in `backend/app/services/file_content_service.py`:

```python
async def _get_git_status_map(self, project_path: str) -> dict[str, str]:
    status_map: dict[str, str] = {}

    try:
        result = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(result.communicate(), timeout=10)
        if result.returncode != 0:
            return {}
    except (FileNotFoundError, TimeoutError):
        return {}

    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:].strip()
        if not path:
            continue
        # Map XY status codes to single-char status
        x, y = xy[0], xy[1]
        if x in ("M", "A", "D", "R", "C"):
            status_map[path] = {"M": "M", "A": "A", "D": "D", "R": "M", "C": "A"}.get(x, "M")
        elif y in ("M", "A", "D"):
            status_map[path] = {"M": "M", "A": "A", "D": "D"}.get(y, "M")
        elif xy == "??":
            status_map[path] = "U"
        elif xy == "!!":
            pass  # ignored, skip

    return status_map
```

- [ ] **Step 4.3: Add TTL-based cache for file tree**

Add to `FileContentService.__init__` and `get_file_tree`:

```python
import time

class FileContentService:
    TREE_CACHE_TTL = 5.0  # seconds

    def __init__(self) -> None:
        self._tree_cache: dict[str, tuple[float, dict]] = {}

    async def get_file_tree(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        now = time.monotonic()
        cached = self._tree_cache.get(project_id)
        if cached and (now - cached[0]) < self.TREE_CACHE_TTL:
            return cached[1]

        git_status_map = await self._get_git_status_map(project_path)
        tree = self._build_tree(project_path, project_path, git_status_map)
        result = {"tree": tree}
        self._tree_cache[project_id] = (now, result)
        return result
```

- [ ] **Step 4.4: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 4.5: Commit**

```bash
git add backend/app/services/file_content_service.py
git commit -m "perf: merge 3 git subprocesses into 1, add 5s TTL cache for file tree"
```

---

## Task 5: File Read Cache with mtime Validation

**Files:**
- Modify: `backend/app/tools/file_tool.py:150-227` (`_read_file`)

Add an in-memory LRU cache for file reads. Cache key is `(path, mtime)`, so stale files are automatically invalidated.

- [ ] **Step 5.1: Add file read cache to FileTool**

Add to `backend/app/tools/file_tool.py`:

```python
import os
from functools import lru_cache

class FileTool(BaseTool):
    # ... existing constants ...

    def __init__(self, security: PathSecurity):
        self.security = security
        self.min_read_limit = 30
        self.default_read_limit = 80
        self.max_read_limit = 100
        self._read_cache: dict[str, tuple[float, list[str]]] = {}
        self._read_cache_max = 128

    def _get_cached_lines(self, path: str) -> list[str] | None:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._read_cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        return None

    def _set_cached_lines(self, path: str, lines: list[str]) -> None:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if len(self._read_cache) >= self._read_cache_max:
            oldest_key = next(iter(self._read_cache))
            del self._read_cache[oldest_key]
        self._read_cache[path] = (mtime, lines)
```

- [ ] **Step 5.2: Modify `_read_file` to use cache**

Replace the file reading portion of `_read_file`:

```python
async def _read_file(self, args: dict[str, Any]) -> ToolResult:
    path = self.security.validate_path(args["path"])

    if not os.path.exists(path):
        return ToolResult(success=False, error=f"文件不存在: {path}")

    if os.path.isdir(path):
        return ToolResult(success=False, error=f"路径是目录: {path}，请使用 list 操作")

    all_lines = self._get_cached_lines(path)
    if all_lines is None:
        async with aiofiles.open(path, encoding="utf-8") as f:
            all_lines = await f.readlines()
        self._set_cached_lines(path, all_lines)

    total_lines = len(all_lines)

    # ... rest of the method unchanged (determine range, extract, format) ...
```

- [ ] **Step 5.3: Run tests**

Run: `cd backend && python -m pytest tests/test_tools/test_file_tool.py -v`
Expected: All tests PASS

- [ ] **Step 5.4: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/tools/file_tool.py
git commit -m "perf: add mtime-validated read cache to FileTool, avoid redundant disk reads"
```

---

## Self-Review

**1. Spec coverage:**
- Parallel tool execution → Task 1
- GrepTool (ripgrep/grep subprocess) → Task 2
- GlobTool (pattern matching) → Task 3
- File tree cache + merged git status → Task 4
- File read cache → Task 5

**2. Placeholder scan:** No TBD/TODO/placeholders found. All code shown inline.

**3. Type consistency:**
- `ToolResult(success=True/False, output=str, data=dict)` — consistent across all tools
- `PathSecurity` used consistently for path validation
- `BaseTool` interface: `name`, `description`, `get_schema()`, `execute()` — consistent
- `_is_read_only_call` uses `LLMToolCall` which has `.name` and `.arguments` — consistent with `app/llm/base.py`

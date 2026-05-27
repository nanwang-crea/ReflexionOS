# 统一 Edit 工具实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将分散的 `file.write`/`patch` 工具统一为单个 `edit` 工具，支持 str_replace（5层级联模糊匹配）、patch、write 三种模式。

**Architecture:** 新增 `EditTool` 类，内含 5 层级联 replacer 策略的 `replace()` 函数；废弃 `PatchTool`，从 `FileTool` 移除 `write`/`delete`；更新注册、前端分类、测试。

**Tech Stack:** Python / asyncio / aiofiles / pytest

---

### Task 1: 实现 5 层级联模糊匹配引擎

**Files:**
- Create: `backend/app/tools/replacer.py`

- [ ] **Step 1: 编写 ExactReplacer + WhitespaceFlexReplacer**

```python
from __future__ import annotations

import re
from typing import Generator


def _exact_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    if old_string and old_string in content:
        yield old_string


def _strip_common_indent(lines: list[str]) -> list[str]:
    min_indent = float("inf")
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            min_indent = min(min_indent, indent)
    if min_indent == float("inf"):
        return lines
    return [line[min_indent:] if line.strip() else line for line in lines]


def _whitespace_flex_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    if not old_string:
        return
    old_lines = old_string.splitlines()
    content_lines = content.splitlines()
    if len(old_lines) > len(content_lines):
        return

    old_trimmed = [l.strip() for l in old_lines]
    old_stripped = _strip_common_indent(old_lines)

    for start in range(len(content_lines) - len(old_lines) + 1):
        block = content_lines[start : start + len(old_lines)]
        if [l.strip() for l in block] == old_trimmed:
            candidate = "\n".join(block)
            if content.find(candidate) != -1:
                yield candidate
            else:
                block_stripped = _strip_common_indent(block)
                candidate2 = "\n".join(block_stripped)
                if old_stripped == block_stripped and content.find(candidate2) != -1:
                    yield candidate2


def replace(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    not_found = True
    for replacer in [
        _exact_replacer,
        _whitespace_flex_replacer,
        _anchor_replacer,
        _escape_normalizer,
        _global_replacer,
    ]:
        for candidate in replacer(content, old_string):
            idx = content.find(candidate)
            if idx == -1:
                continue
            not_found = False
            if replace_all:
                return content.replace(candidate, new_string)
            last_idx = content.rfind(candidate)
            if idx != last_idx:
                continue
            return content[:idx] + new_string + content[idx + len(candidate) :]
    if not_found:
        raise ValueError("未找到匹配内容，请检查 old_string 是否与文件内容一致")
    raise ValueError("匹配到多个位置，请增加上下文以唯一定位")
```

- [ ] **Step 2: 编写 AnchorReplacer**

```python
def _anchor_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    old_lines = old_string.splitlines()
    if len(old_lines) < 3:
        return
    content_lines = content.splitlines()

    first_anchor = old_lines[0].strip()
    last_anchor = old_lines[-1].strip()
    middle_old = old_lines[1:-1]

    for start in range(len(content_lines) - len(old_lines) + 1):
        block = content_lines[start : start + len(old_lines)]
        if block[0].strip() != first_anchor or block[-1].strip() != last_anchor:
            continue
        match_count = sum(
            1 for a, b in zip(middle_old, block[1:-1]) if a.strip() == b.strip()
        )
        if len(middle_old) == 0 or match_count / len(middle_old) >= 0.5:
            candidate = "\n".join(block)
            if content.find(candidate) != -1:
                yield candidate
```

- [ ] **Step 3: 编写 EscapeNormalizer + GlobalReplacer**

```python
_ESCAPE_MAP = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\'": "'",
    '\\"': '"',
    "\\\\": "\\",
}


def _unescape(text: str) -> str:
    for esc, real in _ESCAPE_MAP.items():
        text = text.replace(esc, real)
    return text


def _escape_normalizer(content: str, old_string: str) -> Generator[str, None, None]:
    if not old_string:
        return
    unescaped = _unescape(old_string)
    if unescaped != old_string and unescaped in content:
        yield unescaped
    unescaped_content = _unescape(content)
    if old_string in unescaped_content:
        idx = unescaped_content.find(old_string)
        candidate = content[idx : idx + len(old_string)]
        if candidate in content:
            yield candidate


def _global_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    if not old_string:
        return
    count = content.count(old_string)
    if count > 0:
        yield old_string
```

- [ ] **Step 4: 验证 replacer 模块语法**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "from app.tools.replacer import replace; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/replacer.py
git commit -m "feat: add 5-layer cascading replacer engine for fuzzy string matching"
```

---

### Task 2: 实现 EditTool

**Files:**
- Create: `backend/app/tools/edit_tool.py`

- [ ] **Step 1: 编写 EditTool 骨架 + str_replace + write + patch**

```python
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import aiofiles

from app.errors import ValidationError
from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult
from app.tools.diff_parser import CodexPatchParser, DiffParser
from app.tools.replacer import replace

logger = logging.getLogger(__name__)

_file_locks: dict[str, asyncio.Lock] = {}


def _get_lock(path: str) -> asyncio.Lock:
    if path not in _file_locks:
        _file_locks[path] = asyncio.Lock()
    return _file_locks[path]


def _detect_line_ending(content: str) -> str:
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def _normalize_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _convert_line_ending(text: str, ending: str) -> str:
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    return text


class EditTool(BaseTool):
    def __init__(self, security: PathSecurity):
        self.security = security
        self.parser = DiffParser()
        self.codex_parser = CodexPatchParser()

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "文件编辑工具。推荐使用 str_replace 进行精确或模糊替换；"
            "patch 用于复杂多行 diff 修改；write 仅用于创建新文件。"
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action")
        path = args.get("path")
        if not action:
            return ToolResult(success=False, error="缺少 action 参数")
        if not path:
            return ToolResult(success=False, error="缺少 path 参数")
        try:
            if action == "str_replace":
                return await self._str_replace(args)
            elif action == "patch":
                return await self._patch(args)
            elif action == "write":
                return await self._write(args)
            else:
                return ToolResult(success=False, error=f"未知 action: {action}")
        except Exception as e:
            logger.error("Edit 执行失败: %s", e)
            return ToolResult(success=False, error=str(e))

    async def _str_replace(self, args: dict[str, Any]) -> ToolResult:
        path = self.security.validate_write_path(args["path"])
        old_string = args.get("old_string", None)
        new_string = args.get("new_string", None)

        if old_string is None:
            return ToolResult(success=False, error="缺少 old_string 参数")
        if new_string is None:
            return ToolResult(success=False, error="缺少 new_string 参数")
        if old_string == new_string:
            return ToolResult(success=False, error="old_string 和 new_string 不能相同")
        replace_all = bool(args.get("replace_all", False))

        lock = _get_lock(path)
        async with lock:
            if old_string == "":
                return await self._append_or_create(path, new_string)

            if not os.path.exists(path):
                return ToolResult(success=False, error=f"文件不存在: {path}")
            if os.path.isdir(path):
                return ToolResult(success=False, error=f"路径是目录: {path}")

            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()

            line_ending = _detect_line_ending(content)
            normalized_content = _normalize_to_lf(content)
            normalized_old = _normalize_to_lf(old_string)
            normalized_new = _normalize_to_lf(new_string)

            try:
                result = replace(normalized_content, normalized_old, normalized_new, replace_all)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))

            result = _convert_line_ending(result, line_ending)

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(result)

        return ToolResult(
            success=True,
            output=f"成功替换 {path}",
            data={"file": path, "action": "str_replace", "replace_all": replace_all},
        )

    async def _append_or_create(self, path: str, new_string: str) -> ToolResult:
        lock = _get_lock(path)
        async with lock:
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            if os.path.exists(path):
                async with aiofiles.open(path, encoding="utf-8") as f:
                    content = await f.read()
                line_ending = _detect_line_ending(content)
                normalized_new = _normalize_to_lf(new_string)
                if not content.endswith("\n"):
                    content += line_ending
                content += _convert_line_ending(normalized_new, line_ending)
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(content)
                return ToolResult(
                    success=True,
                    output=f"成功追加内容到 {path}",
                    data={"file": path, "action": "str_replace"},
                )

            normalized_new = _normalize_to_lf(new_string)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(normalized_new)
            return ToolResult(
                success=True,
                output=f"成功创建文件 {path}",
                data={"file": path, "action": "str_replace"},
            )

    async def _patch(self, args: dict[str, Any]) -> ToolResult:
        patch_text = args.get("patch")
        if not patch_text:
            return ToolResult(success=False, error="缺少 patch 参数")
        if self.codex_parser.is_codex_style(patch_text):
            return await self._execute_codex_patch(patch_text)
        return await self._execute_unified_diff(patch_text)

    async def _execute_unified_diff(self, patch_text: str) -> ToolResult:
        file_paths = self.parser.extract_file_paths(patch_text)
        unique_file_paths = list(dict.fromkeys(file_paths))
        if len(unique_file_paths) > 1:
            return ToolResult(success=False, error="Unified Diff 仅支持单文件 patch")
        hunks = self.parser.parse(patch_text)
        if not hunks:
            return ToolResult(success=False, error="无法解析 Unified Diff")
        file_path = self.parser.extract_file_path(patch_text)
        if not file_path:
            return ToolResult(success=False, error="无法提取文件路径")
        file_path = self.security.validate_write_path(file_path)

        lock = _get_lock(file_path)
        async with lock:
            try:
                with open(file_path, encoding="utf-8") as f:
                    original_lines = f.readlines()
            except FileNotFoundError:
                original_lines = []
            result_lines, applied, rejected = self._apply_hunks(original_lines, hunks)
            if rejected > 0:
                return ToolResult(
                    success=False,
                    error=f"Patch 冲突: {rejected}/{len(hunks)} 个修改无法应用",
                    data={"file": file_path, "hunks_applied": applied, "hunks_rejected": rejected},
                )
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(result_lines)

        return ToolResult(
            success=True,
            output=f"成功应用 {applied} 个修改到 {file_path}",
            data={"file": file_path, "hunks_applied": applied, "hunks_rejected": rejected},
        )

    async def _execute_codex_patch(self, patch_text: str) -> ToolResult:
        try:
            parsed = self.codex_parser.parse(patch_text)
        except ValidationError as e:
            return ToolResult(success=False, error=str(e))
        file_path = self.security.validate_write_path(parsed.file_path)

        lock = _get_lock(file_path)
        async with lock:
            if parsed.action == "add":
                if os.path.exists(file_path):
                    return ToolResult(success=False, error=f"目标已存在: {file_path}")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(self._diff_lines_to_file_lines(parsed.lines))
                return ToolResult(
                    success=True,
                    output=f"成功创建文件 {file_path}",
                    data={"file": file_path, "action": "add"},
                )
            if parsed.action == "delete":
                if not os.path.exists(file_path):
                    return ToolResult(success=False, error=f"目标不存在: {file_path}")
                os.remove(file_path)
                return ToolResult(
                    success=True,
                    output=f"成功删除文件 {file_path}",
                    data={"file": file_path, "action": "delete"},
                )
            if parsed.action == "update":
                try:
                    with open(file_path, encoding="utf-8") as f:
                        original_lines = f.readlines()
                except FileNotFoundError:
                    return ToolResult(success=False, error=f"目标不存在: {file_path}")
                result_lines = original_lines[:]
                applied = 0
                for hunk in parsed.hunks:
                    success, error = self._apply_codex_hunk(result_lines, hunk)
                    if not success:
                        return ToolResult(
                            success=False, error=error, data={"file": file_path, "hunks_applied": applied}
                        )
                    applied += 1
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(result_lines)
                return ToolResult(
                    success=True,
                    output=f"成功应用 {applied} 个修改到 {file_path}",
                    data={"file": file_path, "action": "update", "hunks_applied": applied},
                )
        return ToolResult(success=False, error="不支持的 patch 操作")

    async def _write(self, args: dict[str, Any]) -> ToolResult:
        path = self.security.validate_write_path(args["path"])
        content = args.get("content")
        if content is None:
            return ToolResult(success=False, error="缺少 content 参数")
        lock = _get_lock(path)
        async with lock:
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
        return ToolResult(success=True, output=f"文件已写入: {path}")

    def _apply_hunks(self, original_lines: list[str], hunks: list) -> tuple:
        result_lines = original_lines[:]
        applied = 0
        rejected = 0
        for hunk in reversed(hunks):
            success = self._apply_hunk(result_lines, hunk)
            if success:
                applied += 1
            else:
                rejected += 1
        return result_lines, applied, rejected

    def _apply_hunk(self, lines: list[str], hunk: Any) -> bool:
        old_count = 0
        new_lines: list[str] = []
        for line in hunk.lines:
            if line.startswith("-"):
                old_count += 1
            elif line.startswith("+"):
                new_lines.append(line[1:] + "\n")
            elif line.startswith(" "):
                old_count += 1
                new_lines.append(line[1:] + "\n")
        start = hunk.old_start - 1
        if old_count == 0 and hunk.old_start > 0:
            start = hunk.old_start
        if start < 0 and old_count == 0:
            start = 0
        elif start < 0 or start > len(lines):
            return False
        old_offset = 0
        for line in hunk.lines:
            if line.startswith("+"):
                continue
            idx = start + old_offset
            if idx >= len(lines):
                return False
            actual = lines[idx].rstrip("\n").rstrip("\r")
            expected = line[1:]
            if actual != expected:
                return False
            old_offset += 1
        try:
            if start + old_count <= len(lines):
                lines[start : start + old_count] = new_lines
                return True
            return False
        except Exception:
            return False

    def _apply_codex_hunk(self, lines: list[str], hunk_lines: list[str]) -> tuple[bool, str]:
        old_block: list[str] = []
        new_block: list[str] = []
        for line in hunk_lines:
            if line.startswith(" "):
                old_block.append(line[1:] + "\n")
                new_block.append(line[1:] + "\n")
            elif line.startswith("-"):
                old_block.append(line[1:] + "\n")
            elif line.startswith("+"):
                new_block.append(line[1:] + "\n")
        if not old_block:
            return False, "hunk 缺少上下文或删除行"
        matches = []
        max_start = len(lines) - len(old_block)
        for start in range(max_start + 1):
            if lines[start : start + len(old_block)] == old_block:
                matches.append(start)
        if not matches:
            return False, "Patch 冲突: hunk 未匹配到原文件内容"
        if len(matches) > 1:
            return False, "Patch 冲突: hunk 匹配到多个位置，请增加上下文"
        start = matches[0]
        lines[start : start + len(old_block)] = new_block
        return True, ""

    def _diff_lines_to_file_lines(self, diff_lines: list[str]) -> list[str]:
        return [line[1:] + "\n" for line in diff_lines]

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["str_replace", "patch", "write"],
                        "description": (
                            "编辑模式：str_replace=字符串替换（推荐，支持模糊匹配）、"
                            "patch=应用diff补丁、write=全量写入（仅创建新文件）"
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对或绝对）",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "str_replace 使用：要替换的文本；空字符串表示追加到文件末尾或创建新文件",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "str_replace 使用：替换后的文本，必须与 old_string 不同",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "str_replace 使用：替换所有出现位置（默认只替换第一个唯一匹配）",
                    },
                    "patch": {
                        "type": "string",
                        "description": (
                            "patch 使用：补丁内容。支持 Unified Diff 和 Codex-style patch"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "write 使用：文件完整内容",
                    },
                },
                "required": ["action", "path"],
            },
        }
```

- [ ] **Step 2: 验证 EditTool 可导入**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "from app.tools.edit_tool import EditTool; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/app/tools/edit_tool.py
git commit -m "feat: add EditTool with str_replace/patch/write actions"
```

---

### Task 3: 修改 FileTool — 移除 write/delete

**Files:**
- Modify: `backend/app/tools/file_tool.py`

- [ ] **Step 1: 从 schema 中移除 write/delete 及 content 参数**

在 `get_schema()` 中：
- `action` enum 从 `["read", "search", "write", "list", "delete"]` 改为 `["read", "search", "list"]`
- 移除 `content` property
- 更新 `required` 仍为 `["action", "path"]`

- [ ] **Step 2: 从 execute() 中移除 write/delete 分支**

移除 `elif action == "write"` 和 `elif action == "delete"` 分支，更新错误消息为 `"支持: read, list, search"`。

- [ ] **Step 3: 移除 _write_file 和 _delete_file 方法**

删除 `async def _write_file` 和 `async def _delete_file` 两个方法。

- [ ] **Step 4: 验证**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "from app.tools.file_tool import FileTool; t = FileTool(None); print(t.get_schema()['parameters']['properties']['action']['enum'])"`
Expected: `['read', 'search', 'list']`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/file_tool.py
git commit -m "refactor: remove write/delete from FileTool, moved to EditTool"
```

---

### Task 4: 更新工具注册 — agent_service.py

**Files:**
- Modify: `backend/app/services/agent_service.py`

- [ ] **Step 1: 替换 import 和注册**

在 `_build_run_tool_registry` 方法中：
- 将 `from app.tools.patch_tool import PatchTool` 替换为 `from app.tools.edit_tool import EditTool`
- 将 `registry.register(PatchTool(path_security))` 替换为 `registry.register(EditTool(path_security))`

- [ ] **Step 2: 验证导入无误**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "from app.services.agent_service import AgentService; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent_service.py
git commit -m "refactor: register EditTool instead of PatchTool"
```

---

### Task 5: 更新 system prompt — prompt_manager.py

**Files:**
- Modify: `backend/app/execution/prompt_manager.py`

- [ ] **Step 1: 在 system prompt 中增加 edit 工具使用引导**

在 `system` 模板的 `## Rules:` 部分末尾追加：

```
- For file edits, prefer the edit tool with action=str_replace over patch or write.
  str_replace supports fuzzy matching (indentation, whitespace differences are tolerated).
  Use write only when creating a brand-new file.
  Use patch only for complex multi-hunk changes where diff format is more appropriate.
```

- [ ] **Step 2: 验证 prompt 渲染**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "from app.execution.prompt_manager import PromptManager; pm = PromptManager(); p = pm.get_template('system').render(tool_list='test'); print('str_replace' in p)"`
Expected: True

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/prompt_manager.py
git commit -m "docs: add edit tool usage guidance to system prompt"
```

---

### Task 6: 更新前端 receipt 分类 — receiptUtils.ts

**Files:**
- Modify: `frontend/src/components/execution/receiptUtils.ts`

- [ ] **Step 1: 新增 buildEditDetail 函数**

在 `buildPatchDetail` 函数之后添加：

```typescript
function buildEditDetail(id: string, args: Record<string, unknown>): ActionReceiptDetail {
  const action = typeof args.action === 'string' ? args.action : ''
  const path = typeof args.path === 'string' ? args.path : ''
  const target = shortPath(path)

  if (action === 'str_replace') {
    const oldString = typeof args.old_string === 'string' ? args.old_string : ''
    const replaceAll = args.replace_all === true
    if (!oldString) {
      return {
        id,
        toolName: 'edit',
        status: 'pending',
        summary: target ? `创建 ${target}` : '创建文件',
        category: 'create',
        arguments: args,
        target
      }
    }
    const verb = replaceAll ? '批量替换' : '替换'
    return {
      id,
      toolName: 'edit',
      status: 'pending',
      summary: target ? `${verb} ${target}` : `${verb}内容`,
      category: 'edit',
      arguments: args,
      target
    }
  }

  if (action === 'patch') {
    const patchText = typeof args.patch === 'string' ? args.patch : ''
    const category = getPatchCategory(patchText)
    const patchTarget = shortPath(getPatchTarget(patchText))
    const verb = { create: '创建', edit: '编辑', delete: '删除' }[category]
    return {
      id,
      toolName: 'edit',
      status: 'pending',
      summary: patchTarget ? `${verb} ${patchTarget}` : `${verb}文件`,
      category,
      arguments: args,
      target: patchTarget
    }
  }

  if (action === 'write') {
    return {
      id,
      toolName: 'edit',
      status: 'pending',
      summary: target ? `写入 ${target}` : '写入文件',
      category: 'create',
      arguments: args,
      target
    }
  }

  return {
    id,
    toolName: 'edit',
    status: 'pending',
    summary: target ? `处理 ${target}` : '编辑操作',
    category: 'other',
    arguments: args,
    target
  }
}
```

- [ ] **Step 2: 更新 buildReceiptDetail 分发逻辑**

在 `buildReceiptDetail` 函数中，在 `if (toolName === 'patch')` 之后添加：

```typescript
if (toolName === 'edit') {
  return buildEditDetail(id, safeArgs)
}
```

同时移除 `if (toolName === 'patch')` 分支（因为 patch 已被 edit 取代，但保留以防旧数据兼容）。保留 `buildPatchDetail` 函数和 `if (toolName === 'patch')` 分支用于向后兼容。

- [ ] **Step 3: 验证前端编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/execution/receiptUtils.ts
git commit -m "feat: add edit tool receipt categorization"
```

---

### Task 7: 编写 EditTool 测试

**Files:**
- Create: `backend/tests/test_tools/test_edit_tool.py`

- [ ] **Step 1: 编写测试用例**

```python
import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.edit_tool import EditTool


class TestEditToolStrReplace:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return EditTool(security)

    @pytest.mark.asyncio
    async def test_exact_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("def hello():\n    print('hello')\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "print('hello')",
            "new_string": "print('hello world')",
        })
        assert result.success is True
        assert "hello world" in f.read_text()

    @pytest.mark.asyncio
    async def test_whitespace_flex_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("def hello():\n    print('hello')\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "def hello():\nprint('hello')",
            "new_string": "def hello():\nprint('world')",
        })
        assert result.success is True
        assert "world" in f.read_text()

    @pytest.mark.asyncio
    async def test_anchor_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("class Foo:\n    def bar(self):\n        pass\n\n    def baz(self):\n        pass\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "class Foo:\n    def bar(self):\n        something_different\n\n    def baz(self):\n        pass",
            "new_string": "class Foo:\n    def bar(self):\n        new_implementation\n\n    def baz(self):\n        pass",
        })
        assert result.success is True
        assert "new_implementation" in f.read_text()

    @pytest.mark.asyncio
    async def test_replace_all(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("old_value\nkeep\nold_value\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "old_value",
            "new_string": "new_value",
            "replace_all": True,
        })
        assert result.success is True
        content = f.read_text()
        assert content.count("new_value") == 2
        assert "old_value" not in content

    @pytest.mark.asyncio
    async def test_not_found(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("line1\nline2\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "nonexistent",
            "new_string": "replacement",
        })
        assert result.success is False
        assert "未找到" in result.error

    @pytest.mark.asyncio
    async def test_multiple_matches_rejects(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("repeat\nkeep\nrepeat\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "repeat",
            "new_string": "changed",
        })
        assert result.success is False
        assert "多个位置" in result.error

    @pytest.mark.asyncio
    async def test_empty_old_string_creates_file(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "new_file.py"
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "",
            "new_string": "print('created')\n",
        })
        assert result.success is True
        assert f.read_text() == "print('created')\n"

    @pytest.mark.asyncio
    async def test_empty_old_string_appends(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("existing\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "",
            "new_string": "appended\n",
        })
        assert result.success is True
        content = f.read_text()
        assert "existing" in content
        assert "appended" in content

    @pytest.mark.asyncio
    async def test_crlf_preserved(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_bytes(b"line1\r\nline2\r\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "line1",
            "new_string": "line_one",
        })
        assert result.success is True
        content = f.read_bytes()
        assert b"line_one\r\nline2\r\n" == content


class TestEditToolWrite:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return EditTool(security)

    @pytest.mark.asyncio
    async def test_write_creates_new_file(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "new.py"
        result = await edit_tool.execute({
            "action": "write",
            "path": str(f),
            "content": "hello",
        })
        assert result.success is True
        assert f.read_text() == "hello"


class TestEditToolPatch:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return EditTool(security)

    @pytest.mark.asyncio
    async def test_unified_diff(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("def hello():\n    print('hello')\n")
        patch = f"""--- a/{f}
+++ b/{f}
@@ -1,2 +1,2 @@
 def hello():
-    print('hello')
+    print('hello world')
"""
        result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
        assert result.success is True
        assert "hello world" in f.read_text()

    @pytest.mark.asyncio
    async def test_codex_style_update(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.txt"
        f.write_text("alpha\nbeta\ngamma\n")
        patch = f"""*** Begin Patch
*** Update File: {f}
@@
 alpha
-beta
+changed
 gamma
*** End Patch
"""
        result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
        assert result.success is True
        assert f.read_text() == "alpha\nchanged\ngamma\n"
```

- [ ] **Step 2: 运行测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_tools/test_edit_tool.py -v`
Expected: 大部分 PASS

- [ ] **Step 3: 修复任何测试失败**

根据输出修复问题。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_tools/test_edit_tool.py
git commit -m "test: add EditTool tests for str_replace, patch, write"
```

---

### Task 8: 更新 FileTool 测试

**Files:**
- Modify: `backend/tests/test_tools/test_file_tool.py`

- [ ] **Step 1: 移除 write/delete 测试，更新 schema 断言**

- 删除 `test_write_file_success` 和 `test_write_requires_content_after_flattening_schema` 和 `test_delete_file`
- 在 `test_schema_is_flat_and_openai_compatible` 中将 `enum` 断言从 `["read", "search", "write", "list", "delete"]` 改为 `["read", "search", "list"]`
- 从 `props` 集合中移除 `"content"`

- [ ] **Step 2: 运行 FileTool 测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_tools/test_file_tool.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_tools/test_file_tool.py
git commit -m "test: update FileTool tests for read/list/search only"
```

---

### Task 9: 运行全量测试 + 最终验证

**Files:** None

- [ ] **Step 1: 运行全部后端测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: All PASS

- [ ] **Step 2: 验证前端编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: 无错误

- [ ] **Step 3: 验证工具注册完整性**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "
from app.services.agent_service import AgentService
from app.tools.registry import ToolRegistry
from app.tools.file_tool import FileTool
from app.tools.edit_tool import EditTool
from app.security.path_security import PathSecurity
import tempfile, os
tmpdir = tempfile.mkdtemp()
sec = PathSecurity([os.path.realpath(tmpdir)])
reg = ToolRegistry()
reg.register(FileTool(sec))
reg.register(EditTool(sec))
tools = reg.list_tools()
print(tools)
assert 'edit' in tools
assert 'file' in tools
assert 'patch' not in tools
print('OK')
"`
Expected: `['edit', 'file', ...]` and OK

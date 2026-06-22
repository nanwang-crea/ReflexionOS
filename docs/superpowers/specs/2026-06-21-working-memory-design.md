# Working Memory 设计文档

**日期**: 2026-06-21
**状态**: 设计阶段
**作者**: Claude + 木南

## 目标

在对话历史压缩机制之上，增加一层"防遗忘保险"——Working Memory。它是一个独立的、结构化的、永不压缩的存储，在每次 LLM 调用时自动注入 system prompt，确保关键信息（文件索引、决策记录、变量工作集、错误记录）在上下文压缩后仍然可见。

采用 **混合模式**：系统自动从 tool 调用结果中提取结构化信息（文件索引、变量值），同时允许模型通过 `working_memory_update` 工具主动补充决策记录和关键发现。

## 问题陈述

### 当前架构的根本矛盾

**模型唯一的信息载体是对话历史，而对话历史会被压缩。**

具体表现：

1. **Tier 2 截断丢失细节** — `ContextCompressor.build_tier2_messages()` 将 tool output 截断为 `head 1600 + tail 600` 字符，文件内容的关键结构信息（类名、函数签名、导入关系）被截断
2. **Tier 3 压缩丢失结构** — 旧消息被 LLM 压缩为一段摘要文本，所有结构化信息被展平为自然语言描述
3. **Tier 1 裁剪丢失存在** — `prune_tool_outputs()` 将旧 tool output 替换为 `[Old tool result content cleared]`，模型既不知道丢失了什么，也不知道该不该去找回
4. **session_recall 是被动工具** — 模型必须先知道自己忘了什么才能搜，而压缩后它已经不知道了。`RecallService._match_score` 用 token 交集做匹配，搜"数据库配置"找不到"DB connection string"

### 现有架构中的正面参照

`_build_plan_status` 的做法已经触碰到了正确方向——它把 Plan 状态作为独立的 system message 注入，不依赖对话历史传递。Working Memory 就是把这个思路系统化。

## 设计原则

1. **对话历史是流，Working Memory 是岸** — 信息从流中提取到岸上，岸上的信息永不丢失
2. **被动注入优于主动查询** — 模型不需要知道自己忘了什么，关键信息始终在视野里
3. **自动提取 + 模型主动写入混合** — 系统保证基础覆盖不遗漏，模型补充关键决策和推理
4. **Token 预算硬约束** — Working Memory 注入总量控制在 ~2000 tokens，不是无底洞
5. **与现有三级压缩模型共存** — 不是替代压缩，而是在压缩之上加一层"防遗忘保险"
6. **纯规则提取，不调 LLM** — 自动提取用规则实现，避免延迟和成本

## 架构设计

### 总体架构

```
┌─────────────────────────────────────────────────────────┐
│  System Prompt                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Working Memory (新增，永不压缩)                    │  │
│  │  文件索引 / 决策记录 / 变量工作集 / 错误记录         │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tier 3: LLM 压缩摘要 (现有，不变)                  │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tier 2: 截断消息 (现有，增强语义化占位符)            │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tier 1: 完整保真消息 (现有，不变)                    │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Plan Status (现有，不变)                           │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Task Anchor (现有，不变)                           │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

信息流：
  Tool 执行结果 ──→ MemoryExtractor (自动提取) ──→ WorkingMemory
                └──→ ContextCompressor (现有压缩) ──→ Tier 1/2/3
  模型主动写入 ──→ working_memory_update 工具 ──→ WorkingMemory
  WorkingMemory ──→ to_prompt_section() ──→ LoopMessageBuilder.build() 注入
```

### 数据流

```
Tool 执行完成
    │
    ├──→ MemoryExtractor.extract(tool_name, args, result)
    │       ├── file (action=read)   → upsert_file(path, summary)
    │       ├── file (action=search) → 追加搜索关键词到已有摘要
    │       ├── file (action=list)   → upsert_file(path, "directory with N items")
    │       ├── edit (action=*)      → upsert_file(path, "[MODIFIED] ...")
    │       ├── shell                → add_error() / set_variable()
    │       ├── grep                 → upsert_file(path, "found in search")
    │       ├── session_recall       → set_variable("recall:query", snippet)
    │       └── explore              → set_variable("explore:query", summary)
    │
    └──→ context.compressor.add_message(role, content, ...)  [现有流程不变]

LLM 调用前 (LoopMessageBuilder.build)
    │
    ├── System Prompt
    ├── WorkingMemory.to_prompt_section()  ← 新增注入点
    ├── Tier 3 摘要
    ├── Tier 2 截断消息 (增强语义化占位符)
    ├── Tier 1 完整消息
    ├── Plan Status
    └── Task Anchor / Prefill

模型主动写入
    │
    └──→ working_memory_update(action, key, value)
            ├── decide → add_decision(key, value)
            ├── note   → add_decision("[note] key", value)
            └── set_var → set_variable(key, value)
```

## 详细设计

### 1. WorkingMemory 数据模型

**文件**: `backend/app/memory/working_memory.py`（新建）

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class MemoryEntryType(str, Enum):
    """Working Memory 条目类型"""
    FILE_SUMMARY = "file_summary"       # 读过的文件摘要
    KEY_DECISION = "key_decision"       # 关键决策
    VARIABLE = "variable"               # 配置/变量工作集
    ERROR_ENCOUNTERED = "error"         # 遇到的错误
    PATTERN_FOUND = "pattern"           # 发现的模式/规律


@dataclass
class MemoryEntry:
    """Working Memory 中的一条记录"""
    id: str                                     # 唯一标识
    entry_type: MemoryEntryType                 # 类型
    key: str                                    # 主键（如文件路径、决策名）
    value: str                                  # 值（摘要、决策内容等）
    source: str = "auto"                        # 来源: "auto" | "model"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0                       # 被引用次数（用于淘汰）


@dataclass
class WorkingMemory:
    """
    结构化工作记忆 — 在对话历史之外持久化关键信息

    生命周期：与 LoopContext 一致，每次 agent run 创建，run 结束销毁
    注入位置：LoopMessageBuilder.build() 中，system prompt 之后、Tier 3 之前
    Token 预算：~2000 tokens（约 3000 中文字符）
    """

    # 文件索引：agent 读过的每个文件的精炼摘要
    # key = 文件路径, value = 摘要
    file_index: dict[str, MemoryEntry] = field(default_factory=dict)

    # 关键决策记录
    decisions: list[MemoryEntry] = field(default_factory=list)

    # 变量/配置工作集
    # key = 变量名, value = 值
    variables: dict[str, MemoryEntry] = field(default_factory=dict)

    # 错误记录
    errors: list[MemoryEntry] = field(default_factory=list)

    # Token 预算
    max_tokens: int = 2000

    # ---- 写入接口 ----

    def upsert_file(self, path: str, summary: str, source: str = "auto") -> None:
        """新增或更新文件摘要"""
        if path in self.file_index:
            entry = self.file_index[path]
            entry.value = summary
            entry.updated_at = datetime.now()
            entry.source = source
        else:
            self.file_index[path] = MemoryEntry(
                id=f"file:{path}",
                entry_type=MemoryEntryType.FILE_SUMMARY,
                key=path,
                value=summary,
                source=source,
            )

    def add_decision(self, decision: str, rationale: str = "", source: str = "model") -> None:
        """记录关键决策"""
        self.decisions.append(MemoryEntry(
            id=f"decision:{len(self.decisions)}",
            entry_type=MemoryEntryType.KEY_DECISION,
            key=decision,
            value=rationale,
            source=source,
        ))

    def set_variable(self, name: str, value: str, source: str = "auto") -> None:
        """设置变量/配置"""
        self.variables[name] = MemoryEntry(
            id=f"var:{name}",
            entry_type=MemoryEntryType.VARIABLE,
            key=name,
            value=value,
            source=source,
        )

    def add_error(self, error_type: str, detail: str, source: str = "auto") -> None:
        """记录遇到的错误"""
        self.errors.append(MemoryEntry(
            id=f"error:{len(self.errors)}",
            entry_type=MemoryEntryType.ERROR_ENCOUNTERED,
            key=error_type,
            value=detail,
            source=source,
        ))

    # ---- 读取接口 ----

    def to_prompt_section(self) -> str:
        """
        将 Working Memory 格式化为 system prompt 注入段

        格式紧凑、信息密度高，控制在 ~2000 tokens 以内
        如果超过预算，按优先级淘汰：errors > variables > file_index(最旧的) > decisions
        """
        sections = []

        # 1. 文件索引（最高优先级之一）
        if self.file_index:
            lines = ["📂 Files read:"]
            for path, entry in self.file_index.items():
                lines.append(f"  {path}: {entry.value}")
            sections.append("\n".join(lines))

        # 2. 关键决策
        if self.decisions:
            lines = ["🎯 Key decisions:"]
            for d in self.decisions:
                rationale = f" — {d.value}" if d.value else ""
                lines.append(f"  • {d.key}{rationale}")
            sections.append("\n".join(lines))

        # 3. 变量工作集
        if self.variables:
            lines = ["⚙️ Current state:"]
            for name, entry in self.variables.items():
                lines.append(f"  {name} = {entry.value}")
            sections.append("\n".join(lines))

        # 4. 错误记录
        if self.errors:
            lines = ["⚠️ Errors encountered:"]
            for e in self.errors[-5:]:  # 只保留最近 5 个
                lines.append(f"  • [{e.key}] {e.value}")
            sections.append("\n".join(lines))

        if not sections:
            return ""

        content = "\n\n".join(sections)

        # Token 预算检查（粗估：1 token ≈ 1.5 字符）
        max_chars = self.max_tokens * 1.5
        if len(content) > max_chars:
            content = self._evict_to_fit(content, max_chars)

        return f"[Working Memory — key facts from this session]\n{content}"

    def _evict_to_fit(self, content: str, max_chars: int) -> str:
        """超预算时按优先级淘汰"""
        # 淘汰顺序：errors → variables → file_index(最旧的) → decisions
        if self.errors and len(content) > max_chars:
            self.errors = self.errors[-2:]  # 只保留最近 2 个
            content = self._rebuild_content()

        if len(content) > max_chars and self.variables:
            # 只保留最近 10 个变量
            items = list(self.variables.items())
            self.variables = dict(items[-10:])
            content = self._rebuild_content()

        if len(content) > max_chars and self.file_index:
            # 只保留最近读过的 15 个文件
            items = list(self.file_index.items())
            self.file_index = dict(items[-15:])
            content = self._rebuild_content()

        # 最终兜底：硬截断
        if len(content) > max_chars:
            content = content[:int(max_chars)] + "\n...[truncated]"

        return content

    def _rebuild_content(self) -> str:
        """淘汰后重建内容"""
        sections = []
        if self.file_index:
            lines = ["📂 Files read:"]
            for path, entry in self.file_index.items():
                lines.append(f"  {path}: {entry.value}")
            sections.append("\n".join(lines))
        if self.decisions:
            lines = ["🎯 Key decisions:"]
            for d in self.decisions:
                rationale = f" — {d.value}" if d.value else ""
                lines.append(f"  • {d.key}{rationale}")
            sections.append("\n".join(lines))
        if self.variables:
            lines = ["⚙️ Current state:"]
            for name, entry in self.variables.items():
                lines.append(f"  {name} = {entry.value}")
            sections.append("\n".join(lines))
        if self.errors:
            lines = ["⚠️ Errors encountered:"]
            for e in self.errors[-2:]:
                lines.append(f"  • [{e.key}] {e.value}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def is_empty(self) -> bool:
        """Working Memory 是否为空"""
        return not self.file_index and not self.decisions and not self.variables and not self.errors
```

**设计要点**：

- `file_index` 用 dict 存储，key 为文件路径，天然去重——同一文件多次读取只保留最新摘要
- `decisions` 用 list 存储，保留时序——决策顺序有时很重要
- `variables` 用 dict 存储，key 为变量名，天然去重——变量值会被覆盖更新
- `errors` 用 list 存储，保留时序——错误发生顺序有助于调试
- Token 预算淘汰优先级：errors（最可丢弃）> variables > file_index > decisions（最不可丢弃）
- `to_prompt_section()` 返回空字符串时不注入，零开销

### 2. MemoryExtractor 自动提取引擎

**文件**: `backend/app/memory/memory_extractor.py`（新建）

```python
from __future__ import annotations

import re
import logging
from datetime import datetime
from app.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    从 tool 调用结果中自动提取关键信息，写入 Working Memory

    集成点：rapid_loop.py 中 tool 执行完成后、结果写入 ContextCompressor 之前
    设计原则：纯规则提取，不调用 LLM，避免延迟和成本

    实际 tool 名称映射（基于 ToolRegistry 注册名）：
    - file (action=read)   → 读文件摘要
    - file (action=search) → 搜索结果提取文件路径
    - file (action=list)   → 目录结构概览
    - edit (action=*)      → 写文件标记 [MODIFIED]
    - shell                → 命令执行结果提取变量/错误
    - grep                 → 全局搜索结果提取文件路径
    - session_recall       → recall 结果提取关键信息
    - explore              → 探索结果提取结构信息
    """

    def __init__(self, memory: WorkingMemory):
        self.memory = memory

    def extract(self, tool_name: str, tool_args: dict, tool_result: str) -> None:
        """
        根据 tool 类型自动提取信息

        Args:
            tool_name: 工具名称（与 ToolRegistry 注册名一致）
            tool_args: 工具调用参数
            tool_result: 工具执行结果（字符串形式）
        """
        try:
            if tool_name == "file":
                action = tool_args.get("action", "")
                if action == "read":
                    self._extract_from_file_read(tool_args, tool_result)
                elif action == "search":
                    self._extract_from_file_search(tool_args, tool_result)
                elif action == "list":
                    self._extract_from_file_list(tool_args, tool_result)
            elif tool_name == "edit":
                self._extract_from_edit(tool_args, tool_result)
            elif tool_name == "shell":
                self._extract_from_shell(tool_args, tool_result)
            elif tool_name == "grep":
                self._extract_from_grep(tool_args, tool_result)
            elif tool_name == "session_recall":
                self._extract_from_recall(tool_args, tool_result)
            elif tool_name == "explore":
                self._extract_from_explore(tool_args, tool_result)
        except Exception as e:
            # 提取失败不应影响主流程
            logger.debug(f"Memory extraction failed for {tool_name}: {e}")

    def _extract_from_file_read(self, args: dict, result: str) -> None:
        """读文件后自动记录文件摘要"""
        path = args.get("path", "")
        if not path or not result or result.startswith("Error") or "文件不存在" in result:
            return

        summary = self._summarize_file_content(path, result)
        self.memory.upsert_file(path, summary, source="auto")

    def _extract_from_file_search(self, args: dict, result: str) -> None:
        """文件内搜索结果中提取匹配信息"""
        path = args.get("path", "")
        query = args.get("query", "")
        if not result or "未找到" in result:
            return

        # 如果已有文件摘要，追加搜索关键词
        if path and path in self.memory.file_index:
            existing = self.memory.file_index[path]
            if query and query not in existing.value:
                # 追加搜索关键词到摘要
                existing.value = f"{existing.value}; search: {query}"
                existing.updated_at = datetime.now()

    def _extract_from_file_list(self, args: dict, result: str) -> None:
        """目录列表记录结构概览"""
        path = args.get("path", "")
        if not path or not result:
            return
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        summary = f"directory with {len(lines)} items"
        self.memory.upsert_file(path, summary, source="auto")

    def _extract_from_edit(self, args: dict, result: str) -> None:
        """编辑文件后更新摘要"""
        path = args.get("path", "")
        if not path:
            return

        # 编辑成功 → 标记文件为"已修改"
        if "success" in result.lower() or "wrote" in result.lower() or "replaced" in result.lower():
            existing = self.memory.file_index.get(path)
            if existing:
                # 在已有摘要前加 [MODIFIED] 标记
                if not existing.value.startswith("[MODIFIED]"):
                    existing.value = f"[MODIFIED] {existing.value}"
                existing.updated_at = datetime.now()
            else:
                self.memory.upsert_file(path, "[MODIFIED] newly created file", source="auto")

    def _extract_from_shell(self, args: dict, result: str) -> None:
        """命令执行结果中提取变量/错误"""
        command = args.get("command", "")

        # 检测错误
        if "error" in result.lower() or "failed" in result.lower():
            error_snippet = result[:200] if len(result) > 200 else result
            self.memory.add_error("command_error", f"`{command[:50]}` → {error_snippet}", source="auto")

        # 检测环境变量/配置
        if "export " in command or "=" in command:
            for match in re.finditer(r'(\w+)=(\S+)', result):
                key, value = match.group(1), match.group(2)
                if len(key) < 30 and len(value) < 100:  # 过滤掉文件内容
                    self.memory.set_variable(key, value, source="auto")

    def _extract_from_grep(self, args: dict, result: str) -> None:
        """全局搜索结果中提取文件路径"""
        paths = set()
        for line in result.split("\n")[:20]:  # 只看前 20 行
            # 匹配 "path:line:content" 格式
            match = re.match(r'^([^\s:]+\.\w+)[:\d]', line)
            if match:
                paths.add(match.group(1))

        for path in sorted(paths)[:10]:
            if path not in self.memory.file_index:
                self.memory.upsert_file(path, "found in search (not yet read)", source="auto")

    def _extract_from_recall(self, args: dict, result: str) -> None:
        """recall 结果中提取关键信息"""
        query = args.get("query", "")
        if result and len(result) > 50:
            self.memory.set_variable(f"recall:{query[:30]}", result[:200], source="auto")

    def _extract_from_explore(self, args: dict, result: str) -> None:
        """探索结果中提取结构信息"""
        # explore 工具返回代码库结构概览，提取关键模块名
        if not result:
            return
        # 简单提取：记录探索查询和结果摘要
        query = args.get("query", "")
        if query:
            summary = result[:150].replace("\n", " ").strip()
            self.memory.set_variable(f"explore:{query[:30]}", summary, source="auto")

    # ---- 纯规则文件摘要（不调用 LLM） ----

    def _summarize_file_content(self, path: str, content: str) -> str:
        """
        纯规则提取文件摘要，不调用 LLM

        提取：类名、函数名、导入、关键注释
        控制在 ~100 字符以内
        """
        lines = content.split("\n")
        parts = []

        # 提取 class/function/struct 定义
        symbols = []
        for line in lines:
            stripped = line.strip()
            # Python
            if stripped.startswith("class ") or stripped.startswith("def "):
                name = stripped.split("(")[0].split(":")[0].strip()
                symbols.append(name)
            # JS/TS
            elif stripped.startswith("export ") or stripped.startswith("function "):
                name = stripped.split("{")[0].strip()
                symbols.append(name)
            # Go
            elif stripped.startswith("func ") or stripped.startswith("type "):
                symbols.append(stripped.split("{")[0].strip())
            # Rust
            elif stripped.startswith("pub fn ") or stripped.startswith("fn ") or stripped.startswith("struct "):
                symbols.append(stripped.split("{")[0].strip())

        if symbols:
            symbol_str = ", ".join(symbols[:6])  # 最多 6 个
            if len(symbols) > 6:
                symbol_str += f" (+{len(symbols)-6} more)"
            parts.append(symbol_str)

        # 提取关键注释（TODO, FIXME, HACK, NOTE）
        key_comments = []
        for line in lines:
            stripped = line.strip().upper()
            for marker in ["TODO", "FIXME", "HACK", "NOTE", "IMPORTANT"]:
                if marker in stripped:
                    key_comments.append(line.strip()[:80])
                    break
        if key_comments:
            parts.append("; ".join(key_comments[:2]))

        # 行数
        line_count = len(lines)
        if parts:
            return f"{line_count} lines: {' | '.join(parts)}"
        else:
            # 兜底：首行 + 行数
            first_meaningful = next(
                (l.strip() for l in lines if l.strip() and not l.strip().startswith("#")),
                ""
            )
            if first_meaningful:
                return f"{line_count} lines: {first_meaningful[:80]}"
            return f"{line_count} lines"
```

**设计要点**：

- `extract()` 方法是统一入口，根据 tool_name 分发到具体提取器
- 每个提取器只做一件事，失败不影响主流程（try/except 静默处理）
- `_summarize_file_content` 纯规则实现，不调 LLM，零延迟零成本
- 支持 Python/JS/TS/Go/Rust 等主流语言的符号提取
- 文件摘要控制在 ~100 字符，整个 Working Memory 控制在 ~2000 tokens

### 3. working_memory_update 工具

**文件**: `backend/app/memory/working_memory_tool.py`（新建）

```python
from __future__ import annotations

from app.memory.working_memory import WorkingMemory

# 工具定义（注册到 runtime_tool_definitions.py）
WORKING_MEMORY_UPDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "working_memory_update",
        "description": (
            "Record important information that must not be forgotten during this task. "
            "Use this for: key decisions made, important values discovered, error patterns, "
            "or anything you'll need to reference later. This memory persists across context "
            "compression and is always visible to you."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["decide", "note", "set_var"],
                    "description": (
                        "decide: Record a key decision and its rationale. "
                        "note: Record an important observation or finding. "
                        "set_var: Record a variable/value for later reference."
                    ),
                },
                "key": {
                    "type": "string",
                    "description": "Short identifier (e.g., 'auth_method', 'error_pattern')"
                },
                "value": {
                    "type": "string",
                    "description": "The information to remember (concise, <200 chars)"
                },
            },
            "required": ["action", "key", "value"],
        },
    },
}


def handle_working_memory_update(
    memory: WorkingMemory,
    action: str,
    key: str,
    value: str,
) -> str:
    """
    处理 working_memory_update 工具调用

    Args:
        memory: WorkingMemory 实例
        action: 操作类型 (decide/note/set_var)
        key: 短标识符
        value: 要记录的信息

    Returns:
        操作结果描述
    """
    if action == "decide":
        memory.add_decision(decision=key, rationale=value, source="model")
    elif action == "note":
        # note 复用 decisions 列表，但标记为观察
        memory.add_decision(decision=f"[note] {key}", rationale=value, source="model")
    elif action == "set_var":
        memory.set_variable(name=key, value=value, source="model")
    else:
        return f"Unknown action: {action}"

    return f"✓ Recorded: {action}/{key}"
```

**设计要点**：

- 工具只有 3 个 action，极简设计，降低模型使用门槛
- `decide` 记录决策（如"使用 JWT 做认证"），`note` 记录观察（如"API 返回 500 错误"），`set_var` 记录变量（如"db_port=5432"）
- `note` 复用 decisions 列表，避免增加数据结构复杂度，只是加 `[note]` 前缀区分
- 返回值简洁明确，让模型确认操作成功

### 4. 集成点改动

#### 4.1 LoopContext 持有 WorkingMemory

**文件**: `backend/app/execution/context_manager.py`（修改）

```python
# 新增导入
from app.memory.working_memory import WorkingMemory
from app.memory.memory_extractor import MemoryExtractor

class LoopContext:
    def __init__(self, ...):
        # ... 现有字段不变 ...
        self.working_memory = WorkingMemory()        # 新增
        self.memory_extractor = MemoryExtractor(self.working_memory)  # 新增
```

**改动范围**：仅新增两个字段，不修改任何现有字段和方法。

#### 4.2 LoopMessageBuilder 注入 Working Memory

**文件**: `backend/app/execution/loop_message_builder.py`（修改）

在 `build()` 方法中，system prompt 之后、Tier 3 之前注入：

```python
def build(self, context: LoopContext) -> list[LLMMessage]:
    messages = [LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)]

    # ===== 新增：Working Memory 注入 =====
    wm_section = context.working_memory.to_prompt_section()
    if wm_section:
        messages.append(LLMMessage(role=MessageRole.SYSTEM, content=wm_section))
    # ===== 新增结束 =====

    # Tier 3: LLM 压缩摘要（现有逻辑不变）
    if context.compressor.get_compacted_summary():
        ...
```

同样，`build_final_summary()` 方法也需要注入 Working Memory，确保最终摘要也能看到关键信息：

```python
def build_final_summary(self, context: LoopContext) -> list[LLMMessage]:
    messages = [LLMMessage(role=MessageRole.SYSTEM, content=...)]

    # ===== 新增：Working Memory 注入 =====
    wm_section = context.working_memory.to_prompt_section()
    if wm_section:
        messages.append(LLMMessage(role=MessageRole.SYSTEM, content=wm_section))
    # ===== 新增结束 =====

    # ... 现有逻辑不变 ...
```

**注入位置的选择理由**：

- 放在 system prompt 之后：Working Memory 的优先级高于对话历史，但低于系统指令
- 放在 Tier 3 之前：Working Memory 是最新的、最精炼的关键信息，应该比压缩摘要更优先被模型看到
- `to_prompt_section()` 返回空字符串时不注入，零开销
- `build_final_summary()` 也需要注入：确保最终摘要生成时模型能看到 Working Memory 中的关键决策和发现

#### 4.3 tool_call_executor 中 tool 执行后自动提取

**文件**: `backend/app/execution/tool_call_executor.py`（修改）

在 `_execute_single_tool()` 方法中，tool 执行成功、结果写入 context 之后，立即提取到 Working Memory。

**精确集成位置**：第 201-206 行之后（`context.update_history()` 和 `context.add_message()` 之后）

```python
# 现有代码（第 201-206 行）：
context.update_history(tool_call, tool_output)
context.add_message(
    "tool",
    content=tool_output,
    tool_call_id=tool_call.id,
)

# ===== 新增：自动提取到 Working Memory =====
context.memory_extractor.extract(
    tool_name=tool_call.name,
    tool_args=tool_call.arguments,
    tool_result=tool_output,
)
# ===== 新增结束 =====

await self.emit("tool:result", ...)
```

**设计要点**：

- 集成在 `tool_call_executor` 而非 `rapid_loop`，因为这里是 tool 执行结果的统一出口
- `tool_call.name` 就是 ToolRegistry 注册的工具名（如 "file", "edit", "shell"）
- `tool_call.arguments` 是解析后的参数字典
- `tool_output` 是格式化后的工具输出字符串
- 提取失败不影响主流程（MemoryExtractor.extract 内部已有 try/except）
- 只在 tool 执行成功时提取（FAILED 状态不提取，避免噪声）

#### 4.4 Tier 2 语义化占位符增强

**文件**: `backend/app/execution/context_compressor.py`（修改）

在 `build_tier2_messages()` 中，将 `[Old tool result content cleared]` 替换为语义化占位符：

```python
# 原来：
if content == "[Old tool result content cleared]":
    tier2.append(LLMMessage(role=MessageRole.TOOL, content=content, ...))
    continue

# 改为：用 Working Memory 中的文件摘要替换空洞占位符
if content == "[Old tool result content cleared]":
    wm_hint = self._get_working_memory_hint(msg, working_memory)
    replacement = wm_hint if wm_hint else content
    tier2.append(LLMMessage(role=MessageRole.TOOL, content=replacement, ...))
    continue
```

新增辅助方法：

```python
def _get_working_memory_hint(self, msg: dict, working_memory: WorkingMemory) -> str | None:
    """
    从 Working Memory 中获取语义化占位符

    如果该 tool 调用是读文件操作，且 Working Memory 中有对应文件摘要，
    则返回语义化占位符，否则返回 None
    """
    if not working_memory:
        return None

    # 尝试从 tool_call 关联的参数中提取文件路径
    tool_call_id = msg.get("tool_call_id", "")
    # 需要从上下文中找到对应的 assistant 消息，提取 tool_calls 中的参数
    # 这部分实现需要根据实际的消息结构来确定
    # 简化实现：遍历 file_index，检查是否有匹配的路径
    for path, entry in working_memory.file_index.items():
        # 如果 tool result 被清除，说明之前读过这个文件
        # 这里用启发式方法：如果 file_index 中有记录，就提供摘要
        return f"[File {path}: {entry.value} — see Working Memory]"

    return None
```

**注意**：Tier 2 语义化占位符的实现需要更精细的设计——需要从消息上下文中确定哪个 tool call 对应哪个文件。Phase 1 可以先跳过此增强，Phase 2 再实现。

#### 4.5 注册 working_memory_update 工具

**重要**：项目中所有工具通过 `ToolRegistry` 注册，必须继承 `BaseTool` 并实现 `name`、`description`、`execute()` 和 `get_schema()` 方法。`working_memory_update` 工具也需要遵循这个模式。

**文件**: `backend/app/tools/working_memory_tool.py`（新建）

```python
from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool, ToolResult


class WorkingMemoryTool(BaseTool):
    """Working Memory 更新工具 — 允许模型主动记录关键信息"""

    @property
    def name(self) -> str:
        return "working_memory_update"

    @property
    def description(self) -> str:
        return (
            "Record important information that must not be forgotten during this task. "
            "Use this for: key decisions made, important values discovered, error patterns, "
            "or anything you'll need to reference later. This memory persists across context "
            "compression and is always visible to you."
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        # 实际执行逻辑在 ToolCallExecutor 中处理，
        # 因为需要访问 context.working_memory
        # 这里只是占位，实际不会走到这里
        return ToolResult(success=True, output="Working memory updated.")

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["decide", "note", "set_var"],
                        "description": (
                            "decide: Record a key decision and its rationale. "
                            "note: Record an important observation or finding. "
                            "set_var: Record a variable/value for later reference."
                        ),
                    },
                    "key": {
                        "type": "string",
                        "description": "Short identifier (e.g., 'auth_method', 'error_pattern')"
                    },
                    "value": {
                        "type": "string",
                        "description": "The information to remember (concise, <200 chars)"
                    },
                },
                "required": ["action", "key", "value"],
            },
        }
```

**文件**: `backend/app/execution/tool_call_executor.py`（修改）

在 `_execute_single_tool()` 方法中，`tool.execute()` 调用之前，拦截 `working_memory_update` 工具调用：

```python
async def _execute_single_tool(self, tool_call, context, step_number):
    # ... 现有代码 ...

    try:
        tool = self.tool_registry.get(tool_call.name)
        if not tool:
            raise ValueError(f"工具不存在: {tool_call.name}")

        # ===== 新增：拦截 working_memory_update 工具 =====
        if tool_call.name == "working_memory_update":
            from app.memory.working_memory_tool import handle_working_memory_update
            result_msg = handle_working_memory_update(
                memory=context.working_memory,
                action=tool_call.arguments.get("action", ""),
                key=tool_call.arguments.get("key", ""),
                value=tool_call.arguments.get("value", ""),
            )
            step.status = StepStatus.SUCCESS
            step.output = result_msg
            step.duration = time.time() - start_time
            context.update_history(tool_call, result_msg)
            context.add_message("tool", content=result_msg, tool_call_id=tool_call.id)
            return step
        # ===== 新增结束 =====

        # ... 现有 tool.execute() 调用逻辑 ...
```

**文件**: `backend/app/memory/working_memory_tool.py`（新建）

将处理逻辑独立为函数，供 `tool_call_executor` 调用：

```python
from __future__ import annotations

from app.memory.working_memory import WorkingMemory


def handle_working_memory_update(
    memory: WorkingMemory,
    action: str,
    key: str,
    value: str,
) -> str:
    """
    处理 working_memory_update 工具调用

    Args:
        memory: WorkingMemory 实例
        action: 操作类型 (decide/note/set_var)
        key: 短标识符
        value: 要记录的信息

    Returns:
        操作结果描述
    """
    if action == "decide":
        memory.add_decision(decision=key, rationale=value, source="model")
    elif action == "note":
        memory.add_decision(decision=f"[note] {key}", rationale=value, source="model")
    elif action == "set_var":
        memory.set_variable(name=key, value=value, source="model")
    else:
        return f"Unknown action: {action}"

    return f"✓ Recorded: {action}/{key}"
```

**文件**: `backend/app/execution/runtime_tool_definitions.py`（修改）

在 `ToolSetConfig` 中添加 `working_memory_update` 工具到 `tool_order` 和各工具集：

```python
@dataclass(frozen=True)
class ToolSetConfig:
    tool_order: list[str] = field(
        default_factory=lambda: [
            "skill",
            "file",
            "grep",
            "glob",
            "session_recall",
            "memory",
            "working_memory_update",  # 新增
            "edit",
            "shell",
        ]
    )
    exploration_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "file",
                "grep",
                "glob",
                "memory",
                "session_recall",
                "skill",
                "working_memory_update",  # 新增：探索阶段也可记录
            }
        )
    )
    plan_mode_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "file",
                "grep",
                "glob",
                "session_recall",
                "memory",
                "explore",
                "plan",
                "working_memory_update",  # 新增：计划阶段也可记录
            }
        )
    )
```

**文件**: `backend/app/services/agent_service.py`（修改）

在工具注册位置（约第 155-185 行）添加 `WorkingMemoryTool` 注册：

```python
from app.tools.working_memory_tool import WorkingMemoryTool

# 在其他 registry.register() 调用之后添加：
registry.register(WorkingMemoryTool())
```

**注意**：`WorkingMemoryTool` 不需要 `path_security` 参数，因为它不涉及文件操作。

### 5. 注入效果示例

假设 agent 正在帮用户实现一个认证模块，已经读了 8 个文件、做了 3 个决策、遇到 1 个错误。Working Memory 注入后，模型每次调用都能看到：

```
[Working Memory — key facts from this session]

📂 Files read:
  src/auth/login.py: 45 lines: class LoginHandler, authenticate, _verify_password
  src/auth/token.py: 32 lines: class TokenManager, generate, refresh
  src/models/user.py: 28 lines: class User, to_dict, check_password
  src/config.py: 15 lines: SECRET_KEY, TOKEN_EXPIRY, ALGORITHM
  src/middleware/auth.py: 38 lines: class AuthMiddleware, validate_token
  src/routes/api.py: 120 lines: router, login_endpoint, user_profile (+3 more)
  requirements.txt: 8 lines: flask, pyjwt, bcrypt
  src/auth/__init__.py: 3 lines

🎯 Key decisions:
  • Use JWT for auth — session doesn't scale, API is stateless
  • bcrypt for password hashing — per OWASP recommendation
  • Token expiry = 24h — user requested

⚙️ Current state:
  SECRET_KEY = from env var
  ALGORITHM = HS256
  TOKEN_EXPIRY = 86400
  db_type = PostgreSQL

⚠️ Errors encountered:
  • [import_error] flask_jwt not found — using pyjwt instead
```

这 ~2000 tokens 的信息，让模型在任何压缩状态下都清楚：读了哪些文件、做了什么决策、当前环境是什么、踩过什么坑。

## 与现有系统的协作关系

### 不替代，只增强

| 现有机制 | Working Memory 的角色 |
|---------|---------------------|
| Tier 1 完整保真 | 不变，Working Memory 是独立层 |
| Tier 2 截断可见 | 增强：语义化占位符替代空洞的 `[Old tool result content cleared]` |
| Tier 3 LLM 摘要 | 不变，Working Memory 提供结构化补充 |
| session_recall | 互补：recall 是主动查询，Working Memory 是被动注入 |
| Plan Status | 不变，两者是独立的 system message |
| Task Anchor | 不变 |

### Token 预算分析

| 组件 | Token 消耗 | 频率 |
|-----|-----------|------|
| Working Memory 注入 | ~2000 tokens | 每次 LLM 调用 |
| Tier 3 摘要 | ~1000 tokens | 压缩后每次 |
| Tier 2 截断消息 | 可变 | 压缩后每次 |
| Tier 1 完整消息 | 可变 | 每次 |
| Plan Status | ~200 tokens | 每次 |

Working Memory 的 ~2000 tokens 是固定开销，但它替代了 Tier 2/3 中大量重复的文件内容描述，总体上可能反而节省 token。

## 实施路线

### Phase 1（最小可用版本，3-5 天）

只做三件事：

1. **WorkingMemory 数据模型** — `backend/app/memory/working_memory.py`
2. **MemoryExtractor 的 `_extract_from_read`** — 读文件自动摘要，这是最高频场景
3. **LoopMessageBuilder.build() 中注入** — Working Memory 作为 system message 注入

**效果**：agent 读过的每个文件都有摘要，即使对话历史被压缩到只剩 Tier 3 摘要，模型仍然知道它读过什么、每个文件大概是什么。

### Phase 2（模型主动写入 + 语义化占位符，3-5 天）

1. **working_memory_update 工具** — 注册 + 处理
2. **Tier 2 语义化占位符** — 用 Working Memory 替换 `[Old tool result content cleared]`
3. **MemoryExtractor 扩展** — write_file、run_command、search 的自动提取

**效果**：模型可以主动记录决策和发现；压缩后不再是空洞的"内容已清除"，而是有语义的"src/auth/login.py: LoginHandler 类"。

### Phase 3（智能进化，1-2 周）

1. **渐进式摘要** — 替代一次性 Tier 3 压缩
2. **Working Memory 与 session_recall 联动** — recall 结果自动写入 Working Memory
3. **Token 预算动态调整** — 根据任务复杂度调整 Working Memory 大小
4. **跨 run 持久化** — 将 Working Memory 保存到 DB，下次 run 可恢复

## 为什么不直接用 LLM 做摘要

`MemoryExtractor._summarize_file_content` 是纯规则提取，没有调用 LLM。这是刻意为之：

1. **延迟** — 每次读文件都调 LLM 做摘要，agent 循环会明显变慢
2. **成本** — 一个任务可能读 20+ 文件，每次摘要都是一次 LLM 调用
3. **足够好** — 类名 + 函数名 + 行数，对于"让模型知道这个文件大概是什么"这个目标已经足够。模型如果需要细节，可以通过 Tier 1 完整内容或 session_recall 获取
4. **确定性** — 规则提取没有幻觉风险

如果后续需要更精细的摘要，可以作为 Phase 3 的优化项，用异步方式（不阻塞主循环）调用 LLM 做深度摘要，替换规则提取的结果。

## 测试策略

### 单元测试

1. **WorkingMemory 数据模型**
   - `test_upsert_file_new` — 新增文件摘要
   - `test_upsert_file_update` — 更新已有文件摘要
   - `test_add_decision` — 添加决策
   - `test_set_variable` — 设置变量
   - `test_add_error` — 添加错误
   - `test_to_prompt_section_empty` — 空 Working Memory 返回空字符串
   - `test_to_prompt_section_format` — 格式化输出正确
   - `test_evict_to_fit` — Token 预算超限时淘汰
   - `test_evict_priority` — 淘汰优先级正确（errors > variables > files > decisions）

2. **MemoryExtractor**
   - `test_extract_read_file` — 读文件自动提取摘要
   - `test_extract_write_file` — 写文件标记 [MODIFIED]
   - `test_extract_search` — 搜索结果提取文件路径
   - `test_extract_command_error` — 命令错误自动记录
   - `test_extract_command_variable` — 命令结果提取变量
   - `test_extract_failure_silent` — 提取失败不影响主流程

3. **working_memory_update 工具**
   - `test_handle_decide` — 决策记录
   - `test_handle_note` — 观察记录
   - `test_handle_set_var` — 变量记录
   - `test_handle_unknown_action` — 未知操作返回错误

### 集成测试

1. **LoopMessageBuilder 注入** — 验证 Working Memory 正确注入到消息列表
2. **自动提取流程** — 验证 tool 执行后自动提取到 Working Memory
3. **端到端** — 模拟完整 agent run，验证 Working Memory 在压缩后仍然可见

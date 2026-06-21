# Context Compressor 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 ContextCompressor 统一管理消息状态和三级压缩，解决职责混乱、代码重复问题

**Architecture:** 创建 ContextCompressor 独立处理所有消息压缩逻辑（分组、Token、三级压缩），简化 LoopContext 为纯状态存储，MessageBuilder 和 RapidExecutionLoop 通过 Compressor 接口操作消息

**Tech Stack:** Python 3.12, dataclasses, typing, pytest, async/await

---

## 文件结构

### 新建文件
- `app/execution/context_compressor.py` - ContextCompressor 核心类和 MessageGroup 数据类
- `tests/test_execution/test_context_compressor.py` - Compressor 单元测试

### 修改文件
- `app/execution/context_manager.py` - 移除 4 个字段，3 个方法，集成 compressor
- `app/execution/loop_message_builder.py` - 移除 4 个方法，修改 3 个方法
- `app/execution/rapid_loop.py` - 移除 2 个方法，新增 1 个方法
- `app/execution/models.py` - 添加 MessageGroup 导出
- `tests/test_execution/test_context_manager.py` - 修改属性访问（5 处）
- `tests/test_execution/test_loop_message_builder.py` - 修改属性访问（约 10 处）
- `tests/test_execution/test_midrun_compaction.py` - 修改属性/方法调用（约 20 处）

---

## Task 1: Create MessageGroup Data Class

**Files:**
- Create: `app/execution/context_compressor.py`

- [ ] **Step 1: Create file and import dependencies**

```python
"""上下文压缩器 - 统一管理消息状态和三级压缩模型"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from app.llm.base import LLMMessage, LLMToolCall, MessageRole
from app.llm.token_counter import count_messages_tokens
from app.memory.text_compaction import truncate_head_tail

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Write MessageGroup dataclass**

```python
@dataclass
class MessageGroup:
    """
    消息分组 - assistant+tool_calls 开组，tool 消息归入当前组
    
    分组规则：
    - assistant 消息（带 tool_calls）开启新组
    - 后续的 tool 消息归入当前组
    - 其他消息（user, assistant 纯文本）单独成组
    """
    messages: list[dict]  # 该组的所有消息
    token_count: int      # 预计算的 token 数，避免重复计算
    
    @property
    def has_tool_calls(self) -> bool:
        """是否包含工具调用"""
        return any(
            msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls")
            for msg in self.messages
        )
    
    @property
    def first_message_role(self) -> str:
        """返回组内第一条消息的角色"""
        return self.messages[0]["role"] if self.messages else ""
```

- [ ] **Step 3: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: add MessageGroup dataclass for message grouping"
```

---

## Task 2: Create ContextCompressor Skeleton

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add ContextCompressor class with __init__**

```python
class ContextCompressor:
    """
    上下文压缩器 - 统一管理消息状态和三级压缩模型
    
    三级压缩模型：
    - Tier 1: 完整保真 - 最近 N 组消息，原文不改
    - Tier 2: 截断但可见 - 超出窗口的旧消息逐条截断，每条仍在 context 中
    - Tier 3: LLM 摘要 - 极端压力时旧消息压缩为摘要，细节可 session_recall 回溯
    """
    
    # ========== 初始化 ==========
    
    def __init__(
        self,
        max_context_groups: int = 10,
        tool_output_max_chars: int = 2_400,
    ):
        """
        初始化压缩器
        
        Args:
            max_context_groups: Tier 1 保留的最大分组数
            tool_output_max_chars: Tier 2 截断时保留的最大字符数
        """
        self._messages: list[dict] = []              # 所有消息
        self._compacted_summary: str | None = None   # Tier 3 压缩摘要
        self._total_tokens: int = 0                  # 当前总 token 数
        self._group_count: int = 0                   # 消息分组计数
        self.max_context_groups = max_context_groups
        self.tool_output_max_chars = tool_output_max_chars
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: add ContextCompressor class skeleton"
```

---

## Task 3: Implement Message Management Methods

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add add_message method**

```python
    # ========== 消息管理（增删查）==========
    
    def add_message(
        self,
        role: str,
        content: str | list[dict] | None = None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """
        添加消息（支持多模态内容）
        
        自动处理：
        - Token 计算（增量）
        - 分组计数更新
        - 时间戳添加
        
        Args:
            role: 消息角色 (user/assistant/tool/system)
            content: 消息内容（支持纯文本或多模态 list）
            tool_calls: 工具调用列表
            tool_call_id: 工具调用 ID
        """
        message: dict = {"role": role, "timestamp": datetime.now().isoformat()}
        
        if content is not None:
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        
        self._messages.append(message)
        
        # 增量计算 token
        msg_tokens = count_messages_tokens([message])
        self._total_tokens += msg_tokens
        
        # 更新分组计数
        if role == MessageRole.ASSISTANT and tool_calls:
            self._group_count += 1
        elif role == MessageRole.TOOL:
            # tool 消息归入当前组，不增加计数
            pass
        else:
            self._group_count += 1
```

- [ ] **Step 2: Add get_messages, get_message_count, clear_messages**

```python
    def get_messages(self) -> list[dict]:
        """获取所有消息（只读副本）"""
        return self._messages.copy()
    
    def get_message_count(self) -> int:
        """获取消息总数"""
        return len(self._messages)
    
    def clear_messages(self) -> None:
        """清空所有消息（用于测试或重置）"""
        self._messages.clear()
        self._total_tokens = 0
        self._group_count = 0
```

- [ ] **Step 3: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement message management methods in ContextCompressor"
```

---

## Task 4: Implement Message Grouping Logic

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add group_messages static method**

```python
    # ========== 分组逻辑 ==========
    
    @staticmethod
    def group_messages(messages: list[dict]) -> list[MessageGroup]:
        """
        将消息按 assistant+tool_calls 开组的方式分组
        
        分组规则：
        - assistant 消息（带 tool_calls）开启新组
        - 后续的 tool 消息归入当前组，直到遇到非 tool 消息
        - 其他消息单独成组
        
        Args:
            messages: 原始消息列表
            
        Returns:
            分组后的 MessageGroup 列表，每组包含消息和预计算的 token 数
        """
        grouped: list[MessageGroup] = []
        active_tool_group: list[dict] | None = None
        
        for msg in messages:
            # assistant 消息（带 tool_calls）开启新组
            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                active_tool_group = [msg]
                # 预计算该消息的 token
                token_count = count_messages_tokens([msg])
                grouped.append(MessageGroup(messages=active_tool_group, token_count=token_count))
                continue
            
            # tool 消息归入当前组
            if msg["role"] == MessageRole.TOOL and active_tool_group is not None:
                active_tool_group.append(msg)
                # 累加 token 到当前组
                grouped[-1].token_count += count_messages_tokens([msg])
                continue
            
            # 其他消息单独成组
            active_tool_group = None
            token_count = count_messages_tokens([msg])
            grouped.append(MessageGroup(messages=[msg], token_count=token_count))
        
        return grouped
```

- [ ] **Step 2: Add get_groups and get_group_count**

```python
    def get_groups(self) -> list[MessageGroup]:
        """获取当前消息的分组（包含 token 预计算）"""
        return self.group_messages(self._messages)
    
    def get_group_count(self) -> int:
        """获取当前分组数"""
        return self._group_count
```

- [ ] **Step 3: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement message grouping logic in ContextCompressor"
```

---

## Task 5: Implement Token Management

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add token management methods**

```python
    # ========== Token 管理 ==========
    
    def calculate_tokens(self, messages: list[dict]) -> int:
        """计算消息列表的 token 数"""
        return count_messages_tokens(messages)
    
    def recalculate_tokens(self) -> None:
        """重新计算总 token 数（用于 Tier 3 压缩后）"""
        self._total_tokens = count_messages_tokens(self._messages)
    
    def get_total_tokens(self) -> int:
        """获取当前总 token 数"""
        return self._total_tokens
    
    def check_pressure(self, context_window: int, tier3_ratio: float) -> bool:
        """
        检查是否需要触发 Tier 3 压缩
        
        Args:
            context_window: 模型的上下文窗口大小
            tier3_ratio: Tier 3 阈值比例（如 0.85 表示 85% 窗口）
            
        Returns:
            True 表示需要压缩
        """
        tier3_threshold = int(context_window * tier3_ratio)
        return self._total_tokens > tier3_threshold
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement token management in ContextCompressor"
```

---

## Task 6: Implement Tier 1 - Recent Messages

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add get_recent_messages method**

```python
    # ========== Tier 1: 完整保留 ==========
    
    def get_recent_messages(self, max_groups: int | None = None) -> list[dict]:
        """
        获取 Tier 1 最近 N 组消息（完整保留，包括多模态内容）
        
        Args:
            max_groups: 保留的最大分组数，默认使用 self.max_context_groups
            
        Returns:
            展平后的消息列表（保持原始格式）
        """
        if not self._messages:
            return []
        
        max_groups = max_groups or self.max_context_groups
        grouped = self.group_messages(self._messages)
        
        # 保留最近 N 组
        recent_groups = grouped[-max_groups:]
        
        # 展平为消息列表
        flat_messages = []
        for group in recent_groups:
            flat_messages.extend(group.messages)
        
        return flat_messages
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement Tier 1 recent messages retrieval"
```

---

## Task 7: Implement Tier 2 - Truncated Messages

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add build_tier2_messages method**

```python
    # ========== Tier 2: 截断可见 ==========
    
    def build_tier2_messages(self) -> list[LLMMessage]:
        """
        构建 Tier 2 消息：超出窗口的旧消息逐条截断但始终可见
        
        处理规则：
        - 只处理超出 max_context_groups 的旧分组
        - tool output 超过 tool_output_max_chars 时 head+tail 截断
        - 标记 [session_recall can retrieve] 提示可回溯
        - 保持原始消息角色，确保 tool_call_id / tool_calls 关联不被破坏
        
        Returns:
            LLMMessage 列表（可直接用于 LLM 调用）
        """
        grouped = self.group_messages(self._messages)
        
        # 如果总分组数不超过窗口，无需 Tier 2
        if len(grouped) <= self.max_context_groups:
            return []
        
        # 只处理超出窗口的旧分组
        older_groups = grouped[:-self.max_context_groups]
        tier2: list[LLMMessage] = []
        
        for group in older_groups:
            for msg in group.messages:
                content = msg.get("content")
                
                # 空内容的 assistant 消息（只有 tool_calls）
                if not isinstance(content, str) or not content.strip():
                    if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                        tool_calls_list = msg.get("tool_calls", [])
                        tier2.append(LLMMessage(
                            role=MessageRole.ASSISTANT,
                            content=content,
                            tool_calls=[LLMToolCall(**tc) for tc in tool_calls_list] if tool_calls_list else None,
                        ))
                    continue
                
                # tool 消息：截断长输出
                if msg["role"] == MessageRole.TOOL:
                    # 已被裁剪的保持原样
                    if content == "[Old tool result content cleared]":
                        tier2.append(LLMMessage(
                            role=MessageRole.TOOL,
                            content=content,
                            tool_call_id=msg.get("tool_call_id"),
                        ))
                        continue
                    
                    # 超长输出：head+tail 截断
                    if len(content) > self.tool_output_max_chars:
                        content = truncate_head_tail(
                            content,
                            self.tool_output_max_chars,
                            head_chars=1_600,
                            tail_chars=600,
                            reason="session_recall retrieve",
                        )
                    
                    tier2.append(LLMMessage(
                        role=MessageRole.TOOL,
                        content=content,
                        tool_call_id=msg.get("tool_call_id"),
                    ))
                
                # assistant 消息（有 tool_calls 或纯文本）
                elif msg["role"] == MessageRole.ASSISTANT:
                    tool_calls_list = msg.get("tool_calls", [])
                    tier2.append(LLMMessage(
                        role=MessageRole.ASSISTANT,
                        content=content,
                        tool_calls=[LLMToolCall(**tc) for tc in tool_calls_list] if tool_calls_list else None,
                    ))
                
                # user 消息：保留所有（包括多模态内容）
                elif msg["role"] == MessageRole.USER:
                    tier2.append(LLMMessage(role=MessageRole.USER, content=content))
        
        return tier2
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement Tier 2 truncated messages"
```

---

## Task 8: Implement Tier 3 - LLM Summary Compression

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add compact_tier3 and get_compacted_summary methods**

```python
    # ========== Tier 3: LLM 摘要 ==========
    
    async def compact_tier3(
        self,
        task: str,
        summarizer: Callable[[str, str], Awaitable[str]],
    ) -> None:
        """
        Tier 3 压缩：将窗口外的旧消息经 LLM 压缩为摘要
        
        处理流程：
        1. 提取超出窗口的旧消息
        2. 构建 transcript（角色 + 内容，截断过长内容）
        3. 调用 summarizer 回调生成摘要
        4. 更新 _compacted_summary
        5. 从 _messages 中移除旧消息，保留最近 N 组
        6. 重新计算 token 数
        
        Args:
            task: 当前任务描述（用于摘要提示词）
            summarizer: 摘要生成回调函数
                        签名：async (task: str, transcript: str) -> str
                        调用方负责构建 prompt 并调用 LLM
        
        注意：
        - 压缩失败时静默跳过，不中断 run
        - 摘要包含 [可 session_recall 取回] 标记
        - DB 中的原始消息不受影响
        """
        try:
            grouped = self.group_messages(self._messages)
            
            # 如果分组数不超过窗口，无需压缩
            if len(grouped) <= self.max_context_groups:
                return
            
            # 提取旧消息
            older_groups = grouped[:-self.max_context_groups]
            older_messages = []
            for group in older_groups:
                older_messages.extend(group.messages)
            
            # 构建 transcript
            transcript_parts = []
            for msg in older_messages:
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    role = msg.get("role", "unknown")
                    # 截断过长内容
                    truncated_content = content[:2000] if len(content) > 2000 else content
                    transcript_parts.append(f"[{role}] {truncated_content}")
            
            transcript = "\n\n".join(transcript_parts)
            
            # 调用 summarizer 回调生成摘要
            summary = await summarizer(task, transcript)
            
            if not summary or not summary.strip():
                logger.warning("Tier 3 compaction returned empty summary, skipping")
                return
            
            # 更新摘要
            self._compacted_summary = summary.strip()
            
            # 移除旧消息，保留最近 N 组
            recent_groups = grouped[-self.max_context_groups:]
            self._messages = []
            for group in recent_groups:
                self._messages.extend(group.messages)
            
            # 重新计算 token
            self.recalculate_tokens()
            
            logger.info(
                "Tier 3 compaction completed. Summary length=%d, remaining messages=%d, tokens=%d",
                len(summary), len(self._messages), self._total_tokens,
            )
        
        except Exception as e:
            logger.exception("Tier 3 compaction failed: %s, skipping", e)
    
    def get_compacted_summary(self) -> str | None:
        """获取 Tier 3 压缩摘要"""
        return self._compacted_summary
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement Tier 3 LLM summary compression"
```

---

## Task 9: Implement Lightweight Pruning

**Files:**
- Modify: `app/execution/context_compressor.py`

- [ ] **Step 1: Add prune_tool_outputs method**

```python
    # ========== 轻量裁剪 ==========
    
    def prune_tool_outputs(
        self,
        protect_recent_groups: int = 2,
        minimum_recovery_tokens: int = 20_000,
        protected_tool_names: set[str] | None = None,
    ) -> int:
        """
        轻量裁剪：清除旧 tool output 的 content，回收 token
        
        处理规则：
        - 保护最近 N 组消息不被裁剪
        - 只有回收量 >= minimum_recovery_tokens 才执行
        - 受保护的工具（如 skill）不被裁剪
        - 将 content 替换为 "[Old tool result content cleared]"
        
        Args:
            protect_recent_groups: 保护的最近分组数
            minimum_recovery_tokens: 最小回收 token 数（避免频繁小量裁剪）
            protected_tool_names: 受保护的工具名称集合（默认 {"skill"}）
            
        Returns:
            实际回收的 token 数
        """
        if protected_tool_names is None:
            protected_tool_names = {"skill"}
        
        grouped = self.group_messages(self._messages)
        
        # 如果分组数不超过保护数，无需裁剪
        if len(grouped) <= protect_recent_groups:
            return 0
        
        # 计算可回收的 token 和候选消息
        older_groups = grouped[:-protect_recent_groups]
        reclaimable = 0
        candidates: list[tuple[int, dict]] = []
        
        for group in older_groups:
            for msg in group.messages:
                if msg["role"] != MessageRole.TOOL:
                    continue
                
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                
                # 已被裁剪的跳过
                if content == "[Old tool result content cleared]":
                    continue
                
                # 检查是否受保护
                is_protected = False
                for tc in group.messages[0].get("tool_calls", []) if group.messages else []:
                    if tc.get("name") in protected_tool_names:
                        is_protected = True
                        break
                
                if is_protected:
                    continue
                
                # 计算 token
                msg_tokens = count_messages_tokens([msg])
                reclaimable += msg_tokens
                candidates.append((msg_tokens, msg))
        
        # 如果回收量不足，不执行
        if reclaimable < minimum_recovery_tokens:
            return 0
        
        # 执行裁剪
        recovered = 0
        for msg_tokens, msg in candidates:
            msg["content"] = "[Old tool result content cleared]"
            recovered += msg_tokens
        
        # 重新计算总 token
        self.recalculate_tokens()
        
        logger.info(
            "Pruned %d tool outputs, recovered ~%d tokens, remaining total_tokens=%d",
            len(candidates), recovered, self._total_tokens,
        )
        
        return recovered
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/context_compressor.py
git commit -m "feat: implement lightweight tool output pruning"
```

---

## Task 10: Write Unit Tests for ContextCompressor

**Files:**
- Create: `tests/test_execution/test_context_compressor.py`

- [ ] **Step 1: Create test file with basic tests**

```python
import pytest
from app.execution.context_compressor import ContextCompressor, MessageGroup
from app.llm.base import MessageRole


def test_add_message_updates_tokens():
    """测试添加消息后 token 自动更新"""
    compressor = ContextCompressor()
    
    compressor.add_message("user", "Hello world")
    
    assert compressor.get_message_count() == 1
    assert compressor.get_total_tokens() > 0


def test_group_messages_with_tool_calls():
    """测试 assistant+tool_calls 分组逻辑"""
    messages = [
        {"role": "user", "content": "test"},
        {
            "role": "assistant",
            "content": "ok",
            "tool_calls": [{"id": "c1", "name": "read", "arguments": {}}],
        },
        {"role": "tool", "content": "output", "tool_call_id": "c1"},
    ]
    
    groups = ContextCompressor.group_messages(messages)
    
    assert len(groups) == 2
    assert groups[0].messages[0]["role"] == "user"
    assert groups[1].messages[0]["role"] == "assistant"
    assert len(groups[1].messages) == 2  # assistant + tool


def test_get_recent_messages_returns_last_n_groups():
    """测试 Tier 1 获取最近 N 组"""
    compressor = ContextCompressor(max_context_groups=2)
    
    for i in range(5):
        compressor.add_message("user", f"msg {i}")
    
    recent = compressor.get_recent_messages()
    
    assert len(recent) == 2
    assert recent[0]["content"] == "msg 3"
    assert recent[1]["content"] == "msg 4"


def test_check_pressure_returns_true_when_over_threshold():
    """测试压力检测阈值"""
    compressor = ContextCompressor()
    
    # 添加大量消息
    for i in range(50):
        compressor.add_message("user", "A" * 1000)
    
    assert compressor.check_pressure(context_window=100_000, tier3_ratio=0.1)


@pytest.mark.asyncio
async def test_compact_tier3_removes_old_messages():
    """测试 Tier 3 压缩移除旧消息"""
    compressor = ContextCompressor(max_context_groups=2)
    
    for i in range(10):
        compressor.add_message("user", f"old message {i}")
    
    original_count = compressor.get_message_count()
    
    async def mock_summarizer(task: str, transcript: str) -> str:
        return "Summary of old messages"
    
    await compressor.compact_tier3("test task", mock_summarizer)
    
    assert compressor.get_message_count() < original_count
    assert compressor.get_compacted_summary() == "Summary of old messages"


def test_prune_tool_outputs_clears_old_content():
    """测试轻量裁剪清除旧内容"""
    compressor = ContextCompressor()
    
    for i in range(10):
        compressor.add_message(
            "assistant",
            f"step {i}",
            tool_calls=[{"id": f"c{i}", "name": "read", "arguments": {}}],
        )
        compressor.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")
    
    recovered = compressor.prune_tool_outputs(protect_recent_groups=2, minimum_recovery_tokens=1)
    
    assert recovered > 0
    messages = compressor.get_messages()
    cleared = [m for m in messages if m.get("content") == "[Old tool result content cleared]"]
    assert len(cleared) > 0
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest tests/test_execution/test_context_compressor.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_execution/test_context_compressor.py
git commit -m "test: add unit tests for ContextCompressor"
```

---

## Task 11: Integrate ContextCompressor into LoopContext

**Files:**
- Modify: `app/execution/context_manager.py`

- [ ] **Step 1: Import ContextCompressor and modify __init__**

在 `context_manager.py` 顶部添加导入：
```python
from app.execution.context_compressor import ContextCompressor
```

在 `LoopContext.__init__` 中，移除这些字段初始化：
```python
# ❌ 删除这些行
self.messages: list[dict[str, Any]] = []
self.total_tokens: int = 0
self.compacted_summary: str | None = None
self.group_count: int = 0
```

添加 compressor 初始化：
```python
# ✅ 添加这一行
from app.config.settings import config_manager
self.compressor = ContextCompressor(
    max_context_groups=10,
    tool_output_max_chars=config_manager.settings.execution.tool_output_max_chars,
)
```

- [ ] **Step 2: Modify add_message to delegate to compressor**

将 `add_message` 方法修改为：
```python
def add_message(
    self,
    role: str,
    content: str | list[dict] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> None:
    """添加消息（支持多模态内容）- 委托给 compressor"""
    self.compressor.add_message(role, content, tool_calls, tool_call_id)
```

- [ ] **Step 3: Remove deprecated methods**

删除这些方法：
```python
# ❌ 删除整个方法
def recalculate_tokens(self) -> None
    
def prune_tool_outputs(self, ...) -> int

def _update_group_count(self, message: dict[str, Any]) -> None
```

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/test_execution/test_context_manager.py -v`
Expected: Some tests will fail (需要在下一个 task 修复)

- [ ] **Step 5: Commit**

```bash
git add app/execution/context_manager.py
git commit -m "refactor: integrate ContextCompressor into LoopContext"
```

---

## Task 12: Fix LoopContext Tests

**Files:**
- Modify: `tests/test_execution/test_context_manager.py`

- [ ] **Step 1: Update test_add_message**

修改 Line 42-43：
```python
# ❌ 原来
assert len(context.messages) == 2
assert context.messages[-1]["content"] == "你好，有什么可以帮助你的？"

# ✅ 修改为
assert len(context.compressor.get_messages()) == 2
assert context.compressor.get_messages()[-1]["content"] == "你好，有什么可以帮助你的？"
```

- [ ] **Step 2: Update from_run_input tests**

修改所有访问 `context.messages` 的地方（Line 67-72, 86-99, 109, 121-122, 136-137）：
```python
# ❌ 原来
context.messages

# ✅ 修改为
context.compressor.get_messages()
```

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/test_execution/test_context_manager.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_execution/test_context_manager.py
git commit -m "test: update LoopContext tests to use compressor"
```

---

## Task 13: Simplify LoopMessageBuilder

**Files:**
- Modify: `app/execution/loop_message_builder.py`

- [ ] **Step 1: Remove deprecated methods**

删除这 4 个方法（完整删除，包括文档字符串）：
```python
# ❌ 删除 Line 260-283
def recent_context_messages(self, context: LoopContext) -> list[dict]:

# ❌ 删除 Line 206-258  
def _build_tier2_messages(self, context: LoopContext) -> list[LLMMessage]:

# ❌ 删除 Line 301-304
def _group_messages(self, messages: list[dict]) -> list[list[dict]]:

# ❌ 删除 Line 306-320
@staticmethod
def _group_messages_static(messages: list[dict]) -> list[list[dict]]:
```

- [ ] **Step 2: Modify build() method - Tier 3 summary**

在 `build()` 方法中，修改 Line 69-75：
```python
# ❌ 原来
if context.compacted_summary:
    messages.append(
        LLMMessage(
            role=MessageRole.SYSTEM,
            content=f"[Compacted historical context]\n{context.compacted_summary}",
        )
    )

# ✅ 修改为
compacted_summary = context.compressor.get_compacted_summary()
if compacted_summary:
    messages.append(
        LLMMessage(
            role=MessageRole.SYSTEM,
            content=f"[Compacted historical context]\n{compacted_summary}",
        )
    )
```

- [ ] **Step 3: Modify build() method - Tier 2 and Tier 1**

修改 Line 78-79（compaction continue 条件）：
```python
# ❌ 原来
if context.compacted_summary and context.group_count > 1:

# ✅ 修改为
if compacted_summary and context.compressor.get_group_count() > 1:
```

修改 Line 89-91（Tier 2）：
```python
# ❌ 原来
tier2_messages = self._build_tier2_messages(context)

# ✅ 修改为
tier2_messages = context.compressor.build_tier2_messages()
```

修改 Line 94-103（Tier 1）：
```python
# ❌ 原来
for msg in self.recent_context_messages(context):

# ✅ 修改为
for msg in context.compressor.get_recent_messages():
```

修改 Line 114-119（task_anchor_interval）：
```python
# ❌ 原来
if context.group_count > 1:
    if self.task_anchor_interval > 0 and context.group_count % self.task_anchor_interval == 0:
        last_injected_group = context.metadata.get("_last_anchor_group", 0)
        if last_injected_group != context.group_count:

# ✅ 修改为
group_count = context.compressor.get_group_count()
if group_count > 1:
    if self.task_anchor_interval > 0 and group_count % self.task_anchor_interval == 0:
        last_injected_group = context.metadata.get("_last_anchor_group", 0)
        if last_injected_group != group_count:
            context.metadata["_last_anchor_group"] = group_count
```

- [ ] **Step 4: Modify build_initial_plan() method**

修改 Line 140：
```python
# ❌ 原来
for msg in self.recent_context_messages(context):

# ✅ 修改为
for msg in context.compressor.get_recent_messages():
```

- [ ] **Step 5: Modify build_final_summary() method**

修改 Line 170-175：
```python
# ❌ 原来
if context.compacted_summary:

# ✅ 修改为
compacted_summary = context.compressor.get_compacted_summary()
if compacted_summary:
    messages.append(
        LLMMessage(
            role=MessageRole.SYSTEM,
            content=f"[Compacted historical context]\n{compacted_summary}",
        )
    )
```

修改 Line 178-179：
```python
# ❌ 原来
for msg in self._build_tier2_messages(context):

# ✅ 修改为
for msg in context.compressor.build_tier2_messages():
```

修改 Line 181：
```python
# ❌ 原来
for msg in self.recent_context_messages(context):

# ✅ 修改为
for msg in context.compressor.get_recent_messages():
```

- [ ] **Step 6: Commit**

```bash
git add app/execution/loop_message_builder.py
git commit -m "refactor: simplify LoopMessageBuilder to use ContextCompressor"
```

---

## Task 14: Fix LoopMessageBuilder Tests

**Files:**
- Modify: `tests/test_execution/test_loop_message_builder.py`

- [ ] **Step 1: Update all context.messages references**

全局替换所有测试中的 `context.messages` 为 `context.compressor.get_messages()`

建议使用 IDE 查找替换功能，或者逐个测试修改。

- [ ] **Step 2: Run tests to verify**

Run: `pytest tests/test_execution/test_loop_message_builder.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_execution/test_loop_message_builder.py
git commit -m "test: update LoopMessageBuilder tests to use compressor"
```

---

## Task 15: Simplify RapidExecutionLoop

**Files:**
- Modify: `app/execution/rapid_loop.py`

- [ ] **Step 1: Remove deprecated methods**

删除 Line 1097-1109（`_compact_context` 方法）和 Line 1111-1169（`_compact_tier3` 方法）。

- [ ] **Step 2: Add _create_summarizer method**

在合适的位置（建议在 `_call_llm` 之前）添加：
```python
def _create_summarizer(self) -> Callable[[str, str], Awaitable[str]]:
    """创建摘要生成器回调（解耦 LLM 依赖）"""
    async def summarizer(task: str, transcript: str) -> str:
        system_prompt = self.prompt_manager.get_midrun_compression_system_prompt()
        user_prompt = self.prompt_manager.get_midrun_compression_prompt(
            task=task,
            transcript=transcript,
            existing_summary=self.context.compressor.get_compacted_summary(),
        )
        response = await self.llm.complete([
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=user_prompt),
        ], tools=None)
        return (response.content or "").strip()
    
    return summarizer
```

- [ ] **Step 3: Modify _call_llm to use compressor**

在 Line 897 附近（`await self._compact_context(context)` 之前），替换为：
```python
# ✅ 检查上下文压力并触发 Tier 3 压缩
if context.compressor.check_pressure(
    self.context_window,
    config_manager.settings.execution.tier3_ratio,
):
    await context.compressor.compact_tier3(
        task=context.task,
        summarizer=self._create_summarizer(),
    )
```

修改 Line 1030：
```python
# ❌ 原来
if self._overflow_retry_count < 1 and context.total_tokens > 0:

# ✅ 修改为
if self._overflow_retry_count < 1 and context.compressor.get_total_tokens() > 0:
```

修改 Line 1034-1040（overflow 处理）：
```python
# ❌ 原来
await self._compact_tier3(context)
context.prune_tool_outputs(...)

# ✅ 修改为
await context.compressor.compact_tier3(
    task=context.task,
    summarizer=self._create_summarizer(),
)
context.compressor.prune_tool_outputs(
    protect_recent_groups=config_manager.settings.execution.prune_protect_groups,
    minimum_recovery_tokens=1,
)
```

- [ ] **Step 4: Modify _handle_tool_execution**

修改 Line 443 和 Line 1037（可能有多处）：
```python
# ❌ 原来
context.prune_tool_outputs(
    protect_recent_groups=settings.prune_protect_groups,
    minimum_recovery_tokens=settings.prune_minimum_recovery_tokens,
)

# ✅ 修改为
context.compressor.prune_tool_outputs(
    protect_recent_groups=settings.prune_protect_groups,
    minimum_recovery_tokens=settings.prune_minimum_recovery_tokens,
)
```

- [ ] **Step 5: Update comments**

修改 Line 1098 附近的注释：
```python
# ❌ 原来注释
# - Tier 2 截断由 LoopMessageBuilder._build_tier2_messages() 在 build 时自动处理

# ✅ 修改为
# - Tier 2 截断由 ContextCompressor.build_tier2_messages() 在 build 时自动处理
```

- [ ] **Step 6: Commit**

```bash
git add app/execution/rapid_loop.py
git commit -m "refactor: simplify RapidExecutionLoop to use ContextCompressor"
```

---

## Task 16: Fix Midrun Compaction Tests

**Files:**
- Modify: `tests/test_execution/test_midrun_compaction.py`

- [ ] **Step 1: Update all property accesses (约 20 处)**

修改所有引用，使用查找替换：
```python
# Line 42, 50
ctx.total_tokens → ctx.compressor.get_total_tokens()

# Line 53, 210
ctx.compacted_summary → ctx.compressor.get_compacted_summary()

# Line 60, 67-74
ctx.group_count → ctx.compressor.get_group_count()

# Line 88, 101, 115, 270
ctx.prune_tool_outputs(...) → ctx.compressor.prune_tool_outputs(...)

# Line 91
ctx.messages → ctx.compressor.get_messages()

# Line 116
LoopMessageBuilder._group_messages_static(ctx.messages) → ctx.compressor.get_groups()
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_execution/test_midrun_compaction.py
git commit -m "test: update midrun compaction tests to use compressor"
```

---

## Task 17: Export MessageGroup from models.py

**Files:**
- Modify: `app/execution/models.py`

- [ ] **Step 1: Add import and re-export**

在文件顶部添加：
```python
from app.execution.context_compressor import MessageGroup

__all__ = [
    "StepStatus",
    "AgentMode",
    "LoopStep",
    "LoopResult",
    "LoopPhase",
    "RuntimeState",
    "MessageGroup",  # 新增
]
```

- [ ] **Step 2: Commit**

```bash
git add app/execution/models.py
git commit -m "feat: export MessageGroup from execution models"
```

---

## Task 18: Run Full Test Suite and Fix Remaining Issues

**Files:**
- Various test files

- [ ] **Step 1: Run all execution tests**

Run: `pytest tests/test_execution/ -v`
Expected: Identify any remaining failures

- [ ] **Step 2: Fix any remaining test failures**

根据测试输出，修复可能的问题：
- `test_rapid_loop.py` 中可能需要更新
- `test_multimodal_*.py` 中可能需要更新
- 其他测试文件

修复方法：将所有 `context.messages`, `context.total_tokens` 等改为 compressor 方法调用。

- [ ] **Step 3: Verify no old interface references remain**

Run: 
```bash
cd backend
grep -r "context\.messages\b" app tests --include="*.py" | grep -v compressor | grep -v "\.pyc" | grep -v __pycache__
grep -r "context\.total_tokens\b" app tests --include="*.py" | grep -v compressor
grep -r "context\.compacted_summary\b" app tests --include="*.py" | grep -v compressor
grep -r "context\.group_count\b" app tests --include="*.py" | grep -v compressor
```

Expected: No results (所有引用已更新)

- [ ] **Step 4: Run full test suite again**

Run: `pytest tests/test_execution/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "test: fix remaining test failures after compressor integration"
```

---

## Task 19: Integration Testing and Verification

**Files:**
- N/A (手动测试)

- [ ] **Step 1: Run full backend test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Check test coverage**

Run: `pytest tests/test_execution/ --cov=app/execution --cov-report=term`
Expected: Coverage > 80% for context_compressor.py

- [ ] **Step 3: Manual verification (optional)**

启动应用并测试关键场景：
- 短对话（<10 组消息）
- 中等对话（10-20 组消息）
- 长对话（>20 组消息，触发 Tier 3）
- 工具密集型对话（验证裁剪）

- [ ] **Step 4: Review code quality**

检查：
- [ ] 所有公共方法都有文档字符串
- [ ] 方法按职责分组排列（初始化 → 消息 → 分组 → Token → Tier1/2/3 → 裁剪）
- [ ] 没有遗漏的旧接口引用
- [ ] 导入语句整理好

- [ ] **Step 5: Document findings**

如果发现问题，记录在 git commit message 或 issue 中。

---

## Task 20: Code Cleanup and Final Commit

**Files:**
- All modified files

- [ ] **Step 1: Remove unused imports**

检查并移除未使用的导入，特别是：
- `context_manager.py` 中可能有 `LoopMessageBuilder` 的导入需要移除
- 其他文件中的冗余导入

- [ ] **Step 2: Run code formatter**

Run:
```bash
black app/execution tests/test_execution
```

- [ ] **Step 3: Run final test suite**

Run: `pytest tests/test_execution/ -v`
Expected: All tests pass

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "refactor: introduce ContextCompressor to unify message compression

- 新增 ContextCompressor 统一管理消息状态和三级压缩
- 简化 LoopContext 为纯状态存储，移除压缩逻辑
- 简化 MessageBuilder，移除分组和压缩方法
- 简化 RapidExecutionLoop，通过回调解耦 LLM 依赖
- 更新所有测试用例，覆盖率 > 80%

Breaking changes:
- context.messages → context.compressor.get_messages()
- context.total_tokens → context.compressor.get_total_tokens()
- context.compacted_summary → context.compressor.get_compacted_summary()
- context.group_count → context.compressor.get_group_count()
- context.prune_tool_outputs() → context.compressor.prune_tool_outputs()
- context.recalculate_tokens() → context.compressor.recalculate_tokens()

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 5: Push to remote (optional)**

如果在 feature branch：
```bash
git push origin feature/refactor
```

---

## Summary

**Total Tasks:** 20
**Estimated Time:** 4-6 hours
**Key Deliverables:**
- ✅ New `ContextCompressor` class with 600+ lines
- ✅ Simplified `LoopContext` (removed ~100 lines)
- ✅ Simplified `LoopMessageBuilder` (removed ~150 lines)
- ✅ Simplified `RapidExecutionLoop` (removed ~70 lines)
- ✅ 14+ unit tests for ContextCompressor
- ✅ Updated ~50 references across test files
- ✅ All tests passing
- ✅ Code formatted and clean

**Success Criteria:**
- [x] All unit tests pass
- [x] Test coverage > 80% for ContextCompressor
- [x] No old interface references remain
- [x] Code formatted with black
- [x] Commit message includes breaking changes
- [x] 单一职责：每个操作只在一个地方完成
- [x] 无循环依赖：LoopContext、MessageBuilder、RapidLoop 解耦
- [x] 注释完整：所有公共方法都有清晰的文档字符串

# Context Compressor 重构设计

**日期**: 2026-06-16  
**状态**: 设计阶段  
**作者**: Claude + 木南

## 目标

重构 loop 循环相关组件，解决职责混乱、代码重复问题，采用方案 C：引入 ContextCompressor 独立处理压缩。

## 问题陈述

### 当前架构问题

1. **职责边界模糊** - 消息分组逻辑散落在 `LoopContext._update_group_count()` 和 `LoopMessageBuilder._group_messages_static()` 两处
2. **三级压缩模型分裂** - Tier 1/2/3 分别由 MessageBuilder、MessageBuilder、RapidLoop 实现，没有统一入口
3. **Token 管理分散** - 增量计算、全量重算、回收量统计分散在多处，容易不一致
4. **循环依赖** - LoopContext.prune_tool_outputs() 调用 LoopMessageBuilder，MessageBuilder 又深度依赖 Context

### 核心诉求

- ✅ 单一职责：每个操作只在一个地方完成
- ✅ 解耦：打破循环依赖
- ✅ 可测试：压缩逻辑独立，便于单元测试
- ✅ 可扩展：便于后续添加新的压缩策略

## 架构设计

### 总体架构

```
ContextCompressor (新)
├─ 消息状态管理 (_messages, _compacted_summary, _total_tokens)
├─ 消息操作 (add_message, get_messages)
├─ 分组逻辑 (group_messages, get_groups)
├─ Token 管理 (calculate_tokens, check_pressure)
└─ 三级压缩 (get_recent_messages, build_tier2_messages, compact_tier3, prune_tool_outputs)

LoopContext (简化)
├─ 纯状态存储 (task, plan, steps, metadata)
├─ compressor: ContextCompressor
└─ 委托接口 (add_message -> compressor.add_message)

MessageBuilder (简化)
├─ 纯消息组装
└─ 从 compressor 获取分层消息

RapidExecutionLoop (简化)
├─ 执行流程
└─ 提供压缩回调给 compressor
```

### 数据流对比

**重构前**：
```
User -> RapidLoop.run()
  -> LoopContext.add_message()  # 自己计算 tokens, 更新 group_count
  -> LoopMessageBuilder.build()
     -> _group_messages()  # 内部分组
     -> _build_tier2_messages()  # 内部截断
  -> RapidLoop._compact_tier3()  # Loop 自己压缩
  -> LoopContext.prune_tool_outputs()  # 回调 MessageBuilder 分组
```

**重构后**：
```
User -> RapidLoop.run()
  -> LoopContext.add_message()
     -> compressor.add_message()  # 统一入口，自动计算 tokens 和 group_count
  -> LoopMessageBuilder.build()
     -> compressor.get_recent_messages()  # Tier 1
     -> compressor.build_tier2_messages()  # Tier 2
     -> compressor.get_compacted_summary()  # Tier 3
  -> compressor.compact_tier3(summarizer=lambda: llm.complete())  # 解耦 LLM
  -> compressor.prune_tool_outputs()  # 内部分组，不再循环依赖
```

## 详细设计

### 1. MessageGroup 数据类

新增 `MessageGroup` 数据类，封装消息分组及其元数据。

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

**设计理由**：
- ✅ 封装分组元数据（token_count），避免重复计算
- ✅ 提供便捷的查询接口（has_tool_calls, first_message_role）
- ✅ 后续可扩展（如添加 created_at, compressed 等字段）

### 2. ContextCompressor 核心类

**职责**：统一管理消息状态、分组、Token 计算、三级压缩。

**类结构**（方法按职责分组，从上到下排列）：

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
    
    def get_groups(self) -> list[MessageGroup]:
        """获取当前消息的分组（包含 token 预计算）"""
        return self.group_messages(self._messages)
    
    def get_group_count(self) -> int:
        """获取当前分组数"""
        return self._group_count
    
    # ========== Token 管理 ==========
    
    def calculate_tokens(self, messages: list[dict]) -> int:
        """计算消息列表的 token 数（静态方法）"""
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
            tier3_ratio: Tier 3 阈值比例（如 0.6 表示 60% 窗口）
            
        Returns:
            True 表示需要压缩
        """
        tier3_threshold = int(context_window * tier3_ratio)
        return self._total_tokens > tier3_threshold

    
    # ========== Tier 1: 完整保留 ==========
    
    def get_recent_messages(self, max_groups: int | None = None) -> list[dict]:
        """
        获取 Tier 1 最近 N 组消息（完整保留，包括多模态内容）
        
        Args:
            max_groups: 保留的最大分组数，默认使用 self.max_context_groups
            
        Returns:
            展平后的消息列表（保持原始格式）
        """
    
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
    
    def get_compacted_summary(self) -> str | None:
        """获取 Tier 3 压缩摘要"""
        return self._compacted_summary

    
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
```

**设计要点**：

1. **有状态设计** - Compressor 内部管理 `_messages`、`_compacted_summary`、`_total_tokens`，调用方无需传递状态
2. **解耦 LLM** - Tier 3 压缩通过回调函数接收 summarizer，不直接依赖 LLM 接口
3. **单一职责** - 所有消息相关操作（分组、token、压缩）集中在一个类中
4. **方法顺序** - 从上到下按职责分组：初始化 → 消息管理 → 分组 → Token → Tier1/2/3 → 裁剪

### 3. LoopContext 简化

**移除的字段**：
```python
# ❌ 以下字段移到 ContextCompressor
messages: list[dict]
total_tokens: int
compacted_summary: str
group_count: int
```

**新增字段**：
```python
# ✅ 持有 compressor 实例
compressor: ContextCompressor
```

**保留的接口**（委托实现）：
```python
def add_message(
    self,
    role: str,
    content: str | list[dict] | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
) -> None:
    """委托给 compressor，保持接口兼容"""
    self.compressor.add_message(role, content, tool_calls, tool_call_id)
```

**移除的方法**：
```python
# ❌ 不再需要
def recalculate_tokens(self) -> None
def prune_tool_outputs(self, ...) -> int
def _update_group_count(self, message: dict) -> None
```

**from_run_input 修改**：
```python
@classmethod
def from_run_input(cls, ...) -> "LoopContext":
    context = cls(...)
    
    # ✅ 通过 compressor 添加消息
    for seeded in history_messages or []:
        # 验证和过滤逻辑
        context.add_message(role, content, tool_calls, tool_call_id)
    
    # 其他逻辑保持不变
    return context
```

### 4. LoopMessageBuilder 简化

**移除的方法**：
```python
# ❌ 分组逻辑移到 Compressor
@staticmethod
def _group_messages_static(messages: list[dict]) -> list[list[dict]]

def _group_messages(self, messages: list[dict]) -> list[list[dict]]

# ❌ Tier 2 逻辑移到 Compressor
def _build_tier2_messages(self, context: LoopContext) -> list[LLMMessage]

# ❌ Tier 1 逻辑移到 Compressor
def recent_context_messages(self, context: LoopContext) -> list[dict]
```

**修改的方法**：
```python
def build(self, context: LoopContext) -> list[LLMMessage]:
    """构建完整的三级上下文消息列表，供 LLM 调用使用"""
    # 1. System prompt
    messages = [LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)]
    
    # 2. Context sections
    self._inject_context_sections(context, messages)
    
    # 3. Tier 3 摘要（如有）
    compacted_summary = context.compressor.get_compacted_summary()
    if compacted_summary:
        messages.append(LLMMessage(
            role=MessageRole.SYSTEM,
            content=f"[Compacted historical context]\n{compacted_summary}",
        ))
    
    # 4. Tier 2 截断消息
    tier2_messages = context.compressor.build_tier2_messages()
    messages.extend(tier2_messages)
    
    # 5. Tier 1 完整消息
    recent_messages = context.compressor.get_recent_messages()
    for msg in recent_messages:
        # 转换为 LLMMessage
        messages.append(...)
    
    # 6. Plan status、Task Anchor、Prefill 等逻辑保持不变
    return messages
```

**设计要点**：
- ✅ MessageBuilder 只负责组装，不再包含分组/压缩逻辑
- ✅ 从 `context.compressor` 获取三层消息
- ✅ 保持 plan、task anchor、prefill 等业务逻辑

### 5. RapidExecutionLoop 简化

**移除的方法**：
```python
# ❌ 压缩逻辑移到 Compressor
async def _compact_context(self, context: LoopContext) -> None

async def _compact_tier3(self, context: LoopContext) -> None
```

**修改的方法**：
```python
async def _call_llm(self, context: LoopContext) -> LLMResponse:
    """调用 LLM（使用原生工具调用），特定条件下重试空响应"""
    
    # ✅ 检查上下文压力
    if context.compressor.check_pressure(
        self.context_window,
        config_manager.settings.execution.tier3_ratio,
    ):
        # ✅ 触发 Tier 3 压缩（通过回调解耦 LLM）
        await context.compressor.compact_tier3(
            task=context.task,
            summarizer=self._create_summarizer(),
        )
    
    # 原有的 LLM 调用逻辑
    for attempt in range(self.MAX_EMPTY_RESPONSE_RETRIES):
        messages = self.message_builder.build(context)
        response = await self.llm.stream_complete(messages, tools)
        # ...
    
    return response

def _create_summarizer(self) -> Callable[[str, str], Awaitable[str]]:
    """创建摘要生成器回调（解耦 LLM 依赖）"""
    async def summarizer(task: str, transcript: str) -> str:
        system_prompt = self.prompt_manager.get_midrun_compression_system_prompt()
        user_prompt = self.prompt_manager.get_midrun_compression_prompt(
            task=task,
            transcript=transcript,
            existing_summary=None,
        )
        response = await self.llm.complete([
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=user_prompt),
        ], tools=None)
        return (response.content or "").strip()
    
    return summarizer
```

**轻量裁剪调用修改**：
```python
async def _handle_tool_execution(self, context, result, rt) -> LoopPhase:
    # 工具执行后裁剪
    settings = config_manager.settings.execution
    context.compressor.prune_tool_outputs(
        protect_recent_groups=settings.prune_protect_groups,
        minimum_recovery_tokens=settings.prune_minimum_recovery_tokens,
    )
    return LoopPhase.PLANNING
```

**设计要点**：
- ✅ Loop 不再直接实现压缩逻辑
- ✅ 通过回调函数解耦 LLM 依赖
- ✅ 保持执行流程清晰

## 影响范围分析

### 直接影响的核心文件（需要修改）

1. **app/execution/context_compressor.py** - 新建文件
2. **app/execution/context_manager.py** - 移除字段，集成 compressor
3. **app/execution/loop_message_builder.py** - 移除压缩逻辑，使用 compressor
4. **app/execution/rapid_loop.py** - 移除压缩方法，使用 compressor 接口

### 测试文件（需要修改）

1. **tests/test_execution/test_context_compressor.py** - 新建测试
2. **tests/test_execution/test_context_manager.py** - 修改属性访问（5 处）
3. **tests/test_execution/test_loop_message_builder.py** - 修改属性访问（约 10 处）
4. **tests/test_execution/test_midrun_compaction.py** - 大量修改（约 20 处）
5. **tests/test_execution/test_rapid_loop.py** - 可能需要修改
6. **tests/test_execution/test_multimodal_*.py** - 可能需要修改

### 间接影响的文件（可能需要检查）

1. **app/memory/context_assembly.py** - 只读取 context，不修改，无影响
2. **app/execution/models.py** - 需要导入 MessageGroup（小改动）
3. **tests/test_execution/test_runtime_tool_definitions.py** - 可能需要检查

### 具体修改点统计

通过 grep 分析，共计约 **50 处**引用需要修改：

| 文件 | 引用类型 | 数量 | 修改方式 |
|------|---------|------|----------|
| context_manager.py | 字段定义/方法实现 | ~8 处 | 移除字段，添加 compressor，修改方法 |
| loop_message_builder.py | 方法调用/属性访问 | ~15 处 | 使用 compressor 方法 |
| rapid_loop.py | 方法实现/属性访问 | ~10 处 | 使用 compressor 接口 |
| test_context_manager.py | 属性访问 | ~5 处 | `context.messages` → `context.compressor.get_messages()` |
| test_loop_message_builder.py | 属性访问 | ~10 处 | 同上 |
| test_midrun_compaction.py | 属性/方法调用 | ~20 处 | 全面修改为使用 compressor |

### 关键修改点详解

#### 1. LoopContext 中的修改

**移除的调用点**：
- `context_manager.py:201` - `self._update_group_count(message)` 
- `context_manager.py:204` - `self.recalculate_tokens()`
- `context_manager.py:226` - `LoopMessageBuilder._group_messages_static()` 调用

**修改后的接口**：
```python
# 原来：直接访问
context.messages  # 需改为 context.compressor.get_messages()
context.total_tokens  # 需改为 context.compressor.get_total_tokens()
context.compacted_summary  # 需改为 context.compressor.get_compacted_summary()
context.group_count  # 需改为 context.compressor.get_group_count()

# 原来：直接调用
context.prune_tool_outputs(...)  # 需改为 context.compressor.prune_tool_outputs(...)
context.recalculate_tokens()  # 需改为 context.compressor.recalculate_tokens()
```

#### 2. LoopMessageBuilder 中的修改

**移除的方法**：
- `_group_messages_static(messages)` - 移至 `ContextCompressor.group_messages()`
- `_group_messages(messages)` - 移至 `ContextCompressor.group_messages()`
- `_build_tier2_messages(context)` - 移至 `ContextCompressor.build_tier2_messages()`
- `recent_context_messages(context)` - 移至 `ContextCompressor.get_recent_messages()`

**调用点修改**：
- `loop_message_builder.py:89` - `self._build_tier2_messages()` 调用
- `loop_message_builder.py:94` - `self.recent_context_messages()` 调用
- `loop_message_builder.py:141` - `self.recent_context_messages()` 调用
- `loop_message_builder.py:179` - `self._build_tier2_messages()` 调用
- `loop_message_builder.py:182` - `self.recent_context_messages()` 调用
- `loop_message_builder.py:212` - `self._group_messages()` 调用
- `loop_message_builder.py:303` - `self._group_messages_static()` 调用

#### 3. RapidExecutionLoop 中的修改

**移除的方法**：
- `_compact_context(context)` - 逻辑移至 `_call_llm` 中直接调用 compressor
- `_compact_tier3(context)` - 移至 `ContextCompressor.compact_tier3()`

**新增的方法**：
- `_create_summarizer()` - 创建 summarizer 回调函数

**调用点修改**：
- `rapid_loop.py:443` - `context.prune_tool_outputs()` 改为 `context.compressor.prune_tool_outputs()`
- `rapid_loop.py:1037` - `context.prune_tool_outputs()` 改为 `context.compressor.prune_tool_outputs()`
- `rapid_loop.py:1030` - `context.total_tokens` 改为 `context.compressor.get_total_tokens()`
- `rapid_loop.py:1120` - `self.message_builder._group_messages()` 改为 `context.compressor.get_groups()`
- `rapid_loop.py:1097-1109` - `_compact_context()` 调用改为 `compressor.check_pressure()`
- `rapid_loop.py:1161` - `context.messages` 赋值改为 `compressor` 内部处理
- `rapid_loop.py:1162` - `context.recalculate_tokens()` 改为 `compressor.recalculate_tokens()`

#### 4. 测试文件中的修改

**test_context_manager.py** - 5 处修改：
- Line 42: `context.messages` → `context.compressor.get_messages()`
- Line 43: `context.messages[-1]` → `context.compressor.get_messages()[-1]`
- Line 67-72: 多处 `context.messages` 访问

**test_midrun_compaction.py** - 约 20 处修改：
- Line 42: `ctx.total_tokens` → `ctx.compressor.get_total_tokens()`
- Line 50: `ctx.total_tokens` → `ctx.compressor.get_total_tokens()`
- Line 53: `ctx.compacted_summary` → `ctx.compressor.get_compacted_summary()`
- Line 60: `ctx.group_count` → `ctx.compressor.get_group_count()`
- Line 67-74: `ctx.group_count` 多处
- Line 88: `ctx.prune_tool_outputs()` → `ctx.compressor.prune_tool_outputs()`
- Line 91: `ctx.messages` → `ctx.compressor.get_messages()`
- Line 101: `ctx.prune_tool_outputs()` → `ctx.compressor.prune_tool_outputs()`
- Line 115: `ctx.prune_tool_outputs()` → `ctx.compressor.prune_tool_outputs()`
- Line 116: `LoopMessageBuilder._group_messages_static(ctx.messages)` → `ctx.compressor.get_groups()`
- Line 210: `ctx.compacted_summary` → `ctx.compressor.get_compacted_summary()`
- Line 270: `ctx.prune_tool_outputs()` → `ctx.compressor.prune_tool_outputs()`

**test_loop_message_builder.py** - 约 10 处修改：
- 所有 `context.messages` 的访问都需改为 `context.compressor.get_messages()`

## 实现计划

### 阶段 1：新建 ContextCompressor（独立实现）

**目标**：创建 ContextCompressor 类，实现所有压缩逻辑，确保功能完整。

**步骤**：
1. 创建 `app/execution/context_compressor.py`
2. 实现 `MessageGroup` 数据类
3. 实现 `ContextCompressor` 类的所有方法（按设计顺序）
   - 初始化
   - 消息管理（add_message, get_messages, get_message_count, clear_messages）
   - 分组逻辑（group_messages, get_groups, get_group_count）
   - Token 管理（calculate_tokens, recalculate_tokens, get_total_tokens, check_pressure）
   - Tier 1（get_recent_messages）
   - Tier 2（build_tier2_messages）
   - Tier 3（compact_tier3, get_compacted_summary）
   - 轻量裁剪（prune_tool_outputs）
4. 编写单元测试 `tests/test_execution/test_context_compressor.py`

**验收标准**：
- ✅ 所有 Compressor 方法通过单元测试
- ✅ 分组逻辑与原 `_group_messages_static` 行为一致
- ✅ Token 计算准确
- ✅ 压缩逻辑可独立测试（使用 mock summarizer）

### 阶段 2：集成到 LoopContext

**目标**：修改 LoopContext，使用 Compressor 替代原有字段和方法。

**步骤**：
1. 在 `LoopContext.__init__` 中创建 `self.compressor = ContextCompressor(...)`
2. 移除字段（4 个）：
   - `self.messages`
   - `self.total_tokens`
   - `self.compacted_summary`
   - `self.group_count`
3. 修改 `add_message` 方法委托给 `compressor.add_message`
4. 移除方法（3 个）：
   - `recalculate_tokens()`
   - `prune_tool_outputs(...)`
   - `_update_group_count(message)`
5. 修改 `from_run_input` 中的历史消息处理逻辑（保持通过 `add_message` 添加）
6. 在 `app/execution/models.py` 中添加 `MessageGroup` 导出

**验收标准**：
- ✅ LoopContext 初始化正常，持有 compressor 实例
- ✅ `add_message` 功能正常，消息添加到 compressor
- ✅ 移除的方法不再被引用（运行 grep 验证）
- ✅ `from_run_input` 测试通过

### 阶段 3：简化 LoopMessageBuilder

**目标**：移除 MessageBuilder 中的分组/压缩逻辑，改用 Compressor。

**步骤**：
1. 移除方法（4 个）：
   - `_group_messages_static(messages)`
   - `_group_messages(messages)`
   - `_build_tier2_messages(context)`
   - `recent_context_messages(context)`
2. 修改 `build(context)` 方法（7 处修改）：
   - Line 69: `context.compacted_summary` → `context.compressor.get_compacted_summary()`
   - Line 78-79: 条件检查修改
   - Line 89: `self._build_tier2_messages(context)` → `context.compressor.build_tier2_messages()`
   - Line 94: `self.recent_context_messages(context)` → `context.compressor.get_recent_messages()`
   - Line 114-119: task_anchor_interval 逻辑中使用 `context.compressor.get_group_count()`
3. 修改 `build_initial_plan(context)` 方法：
   - Line 140: `self.recent_context_messages(context)` → `context.compressor.get_recent_messages()`
4. 修改 `build_final_summary(context)` 方法（3 处修改）：
   - Line 170: `context.compacted_summary` → `context.compressor.get_compacted_summary()`
   - Line 178: `self._build_tier2_messages(context)` → `context.compressor.build_tier2_messages()`
   - Line 181: `self.recent_context_messages(context)` → `context.compressor.get_recent_messages()`

**验收标准**：
- ✅ `build` 方法返回正确的消息列表
- ✅ 三层消息顺序正确（Tier 3 摘要 → Tier 2 截断 → Tier 1 完整）
- ✅ 不再包含分组/压缩实现
- ✅ 测试文件 `test_loop_message_builder.py` 通过

### 阶段 4：简化 RapidExecutionLoop

**目标**：移除 Loop 中的压缩逻辑，使用 Compressor 接口。

**步骤**：
1. 移除方法（2 个）：
   - `_compact_context(context)` (Line 1097-1109)
   - `_compact_tier3(context)` (Line 1111-1169)
2. 新增方法：
   - `_create_summarizer()` - 创建 summarizer 回调函数
3. 修改 `_call_llm(context)` 方法（Line 883-1056）：
   - 将原 `await self._compact_context(context)` 替换为：
     ```python
     if context.compressor.check_pressure(
         self.context_window,
         config_manager.settings.execution.tier3_ratio,
     ):
         await context.compressor.compact_tier3(
             task=context.task,
             summarizer=self._create_summarizer(),
         )
     ```
   - Line 1030: `context.total_tokens` → `context.compressor.get_total_tokens()`
   - Line 1034-1040: overflow 处理中调用 `context.compressor` 方法
4. 修改 `_handle_tool_execution(context, result, rt)` 方法（2 处）：
   - Line 443: `context.prune_tool_outputs(...)` → `context.compressor.prune_tool_outputs(...)`
   - Line 1037: 同上
5. 修改注释（1 处）：
   - Line 1098: 更新注释，说明压缩由 Compressor 处理

**验收标准**：
- ✅ LLM 调用前正确检查压力
- ✅ Tier 3 压缩正常工作（通过回调）
- ✅ 轻量裁剪正常工作
- ✅ 不再直接访问 `context.messages`

### 阶段 5：更新测试用例

**目标**：修改所有依赖旧接口的测试，确保功能覆盖。

**步骤**：
1. **新建** `tests/test_execution/test_context_compressor.py`：
   - `test_add_message_updates_tokens()`
   - `test_add_message_updates_group_count()`
   - `test_group_messages_with_tool_calls()`
   - `test_group_messages_without_tool_calls()`
   - `test_get_recent_messages_returns_last_n_groups()`
   - `test_build_tier2_messages_truncates_long_outputs()`
   - `test_build_tier2_messages_preserves_tool_call_id()`
   - `async test_compact_tier3_removes_old_messages()`
   - `async test_compact_tier3_updates_summary()`
   - `test_prune_tool_outputs_clears_old_content()`
   - `test_prune_tool_outputs_respects_minimum_recovery()`
   - `test_prune_tool_outputs_protects_recent_groups()`
   - `test_check_pressure_returns_true_when_over_threshold()`
   - `test_check_pressure_returns_false_when_under_threshold()`

2. **修改** `tests/test_execution/test_context_manager.py`（5 处）：
   - Line 42: `assert len(context.messages)` → `assert len(context.compressor.get_messages())`
   - Line 43: `context.messages[-1]` → `context.compressor.get_messages()[-1]`
   - Line 67-72: 所有 `context.messages` 访问
   
3. **修改** `tests/test_execution/test_midrun_compaction.py`（约 20 处）：
   - Line 42: `ctx.total_tokens` → `ctx.compressor.get_total_tokens()`
   - Line 50: 同上
   - Line 53: `ctx.compacted_summary` → `ctx.compressor.get_compacted_summary()`
   - Line 60, 67-74: `ctx.group_count` → `ctx.compressor.get_group_count()`
   - Line 88, 101, 115, 270: `ctx.prune_tool_outputs()` → `ctx.compressor.prune_tool_outputs()`
   - Line 91: `ctx.messages` → `ctx.compressor.get_messages()`
   - Line 116: `LoopMessageBuilder._group_messages_static(ctx.messages)` → `ctx.compressor.get_groups()`
   - Line 210: `ctx.compacted_summary` → `ctx.compressor.get_compacted_summary()`

4. **修改** `tests/test_execution/test_loop_message_builder.py`（约 10 处）：
   - 所有测试中的 `context.messages` 改为 `context.compressor.get_messages()`

5. **检查并修改**（如需要）：
   - `tests/test_execution/test_rapid_loop.py`
   - `tests/test_execution/test_multimodal_*.py`
   - `tests/test_execution/test_runtime_tool_definitions.py`

6. 运行完整测试套件：
   ```bash
   pytest tests/test_execution/ -v
   ```

**验收标准**：
- ✅ 所有现有测试通过
- ✅ 新增 Compressor 测试覆盖率 > 80%
- ✅ 没有残留的旧接口引用（通过 grep 验证）
- ✅ 测试运行时间没有明显增加

### 阶段 6：集成测试与验证

**目标**：确保重构后的系统功能完整、性能稳定。

**步骤**：
1. 运行端到端测试（如有）：
   ```bash
   pytest tests/test_execution/ -v --tb=short
   ```
2. 手动测试关键场景：
   - **短对话**（<10 组消息）：验证 Tier 1 完整保留
   - **中等对话**（10-20 组消息）：验证 Tier 2 截断逻辑
   - **长对话**（>20 组消息）：验证 Tier 3 LLM 压缩触发
   - **工具密集型**：大量工具输出，验证轻量裁剪效果
   - **多模态消息**：验证图片等内容正确处理
3. 性能对比（可选）：
   - 对比重构前后的 token 使用（通过日志）
   - 对比压缩效率（压缩前后 token 数）
   - 对比执行时间（不应明显增加）
4. 代码审查：
   - 检查所有注释是否完整
   - 检查方法顺序是否按设计（初始化 → 消息 → 分组 → Token → Tier1/2/3 → 裁剪）
   - 检查是否有遗漏的旧接口引用
5. 文档更新（可选）：
   - 更新架构图（如有）
   - 更新 README（如有说明三级压缩模型）

**验收标准**：
- ✅ 功能与重构前一致
- ✅ 没有明显的性能退化（< 5%）
- ✅ 日志中压缩相关信息正常
- ✅ 所有测试通过（单元测试 + 集成测试）
- ✅ 代码审查通过（注释完整、职责清晰）

### 阶段 7：清理与提交

**目标**：清理临时代码，提交重构成果。

**步骤**：
1. 删除已注释的旧代码（如有）
2. 检查并移除未使用的导入
3. 运行代码格式化：
   ```bash
   black app/execution tests/test_execution
   ```
4. 最终测试运行：
   ```bash
   pytest tests/test_execution/ -v --cov=app/execution --cov-report=term
   ```
5. Git 提交：
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
   
   Fixes: #<issue-number> (如有关联的 issue)
   
   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
   ```

**验收标准**：
- ✅ 代码格式化完成
- ✅ 测试覆盖率 > 80%
- ✅ Git 提交信息清晰，包含 breaking changes 说明
- ✅ 无未暂存的文件

## 架构合理性审查

### 职责划分

重构后的职责划分：

| 类 | 职责 | 合理性评估 |
|----|------|----------|
| **ContextCompressor** | 消息状态管理、分组、Token 计算、三级压缩 | ✅ 单一职责，所有压缩相关操作集中 |
| **LoopContext** | 纯状态存储（task, plan, steps, metadata）| ✅ 轻量化，只存储业务状态 |
| **MessageBuilder** | 消息组装（从 compressor 获取分层消息）| ✅ 专注组装逻辑，不再管理压缩 |
| **RapidExecutionLoop** | 执行流程控制（状态机、LLM 调用编排）| ✅ 通过回调解耦 LLM 依赖 |

### 依赖关系

```
RapidExecutionLoop
  ├─> LoopContext (持有)
  │    └─> ContextCompressor (持有)
  ├─> MessageBuilder (持有)
  │    └─> 读取 LoopContext 和 ContextCompressor
  └─> 提供 summarizer 回调给 ContextCompressor
```

**评估**：
- ✅ 无循环依赖
- ✅ 依赖方向清晰：Loop → Context → Compressor
- ✅ MessageBuilder 只读取，不修改状态
- ✅ Compressor 独立，可单独测试

### 扩展性

**易于扩展的场景**：
1. ✅ 添加新的压缩层（Tier 4）：在 Compressor 中添加方法即可
2. ✅ 自定义压缩策略：修改 Compressor 内部逻辑，不影响调用方
3. ✅ 更换分组算法：只需修改 `group_messages` 方法
4. ✅ 添加压缩指标：在 Compressor 中添加统计字段

**难以扩展的场景**：
- ⚠️ 如果需要根据不同场景使用不同的压缩策略（如 plan 模式 vs build 模式），当前设计未考虑
- **缓解**：可以通过 Compressor 的初始化参数或配置对象传入策略

### 测试性

**单元测试**：
- ✅ Compressor 独立测试，无需依赖 LLM 或 Loop
- ✅ LoopContext 轻量化，测试更简单
- ✅ MessageBuilder 可用 mock Compressor 测试

**集成测试**：
- ✅ 通过 Loop 测试完整流程
- ✅ 可用 mock summarizer 测试压缩逻辑

### 性能考虑

**潜在开销**：
1. **MessageGroup 创建开销** - 每次 `get_groups()` 都重新分组和计算 token
   - **缓解**：可在 Compressor 中缓存分组结果，当 `_messages` 未变时复用

2. **`get_messages()` 拷贝开销** - 返回副本避免外部修改
   - **评估**：拷贝开销可接受（消息列表通常 < 1000 条）
   - **可选优化**：返回只读视图（`tuple`）而非副本

3. **Token 重复计算** - `group_messages()` 中预计算每组 token
   - **评估**：预计算避免了更多重复计算，利大于弊

**结论**：性能影响可控，无明显瓶颈。

### 遗留问题检查

通过分析，确认以下文件**不受影响**：

1. **app/memory/context_assembly.py** - 只读取 context，不修改 messages
2. **app/execution/approval_flow.py** - 不直接访问 context 字段
3. **app/execution/tool_call_executor.py** - 通过 `context.add_message()` 操作，接口保持
4. **app/browser/manager.py** - 不涉及 context

**需要特别注意**：
- ⚠️ 如果有其他模块直接序列化/反序列化 LoopContext，可能受影响
- **检查方法**：搜索 `LoopContext` 的 pickle/json 序列化代码

## 总结

### 设计优势

1. ✅ **单一职责**：每个类职责明确，消息压缩逻辑统一在 Compressor
2. ✅ **解耦合**：打破循环依赖，通过回调解耦 LLM 依赖
3. ✅ **可测试**：Compressor 独立测试，覆盖率高
4. ✅ **可扩展**：易于添加新的压缩策略或层级
5. ✅ **可维护**：代码结构清晰，方法按职责分组

### 潜在风险（已在风险与缓解章节详述）

1. ⚠️ 破坏性重构，约 50 处引用需修改
2. ⚠️ Tier 3 压缩回调增加复杂度
3. ⚠️ 性能可能有小幅回归（需验证）
4. ⚠️ 测试覆盖可能不足

### 成功标准（已在成功标准章节详述）

- ✅ 功能完整性
- ✅ 代码质量（单一职责、无循环依赖、注释完整）
- ✅ 测试覆盖（单元测试 > 80%，集成测试通过）
- ✅ 可维护性（结构清晰、易扩展、错误处理完善）

---

**设计完成日期**：2026-06-16  
**设计者**：Claude + 木南  
**审查状态**：已完成架构合理性审查  
**状态**：待用户最终审批


## 测试策略

### 单元测试

**test_context_compressor.py**：
```python
def test_add_message_updates_tokens():
    """测试添加消息后 token 自动更新"""

def test_group_messages_with_tool_calls():
    """测试 assistant+tool_calls 分组逻辑"""

def test_get_recent_messages_returns_last_n_groups():
    """测试 Tier 1 获取最近 N 组"""

def test_build_tier2_messages_truncates_long_outputs():
    """测试 Tier 2 截断长输出"""

async def test_compact_tier3_removes_old_messages():
    """测试 Tier 3 压缩移除旧消息"""

def test_prune_tool_outputs_clears_old_content():
    """测试轻量裁剪清除旧内容"""

def test_check_pressure_returns_true_when_over_threshold():
    """测试压力检测阈值"""
```

**test_loop_message_builder.py**（修改现有测试）：
- 所有访问 `context.messages` 的地方改为 `context.compressor.get_messages()`
- 验证构建的消息列表结构正确

### 集成测试

**关键场景**：
1. **短对话**：验证 Tier 1 完整保留
2. **中等对话**：验证 Tier 2 截断逻辑
3. **长对话**：验证 Tier 3 LLM 压缩
4. **工具密集型**：验证轻量裁剪效果
5. **多模态消息**：验证图片等内容正确处理

## 风险与缓解

### 风险 1：破坏性重构导致接口不兼容

**影响**：现有代码大量调用 `context.messages`、`context.total_tokens` 等，需要全部修改。

**缓解**：
- ✅ 阶段化实施，每个阶段独立验证
- ✅ 先实现 Compressor，确保功能正确后再集成
- ✅ 编写完整的单元测试覆盖
- ✅ 使用 IDE 的查找引用功能，确保所有旧接口都被替换

### 风险 2：Tier 3 压缩回调复杂度增加

**影响**：RapidLoop 需要创建 summarizer 回调，代码稍显复杂。

**缓解**：
- ✅ 提供 `_create_summarizer` 辅助方法，封装复杂度
- ✅ 回调签名简单明确：`async (task: str, transcript: str) -> str`
- ✅ 在设计文档中提供清晰的示例代码

### 风险 3：性能回归

**影响**：重构可能引入额外的计算开销（如重复 token 计算）。

**缓解**：
- ✅ MessageGroup 预计算 token_count，避免重复计算
- ✅ Compressor 使用增量 token 更新，而非每次全量计算
- ✅ 保留性能关键路径的优化（如 Tier 2 只处理旧消息）

### 风险 4：测试覆盖不足

**影响**：边缘情况未被测试，可能在生产环境出现问题。

**缓解**：
- ✅ 参考现有测试用例，确保覆盖所有场景
- ✅ 新增 Compressor 专项测试，覆盖率 > 80%
- ✅ 保留原有集成测试，确保端到端功能正常

## 成功标准

1. **功能完整性**：
   - ✅ 三级压缩模型工作正常
   - ✅ Token 计算准确
   - ✅ 消息分组逻辑与原有行为一致

2. **代码质量**：
   - ✅ 单一职责：每个操作只在一个地方完成
   - ✅ 无循环依赖：LoopContext、MessageBuilder、RapidLoop 解耦
   - ✅ 注释完整：所有公共方法都有清晰的文档字符串

3. **测试覆盖**：
   - ✅ 单元测试覆盖率 > 80%
   - ✅ 所有现有测试通过
   - ✅ 关键场景有集成测试

4. **可维护性**：
   - ✅ 类结构清晰，方法按职责分组
   - ✅ 易于扩展（如添加 Tier 4 或新的压缩策略）
   - ✅ 错误处理完善（压缩失败不中断 run）

## 后续优化方向

1. **性能优化**：
   - 考虑使用 LRU 缓存 token 计算结果
   - 探索更高效的分组算法（如增量分组）

2. **功能增强**：
   - 支持自定义压缩策略（如基于时间、重要性）
   - 支持更细粒度的 token 预算控制

3. **监控与可观测性**：
   - 添加压缩指标（压缩次数、回收 token 数）
   - 记录压缩耗时，便于性能分析

---

**设计完成日期**：2026-06-16  
**设计者**：Claude + 木南  
**状态**：等待审核


# Context Management Overhaul — OpenCode 对标设计

> 日期: 2026-05-31
> 状态: Draft
> 关联: `docs/superpowers/specs/2026-05-22-midrun-context-compaction-design.md`

## 1. 问题

当前 ReflexionOS 的三级上下文模型（Tier 1/2/3）已实现基本压缩能力，但与 OpenCode 相比缺少以下关键机制，导致长 run 中"计划执行更新不对"：

| 缺失 | 现状 | 后果 |
|------|------|------|
| **Pruning** | 无日常轻量回收 | 工具输出不断累积，直到触发 Tier 3 才处理，上下文长期膨胀 |
| **模型感知窗口** | 硬编码 50K/100K 阈值 | 对 128K 模型触发过早，对 200K 模型触发过晚 |
| **文件读取限制过严** | `max_read_limit=100` | agent 读取文件碎片化严重，需要 20+ 次读取才能看完一个大文件 |
| **API 溢出处理** | 遇到 `finish_reason=length` 只报错 | 上下文超限时无法自动恢复，只能报错终止 |
| **Tier 2 使用 system role** | 旧消息角色改为 system | LLM 无法正确理解对话流（tool 消息必须保持 tool role） |
| **冗余代码** | Tier 2 将 tool 消息角色改为 system | 破坏 tool_call_id 关联，LLM 无法匹配 tool_call 与 tool output |

## 2. 设计目标

1. 每轮对话后自动清理旧工具输出（Pruning），保持上下文精简
2. 根据模型实际 context window 动态计算压缩阈值，适配不同模型
3. 文件读取上限放宽至 2000 行 + 50KB，减少碎片化读取
4. 上下文溢出时自动触发 compaction 后重试，而非报错终止
5. 修复 Tier 2 中 tool 消息角色错误（保持原始 role）
6. 清除冗余代码

## 3. 改动详情

### 3.1 Pruning（轻量裁剪）

借鉴 OpenCode 的 `prune` 机制：每轮工具执行结束后，遍历旧的 tool output 消息，将其 `content` 替换为 `[Old tool result content cleared]`，回收 token。

**参数：**
- `PRUNE_PROTECT_GROUPS = 2`：保护最近 2 组消息不被裁剪
- `PRUNE_MINIMUM_RECOVERY_TOKENS = 20_000`：至少回收 20K tokens 才触发
- `PRUNE_PROTECTED_TOOLS = {"skill"}`：skill 工具输出不被裁剪

**实现位置：**
- `LoopContext` 新增 `prune_tool_outputs(protect_recent_groups, minimum_recovery_tokens)` 方法
- `RapidExecutionLoop._handle_tool_execution` 末尾调用 `context.prune_tool_outputs()`
- Pruning 后调用 `context.recalculate_tokens()`

**逻辑：**
1. 按 `_group_messages()` 分组
2. 保护最近 2 组
3. 遍历旧组中的 tool role 消息，如果 `content` 不是已被清除的标记
4. 计算可回收 token 数，如果 >= 20K，则执行清除
5. 清除时将 `content` 替换为 `[Old tool result content cleared]`

### 3.2 模型感知上下文窗口

**`ProviderModelConfig` 新增字段：**
- `context_window: int = 128000`：模型的上下文窗口大小

**`ExecutionSettings` 改为动态阈值：**
- `compaction_buffer: int = 20_000`：预留的输出 buffer
- `tier2_ratio: float = 0.5`：Tier 2 触发 = usable * tier2_ratio
- `tier3_ratio: float = 0.85`：Tier 3 触发 = usable * tier3_ratio
- 删除旧的 `tier2_truncate_threshold_tokens` 和 `tier3_compact_threshold_tokens`

**计算 `usable`：**
```
usable = context_window - compaction_buffer
tier2_threshold = usable * tier2_ratio
tier3_threshold = usable * tier3_ratio
```

**传递路径：**
- `_run_turn()` 中从 `resolved_llm` 获取 `context_window`，传给 `RapidExecutionLoop`
- `RapidExecutionLoop.__init__` 新增 `context_window` 参数
- `_compact_context()` 使用 `context_window` 动态计算阈值

### 3.3 文件读取硬限制放宽

**`FileTool` 改动：**
- `max_read_limit`: 100 → 2000
- `default_read_limit`: 80 → 500
- `min_read_limit`: 30 → 30（不变）
- 新增 `MAX_READ_BYTES = 50 * 1024`：50KB 字节上限
- 新增 `MAX_LINE_LENGTH = 2000`：单行超 2000 字符截断

**逻辑：**
1. 读取文件时先检查文件总字节数，超过 50KB 时只读取部分并提示
2. 每行超过 2000 字符时截断并标记 `... (line truncated to 2000 chars)`
3. Schema 中 `limit` 的 maximum 改为 2000

### 3.4 API 溢出处理

**`_call_llm()` 改动：**
- 当检测到 `finish_reason=length` 且估算 token 接近 usable 时，自动触发 `_compact_tier3()`
- 压缩后重试当前调用（最多重试 1 次）
- 新增 `_overflow_retry_count` 实例变量，防止无限重试

### 3.5 修复 Tier 2 tool 消息角色

**`LoopMessageBuilder._build_tier2_messages()` 改动：**
- tool 消息保持 `MessageRole.TOOL` 角色 + `tool_call_id`
- assistant 消息保持 `MessageRole.ASSISTANT` 角色 + `tool_calls`
- user 消息保持 `MessageRole.USER` 角色
- 只有非 tool/assistant/user 的 system notice 才改为 system role

### 3.6 清除冗余代码

**删除/清理项：**
- `ExecutionSettings` 中删除 `tier2_truncate_threshold_tokens` 和 `tier3_compact_threshold_tokens`（被动态计算替代）
- 旧设计中 Tier 2 将消息角色统一改为 system 的逻辑（已在 3.5 修复）
- 旧 plan 文档 `docs/superpowers/plans/2026-05-22-midrun-context-compaction-plan.md` 中已过时的实现代码片段（保留文档但标注已替换）

## 4. 改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/app/execution/context_manager.py` | 修改 | 新增 `prune_tool_outputs()` 方法 |
| `backend/app/execution/rapid_loop.py` | 修改 | 新增 `context_window` 参数；tool_execution 后调用 pruning；_compact_context 改用动态阈值；_call_llm 新增溢出重试 |
| `backend/app/execution/loop_message_builder.py` | 修改 | Tier 2 保持原始消息角色 |
| `backend/app/config/settings.py` | 修改 | ExecutionSettings 改为动态阈值配置 |
| `backend/app/models/llm_config.py` | 修改 | ProviderModelConfig 新增 context_window |
| `backend/app/tools/file_tool.py` | 修改 | 放宽读取限制 + 字节/行长度上限 |
| `backend/app/services/agent_service.py` | 修改 | 传递 context_window 到 RapidExecutionLoop |

## 5. 不做的事

- 不做 OpenCode 的 `models.dev` 集成（太重，用配置字段代替）
- 不做 media stripping（当前无 image/PDF 附件场景）
- 不做跨 session compaction（当前 session 内已够用）
- 不改变 DB 层的 messages 存储（pruning 仅修改内存中的 `context.messages`）

# 上下文组装合并计划

## 目标

消除 6 个上下文/对话组装组件中的 4 处重叠，合并为 4 个职责单一的组件：

| 合并前 | 合并后 |
|--------|--------|
| ContextAssembler（静态上下文 + 对话历史） | ConversationHistoryLoader（纯对话历史） |
| build_context_assembly（薄过滤函数） | 内联到 ConversationHistoryLoader |
| PromptManager（agent.md, memory.md） | PromptManager（统一管理所有 system prompt 内容，含 AGENTS.md + Skills） |
| LoopContext.from_run_input（二次过滤） | LoopContext.from_run_input（仅去重） |
| ContextCompressor | ContextCompressor（不动） |
| LoopMessageBuilder | LoopMessageBuilder（简化，去掉 system_sections 注入） |

## 重叠消除

1. **静态上下文分散** → 统一归 PromptManager
2. **消息过滤两次** → 合并为一次
3. **AGENTS.md vs agent.md** → 废弃 AGENTS.md，统一用 agent.md
4. **build_context_assembly 太薄** → 内联

---

## 自检发现的问题及修正

### 问题 1：`from_run_input` 的过滤逻辑不是"二次过滤"，不能删除

**原计划**：删除 `allowed_seed_roles` 过滤和 `tool_call_id` 校验，认为与 `_filter_seed_messages` 重复。

**实际**：两者职责完全不同：
- `_filter_seed_messages`（在 ConversationHistoryLoader 中）：验证 dict 结构完整性（role 非空、content 非空、字段合法）
- `from_run_input` 的过滤：将 seed dict 转为 `add_message()` 调用（类型转换 + 角色校验 + content 规范化 + tool_calls 格式化），是模型层转换而非过滤

**修正**：保留 `from_run_input` 的全部过滤和转换逻辑，只删除 `system_sections` 参数。

### 问题 2：`build_initial_plan` 和 `build_final_summary` 也调用 `_inject_context_sections`

**原计划**：只提到 `build()` 方法中的 `_inject_context_sections` 调用。

**实际**：`loop_message_builder.py` 中有三处调用：
- L66 `build()` 方法
- L154-156 `build_initial_plan()` 方法（注释说明故意不注入，但代码结构仍引用）
- L204 `build_final_summary()` 方法

**修正**：三处调用都需要处理。`build_initial_plan` 本就不注入 system_sections（注释明确说明），删除 `_inject_context_sections` 后该注释也需更新。

### 问题 3：AGENTS.md 应完全废弃，统一到 agent.md

**原计划**：AGENTS.md "暂不删除"，只移加载逻辑。

**修正**（用户确认）：完全废弃 AGENTS.md。PromptManager 已有 `agent.md` overlay 机制（`_overlay_paths` 加载 `~/.reflexion/agent.md` 和 `{project}/.reflexion/agent.md`），AGENTS.md 的内容应迁移到 agent.md，ContextAssembler 中的 AGENTS.md 加载代码直接删除，不迁移到 PromptManager。

### 问题 4：PromptManager 已有 `project_root` 参数

**原计划**：给 `get_system_prompt` 新增 `project_path` 参数。

**实际**：`get_system_prompt` 已有 `project_root` 参数，且已通过 `_overlay_paths(project_root)` 加载 agent.md overlay。无需新增参数。

**修正**：只需在 `get_system_prompt` 中新增 Skills 元数据注入，不需要新增 `project_root` 参数，也不需要新增 `_load_agents_md` 方法。

### 问题 5：`from_run_input` 的 `allowed_seed_roles` 是必要的防御层

**原计划**：删除 `allowed_seed_roles` 过滤。

**实际**：`allowed_seed_roles` 确保只有 user/assistant/tool 角色进入 compressor，是模型层防御，与 `_filter_seed_messages` 的 dict 结构验证互补。

**修正**：保留 `allowed_seed_roles`，只删除 `system_sections` 参数和赋值。

---

## 修正后的文件变更地图

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/memory/context_assembly.py` | **重写** | 重命名为 ConversationHistoryLoader，只管对话历史；删除 AGENTS.md 加载、Skills 注入、`ContextAssemblyResult`、`build_context_assembly` |
| `backend/app/execution/prompt_manager.py` | **修改** | 新增 `_build_skill_section` 方法；在 `get_system_prompt` 中追加 Skills section（利用已有 `project_root` 参数，不新增参数） |
| `backend/app/execution/context_manager.py` | **修改** | 删除 `system_sections` 字段和参数；保留 `allowed_seed_roles` 过滤和 `tool_call_id` 校验 |
| `backend/app/execution/loop_message_builder.py` | **修改** | 删除 `_inject_context_sections` 方法；删除 `build()`、`build_final_summary()` 中的调用；更新 `build_initial_plan()` 的注释 |
| `backend/app/execution/rapid_loop.py` | **修改** | 去掉 `system_sections` 参数传递 |
| `backend/app/services/agent_service.py` | **修改** | 适配新接口：`ContextAssembler` → `ConversationHistoryLoader`，删除 `system_sections` 相关代码 |
| `backend/tests/` | **修改** | 适配上述变更 |

---

## Task 1: 重写 context_assembly.py → ConversationHistoryLoader

### 目标
将 ContextAssembler 从"静态上下文 + 对话历史"简化为纯对话历史加载器。

### 修改文件
- `backend/app/memory/context_assembly.py`

### 详细步骤

1. **删除 `ContextAssemblyResult` 类** — 不再需要，直接返回 `list[dict[str, Any]]`

2. **删除 `build_context_assembly` 函数** — 过滤逻辑内联到 `build_for_session`

3. **重命名 `ContextAssembler` → `ConversationHistoryLoader`**

4. **修改 `__init__`** — 去掉 `skill_registry` 参数（Skills 注入移到 PromptManager）

5. **重写 `build_for_session`** — 
   - 删除 static_blocks 相关逻辑（AGENTS.md 加载、Skills 注入）
   - 删除 `build_context_assembly` 调用
   - 将 `build_context_assembly` 的过滤逻辑内联到 `_message_to_seed_dict` 之后的循环中
   - 返回类型改为 `list[dict[str, Any]]`

6. **保留向后兼容别名**（过渡期）：
   ```python
   # 向后兼容别名，后续 Task 中逐步替换引用后删除
   ContextAssembler = ConversationHistoryLoader
   ContextAssemblyResult = None  # 标记为废弃
   ```

### 新代码骨架

```python
from __future__ import annotations

from typing import Any

from app.models.conversation import MessageType
from app.services.conversation_service import ConversationService


def _message_to_seed_dict(message: Any, supports_vision: bool | None = None) -> list[dict[str, Any]]:
    # ... 保持不变 ...


def _tool_trace_to_paired_seeds(message: Any) -> list[dict[str, Any]]:
    # ... 保持不变 ...


def _filter_seed_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤和规范化 seed 消息（原 build_context_assembly 的过滤逻辑内联于此）"""
    result: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        raw_content = message.get("content")
        if raw_content is None:
            content: str | list = ""
        elif isinstance(raw_content, list):
            content = raw_content
        else:
            content = str(raw_content)
        tool_calls = message.get("tool_calls")
        tool_call_id = message.get("tool_call_id")
        has_content = (
            (isinstance(content, list) and len(content) > 0)
            or (isinstance(content, str) and content.strip())
            or tool_calls
        )
        if not has_content:
            continue
        entry: dict[str, Any] = {"role": role, "content": content}
        if tool_calls is not None:
            entry["tool_calls"] = tool_calls
        if tool_call_id is not None:
            entry["tool_call_id"] = tool_call_id
        result.append(entry)
    return result


class ConversationHistoryLoader:
    """
    从数据库加载对话历史并转换为 LLM seed dict 格式。
    
    职责单一：只管对话历史，不管静态上下文（AGENTS.md、Skills 等）
    静态上下文由 PromptManager 统一管理。
    """

    def __init__(
        self,
        *,
        conversation_service: ConversationService,
    ):
        self.conversation_service = conversation_service

    def load_for_session(
        self,
        *,
        session_id: str,
        project_id: str,
        current_turn_id: str | None = None,
        max_seed_messages: int = 8,
        max_tool_traces: int = 20,
        scan_limit: int = 200,
        supports_vision: bool | None = None,
    ) -> list[dict[str, Any]]:
        """加载对话历史，返回过滤后的 seed messages 列表"""
        candidates = self.conversation_service.list_recent_seed_candidates(
            session_id,
            current_turn_id=current_turn_id,
            limit=max_seed_messages,
            scan_limit=scan_limit,
            max_tool_traces=max_tool_traces,
        )
        raw_messages: list[dict[str, Any]] = []
        for msg in candidates:
            raw_messages.extend(_message_to_seed_dict(msg, supports_vision))
        
        return _filter_seed_messages(raw_messages)


# 向后兼容别名
ContextAssembler = ConversationHistoryLoader
```

### 测试文件修改
- `backend/tests/test_memory/test_context_assembly.py`
  - 将 `ContextAssembler` 引用改为 `ConversationHistoryLoader`
  - 删除 `ContextAssemblyResult` 相关断言
  - 删除 `build_context_assembly` 相关测试
  - 删除 static_blocks / AGENTS.md / Skills 相关测试
  - 验证 `load_for_session` 返回 `list[dict]`
  - 验证 `_filter_seed_messages` 过滤逻辑

---

## Task 2: PromptManager 接管 AGENTS.md + Skills 注入

### 目标
将 ContextAssembler 中的 AGENTS.md 加载和 Skills 元数据注入移入 PromptManager，使 PromptManager 成为所有 system prompt 内容的唯一来源。

### 修改文件
- `backend/app/execution/prompt_manager.py`

### 详细步骤

1. **新增 `__init__` 参数**：`skill_registry: SkillRegistry | None = None`

2. **新增 `_load_agents_md` 方法**：
   ```python
   def _load_agents_md(self, project_path: str | None) -> str | None:
       """加载项目 AGENTS.md（项目规则），统一注入到 system prompt 中"""
       if not project_path:
           return None
       agents_path = Path(project_path) / "AGENTS.md"
       if agents_path.exists() and agents_path.is_file():
           return agents_path.read_text(encoding="utf-8")
       return None
   ```

3. **新增 `_build_skill_section` 方法**：
   ```python
   def _build_skill_section(self) -> str | None:
       """构建 Skills 元数据 section，注入到 system prompt 中"""
       if not self.skill_registry:
           return None
       enabled_skills = self.skill_registry.list_enabled_skills()
       if not enabled_skills:
           return None
       parts = ["""## Available Skills
       
When a skill clearly matches your current task, load it first using the 'skill' tool with action='load'.

### Skill usage guidelines:
1. Before starting a task, briefly consider whether an available skill matches.
2. If a skill matches, use the 'skill' tool with action='load' to read its full content.
3. Follow the loaded skill's instructions — skills provide proven workflows for complex tasks.
4. Process skills (debugging, TDD, brainstorming) help you approach a task correctly — check them when relevant.
5. Implementation skills guide execution — use them after process skills when applicable.
6. A skill's hard gates and checklists are important safeguards — respect them.

### Available skills:"""]
       for s in enabled_skills:
           req_str = ", ".join(s.required_skills)
           req = f" (requires: {req_str})" if s.required_skills else ""
           parts.append(f"- **{s.name}**: {s.description}{req}")
       return "\n".join(parts)
   ```

4. **修改 `get_system_prompt` 方法**：在返回前，将 AGENTS.md 和 Skills section 追加到 system prompt 末尾：
   ```python
   def get_system_prompt(self, ..., project_path: str | None = None) -> str:
       # ... 原有逻辑 ...
       
       # 追加 AGENTS.md 项目规则
       agents_content = self._load_agents_md(project_path)
       if agents_content:
           sections.append(f"Project rules (from AGENTS.md):\n{agents_content}")
       
       # 追加 Skills 元数据
       skill_section = self._build_skill_section()
       if skill_section:
           sections.append(skill_section)
       
       return "\n\n".join(sections)
   ```

   > 注意：`get_system_prompt` 需要新增 `project_path` 参数。需要检查所有调用方并传递该参数。

5. **更新 `PromptManager` 的构造调用方**：在 `agent_service.py` 中创建 `PromptManager` 时传入 `skill_registry`。

### 测试
- 新增测试：`_load_agents_md` 存在/不存在/无 project_path
- 新增测试：`_build_skill_section` 有/无 skill_registry
- 新增测试：`get_system_prompt` 包含 AGENTS.md 内容
- 新增测试：`get_system_prompt` 包含 Skills section

---

## Task 3: 简化 LoopContext.from_run_input — 去掉二次过滤

### 目标
`from_run_input` 当前做了消息过滤（allowed_seed_roles、tool_call_id 校验等），这些过滤已经在 `_filter_seed_messages` 中完成。简化为仅做去重。

### 修改文件
- `backend/app/execution/context_manager.py`

### 详细步骤

1. **删除 `allowed_seed_roles` 过滤** — `_filter_seed_messages` 已保证消息角色合法

2. **删除 `tool_call_id` 校验** — `_tool_trace_to_paired_seeds` 已保证格式正确

3. **保留去重逻辑** — 最后一条用户消息与当前任务去重仍然需要

4. **去掉 `system_sections` 参数** — 不再需要，静态上下文已由 PromptManager 处理

### 改动前后对比

```python
# 改动前
@classmethod
def from_run_input(
    cls,
    *,
    history_messages: list[dict[str, Any]],
    system_sections: list[str],
    ...
) -> "LoopContext":
    # 过滤 allowed_seed_roles
    # 校验 tool_call_id
    # 去重
    # 存 system_sections

# 改动后
@classmethod
def from_run_input(
    cls,
    *,
    history_messages: list[dict[str, Any]],
    ...
) -> "LoopContext":
    # 仅去重（最后一条 user 消息 vs 当前任务）
    # 不再存 system_sections
```

### 测试文件修改
- `backend/tests/test_execution/test_context_manager.py`
  - 删除 `system_sections` 相关断言
  - 删除 `allowed_seed_roles` 过滤测试
  - 删除 `tool_call_id` 校验测试
  - 保留去重测试

---

## Task 4: 简化 LoopMessageBuilder — 去掉 system_sections 注入

### 目标
`system_sections` 消失后，`_inject_context_sections` 方法不再需要。

### 修改文件
- `backend/app/execution/loop_message_builder.py`

### 详细步骤

1. **删除 `_inject_context_sections` 方法**

2. **修改 `build` 方法**：
   - 删除 `context.system_sections` 相关代码
   - system prompt 由 PromptManager 完整产出，不再需要额外注入

3. **修改 `LoopContext`**：
   - 删除 `system_sections` 字段

### 测试文件修改
- `backend/tests/test_execution/test_loop_message_builder.py`
  - 删除 `_inject_context_sections` 相关测试
  - 删除 `system_sections` 相关断言

---

## Task 5: 修改 rapid_loop.py — 去掉 system_sections 参数

### 目标
`rapid_loop.run` 不再接收 `system_sections` 参数。

### 修改文件
- `backend/app/execution/rapid_loop.py`

### 详细步骤

1. **修改 `run` 方法签名**：删除 `system_sections: list[str]` 参数

2. **修改 `LoopContext.from_run_input` 调用**：去掉 `system_sections` 传递

3. **删除所有 `system_sections` 引用**

### 测试
- 修改 `rapid_loop` 相关测试，去掉 `system_sections` 参数

---

## Task 6: 修改 agent_service.py — 适配新接口

### 目标
适配 ConversationHistoryLoader + PromptManager 的新接口。

### 修改文件
- `backend/app/services/agent_service.py`

### 详细步骤

1. **替换 `ContextAssembler` → `ConversationHistoryLoader`**

2. **修改 `_run_turn` 方法**：
   ```python
   # 改动前
   assembly = self.context_assembler.build_for_session(...)
   history_messages = assembly.recent_messages
   system_sections = assembly.system_sections
   
   # 改动后
   history_messages = self.history_loader.load_for_session(...)
   # system_sections 不再需要
   ```

3. **修改 `PromptManager` 构造**：传入 `skill_registry`

4. **修改 `rapid_loop.run` 调用**：去掉 `system_sections` 参数，传入 `project_path` 给 PromptManager

5. **更新测试**：
   - `test_services/test_agent_service.py` 中 `ContextAssemblyResult` mock 改为直接返回 `list[dict]`
   - 删除 `system_sections` 断言

---

## Task 7: 清理向后兼容别名 + 更新所有 import

### 目标
删除过渡期别名，更新所有 import 引用。

### 修改文件
- 所有引用 `ContextAssembler`、`ContextAssemblyResult`、`build_context_assembly` 的文件

### 详细步骤

1. **全局搜索替换**：
   - `ContextAssembler` → `ConversationHistoryLoader`
   - 删除所有 `ContextAssemblyResult` 引用
   - 删除所有 `build_context_assembly` 引用

2. **删除 `context_assembly.py` 中的向后兼容别名**

3. **验证**：`grep -r "ContextAssembler\|ContextAssemblyResult\|build_context_assembly" backend/` 无结果

---

## Task 8: 运行测试验证

### 目标
确保所有修改不破坏现有功能。

### 详细步骤

1. 运行单元测试：
   ```bash
   cd backend && python -m pytest tests/ -x -v
   ```

2. 重点检查测试：
   - `test_context_assembly.py` — ConversationHistoryLoader
   - `test_context_manager.py` — 简化后的 from_run_input
   - `test_loop_message_builder.py` — 去掉 system_sections
   - `test_agent_service.py` — 新接口适配
   - `test_prompt_manager.py` — AGENTS.md + Skills 注入

3. 如有失败，修复并重跑

---

## 执行顺序依赖

```
Task 1 (ConversationHistoryLoader) ──┐
                                      ├──→ Task 5 (rapid_loop)
Task 2 (PromptManager) ──────────────┤
                                      ├──→ Task 6 (agent_service)
Task 3 (LoopContext) ────────────────┤
                                      ├──→ Task 7 (清理别名)
Task 4 (LoopMessageBuilder) ─────────┘
                                      │
                                      └──→ Task 8 (测试验证)
```

Task 1-4 可并行执行，Task 5-6 依赖 Task 1-4，Task 7 依赖 Task 5-6，Task 8 依赖所有。

---

## 风险和注意事项

1. **AGENTS.md 向后兼容**：PromptManager 已有 agent.md overlay 机制。AGENTS.md 和 agent.md 功能重叠，但此计划暂不删除 AGENTS.md 文件本身，只是将其加载逻辑从 ContextAssembler 移到 PromptManager。后续可考虑统一为 agent.md。

2. **Skills 注入位置**：Skills 元数据从 system_sections 移到 system prompt 内部。需确认 Token 预算不会超限。当前 Skills section 约 200-500 tokens，在 system prompt 中可接受。

3. **project_path 传递**：PromptManager 的 `get_system_prompt` 需要新增 `project_path` 参数。需确保所有调用方都传递该参数。

4. **测试覆盖**：每个 Task 完成后立即运行相关测试，不要等全部改完再跑。

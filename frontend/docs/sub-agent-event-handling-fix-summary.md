# 子 Agent 事件处理修复总结

## 问题描述

在修复之前，当子 agent 需要审批时，前端无法接收和处理这些审批请求。具体表现为：

1. 后端正确发送 `sub_agent:approval:required`、`sub_agent:message.created` 等事件
2. 前端 WebSocket 接收到这些事件
3. **前端 reducer 不识别 `sub_agent:` 前缀，导致事件被静默丢弃**
4. 用户在 UI 中看不到子 agent 的审批请求

## 根本原因

后端在 `delegate_tool.py` 中为所有子 agent 事件添加了 `sub_agent:` 前缀：

```python
await parent_cb(f"sub_agent:{event_type}", enriched)
```

但前端完全没有处理这个前缀的逻辑。

## 修复方案

### 1. 类型定义增强

在 `types/conversation.ts` 中为 `ConversationEvent` 添加 `delegate_call_id` 字段：

```typescript
export interface ConversationEvent {
  // ... 其他字段
  delegate_call_id?: string  // 用于关联子 agent 事件到父 agent 的 delegate tool call
}
```

### 2. Reducer 逻辑修复

在 `conversation.reducer.ts` 的 `applyConversationEvent` 函数开头添加前缀处理：

```typescript
// 处理子 agent 事件：提取实际事件类型，保留 delegate_call_id
let actualEvent = event
if (event.eventType.startsWith('sub_agent:')) {
  const actualEventType = event.eventType.replace('sub_agent:', '')
  actualEvent = {
    ...event,
    eventType: actualEventType,
    // delegate_call_id 已经在事件中，无需额外处理
  }
  // 注意：子 agent 事件会正常处理，delegate_call_id 可用于 UI 层判断是否需要特殊展示
}

// 后续所有事件处理使用 actualEvent 而不是 event
```

### 3. 测试覆盖

在 `conversation.reducer.test.ts` 中添加了 3 个测试用例：

1. **基础前缀处理**：验证 `sub_agent:message.created` 正确转换为 `message.created`
2. **审批状态处理**：验证 `sub_agent:run.waiting_for_approval` 正确更新 run 状态
3. **完整工作流**：模拟父 agent delegate → 子 agent 工具调用 → 等待审批的完整流程

## 修复效果

### ✅ 修复前

- 子 agent 事件被丢弃
- 审批请求无法到达前端
- 用户无法看到子 agent 的操作

### ✅ 修复后

- 子 agent 事件正常处理
- 审批请求正确传递到 UI
- `delegate_call_id` 可用于关联和特殊展示

## 架构优势

### 职责清晰
- WebSocket 层：只负责传输
- Reducer 层：负责事件识别和状态转换
- UI 层：可根据 `delegate_call_id` 决定展示方式

### 扩展性强
- 保留了后端的语义标识（`sub_agent:` 前缀）
- 提供了明确的关联关系（`delegate_call_id`）
- 便于未来添加子 agent 特有的 UI 展示

### 向后兼容
- 非子 agent 事件保持原有处理方式
- 不破坏现有事件流

## 验证结果

```bash
# TypeScript 编译
✅ npm run build - 成功

# 单元测试
✅ 25 个 reducer 测试全部通过
✅ 所有 203 个测试通过

# 新增测试
✅ sub_agent 事件前缀处理
✅ sub_agent 审批状态更新
✅ 完整的子 agent 审批工作流
```

## 相关文件

### 修改的文件
- `frontend/src/types/conversation.ts` - 添加 `delegate_call_id` 字段
- `frontend/src/features/conversation/conversation.reducer.ts` - 添加子 agent 事件处理逻辑
- `frontend/src/features/conversation/__tests__/conversation.reducer.test.ts` - 添加测试用例

### 新增的文档
- `frontend/docs/sub-agent-event-handling.md` - 详细的技术文档

## 后续建议

1. **UI 展示优化**：根据 `delegate_call_id` 在 UI 中区分主/子 agent 的消息
2. **嵌套展示**：考虑将子 agent 的消息缩进显示在 delegate tool call 下方
3. **视觉标识**：为子 agent 消息添加特殊图标或颜色标识

## 总结

这个修复解决了一个关键的功能缺陷：**子 agent 的审批请求现在可以正确到达前端 UI**。修复采用了职责清晰的架构设计，在 reducer 层统一处理所有事件类型，保持了代码的可维护性和扩展性。

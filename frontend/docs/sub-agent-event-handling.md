# 子 Agent 事件处理机制

## 背景

当后端使用 `delegate` 工具创建子 agent 时，子 agent 产生的所有事件都会被添加 `sub_agent:` 前缀，以区分主 agent 和子 agent 的事件。

## 后端事件格式

后端在 `delegate_tool.py` 中发送子 agent 事件时会添加前缀：

```python
# 第 130 行
await parent_cb(f"sub_agent:{event_type}", enriched)
```

因此：
- `approval:required` → `sub_agent:approval:required`
- `message.created` → `sub_agent:message.created`
- `run.waiting_for_approval` → `sub_agent:run.waiting_for_approval`

同时，后端会在事件的 payload 中注入 `delegate_call_id` 字段，用于将子 agent 事件关联到父 agent 的 delegate tool call。

## 前端处理机制

### 类型定义

在 `types/conversation.ts` 中，`ConversationEvent` 接口添加了 `delegate_call_id` 字段：

```typescript
export interface ConversationEvent {
  // ... 其他字段
  delegate_call_id?: string  // 关联到父 agent 的 delegate tool call
}
```

### Reducer 处理逻辑

在 `conversation.reducer.ts` 的 `applyConversationEvent` 函数中：

```typescript
// 识别并处理 sub_agent: 前缀
let actualEvent = event
if (event.eventType.startsWith('sub_agent:')) {
  const actualEventType = event.eventType.replace('sub_agent:', '')
  actualEvent = {
    ...event,
    eventType: actualEventType,
    // delegate_call_id 保留在事件中
  }
}

// 后续使用 actualEvent 进行正常的事件处理
```

### 处理流程

1. **识别子 agent 事件**：检查 `eventType` 是否以 `sub_agent:` 开头
2. **提取实际事件类型**：移除前缀，得到原始事件类型（如 `message.created`）
3. **保留关联信息**：`delegate_call_id` 字段保留在事件中，供 UI 层使用
4. **统一处理**：使用提取后的事件类型，按照正常事件流程处理

## 示例：完整的子 agent 审批流程

### 1. 父 agent 创建 delegate 调用

```json
{
  "eventType": "message.created",
  "payloadJson": {
    "message_type": "tool_trace",
    "payload_json": {
      "tool_name": "delegate",
      "tool_call_id": "delegate-call-123",
      "arguments": {
        "task": "Fix the bug in utils.ts"
      }
    }
  }
}
```

### 2. 子 agent 需要审批的工具调用

```json
{
  "eventType": "sub_agent:message.created",
  "delegate_call_id": "delegate-call-123",
  "payloadJson": {
    "message_type": "tool_trace",
    "payload_json": {
      "tool_name": "shell",
      "tool_call_id": "shell-call-456",
      "arguments": {
        "command": "rm -rf /tmp/cache"
      }
    }
  }
}
```

### 3. 子 agent run 进入等待审批状态

```json
{
  "eventType": "sub_agent:run.waiting_for_approval",
  "delegate_call_id": "delegate-call-123",
  "payloadJson": {}
}
```

## UI 展示建议

前端可以根据 `delegate_call_id` 字段来判断消息是否来自子 agent：

```typescript
const isSubAgentMessage = (message: ConversationMessage, event: ConversationEvent) => {
  return event.delegate_call_id !== undefined
}
```

可选的 UI 展示方式：
- **嵌套展示**：将子 agent 的消息缩进显示在父 agent 的 delegate tool call 下方
- **标记展示**：为子 agent 的消息添加特殊标记（如图标、颜色）
- **独立展示**：保持平铺展示，但添加视觉提示表明其来源

## 测试

在 `conversation.reducer.test.ts` 中包含了完整的子 agent 事件处理测试：

- ✅ 基本的 `sub_agent:` 前缀移除
- ✅ 子 agent 的 `run.waiting_for_approval` 处理
- ✅ 完整的子 agent 审批工作流

运行测试：

```bash
npm test -- conversation.reducer.test.ts
```

## 架构优势

### 职责清晰
- **WebSocket 层**：只负责接收和分发原始事件
- **Reducer 层**：负责识别和处理事件类型，包括子 agent 事件

### 扩展性强
- 保留了后端的语义标识（`sub_agent:` 前缀）
- `delegate_call_id` 提供了明确的关联关系
- 便于未来添加子 agent 特有的处理逻辑

### 向后兼容
- 不破坏现有事件处理流程
- 非子 agent 事件保持原有处理方式

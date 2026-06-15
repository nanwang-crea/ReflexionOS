# 多模态前端集成设计文档

## 概述

实现前端多模态支持，允许用户在对话中上传图片（粘贴/拖拽/文件选择），与文字一起发送给 LLM 进行分析。

## 前提

后端已完全实现多模态支持：
- `POST /api/sessions/{session_id}/upload` — 上传图片，返回 `attachment_id`
- WebSocket `conversation:start_turn` 已支持 `attachment_ids` 字段
- 后端完整链路：upload → attachment_ids → agent_service → message_repo → context_assembly → OpenAI adapter → LLM API

## 设计方案

采用方案 B：Composable Hooks + 独立组件

### 架构

```
ChatInput.tsx (组合层)
├── useImageUpload.ts (hook: 上传、压缩、状态管理)
├── ImagePreview.tsx (组件: 预览、删除、重试)
└── 模型视觉能力检测 (内联逻辑)
```

### 数据流

```
用户粘贴/拖拽/选择图片
    ↓
useImageUpload.addFiles(files)
    ↓
客户端压缩 (>1MB)
    ↓
POST /api/sessions/{sessionId}/upload
    ↓
返回 attachment_id → 更新 pendingAttachments 状态
    ↓
用户点击发送
    ↓
sendMessage(content, attachmentIds)
    ↓
buildStartTurnMessage({ content, attachmentIds })
    ↓
WebSocket 发送 conversation:start_turn
    ↓
发送成功 → clearAttachments()
```

---

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/hooks/useImageUpload.ts` | 图片上传 hook（压缩、上传、重试、状态管理） |
| `frontend/src/components/chat/ImagePreview.tsx` | 图片预览组件 |
| `frontend/src/constants/visionModels.ts` | 支持视觉的模型列表 |

### 修改文件

| 文件 | 说明 |
|------|------|
| `frontend/src/components/chat/ChatInput.tsx` | 添加粘贴/拖拽/上传按钮/预览区域 |
| `frontend/src/services/sessionConversationWebSocket.ts` | `buildStartTurnMessage` 增加 `attachment_ids` |
| `frontend/src/hooks/useConversationRuntime.ts` | `startTurn` 接口增加 `attachmentIds` |
| `frontend/src/hooks/useSendMessage.ts` | 传递 `attachmentIds` 到 `startTurn` |
| `frontend/src/components/workspace/UserMessageItem.tsx` | 显示已发送的图片 |

---

## 详细设计

### 1. useImageUpload hook

**文件**: `frontend/src/hooks/useImageUpload.ts`

**状态**:
```typescript
interface PendingAttachment {
  id: string           // 前端临时 ID (crypto.randomUUID())
  serverId?: string    // 后端返回的 attachment_id
  file: File
  previewUrl: string   // URL.createObjectURL
  status: 'compressing' | 'uploading' | 'uploaded' | 'error'
  error?: string
  retryCount: number
}
```

**接口**:
```typescript
function useImageUpload(sessionId: string | null) {
  return {
    attachments: PendingAttachment[],
    addFiles: (files: File[]) => Promise<void>,
    removeAttachment: (id: string) => void,
    clearAttachments: () => void,
    retryUpload: (id: string) => Promise<void>,
    uploadedIds: string[],  // 已上传的 attachment_id 列表
    isUploading: boolean,
  }
}
```

**压缩逻辑**:
- 触发：文件 > 1MB
- 方法：canvas 绘制，最大 2048px 宽/高，质量 0.8
- 输出：image/jpeg

**上传逻辑**:
- FormData POST 到 `/api/sessions/${sessionId}/upload`
- 失败重试 2 次（指数退避 1s, 2s）
- 错误状态标记到 attachment

### 2. ImagePreview 组件

**文件**: `frontend/src/components/chat/ImagePreview.tsx`

**Props**:
```typescript
interface ImagePreviewProps {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
  onRetry: (id: string) => void
}
```

**UI**:
- 水平滚动区域，每个缩略图 64x64px，圆角
- 上传中：半透明 + spinner
- 上传失败：红色边框 + 重试按钮
- hover 显示删除按钮 (X)
- 点击可放大预览（可选）

### 3. ChatInput 修改

**新增 Props**:
```typescript
interface ChatInputProps {
  // ... existing props
  onImageAdd?: (files: File[]) => void
  attachments?: PendingAttachment[]
  onRemoveAttachment?: (id: string) => void
  onRetryAttachment?: (id: string) => void
}
```

**新增功能**:

1. **粘贴支持** (onPaste):
   - 检测 `clipboardData.items` 中的 `image/*` 类型
   - 调用 `onImageAdd(files)`

2. **拖拽支持** (onDragOver/onDrop):
   - 拖入时边框高亮
   - drop 时提取 `image/*` 文件

3. **上传按钮**:
   - 工具栏添加图片按钮 (Image icon)
   - 点击触发隐藏的 `<input type="file" accept="image/*" multiple />`

4. **预览区域**:
   - textarea 上方显示 ImagePreview 组件
   - 有待上传图片时显示

### 4. WebSocket 消息扩展

**修改 `sessionConversationWebSocket.ts`**:

```typescript
function buildStartTurnMessage(payload: {
  content: string
  providerId?: string | null
  modelId?: string | null
  attachmentIds?: string[]  // 新增
}) {
  return {
    type: 'conversation:start_turn',
    data: {
      content: payload.content,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
      attachment_ids: payload.attachmentIds ?? [],  // 新增
    },
  }
}
```

`startTurn` 方法签名同步更新。

### 5. 发送消息流扩展

**修改 `useConversationRuntime.ts`**:

`StartTurnPayload` 增加 `attachmentIds?: string[]`。

**修改 `useSendMessage.ts`**:

`createSendMessage` 接口增加 `attachmentIds?: string[]`，传递到 `startTurn`。

### 6. UserMessageItem 修改

**新增 Props**:
```typescript
interface UserMessageItemProps {
  // ... existing props
  attachments?: Array<{
    id: string
    previewUrl?: string  // 本地预览 URL（可选）
    mimeType?: string
  }>
}
```

**UI**:
- 在文字气泡上方显示图片缩略图网格
- 最多显示 4 张图片，超出显示 +N
- 点击可放大预览（dialog）

### 7. 模型视觉能力检测

**新增 `frontend/src/constants/visionModels.ts`**:

```typescript
export const VISION_MODELS = [
  'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4-vision-preview',
  'claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku', 'claude-3-5-sonnet', 'claude-fable-5',
  'gemini-pro-vision', 'gemini-1.5-pro', 'gemini-1.5-flash',
]

export function supportsVision(modelId: string): boolean {
  return VISION_MODELS.some(m => modelId.startsWith(m))
}
```

**检测时机**:
- 用户添加图片时检测当前模型
- 不支持视觉时显示 toast 警告
- 不阻止上传和发送（后端也有校验）

---

## 错误处理

| 场景 | 处理 |
|------|------|
| 上传失败（网络） | toast 错误 + 标记 error 状态 + 重试按钮 |
| 上传失败（文件过大） | toast 提示最大 10MB |
| 上传失败（非图片） | toast 提示只支持图片 |
| 模型不支持视觉 | toast 警告 + 建议切换模型 |
| 发送时后端报错 | 消息气泡中显示错误提示 |
| 压缩失败 | 使用原始文件上传 |

---

## 性能考虑

- **压缩**：>1MB 图片在客户端压缩，减少上传时间和后端存储
- **预览 URL**：使用 `URL.createObjectURL`，组件卸载时 `revokeObjectURL` 释放内存
- **并发上传**：多张图片并行上传（最多 3 个并发）
- **文件大小限制**：前端校验 10MB，与后端一致

# 多模态前端集成实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现前端多模态支持，允许用户粘贴/拖拽/选择图片上传，与文字一起发送给 LLM 分析

**Architecture:** 采用 Composable Hooks + 独立组件方案。useImageUpload hook 封装上传/压缩/状态管理，ImagePreview 组件负责预览和删除，ChatInput 组合它们。WebSocket 消息增加 attachment_ids 字段。

**Tech Stack:** React, TypeScript, Zustand, Framer Motion, Tailwind CSS

---

## 文件结构

### 新增文件
- `frontend/src/hooks/useImageUpload.ts` — 图片上传 hook
- `frontend/src/components/chat/ImagePreview.tsx` — 图片预览组件
- `frontend/src/constants/visionModels.ts` — 视觉模型列表

### 修改文件
- `frontend/src/components/chat/ChatInput.tsx` — 添加粘贴/拖拽/上传按钮
- `frontend/src/services/sessionConversationWebSocket.ts` — 增加 attachment_ids
- `frontend/src/hooks/useConversationRuntime.ts` — startTurn 增加 attachmentIds
- `frontend/src/hooks/useSendMessage.ts` — 传递 attachmentIds
- `frontend/src/components/workspace/UserMessageItem.tsx` — 显示已发送图片

---

## Task 1: 视觉模型常量

**Files:**
- Create: `frontend/src/constants/visionModels.ts`

- [ ] **Step 1: 创建视觉模型常量文件**

```typescript
// frontend/src/constants/visionModels.ts
export const VISION_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4-turbo',
  'gpt-4-vision-preview',
  'claude-3-opus',
  'claude-3-sonnet',
  'claude-3-haiku',
  'claude-3-5-sonnet',
  'claude-fable-5',
  'gemini-pro-vision',
  'gemini-1.5-pro',
  'gemini-1.5-flash',
]

export function supportsVision(modelId: string | null | undefined): boolean {
  if (!modelId) return false
  return VISION_MODELS.some((m) => modelId.startsWith(m))
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/constants/visionModels.ts
git commit -m "feat: add vision model capability constants"
```

---

## Task 2: useImageUpload hook

**Files:**
- Create: `frontend/src/hooks/useImageUpload.ts`

- [ ] **Step 1: 创建 useImageUpload hook**

```typescript
// frontend/src/hooks/useImageUpload.ts
import { useCallback, useRef, useState } from 'react'

export interface PendingAttachment {
  id: string
  serverId?: string
  file: File
  previewUrl: string
  status: 'compressing' | 'uploading' | 'uploaded' | 'error'
  error?: string
  retryCount: number
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const MAX_RETRY = 2
const MAX_DIMENSION = 2048
const COMPRESS_THRESHOLD = 1024 * 1024 // 1MB

async function compressImage(file: File): Promise<File> {
  if (file.size <= COMPRESS_THRESHOLD) {
    return file
  }

  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)

    img.onload = () => {
      URL.revokeObjectURL(url)

      let { width, height } = img
      if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
        const ratio = Math.min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        width = Math.round(width * ratio)
        height = Math.round(height * ratio)
      }

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        resolve(file)
        return
      }

      ctx.drawImage(img, 0, 0, width, height)
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file)
            return
          }
          const compressed = new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), {
            type: 'image/jpeg',
            lastModified: Date.now(),
          })
          resolve(compressed)
        },
        'image/jpeg',
        0.8
      )
    }

    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(file)
    }

    img.src = url
  })
}

async function uploadFile(
  sessionId: string,
  file: File,
  signal?: AbortSignal
): Promise<{ attachment_id: string }> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`/api/sessions/${sessionId}/upload`, {
    method: 'POST',
    body: formData,
    signal,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(error.detail || '上传失败')
  }

  return response.json()
}

export function useImageUpload(sessionId: string | null) {
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())

  const uploadedIds = attachments
    .filter((a) => a.status === 'uploaded' && a.serverId)
    .map((a) => a.serverId!)

  const isUploading = attachments.some(
    (a) => a.status === 'compressing' || a.status === 'uploading'
  )

  const doUpload = useCallback(
    async (attachment: PendingAttachment) => {
      if (!sessionId) return

      const controller = new AbortController()
      abortControllersRef.current.set(attachment.id, controller)

      try {
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === attachment.id ? { ...a, status: 'uploading' as const, error: undefined } : a
          )
        )

        const result = await uploadFile(sessionId, attachment.file, controller.signal)

        setAttachments((prev) =>
          prev.map((a) =>
            a.id === attachment.id
              ? { ...a, status: 'uploaded' as const, serverId: result.attachment_id }
              : a
          )
        )
      } catch (err) {
        if (controller.signal.aborted) return

        const errorMsg = err instanceof Error ? err.message : '上传失败'
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === attachment.id
              ? { ...a, status: 'error' as const, error: errorMsg }
              : a
          )
        )
      } finally {
        abortControllersRef.current.delete(attachment.id)
      }
    },
    [sessionId]
  )

  const addFiles = useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter((f) => f.type.startsWith('image/'))
      if (imageFiles.length === 0) return

      const oversized = imageFiles.filter((f) => f.size > MAX_FILE_SIZE)
      if (oversized.length > 0) {
        throw new Error(`图片大小超过限制（最大 10MB）：${oversized.map((f) => f.name).join(', ')}`)
      }

      const newAttachments: PendingAttachment[] = imageFiles.map((file) => ({
        id: crypto.randomUUID(),
        file,
        previewUrl: URL.createObjectURL(file),
        status: 'compressing' as const,
        retryCount: 0,
      }))

      setAttachments((prev) => [...prev, ...newAttachments])

      for (const attachment of newAttachments) {
        try {
          const compressed = await compressImage(attachment.file)
          const updatedAttachment = { ...attachment, file: compressed }
          setAttachments((prev) =>
            prev.map((a) => (a.id === attachment.id ? updatedAttachment : a))
          )
          await doUpload(updatedAttachment)
        } catch {
          setAttachments((prev) =>
            prev.map((a) =>
              a.id === attachment.id
                ? { ...a, status: 'error' as const, error: '压缩失败' }
                : a
            )
          )
        }
      }
    },
    [doUpload]
  )

  const removeAttachment = useCallback((id: string) => {
    const controller = abortControllersRef.current.get(id)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(id)
    }

    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id)
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return prev.filter((a) => a.id !== id)
    })
  }, [])

  const clearAttachments = useCallback(() => {
    abortControllersRef.current.forEach((controller) => controller.abort())
    abortControllersRef.current.clear()

    setAttachments((prev) => {
      prev.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl)
      })
      return []
    })
  }, [])

  const retryUpload = useCallback(
    async (id: string) => {
      const attachment = attachments.find((a) => a.id === id)
      if (!attachment || attachment.status !== 'error') return
      if (attachment.retryCount >= MAX_RETRY) return

      setAttachments((prev) =>
        prev.map((a) =>
          a.id === id ? { ...a, retryCount: a.retryCount + 1, status: 'uploading' as const } : a
        )
      )

      await doUpload({ ...attachment, retryCount: attachment.retryCount + 1 })
    },
    [attachments, doUpload]
  )

  return {
    attachments,
    addFiles,
    removeAttachment,
    clearAttachments,
    retryUpload,
    uploadedIds,
    isUploading,
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/hooks/useImageUpload.ts
git commit -m "feat: add useImageUpload hook with compression and retry"
```

---

## Task 3: ImagePreview 组件

**Files:**
- Create: `frontend/src/components/chat/ImagePreview.tsx`

- [ ] **Step 1: 创建 ImagePreview 组件**

```tsx
// frontend/src/components/chat/ImagePreview.tsx
import { memo } from 'react'
import { Loader2, RotateCcw, X } from 'lucide-react'
import type { PendingAttachment } from '@/hooks/useImageUpload'

interface ImagePreviewProps {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
  onRetry: (id: string) => void
}

export const ImagePreview = memo(function ImagePreview({
  attachments,
  onRemove,
  onRetry,
}: ImagePreviewProps) {
  if (attachments.length === 0) return null

  return (
    <div className="flex gap-2 overflow-x-auto px-3 py-2 border-b border-edge-subtle">
      {attachments.map((attachment) => (
        <div
          key={attachment.id}
          className="relative group shrink-0"
        >
          <div
            className={`h-16 w-16 overflow-hidden rounded-lg border-2 ${
              attachment.status === 'error'
                ? 'border-status-error'
                : 'border-edge-subtle'
            }`}
          >
            <img
              src={attachment.previewUrl}
              alt="预览"
              className="h-full w-full object-cover"
            />

            {(attachment.status === 'compressing' || attachment.status === 'uploading') && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                <Loader2 className="h-5 w-5 animate-spin text-white" />
              </div>
            )}

            {attachment.status === 'error' && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                <button
                  type="button"
                  onClick={() => onRetry(attachment.id)}
                  className="rounded-full bg-white/20 p-1 hover:bg-white/40 transition-colors"
                  title="重试上传"
                >
                  <RotateCcw className="h-3 w-3 text-white" />
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => onRemove(attachment.id)}
            className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-surface-tertiary border border-edge text-content-muted opacity-0 group-hover:opacity-100 transition-opacity hover:bg-status-error hover:text-white hover:border-status-error"
          >
            <X className="h-3 w-3" />
          </button>

          {attachment.error && (
            <div className="absolute left-1/2 top-full z-10 mt-1 w-max max-w-[200px] -translate-x-1/2 rounded-md bg-status-error-soft px-2 py-1 text-xs text-status-error opacity-0 group-hover:opacity-100 transition-opacity">
              {attachment.error}
            </div>
          )}
        </div>
      ))}
    </div>
  )
})
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/chat/ImagePreview.tsx
git commit -m "feat: add ImagePreview component for upload preview"
```

---

## Task 4: WebSocket 消息扩展

**Files:**
- Modify: `frontend/src/services/sessionConversationWebSocket.ts:107-120`
- Modify: `frontend/src/services/sessionConversationWebSocket.ts:306-310`

- [ ] **Step 1: 修改 buildStartTurnMessage 增加 attachmentIds**

在 `frontend/src/services/sessionConversationWebSocket.ts` 中修改 `buildStartTurnMessage` 函数：

```typescript
// 原代码 (107-120):
function buildStartTurnMessage(payload: {
  content: string
  providerId?: string | null
  modelId?: string | null
}) {
  return {
    type: 'conversation:start_turn',
    data: {
      content: payload.content,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
    },
  }
}

// 改为:
function buildStartTurnMessage(payload: {
  content: string
  providerId?: string | null
  modelId?: string | null
  attachmentIds?: string[]
}) {
  return {
    type: 'conversation:start_turn',
    data: {
      content: payload.content,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
      attachment_ids: payload.attachmentIds ?? [],
    },
  }
}
```

- [ ] **Step 2: 修改 startTurn 方法签名**

```typescript
// 原代码 (306-310):
startTurn(payload: { content: string; providerId?: string | null; modelId?: string | null }): void {
  if (this.ws && this.ws.readyState === WebSocket.OPEN) {
    this.ws.send(JSON.stringify(buildStartTurnMessage(payload)))
  }
}

// 改为:
startTurn(payload: { content: string; providerId?: string | null; modelId?: string | null; attachmentIds?: string[] }): void {
  if (this.ws && this.ws.readyState === WebSocket.OPEN) {
    this.ws.send(JSON.stringify(buildStartTurnMessage(payload)))
  }
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/services/sessionConversationWebSocket.ts
git commit -m "feat: add attachment_ids support to WebSocket startTurn message"
```

---

## Task 5: useConversationRuntime 扩展

**Files:**
- Modify: `frontend/src/hooks/useConversationRuntime.ts`

- [ ] **Step 1: 修改 StartTurnPayload 接口**

在 `frontend/src/hooks/useConversationRuntime.ts` 中找到 `StartTurnPayload` 接口（通常在文件开头或 hook 内部），增加 `attachmentIds`：

```typescript
// 找到类似这样的接口定义:
interface StartTurnPayload {
  sessionId: string
  message: string
  providerId: string
  modelId: string
}

// 改为:
interface StartTurnPayload {
  sessionId: string
  message: string
  providerId: string
  modelId: string
  attachmentIds?: string[]
}
```

- [ ] **Step 2: 修改 startTurn 回调传递 attachmentIds**

找到 `startTurn` 回调中调用 `wsRef.current?.startTurn` 的位置（约第 372 行），修改为：

```typescript
// 原代码:
wsRef.current?.startTurn({
  content,
  providerId: payload.providerId,
  modelId: payload.modelId,
})

// 改为:
wsRef.current?.startTurn({
  content,
  providerId: payload.providerId,
  modelId: payload.modelId,
  attachmentIds: payload.attachmentIds,
})
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/hooks/useConversationRuntime.ts
git commit -m "feat: pass attachmentIds through useConversationRuntime startTurn"
```

---

## Task 6: useSendMessage 扩展

**Files:**
- Modify: `frontend/src/hooks/useSendMessage.ts:26-32`
- Modify: `frontend/src/hooks/useSendMessage.ts:36`
- Modify: `frontend/src/hooks/useSendMessage.ts:83-88`
- Modify: `frontend/src/hooks/useSendMessage.ts:97-118`

- [ ] **Step 1: 修改 SendMessageDependencies 接口**

```typescript
// 原代码 (26-32):
startTurn: (payload: {
  sessionId: string
  message: string
  providerId: string
  modelId: string
}) => Promise<void> | void

// 改为:
startTurn: (payload: {
  sessionId: string
  message: string
  providerId: string
  modelId: string
  attachmentIds?: string[]
}) => Promise<void> | void
```

- [ ] **Step 2: 修改 createSendMessage 函数签名**

```typescript
// 原代码 (36):
return async function sendMessage(message: string) {

// 改为:
return async function sendMessage(message: string, attachmentIds?: string[]) {
```

- [ ] **Step 3: 修改 startTurn 调用**

```typescript
// 原代码 (83-88):
await dependencies.startTurn({
  sessionId: targetSession.id,
  message,
  providerId: dependencies.selection.providerId,
  modelId: dependencies.selection.modelId,
})

// 改为:
await dependencies.startTurn({
  sessionId: targetSession.id,
  message,
  providerId: dependencies.selection.providerId,
  modelId: dependencies.selection.modelId,
  attachmentIds,
})
```

- [ ] **Step 4: 修改 useSendMessage hook 返回值类型**

```typescript
// 原代码 (97-118):
export function useSendMessage(options: {
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  startTurn: SendMessageDependencies['startTurn']
}) {
  const { currentProject } = useProjectStore()
  const { createSession } = useSessionActions()

  const sendMessage = useCallback(async (message: string) => {
    const sendFn = createSendMessage({
      currentProject,
      currentSession: options.currentSession,
      configured: options.configured,
      selection: options.selection,
      createSession,
      writeSessionPreferences: writeSessionPreferencesAction,
      startTurn: options.startTurn,
      notify: nativeDialogService.notifyError,
    })
    await sendFn(message)
  }, [currentProject, options.currentSession, options.configured, options.selection, createSession, options.startTurn])

  return {
    sendMessage,
  }
}

// 改为:
export function useSendMessage(options: {
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  startTurn: SendMessageDependencies['startTurn']
}) {
  const { currentProject } = useProjectStore()
  const { createSession } = useSessionActions()

  const sendMessage = useCallback(async (message: string, attachmentIds?: string[]) => {
    const sendFn = createSendMessage({
      currentProject,
      currentSession: options.currentSession,
      configured: options.configured,
      selection: options.selection,
      createSession,
      writeSessionPreferences: writeSessionPreferencesAction,
      startTurn: options.startTurn,
      notify: nativeDialogService.notifyError,
    })
    await sendFn(message, attachmentIds)
  }, [currentProject, options.currentSession, options.configured, options.selection, createSession, options.startTurn])

  return {
    sendMessage,
  }
}
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/hooks/useSendMessage.ts
git commit -m "feat: pass attachmentIds through useSendMessage hook"
```

---

## Task 7: ChatInput 组件修改

**Files:**
- Modify: `frontend/src/components/chat/ChatInput.tsx`

- [ ] **Step 1: 添加 imports 和新 props**

在 `ChatInput.tsx` 顶部添加 import：

```typescript
import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Image as ImageIcon, Loader2, Send, Square } from 'lucide-react'  // 新增 ImageIcon
import { RunningIndicator } from '@/components/workspace/RunningIndicator'
import { ImagePreview } from '@/components/chat/ImagePreview'  // 新增
import type { PendingAttachment } from '@/hooks/useImageUpload'  // 新增
```

在 `ChatInputProps` 接口中添加新 props：

```typescript
interface ChatInputProps {
  // ... 所有现有 props 保持不变
  onImageAdd?: (files: File[]) => void
  attachments?: PendingAttachment[]
  onRemoveAttachment?: (id: string) => void
  onRetryAttachment?: (id: string) => void
}
```

在解构参数中添加新 props：

```typescript
export function ChatInput({ 
  onSend, 
  onCancel,
  disabled = false, 
  placeholder = '描述你想要 Agent 做...',
  isLoading = false,
  canCancel = false,
  isCancelling = false,
  providerOptions = [],
  modelOptions = [],
  selectedProviderId = null,
  selectedModelId = null,
  onProviderChange,
  onModelChange,
  selectionDisabled = false,
  runtimeStatusLabel = null,
  agentMode = 'build',
  onModeChange,
  onImageAdd,           // 新增
  attachments = [],     // 新增
  onRemoveAttachment,   // 新增
  onRetryAttachment,    // 新增
}: ChatInputProps) {
```

- [ ] **Step 2: 添加粘贴和拖拽处理**

在 `ChatInput` 组件内，`handleSend` 函数之后添加：

```typescript
const [isDragOver, setIsDragOver] = useState(false)
const fileInputRef = useRef<HTMLInputElement>(null)

const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
  if (!onImageAdd) return
  const items = e.clipboardData?.items
  if (!items) return

  const imageFiles: File[] = []
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) imageFiles.push(file)
    }
  }

  if (imageFiles.length > 0) {
    e.preventDefault()
    onImageAdd(imageFiles)
  }
}

const handleDragOver = (e: React.DragEvent) => {
  e.preventDefault()
  e.stopPropagation()
  if (onImageAdd) setIsDragOver(true)
}

const handleDragLeave = (e: React.DragEvent) => {
  e.preventDefault()
  e.stopPropagation()
  setIsDragOver(false)
}

const handleDrop = (e: React.DragEvent) => {
  e.preventDefault()
  e.stopPropagation()
  setIsDragOver(false)

  if (!onImageAdd) return

  const files = Array.from(e.dataTransfer.files).filter((f) =>
    f.type.startsWith('image/')
  )
  if (files.length > 0) {
    onImageAdd(files)
  }
}

const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
  if (!onImageAdd) return
  const files = Array.from(e.target.files || []).filter((f) =>
    f.type.startsWith('image/')
  )
  if (files.length > 0) {
    onImageAdd(files)
  }
  e.target.value = ''
}
```

- [ ] **Step 3: 修改 textarea 添加粘贴事件和拖拽区域**

修改 textarea 所在的容器 div，添加拖拽事件和高亮：

```tsx
// 原代码:
<motion.div
  className="relative overflow-hidden rounded-2xl border-2 border-edge bg-surface-primary focus-within:border-accent transition-all duration-200"
  animate={{ scale: isFocused ? 1.01 : 1 }}
  transition={{ duration: 0.2 }}
>

// 改为:
<motion.div
  className={`relative overflow-hidden rounded-2xl border-2 bg-surface-primary focus-within:border-accent transition-all duration-200 ${
    isDragOver ? 'border-accent bg-accent/5' : 'border-edge'
  }`}
  animate={{ scale: isFocused ? 1.01 : 1 }}
  transition={{ duration: 0.2 }}
  onDragOver={handleDragOver}
  onDragLeave={handleDragLeave}
  onDrop={handleDrop}
>
```

修改 textarea 添加 onPaste：

```tsx
// 原代码:
<textarea
  ref={textareaRef}
  value={value}
  onChange={(e) => setValue(e.target.value)}
  onFocus={() => setIsFocused(true)}
  onBlur={() => setIsFocused(false)}
  onCompositionStart={() => setIsComposing(true)}
  onCompositionEnd={() => setIsComposing(false)}
  onKeyDown={handleKeyDown}
  placeholder={placeholder}
  disabled={disabled || isLoading}
  rows={1}
  className="min-h-[88px] w-full resize-none bg-transparent px-4 py-3 pr-4 text-[15px] leading-7 text-content-secondary outline-none disabled:cursor-not-allowed disabled:bg-surface-tertiary"
/>

// 改为:
<textarea
  ref={textareaRef}
  value={value}
  onChange={(e) => setValue(e.target.value)}
  onFocus={() => setIsFocused(true)}
  onBlur={() => setIsFocused(false)}
  onCompositionStart={() => setIsComposing(true)}
  onCompositionEnd={() => setIsComposing(false)}
  onKeyDown={handleKeyDown}
  onPaste={handlePaste}
  placeholder={attachments.length > 0 ? '添加图片说明（可选）...' : placeholder}
  disabled={disabled || isLoading}
  rows={1}
  className="min-h-[88px] w-full resize-none bg-transparent px-4 py-3 pr-4 text-[15px] leading-7 text-content-secondary outline-none disabled:cursor-not-allowed disabled:bg-surface-tertiary"
/>
```

- [ ] **Step 4: 在 textarea 上方添加 ImagePreview**

在 textarea 元素之前（runtimeStatusLabel 判断之后）插入：

```tsx
{runtimeStatusLabel && (
  <RunningIndicator
    label={runtimeStatusLabel}
    layout="header"
    rootDataAttr="data-chat-running"
    barDataAttr="data-chat-running-bar"
  />
)}
{/* 新增: 图片预览区域 */}
<ImagePreview
  attachments={attachments}
  onRemove={onRemoveAttachment ?? (() => {})}
  onRetry={onRetryAttachment ?? (() => {})}
/>
```

- [ ] **Step 5: 在工具栏添加图片上传按钮**

在工具栏中 `agentMode` 按钮之后添加图片按钮和隐藏的 file input：

```tsx
<button
  type="button"
  onClick={() => onModeChange?.(agentMode === 'build' ? 'plan' : 'build')}
  disabled={selectionDisabled}
  className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors disabled:cursor-not-allowed ${
    agentMode === 'plan'
      ? 'bg-blue-500/15 text-blue-500'
      : 'bg-surface-tertiary text-content-secondary'
  }`}
>
  {agentMode === 'plan' ? 'PLAN' : 'BUILD'}
</button>
{/* 新增: 图片上传按钮 */}
{onImageAdd && (
  <>
    <input
      ref={fileInputRef}
      type="file"
      accept="image/*"
      multiple
      className="hidden"
      onChange={handleFileSelect}
    />
    <button
      type="button"
      onClick={() => fileInputRef.current?.click()}
      disabled={disabled || isLoading}
      className="rounded-full p-1.5 text-content-muted hover:text-content-secondary hover:bg-surface-tertiary transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      title="上传图片（或粘贴/拖拽图片）"
    >
      <ImageIcon className="h-4 w-4" />
    </button>
  </>
)}
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/chat/ChatInput.tsx
git commit -m "feat: add image paste, drag-drop, and upload button to ChatInput"
```

---

## Task 8: UserMessageItem 显示图片

**Files:**
- Modify: `frontend/src/components/workspace/UserMessageItem.tsx:1-16`
- Modify: `frontend/src/components/workspace/UserMessageItem.tsx:56-59`

- [ ] **Step 1: 添加 attachments prop**

```typescript
// 原代码 (1-16):
import { memo } from 'react'
import { Copy, Pencil } from 'lucide-react'
import { useToastStore } from '@/shared/stores/toast.store'

interface UserMessageItemProps {
  messageId: string
  contentText: string
  onEdit: (messageId: string, contentText: string) => void
  isEditing: boolean
  editContent: string
  onEditContentChange: (content: string) => void
  onEditCancel: () => void
  onEditSubmit: () => void
  showActions: boolean
}

// 改为:
import { memo } from 'react'
import { Copy, Pencil } from 'lucide-react'
import { useToastStore } from '@/shared/stores/toast.store'

interface MessageAttachment {
  id: string
  mimeType?: string
}

interface UserMessageItemProps {
  messageId: string
  contentText: string
  onEdit: (messageId: string, contentText: string) => void
  isEditing: boolean
  editContent: string
  onEditContentChange: (content: string) => void
  onEditCancel: () => void
  onEditSubmit: () => void
  showActions: boolean
  attachments?: MessageAttachment[]
}
```

- [ ] **Step 2: 在解构参数中添加 attachments**

```typescript
// 原代码:
export const UserMessageItem = memo(function UserMessageItem({
  messageId,
  contentText,
  onEdit,
  isEditing,
  editContent,
  onEditContentChange,
  onEditCancel,
  onEditSubmit,
  showActions,
}: UserMessageItemProps) {

// 改为:
export const UserMessageItem = memo(function UserMessageItem({
  messageId,
  contentText,
  onEdit,
  isEditing,
  editContent,
  onEditContentChange,
  onEditCancel,
  onEditSubmit,
  showActions,
  attachments = [],
}: UserMessageItemProps) {
```

- [ ] **Step 3: 在气泡上方添加图片网格显示**

在 `return` 语句中，气泡 div 之前添加图片网格：

```tsx
// 原代码 (56-59):
return (
  <div className="mb-6 flex min-w-0 flex-col items-end pr-8 group">
    {isEditing ? (

// 改为:
return (
  <div className="mb-6 flex min-w-0 flex-col items-end pr-8 group">
    {attachments.length > 0 && !isEditing && (
      <div className="mb-2 flex max-w-[min(720px,calc(100%_-_16px))] flex-wrap gap-1.5">
        {attachments.slice(0, 4).map((att) => (
          <div
            key={att.id}
            className="h-20 w-20 overflow-hidden rounded-lg border border-edge-subtle"
          >
            <div className="flex h-full w-full items-center justify-center bg-surface-tertiary text-xs text-content-muted">
              {att.mimeType?.startsWith('image/') ? '🖼️' : '📎'}
            </div>
          </div>
        ))}
        {attachments.length > 4 && (
          <div className="flex h-20 w-20 items-center justify-center rounded-lg border border-edge-subtle bg-surface-tertiary text-sm text-content-muted">
            +{attachments.length - 4}
          </div>
        )}
      </div>
    )}
    {isEditing ? (
```

注意：由于后端目前返回的 `ConversationMessage` 类型中没有 `attachments` 字段，这里先用占位显示。后续需要扩展 `ConversationMessage` 类型以包含附件信息，届时替换占位 UI 为真实的图片 URL 显示。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/workspace/UserMessageItem.tsx
git commit -m "feat: display attachment indicators in UserMessageItem"
```

---

## Task 9: 集成到页面组件

**Files:**
- Modify: 使用 ChatInput 的页面组件（需要查找并传入新 props）

- [ ] **Step 1: 查找使用 ChatInput 的组件**

运行以下命令找到 ChatInput 的使用位置：

```bash
grep -r "ChatInput" frontend/src --include="*.tsx" --include="*.ts" -l
```

- [ ] **Step 2: 在使用 ChatInput 的组件中集成 useImageUpload**

假设 ChatInput 在某个 Workspace 页面中使用，需要：

```typescript
// 在使用 ChatInput 的组件中添加:
import { useImageUpload } from '@/hooks/useImageUpload'
import { supportsVision } from '@/constants/visionModels'
import { useToastStore } from '@/shared/stores/toast.store'

// 在组件内部:
const { attachments, addFiles, removeAttachment, clearAttachments, retryUpload, uploadedIds } =
  useImageUpload(currentSession?.id ?? null)

const handleImageAdd = useCallback(
  (files: File[]) => {
    // 检查模型是否支持视觉
    if (selection.modelId && !supportsVision(selection.modelId)) {
      useToastStore.getState().addToast(
        'warning',
        '当前模型可能不支持图片分析，建议切换到 gpt-4o 等模型'
      )
    }
    addFiles(files)
  },
  [selection.modelId, addFiles]
)

// 修改 sendMessage 调用，在发送成功后清空附件
const handleSend = useCallback(
  async (message: string) => {
    await sendMessage(message, uploadedIds.length > 0 ? uploadedIds : undefined)
    clearAttachments()
  },
  [sendMessage, uploadedIds, clearAttachments]
)
```

- [ ] **Step 3: 传入 ChatInput 的新 props**

```tsx
<ChatInput
  // ... 所有现有 props
  onImageAdd={handleImageAdd}
  attachments={attachments}
  onRemoveAttachment={removeAttachment}
  onRetryAttachment={retryUpload}
/>
```

- [ ] **Step 4: 提交**

```bash
git add <modified files>
git commit -m "feat: integrate multimodal image upload into workspace"
```

---

## Task 10: 端到端测试

- [ ] **Step 1: 启动开发服务器验证基本功能**

```bash
cd frontend && npm run dev
```

- [ ] **Step 2: 手动测试清单**

  - [ ] 粘贴图片到输入框 → 显示预览
  - [ ] 拖拽图片到输入框 → 显示预览
  - [ ] 点击图片按钮选择文件 → 显示预览
  - [ ] 多张图片同时添加 → 水平滚动预览
  - [ ] 删除已添加图片 → 预览消失
  - [ ] 上传失败 → 显示错误和重试按钮
  - [ ] 点击重试 → 重新上传
  - [ ] 发送带图片的消息 → 后端收到 attachment_ids
  - [ ] 切换到不支持视觉的模型 → 显示警告 toast
  - [ ] 输入框拖拽高亮效果正常

- [ ] **Step 3: 运行 lint 检查**

```bash
cd frontend && npm run lint
```

- [ ] **Step 4: 运行类型检查**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: 运行现有测试确保无回归**

```bash
cd frontend && npm test
```

---

## 实现计划自审

### 1. 规格覆盖检查
- ✅ 图片粘贴 — Task 7
- ✅ 图片拖拽 — Task 7
- ✅ 文件选择上传 — Task 7
- ✅ 客户端压缩 — Task 2
- ✅ 上传重试 — Task 2 + Task 3
- ✅ 图片预览 — Task 3
- ✅ WebSocket attachment_ids — Task 4
- ✅ startTurn 传递 — Task 5 + Task 6
- ✅ 消息气泡显示图片 — Task 8
- ✅ 模型视觉能力检测 — Task 1 + Task 9
- ✅ 错误处理 — Task 2 + Task 3 + Task 9

### 2. Placeholder 扫描
- 无 TBD/TODO
- Task 8 中图片显示为占位 emoji，因为后端消息类型暂无附件字段，已明确标注

### 3. 类型一致性
- `PendingAttachment`: Task 2 定义，Task 3/7 使用
- `StartTurnPayload`: Task 5 修改，与 Task 4/6 一致
- `attachmentIds`: 命名在所有 Task 中一致

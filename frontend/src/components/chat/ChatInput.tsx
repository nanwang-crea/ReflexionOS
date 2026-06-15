import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Image as ImageIcon, Loader2, Send, Square } from 'lucide-react'
import { RunningIndicator } from '@/components/workspace/RunningIndicator'
import { ImagePreview } from '@/components/chat/ImagePreview'
import type { PendingAttachment } from '@/features/conversation/hooks/useImageUpload'

interface ChatSelectOption {
  id: string
  label: string
}

interface ChatInputProps {
  onSend: (message: string) => void
  onCancel?: () => void
  disabled?: boolean
  placeholder?: string
  isLoading?: boolean
  canCancel?: boolean
  isCancelling?: boolean
  providerOptions?: ChatSelectOption[]
  modelOptions?: ChatSelectOption[]
  selectedProviderId?: string | null
  selectedModelId?: string | null
  onProviderChange?: (providerId: string | null) => void
  onModelChange?: (modelId: string | null) => void
  selectionDisabled?: boolean
  runtimeStatusLabel?: string | null
  agentMode?: 'build' | 'plan'
  onModeChange?: (mode: 'build' | 'plan') => void
  onImageAdd?: (files: File[]) => void
  attachments?: PendingAttachment[]
  onRemoveAttachment?: (id: string) => void
}

export function ChatInput({ 
  onSend, 
  onCancel,
  disabled = false, 
  placeholder = '描述你想要 Agent 做什么...',
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
  onImageAdd,
  attachments = [],
  onRemoveAttachment,
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [isComposing, setIsComposing] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`
  }, [value])
  
  const handleSend = () => {
    if ((value.trim() || attachments.length > 0) && !disabled && !isLoading) {
      onSend(value.trim())
      setValue('')
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || isComposing) {
      return
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

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
  
  return (
    <div className="relative">
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
        {runtimeStatusLabel && (
          <RunningIndicator
            label={runtimeStatusLabel}
            layout="header"
            rootDataAttr="data-chat-running"
            barDataAttr="data-chat-running-bar"
          />
        )}
        <ImagePreview
          attachments={attachments}
          onRemove={onRemoveAttachment ?? (() => {})}
        />
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

        <div className="flex flex-col gap-3 border-t border-edge-subtle px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
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
            {providerOptions.length > 0 ? (
              <>
                 <label className="flex w-full items-center gap-2 text-xs text-content-muted sm:w-auto">
                   <span className="shrink-0">供应商</span>
                   <select
                     value={selectedProviderId || ''}
                     onChange={(e) => onProviderChange?.(e.target.value || null)}
                     disabled={selectionDisabled}
                     className="min-w-0 flex-1 rounded-lg border border-edge bg-surface-primary px-2 py-1 text-xs text-content-secondary outline-none disabled:cursor-not-allowed disabled:bg-surface-secondary sm:w-40 sm:flex-none"
                   >
                    <option value="">请选择供应商</option>
                    {providerOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                 <label className="flex w-full items-center gap-2 text-xs text-content-muted sm:w-auto">
                   <span className="shrink-0">模型</span>
                   <select
                     value={selectedModelId || ''}
                     onChange={(e) => onModelChange?.(e.target.value || null)}
                     disabled={selectionDisabled || modelOptions.length === 0}
                     className="min-w-0 flex-1 rounded-lg border border-edge bg-surface-primary px-2 py-1 text-xs text-content-secondary outline-none disabled:cursor-not-allowed disabled:bg-surface-secondary sm:w-44 sm:flex-none"
                   >
                    <option value="">请选择模型</option>
                    {modelOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <span className="text-xs text-content-muted">
                请先在设置页配置供应商和模型
              </span>
            )}
            <span className="hidden text-xs text-content-muted sm:inline">
              `Enter` 发送，`Shift + Enter` 换行
            </span>
          </div>

          <div className="flex w-full items-center justify-end gap-2 sm:w-auto sm:shrink-0">
            {canCancel || isCancelling ? (
              <motion.button
                type="button"
                onClick={onCancel}
                disabled={isCancelling}
                className="flex items-center gap-2 rounded-xl bg-surface-tertiary px-3 py-2 text-sm font-medium text-content-secondary transition hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:text-content-muted"
                whileHover={isCancelling ? undefined : { scale: 1.03 }}
                whileTap={isCancelling ? undefined : { scale: 0.97 }}
              >
                {isCancelling ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                <span>{isCancelling ? '取消中' : '取消'}</span>
              </motion.button>
            ) : (
              <motion.button
                type="button"
                onClick={handleSend}
                disabled={(!value.trim() && attachments.length === 0) || disabled || isLoading}
                className="flex h-8 items-center justify-center rounded-xl bg-accent px-4 font-medium text-white shadow-lg shadow-accent/30 transition focus:ring-2 focus:ring-accent/50 outline-none disabled:cursor-not-allowed disabled:bg-surface-tertiary disabled:text-content-muted disabled:shadow-none"
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 400 }}
              >
                {isLoading ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  >
                    <Loader2 className="h-4 w-4" />
                  </motion.div>
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </motion.button>
            )}
          </div>
        </div>
        
        <motion.div
          className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-accent to-accent-hover"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: isFocused ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />
      </motion.div>
    </div>
  )
}

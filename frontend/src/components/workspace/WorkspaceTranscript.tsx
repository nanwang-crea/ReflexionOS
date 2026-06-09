import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Virtuoso, type ScrollerProps } from 'react-virtuoso'
import type { ConversationMessage, ConversationRun } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'
import type { Plan } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import type { Project } from '@/types/project'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import type { ToolApprovalActionHandler } from '@/components/workspace/ToolTraceCard'
import { AUTO_SCROLL_FOLLOW_THRESHOLD_PX } from '@/features/workspace/autoScroll'
import { useSettingsStore } from '@/stores/settingsStore'
import { ArrowDown, Loader2 } from 'lucide-react'
import { PlanProgress } from './PlanProgress'
import { RunningIndicator } from './RunningIndicator'
import {
  getAssistantReasoningText,
  getLatestAssistantMessage,
  type RuntimeStatusDescriptor,
} from './runtimeStatus'
import { buildTranscriptItems, isProcessGroupStreaming, type TranscriptItem } from './transcriptItems'
import { UserMessageItem } from './UserMessageItem'
import { AssistantMessageItem } from './AssistantMessageItem'
import { SystemNoticeItem } from './SystemNoticeItem'
import { ProcessGroupBlock } from './ProcessGroupBlock'

const VIRTUOSO_INDEX_OFFSET = 1_000_000
const MIN_TRANSCRIPT_BOTTOM_INSET_PX = 20
const TRANSCRIPT_BOTTOM_GAP_PX = 16

interface TranscriptScrollerContextValue {
  bottomPadding: number
  onUserScrollIntent: () => void
  onScrollerScroll: (event: React.UIEvent<HTMLDivElement>) => void
  loaded: boolean
  configured: boolean
  currentProject: Project | null
  currentSession: SessionSummary | null
  messagesLength: number
  isLoadingMore: boolean
  showReconnectIndicator: boolean
  reconnectLabel: string | null
  reconnectCountdownSeconds: number
  showThinkingIndicator: boolean
  runtimeStatus: RuntimeStatusDescriptor
  isRunning: boolean
  plan: Plan | null
  liveThinkingText: string
  isPlanMinimized: boolean
  onTogglePlanMinimize: () => void
}

const noop = () => {}
const TranscriptScrollerContext = React.createContext<TranscriptScrollerContextValue>({
  bottomPadding: getTranscriptBottomPadding(MIN_TRANSCRIPT_BOTTOM_INSET_PX),
  onUserScrollIntent: noop,
  onScrollerScroll: noop,
  loaded: false,
  configured: false,
  currentProject: null,
  currentSession: null,
  messagesLength: 0,
  isLoadingMore: false,
  showReconnectIndicator: false,
  reconnectLabel: null,
  reconnectCountdownSeconds: 0,
  showThinkingIndicator: false,
  runtimeStatus: { kind: 'idle', label: '' },
  isRunning: false,
  plan: null,
  liveThinkingText: '',
  isPlanMinimized: false,
  onTogglePlanMinimize: noop,
})

const TranscriptScroller = React.forwardRef<HTMLDivElement, ScrollerProps>(function TranscriptScroller(
  { style, children, ...props },
  ref
) {
  const { onUserScrollIntent, onScrollerScroll } = React.useContext(TranscriptScrollerContext)
  const domHandlers = props as React.HTMLAttributes<HTMLDivElement>

  return (
    <div
      {...props}
      ref={ref}
      onScroll={(event) => {
        domHandlers.onScroll?.(event)
        onScrollerScroll(event)
      }}
      onWheel={(event) => {
        onUserScrollIntent()
        domHandlers.onWheel?.(event)
      }}
      onTouchMove={(event) => {
        onUserScrollIntent()
        domHandlers.onTouchMove?.(event)
      }}
      onPointerDown={(event) => {
        onUserScrollIntent()
        domHandlers.onPointerDown?.(event)
      }}
      style={{
        ...style,
        overflowX: 'hidden',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      <div
        data-transcript-frame
        style={{
          maxWidth: 1280,
          marginLeft: 'auto',
          marginRight: 'auto',
          width: '100%',
          boxSizing: 'border-box',
          paddingLeft: 32,
          paddingRight: 32,
          paddingTop: 32,
        }}
      >
        {children}
      </div>
    </div>
  )
})

function TranscriptHeader() {
  const {
    loaded,
    configured,
    currentProject,
    currentSession,
    messagesLength,
    isLoadingMore,
  } = React.useContext(TranscriptScrollerContext)

  return (
    <>
      {loaded && !configured && (
        <div className="mb-4 rounded-lg border border-status-warning-border bg-status-warning-soft p-4">
          <p className="text-status-warning">请先在设置页面配置供应商、模型和默认项</p>
        </div>
      )}

      {!currentProject && (
        <div className="max-w-[720px] rounded-3xl border border-edge bg-surface-secondary px-6 py-8 text-content-muted">
          先在左侧选择一个项目，再开始新的聊天。
        </div>
      )}

      {currentProject && !currentSession && messagesLength === 0 && (
        <div className="max-w-[720px] rounded-3xl border border-edge bg-surface-secondary px-6 py-8 text-content-muted">
          这个项目下还没有聊天。可以直接在下方输入，或者从左侧点击"新建聊天"。
        </div>
      )}

      {isLoadingMore && (
        <div className="py-4 text-center text-sm text-content-muted">加载更多消息...</div>
      )}
    </>
  )
}

function TranscriptFooter() {
  const {
    bottomPadding,
    showReconnectIndicator,
    reconnectLabel,
    reconnectCountdownSeconds,
    showThinkingIndicator,
    runtimeStatus,
    isRunning,
    plan,
    liveThinkingText,
    isPlanMinimized,
    onTogglePlanMinimize,
  } = React.useContext(TranscriptScrollerContext)

  return (
    <>
      {showReconnectIndicator && (
        <div className="mb-8 flex items-center gap-3 text-sm text-status-warning" aria-live="polite">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-status-warning" />
          <span>{reconnectLabel} · {reconnectCountdownSeconds} 秒后重试</span>
        </div>
      )}

      {showThinkingIndicator && (
        <RunningIndicator
          label={runtimeStatus.label || '等待模型响应'}
          rootDataAttr="data-running-bars"
          barDataAttr="data-running-bar"
        />
      )}

      {!showReconnectIndicator && !showThinkingIndicator && isRunning && !plan && runtimeStatus.kind !== 'idle' && !liveThinkingText && (
        <RunningIndicator
          label={runtimeStatus.label}
          rootDataAttr="data-running-bars"
          barDataAttr="data-running-bar"
        />
      )}

      <AnimatePresence>
        {plan && (
          <PlanProgress
            plan={plan}
            isMinimized={isPlanMinimized}
            onToggleMinimize={onTogglePlanMinimize}
          />
        )}
      </AnimatePresence>
      <div
        data-transcript-bottom-spacer
        aria-hidden="true"
        style={{ height: bottomPadding }}
      />
    </>
  )
}

const VIRTUOSO_COMPONENTS = {
  Scroller: TranscriptScroller,
  Header: TranscriptHeader,
  Footer: TranscriptFooter,
}

interface VirtualListIndexSnapshot {
  sessionId: string | null
  firstItemId: string | null
  lastItemId: string | null
  itemCount: number
  firstItemIndex: number
}

export function getNextFirstItemIndex(
  previous: VirtualListIndexSnapshot | null,
  next: Omit<VirtualListIndexSnapshot, 'firstItemIndex'>
) {
  if (!previous || previous.sessionId !== next.sessionId || next.itemCount === 0) {
    return Math.max(1, VIRTUOSO_INDEX_OFFSET - next.itemCount)
  }

  const addedItemCount = next.itemCount - previous.itemCount
  const prependedItems = (
    addedItemCount > 0 &&
    previous.lastItemId === next.lastItemId &&
    previous.firstItemId !== next.firstItemId
  )

  if (prependedItems) {
    return Math.max(1, previous.firstItemIndex - addedItemCount)
  }

  return previous.firstItemIndex
}

export function getRetryCountdownSeconds(delay: number, elapsedMs = 0) {
  const delaySeconds = Number.isFinite(delay) ? Math.max(0, Math.ceil(delay)) : 0
  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000))
  return Math.max(0, delaySeconds - elapsedSeconds)
}

export function getTranscriptBottomPadding(bottomInset: number) {
  return Math.max(MIN_TRANSCRIPT_BOTTOM_INSET_PX, bottomInset) + TRANSCRIPT_BOTTOM_GAP_PX
}

export function shouldMarkUserScrolledAway(position: {
  userScrollIntent: boolean
  distanceFromBottom: number
}) {
  if (position.distanceFromBottom <= AUTO_SCROLL_FOLLOW_THRESHOLD_PX) {
    return false
  }
  return position.userScrollIntent
}

export function shouldForceBottomOnNewUserMessage(wasUserScrolledAway: boolean) {
  return wasUserScrolledAway
}

export function shouldForceBottomAfterUserAppend(position: {
  previousLastUserMessageId: string | null
  nextLastUserMessageId: string | null
  wasUserScrolledAway: boolean
}) {
  return Boolean(
    position.wasUserScrolledAway &&
    position.nextLastUserMessageId &&
    position.nextLastUserMessageId !== position.previousLastUserMessageId
  )
}

interface WorkspaceTranscriptProps {
  loaded: boolean
  configured: boolean
  currentProject: Project | null
  currentSession: SessionSummary | null
  messages: ConversationMessage[]
  isRunning?: boolean
  retryInfo?: LlmRetryDto | null
  plan?: Plan | null
  runtimeStatus?: RuntimeStatusDescriptor
  isPlanMinimized?: boolean
  onTogglePlanMinimize?: () => void
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: (detail: ActionReceiptDetail) => void
  runsById?: Record<string, ConversationRun>
  onEditMessage?: (messageId: string, contentText: string) => void
  onRegenerateMessage?: (messageId: string) => void
  hasMore?: boolean
  isLoadingMore?: boolean
  oldestLoadedTurnId?: string | null
  onLoadMore?: (beforeTurnId: string) => void
  bottomInset?: number
}

export function WorkspaceTranscript({
  loaded,
  configured,
  currentProject,
  currentSession,
  messages,
  isRunning = false,
  retryInfo = null,
  plan = null,
  runtimeStatus = { kind: 'idle', label: '' },
  isPlanMinimized = false,
  onTogglePlanMinimize,
  onApprovalAction,
  onDetailClick,
  runsById,
  onEditMessage,
  onRegenerateMessage,
  hasMore = false,
  isLoadingMore = false,
  oldestLoadedTurnId = null,
  onLoadMore,
  bottomInset = MIN_TRANSCRIPT_BOTTOM_INSET_PX,
}: WorkspaceTranscriptProps) {
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [isAtBottom, setIsAtBottom] = useState(false)
  const virtuosoRef = useRef<import('react-virtuoso').VirtuosoHandle>(null)
  const virtualListIndexSnapshotRef = useRef<VirtualListIndexSnapshot | null>(null)
  const isAtBottomRef = useRef(false)
  const userScrolledAwayRef = useRef(false)
  const userScrollIntentRef = useRef(false)
  const hasSeenStartReachedRef = useRef(false)
  const showContinuationNotices = useSettingsStore((s) => s.showContinuationNotices)
  const showProcessExpanded = useSettingsStore((s) => s.showProcessExpanded)
  const autoCollapseProcess = useSettingsStore((s) => s.autoCollapseProcess)
  const transcriptBottomPadding = getTranscriptBottomPadding(bottomInset)

  const filteredMessages = useMemo(() => {
    if (showContinuationNotices) return messages
    return messages.filter((message) => {
      if (message.messageType === 'system_notice') {
        const kind = message.payloadJson?.kind
        if (kind === 'continuation_artifact') return false
      }
      return true
    })
  }, [messages, showContinuationNotices])

  const transcriptItems = useMemo(() => buildTranscriptItems(filteredMessages), [filteredMessages])

  const hasVisibleStreamingMessage = filteredMessages.some((message) => {
    if (message.messageType === 'assistant_message' && message.streamState === 'streaming') {
      return true
    }
    if (message.messageType === 'tool_trace' && (message.streamState === 'streaming' || message.streamState === 'idle')) {
      return true
    }
    return false
  })

  const [reconnectCountdownSeconds, setReconnectCountdownSeconds] = useState(() => (
    getRetryCountdownSeconds(retryInfo?.delay ?? 0)
  ))
  const hasRetryInfo = retryInfo !== null
  const retryAttempt = retryInfo?.attempt ?? null
  const retryDelay = retryInfo?.delay ?? 0
  const retryMaxRetries = retryInfo?.max_retries ?? null
  const reconnectLabel = hasRetryInfo ? `reconnect（${retryAttempt}/${retryMaxRetries}）` : null
  const showReconnectIndicator = isRunning && reconnectLabel !== null

  const latestAssistantMessage = useMemo(
    () => getLatestAssistantMessage(filteredMessages),
    [filteredMessages]
  )
  const liveThinkingText = latestAssistantMessage ? getAssistantReasoningText(latestAssistantMessage) : ''
  const showThinkingIndicator = (
    isRunning &&
    !showReconnectIndicator &&
    !plan &&
    !liveThinkingText &&
    !hasVisibleStreamingMessage
  )

  useEffect(() => {
    if (!hasRetryInfo || !isRunning) {
      setReconnectCountdownSeconds(0)
      return
    }

    setReconnectCountdownSeconds(getRetryCountdownSeconds(retryDelay))
    const intervalId = window.setInterval(() => {
      setReconnectCountdownSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)

    return () => window.clearInterval(intervalId)
  }, [hasRetryInfo, isRunning, retryAttempt, retryDelay, retryMaxRetries])

  const handleStartReached = useCallback(() => {
    if (!hasSeenStartReachedRef.current) {
      hasSeenStartReachedRef.current = true
      return
    }
    if (hasMore && oldestLoadedTurnId && !isLoadingMore) {
      onLoadMore?.(oldestLoadedTurnId)
    }
  }, [hasMore, oldestLoadedTurnId, isLoadingMore, onLoadMore])

  const handleEditStart = useCallback((messageId: string, contentText: string) => {
    setEditingMessageId(messageId)
    setEditContent(contentText)
  }, [])

  const handleEditSubmit = useCallback(() => {
    if (editContent.trim() && editingMessageId) {
      onEditMessage?.(editingMessageId, editContent.trim())
      setEditingMessageId(null)
    }
  }, [editContent, editingMessageId, onEditMessage])

  const handleEditCancel = useCallback(() => {
    setEditingMessageId(null)
  }, [])

  const followOutput = useCallback((_atBottom: boolean) => {
    if (userScrolledAwayRef.current) return false
    return true
  }, [])

  const markUserScrollIntent = useCallback(() => {
    userScrollIntentRef.current = true
  }, [])

  const handleScrollerScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget
    const distanceFromBottom = Math.max(
      0,
      target.scrollHeight - (target.scrollTop + target.clientHeight)
    )

    if (distanceFromBottom <= AUTO_SCROLL_FOLLOW_THRESHOLD_PX) {
      userScrolledAwayRef.current = false
      userScrollIntentRef.current = false
      return
    }

    if (shouldMarkUserScrolledAway({
      userScrollIntent: userScrollIntentRef.current,
      distanceFromBottom,
    })) {
      userScrolledAwayRef.current = true
    }
  }, [])

  const firstItemId = transcriptItems[0]?.id ?? null
  const lastItemId = transcriptItems[transcriptItems.length - 1]?.id ?? null
  const firstItemIndex = getNextFirstItemIndex(virtualListIndexSnapshotRef.current, {
    sessionId: currentSession?.id ?? null,
    firstItemId,
    lastItemId,
    itemCount: transcriptItems.length,
  })
  virtualListIndexSnapshotRef.current = {
    sessionId: currentSession?.id ?? null,
    firstItemId,
    lastItemId,
    itemCount: transcriptItems.length,
    firstItemIndex,
  }
  const lastItemIndex = firstItemIndex + Math.max(0, transcriptItems.length - 1)
  const initialTopMostItemIndexRef = useRef<{
    sessionId: string | null
    index: number
  } | null>(null)
  const sessionId = currentSession?.id ?? null
  if (initialTopMostItemIndexRef.current?.sessionId !== sessionId) {
    initialTopMostItemIndexRef.current = {
      sessionId,
      index: lastItemIndex,
    }
  }

  const scrollToTranscriptBottom = useCallback((behavior: 'auto' | 'smooth' = 'auto') => {
    virtuosoRef.current?.scrollToIndex({
      index: 'LAST',
      align: 'end',
      behavior,
    })
  }, [])

  const prevLastUserMessageIdRef = useRef<string | null>(null)
  useEffect(() => {
    const lastMessage = filteredMessages[filteredMessages.length - 1]
    const lastUserMsgId = lastMessage?.messageType === 'user_message' ? lastMessage.id : null
    if (lastUserMsgId) {
      const wasUserScrolledAway = userScrolledAwayRef.current
      userScrolledAwayRef.current = false
      userScrollIntentRef.current = false
      if (shouldForceBottomAfterUserAppend({
        previousLastUserMessageId: prevLastUserMessageIdRef.current,
        nextLastUserMessageId: lastUserMsgId,
        wasUserScrolledAway,
      })) {
        scrollToTranscriptBottom('auto')
      }
    }
    prevLastUserMessageIdRef.current = lastUserMsgId
  }, [filteredMessages, scrollToTranscriptBottom])

  const computeItemKey = useCallback((_: number, item: TranscriptItem) => item.id, [])

  const handleAtBottomStateChange = useCallback((atBottom: boolean) => {
    isAtBottomRef.current = atBottom
    setIsAtBottom(atBottom)
    if (atBottom) {
      userScrolledAwayRef.current = false
      userScrollIntentRef.current = false
    }
  }, [])

  const scrollToBottom = useCallback(() => {
    userScrolledAwayRef.current = false
    userScrollIntentRef.current = false
    scrollToTranscriptBottom('smooth')
  }, [scrollToTranscriptBottom])

  const itemContent = useCallback((index: number, item: TranscriptItem) => {
    const isLastItem = index === transcriptItems.length - 1

    if (item.kind === 'process_group') {
      const isStreaming = isProcessGroupStreaming(item.subItems)
      const shouldAnimateEntry = isLastItem && !isStreaming
      return (
        <div className={shouldAnimateEntry ? 'transcript-item-enter' : ''}>
          <ProcessGroupBlock
            runId={item.runId}
            subItems={item.subItems}
            isStreaming={isStreaming}
            isRunActive={isRunning}
            defaultExpanded={showProcessExpanded}
            autoCollapse={autoCollapseProcess}
            onApprovalAction={onApprovalAction}
            onDetailClick={onDetailClick}
          />
        </div>
      )
    }

    if (item.kind === 'answer_message') {
      const { message } = item
      const isLiveItem = message.streamState === 'streaming' || message.streamState === 'idle'
      const shouldAnimateEntry = isLastItem && !isLiveItem
      return (
        <div className={shouldAnimateEntry ? 'transcript-item-enter' : ''}>
          <AssistantMessageItem
            messageId={message.id}
            contentText={message.contentText}
            streamState={message.streamState}
            displayMode={message.displayMode}
            payloadJson={message.payloadJson}
            runId={message.runId}
            runsById={runsById}
            onEdit={onEditMessage ?? (() => {})}
            onRegenerate={onRegenerateMessage ?? (() => {})}
            onDetailClick={onDetailClick}
          />
        </div>
      )
    }

    if (item.kind === 'message') {
      const { message } = item
      const isLiveItem = message.streamState === 'streaming' || message.streamState === 'idle'
      const shouldAnimateEntry = isLastItem && !isLiveItem

      if (message.messageType === 'user_message') {
        const isEditing = editingMessageId === message.id
        return (
          <div className={shouldAnimateEntry ? 'transcript-item-enter' : ''}>
            <UserMessageItem
              messageId={message.id}
              contentText={message.contentText}
              isEditing={isEditing}
              editContent={editContent}
              onEdit={handleEditStart}
              onEditContentChange={setEditContent}
              onEditCancel={handleEditCancel}
              onEditSubmit={handleEditSubmit}
              showActions={!!onEditMessage}
            />
          </div>
        )
      }

      if (message.messageType === 'system_notice') {
        return (
          <div className={shouldAnimateEntry ? 'transcript-item-enter' : ''}>
            <SystemNoticeItem contentText={message.contentText} />
          </div>
        )
      }

      if (message.messageType === 'tool_trace') return null

      if (message.messageType === 'assistant_message') return null
    }

    return null
  }, [editingMessageId, editContent, onApprovalAction, onDetailClick, onEditMessage, onRegenerateMessage, runsById, handleEditStart, handleEditCancel, handleEditSubmit, transcriptItems.length, showProcessExpanded, autoCollapseProcess, isRunning])

  const scrollerContextValue = useMemo(() => ({
    bottomPadding: transcriptBottomPadding,
    onUserScrollIntent: markUserScrollIntent,
    onScrollerScroll: handleScrollerScroll,
    loaded,
    configured,
    currentProject,
    currentSession,
    messagesLength: messages.length,
    isLoadingMore,
    showReconnectIndicator,
    reconnectLabel,
    reconnectCountdownSeconds,
    showThinkingIndicator,
    runtimeStatus,
    isRunning,
    plan,
    liveThinkingText,
    isPlanMinimized,
    onTogglePlanMinimize: onTogglePlanMinimize ?? noop,
  }), [
    transcriptBottomPadding,
    markUserScrollIntent,
    handleScrollerScroll,
    loaded,
    configured,
    currentProject,
    currentSession,
    messages.length,
    isLoadingMore,
    showReconnectIndicator,
    reconnectLabel,
    reconnectCountdownSeconds,
    showThinkingIndicator,
    runtimeStatus,
    isRunning,
    plan,
    liveThinkingText,
    isPlanMinimized,
    onTogglePlanMinimize,
  ])

  return (
    <TranscriptScrollerContext.Provider value={scrollerContextValue}>
      <div className="relative flex-1 overflow-hidden bg-surface-primary">
        <Virtuoso
          ref={virtuosoRef}
          data={transcriptItems}
          itemContent={itemContent}
          computeItemKey={computeItemKey}
          firstItemIndex={firstItemIndex}
          alignToBottom
          atBottomThreshold={AUTO_SCROLL_FOLLOW_THRESHOLD_PX}
          followOutput={followOutput}
          initialTopMostItemIndex={initialTopMostItemIndexRef.current.index}
          startReached={handleStartReached}
          atBottomStateChange={handleAtBottomStateChange}
          components={VIRTUOSO_COMPONENTS}
        />
        <AnimatePresence>
          {!isAtBottom && (
            <div className="pointer-events-none absolute bottom-4 left-0 right-0 z-20 flex justify-center">
              <motion.button
                type="button"
                aria-label="滚动到底部"
                title="滚动到底部"
                onClick={scrollToBottom}
                initial={{ opacity: 0, y: 10, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.96 }}
                transition={{ duration: 0.18 }}
                className="pointer-events-auto grid h-11 w-11 place-items-center rounded-full border border-edge bg-surface-primary text-content-secondary shadow-theme transition-colors hover:border-edge hover:text-content-primary"
              >
                <ArrowDown className="h-5 w-5" />
              </motion.button>
            </div>
          )}
        </AnimatePresence>
      </div>
    </TranscriptScrollerContext.Provider>
  )
}

export { getAssistantReasoningText } from './runtimeStatus'

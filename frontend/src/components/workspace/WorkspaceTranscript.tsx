/**
 * 文件功能：工作区对话记录虚拟列表
 * 文件描述：基于 react-virtuoso 实现的对话记录虚拟滚动列表，渲染用户消息、助手消息、系统提示、
 *          过程分组（思考/工具调用）等条目，并处理自动跟随滚动、分页加载更多、重连倒计时、
 *          计划进度展示等交互逻辑
 * 核心逻辑：
 *   1. 通过 buildTranscriptItems 将原始消息数组转换为虚拟列表可渲染的条目（TranscriptItem）
 *   2. 用户主动向上滚动后标记 userScrolledAway，暂停自动跟底；新用户消息发出或用户重新回到底部时恢复跟随
 *   3. Virtuoso 的 Header/Footer/Scroller 通过 Context 注入公共状态，避免为每个条目单独传递大量 props
 *   4. firstItemIndex 采用一个较大的固定偏移量（VIRTUOSO_INDEX_OFFSET）以配合 Virtuoso 的双向无限加载
 */
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
import { useSettingsStore } from '@/features/settings/stores/settings.store'
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

/**
 * 组件名：TranscriptScroller
 * 入参（props，ScrollerProps，由 Virtuoso 内部传入）：
 *   - style、children、...props: Virtuoso 要求的滚动容器标准 props
 * 作用/渲染逻辑：Virtuoso 自定义 Scroller 组件，包裹一层固定最大宽度的内容容器实现居中排版；
 *          转发 onScroll 事件用于更新滚动位置状态，转发 onWheel/onTouchMove/onPointerDown
 *          用于标记“用户主动滚动意图”（区分程序自动滚动与用户手动滚动）
 * 返回值：JSX.Element - 滚动容器（forwardRef 转发 DOM ref 给 Virtuoso）
 */
const TranscriptScroller = React.forwardRef<HTMLDivElement, ScrollerProps>(function TranscriptScroller(
  { style, children, ...props },
  ref
) {
  const { onUserScrollIntent, onScrollerScroll } = React.useContext(TranscriptScrollerContext)

  return (
    <div
      {...props}
      ref={ref}
      onScroll={(event) => {
        if ('onScroll' in props && typeof props.onScroll === 'function') {
          props.onScroll(event)
        }
        onScrollerScroll(event)
      }}
      onWheel={(event) => {
        onUserScrollIntent()
        if ('onWheel' in props && typeof props.onWheel === 'function') {
          props.onWheel(event)
        }
      }}
      onTouchMove={(event) => {
        onUserScrollIntent()
        if ('onTouchMove' in props && typeof props.onTouchMove === 'function') {
          props.onTouchMove(event)
        }
      }}
      onPointerDown={(event) => {
        onUserScrollIntent()
        if ('onPointerDown' in props && typeof props.onPointerDown === 'function') {
          props.onPointerDown(event)
        }
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

/**
 * 组件名：TranscriptHeader
 * 入参：无（通过 TranscriptScrollerContext 读取 loaded/configured/currentProject/currentSession/messagesLength/isLoadingMore）
 * 作用/渲染逻辑：Virtuoso 列表头部，依次展示：未配置供应商提示、未选择项目提示、空会话提示、加载更多指示器
 * 返回值：JSX.Element - 列表头部提示区
 */
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

/**
 * 组件名：TranscriptFooter
 * 入参：无（通过 TranscriptScrollerContext 读取重连状态、运行状态、计划进度等）
 * 作用/渲染逻辑：Virtuoso 列表尾部，依次展示：重连倒计时提示、等待模型响应指示器、
 *          运行中通用指示器（无计划/无思考文本时）、计划进度条（PlanProgress）、底部占位间距
 * 返回值：JSX.Element - 列表尾部状态区
 */
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

/**
 * 函数名：getNextFirstItemIndex
 * 入参：
 *   - previous (VirtualListIndexSnapshot | null): 上一次渲染时记录的虚拟列表索引快照
 *   - next (Omit<VirtualListIndexSnapshot, 'firstItemIndex'>): 本次渲染的会话/条目信息（不含索引）
 * 功能：计算 Virtuoso 所需的 firstItemIndex，支撑“向上加载更多历史消息”时列表不跳动
 * 运行逻辑：
 *   1. 无历史快照，或切换了会话，或条目数为 0：重置为固定偏移量减去条目数（保证末尾对齐）
 *   2. 若尾部条目不变但头部条目变化且条目数增加：判定为“向上追加了历史消息”，索引相应前移
 *   3. 其余情况维持上一次的 firstItemIndex 不变
 * 出参：number - 供 Virtuoso 使用的 firstItemIndex
 */
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

/**
 * 函数名：getRetryCountdownSeconds
 * 入参：
 *   - delay (number): 本次重试的延迟时间（秒）
 *   - elapsedMs (number，默认 0): 自重试开始已经过的时间（毫秒）
 * 功能：计算重连倒计时剩余秒数，用于展示“N 秒后重试”
 * 运行逻辑：对 delay 取整并下限为 0，减去已经过的整秒数，结果不小于 0
 * 出参：number - 剩余倒计时秒数
 */
export function getRetryCountdownSeconds(delay: number, elapsedMs = 0) {
  const delaySeconds = Number.isFinite(delay) ? Math.max(0, Math.ceil(delay)) : 0
  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000))
  return Math.max(0, delaySeconds - elapsedSeconds)
}

/**
 * 函数名：getTranscriptBottomPadding
 * 入参：
 *   - bottomInset (number): 外部传入的底部安全区高度（如输入框高度）
 * 功能：计算列表底部占位间距，保证内容不被底部固定元素遮挡
 * 运行逻辑：取 bottomInset 与最小底部安全区的较大值，再加上固定的底部间隙
 * 出参：number - 底部占位高度（像素）
 */
export function getTranscriptBottomPadding(bottomInset: number) {
  return Math.max(MIN_TRANSCRIPT_BOTTOM_INSET_PX, bottomInset) + TRANSCRIPT_BOTTOM_GAP_PX
}

/**
 * 函数名：shouldMarkUserScrolledAway
 * 入参：
 *   - position ({ userScrollIntent, distanceFromBottom }): 用户是否有主动滚动意图、距底部的距离
 * 功能：判断是否应将当前状态标记为“用户已主动滚离底部”（从而暂停自动跟随滚动）
 * 运行逻辑：若距离底部小于等于自动跟随阈值，视为仍在底部，不标记；否则按是否存在主动滚动意图决定
 * 出参：boolean - 是否应标记为用户已滚离底部
 */
export function shouldMarkUserScrolledAway(position: {
  userScrollIntent: boolean
  distanceFromBottom: number
}) {
  if (position.distanceFromBottom <= AUTO_SCROLL_FOLLOW_THRESHOLD_PX) {
    return false
  }
  return position.userScrollIntent
}

/**
 * 函数名：shouldForceBottomOnNewUserMessage
 * 入参：
 *   - wasUserScrolledAway (boolean): 发送新消息前用户是否已滚离底部
 * 功能：判断用户发出新消息时是否应强制滚动回底部
 * 运行逻辑：直接返回入参值（滚离状态即代表需要强制回底）
 * 出参：boolean - 是否强制滚动到底部
 */
export function shouldForceBottomOnNewUserMessage(wasUserScrolledAway: boolean) {
  return wasUserScrolledAway
}

/**
 * 函数名：shouldForceBottomAfterUserAppend
 * 入参：
 *   - position ({ previousLastUserMessageId, nextLastUserMessageId, wasUserScrolledAway }):
 *     追加前/后最后一条用户消息 ID，以及追加前用户是否已滚离底部
 * 功能：判断在消息列表末尾追加了新的用户消息后，是否应强制滚动到底部
 * 运行逻辑：仅当此前用户已滚离底部，且确实出现了新的、与之前不同的最后一条用户消息 ID 时才强制回底
 * 出参：boolean - 是否强制滚动到底部
 */
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
  onRegenerateMessage?: (messageId: string) => void | Promise<void>
  hasMore?: boolean
  isLoadingMore?: boolean
  oldestLoadedTurnId?: string | null
  onLoadMore?: (beforeTurnId: string) => void
  bottomInset?: number
}

/**
 * 组件名：WorkspaceTranscript
 * 入参（props，WorkspaceTranscriptProps，节选关键项）：
 *   - loaded/configured (boolean): 设置是否已加载/是否已配置供应商模型
 *   - currentProject/currentSession: 当前项目与会话信息
 *   - messages (ConversationMessage[]): 完整会话消息数组
 *   - isRunning (boolean，默认 false): 当前 run 是否在执行中
 *   - retryInfo (LlmRetryDto | null): WebSocket 重连/重试信息
 *   - plan (Plan | null): 当前计划进度信息
 *   - runtimeStatus (RuntimeStatusDescriptor): 运行状态描述（用于底部指示器文案）
 *   - isPlanMinimized/onTogglePlanMinimize: 计划面板最小化状态与切换回调
 *   - onApprovalAction/onDetailClick: 审批操作与详情点击回调，转发给过程分组/工具卡片
 *   - runsById: run 信息映射表，转发给助手消息用于错误回退展示
 *   - onEditMessage/onRegenerateMessage: 编辑/重新生成消息回调
 *   - hasMore/isLoadingMore/oldestLoadedTurnId/onLoadMore: 历史消息分页加载相关状态与回调
 *   - bottomInset (number): 底部安全区高度（用于计算底部占位）
 * 作用/渲染逻辑：
 *   1. 用 buildTranscriptItems 将消息数组转换为虚拟列表条目，并按条目 kind（process_group/answer_message/message）
 *      分别渲染 ProcessGroupBlock、AssistantMessageItem、UserMessageItem、SystemNoticeItem
 *   2. 维护滚动跟随逻辑：记录用户是否主动滚离底部、是否有滚动意图，决定新消息到达时是否自动滚到底部
 *   3. 维护 Virtuoso 所需的 firstItemIndex/initialTopMostItemIndex，支持向上分页加载历史消息且不跳动
 *   4. 通过 Context 向 Header/Footer/Scroller 注入公共状态，避免逐条目传递大量 props
 *   5. 未处于底部时展示悬浮的“滚动到底部”按钮
 * 返回值：JSX.Element - 对话记录虚拟列表（含头部/尾部/滚动到底部按钮）
 */
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
  const showProcessExpanded = useSettingsStore((s) => s.showProcessExpanded)
  const autoCollapseProcess = useSettingsStore((s) => s.autoCollapseProcess)
  const transcriptBottomPadding = getTranscriptBottomPadding(bottomInset)

  const transcriptItems = useMemo(() => buildTranscriptItems(messages), [messages])

  const hasVisibleStreamingMessage = messages.some((message) => {
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
    () => getLatestAssistantMessage(messages),
    [messages]
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
    const lastMessage = messages[messages.length - 1]
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
  }, [messages, scrollToTranscriptBottom])

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
              attachments={message.attachments}
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

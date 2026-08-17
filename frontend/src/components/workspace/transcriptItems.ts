/**
 * 文件功能：会话消息转录条目构建工具
 * 文件描述：将扁平的会话消息列表（ConversationMessage[]）按运行（run）和时间聚合成用于渲染的转录条目结构
 *          （用户消息、系统提示、思考过程、工作笔记、工具调用组、回答消息等）
 * 核心逻辑：顺序遍历消息，按 runId 分组为 process_group（过程分组），组内再将连续的工具调用聚合为 tool_group；
 *          用户消息/系统提示/回答消息会触发当前分组的 flush（结算输出），保证时间顺序与分组边界正确
 */
import { buildApprovalDetailFromPayload, buildReceiptDetail } from '@/components/execution/receiptUtils'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ConversationMessage } from '@/types/conversation'
import { getAssistantReasoningText } from './runtimeStatus'

const TOOL_GROUP_GAP_MS = 90_000

export type TranscriptItem =
  | { kind: 'message'; id: string; message: ConversationMessage }
  | { kind: 'process_group'; id: string; runId: string; subItems: ProcessSubItem[] }
  | { kind: 'answer_message'; id: string; message: ConversationMessage }

export type ProcessSubItem =
  | { kind: 'thinking'; id: string; text: string; streamState: ConversationMessage['streamState'] }
  | { kind: 'working_note'; id: string; text: string; streamState: ConversationMessage['streamState'] }
  | { kind: 'tool_group'; id: string; messages: ConversationMessage[]; details: ActionReceiptDetail[]; status: ActionReceiptStatus }

/**
 * 函数名：getMessageTime
 * 入参：
 *   - message (ConversationMessage): 会话消息
 * 功能：解析消息的时间戳（优先创建时间，退化到更新时间）
 * 运行逻辑：调用 Date.parse 解析 createdAt 或 updatedAt，解析失败（NaN）时返回 null
 * 出参：number | null - 毫秒时间戳，解析失败为 null
 */
function getMessageTime(message: ConversationMessage) {
  const timestamp = Date.parse(message.createdAt || message.updatedAt)
  return Number.isFinite(timestamp) ? timestamp : null
}

/**
 * 函数名：isApprovalDecisionStatus
 * 入参：
 *   - status (unknown): 消息 payload 中的状态字段
 * 功能：判断状态是否为审批决策结果（已批准/已拒绝）
 * 运行逻辑：直接比较是否等于 'approved' 或 'denied'
 * 出参：boolean - 是否为审批决策状态
 */
function isApprovalDecisionStatus(status: unknown) {
  return status === 'approved' || status === 'denied'
}

/**
 * 函数名：getToolTraceStatus
 * 入参：
 *   - message (ConversationMessage): 类型为 tool_trace 的消息
 * 功能：推断单条工具调用消息对应的回执详情状态
 * 运行逻辑：
 *   1. payload.status 为 waiting_for_approval 直接映射为等待审批
 *   2. payload.status 为 approved 映射为成功，denied 映射为取消
 *   3. streamState 为 failed/cancelled 分别映射为失败/取消
 *   4. streamState 为 streaming/idle 映射为运行中
 *   5. 其余情况默认视为成功
 * 出参：ActionReceiptDetail['status'] - 推断出的详情状态
 */
function getToolTraceStatus(message: ConversationMessage): ActionReceiptDetail['status'] {
  if (message.payloadJson.status === 'waiting_for_approval') return 'waiting_for_approval'
  if (message.payloadJson.status === 'approved') return 'success'
  if (message.payloadJson.status === 'denied') return 'cancelled'
  if (message.streamState === 'failed') return 'failed'
  if (message.streamState === 'cancelled') return 'cancelled'
  if (message.streamState === 'streaming' || message.streamState === 'idle') return 'running'
  return 'success'
}

/**
 * 函数名：getToolGroupStatus
 * 入参：
 *   - messages (ConversationMessage[]): 一个工具调用组内的所有消息
 * 功能：综合组内所有消息的状态，推断出整组的回执状态
 * 运行逻辑：
 *   1. 存在等待审批的消息，整组视为等待审批
 *   2. 统计失败消息数量：全部失败视为 failed，部分失败视为 partial_failed
 *   3. 存在已取消或已拒绝的消息，整组视为 cancelled
 *   4. 存在非审批决策且仍在 streaming/idle 的消息，整组视为 running
 *   5. 其余情况视为 completed
 * 出参：ActionReceiptStatus - 推断出的整组状态
 */
function getToolGroupStatus(messages: ConversationMessage[]): ActionReceiptStatus {
  if (messages.some((m) => m.payloadJson.status === 'waiting_for_approval')) return 'waiting_for_approval'
  const failedCount = messages.filter((m) => m.streamState === 'failed').length
  if (failedCount > 0) return failedCount === messages.length ? 'failed' : 'partial_failed'
  if (messages.some((m) => m.streamState === 'cancelled')) return 'cancelled'
  if (messages.some((m) => m.payloadJson.status === 'denied')) return 'cancelled'
  if (messages.some((m) => !isApprovalDecisionStatus(m.payloadJson.status) && (m.streamState === 'streaming' || m.streamState === 'idle'))) return 'running'
  return 'completed'
}

/**
 * 函数名：isRecord
 * 入参：
 *   - v (unknown): 待判断的任意值
 * 功能：判断值是否为普通对象（非 null、非数组）
 * 运行逻辑：typeof 校验为 object 且不为 null 且不是数组即视为普通对象
 * 出参：boolean（类型谓词）- 是否为 Record<string, unknown>
 */
function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/**
 * 函数名：buildToolTraceDetail
 * 入参：
 *   - message (ConversationMessage): 类型为 tool_trace 的消息
 * 功能：将单条工具调用消息转换为可展示的回执详情（ActionReceiptDetail）
 * 运行逻辑：
 *   1. 从 payload 中取出工具名与参数，调用 buildReceiptDetail 生成基础详情，再覆盖为实际状态
 *   2. 若状态为等待审批且具备 runId 与 approval_id，解析出审批上下文并挂载到 detail.approval/data
 *   3. 提取输出（字符串或 JSON 序列化）、错误信息、耗时等字段
 *   4. 将 tool_call_id 与 session_id 写入 data 字段，供 delegate 等工具关联子代理事件使用
 * 出参：ActionReceiptDetail - 构建好的回执详情对象
 */
export function buildToolTraceDetail(message: ConversationMessage): ActionReceiptDetail {
  const payload = message.payloadJson
  const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : 'tool'
  const args = isRecord(payload.arguments) ? payload.arguments : undefined
  const detail = buildReceiptDetail(message.id, toolName, args)
  detail.status = getToolTraceStatus(message)

  if (detail.status === 'waiting_for_approval' && typeof message.runId === 'string' && typeof payload.approval_id === 'string') {
    const approvalDetail = buildApprovalDetailFromPayload({
      ...payload,
      run_id: message.runId,
    })
    if (approvalDetail?.approval) {
      detail.approval = approvalDetail.approval
      detail.data = { ...detail.data, ...approvalDetail.data }
    }
  }

  if (typeof payload.output === 'string') { detail.output = payload.output }
  else if (payload.output !== undefined) { try { detail.output = JSON.stringify(payload.output, null, 2) } catch { detail.output = String(payload.output) } }

  if (typeof payload.error === 'string') { detail.error = payload.error }
  else if (typeof payload.error_message === 'string') { detail.error = payload.error_message }

  if (typeof payload.duration === 'number' && Number.isFinite(payload.duration)) { detail.duration = payload.duration }

  // 将 tool_call_id 存入 data 字段，delegate 等工具需要它来关联 sub_agent 事件
  // detail.id 是 message.id，而 sub_agent store 以 tool_call_id 为 key，两者不同
  if (typeof payload.tool_call_id === 'string') {
    detail.data = { ...detail.data, tool_call_id: payload.tool_call_id }
  }
  detail.data = { ...detail.data, session_id: message.sessionId }

  return detail
}

/**
 * 函数名：shouldAppendToToolGroup
 * 入参：
 *   - groupMessages (ConversationMessage[]): 当前工具调用组已缓冲的消息
 *   - message (ConversationMessage): 待判断是否可并入该组的新消息
 * 功能：判断新消息是否应并入当前工具调用组，还是需要另起一组
 * 运行逻辑：
 *   1. 组内为空则直接允许并入
 *   2. turnId 或 runId 与组内最后一条不一致则不允许并入
 *   3. 时间戳缺失时默认允许并入；否则要求时间间隔不超过 TOOL_GROUP_GAP_MS
 * 出参：boolean - 是否应并入当前组
 */
function shouldAppendToToolGroup(groupMessages: ConversationMessage[], message: ConversationMessage) {
  const previous = groupMessages[groupMessages.length - 1]
  if (!previous) return true
  if (previous.turnId !== message.turnId || previous.runId !== message.runId) return false
  const previousTime = getMessageTime(previous)
  const nextTime = getMessageTime(message)
  if (previousTime === null || nextTime === null) return true
  return nextTime - previousTime <= TOOL_GROUP_GAP_MS
}

/**
 * 函数名：isProcessGroupStreaming
 * 入参：
 *   - subItems (ProcessSubItem[]): 某个过程分组内的子条目列表
 * 功能：判断该过程分组是否仍在流式输出/运行中，用于 UI 展示加载态
 * 运行逻辑：遍历子条目，thinking/working_note 类型检查 streamState 是否为 streaming/idle，
 *          tool_group 类型检查 status 是否为 running/waiting_for_approval，命中任一即返回 true
 * 出参：boolean - 该分组是否仍在进行中
 */
export function isProcessGroupStreaming(subItems: ProcessSubItem[]): boolean {
  return subItems.some((item) => {
    if (item.kind === 'thinking' || item.kind === 'working_note') {
      return item.streamState === 'streaming' || item.streamState === 'idle'
    }
    if (item.kind === 'tool_group') {
      return item.status === 'running' || item.status === 'waiting_for_approval'
    }
    return false
  })
}

/**
 * 函数名：buildTranscriptItems
 * 入参：
 *   - messages (ConversationMessage[]): 完整的会话消息列表（按时间顺序）
 * 功能：将扁平消息列表转换为用于渲染的转录条目数组，按 run 聚合思考/工作笔记/工具调用为过程分组
 * 运行逻辑：
 *   1. 维护当前分组状态（currentRunId/currentSubItems）与工具调用缓冲区（currentToolBuffer）
 *   2. 用户消息/系统提示：结算当前分组后直接作为独立 message 条目输出
 *   3. tool_trace 消息：按 runId 判断是否需要新开分组，再判断是否能并入当前工具缓冲区（否则先结算缓冲区），最终缓冲入组
 *   4. assistant_message 消息：
 *      - working_note 展示模式：结算工具缓冲区后作为 working_note 子条目加入当前分组
 *      - 携带 reasoning_text：结算工具缓冲区后作为 thinking 子条目加入当前分组
 *      - 携带最终内容文本或已失败/取消：结算整个分组后作为独立的 answer_message 条目输出
 *   5. 遍历结束后结算最后一个未关闭的分组
 * 出参：TranscriptItem[] - 构建完成的转录条目数组，供 UI 渲染
 */
export function buildTranscriptItems(messages: ConversationMessage[]): TranscriptItem[] {
  const items: TranscriptItem[] = []
  const runGroupCounter: Record<string, number> = {}

  let currentRunId: string | null = null
  let currentSubItems: ProcessSubItem[] = []
  let currentToolBuffer: ConversationMessage[] = []

  const flushToolBuffer = () => {
    if (currentToolBuffer.length === 0) return
    currentSubItems.push({
      kind: 'tool_group',
      id: `tools-${currentToolBuffer[0].id}`,
      messages: currentToolBuffer,
      details: currentToolBuffer.map(buildToolTraceDetail),
      status: getToolGroupStatus(currentToolBuffer),
    })
    currentToolBuffer = []
  }

  const flushProcessGroup = () => {
    flushToolBuffer()
    if (currentRunId !== null && currentSubItems.length > 0) {
      const seq = (runGroupCounter[currentRunId] = (runGroupCounter[currentRunId] ?? 0) + 1)
      items.push({
        kind: 'process_group',
        id: `process-${currentRunId}-${seq}`,
        runId: currentRunId,
        subItems: currentSubItems,
      })
    }
    currentRunId = null
    currentSubItems = []
  }

  for (const message of messages) {
    if (message.messageType === 'user_message' || message.messageType === 'system_notice') {
      flushProcessGroup()
      items.push({ kind: 'message', id: message.id, message })
      continue
    }

    if (message.messageType === 'tool_trace') {
      const runId = message.runId ?? 'unknown'
      if (currentRunId !== null && currentRunId !== runId) {
        flushProcessGroup()
      }
      if (currentRunId === null) {
        currentRunId = runId
        currentSubItems = []
        currentToolBuffer = []
      }
      if (!shouldAppendToToolGroup(currentToolBuffer, message)) {
        flushToolBuffer()
      }
      currentToolBuffer.push(message)
      continue
    }

    if (message.messageType === 'assistant_message') {
      const runId = message.runId ?? 'unknown'
      const isWorkingNote = message.displayMode === 'working_note'
      const reasoningText = getAssistantReasoningText(message)

      if (isWorkingNote) {
        if (currentRunId !== null && currentRunId !== runId) {
          flushProcessGroup()
        }
        if (currentRunId === null) {
          currentRunId = runId
          currentSubItems = []
          currentToolBuffer = []
        }
        flushToolBuffer()
        if (message.contentText) {
          currentSubItems.push({
            kind: 'working_note',
            id: message.id,
            text: message.contentText,
            streamState: message.streamState,
          })
        }
        continue
      }

      if (reasoningText) {
        if (currentRunId !== null && currentRunId !== runId) {
          flushProcessGroup()
        }
        if (currentRunId === null) {
          currentRunId = runId
          currentSubItems = []
          currentToolBuffer = []
        }
        flushToolBuffer()
        currentSubItems.push({
          kind: 'thinking',
          id: `thinking-${message.id}`,
          text: reasoningText,
          streamState: message.streamState,
        })
      }

      if (message.contentText || message.streamState === 'failed' || message.streamState === 'cancelled') {
        flushProcessGroup()
        items.push({ kind: 'answer_message', id: message.id, message })
      }

      continue
    }
  }

  flushProcessGroup()
  return items
}

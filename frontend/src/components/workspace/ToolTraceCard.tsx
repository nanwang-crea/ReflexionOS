/**
 * 文件功能：工具调用轨迹卡片
 * 文件描述：将单条工具调用类型的会话消息转换为展示状态，并渲染为 ActionReceipt 卡片；
 *          delegate 工具单独路由到专属的 DelegateToolCall 组件
 * 核心逻辑：优先取 payloadJson.status，缺失时回退到消息的 streamState，映射为统一的
 *          ActionReceiptStatus（failed/cancelled/waiting_for_approval/running/completed）
 */
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import type { ApprovalActionPayload, ApprovalActionType } from '@/components/execution/approvalActions'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'

export type ReceiptDetailClickHandler = (detail: ActionReceiptDetail) => void
import type { ConversationMessage } from '@/types/conversation'
import { buildToolTraceDetail } from './transcriptItems'
import { DelegateToolCall } from './DelegateToolCall'

export type ToolApprovalActionHandler = (
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) => void

/**
 * 函数名：toActionReceiptStatus
 * 入参：
 *   - message (ConversationMessage): 工具调用类型的会话消息
 * 功能：将消息的原始状态字段映射为统一的 ActionReceiptStatus
 * 运行逻辑：优先读取 payloadJson.status（字符串），若不存在则回退到 message.streamState；
 *          再按取值分别映射为 failed/cancelled/waiting_for_approval/running，其余情况归为 completed
 * 出参：ActionReceiptStatus - 归一化后的回执状态
 */
function toActionReceiptStatus(message: ConversationMessage): ActionReceiptStatus {
  const status = typeof message.payloadJson.status === 'string'
    ? message.payloadJson.status
    : message.streamState

  if (status === 'failed') {
    return 'failed'
  }
  if (status === 'cancelled') {
    return 'cancelled'
  }
  if (status === 'waiting_for_approval') {
    return 'waiting_for_approval'
  }
  if (status === 'running' || status === 'streaming' || status === 'idle') {
    return 'running'
  }
  return 'completed'
}

/**
 * 组件名：ToolTraceGroup
 * 入参（props）：
 *   - details (ActionReceiptDetail[]): 待展示的工具调用详情列表
 *   - status (ActionReceiptStatus): 整组的展示状态
 *   - onApprovalAction (ToolApprovalActionHandler，可选): 审批操作回调
 *   - onDetailClick (ReceiptDetailClickHandler，可选): 详情点击回调
 * 作用/渲染逻辑：直接透传参数渲染 ActionReceipt 卡片
 * 返回值：JSX.Element - ActionReceipt 卡片
 */
export function ToolTraceGroup({
  details,
  status,
  onApprovalAction,
  onDetailClick,
}: {
  details: ActionReceiptDetail[]
  status: ActionReceiptStatus
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: ReceiptDetailClickHandler
}) {
  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
      onDetailClick={onDetailClick}
    />
  )
}

/**
 * 组件名：ToolTraceCard
 * 入参（props）：
 *   - message (ConversationMessage): 工具调用类型的会话消息
 *   - onApprovalAction (ToolApprovalActionHandler，可选): 审批操作回调
 * 作用/渲染逻辑：
 *   1. 通过 buildToolTraceDetail 将消息转换为 ActionReceiptDetail
 *   2. 若为 delegate 工具，解析出 arguments 并渲染专属的 DelegateToolCall 组件
 *   3. 其余工具调用统一渲染为 ToolTraceGroup（单条详情包装为数组）
 * 返回值：JSX.Element - DelegateToolCall 或 ToolTraceGroup
 */
export function ToolTraceCard({
  message,
  onApprovalAction,
}: {
  message: ConversationMessage
  onApprovalAction?: ToolApprovalActionHandler
}) {
  const detail = buildToolTraceDetail(message)

  // delegate 工具使用专属 UI 组件（子任务卡片）
  if (detail.toolName === 'delegate') {
    const args = typeof message.payloadJson.arguments === 'object' && message.payloadJson.arguments !== null
      ? message.payloadJson.arguments as Record<string, unknown>
      : undefined
    return <DelegateToolCall detail={detail} args={args} onApprovalAction={onApprovalAction} />
  }

  return (
    <ToolTraceGroup
      status={toActionReceiptStatus(message)}
      details={[detail]}
      onApprovalAction={onApprovalAction}
    />
  )
}

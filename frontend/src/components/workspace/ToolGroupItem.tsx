/**
 * 文件功能：工具调用分组展示组件
 * 文件描述：展示一组工具调用（tool_group）的回执，将 delegate 工具调用拆分为独立的 DelegateToolCall 组件渲染，
 *          其余工具调用合并为一张 ActionReceipt 卡片
 * 核心逻辑：按连续段切分 details（delegate 类型单独成段，其余连续归为一段），
 *          保证并行 delegate 场景下每个 delegate 调用都能独立渲染出专属 UI
 */
import { memo } from 'react'
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ReceiptDetailClickHandler, ToolApprovalActionHandler } from './ToolTraceCard'
import { DelegateToolCall } from './DelegateToolCall'

interface ToolGroupItemProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: ReceiptDetailClickHandler
}

type DetailSegment =
  | { kind: 'delegate'; detail: ActionReceiptDetail }
  | { kind: 'other'; details: ActionReceiptDetail[] }

// 按 toolName === 'delegate' 切分连续段：并行 delegate 场景下一个 tool_group
// 可能同时包含多个 delegate 调用，每个都需要各自独立渲染 DelegateToolCall；
// 非 delegate 的连续段仍合并成一张 ActionReceipt 卡片，保持原有分组展示。
/**
 * 函数名：segmentDetails
 * 入参：
 *   - details (ActionReceiptDetail[]): 一个工具调用组内的所有详情
 * 功能：按 toolName 是否为 'delegate' 将详情数组切分为若干连续段
 * 运行逻辑：顺序遍历详情，遇到 delegate 类型立即单独成段（先结算之前缓冲的 other 段），
 *          非 delegate 类型持续缓冲；遍历结束后结算末尾剩余的 other 缓冲段
 * 出参：DetailSegment[] - 切分后的分段数组，delegate 段与 other 段交替出现
 */
function segmentDetails(details: ActionReceiptDetail[]): DetailSegment[] {
  const segments: DetailSegment[] = []
  let otherBuffer: ActionReceiptDetail[] = []

  const flushOther = () => {
    if (otherBuffer.length > 0) {
      segments.push({ kind: 'other', details: otherBuffer })
      otherBuffer = []
    }
  }

  for (const detail of details) {
    if (detail.toolName === 'delegate') {
      flushOther()
      segments.push({ kind: 'delegate', detail })
    } else {
      otherBuffer.push(detail)
    }
  }
  flushOther()

  return segments
}

/**
 * 组件名：ToolGroupItem
 * 入参（props，ToolGroupItemProps）：
 *   - status (ActionReceiptStatus): 整组工具调用的状态
 *   - details (ActionReceiptDetail[]): 组内所有工具调用详情
 *   - onApprovalAction (ToolApprovalActionHandler，可选): 审批操作回调，转发给 ActionReceipt/DelegateToolCall
 *   - onDetailClick (ReceiptDetailClickHandler，可选): 详情点击回调，转发给 ActionReceipt
 * 作用/渲染逻辑：
 *   1. 调用 segmentDetails 将详情切分为 delegate 段与 other 段
 *   2. 若整组只有一个 other 段（无 delegate），直接渲染单张 ActionReceipt 卡片（兼容原有展示）
 *   3. 否则按段依次渲染：delegate 段渲染为独立的 DelegateToolCall，other 段渲染为独立的 ActionReceipt
 * 返回值：JSX.Element - 一个或多个工具调用展示卡片
 */
export const ToolGroupItem = memo(function ToolGroupItem({
  status,
  details,
  onApprovalAction,
  onDetailClick,
}: ToolGroupItemProps) {
  // delegate 工具使用专用的 DelegateToolCall 组件，展示子 agent 运行状态和时间线；
  // 其他工具继续使用通用的 ActionReceipt 组件。逐项判断而非整组判断，
  // 使一个 tool_group 内多个并行 delegate 调用能各自正确渲染。
  const segments = segmentDetails(details)

  if (segments.length === 1 && segments[0].kind === 'other') {
    return (
      <ActionReceipt
        status={status}
        details={segments[0].details}
        onApprovalAction={onApprovalAction}
        onDetailClick={onDetailClick}
      />
    )
  }

  return (
    <>
      {segments.map((segment, index) =>
        segment.kind === 'delegate' ? (
          <DelegateToolCall
            key={segment.detail.id}
            detail={segment.detail}
            args={segment.detail.arguments}
            onApprovalAction={onApprovalAction}
          />
        ) : (
          <ActionReceipt
            key={`other-${index}`}
            status={status}
            details={segment.details}
            onApprovalAction={onApprovalAction}
            onDetailClick={onDetailClick}
          />
        )
      )}
    </>
  )
})

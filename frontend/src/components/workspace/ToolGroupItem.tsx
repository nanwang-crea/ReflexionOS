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

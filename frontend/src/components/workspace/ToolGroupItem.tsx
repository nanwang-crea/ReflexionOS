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

export const ToolGroupItem = memo(function ToolGroupItem({
  status,
  details,
  onApprovalAction,
  onDetailClick,
}: ToolGroupItemProps) {
  // delegate 工具使用专用的 DelegateToolCall 组件，展示子 agent 运行状态和时间线
  // 其他工具继续使用通用的 ActionReceipt 组件
  if (details.length === 1 && details[0].toolName === 'delegate') {
    return (
      <DelegateToolCall
        detail={details[0]}
        args={details[0].arguments}
      />
    )
  }

  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
      onDetailClick={onDetailClick}
    />
  )
})

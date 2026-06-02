import { memo } from 'react'
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ReceiptDetailClickHandler, ToolApprovalActionHandler } from './ToolTraceCard'

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
  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
      onDetailClick={onDetailClick}
    />
  )
})

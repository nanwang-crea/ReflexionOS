import { memo } from 'react'

export const SystemNoticeItem = memo(function SystemNoticeItem({ contentText }: { contentText: string }) {
  return (
    <div className="mb-6 max-w-[920px] mx-auto w-full rounded-2xl border border-status-warning-border bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
      {contentText}
    </div>
  )
})

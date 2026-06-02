import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

export function WorkingNoteBlock({ text }: { text: string }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="mb-4 max-w-[920px] mx-auto w-full rounded-lg border border-edge bg-surface-secondary/50 px-3 py-2 text-sm leading-6 text-content-muted">
      <button
        type="button"
        onClick={() => setIsExpanded((value) => !value)}
        aria-expanded={isExpanded}
        className="flex w-full items-center gap-2 text-left"
      >
        {isExpanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
        )}
        <span>过程说明</span>
      </button>
      {isExpanded && (
        <div className="mt-2 whitespace-pre-wrap pl-5 text-content-secondary">
          {text}
        </div>
      )}
    </div>
  )
}

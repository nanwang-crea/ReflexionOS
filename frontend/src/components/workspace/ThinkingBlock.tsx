import { useState, useEffect } from 'react'
import { Brain, ChevronDown, ChevronRight } from 'lucide-react'

export function ThinkingBlock({
  text,
  isStreaming,
}: {
  text: string
  isStreaming: boolean
}) {
  const [isExpanded, setIsExpanded] = useState(isStreaming)

  useEffect(() => {
    if (isStreaming) {
      setIsExpanded(true)
      return
    }
    setIsExpanded(false)
  }, [isStreaming])

  return (
    <div className="mb-3 max-w-[920px] mx-auto w-full rounded-lg border border-edge bg-surface-secondary/60 px-3 py-2 text-xs leading-6 text-content-muted">
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
        <Brain className="h-3.5 w-3.5 shrink-0" />
        <span>Thinking</span>
      </button>
      <div
        className={`mt-2 whitespace-pre-wrap pl-9 ${isExpanded ? 'block' : 'hidden'}`}
        aria-hidden={!isExpanded}
      >
        {text}
      </div>
    </div>
  )
}

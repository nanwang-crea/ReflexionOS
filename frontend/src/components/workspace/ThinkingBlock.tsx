/**
 * 文件功能：模型思考过程展示块
 * 文件描述：以可折叠区块展示模型的思维链（reasoning）文本，流式输出时自动展开，结束后按 defaultExpanded 决定是否收起
 * 核心逻辑：isStreaming 变化时通过 useEffect 联动展开状态——流式中强制展开，流式结束后回退到默认展开状态
 */
import { useState, useEffect } from 'react'
import { Brain, ChevronDown, ChevronRight } from 'lucide-react'

/**
 * 组件名：ThinkingBlock
 * 入参（props）：
 *   - text (string): 思考过程的文本内容
 *   - isStreaming (boolean): 是否仍在流式输出中
 *   - defaultExpanded (boolean，默认 false): 流式结束后的默认展开状态
 * 作用/渲染逻辑：
 *   1. 初始展开状态为 isStreaming 或 defaultExpanded
 *   2. isStreaming 为 true 时强制展开；变为 false 后回退到 defaultExpanded
 *   3. 点击标题栏可手动切换展开/收起，展开时展示思考文本
 * 返回值：JSX.Element - 可折叠的思考过程展示块
 */
export function ThinkingBlock({
  text,
  isStreaming,
  defaultExpanded = false,
}: {
  text: string
  isStreaming: boolean
  defaultExpanded?: boolean
}) {
  const [isExpanded, setIsExpanded] = useState(() => isStreaming || defaultExpanded)

  useEffect(() => {
    if (isStreaming) {
      setIsExpanded(true)
      return
    }
    setIsExpanded(defaultExpanded)
  }, [isStreaming, defaultExpanded])

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

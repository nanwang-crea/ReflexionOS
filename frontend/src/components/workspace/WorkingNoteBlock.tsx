/**
 * 文件功能：过程说明（工作笔记）展示块
 * 文件描述：以可折叠区块展示模型在执行过程中输出的说明性文本（working note），支持 Markdown 渲染
 * 核心逻辑：内部维护展开/收起状态，展开时以 MarkdownRenderer 的 plain 变体渲染文本内容
 */
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'

/**
 * 组件名：WorkingNoteBlock
 * 入参（props）：
 *   - text (string): 过程说明的文本内容（Markdown 格式）
 *   - defaultExpanded (boolean，默认 false): 初始是否展开
 * 作用/渲染逻辑：点击标题栏切换展开/收起状态，展开时使用 MarkdownRenderer 渲染文本内容
 * 返回值：JSX.Element - 可折叠的过程说明展示块
 */
export function WorkingNoteBlock({
  text,
  defaultExpanded = false,
}: {
  text: string
  defaultExpanded?: boolean
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

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
        <div className="mt-2 pl-5 text-content-secondary">
          <MarkdownRenderer content={text} variant="plain" />
        </div>
      )}
    </div>
  )
}

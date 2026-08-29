// Markdown 渲染组件：把 AI 回复等 Markdown 文本渲染为带样式的 HTML（代码块高亮容器、标题、列表、
// 链接、引用、表格等），并支持流式输出时的未闭合代码块修补和光标闪烁效果。
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useMemo } from 'react'

interface MarkdownRendererProps {
  content: string
  className?: string
  variant?: 'prose' | 'plain'
  isStreaming?: boolean
}

// 参数：content - 原始 Markdown 文本；isStreaming - 是否处于流式输出中（内容可能还没结束）。
// 作用：统一换行符为 \n；若正在流式输出且代码块围栏（```）数量为奇数（说明有一个未闭合的代码块），
// 则在末尾补一个 ``` 闭合，避免流式渲染过程中样式错乱。
// 返回：处理后的 Markdown 字符串。
function normalizeStreamingMarkdown(content: string, isStreaming: boolean) {
  const normalized = content.replace(/\r\n/g, '\n')

  if (!isStreaming) {
    return normalized
  }

  const fenceMatches = normalized.match(/```/g)
  if (fenceMatches && fenceMatches.length % 2 === 1) {
    return `${normalized}\n\`\`\``
  }

  return normalized
}

// react-markdown 的自定义渲染组件映射：为代码块（含复制按钮与语言标签）、标题、列表、链接、
// 引用、表格等元素指定统一的 Tailwind 样式，替代默认的原生标签渲染。
const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '')
    const isInline = !match
    const language = match ? match[1] : null

    if (!isInline) {
      return (
        <div className="relative group">
          {language && (
            <div className="absolute top-2 left-3 text-xs text-content-muted/60 font-mono select-none">
              {language}
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              const text = String(children).replace(/\n$/, '')
              navigator.clipboard.writeText(text).catch(() => {})
            }}
            className="absolute top-2 right-2 rounded-md px-1.5 py-0.5 text-xs text-content-muted opacity-0 group-hover:opacity-100 transition-opacity bg-surface-tertiary/80 hover:text-content-secondary"
          >
            复制
          </button>
          <pre className="bg-surface-code text-content-primary rounded-lg p-4 overflow-x-auto my-3 pt-8 max-w-full">
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        </div>
      )
    }

    return (
      <code className="bg-surface-tertiary text-content-secondary px-1.5 py-0.5 rounded text-sm" {...props}>
        {children}
      </code>
    )
  },

  h1: ({ children }) => (
    <h1 className="text-2xl font-bold mt-6 mb-3">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-semibold mt-5 mb-2">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-medium mt-4 mb-2">{children}</h3>
  ),

  ul: ({ children }) => (
    <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>
  ),

  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent hover:underline"
    >
      {children}
    </a>
  ),

  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-edge pl-4 italic my-3 text-content-muted">
      {children}
    </blockquote>
  ),

  table: ({ children }) => (
    <div className="overflow-x-auto my-3 max-w-full">
      <table className="min-w-full border border-edge">
        {children}
      </table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-edge px-3 py-2 bg-surface-secondary font-semibold">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-edge px-3 py-2">
      {children}
    </td>
  ),
}

// 参数：content - 要渲染的 Markdown 文本；className - 外层容器额外样式类名；
// variant - 'prose' 使用 Tailwind Typography 排版样式，'plain' 不套用；
// isStreaming - 是否处于流式输出中，为 true 时会在末尾显示光标闪烁效果并修补未闭合代码块。
// 作用：对内容做流式修补后交给 ReactMarkdown 渲染（remark-gfm 支持表格/删除线等 GFM 语法），
// 用 useMemo 缓存修补结果和渲染结果，减少流式更新时的重复计算。
// 返回：包裹渲染结果的 div；流式状态下额外渲染一个闪烁光标 span。
export function MarkdownRenderer({
  content,
  className = '',
  variant = 'prose',
  isStreaming = false
}: MarkdownRendererProps) {
  const baseClassName = variant === 'prose' ? 'prose prose-sm max-w-none' : ''
  const renderedContent = useMemo(
    () => normalizeStreamingMarkdown(content, isStreaming),
    [content, isStreaming]
  )

  const markdownContent = useMemo(() => (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {renderedContent}
    </ReactMarkdown>
  ), [renderedContent])

  return (
    <div className={`${baseClassName} ${className}`.trim()}>
      {markdownContent}
      {isStreaming && (
        <span className="ml-1 inline-block h-5 w-2 bg-content-muted align-middle animate-cursor-blink" />
      )}
    </div>
  )
}

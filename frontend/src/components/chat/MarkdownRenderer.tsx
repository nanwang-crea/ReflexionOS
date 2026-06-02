import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useMemo } from 'react'

interface MarkdownRendererProps {
  content: string
  className?: string
  variant?: 'prose' | 'plain'
  isStreaming?: boolean
}

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

  const components = {
    code({ className, children, ...props }: any) {
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

    h1: ({ children }: any) => (
      <h1 className="text-2xl font-bold mt-6 mb-3">{children}</h1>
    ),
    h2: ({ children }: any) => (
      <h2 className="text-xl font-semibold mt-5 mb-2">{children}</h2>
    ),
    h3: ({ children }: any) => (
      <h3 className="text-lg font-medium mt-4 mb-2">{children}</h3>
    ),

    ul: ({ children }: any) => (
      <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>
    ),
    ol: ({ children }: any) => (
      <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>
    ),

    a: ({ href, children }: any) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent hover:underline"
      >
        {children}
      </a>
    ),

    blockquote: ({ children }: any) => (
      <blockquote className="border-l-4 border-edge pl-4 italic my-3 text-content-muted">
        {children}
      </blockquote>
    ),

    table: ({ children }: any) => (
      <div className="overflow-x-auto my-3 max-w-full">
        <table className="min-w-full border border-edge">
          {children}
        </table>
      </div>
    ),
    th: ({ children }: any) => (
      <th className="border border-edge px-3 py-2 bg-surface-secondary font-semibold">
        {children}
      </th>
    ),
    td: ({ children }: any) => (
      <td className="border border-edge px-3 py-2">
        {children}
      </td>
    ),
  }

  const markdownContent = !isStreaming
    ? useMemo(() => (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {renderedContent}
        </ReactMarkdown>
      ), [renderedContent])
    : (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {renderedContent}
        </ReactMarkdown>
      )

  return (
    <div className={`${baseClassName} ${className}`.trim()}>
      {markdownContent}
      {isStreaming && (
        <span className="ml-1 inline-block h-5 w-2 bg-content-muted align-middle animate-cursor-blink" />
      )}
    </div>
  )
}

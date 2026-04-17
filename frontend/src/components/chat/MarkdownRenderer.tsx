import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion } from 'framer-motion'

interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  return (
    <motion.div
      className={`prose prose-sm max-w-none ${className}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const isInline = !match
            return !isInline ? (
              <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto my-3">
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            ) : (
              <code className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm" {...props}>
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
              className="text-blue-600 hover:underline"
            >
              {children}
            </a>
          ),
          
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-gray-300 pl-4 italic my-3 text-gray-600">
              {children}
            </blockquote>
          ),
          
          table: ({ children }) => (
            <div className="overflow-x-auto my-3">
              <table className="min-w-full border border-gray-200">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-gray-200 px-3 py-2 bg-gray-50 font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-200 px-3 py-2">
              {children}
            </td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </motion.div>
  )
}

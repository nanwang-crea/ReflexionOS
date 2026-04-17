import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { StatusBadge } from './StatusBadge'

interface StepCardProps {
  stepNumber: number
  toolName: string
  status: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, any>
  defaultExpanded?: boolean
  autoCollapse?: boolean
}

export function StepCard({
  stepNumber,
  toolName,
  status,
  output,
  error,
  duration,
  arguments: args,
  defaultExpanded = true,
  autoCollapse = true
}: StepCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [hasAutoCollapsed, setHasAutoCollapsed] = useState(false)
  
  if (autoCollapse && status !== 'running' && !hasAutoCollapsed && output) {
    setTimeout(() => {
      setIsExpanded(false)
      setHasAutoCollapsed(true)
    }, 2000)
  }
  
  const hasContent = output || error || args
  
  return (
    <motion.div
      className="bg-white rounded-lg border-2 overflow-hidden"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      style={{
        borderColor: status === 'running' ? '#3B82F6' :
                     status === 'success' ? '#10B981' :
                     status === 'failed' ? '#EF4444' : '#E5E7EB'
      }}
    >
      <div 
        className="flex items-center justify-between p-3 hover:bg-gray-50 cursor-pointer"
        onClick={() => hasContent && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <StatusBadge status={status} />
          <span className="font-medium text-gray-700">Step {stepNumber}</span>
          <span className="text-gray-500">{toolName}</span>
        </div>
        
        <div className="flex items-center gap-2">
          {duration && (
            <span className="text-sm text-gray-500">
              {duration.toFixed(2)}s
            </span>
          )}
          {hasContent && (
            <motion.div
              animate={{ rotate: isExpanded ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown className="w-4 h-4 text-gray-400" />
            </motion.div>
          )}
        </div>
      </div>
      
      <AnimatePresence>
        {isExpanded && hasContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-gray-200"
          >
            <div className="p-3 space-y-2">
              {args && Object.keys(args).length > 0 && (
                <div className="text-sm">
                  <span className="font-medium text-gray-600">参数:</span>
                  <pre className="mt-1 text-xs bg-gray-50 p-2 rounded overflow-auto">
                    {JSON.stringify(args, null, 2)}
                  </pre>
                </div>
              )}
              
              {output && (
                <div className="text-sm">
                  <span className="font-medium text-gray-600">输出:</span>
                  <pre className="mt-1 text-xs bg-gray-50 p-2 rounded overflow-auto max-h-40">
                    {output}
                  </pre>
                </div>
              )}
              
              {error && (
                <div className="text-sm">
                  <span className="font-medium text-red-600">错误:</span>
                  <pre className="mt-1 text-xs bg-red-50 text-red-700 p-2 rounded overflow-auto">
                    {error}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

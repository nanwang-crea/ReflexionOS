import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Loader2, Send, Square } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  onCancel?: () => void
  disabled?: boolean
  placeholder?: string
  isLoading?: boolean
  canCancel?: boolean
  isCancelling?: boolean
}

export function ChatInput({ 
  onSend, 
  onCancel,
  disabled = false, 
  placeholder = '描述你想要 Agent 做什么...',
  isLoading = false,
  canCancel = false,
  isCancelling = false
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [isComposing, setIsComposing] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`
  }, [value])
  
  const handleSend = () => {
    if (value.trim() && !disabled && !isLoading) {
      onSend(value.trim())
      setValue('')
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || isComposing) {
      return
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }
  
  return (
    <div className="relative">
      <motion.div
        className="relative overflow-hidden rounded-2xl border-2 border-gray-200 bg-white transition-all duration-200"
        animate={{ scale: isFocused ? 1.01 : 1 }}
        transition={{ duration: 0.2 }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          rows={1}
          className="min-h-[88px] w-full resize-none bg-transparent px-4 py-3 pr-4 text-[15px] leading-7 text-slate-700 outline-none disabled:cursor-not-allowed disabled:bg-gray-50"
        />

        <div className="flex items-center justify-between border-t border-gray-100 px-3 py-2">
          <span className="text-xs text-slate-400">
            `Enter` 发送，`Shift + Enter` 换行
          </span>

          <div className="flex items-center gap-2">
            {canCancel || isCancelling ? (
              <motion.button
                type="button"
                onClick={onCancel}
                disabled={isCancelling}
                className="flex items-center gap-2 rounded-xl bg-slate-100 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:text-slate-400"
                whileHover={isCancelling ? undefined : { scale: 1.03 }}
                whileTap={isCancelling ? undefined : { scale: 0.97 }}
              >
                {isCancelling ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                <span>{isCancelling ? '取消中' : '取消'}</span>
              </motion.button>
            ) : (
              <motion.button
                type="button"
                onClick={handleSend}
                disabled={!value.trim() || disabled || isLoading}
                className="rounded-xl bg-blue-600 px-4 py-2 font-medium text-white shadow-lg shadow-blue-500/30 transition disabled:cursor-not-allowed disabled:bg-gray-300"
                whileHover={{ scale: 1.03, y: -1 }}
                whileTap={{ scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 400 }}
              >
                {isLoading ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  >
                    <Loader2 className="h-4 w-4" />
                  </motion.div>
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </motion.button>
            )}
          </div>
        </div>
        
        <motion.div
          className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500 to-purple-500"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: isFocused ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />
      </motion.div>
    </div>
  )
}

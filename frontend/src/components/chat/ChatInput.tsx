import { useState } from 'react'
import { motion } from 'framer-motion'
import { Send, Loader2 } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
  isLoading?: boolean
}

export function ChatInput({ 
  onSend, 
  disabled = false, 
  placeholder = '描述你想要 Agent 做什么...',
  isLoading = false 
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  
  const handleSend = () => {
    if (value.trim() && !disabled && !isLoading) {
      onSend(value.trim())
      setValue('')
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }
  
  return (
    <div className="relative">
      <motion.div
        className="relative"
        animate={{ scale: isFocused ? 1.01 : 1 }}
        transition={{ duration: 0.2 }}
      >
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          className="w-full px-4 py-3 bg-white border-2 border-gray-200 rounded-xl
                     focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20
                     transition-all duration-200 disabled:bg-gray-50 disabled:cursor-not-allowed"
        />
        
        <motion.div
          className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500 to-purple-500"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: isFocused ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />
      </motion.div>
      
      <motion.button
        onClick={handleSend}
        disabled={!value.trim() || disabled || isLoading}
        className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 
                   bg-blue-600 text-white rounded-lg font-medium
                   disabled:bg-gray-300 disabled:cursor-not-allowed
                   shadow-lg shadow-blue-500/30"
        whileHover={{ scale: 1.05, y: -1 }}
        whileTap={{ scale: 0.95 }}
        transition={{ type: 'spring', stiffness: 400 }}
      >
        {isLoading ? (
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <Loader2 className="w-4 h-4" />
          </motion.div>
        ) : (
          <Send className="w-4 h-4" />
        )}
      </motion.button>
    </div>
  )
}

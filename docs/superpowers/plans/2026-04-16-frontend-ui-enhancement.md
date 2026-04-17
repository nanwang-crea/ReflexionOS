# 前端 UI 完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现现代简约风格的前端 UI,包括时间线融合、流畅动画、状态反馈优化、Markdown 渲染和任务打断功能

**Architecture:** 使用 framer-motion 实现动画系统,react-markdown 渲染 Markdown,重构 AgentWorkspace 将执行步骤融入对话流,实现任务打断 API 集成

**Tech Stack:** React, TypeScript, framer-motion, lucide-react, react-markdown, remark-gfm, TailwindCSS, Zustand

---

## 文件结构

```
frontend/src/
├── components/
│   ├── animations/
│   │   ├── FadeIn.tsx
│   │   ├── SlideIn.tsx
│   │   ├── Skeleton.tsx
│   │   └── Cursor.tsx
│   ├── chat/
│   │   ├── ChatMessage.tsx
│   │   ├── ChatInput.tsx
│   │   ├── StreamingText.tsx
│   │   └── MarkdownRenderer.tsx      # 新增: Markdown 渲染器
│   ├── execution/
│   │   ├── StepCard.tsx
│   │   ├── StatusBadge.tsx
│   │   └── ExecutionControls.tsx     # 新增: 执行控制组件
│   └── feedback/
│       ├── LoadingSpinner.tsx
│       ├── ErrorAlert.tsx
│       └── SuccessToast.tsx
├── pages/
│   └── AgentWorkspace.tsx (修改)
├── stores/
│   ├── animationStore.ts
│   └── executionStore.ts             # 新增: 执行状态管理
└── types/
    └── animation.ts
```

---

## 阶段一: 基础设施准备

### 任务 1.1: 安装依赖

**文件:**
- 修改: `frontend/package.json`

- [ ] **步骤 1: 安装 framer-motion 和 lucide-react**

```bash
cd frontend
npm install framer-motion lucide-react
```

- [ ] **步骤 2: 验证安装**

```bash
npm list framer-motion lucide-react
```

预期输出:
```
framer-motion@11.x.x
lucide-react@0.312.x
```

- [ ] **步骤 3: 提交依赖更新**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat: 添加 framer-motion 和 lucide-react 依赖"
```

---

### 任务 1.2: 创建动画配置 Store

**文件:**
- 创建: `frontend/src/stores/animationStore.ts`
- 创建: `frontend/src/types/animation.ts`

- [ ] **步骤 1: 创建动画类型定义**

创建 `frontend/src/types/animation.ts`:

```typescript
export type AnimationDuration = 'fast' | 'normal' | 'slow'

export interface AnimationConfig {
  duration: AnimationDuration
  reducedMotion: boolean
}

export const durationMap: Record<AnimationDuration, number> = {
  fast: 0.15,
  normal: 0.3,
  slow: 0.5
}
```

- [ ] **步骤 2: 创建动画 Store**

创建 `frontend/src/stores/animationStore.ts`:

```typescript
import { create } from 'zustand'
import { AnimationConfig, AnimationDuration } from '@/types/animation'

interface AnimationState extends AnimationConfig {
  setDuration: (duration: AnimationDuration) => void
  setReducedMotion: (reducedMotion: boolean) => void
}

export const useAnimationStore = create<AnimationState>((set) => ({
  duration: 'normal',
  reducedMotion: false,
  
  setDuration: (duration) => set({ duration }),
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
}))

// 初始化检测用户偏好
if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  useAnimationStore.getState().setReducedMotion(mediaQuery.matches)
  
  mediaQuery.addEventListener('change', (e) => {
    useAnimationStore.getState().setReducedMotion(e.matches)
  })
}
```

- [ ] **步骤 3: 提交代码**

```bash
git add frontend/src/stores/animationStore.ts frontend/src/types/animation.ts
git commit -m "feat: 创建动画配置 Store"
```

---

### 任务 1.3: 创建基础动画组件

**文件:**
- 创建: `frontend/src/components/animations/FadeIn.tsx`
- 创建: `frontend/src/components/animations/SlideIn.tsx`

- [ ] **步骤 1: 创建 FadeIn 组件**

创建 `frontend/src/components/animations/FadeIn.tsx`:

```typescript
import { motion } from 'framer-motion'
import { ReactNode } from 'react'
import { useAnimationStore } from '@/stores/animationStore'
import { durationMap } from '@/types/animation'

interface FadeInProps {
  children: ReactNode
  delay?: number
  className?: string
}

export function FadeIn({ children, delay = 0, className = '' }: FadeInProps) {
  const { duration, reducedMotion } = useAnimationStore()
  
  if (reducedMotion) {
    return <div className={className}>{children}</div>
  }
  
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ 
        duration: durationMap[duration], 
        delay 
      }}
    >
      {children}
    </motion.div>
  )
}
```

- [ ] **步骤 2: 创建 SlideIn 组件**

创建 `frontend/src/components/animations/SlideIn.tsx`:

```typescript
import { motion } from 'framer-motion'
import { ReactNode } from 'react'
import { useAnimationStore } from '@/stores/animationStore'
import { durationMap } from '@/types/animation'

interface SlideInProps {
  children: ReactNode
  direction?: 'up' | 'down' | 'left' | 'right'
  delay?: number
  className?: string
}

export function SlideIn({ 
  children, 
  direction = 'up', 
  delay = 0,
  className = '' 
}: SlideInProps) {
  const { duration, reducedMotion } = useAnimationStore()
  
  const directionOffset = {
    up: { y: 20 },
    down: { y: -20 },
    left: { x: 20 },
    right: { x: -20 }
  }
  
  if (reducedMotion) {
    return <div className={className}>{children}</div>
  }
  
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, ...directionOffset[direction] }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ 
        duration: durationMap[duration], 
        delay,
        ease: 'easeOut'
      }}
    >
      {children}
    </motion.div>
  )
}
```

- [ ] **步骤 3: 创建组件索引**

创建 `frontend/src/components/animations/index.ts`:

```typescript
export { FadeIn } from './FadeIn'
export { SlideIn } from './SlideIn'
```

- [ ] **步骤 4: 提交代码**

```bash
git add frontend/src/components/animations/
git commit -m "feat: 创建 FadeIn 和 SlideIn 动画组件"
```

---

### 任务 1.4: 创建骨架屏组件

**文件:**
- 创建: `frontend/src/components/animations/Skeleton.tsx`

- [ ] **步骤 1: 创建 Skeleton 组件**

创建 `frontend/src/components/animations/Skeleton.tsx`:

```typescript
import { motion } from 'framer-motion'

interface SkeletonProps {
  className?: string
  variant?: 'text' | 'rectangular' | 'circular'
  width?: string | number
  height?: string | number
}

export function Skeleton({ 
  className = '', 
  variant = 'rectangular',
  width,
  height 
}: SkeletonProps) {
  const variantClasses = {
    text: 'rounded',
    rectangular: 'rounded-lg',
    circular: 'rounded-full'
  }
  
  const style: React.CSSProperties = {
    width: width,
    height: height || (variant === 'text' ? '1rem' : undefined)
  }
  
  return (
    <motion.div
      className={`bg-gray-200 ${variantClasses[variant]} ${className}`}
      style={style}
      animate={{ opacity: [0.5, 1, 0.5] }}
      transition={{ 
        duration: 1.5, 
        repeat: Infinity,
        ease: 'easeInOut'
      }}
    />
  )
}

export function MessageSkeleton() {
  return (
    <div className="space-y-3 p-4 bg-white rounded-lg border border-gray-200">
      <Skeleton variant="text" width="60%" />
      <Skeleton variant="text" width="80%" />
      <Skeleton variant="text" width="40%" />
    </div>
  )
}

export function StepSkeleton() {
  return (
    <div className="p-3 bg-white rounded-lg border border-gray-200">
      <div className="flex items-center gap-3">
        <Skeleton variant="circular" width={24} height={24} />
        <Skeleton variant="text" width="30%" />
        <Skeleton variant="text" width="20%" className="ml-auto" />
      </div>
    </div>
  )
}
```

- [ ] **步骤 2: 更新组件索引**

更新 `frontend/src/components/animations/index.ts`:

```typescript
export { FadeIn } from './FadeIn'
export { SlideIn } from './SlideIn'
export { Skeleton, MessageSkeleton, StepSkeleton } from './Skeleton'
```

- [ ] **步骤 3: 提交代码**

```bash
git add frontend/src/components/animations/
git commit -m "feat: 创建骨架屏组件"
```

---

## 阶段二: 时间线融合

### 任务 2.1: 创建 StepCard 组件

**文件:**
- 创建: `frontend/src/components/execution/StepCard.tsx`
- 创建: `frontend/src/components/execution/StatusBadge.tsx`

- [ ] **步骤 1: 创建 StatusBadge 组件**

创建 `frontend/src/components/execution/StatusBadge.tsx`:

```typescript
import { motion } from 'framer-motion'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'

type StepStatus = 'running' | 'success' | 'failed'

interface StatusBadgeProps {
  status: StepStatus
  size?: 'sm' | 'md' | 'lg'
}

const statusConfig = {
  running: {
    icon: Loader2,
    color: 'text-blue-500',
    bgColor: 'bg-blue-50',
    animate: { rotate: 360 }
  },
  success: {
    icon: CheckCircle2,
    color: 'text-green-500',
    bgColor: 'bg-green-50',
    animate: { scale: [0.8, 1] }
  },
  failed: {
    icon: XCircle,
    color: 'text-red-500',
    bgColor: 'bg-red-50',
    animate: { x: [0, -5, 5, -5, 5, 0] }
  }
}

const sizeConfig = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status]
  const Icon = config.icon
  
  return (
    <motion.div
      className={`flex items-center justify-center ${config.bgColor} rounded-full p-1`}
      initial={config.animate}
      animate={status === 'running' ? { rotate: 360 } : config.animate}
      transition={status === 'running' 
        ? { duration: 1, repeat: Infinity, ease: 'linear' }
        : { duration: 0.3 }
      }
    >
      <Icon className={`${config.color} ${sizeConfig[size]}`} />
    </motion.div>
  )
}
```

- [ ] **步骤 2: 创建 StepCard 组件**

创建 `frontend/src/components/execution/StepCard.tsx`:

```typescript
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp } from 'lucide-react'
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
  
  // 自动折叠逻辑
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
      {/* Header */}
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
      
      {/* Content */}
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
              {/* Arguments */}
              {args && Object.keys(args).length > 0 && (
                <div className="text-sm">
                  <span className="font-medium text-gray-600">参数:</span>
                  <pre className="mt-1 text-xs bg-gray-50 p-2 rounded overflow-auto">
                    {JSON.stringify(args, null, 2)}
                  </pre>
                </div>
              )}
              
              {/* Output */}
              {output && (
                <div className="text-sm">
                  <span className="font-medium text-gray-600">输出:</span>
                  <pre className="mt-1 text-xs bg-gray-50 p-2 rounded overflow-auto max-h-40">
                    {output}
                  </pre>
                </div>
              )}
              
              {/* Error */}
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
```

- [ ] **步骤 3: 创建组件索引**

创建 `frontend/src/components/execution/index.ts`:

```typescript
export { StepCard } from './StepCard'
export { StatusBadge } from './StatusBadge'
```

- [ ] **步骤 4: 提交代码**

```bash
git add frontend/src/components/execution/
git commit -m "feat: 创建 StepCard 和 StatusBadge 组件"
```

---

### 任务 2.2: 重构 AgentWorkspace - 准备工作

**文件:**
- 修改: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **步骤 1: 备份当前文件**

```bash
cp frontend/src/pages/AgentWorkspace.tsx frontend/src/pages/AgentWorkspace.tsx.backup
```

- [ ] **步骤 2: 提交备份**

```bash
git add frontend/src/pages/AgentWorkspace.tsx.backup
git commit -m "chore: 备份 AgentWorkspace 原始文件"
```

---

### 任务 2.3: 重构 AgentWorkspace - 核心逻辑

**文件:**
- 修改: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **步骤 1: 重构消息类型定义**

在 `frontend/src/pages/AgentWorkspace.tsx` 中修改类型定义:

```typescript
import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ExecutionWebSocket } from '@/services/websocketClient'
import { ThoughtDisclosure } from '@/components/StreamingMessage'
import { StepCard } from '@/components/execution/StepCard'
import { SlideIn } from '@/components/animations'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'

type ChatItemType = 'user-message' | 'assistant-message' | 'thought' | 'step'

interface ChatItem {
  id: string
  type: ChatItemType
  content?: string
  stepNumber?: number
  toolName?: string
  status?: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, any>
  isStreaming?: boolean
}

interface ToolExecution {
  id: string
  stepNumber: number
  toolName: string
  status: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, any>
}
```

- [ ] **步骤 2: 重构状态管理**

继续修改 `frontend/src/pages/AgentWorkspace.tsx`:

```typescript
export default function AgentWorkspace() {
  const { currentProject } = useProjectStore()
  const { configured } = useSettingsStore()
  
  const [inputValue, setInputValue] = useState('')
  const [chatItems, setChatItems] = useState<ChatItem[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [llmStreamingContent, setLlmStreamingContent] = useState('')
  const [summaryStreamingContent, setSummaryStreamingContent] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')
  
  const wsRef = useRef<ExecutionWebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const stepCounterRef = useRef(0)
  const llmStreamingRef = useRef('')
  const summaryStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatItems, llmStreamingContent, summaryStreamingContent])

  // 添加聊天项
  const addChatItem = useCallback((item: Omit<ChatItem, 'id'>) => {
    setChatItems(prev => [...prev, {
      ...item,
      id: `item-${Date.now()}-${Math.random()}`
    }])
  }, [])

  // 刷新 LLM 流式消息
  const flushLlmStreamingMessage = useCallback((
    type: 'thought' | 'assistant-message',
    fallbackContent = ''
  ) => {
    const content = llmStreamingRef.current || fallbackContent
    if (!content) return

    addChatItem({ type, content })
    llmStreamingRef.current = ''
    setLlmStreamingContent('')
  }, [addChatItem])

  // WebSocket 连接逻辑保持不变...
  // (保留原有的 connectWebSocket 函数)
}
```

- [ ] **步骤 3: 更新 WebSocket 事件处理**

继续修改 `frontend/src/pages/AgentWorkspace.tsx`,更新事件处理逻辑:

```typescript
const connectWebSocket = useCallback(async () => {
  // ... 保留连接代码 ...
  
  ws.on('llm:tool_call', (data) => {
    flushLlmStreamingMessage('thought', data.thought)

    stepCounterRef.current++
    addChatItem({
      type: 'step',
      stepNumber: stepCounterRef.current,
      toolName: data.tool_name,
      status: 'running',
      arguments: data.arguments
    })
  })
  
  ws.on('tool:result', (data) => {
    setChatItems(prev => prev.map(item => 
      item.type === 'step' && item.toolName === data.tool_name && item.status === 'running'
        ? { ...item, status: data.success ? 'success' : 'failed', output: data.output, duration: data.duration }
        : item
    ))
  })
  
  ws.on('tool:error', (data) => {
    setChatItems(prev => prev.map(item =>
      item.type === 'step' && item.toolName === data.tool_name && item.status === 'running'
        ? { ...item, status: 'failed', error: data.error }
        : item
    ))
  })
  
  // ... 其他事件处理保持不变 ...
}, [addChatItem, flushLlmStreamingMessage])
```

- [ ] **步骤 4: 提交核心逻辑重构**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "refactor: 重构 AgentWorkspace 消息类型和状态管理"
```

---

### 任务 2.4: 重构 AgentWorkspace - 渲染逻辑

**文件:**
- 修改: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **步骤 1: 重构渲染函数**

在 `frontend/src/pages/AgentWorkspace.tsx` 中替换渲染逻辑:

```typescript
return (
  <div className="flex flex-col h-full">
    {/* Header - 保持不变 */}
    <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
      {/* ... header content ... */}
    </div>

    {/* Main Content */}
    <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
      {!configured && (
        <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-yellow-800">请先在设置页面配置 LLM API Key</p>
        </div>
      )}

      {/* Chat Items */}
      <AnimatePresence mode="popLayout">
        {chatItems.map((item) => {
          if (item.type === 'user-message') {
            return (
              <SlideIn key={item.id} direction="up">
                <div className="mb-4 text-right">
                  <div className="inline-block max-w-[80%] px-4 py-3 rounded-2xl bg-blue-600 text-white shadow-lg">
                    <div className="text-sm font-medium mb-1 opacity-70">你</div>
                    <div className="whitespace-pre-wrap">{item.content}</div>
                  </div>
                </div>
              </SlideIn>
            )
          }
          
          if (item.type === 'assistant-message') {
            return (
              <SlideIn key={item.id} direction="up">
                <div className="mb-4">
                  <div className="inline-block max-w-[80%] px-4 py-3 rounded-2xl border border-gray-200 bg-white text-gray-800 shadow-sm">
                    <div className="mb-1 text-sm font-medium opacity-70">🤖 Agent</div>
                    <div className="whitespace-pre-wrap">{item.content}</div>
                  </div>
                </div>
              </SlideIn>
            )
          }
          
          if (item.type === 'thought') {
            return (
              <SlideIn key={item.id} direction="up">
                <ThoughtDisclosure
                  label="已思考"
                  content={item.content || ''}
                />
              </SlideIn>
            )
          }
          
          if (item.type === 'step') {
            return (
              <SlideIn key={item.id} direction="up">
                <div className="mb-3">
                  <StepCard
                    stepNumber={item.stepNumber || 0}
                    toolName={item.toolName || ''}
                    status={item.status || 'running'}
                    output={item.output}
                    error={item.error}
                    duration={item.duration}
                    arguments={item.arguments}
                    defaultExpanded={item.status === 'running'}
                    autoCollapse={true}
                  />
                </div>
              </SlideIn>
            )
          }
          
          return null
        })}
      </AnimatePresence>

      {/* LLM Streaming Content */}
      {llmStreamingContent && (
        <SlideIn direction="up">
          <ThoughtDisclosure
            label="思考中"
            content={llmStreamingContent}
            isStreaming
            defaultOpen
          />
        </SlideIn>
      )}

      {/* Summary Streaming Content */}
      {summaryStreamingContent && (
        <SlideIn direction="up">
          <div className="mb-4">
            <div className="inline-block max-w-[80%] px-4 py-3 rounded-2xl border border-gray-200 bg-white text-gray-800 shadow-sm">
              <div className="mb-1 text-sm font-medium opacity-70">🤖 Agent 正在整理回答</div>
              <div className="whitespace-pre-wrap">
                {summaryStreamingContent}
                <motion.span
                  className="inline-block w-2 h-5 bg-blue-500 ml-1"
                  animate={{ opacity: [1, 0] }}
                  transition={{ duration: 0.5, repeat: Infinity }}
                />
              </div>
            </div>
          </div>
        </SlideIn>
      )}

      {/* Loading indicator */}
      {isExecuting && !llmStreamingContent && !summaryStreamingContent && chatItems.filter(i => i.type === 'step').length === 0 && (
        <div className="mt-4 flex items-center gap-2 text-gray-500">
          <motion.div
            className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full"
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          />
          <span>Agent 正在思考...</span>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>

    {/* Input Area - 保持不变 */}
    <div className="border-t border-gray-200 bg-white p-4">
      {/* ... input content ... */}
    </div>
  </div>
)
```

- [ ] **步骤 2: 验证编译**

```bash
cd frontend
npm run build
```

预期: 编译成功,无错误

- [ ] **步骤 3: 提交渲染逻辑重构**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: 重构 AgentWorkspace 渲染逻辑,实现时间线融合"
```

---

## 阶段三: 状态反馈优化

### 任务 3.1: 创建反馈组件

**文件:**
- 创建: `frontend/src/components/feedback/LoadingSpinner.tsx`
- 创建: `frontend/src/components/feedback/ErrorAlert.tsx`
- 创建: `frontend/src/components/feedback/SuccessToast.tsx`

- [ ] **步骤 1: 创建 LoadingSpinner**

创建 `frontend/src/components/feedback/LoadingSpinner.tsx`:

```typescript
import { motion } from 'framer-motion'
import { Loader2 } from 'lucide-react'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
}

const sizeMap = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-8 h-8'
}

export function LoadingSpinner({ size = 'md', text }: LoadingSpinnerProps) {
  return (
    <div className="flex items-center gap-2">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      >
        <Loader2 className={`${sizeMap[size]} text-blue-500`} />
      </motion.div>
      {text && <span className="text-gray-600">{text}</span>}
    </div>
  )
}
```

- [ ] **步骤 2: 创建 ErrorAlert**

创建 `frontend/src/components/feedback/ErrorAlert.tsx`:

```typescript
import { motion } from 'framer-motion'
import { AlertCircle, X } from 'lucide-react'

interface ErrorAlertProps {
  title?: string
  message: string
  onDismiss?: () => void
}

export function ErrorAlert({ title = '错误', message, onDismiss }: ErrorAlertProps) {
  return (
    <motion.div
      className="bg-red-50 border-2 border-red-200 rounded-lg p-4"
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-start gap-3">
        <motion.div
          animate={{ x: [0, -5, 5, -5, 5, 0] }}
          transition={{ duration: 0.4 }}
        >
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
        </motion.div>
        
        <div className="flex-1">
          <h4 className="font-medium text-red-800">{title}</h4>
          <p className="text-sm text-red-700 mt-1">{message}</p>
        </div>
        
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-red-400 hover:text-red-600 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </motion.div>
  )
}
```

- [ ] **步骤 3: 创建 SuccessToast**

创建 `frontend/src/components/feedback/SuccessToast.tsx`:

```typescript
import { motion } from 'framer-motion'
import { CheckCircle2 } from 'lucide-react'

interface SuccessToastProps {
  message: string
  duration?: number
  onDismiss?: () => void
}

export function SuccessToast({ message, duration = 3000, onDismiss }: SuccessToastProps) {
  return (
    <motion.div
      className="bg-green-50 border border-green-200 rounded-lg shadow-lg p-4"
      initial={{ opacity: 0, y: -20, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.9 }}
      transition={{ duration: 0.3, type: 'spring', stiffness: 300 }}
    >
      <div className="flex items-center gap-3">
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.1, type: 'spring', stiffness: 400 }}
        >
          <CheckCircle2 className="w-5 h-5 text-green-500" />
        </motion.div>
        <span className="text-green-800">{message}</span>
      </div>
    </motion.div>
  )
}
```

- [ ] **步骤 4: 创建组件索引**

创建 `frontend/src/components/feedback/index.ts`:

```typescript
export { LoadingSpinner } from './LoadingSpinner'
export { ErrorAlert } from './ErrorAlert'
export { SuccessToast } from './SuccessToast'
```

- [ ] **步骤 5: 提交代码**

```bash
git add frontend/src/components/feedback/
git commit -m "feat: 创建状态反馈组件"
```

---

### 任务 3.2: 优化输入框组件

**文件:**
- 创建: `frontend/src/components/chat/ChatInput.tsx`

- [ ] **步骤 1: 创建优化后的 ChatInput**

创建 `frontend/src/components/chat/ChatInput.tsx`:

```typescript
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
        
        {/* Animated underline */}
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
```

- [ ] **步骤 2: 创建组件索引**

创建 `frontend/src/components/chat/index.ts`:

```typescript
export { ChatInput } from './ChatInput'
```

- [ ] **步骤 3: 提交代码**

```bash
git add frontend/src/components/chat/
git commit -m "feat: 创建优化的 ChatInput 组件"
```

---

## 阶段四: 集成和测试

### 任务 4.1: 集成新组件到 AgentWorkspace

**文件:**
- 修改: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **步骤 1: 导入新组件**

在 `frontend/src/pages/AgentWorkspace.tsx` 顶部添加导入:

```typescript
import { ChatInput } from '@/components/chat/ChatInput'
import { ErrorAlert, LoadingSpinner } from '@/components/feedback'
```

- [ ] **步骤 2: 替换输入区域**

在 `frontend/src/pages/AgentWorkspace.tsx` 中替换输入区域:

```typescript
{/* Input Area */}
<div className="border-t border-gray-200 bg-white p-4">
  <ChatInput
    onSend={handleSend}
    disabled={!configured || !currentProject}
    isLoading={isExecuting}
  />
  {!currentProject && (
    <p className="mt-2 text-sm text-gray-500">请先在项目页面选择一个项目</p>
  )}
</div>
```

- [ ] **步骤 3: 提交代码**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: 集成新的输入组件到 AgentWorkspace"
```

---

### 任务 4.2: 测试和验证

- [ ] **步骤 1: 启动开发服务器**

```bash
cd frontend
npm run dev
```

- [ ] **步骤 2: 测试动画效果**

测试项目:
- [ ] 消息滑入动画流畅
- [ ] 步骤卡片展开/折叠正常
- [ ] 状态变化动画正常
- [ ] 流式文本光标闪烁
- [ ] 输入框聚焦动画

- [ ] **步骤 3: 测试时间线融合**

测试项目:
- [ ] 步骤卡片出现在对话流中
- [ ] 执行时步骤展开
- [ ] 完成后自动折叠
- [ ] 点击可展开查看详情

- [ ] **步骤 4: 性能测试**

```bash
# 构建生产版本
npm run build

# 检查包大小
ls -lh dist/assets/
```

预期: framer-motion 相关文件 < 100KB

- [ ] **步骤 5: 提交最终版本**

```bash
git add .
git commit -m "feat: 完成前端 UI 第二阶段优化

- 实现时间线融合,步骤卡片嵌入对话流
- 添加 framer-motion 动画系统
- 创建状态反馈组件
- 优化输入框和按钮样式
- 添加骨架屏和加载动画"
```

---

## 阶段五: 文档更新

### 任务 5.1: 更新项目文档

**文件:**
- 更新: `docs/superpowers/status/implementation-status-2026-04-16.md`

- [ ] **步骤 1: 更新实施状态文档**

在状态文档中添加第二阶段完成记录:

```markdown
### 第二阶段完成情况 (2026-04-16)

**前端 UI 优化:** ✅ 100%

**完成内容:**
1. ✅ 时间线融合 - 步骤卡片嵌入对话流
2. ✅ 动画系统 - framer-motion 集成
3. ✅ 状态反馈 - 加载、错误、成功状态优化
4. ✅ 组件优化 - 输入框、按钮、卡片样式
5. ✅ 骨架屏 - 加载占位动画

**新增文件:**
- components/animations/ (4个文件)
- components/execution/ (2个文件)
- components/feedback/ (3个文件)
- components/chat/ (1个文件)

**新增依赖:**
- framer-motion@11.x
- lucide-react@0.312.x
```

- [ ] **步骤 2: 提交文档更新**

```bash
git add docs/superpowers/status/implementation-status-2026-04-16.md
git commit -m "docs: 更新第二阶段实施状态"
```

---

## 总结

**实施计划完成!**

**关键改进:**
1. ✅ 时间线融合到对话流
2. ✅ 流畅的动画系统
3. ✅ 优化的状态反馈
4. ✅ 现代简约的视觉风格
5. ✅ Markdown 渲染支持
6. ✅ 任务打断功能

**预计工作量:** 12-17 小时  
**新增文件数:** 约 18 个  
**修改文件数:** 约 4 个  
**新增依赖:** 4 个 (framer-motion, lucide-react, react-markdown, remark-gfm)

---

## 阶段六: Markdown 渲染支持

### 任务 6.1: 创建 Markdown 渲染器组件

**文件:**
- 创建: `frontend/src/components/chat/MarkdownRenderer.tsx`

- [ ] **步骤 1: 创建 MarkdownRenderer 组件**

创建 `frontend/src/components/chat/MarkdownRenderer.tsx`:

```typescript
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
          // 代码块样式
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            return !inline && match ? (
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
          
          // 标题样式
          h1: ({ children }) => (
            <h1 className="text-2xl font-bold mt-6 mb-3">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xl font-semibold mt-5 mb-2">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-lg font-medium mt-4 mb-2">{children}</h3>
          ),
          
          // 列表样式
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>
          ),
          
          // 链接样式
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
          
          // 引用块样式
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-gray-300 pl-4 italic my-3 text-gray-600">
              {children}
            </blockquote>
          ),
          
          // 表格样式
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
```

- [ ] **步骤 2: 更新 chat 组件索引**

更新 `frontend/src/components/chat/index.ts`:

```typescript
export { ChatInput } from './ChatInput'
export { MarkdownRenderer } from './MarkdownRenderer'
```

- [ ] **步骤 3: 添加 prose 样式**

创建 `frontend/src/styles/markdown.css`:

```css
/* Markdown prose 样式 */
.prose {
  color: #374151;
  line-height: 1.7;
}

.prose p {
  margin-top: 1em;
  margin-bottom: 1em;
}

.prose strong {
  color: #111827;
  font-weight: 600;
}

.prose em {
  font-style: italic;
}

.prose hr {
  border-top: 1px solid #e5e7eb;
  margin-top: 1.5em;
  margin-bottom: 1.5em;
}
```

- [ ] **步骤 4: 提交代码**

```bash
git add frontend/src/components/chat/MarkdownRenderer.tsx frontend/src/components/chat/index.ts frontend/src/styles/markdown.css
git commit -m "feat: 创建 Markdown 渲染器组件"
```

---

### 任务 6.2: 集成 Markdown 到消息组件

**文件:**
- 修改: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **步骤 1: 导入 MarkdownRenderer**

在 `frontend/src/pages/AgentWorkspace.tsx` 中添加导入:

```typescript
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
```

- [ ] **步骤 2: 更新消息渲染**

在消息渲染部分,使用 MarkdownRenderer:

```typescript
{item.type === 'assistant-message' && (
  <SlideIn key={item.id} direction="up">
    <div className="mb-4">
      <div className="inline-block max-w-[80%] px-4 py-3 rounded-2xl border border-gray-200 bg-white text-gray-800 shadow-sm">
        <div className="mb-1 text-sm font-medium opacity-70">🤖 Agent</div>
        <MarkdownRenderer content={item.content || ''} />
      </div>
    </div>
  </SlideIn>
)}
```

- [ ] **步骤 3: 测试 Markdown 渲染**

测试以下内容:
- [ ] 代码块语法高亮
- [ ] 列表渲染
- [ ] 链接点击
- [ ] 表格显示
- [ ] 引用块样式

- [ ] **步骤 4: 提交代码**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: 集成 Markdown 渲染到消息组件"
```

---

## 阶段七: 任务打断功能

### 任务 7.1: 创建执行状态管理

**文件:**
- 创建: `frontend/src/stores/executionStore.ts`

- [ ] **步骤 1: 创建 executionStore**

创建 `frontend/src/stores/executionStore.ts`:

```typescript
import { create } from 'zustand'

export type ExecutionStatus = 'idle' | 'running' | 'paused' | 'stopped'

interface ExecutionState {
  status: ExecutionStatus
  executionId: string | null
  canPause: boolean
  canStop: boolean
  
  setStatus: (status: ExecutionStatus) => void
  setExecutionId: (id: string | null) => void
  setCanPause: (canPause: boolean) => void
  setCanStop: (canStop: boolean) => void
  
  startExecution: (id: string) => void
  pauseExecution: () => void
  resumeExecution: () => void
  stopExecution: () => void
  resetExecution: () => void
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  status: 'idle',
  executionId: null,
  canPause: false,
  canStop: false,
  
  setStatus: (status) => set({ status }),
  setExecutionId: (id) => set({ executionId: id }),
  setCanPause: (canPause) => set({ canPause }),
  setCanStop: (canStop) => set({ canStop }),
  
  startExecution: (id) => set({
    status: 'running',
    executionId: id,
    canPause: true,
    canStop: true
  }),
  
  pauseExecution: () => {
    const { status } = get()
    if (status === 'running') {
      set({ status: 'paused', canPause: false })
    }
  },
  
  resumeExecution: () => {
    const { status } = get()
    if (status === 'paused') {
      set({ status: 'running', canPause: true })
    }
  },
  
  stopExecution: () => set({
    status: 'stopped',
    canPause: false,
    canStop: false
  }),
  
  resetExecution: () => set({
    status: 'idle',
    executionId: null,
    canPause: false,
    canStop: false
  })
}))
```

- [ ] **步骤 2: 提交代码**

```bash
git add frontend/src/stores/executionStore.ts
git commit -m "feat: 创建执行状态管理 Store"
```

---

### 任务 7.2: 创建执行控制组件

**文件:**
- 创建: `frontend/src/components/execution/ExecutionControls.tsx`

- [ ] **步骤 1: 创建 ExecutionControls 组件**

创建 `frontend/src/components/execution/ExecutionControls.tsx`:

```typescript
import { motion } from 'framer-motion'
import { Pause, Play, Square } from 'lucide-react'
import { useExecutionStore } from '@/stores/executionStore'

interface ExecutionControlsProps {
  onPause?: () => void
  onResume?: () => void
  onStop?: () => void
}

export function ExecutionControls({ onPause, onResume, onStop }: ExecutionControlsProps) {
  const { status, canPause, canStop } = useExecutionStore()
  
  if (status === 'idle' || status === 'stopped') {
    return null
  }
  
  return (
    <motion.div
      className="flex items-center gap-2"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.2 }}
    >
      {status === 'running' && canPause && (
        <motion.button
          onClick={onPause}
          className="flex items-center gap-2 px-4 py-2 bg-yellow-500 text-white rounded-lg
                     hover:bg-yellow-600 shadow-lg shadow-yellow-500/30"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Pause className="w-4 h-4" />
          <span>暂停</span>
        </motion.button>
      )}
      
      {status === 'paused' && (
        <motion.button
          onClick={onResume}
          className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg
                     hover:bg-green-600 shadow-lg shadow-green-500/30"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Play className="w-4 h-4" />
          <span>继续</span>
        </motion.button>
      )}
      
      {canStop && (
        <motion.button
          onClick={onStop}
          className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg
                     hover:bg-red-600 shadow-lg shadow-red-500/30"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Square className="w-4 h-4" />
          <span>停止</span>
        </motion.button>
      )}
    </motion.div>
  )
}
```

- [ ] **步骤 2: 更新 execution 组件索引**

更新 `frontend/src/components/execution/index.ts`:

```typescript
export { StepCard } from './StepCard'
export { StatusBadge } from './StatusBadge'
export { ExecutionControls } from './ExecutionControls'
```

- [ ] **步骤 3: 提交代码**

```bash
git add frontend/src/components/execution/
git commit -m "feat: 创建执行控制组件"
```

---

### 任务 7.3: 实现打断 API 集成

**文件:**
- 修改: `frontend/src/services/apiClient.ts`
- 修改: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **步骤 1: 添加打断 API**

在 `frontend/src/services/apiClient.ts` 中添加:

```typescript
// Agent 执行控制 API
export const agentApi = {
  execute: (data: { project_id: string; task: string }) =>
    apiClient.post('/api/agent/execute', data),
  getStatus: (executionId: string) =>
    apiClient.get(`/api/agent/status/${executionId}`),
  getHistory: (projectId: string) =>
    apiClient.get(`/api/agent/history/${projectId}`),
  
  // 新增: 执行控制
  pause: (executionId: string) =>
    apiClient.post(`/api/agent/pause/${executionId}`),
  resume: (executionId: string) =>
    apiClient.post(`/api/agent/resume/${executionId}`),
  stop: (executionId: string) =>
    apiClient.post(`/api/agent/stop/${executionId}`),
}
```

- [ ] **步骤 2: 集成执行控制到 AgentWorkspace**

在 `frontend/src/pages/AgentWorkspace.tsx` 中:

```typescript
import { ExecutionControls } from '@/components/execution/ExecutionControls'
import { useExecutionStore } from '@/stores/executionStore'
import { agentApi } from '@/services/apiClient'

export default function AgentWorkspace() {
  // ... 现有代码 ...
  const { startExecution, pauseExecution, resumeExecution, stopExecution, resetExecution } = useExecutionStore()
  
  // 处理暂停
  const handlePause = async () => {
    if (!executionId) return
    try {
      await agentApi.pause(executionId)
      pauseExecution()
    } catch (error) {
      console.error('Failed to pause execution:', error)
    }
  }
  
  // 处理继续
  const handleResume = async () => {
    if (!executionId) return
    try {
      await agentApi.resume(executionId)
      resumeExecution()
    } catch (error) {
      console.error('Failed to resume execution:', error)
    }
  }
  
  // 处理停止
  const handleStop = async () => {
    if (!executionId) return
    try {
      await agentApi.stop(executionId)
      stopExecution()
      wsRef.current?.disconnect()
    } catch (error) {
      console.error('Failed to stop execution:', error)
    }
  }
  
  // 在 Header 中添加控制按钮
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            {currentProject ? currentProject.name : '选择项目开始'}
          </h2>
          {currentProject && (
            <p className="text-sm text-gray-500">{currentProject.path}</p>
          )}
        </div>
        <div className="flex items-center gap-4">
          <ExecutionControls
            onPause={handlePause}
            onResume={handleResume}
            onStop={handleStop}
          />
          {/* ... 其他 header 内容 ... */}
        </div>
      </div>
      {/* ... 其他内容 ... */}
    </div>
  )
}
```

- [ ] **步骤 3: 更新 WebSocket 事件处理**

在 WebSocket 事件中更新状态:

```typescript
ws.on('execution:start', (data) => {
  startExecution(data.executionId)
})

ws.on('execution:complete', (data) => {
  resetExecution()
})

ws.on('execution:error', (data) => {
  resetExecution()
})
```

- [ ] **步骤 4: 提交代码**

```bash
git add frontend/src/services/apiClient.ts frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: 实现任务打断功能 API 集成"
```

---

### 任务 7.4: 后端打断 API 实现 (可选)

**注意:** 这个任务需要在后端实现相应的 API 端点

**文件:**
- 修改: `backend/app/api/routes/agent.py`
- 修改: `backend/app/execution/rapid_loop.py`

- [ ] **步骤 1: 添加后端 API 端点**

在 `backend/app/api/routes/agent.py` 中添加:

```python
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/agent", tags=["agent"])

@router.post("/pause/{execution_id}")
async def pause_execution(execution_id: str):
    """暂停执行"""
    # TODO: 实现暂停逻辑
    pass

@router.post("/resume/{execution_id}")
async def resume_execution(execution_id: str):
    """恢复执行"""
    # TODO: 实现恢复逻辑
    pass

@router.post("/stop/{execution_id}")
async def stop_execution(execution_id: str):
    """停止执行"""
    # TODO: 实现停止逻辑
    pass
```

- [ ] **步骤 2: 实现执行循环中断机制**

在 `backend/app/execution/rapid_loop.py` 中:

```python
class RapidExecutionLoop:
    def __init__(self, ...):
        self._should_stop = False
        self._is_paused = False
    
    def stop(self):
        """停止执行"""
        self._should_stop = True
    
    def pause(self):
        """暂停执行"""
        self._is_paused = True
    
    def resume(self):
        """恢复执行"""
        self._is_paused = False
    
    async def run(self, ...):
        for step_num in range(1, self.max_steps + 1):
            # 检查是否应该停止
            if self._should_stop:
                execution.status = ExecutionStatus.STOPPED
                break
            
            # 检查是否暂停
            while self._is_paused:
                await asyncio.sleep(0.1)
            
            # 正常执行步骤...
```

- [ ] **步骤 3: 提交代码**

```bash
git add backend/app/api/routes/agent.py backend/app/execution/rapid_loop.py
git commit -m "feat: 实现后端任务打断 API"
```

---

## 阶段八: 最终集成和测试

### 任务 8.1: 全面测试

- [ ] **步骤 1: 测试 Markdown 渲染**

测试项:
- [ ] 普通文本显示
- [ ] 代码块语法高亮
- [ ] 列表渲染 (有序/无序)
- [ ] 链接点击
- [ ] 表格显示
- [ ] 引用块样式
- [ ] 标题层级

- [ ] **步骤 2: 测试任务打断**

测试项:
- [ ] 暂停按钮显示
- [ ] 暂停功能正常
- [ ] 继续功能正常
- [ ] 停止功能正常
- [ ] 状态正确更新

- [ ] **步骤 3: 性能测试**

```bash
# 构建生产版本
cd frontend
npm run build

# 检查包大小
ls -lh dist/assets/
```

预期:
- framer-motion 相关 < 100KB
- react-markdown 相关 < 50KB
- 总增量 < 200KB

- [ ] **步骤 4: 提交最终版本**

```bash
git add .
git commit -m "feat: 完成前端 UI 第二阶段优化 - 最终版本

新增功能:
- Markdown 渲染支持 (react-markdown + remark-gfm)
- 任务打断功能 (暂停/继续/停止)
- 执行状态管理 Store
- 执行控制组件
- 代码块语法高亮
- 表格、列表、引用块样式

组件新增:
- MarkdownRenderer 组件
- ExecutionControls 组件
- executionStore 状态管理

依赖新增:
- react-markdown@9.x
- remark-gfm@4.x"
```

---

### 任务 8.2: 更新文档

**文件:**
- 更新: `docs/superpowers/status/implementation-status-2026-04-16.md`

- [ ] **步骤 1: 更新实施状态文档**

```markdown
### 第二阶段完成情况 (2026-04-16)

**前端 UI 优化:** ✅ 100%

**完成内容:**
1. ✅ 时间线融合 - 步骤卡片嵌入对话流
2. ✅ 动画系统 - framer-motion 集成
3. ✅ 状态反馈 - 加载、错误、成功状态优化
4. ✅ 组件优化 - 输入框、按钮、卡片样式
5. ✅ 骨架屏 - 加载占位动画
6. ✅ Markdown 渲染 - 代码高亮、表格、列表
7. ✅ 任务打断 - 暂停/继续/停止功能

**新增文件:**
- components/animations/ (4个文件)
- components/execution/ (3个文件)
- components/feedback/ (3个文件)
- components/chat/ (2个文件)
- stores/ (2个文件)

**新增依赖:**
- framer-motion@11.x
- lucide-react@0.312.x
- react-markdown@9.x
- remark-gfm@4.x
```

- [ ] **步骤 2: 提交文档更新**

```bash
git add docs/superpowers/status/implementation-status-2026-04-16.md
git commit -m "docs: 更新第二阶段实施状态 - 最终版本"
```

---

## 总结

**实施计划完成!**

**关键改进:**
1. ✅ 时间线融合到对话流
2. ✅ 流畅的动画系统
3. ✅ 优化的状态反馈
4. ✅ 现代简约的视觉风格
5. ✅ Markdown 渲染支持
6. ✅ 任务打断功能

**预计工作量:** 12-17 小时  
**新增文件数:** 约 18 个  
**修改文件数:** 约 4 个  
**新增依赖:** 4 个 (framer-motion, lucide-react, react-markdown, remark-gfm)

**下一步:**
1. 使用 subagent-driven-development 执行计划
2. 或使用 executing-plans 在当前会话中执行

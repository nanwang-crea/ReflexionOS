// 文件功能：为“当前会话”整体视图组装视图模型（ViewModel）
// 文件描述：聚合会话基础数据、供应商/模型选择、加载更多历史消息、编辑消息重跑、重新生成回复等交互逻辑，
// 统一输出 header/transcript/input 三块 UI 所需的 props，避免顶层组件直接耦合多个 store 和业务规则
// 核心逻辑：组合 useSessionData 和 useSessionSelection 两个子 hook 获取基础状态，
// 再用 useCallback 包装“加载更多”“编辑消息”“重新生成”等交互回调，最终拼装成三组 props 返回
import { useCallback, useRef, useState } from 'react'
import { nativeDialogService } from '@/services/dialogService'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import type { ConversationMessage } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'
import type { Plan } from '@/types/conversation'
import type { ToolApprovalActionHandler } from '@/components/workspace/ToolTraceCard'
import { getRuntimeStatusDescriptor } from '@/components/workspace/runtimeStatus'
import { useSessionData } from './useSessionData'
import { useSessionSelection } from './useSessionSelection'

const REGENERATE_CONFIRM_MESSAGE = '重新生成回复？此消息之后的对话内容将被清除，AI 将基于当前上下文重新生成回复。'

// 函数名：useCurrentSessionViewModel
// 入参：
//   - options.messages (ConversationMessage[]): 当前会话的消息列表
//   - options.isRunning (boolean): 当前是否有运行中的对话轮次
//   - options.isCancelling (boolean): 当前是否正在取消运行
//   - options.connectionStatus ('connected'|'connecting'|'disconnected'): WebSocket 连接状态
//   - options.retryInfo (LlmRetryDto | null): LLM 重试信息，用于展示运行时状态
//   - options.plan (Plan | null): 当前会话关联的计划
//   - options.hasMore (boolean, 可选): 是否还有更早的历史消息可加载
//   - options.onLoadMore (function, 可选): 加载更早消息的回调，接收游标 turnId
//   - options.onReset (function): 重置/新建会话的回调
//   - options.onApprovalAction (ToolApprovalActionHandler, 可选): 工具调用审批操作的处理函数
//   - options.editAndRerun (function, 可选): 编辑消息并基于新内容重新发起对话的回调
// 功能：组装当前会话视图所需的全部状态与交互回调，输出给 header/transcript/input 三个子区域使用
// 运行逻辑：
//   1. 从 settingsStore 读取 configured/loaded；从 useSessionData 读取当前项目和当前会话摘要
//   2. 用 useSessionSelection 解析当前应使用的供应商/模型（以会话已保存的偏好作为初始倾向）
//   3. 用 isLoadingMoreRef + isLoadingMore 状态防止“加载更多”重复触发，
//      handleLoadMore 内部用 try/finally 保证加载完成后正确复位标记
//   4. handleEditMessage：校验当前有会话后，带上当前选择的供应商/模型调用 editAndRerun
//   5. handleRegenerateMessage：先弹出二次确认对话框，确认后以 newContent: null 的方式调用
//      editAndRerun，表示“重新生成”而非“编辑内容”
//   6. 用 getRuntimeStatusDescriptor 根据运行状态/重试信息/消息列表计算运行时状态描述
//   7. 最终返回 currentProject/currentSession/configured 等基础字段，以及 headerProps、
//      transcriptProps、inputProps 三组供 UI 直接展开使用的 props 对象
// 出参：{ currentProject, currentSession, configured, loaded, selection, availableProviders,
//   selectedModels, headerProps, transcriptProps, inputProps } - 当前会话视图的完整视图模型
export function useCurrentSessionViewModel(options: {
  messages: ConversationMessage[]
  isRunning: boolean
  isCancelling: boolean
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
  retryInfo: LlmRetryDto | null
  plan: Plan | null
  hasMore?: boolean
  onLoadMore?: (beforeTurnId: string) => void
  onReset: () => void | Promise<void>
  onApprovalAction?: ToolApprovalActionHandler
  editAndRerun?: (payload: {
    messageId: string
    newContent?: string | null
    providerId?: string | null
    modelId?: string | null
  }) => void
}) {
  const { configured, loaded } = useSettingsStore()
  const {
    currentProject,
    currentSessionSummary,
  } = useSessionData()
  const {
    selection,
    availableProviders,
    selectedModels,
    handleProviderChange,
    handleModelChange,
  } = useSessionSelection({
    preferredProviderId: currentSessionSummary?.preferredProviderId,
    preferredModelId: currentSessionSummary?.preferredModelId,
  })

  const isLoadingMoreRef = useRef(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  const handleLoadMore = useCallback(async (beforeTurnId: string) => {
    if (isLoadingMoreRef.current || !options.hasMore) return
    isLoadingMoreRef.current = true
    setIsLoadingMore(true)
    try {
      await options.onLoadMore?.(beforeTurnId)
    } finally {
      isLoadingMoreRef.current = false
      setIsLoadingMore(false)
    }
  }, [options])

  const handleEditMessage = useCallback((messageId: string, newContent: string) => {
    if (!currentSessionSummary) return
    options.editAndRerun?.({
      messageId,
      newContent,
      providerId: selection.providerId,
      modelId: selection.modelId,
    })
  }, [currentSessionSummary, options, selection.providerId, selection.modelId])

  const handleRegenerateMessage = useCallback(async (messageId: string) => {
    if (!currentSessionSummary) return
    const confirmed = await nativeDialogService.confirmAction(REGENERATE_CONFIRM_MESSAGE, { variant: 'danger' })
    if (!confirmed) return
    options.editAndRerun?.({
      messageId,
      newContent: null,
      providerId: selection.providerId,
      modelId: selection.modelId,
    })
  }, [currentSessionSummary, options, selection.providerId, selection.modelId])

  const runtimeStatus = getRuntimeStatusDescriptor({
    isRunning: options.isRunning,
    retryInfo: options.retryInfo,
    messages: options.messages,
  })

  return {
    currentProject,
    currentSession: currentSessionSummary,
    configured,
    loaded,
    selection,
    availableProviders,
    selectedModels,
    headerProps: {
      title: currentSessionSummary?.title || (currentProject ? currentProject.name : '选择项目开始'),
      projectPath: currentProject?.path,
      connectionStatus: options.connectionStatus,
      onReset: options.onReset,
    },
    transcriptProps: {
      loaded,
      configured,
      currentProject,
      currentSession: currentSessionSummary,
      messages: options.messages,
      isRunning: options.isRunning,
      retryInfo: options.retryInfo,
      plan: options.plan,
      runtimeStatus,
      onApprovalAction: options.onApprovalAction,
      onEditMessage: handleEditMessage,
      onRegenerateMessage: handleRegenerateMessage,
      hasMore: options.hasMore,
      isLoadingMore,
      onLoadMore: handleLoadMore,
    },
    inputProps: {
      disabled: !loaded || !configured || !currentProject || options.isRunning || options.isCancelling,
      isLoading: options.isRunning || options.isCancelling,
      canCancel: options.isRunning && !options.isCancelling,
      isCancelling: options.isCancelling,
      placeholder: currentProject ? '给当前项目开一个新任务...' : '请先选择项目',
      providerOptions: availableProviders.map((provider) => ({ id: provider.id, label: provider.name })),
      modelOptions: selectedModels.map((model) => ({ id: model.id, label: model.display_name })),
      selectedProviderId: selection.providerId,
      selectedModelId: selection.modelId,
      onProviderChange: handleProviderChange,
      onModelChange: handleModelChange,
      selectionDisabled: !loaded || options.isRunning || options.isCancelling || availableProviders.length === 0,
      runtimeStatusLabel: runtimeStatus.kind === 'idle' ? null : runtimeStatus.label,
    },
  }
}

// 文件功能：封装“发送消息”这一复合操作，包含前置校验、必要时创建新会话、写入会话偏好、发起对话轮次
// 文件描述：createSendMessage 是纯函数版本，通过依赖注入方式接收所有外部依赖，便于单测；
// useSendMessage 是面向组件的 hook 版本，自动装配好这些依赖并返回稳定的 sendMessage 回调
// 核心逻辑：发送前依次校验“是否有内容”“是否已选项目”“是否已完成配置”“是否已选供应商和模型”；
// 若当前会话不属于当前项目（或没有当前会话）则先创建新会话，否则复用当前会话并同步写入供应商/模型偏好；
// 最终调用 startTurn 发起真正的对话请求，异常时通过 notify 提示用户
import { useCallback } from 'react'
import { writeSessionPreferences as writeSessionPreferencesAction } from '@/features/sessions/session.actions'
import { nativeDialogService } from '@/services/dialogService'
import { useProjectStore } from '@/features/projects/stores/project.store'
import type { SessionSummary } from '@/types/workspace'
import { useSessionActions } from '@/features/sessions/hooks/useSessionActions'

interface SelectionState {
  providerId: string | null
  modelId: string | null
}

interface SendMessageDependencies {
  currentProject: { id: string; name?: string; path?: string } | null
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  createSession: (
    projectId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<SessionSummary>
  writeSessionPreferences: (
    sessionId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<unknown>
  startTurn: (payload: {
    sessionId: string
    message: string
    providerId: string
    modelId: string
    attachmentIds?: string[]
  }) => Promise<void> | void
  notify: (message: string) => void
}

// 函数名：createSendMessage
// 入参：
//   - dependencies (SendMessageDependencies): 发送消息所需的全部外部依赖（当前项目/会话、选择状态、
//     创建会话、写入偏好、发起对话轮次、错误提示等函数），以依赖注入方式传入便于测试
// 功能：返回一个 sendMessage 异步函数，完成发送消息的完整业务流程
// 运行逻辑：
//   1. 消息为空且无附件时直接返回，不发送
//   2. 依次校验：是否已选项目 -> 是否已完成基础配置 -> 是否已选供应商和模型；任一不满足则提示并返回
//   3. 判断是否需要新建会话：当前无会话，或当前会话不属于当前项目时，调用 createSession 新建；
//      否则复用当前会话
//   4. 复用现有会话时，先调用 writeSessionPreferences 把当前选择的供应商/模型写回会话偏好
//   5. 调用 startTurn 发起对话轮次，传入目标会话、消息内容、供应商、模型、附件 ID 列表
//   6. 捕获异常并通过 notify 提示错误信息
// 出参：(message: string, attachmentIds?: string[]) => Promise<void> - 可直接调用的发送消息函数
export function createSendMessage(dependencies: SendMessageDependencies) {
  return async function sendMessage(message: string, attachmentIds?: string[]) {
    if (!message.trim() && (!attachmentIds || attachmentIds.length === 0)) {
      return
    }

    if (!dependencies.currentProject) {
      dependencies.notify('请先选择一个项目')
      return
    }

    if (!dependencies.configured) {
      dependencies.notify('请先在设置页面配置供应商、模型和默认项')
      return
    }

    if (!dependencies.selection.providerId || !dependencies.selection.modelId) {
      dependencies.notify('请先选择要使用的供应商和模型')
      return
    }

    try {
      const requiresFreshSession = (
        !dependencies.currentSession ||
        dependencies.currentSession.projectId !== dependencies.currentProject.id
      )
      let targetSession: SessionSummary

      if (requiresFreshSession) {
        targetSession = await dependencies.createSession(dependencies.currentProject.id, {
          preferredProviderId: dependencies.selection.providerId,
          preferredModelId: dependencies.selection.modelId,
        })
      } else {
        if (!dependencies.currentSession) {
          return
        }

        targetSession = dependencies.currentSession
      }

      if (!requiresFreshSession) {
        await dependencies.writeSessionPreferences(targetSession.id, {
          preferredProviderId: dependencies.selection.providerId,
          preferredModelId: dependencies.selection.modelId,
        })
      }

      await dependencies.startTurn({
        sessionId: targetSession.id,
        message,
        providerId: dependencies.selection.providerId,
        modelId: dependencies.selection.modelId,
        attachmentIds,
      })
    } catch (error) {
      console.error('Failed to send message:', error)
      const errorMessage = error instanceof Error ? error.message : '发送消息失败'
      dependencies.notify(errorMessage)
    }
  }
}

// 函数名：useSendMessage
// 入参：
//   - options.currentSession (SessionSummary | null): 当前会话摘要
//   - options.configured (boolean): 应用基础配置（供应商/模型/默认项）是否已完成
//   - options.selection (SelectionState): 当前选中的供应商/模型
//   - options.startTurn (function): 发起对话轮次的方法，由调用方（通常是运行时 hook）提供
// 功能：为组件提供一个稳定的 sendMessage 回调，内部自动装配好项目、会话创建、写偏好、错误提示等依赖
// 运行逻辑：
//   1. 从 projectStore 读取当前项目，从 useSessionActions 读取 createSession 方法
//   2. 用 useCallback 包装 sendMessage：每次调用时用最新的 options 和依赖组装出
//      SendMessageDependencies，再交给 createSendMessage 生成的函数执行
//   3. 依赖数组包含 currentProject 及 options 中各字段，保证依赖变化时回调引用及时更新
// 出参：{ sendMessage } - 可直接绑定到发送按钮/输入框提交事件的异步函数
export function useSendMessage(options: {
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  startTurn: SendMessageDependencies['startTurn']
}) {
  const { currentProject } = useProjectStore()
  const { createSession } = useSessionActions()

  const sendMessage = useCallback(async (message: string, attachmentIds?: string[]) => {
    const sendFn = createSendMessage({
      currentProject,
      currentSession: options.currentSession,
      configured: options.configured,
      selection: options.selection,
      createSession,
      writeSessionPreferences: writeSessionPreferencesAction,
      startTurn: options.startTurn,
      notify: nativeDialogService.notifyError,
    })
    await sendFn(message, attachmentIds)
  }, [currentProject, options.currentSession, options.configured, options.selection, createSession, options.startTurn])

  return {
    sendMessage,
  }
}

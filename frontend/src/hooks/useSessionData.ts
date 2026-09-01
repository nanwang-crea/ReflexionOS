// 文件功能：聚合当前项目/当前会话的基础数据，并处理会话失效时的兜底逻辑
// 文件描述：负责在应用启动时加载 LLM 设置，并在当前选中的会话已不存在于当前项目会话列表中时
// （例如会话被删除或切换了项目）自动清空 currentSessionId，避免 UI 停留在无效会话上
// 核心逻辑：从 project/session/workspace 等多个 store 中读取数据，用 useMemo 派生出当前会话摘要，
// 用两个独立 useEffect 分别处理“加载 LLM 设置”和“清理失效会话 ID”两件事
import { useEffect, useMemo } from 'react'
import { ensureLLMSettingsLoaded } from '@/features/llm/llmSettings.loader'
import { useSessionStore } from '@/features/sessions/stores/session.store'
import { useProjectStore } from '@/features/projects/stores/project.store'
import { useToastStore } from '@/shared/stores/toast.store'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'
import type { SessionSummary } from '@/types/workspace'

const EMPTY_SESSIONS: SessionSummary[] = []

// 函数名：findCurrentSessionSummary
// 入参：
//   - projectSessions (SessionSummary[]): 当前项目下的会话摘要列表
//   - currentSessionId (string | null): 当前选中的会话 ID
// 功能：根据会话 ID 在会话列表中查找对应的会话摘要
// 运行逻辑：currentSessionId 为空时直接返回 null；否则在 projectSessions 中按 id 匹配查找
// 出参：SessionSummary | null - 匹配到的会话摘要，未匹配到则为 null
export function findCurrentSessionSummary(
  projectSessions: SessionSummary[],
  currentSessionId: string | null
) {
  if (!currentSessionId) {
    return null
  }

  return projectSessions.find((session) => session.id === currentSessionId) || null
}

// 函数名：shouldClearStaleCurrentSessionId
// 入参：
//   - options.currentSessionId (string | null): 当前选中的会话 ID
//   - options.currentSessionSummary (SessionSummary | null): 该会话 ID 对应的会话摘要（若存在）
//   - options.hasLoadedProjectSessions (boolean): 当前项目的会话列表是否已经加载完成
// 功能：判断是否需要清空当前会话 ID（即会话已失效）
// 运行逻辑：只有当“存在 currentSessionId”且“项目会话列表已加载完成”但“找不到对应摘要”时，
// 才认为该会话已失效，需要清空；会话列表尚未加载完成时不做判断，避免误判
// 出参：boolean - true 表示应清空 currentSessionId
export function shouldClearStaleCurrentSessionId(options: {
  currentSessionId: string | null
  currentSessionSummary: SessionSummary | null
  hasLoadedProjectSessions: boolean
}) {
  return Boolean(
    options.currentSessionId &&
    options.hasLoadedProjectSessions &&
    !options.currentSessionSummary
  )
}

interface UseSessionDataResult {
  currentProject: ReturnType<typeof useProjectStore.getState>['currentProject']
  currentSessionId: string | null
  currentSessionSummary: SessionSummary | null
}

// 函数名：useSessionData
// 入参：无
// 功能：为顶层视图提供当前项目、当前会话 ID、当前会话摘要，并在后台完成 LLM 设置加载与失效会话清理
// 运行逻辑：
//   1. 从 projectStore/workspaceStore/sessionStore 中读取当前项目、当前会话 ID、项目会话列表
//   2. 用 useMemo 计算 currentSessionSummary（依赖 findCurrentSessionSummary）
//   3. 首次挂载时触发 ensureLLMSettingsLoaded，加载失败则弹出警告提示
//   4. 监听 currentSessionId/currentSessionSummary/hasLoadedProjectSessions 变化，
//      若判定会话已失效（shouldClearStaleCurrentSessionId 为 true）则调用 setCurrentSessionId(null)
// 出参：UseSessionDataResult - { currentProject, currentSessionId, currentSessionSummary }
export function useSessionData(): UseSessionDataResult {
  const { currentProject } = useProjectStore()
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const setCurrentSessionId = useWorkspaceStore((state) => state.setCurrentSessionId)
  const sessionsByProjectId = useSessionStore((state) => state.sessionsByProjectId)

  const projectSessions = currentProject ? sessionsByProjectId[currentProject.id] || EMPTY_SESSIONS : EMPTY_SESSIONS
  const hasLoadedProjectSessions = currentProject
    ? Object.prototype.hasOwnProperty.call(sessionsByProjectId, currentProject.id)
    : false
  const currentSessionSummary = useMemo(
    () => findCurrentSessionSummary(projectSessions, currentSessionId),
    [currentSessionId, projectSessions]
  )

  useEffect(() => {
    ensureLLMSettingsLoaded().catch((error) => {
      console.error('Failed to load LLM settings:', error)
      useToastStore.getState().addToast('warning', '加载 LLM 设置失败')
    })
  }, [])

  useEffect(() => {
    if (!currentSessionId) {
      return
    }

    if (shouldClearStaleCurrentSessionId({
      currentSessionId,
      currentSessionSummary,
      hasLoadedProjectSessions,
    })) {
      setCurrentSessionId(null)
      return
    }

    if (!currentSessionSummary) {
      return
    }
  }, [currentSessionId, currentSessionSummary, hasLoadedProjectSessions, setCurrentSessionId])

  return {
    currentProject,
    currentSessionId,
    currentSessionSummary,
  }
}

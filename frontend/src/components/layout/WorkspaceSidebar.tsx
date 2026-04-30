import { useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useSessionStore } from '@/features/sessions/sessionStore'
import {
  ChevronDown,
  ChevronRight,
  Folder,
  FolderPlus,
  Pencil,
  Puzzle,
  Search,
  Settings,
  Sparkles,
  SquarePen,
  Trash2,
  Workflow
} from 'lucide-react'
import { ensureProjectsLoaded } from '@/features/projects/projectLoader'
import { isElectronRuntime } from '@/services/desktopClient'
import { useConversationStore } from '@/features/conversation/conversationStore'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { SessionSummary } from '@/types/workspace'
import type { Project } from '@/types/project'
import { isConversationBusy } from './sidebarBusy'
import { useSidebarFilteredProjects } from './useSidebarFilteredProjects'
import { useSidebarProjectActions } from './useSidebarProjectActions'
import { useSidebarSessionActions } from './useSidebarSessionActions'

const sidebarEntryClassName = 'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[15px] text-slate-700 transition hover:bg-slate-200/60'

function formatRelativeTime(dateString: string) {
  const timestamp = new Date(dateString).getTime()
  const diff = Date.now() - timestamp

  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  const week = 7 * day

  if (diff < hour) {
    const value = Math.max(1, Math.floor(diff / minute))
    return `${value} 分钟`
  }

  if (diff < day) {
    return `${Math.max(1, Math.floor(diff / hour))} 小时`
  }

  if (diff < week) {
    return `${Math.max(1, Math.floor(diff / day))} 天`
  }

  return `${Math.max(1, Math.floor(diff / week))} 周`
}

function deriveProjectSelection(
  projects: Project[],
  currentProject: Project | null,
  currentSessionProjectId: string | null
) {
  if (currentSessionProjectId) {
    return projects.find(project => project.id === currentSessionProjectId) || null
  }

  if (currentProject) {
    return projects.find(project => project.id === currentProject.id) || null
  }

  return projects[0] || null
}

export function WorkspaceSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const {
    projects,
    currentProject,
    addProject,
    removeProject,
    setCurrentProject,
    loading
  } = useProjectStore()
  const { defaultProviderId, defaultModelId } = useSettingsStore()
  const {
    currentSessionId,
    expandedProjectIds,
    expandedSessionProjectIds,
    searchOpen,
    searchQuery,
    setCurrentSessionId,
    toggleProjectExpanded,
    setProjectExpanded,
    toggleProjectShowAll,
    setSearchOpen,
    setSearchQuery,
  } = useWorkspaceStore()
  const currentConversation = useConversationStore((state) => (
    currentSessionId ? state.conversationsBySessionId[currentSessionId] : undefined
  ))
  const sessionsByProjectId = useSessionStore((state) => state.sessionsByProjectId)

  const [showProjectModal, setShowProjectModal] = useState(false)
  const [formData, setFormData] = useState({ name: '', path: '', language: 'python' })
  const canSelectDirectory = isElectronRuntime()

  const busy = isConversationBusy(currentConversation)
  const projectSessionsById = sessionsByProjectId
  const sessions = useMemo(
    () => Object.values(projectSessionsById).flat(),
    [projectSessionsById]
  )
  const currentSession = useMemo(
    () => sessions.find(session => session.id === currentSessionId) || null,
    [currentSessionId, sessions]
  )

  useEffect(() => {
    ensureProjectsLoaded().catch((error) => {
      console.error('Failed to load projects:', error)
    })
  }, [])

  useEffect(() => {
    if (projects.length === 0) {
      return
    }

    const nextProject = deriveProjectSelection(
      projects,
      currentProject,
      currentSession?.projectId || null
    )

    if (nextProject && nextProject.id !== currentProject?.id) {
      setCurrentProject(nextProject)
    }
  }, [currentProject, currentSession?.projectId, projects, setCurrentProject])

  const filteredProjects = useSidebarFilteredProjects({
    projects,
    projectSessionsById,
    searchQuery,
  })

  const {
    handleCreateProject,
    handleDeleteProject,
    handleSelectDirectory,
  } = useSidebarProjectActions({
    busy,
    currentProject,
    addProject,
    removeProject,
    setCurrentProject,
    setProjectExpanded,
    setShowProjectModal,
    setFormData,
    navigate,
  })

  const {
    handleCreateSession,
    handleRenameSession,
    handleDeleteSession,
  } = useSidebarSessionActions({
    busy,
    projects,
    currentProject,
    currentSessionId,
    defaultProviderId,
    defaultModelId,
    setCurrentProject,
    setProjectExpanded,
    setCurrentSessionId,
    setShowProjectModal,
    navigate,
  })

  const handleProjectSelect = (project: Project, projectSessions: SessionSummary[]) => {
    if (busy) {
      return
    }

    setCurrentProject(project)
    setProjectExpanded(project.id, true)

    if (!currentSession || currentSession.projectId !== project.id) {
      setCurrentSessionId(projectSessions[0]?.id || null)
    }

    navigate('/agent')
  }

  const handleSessionSelect = (project: Project, sessionId: string) => {
    if (busy) {
      return
    }

    setCurrentProject(project)
    setProjectExpanded(project.id, true)
    setCurrentSessionId(sessionId)
    navigate('/agent')
  }

  const globalEntries = [
    {
      key: 'new-chat',
      label: '新建聊天',
      icon: SquarePen,
      onClick: handleCreateSession,
      disabled: false,
      path: null
    },
    {
      key: 'search',
      label: '搜索',
      icon: Search,
      onClick: () => setSearchOpen(!searchOpen),
      disabled: false,
      path: null
    },
    {
      key: 'skills',
      label: '技能',
      icon: Sparkles,
      onClick: () => navigate('/skills'),
      disabled: false,
      path: '/skills'
    },
    {
      key: 'plugins',
      label: '插件',
      icon: Puzzle,
      onClick: () => navigate('/plugins'),
      disabled: false,
      path: '/plugins'
    },
    {
      key: 'automation',
      label: '自动化',
      icon: Workflow,
      onClick: () => navigate('/automation'),
      disabled: false,
      path: '/automation'
    }
  ]

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col border-r border-slate-200 bg-slate-100/80">
      <div className="flex-1 overflow-y-auto px-4 pb-4 pt-5">
        <div className="space-y-1">
          {globalEntries.map((entry) => {
            const Icon = entry.icon
            const disabled = entry.disabled || busy
            const active = entry.path ? location.pathname.startsWith(entry.path) : false

            return (
              <button
                key={entry.key}
                type="button"
                onClick={entry.onClick}
                disabled={disabled}
                className={`${sidebarEntryClassName} ${
                  active ? 'bg-slate-200 text-slate-900' : ''
                } ${
                  disabled ? 'cursor-default opacity-45 hover:bg-transparent' : ''
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="font-medium">{entry.label}</span>
              </button>
            )
          })}
        </div>

        {searchOpen && (
          <div className="mt-4">
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="搜索项目或聊天..."
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-slate-300"
            />
          </div>
        )}

        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between px-2 text-sm text-slate-400">
            <span className="font-medium">聊天</span>
            <div className="flex items-center gap-1">
                 <button
                 type="button"
                 onClick={handleCreateSession}
                disabled={busy}
                className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-200 hover:text-slate-600 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent"
                title="新建聊天"
              >
                <SquarePen className="h-4 w-4" />
              </button>
                               <button
                                 type="button"
                onClick={() => setShowProjectModal(true)}
                disabled={busy}
                className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-200 hover:text-slate-600 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent"
                title="新建项目"
              >
                <FolderPlus className="h-4 w-4" />
              </button>
            </div>
          </div>

          {loading ? (
            <div className="px-2 py-3 text-sm text-slate-400">加载项目中...</div>
          ) : filteredProjects.length === 0 ? (
            <div className="px-2 py-3 text-sm text-slate-400">暂无项目</div>
          ) : (
            <div className="space-y-4">
              {filteredProjects.map(({ project, sessions: projectSessions }) => {
                const searching = searchQuery.trim().length > 0
                const expanded = searching || expandedProjectIds.includes(project.id)
                const showAllSessions = expandedSessionProjectIds.includes(project.id)
                const visibleSessions = searching || showAllSessions
                  ? projectSessions
                  : projectSessions.slice(0, 5)
                const isCurrentProject = currentProject?.id === project.id

                return (
                  <div key={project.id}>
                    <div
                      className={`group flex items-center gap-1 rounded-xl px-2 py-1.5 text-[15px] transition ${
                        busy ? 'opacity-75' : 'hover:bg-slate-200/70'
                      } ${isCurrentProject ? 'text-slate-900' : 'text-slate-600'}`}
                    >
                               <button
                        type="button"
                        onClick={() => {
                          if (!busy) {
                            toggleProjectExpanded(project.id)
                          }
                        }}
                        className="rounded p-0.5 text-slate-400 hover:bg-slate-200"
                      >
                        {expanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleProjectSelect(project, projectSessions)}
                        disabled={busy}
                        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-0.5 text-left"
                      >
                        <Folder className="h-5 w-5 shrink-0 text-slate-500" />
                        <span className="truncate text-[17px]">{project.name}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteProject(project)}
                        disabled={busy}
                        className="rounded-lg p-1 text-slate-400 opacity-0 transition hover:bg-slate-200 hover:text-red-500 group-hover:opacity-100 disabled:cursor-default disabled:opacity-0"
                        title="删除项目"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                    {expanded && (
                      <div className="mt-2 space-y-1 pl-10">
                        {projectSessions.length === 0 ? (
                          <div className="px-2 py-2 text-sm text-slate-400">暂无聊天</div>
                        ) : (
                          <>
                            {visibleSessions.map((session) => {
                              const active = currentSessionId === session.id && currentProject?.id === project.id

                              return (
                                <div
                                  key={session.id}
                                  className={`group flex items-center gap-2 rounded-2xl px-4 py-2.5 text-[15px] transition ${
                                    active
                                      ? 'bg-slate-200 text-slate-900'
                                      : 'text-slate-600 hover:bg-slate-200/70'
                                  } ${busy ? 'opacity-75' : ''}`}
                                >
                                  <button
                                    type="button"
                                    onClick={() => handleSessionSelect(project, session.id)}
                                    disabled={busy}
                                    className="flex min-w-0 flex-1 items-center justify-between gap-3 text-left"
                                  >
                                    <span className="truncate">{session.title}</span>
                                    <span className="shrink-0 text-slate-400">
                                      {formatRelativeTime(session.updatedAt)}
                                    </span>
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleRenameSession(session)}
                                    disabled={busy}
                                    className="rounded-lg p-1 text-slate-400 opacity-0 transition hover:bg-slate-300/70 hover:text-slate-600 group-hover:opacity-100 disabled:cursor-default disabled:opacity-0"
                                    title="重命名聊天"
                                  >
                                    <Pencil className="h-4 w-4" />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleDeleteSession(session)}
                                    disabled={busy}
                                    className="rounded-lg p-1 text-slate-400 opacity-0 transition hover:bg-slate-300/70 hover:text-red-500 group-hover:opacity-100 disabled:cursor-default disabled:opacity-0"
                                    title="删除聊天"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </button>
                                </div>
                              )
                            })}

                            {projectSessions.length > 5 && (
                              <button
                                type="button"
                                onClick={() => toggleProjectShowAll(project.id)}
                                className="px-4 py-2 text-left text-sm text-slate-400 transition hover:text-slate-600"
                              >
                                {showAllSessions ? '收起显示' : '展开显示'}
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-slate-200 p-4">
        <NavLink
          to="/settings"
          className={({ isActive }) => `${sidebarEntryClassName} ${
            isActive ? 'bg-slate-200 text-slate-900' : ''
          }`}
        >
          <Settings className="h-5 w-5" />
          <span className="font-medium">设置</span>
        </NavLink>
      </div>

      {showProjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-slate-900">新建项目</h3>
            <div className="mt-5 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-600">项目名称</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(event) => setFormData({ ...formData, name: event.target.value })}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-700 outline-none transition focus:border-slate-300"
                  placeholder="ReflexionOS"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-600">项目路径</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={formData.path}
                    onChange={(event) => setFormData({ ...formData, path: event.target.value })}
                    className="w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-700 outline-none transition focus:border-slate-300"
                    placeholder="/path/to/project"
                  />
                  {canSelectDirectory && (
                     <button
                      type="button"
                      onClick={handleSelectDirectory}
                      disabled={busy}
                      className="shrink-0 rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
                    >
                      选择目录
                    </button>
                  )}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-600">主要语言</label>
                <select
                  value={formData.language}
                  onChange={(event) => setFormData({ ...formData, language: event.target.value })}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-slate-700 outline-none transition focus:border-slate-300"
                >
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                  <option value="typescript">TypeScript</option>
                  <option value="rust">Rust</option>
                  <option value="go">Go</option>
                  <option value="java">Java</option>
                </select>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowProjectModal(false)}
                className="rounded-xl px-4 py-2 text-slate-600 transition hover:bg-slate-100"
              >
                取消
              </button>
               <button
                 type="button"
                 onClick={() => handleCreateProject(formData)}
                className="rounded-xl bg-slate-900 px-4 py-2 text-white transition hover:bg-slate-800"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

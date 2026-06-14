import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useSessionStore } from '@/features/sessions/stores/session.store'
import {
  ChevronDown,
  ChevronRight,
  Folder,
  FolderPlus,
  Monitor,
  Moon,
  PanelLeftClose,
  Pencil,
  Puzzle,
  Search,
  Settings,
  Sparkles,
  SquarePen,
  Sun,
  Trash2,
  Workflow
} from 'lucide-react'
import { ensureProjectsLoaded } from '@/features/projects/project.loader'
import { isElectronRuntime } from '@/services/desktopClient'
import { useToastStore } from '@/shared/stores/toast.store'
import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import { useProjectStore } from '@/features/projects/stores/project.store'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import { useThemeStore } from '@/shared/stores/theme.store'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'
import type { SessionSummary } from '@/types/workspace'
import type { Project } from '@/types/project'
import { isConversationBusy } from './sidebarBusy'
import { useSidebarFilteredProjects } from './useSidebarFilteredProjects'
import { useSidebarProjectActions } from './useSidebarProjectActions'
import { useSidebarSessionActions } from './useSidebarSessionActions'

const sidebarEntryClassName = 'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[15px] text-content-secondary transition hover:bg-surface-tertiary'

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

function SessionRow({
  session,
  active,
  busy,
  onSelect,
  onRename,
  onDelete,
}: {
  session: SessionSummary
  active: boolean
  busy: boolean
  onSelect: () => void
  onRename: (sessionId: string, title: string) => Promise<void>
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(session.title)
  const [renaming, setRenaming] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  useEffect(() => {
    if (!editing) {
      setEditTitle(session.title)
    }
  }, [session.title, editing])

  const submitRename = async () => {
    const trimmed = editTitle.trim()
    if (!trimmed || trimmed === session.title) {
      setEditing(false)
      setEditTitle(session.title)
      return
    }

    setRenaming(true)
    try {
      await onRename(session.id, trimmed)
      setEditing(false)
    } catch {
      setEditTitle(session.title)
    } finally {
      setRenaming(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      submitRename()
    } else if (e.key === 'Escape') {
      setEditing(false)
      setEditTitle(session.title)
    }
  }

  return (
    <div
      className={`group flex items-center gap-2 rounded-2xl px-4 py-2.5 text-[15px] transition ${
        active
          ? 'bg-surface-tertiary text-content-primary'
          : 'text-content-secondary hover:bg-surface-tertiary'
      } ${busy ? 'opacity-75' : ''}`}
    >
      {editing ? (
        <input
          ref={inputRef}
          type="text"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={submitRename}
          onKeyDown={handleKeyDown}
          disabled={renaming}
           className="min-w-0 flex-1 rounded border border-edge bg-surface-primary px-1.5 py-0.5 text-[15px] text-content-secondary outline-none focus:border-edge"
        />
      ) : (
        <button
          type="button"
          onClick={onSelect}
          disabled={busy}
          className="flex min-w-0 flex-1 items-center justify-between gap-3 text-left"
        >
          <span className="truncate">{session.title}</span>
           <span className="shrink-0 text-content-muted">
            {formatRelativeTime(session.updatedAt)}
          </span>
        </button>
      )}
      <button
        type="button"
        onClick={() => setEditing(true)}
        disabled={busy || renaming}
         className="rounded-lg p-1 text-content-muted opacity-0 transition hover:bg-surface-tertiary hover:text-content-secondary group-hover:opacity-100 disabled:cursor-default disabled:opacity-0"
        title="重命名聊天"
      >
        <Pencil className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onDelete}
        disabled={busy}
         className="rounded-lg p-1 text-content-muted opacity-0 transition hover:bg-surface-tertiary hover:text-status-error group-hover:opacity-100 disabled:cursor-default disabled:opacity-0"
        title="删除聊天"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  )
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
  const theme = useThemeStore((s) => s.theme)
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
  const [formData, setFormData] = useState({ name: '', path: '' })
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
      useToastStore.getState().addToast('error', '加载项目列表失败')
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
    <aside className="flex max-h-[42vh] w-full shrink-0 flex-col overflow-hidden border-b border-edge bg-surface-secondary md:h-full md:max-h-none md:w-64 md:border-b-0 md:border-r lg:w-[320px]">
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
                  active ? 'bg-surface-tertiary text-content-primary' : ''
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
              className="w-full rounded-xl border border-edge bg-surface-primary px-3 py-2 text-sm text-content-secondary outline-none transition focus:border-edge"
            />
          </div>
        )}

        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between px-2 text-sm text-content-muted">
            <span className="font-medium">聊天</span>
            <div className="flex items-center gap-1">
                 <button
                 type="button"
                 onClick={handleCreateSession}
                disabled={busy}
                 className="rounded-lg p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent"
                 title="新建聊天"
              >
                <SquarePen className="h-4 w-4" />
              </button>
                               <button
                                 type="button"
                onClick={() => setShowProjectModal(true)}
                disabled={busy}
                 className="rounded-lg p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent"
                 title="新建项目"
              >
                <FolderPlus className="h-4 w-4" />
              </button>
            </div>
          </div>

          {loading ? (
            <div className="px-2 py-3 text-sm text-content-muted">加载项目中...</div>
          ) : filteredProjects.length === 0 ? (
            <div className="px-2 py-3 text-sm text-content-muted">暂无项目</div>
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
                        busy ? 'opacity-75' : 'hover:bg-surface-tertiary'
                      } ${isCurrentProject ? 'text-content-primary' : 'text-content-secondary'}`}
                    >
                               <button
                        type="button"
                        onClick={() => {
                          if (!busy) {
                            toggleProjectExpanded(project.id)
                          }
                        }}
                         className="rounded p-0.5 text-content-muted hover:bg-surface-tertiary"
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
                         <Folder className="h-5 w-5 shrink-0 text-content-muted" />
                        <span className="truncate text-[17px]">{project.name}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteProject(project)}
                        disabled={busy}
                         className="rounded-lg p-1 text-content-muted opacity-0 transition hover:bg-surface-tertiary hover:text-status-error group-hover:opacity-100 disabled:cursor-default disabled:opacity-0"
                        title="删除项目"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                    {expanded && (
                      <div className="mt-2 space-y-1 pl-10">
                        {projectSessions.length === 0 ? (
                           <div className="px-2 py-2 text-sm text-content-muted">暂无聊天</div>
                        ) : (
                          <>
                            {visibleSessions.map((session) => {
                              const active = currentSessionId === session.id && currentProject?.id === project.id

                              return (
                                <SessionRow
                                  key={session.id}
                                  session={session}
                                  active={active}
                                  busy={busy}
                                  onSelect={() => handleSessionSelect(project, session.id)}
                                  onRename={handleRenameSession}
                                  onDelete={() => handleDeleteSession(session)}
                                />
                              )
                            })}

                            {projectSessions.length > 5 && (
                              <button
                                type="button"
                                onClick={() => toggleProjectShowAll(project.id)}
                                className="px-4 py-2 text-left text-sm text-content-muted transition hover:text-content-secondary"
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

      <div className="border-t border-edge p-4">
        <div className="flex items-center justify-between">
          <NavLink
            to="/settings"
            className={({ isActive }) => `flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[15px] transition hover:bg-surface-tertiary ${
              isActive ? 'bg-surface-tertiary text-content-primary' : 'text-content-secondary'
            }`}
          >
            <Settings className="h-5 w-5" />
            <span className="font-medium">设置</span>
          </NavLink>
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              onClick={() => useThemeStore.getState().toggleSidebar()}
              className="rounded-lg p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary"
              title="收起侧边栏"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => {
                const current = useThemeStore.getState().theme
                const next = current === 'light' ? 'dark' : current === 'dark' ? 'system' : 'light'
                useThemeStore.getState().setTheme(next)
              }}
              className="rounded-lg p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary"
              title={`切换主题`}
            >
              {theme === 'dark' ? <Moon className="h-4 w-4" /> : theme === 'system' ? <Monitor className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>

      {showProjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-3xl bg-surface-primary p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-content-primary">新建项目</h3>
            <div className="mt-5 space-y-4">
              <div>
                 <label className="mb-1 block text-sm font-medium text-content-secondary">项目名称</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(event) => setFormData({ ...formData, name: event.target.value })}
                   className="w-full rounded-xl border border-edge bg-surface-primary px-3 py-2 text-content-secondary outline-none transition focus:border-edge"
                   placeholder="ReflexionOS"
                />
              </div>
              <div>
                 <label className="mb-1 block text-sm font-medium text-content-secondary">项目路径</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={formData.path}
                    onChange={(event) => setFormData({ ...formData, path: event.target.value })}
className="w-full rounded-xl border border-edge bg-surface-primary px-3 py-2 text-content-secondary outline-none transition focus:border-edge"
                      placeholder="/path/to/project"
                  />
                  {canSelectDirectory && (
                     <button
                      type="button"
                      onClick={handleSelectDirectory}
                      disabled={busy}
                       className="shrink-0 rounded-xl border border-edge px-3 py-2 text-sm text-content-secondary transition hover:bg-surface-tertiary"
                    >
                      选择目录
                    </button>
                  )}
                </div>
              </div>

            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowProjectModal(false)}
                 className="rounded-xl px-4 py-2 text-content-secondary transition hover:bg-surface-tertiary"
              >
                取消
              </button>
               <button
                 type="button"
                 onClick={() => handleCreateProject(formData)}
                 className="rounded-xl bg-accent px-4 py-2 text-white transition hover:bg-accent-hover"
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

import { useEffect, useState, useCallback } from 'react'
import {
  Puzzle,
  Plus,
  Trash2,
  RefreshCw,
  Wrench,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Package,
  Globe,
  Download,
} from 'lucide-react'
import { pluginApi } from '@/features/plugins/pluginApi'
import { useToastStore } from '@/stores/toastStore'
import type { Plugin, InstallPluginRequest } from '@/types/plugin'

interface PluginSkill {
  name: string
  description: string
  category: string
  enabled: boolean
}

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState<string | null>(null)
  const [updating, setUpdating] = useState<string | null>(null)
  const [updatingAll, setUpdatingAll] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null)
  const [pluginSkills, setPluginSkills] = useState<Record<string, PluginSkill[]>>({})
  const [skillsLoading, setSkillsLoading] = useState<string | null>(null)
  const [showInstallDialog, setShowInstallDialog] = useState(false)
  const [installSpecifier, setInstallSpecifier] = useState('')

  const loadPlugins = useCallback(async () => {
    setLoading(true)
    try {
      const res = await pluginApi.list()
      setPlugins(res.data)
    } catch (error) {
      console.error('Failed to load plugins:', error)
      useToastStore.getState().addToast('warning', '加载插件列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPlugins()
  }, [loadPlugins])

  const handleInstall = async () => {
    const specifier = installSpecifier.trim()
    if (!specifier) return
    setInstalling(true)
    try {
      await pluginApi.install({ specifier } as InstallPluginRequest)
      useToastStore.getState().addToast('info', `插件 ${specifier} 安装成功`)
      setInstallSpecifier('')
      setShowInstallDialog(false)
      await loadPlugins()
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.message || '安装失败'
      useToastStore.getState().addToast('warning', `安装失败: ${msg}`)
    } finally {
      setInstalling(false)
    }
  }

  const handleUninstall = async (name: string) => {
    setUninstalling(name)
    try {
      await pluginApi.uninstall(name)
      useToastStore.getState().addToast('info', `插件 ${name} 已卸载`)
      if (expandedPlugin === name) {
        setExpandedPlugin(null)
      }
      await loadPlugins()
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.message || '卸载失败'
      useToastStore.getState().addToast('warning', `卸载失败: ${msg}`)
    } finally {
      setUninstalling(null)
    }
  }

  const handleUpdate = async (name: string) => {
    setUpdating(name)
    try {
      await pluginApi.update(name)
      useToastStore.getState().addToast('info', `插件 ${name} 更新成功`)
      await loadPlugins()
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.message || '更新失败'
      useToastStore.getState().addToast('warning', `更新失败: ${msg}`)
    } finally {
      setUpdating(null)
    }
  }

  const handleUpdateAll = async () => {
    setUpdatingAll(true)
    try {
      const res = await pluginApi.updateAll()
      const { updated = [], errors = [] } = res.data
      if (updated.length > 0) {
        useToastStore.getState().addToast('info', `已更新 ${updated.length} 个插件`)
      }
      if (errors.length > 0) {
        useToastStore.getState().addToast('warning', `${errors.length} 个插件更新失败`)
      }
      if (updated.length === 0 && errors.length === 0) {
        useToastStore.getState().addToast('info', '所有插件已是最新版本')
      }
      await loadPlugins()
    } catch (error) {
      console.error('Failed to update all plugins:', error)
      useToastStore.getState().addToast('warning', '批量更新失败')
    } finally {
      setUpdatingAll(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadPlugins()
      useToastStore.getState().addToast('info', '插件列表已刷新')
    } finally {
      setRefreshing(false)
    }
  }

  const handleToggleExpand = async (name: string) => {
    if (expandedPlugin === name) {
      setExpandedPlugin(null)
      return
    }
    setExpandedPlugin(name)
    if (!pluginSkills[name]) {
      setSkillsLoading(name)
      try {
        const res = await pluginApi.skills(name)
        setPluginSkills((prev) => ({ ...prev, [name]: res.data }))
      } catch (error) {
        console.error('Failed to load plugin skills:', error)
        useToastStore.getState().addToast('warning', '加载插件技能列表失败')
      } finally {
        setSkillsLoading(null)
      }
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-primary">
      <div className="mx-auto max-w-5xl px-10 py-10">
        {/* Header */}
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-surface-tertiary px-3 py-1 text-sm text-content-muted">
            <Puzzle className="h-4 w-4" />
            <span>插件</span>
          </div>
          <h1 className="text-3xl font-semibold text-content-primary">插件工作台</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-content-muted">
            管理已安装的插件，安装新插件以扩展 Agent 能力。插件可以提供工具和技能。
          </p>
        </div>

        {/* Toolbar */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm text-content-muted">
              {plugins.length > 0 ? `已安装 ${plugins.length} 个插件` : '暂无已安装插件'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {plugins.length > 0 && (
              <button
                onClick={handleUpdateAll}
                disabled={updatingAll}
                className="inline-flex items-center gap-1.5 rounded-xl border border-edge bg-surface-tertiary px-3 py-1.5 text-sm text-content-secondary transition-colors hover:bg-surface-secondary disabled:opacity-50"
              >
                <Download className={`h-3.5 w-3.5 ${updatingAll ? 'animate-bounce' : ''}`} />
                全部更新
              </button>
            )}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="rounded-xl border border-edge bg-surface-tertiary p-2 text-content-secondary transition-colors hover:bg-surface-secondary disabled:opacity-50"
              title="刷新"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setShowInstallDialog(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-content-primary px-3 py-2 text-sm font-medium text-surface-primary transition-colors hover:bg-content-primary/90"
            >
              <Plus className="h-4 w-4" />
              安装插件
            </button>
          </div>
        </div>

        {/* Install Dialog */}
        {showInstallDialog && (
          <div className="mb-6 rounded-3xl border border-edge bg-surface-tertiary p-6">
            <h3 className="mb-3 text-sm font-medium text-content-primary">安装新插件</h3>
            <p className="mb-4 text-sm text-content-muted">
              输入插件标识符（如 GitHub 仓库路径 <code className="rounded bg-surface-primary px-1.5 py-0.5 text-xs">owner/repo</code> 或带版本 <code className="rounded bg-surface-primary px-1.5 py-0.5 text-xs">owner/repo@v1.0</code>）
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="例如: owner/repo 或 owner/repo@v1.0"
                value={installSpecifier}
                onChange={(e) => setInstallSpecifier(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleInstall()
                }}
                className="flex-1 rounded-2xl border border-edge bg-surface-primary px-4 py-2 text-sm text-content-primary placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-content-primary"
                autoFocus
              />
              <button
                onClick={handleInstall}
                disabled={installing || !installSpecifier.trim()}
                className="rounded-xl bg-content-primary px-4 py-2 text-sm font-medium text-surface-primary transition-colors hover:bg-content-primary/90 disabled:opacity-50"
              >
                {installing ? '安装中...' : '安装'}
              </button>
              <button
                onClick={() => {
                  setShowInstallDialog(false)
                  setInstallSpecifier('')
                }}
                className="rounded-xl border border-edge bg-surface-tertiary px-4 py-2 text-sm text-content-secondary transition-colors hover:bg-surface-secondary"
              >
                取消
              </button>
            </div>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            正在加载插件列表...
          </div>
        ) : plugins.length === 0 ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-8 py-10">
            <div className="flex items-start gap-4">
              <div className="rounded-2xl bg-surface-primary p-3 text-content-muted shadow-sm">
                <Package className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-content-primary">暂未安装插件</h2>
                <p className="mt-3 max-w-2xl text-[15px] leading-7 text-content-muted">
                  点击上方「安装插件」按钮，输入插件标识符来安装新插件。插件可以为 Agent 提供额外的工具和技能。
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {plugins.map((plugin) => (
              <div key={plugin.name}>
                {/* Plugin Card */}
                <div
                  onClick={() => handleToggleExpand(plugin.name)}
                  className={`cursor-pointer rounded-3xl border bg-surface-primary p-6 transition-colors hover:bg-surface-secondary ${
                    expandedPlugin === plugin.name
                      ? 'border-content-primary'
                      : 'border-edge'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h2 className="text-xl font-semibold text-content-primary">
                          {plugin.name}
                        </h2>
                        {plugin.has_tools && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400">
                            <Wrench className="h-3 w-3" />
                            工具
                          </span>
                        )}
                        {plugin.num_skills > 0 && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs text-blue-400">
                            <BookOpen className="h-3 w-3" />
                            {plugin.num_skills} 技能
                          </span>
                        )}
                      </div>
                      {plugin.specifier && (
                        <p className="mt-1 text-sm text-content-muted">
                          {plugin.specifier}
                        </p>
                      )}
                      {plugin.resolved_ref && (
                        <div className="mt-2 flex items-center gap-1.5 text-xs text-content-muted">
                          <Globe className="h-3 w-3" />
                          <span>{plugin.resolved_ref}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleUpdate(plugin.name)
                        }}
                        disabled={updating === plugin.name}
                        className="rounded-lg p-1 text-content-muted transition-colors hover:bg-surface-tertiary hover:text-content-secondary disabled:opacity-50"
                        title="更新"
                      >
                        <RefreshCw className={`h-4 w-4 ${updating === plugin.name ? 'animate-spin' : ''}`} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleUninstall(plugin.name)
                        }}
                        disabled={uninstalling === plugin.name}
                        className="rounded-lg p-1 text-content-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                        title="卸载"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                      {expandedPlugin === plugin.name ? (
                        <ChevronUp className="h-4 w-4 text-content-muted" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-content-muted" />
                      )}
                    </div>
                  </div>
                </div>

                {/* Expanded Skills Panel */}
                {expandedPlugin === plugin.name && (
                  <div className="rounded-b-3xl border border-t-0 border-edge bg-surface-tertiary px-6 py-5">
                    <div className="mb-3 flex items-center gap-2 text-sm font-medium text-content-primary">
                      <BookOpen className="h-4 w-4" />
                      <span>插件技能</span>
                    </div>
                    {skillsLoading === plugin.name ? (
                      <p className="text-sm text-content-muted">加载中...</p>
                    ) : pluginSkills[plugin.name]?.length > 0 ? (
                      <div className="space-y-2">
                        {pluginSkills[plugin.name].map((skill) => (
                          <div
                            key={skill.name}
                            className="flex items-center justify-between rounded-2xl bg-surface-primary px-4 py-2.5"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-content-primary">
                                  {skill.name}
                                </span>
                                <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs text-content-muted">
                                  {skill.category}
                                </span>
                              </div>
                              <p className="mt-0.5 text-xs text-content-muted line-clamp-1">
                                {skill.description}
                              </p>
                            </div>
                            <span
                              className={`ml-2 rounded-full px-2 py-0.5 text-xs ${
                                skill.enabled
                                  ? 'bg-green-500/10 text-green-400'
                                  : 'bg-surface-tertiary text-content-muted'
                              }`}
                            >
                              {skill.enabled ? '已启用' : '已禁用'}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-content-muted">该插件没有注册技能</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

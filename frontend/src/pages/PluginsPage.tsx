/**
 * 文件功能：插件工作台页面
 * 文件描述：展示和管理已安装的插件，支持安装新插件（从 Git 仓库/URL）、卸载、更新单个/全部插件、
 *          刷新插件列表，以及展开查看每个插件下注册的技能列表
 * 核心逻辑：插件列表通过 pluginApi 全量加载（非分页）；安装时支持在标识符后拼接可选分支/标签；
 *          展开插件卡片时按需懒加载该插件的技能列表并缓存到 pluginSkills 中，避免重复请求
 */
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
import { pluginApi } from '@/features/plugins/api/plugin.api'
import { useToastStore } from '@/shared/stores/toast.store'
import type { Plugin, InstallPluginRequest } from '@/types/plugin'

/** 插件下单个技能的展示数据结构 */
interface PluginSkill {
  name: string
  description: string
  category: string
  enabled: boolean
}

/**
 * 函数名：PluginsPage
 * 入参：无
 * 功能：渲染插件工作台页面，提供插件的浏览、安装、卸载、更新、展开查看技能等完整交互
 * 运行逻辑：
 *   1. 维护插件列表、各类加载/操作中状态（安装/卸载/更新/批量更新/刷新）、当前展开的插件、
 *      各插件的技能缓存、安装弹窗的输入状态等本地 state
 *   2. 挂载时通过 loadPlugins 加载插件列表
 *   3. handleInstall 根据标识符和可选分支拼接安装参数并调用后端安装接口
 *   4. handleUninstall/handleUpdate/handleUpdateAll/handleRefresh 分别处理卸载、单个更新、
 *      批量更新、刷新列表，均调用 pluginApi 对应接口并通过 toast 反馈结果
 *   5. handleToggleExpand 控制插件卡片的展开/收起，展开时若技能数据未缓存则发起请求加载
 *   6. 渲染顶部工具栏、安装弹窗、插件卡片列表（含展开后的技能面板）
 * 出参：JSX.Element - 插件工作台页面的 DOM 结构
 */
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
  const [installBranch, setInstallBranch] = useState('')

  /**
   * 函数名：loadPlugins
   * 入参：无
   * 功能：从后端加载已安装插件的完整列表
   * 运行逻辑：设置 loading 为 true，调用 pluginApi.list() 请求列表接口，成功写入 plugins state；
   *          失败则打印错误并弹出警告 toast；结束后重置 loading
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新 state）
   */
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

  /**
   * 函数名：useEffect（挂载时加载插件列表）
   * 入参：依赖 [loadPlugins]
   * 功能：组件挂载时触发一次插件列表加载
   * 运行逻辑：调用 loadPlugins 发起请求
   * 出参：无（副作用型 hook）
   */
  useEffect(() => {
    loadPlugins()
  }, [loadPlugins])

  /**
   * 函数名：handleInstall
   * 入参：无（从组件 state 中读取 installSpecifier 标识符和可选的 installBranch 分支名）
   * 功能：根据用户输入的插件标识符（及可选分支/标签）安装新插件
   * 运行逻辑：
   *   1. 去除标识符首尾空格，为空则直接返回
   *   2. 若用户填写了分支，根据标识符的格式（已有 @ 版本号 / URL / 短格式）拼接分支信息：
   *      - 已含 @ 但非 @git+ 前缀：替换 @ 之后的版本部分为新分支
   *      - http(s) URL：去掉原有 # 片段后追加 #分支
   *      - 短格式（owner/repo）：直接追加 @分支
   *   3. 调用 pluginApi.install 提交安装请求
   *   4. 成功后弹出提示 toast，清空输入框、关闭安装弹窗，并重新加载插件列表
   *   5. 失败时从错误响应中提取 detail 信息（或降级为 Error.message / 默认文案）展示为警告 toast
   *   6. 结束后重置 installing 状态
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleInstall = async () => {
    let specifier = installSpecifier.trim()
    if (!specifier) return

    // 如果用户指定了分支，添加到specifier
    if (installBranch.trim()) {
      const branch = installBranch.trim()
      // 判断格式并添加分支
      if (specifier.includes('@') && !specifier.includes('@git+')) {
        // 已有@符号，替换分支部分
        specifier = specifier.split('@')[0] + '@' + branch
      } else if (specifier.startsWith('http')) {
        // URL格式，使用#添加分支
        specifier = specifier.replace(/#.*$/, '') + '#' + branch
      } else {
        // 短格式，使用@添加分支
        specifier = specifier + '@' + branch
      }
    }

    setInstalling(true)
    try {
      await pluginApi.install({ specifier } satisfies InstallPluginRequest)
      useToastStore.getState().addToast('info', `插件 ${specifier} 安装成功`)
      setInstallSpecifier('')
      setInstallBranch('')
      setShowInstallDialog(false)
      await loadPlugins()
    } catch (error: unknown) {
      const msg = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || (error as Error)?.message || '安装失败'
      useToastStore.getState().addToast('warning', `安装失败: ${msg}`)
    } finally {
      setInstalling(false)
    }
  }

  /**
   * 函数名：handleUninstall
   * 入参：
   *   - name (string): 待卸载的插件名称
   * 功能：卸载指定插件
   * 运行逻辑：
   *   1. 记录当前正在卸载的插件名（用于按钮 loading 态）
   *   2. 调用 pluginApi.uninstall 提交卸载请求
   *   3. 成功后弹出提示 toast；若该插件当前正处于展开状态，则收起展开面板
   *   4. 重新加载插件列表
   *   5. 失败时从错误响应中提取 detail 信息（或降级处理）展示为警告 toast
   *   6. 结束后清除 uninstalling 标记
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleUninstall = async (name: string) => {
    setUninstalling(name)
    try {
      await pluginApi.uninstall(name)
      useToastStore.getState().addToast('info', `插件 ${name} 已卸载`)
      if (expandedPlugin === name) {
        setExpandedPlugin(null)
      }
      await loadPlugins()
    } catch (error: unknown) {
      const msg = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || (error as Error)?.message || '卸载失败'
      useToastStore.getState().addToast('warning', `卸载失败: ${msg}`)
    } finally {
      setUninstalling(null)
    }
  }

  /**
   * 函数名：handleUpdate
   * 入参：
   *   - name (string): 待更新的插件名称
   * 功能：将指定插件更新到最新版本
   * 运行逻辑：
   *   1. 记录当前正在更新的插件名（用于按钮 loading/旋转动画）
   *   2. 调用 pluginApi.update 提交更新请求
   *   3. 成功后弹出提示 toast，重新加载插件列表
   *   4. 失败时从错误响应中提取 detail 信息（或降级处理）展示为警告 toast
   *   5. 结束后清除 updating 标记
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleUpdate = async (name: string) => {
    setUpdating(name)
    try {
      await pluginApi.update(name)
      useToastStore.getState().addToast('info', `插件 ${name} 更新成功`)
      await loadPlugins()
    } catch (error: unknown) {
      const msg = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || (error as Error)?.message || '更新失败'
      useToastStore.getState().addToast('warning', `更新失败: ${msg}`)
    } finally {
      setUpdating(null)
    }
  }

  /**
   * 函数名：handleUpdateAll
   * 入参：无
   * 功能：批量更新所有已安装插件到最新版本
   * 运行逻辑：
   *   1. 设置 updatingAll 为 true（用于按钮 loading 态）
   *   2. 调用 pluginApi.updateAll() 提交批量更新请求，返回成功更新和失败的插件列表
   *   3. 根据 updated/errors 数量分别弹出对应的提示或警告 toast；两者都为空时提示“已是最新版本”
   *   4. 重新加载插件列表
   *   5. 请求本身失败（非部分失败）时打印错误并弹出警告 toast
   *   6. 结束后重置 updatingAll 状态
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
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

  /**
   * 函数名：handleRefresh
   * 入参：无
   * 功能：手动刷新插件列表
   * 运行逻辑：设置 refreshing 为 true，调用 loadPlugins 重新加载列表，成功后弹出提示 toast，
   *          结束后重置 refreshing 状态（无论成功失败）
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadPlugins()
      useToastStore.getState().addToast('info', '插件列表已刷新')
    } finally {
      setRefreshing(false)
    }
  }

  /**
   * 函数名：handleToggleExpand
   * 入参：
   *   - name (string): 要展开/收起的插件名称
   * 功能：切换指定插件卡片的展开/收起状态，展开时按需懒加载该插件的技能列表
   * 运行逻辑：
   *   1. 若当前已展开的插件正是该插件，则收起（设为 null）并直接返回
   *   2. 否则设置该插件为展开状态
   *   3. 若该插件的技能数据尚未缓存（pluginSkills 中没有对应 key），则发起请求加载：
   *      记录 skillsLoading 状态，调用 pluginApi.skills 获取数据后写入缓存；
   *      失败则打印错误并弹出警告 toast；结束后清除 skillsLoading
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新展开状态和技能缓存）
   */
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
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        {/* Header */}
        <div className="mb-8 lg:mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-surface-tertiary px-3 py-1 text-sm text-content-muted">
            <Puzzle className="h-4 w-4" />
            <span>插件</span>
          </div>
          <h1 className="text-2xl font-semibold text-content-primary sm:text-3xl">插件工作台</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-content-muted">
            管理已安装的插件，安装新插件以扩展 Agent 能力。插件可以提供工具和技能。
          </p>
        </div>

        {/* Toolbar */}
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
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
          <div className="mb-6 rounded-3xl border border-edge bg-surface-tertiary p-4 sm:p-6">
            <h3 className="mb-3 text-sm font-medium text-content-primary">安装新插件</h3>
            <p className="mb-3 text-sm text-content-muted">
              输入插件标识符。系统会自动检测 GitHub 仓库的默认分支（main/master等）。
            </p>
            <div className="mb-4 rounded-2xl border border-edge bg-surface-primary p-3">
              <p className="mb-2 text-xs font-medium text-content-secondary">支持的格式：</p>
              <ul className="space-y-1.5 text-xs text-content-muted">
                <li className="flex items-start gap-2">
                  <code className="rounded bg-surface-tertiary px-1.5 py-0.5 text-content-secondary">owner/repo</code>
                  <span className="flex-1">GitHub 短格式（自动检测默认分支）</span>
                </li>
                <li className="flex items-start gap-2">
                  <code className="rounded bg-surface-tertiary px-1.5 py-0.5 text-content-secondary">owner/repo@branch</code>
                  <span className="flex-1">指定分支或标签</span>
                </li>
                <li className="flex items-start gap-2">
                  <code className="rounded bg-surface-tertiary px-1.5 py-0.5 text-content-secondary">https://github.com/owner/repo</code>
                  <span className="flex-1">GitHub URL（自动检测默认分支）</span>
                </li>
                <li className="flex items-start gap-2">
                  <code className="rounded bg-surface-tertiary px-1.5 py-0.5 text-content-secondary">name@git+https://...</code>
                  <span className="flex-1">Git 完整格式</span>
                </li>
              </ul>
            </div>
            <div className="flex flex-col gap-3">
              <input
                type="text"
                placeholder="例如: obra/superpowers 或 https://github.com/owner/repo"
                value={installSpecifier}
                onChange={(e) => setInstallSpecifier(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !installBranch) handleInstall()
                }}
                className="rounded-2xl border border-edge bg-surface-primary px-4 py-2 text-sm text-content-primary placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-content-primary"
                autoFocus
              />
              <div className="flex items-center gap-2">
                <label className="text-xs text-content-muted whitespace-nowrap">
                  分支（可选）:
                </label>
                <input
                  type="text"
                  placeholder="留空则自动检测默认分支，如: master, develop"
                  value={installBranch}
                  onChange={(e) => setInstallBranch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleInstall()
                  }}
                  className="flex-1 rounded-2xl border border-edge bg-surface-primary px-4 py-2 text-sm text-content-primary placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-content-primary"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleInstall}
                  disabled={installing || !installSpecifier.trim()}
                  className="flex-1 rounded-xl bg-content-primary px-4 py-2 text-sm font-medium text-surface-primary transition-colors hover:bg-content-primary/90 disabled:opacity-50"
                >
                  {installing ? '安装中...' : '安装'}
                </button>
                <button
                  onClick={() => {
                    setShowInstallDialog(false)
                    setInstallSpecifier('')
                    setInstallBranch('')
                  }}
                  className="flex-1 rounded-xl border border-edge bg-surface-tertiary px-4 py-2 text-sm text-content-secondary transition-colors hover:bg-surface-secondary"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            正在加载插件列表...
          </div>
        ) : plugins.length === 0 ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-4 py-6 sm:px-8 sm:py-10">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
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
                  className={`cursor-pointer rounded-3xl border bg-surface-primary p-4 transition-colors hover:bg-surface-secondary sm:p-6 ${
                    expandedPlugin === plugin.name
                      ? 'border-content-primary'
                      : 'border-edge'
                  }`}
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="min-w-0 break-words text-xl font-semibold text-content-primary">
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
                        <p className="mt-1 break-all text-sm text-content-muted">
                          {plugin.specifier}
                        </p>
                      )}
                      {plugin.resolved_ref && (
                        <div className="mt-2 flex min-w-0 items-center gap-1.5 text-xs text-content-muted">
                          <Globe className="h-3 w-3" />
                          <span className="min-w-0 break-all">{plugin.resolved_ref}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-2 self-end sm:self-start">
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
                  <div className="rounded-b-3xl border border-t-0 border-edge bg-surface-tertiary px-4 py-5 sm:px-6">
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
                            className="flex flex-col gap-2 rounded-2xl bg-surface-primary px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
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
                              className={`self-start rounded-full px-2 py-0.5 text-xs sm:ml-2 sm:self-center ${
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

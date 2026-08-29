/**
 * 文件功能：技能配置页面
 * 文件描述：展示和管理 Agent 可用的技能列表，支持按分类/插件筛选、搜索、启用/禁用、
 *          从 Git 仓库或本地路径安装新技能、删除技能、刷新技能列表等操作
 * 核心逻辑：技能列表数据通过 useSkillList hook 分页加载（支持分类/插件/搜索条件），
 *          分类数据单独通过 skillApi.categories 获取；搜索输入做 300ms 防抖后才触发查询
 */
import { useEffect, useState, useMemo } from 'react'
import { Sparkles, Search, BookOpen, RefreshCw, Code2, Globe, Plus, Trash2 } from 'lucide-react'
import { skillApi } from '@/features/skills/api/skill.api'
import type { InstallSkillRequest } from '@/features/skills/api/skill.api'
import { useSkillList } from '@/features/skills/hooks/useSkillList'
import { useToastStore } from '@/shared/stores/toast.store'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'
import type { SkillCategories } from '@/types/skill'
import PluginFilter from '@/features/skills/components/PluginFilter'
import LoadMoreButton from '@/features/skills/components/LoadMoreButton'
import {
  getPluginList,
  getTopPlugins,
  getPluginType,
  getPluginDisplayName,
} from '@/features/skills/utils/skillHelpers'

/** 技能分类 key 到中文展示文案的映射表 */
const CATEGORY_LABELS: Record<string, string> = {
  discipline: '规范',
  technique: '技法',
  pattern: '模式',
  reference: '参考',
  uncategorized: '未分类',
}

/**
 * 函数名：SkillsPage
 * 入参：无
 * 功能：渲染技能配置页面，提供技能的浏览、筛选、搜索、启用/禁用、安装、删除等完整交互
 * 运行逻辑：
 *   1. 维护分类数据、当前选中分类/插件、搜索关键字（含防抖后的值）、各类加载态等本地 state
 *   2. 通过 useSkillList hook 按当前筛选条件（分类/插件/防抖后的搜索词）分页加载技能列表
 *   3. 搜索框输入后延迟 300ms 才更新 debouncedSearch，避免频繁请求
 *   4. 挂载时调用 loadCategories 加载分类数据
 *   5. 用 useMemo 派生插件列表、常用插件列表、分类 Tab 列表，避免重复计算
 *   6. handleToggle/handleRefresh/handleInstall/handleDelete 分别处理技能启用禁用、刷新列表、
 *      安装新技能、删除技能，均通过 skillApi 调用后端接口并用 toast 提示结果
 *   7. 渲染分类筛选、插件筛选、搜索框、安装弹窗、技能卡片列表（含加载更多按钮）
 * 出参：JSX.Element - 技能配置页面的 DOM 结构
 */
export default function SkillsPage() {
  const [categories, setCategories] = useState<SkillCategories>({})
  const [activeCategory, setActiveCategory] = useState<string>('全部')
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [activePlugin, setActivePlugin] = useState<string>('all')
  const [toggling, setToggling] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showInstallDialog, setShowInstallDialog] = useState(false)
  const [installSpecifier, setInstallSpecifier] = useState('')
  const [installing, setInstalling] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  const openFile = useCodeTabStore((s) => s.openFile)

  // 使用 useSkillList hook 获取技能列表
  // 根据当前分类/插件/防抖后的搜索词作为查询条件，hook 内部负责分页加载
  const {
    skills,
    loading,
    error,
    hasMore,
    loadMore,
    refresh: refreshSkills,
  } = useSkillList({
    category: activeCategory === '全部' ? undefined : activeCategory,
    pluginName: activePlugin === 'all' ? undefined : activePlugin === 'independent' ? '' : activePlugin,
    search: debouncedSearch,
  })

  /**
   * 函数名：useEffect（搜索防抖）
   * 入参：依赖 [searchQuery]
   * 功能：对搜索输入做 300ms 防抖，避免用户每次按键都触发一次列表查询
   * 运行逻辑：searchQuery 变化后启动一个 300ms 的定时器，到期后才把值同步到 debouncedSearch；
   *          若在 300ms 内 searchQuery 再次变化，则清除旧定时器重新计时
   * 出参：无（副作用型 hook）
   */
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  /**
   * 函数名：loadCategories
   * 入参：无
   * 功能：从后端加载技能分类数据，用于渲染分类 Tab
   * 运行逻辑：调用 skillApi.categories() 请求分类接口，成功后写入 categories state；
   *          失败时仅在控制台打印错误，不影响页面其他功能
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新 state）
   */
  const loadCategories = async () => {
    try {
      const categoriesRes = await skillApi.categories()
      setCategories(categoriesRes.data)
    } catch (error) {
      console.error('Failed to load categories:', error)
    }
  }

  /**
   * 函数名：useEffect（挂载时加载分类）
   * 入参：依赖 []（仅挂载时执行一次）
   * 功能：组件首次挂载时触发分类数据加载
   * 运行逻辑：调用 loadCategories 发起一次分类请求
   * 出参：无（副作用型 hook）
   */
  useEffect(() => {
    loadCategories()
  }, [])

  const pluginList = useMemo(() => getPluginList(skills), [skills])
  const topPlugins = useMemo(() => getTopPlugins(pluginList), [pluginList])

  const categoryTabs = useMemo(() => {
    const tabs = ['全部']
    const keys = Object.keys(categories)
    if (keys.length > 0) {
      tabs.push(...keys)
    } else {
      const uniqueCats = [...new Set(skills.map((s) => s.category))]
      tabs.push(...uniqueCats)
    }
    return tabs
  }, [categories, skills])

  /**
   * 函数名：handleToggle
   * 入参：
   *   - name (string): 技能名称
   *   - enabled (boolean): 技能当前是否已启用
   * 功能：切换指定技能的启用/禁用状态
   * 运行逻辑：
   *   1. 记录当前正在切换的技能名（用于按钮 loading 态）
   *   2. 若当前已启用则调用 skillApi.disable，否则调用 skillApi.enable
   *   3. 成功后刷新技能列表；失败则打印错误并弹出警告 toast
   *   4. 结束后清除 toggling 标记
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleToggle = async (name: string, enabled: boolean) => {
    setToggling(name)
    try {
      if (enabled) {
        await skillApi.disable(name)
      } else {
        await skillApi.enable(name)
      }
      refreshSkills()
    } catch (error) {
      console.error('Failed to toggle skill:', error)
      useToastStore.getState().addToast('warning', '切换技能状态失败')
    } finally {
      setToggling(null)
    }
  }

  /**
   * 函数名：handleRefresh
   * 入参：无
   * 功能：刷新技能列表和分类数据（重新扫描技能目录）
   * 运行逻辑：
   *   1. 设置 refreshing 为 true（用于刷新按钮的旋转动画）
   *   2. 调用 skillApi.refresh() 触发后端重新扫描技能
   *   3. 刷新本地技能列表和分类数据，成功后弹出提示 toast
   *   4. 失败则打印错误并弹出警告 toast
   *   5. 结束后重置 refreshing 状态
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await skillApi.refresh()
      refreshSkills()
      await loadCategories()
      useToastStore.getState().addToast('info', '技能列表已刷新')
    } catch (error) {
      console.error('Failed to refresh skills:', error)
      useToastStore.getState().addToast('warning', '刷新技能列表失败')
    } finally {
      setRefreshing(false)
    }
  }

  /**
   * 函数名：handleInstall
   * 入参：无（从组件 state 中读取 installSpecifier 作为安装标识符）
   * 功能：根据用户输入的标识符（GitHub 短格式/URL/Git 完整格式/本地路径等）安装新技能
   * 运行逻辑：
   *   1. 去除输入首尾空格，若为空则直接返回不处理
   *   2. 调用 skillApi.install 提交安装请求
   *   3. 成功后弹出提示 toast，清空输入框并关闭安装弹窗，刷新技能列表和分类数据
   *   4. 失败时从错误响应中提取后端返回的 detail 信息（或降级为 Error.message / 默认文案）展示为警告 toast
   *   5. 结束后重置 installing 状态
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleInstall = async () => {
    const specifier = installSpecifier.trim()
    if (!specifier) return
    setInstalling(true)
    try {
      await skillApi.install({ specifier } satisfies InstallSkillRequest)
      useToastStore.getState().addToast('info', `技能 ${specifier} 安装成功`)
      setInstallSpecifier('')
      setShowInstallDialog(false)
      refreshSkills()
      await loadCategories()
    } catch (error: unknown) {
      const msg = typeof error === 'object' && error !== null && 'response' in error && typeof error.response === 'object' && error.response !== null && 'data' in error.response && typeof error.response.data === 'object' && error.response.data !== null && 'detail' in error.response.data && typeof error.response.data.detail === 'string' ? error.response.data.detail : error instanceof Error ? error.message : '安装失败'
      useToastStore.getState().addToast('warning', `安装失败: ${msg}`)
    } finally {
      setInstalling(false)
    }
  }

  /**
   * 函数名：handleDelete
   * 入参：
   *   - name (string): 待删除的技能名称
   * 功能：删除指定技能
   * 运行逻辑：
   *   1. 记录当前正在删除的技能名（用于按钮 loading 态）
   *   2. 调用 skillApi.remove 提交删除请求
   *   3. 成功后弹出提示 toast，刷新技能列表和分类数据
   *   4. 失败时从错误响应中提取 detail 信息（或降级处理）展示为警告 toast
   *   5. 结束后清除 deleting 标记
   * 出参：Promise<void>（异步函数，无返回值，通过副作用更新列表和提示）
   */
  const handleDelete = async (name: string) => {
    setDeleting(name)
    try {
      await skillApi.remove(name)
      useToastStore.getState().addToast('info', `技能 ${name} 已删除`)
      refreshSkills()
      await loadCategories()
    } catch (error: unknown) {
      const msg = typeof error === 'object' && error !== null && 'response' in error && typeof error.response === 'object' && error.response !== null && 'data' in error.response && typeof error.response.data === 'object' && error.response.data !== null && 'detail' in error.response.data && typeof error.response.data.detail === 'string' ? error.response.data.detail : error instanceof Error ? error.message : '删除失败'
      useToastStore.getState().addToast('warning', `删除失败: ${msg}`)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-primary">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <div className="mb-8 lg:mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-surface-tertiary px-3 py-1 text-sm text-content-muted">
            <Sparkles className="h-4 w-4" />
            <span>技能</span>
          </div>
          <h1 className="text-2xl font-semibold text-content-primary sm:text-3xl">
            技能配置
          </h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-content-muted">
            技能决定了 Agent 在特定任务下优先采用的工具组合和执行偏好，你可以按类别浏览并管理技能的启用状态。
          </p>
        </div>

        <div className="mb-6 flex flex-col gap-4">
          {/* 第一行：分类筛选 + 插件筛选 */}
          <div className="flex flex-wrap items-center gap-3">
            {/* 分类筛选 */}
            <div className="flex flex-wrap gap-2">
              {categoryTabs.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                    activeCategory === cat
                      ? 'bg-content-primary text-surface-primary'
                      : 'bg-surface-tertiary text-content-secondary hover:bg-surface-secondary'
                  }`}
                >
                  {cat === '全部' ? '全部' : CATEGORY_LABELS[cat] || cat}
                </button>
              ))}
            </div>

            {/* 分隔符 */}
            <div className="h-6 w-px bg-edge" />

            {/* 插件筛选 */}
            <PluginFilter
              plugins={pluginList}
              topPlugins={topPlugins}
              activePlugin={activePlugin}
              onPluginChange={setActivePlugin}
            />
          </div>

          {/* 第二行：搜索框和操作按钮 */}
          <div className="flex items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-muted" />
              <input
                type="text"
                placeholder="搜索技能..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-2xl border border-edge bg-surface-tertiary py-2 pl-9 pr-4 text-sm text-content-primary placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-content-primary"
              />
            </div>
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
              安装技能
            </button>
          </div>
        </div>

        {showInstallDialog && (
          <div className="mb-6 rounded-3xl border border-edge bg-surface-tertiary p-4 sm:p-6">
            <h3 className="mb-3 text-sm font-medium text-content-primary">安装新技能</h3>
            <ul className="mb-4 space-y-1 text-xs text-content-muted">
              <li><code className="rounded bg-surface-primary px-1.5 py-0.5">owner/repo</code> — GitHub 短格式</li>
              <li><code className="rounded bg-surface-primary px-1.5 py-0.5">owner/repo@v1.0</code> — GitHub 带版本/分支</li>
              <li><code className="rounded bg-surface-primary px-1.5 py-0.5">https://github.com/owner/repo</code> — GitHub URL</li>
              <li><code className="rounded bg-surface-primary px-1.5 py-0.5">name@git+https://...</code> — Git 完整格式</li>
              <li><code className="rounded bg-surface-primary px-1.5 py-0.5">name@file:///path</code> — 本地路径</li>
            </ul>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                placeholder="例如: obra/superpowers 或 obra/superpowers@main"
                value={installSpecifier}
                onChange={(e) => setInstallSpecifier(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleInstall()
                }}
                className="min-w-0 flex-1 rounded-2xl border border-edge bg-surface-primary px-4 py-2 text-sm text-content-primary placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-content-primary"
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

        {loading ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            正在加载技能列表...
          </div>
        ) : error ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            加载失败: {error.message}
          </div>
        ) : skills.length === 0 && !searchQuery && activeCategory === '全部' && activePlugin === 'all' ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            暂无技能。点击 + 按钮从 Git 仓库安装技能，或将 SKILL.md 文件放入 skills/ 目录。
          </div>
        ) : skills.length === 0 ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            未找到匹配的技能
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              {skills.map((skill) => {
                const pluginType = getPluginType(skill)
                const pluginDisplayName = getPluginDisplayName(skill)
                const pluginBadgeStyle =
                  pluginType === 'builtin'
                    ? 'bg-green-500/10 text-green-400'
                    : pluginType === 'installed'
                      ? 'bg-blue-500/10 text-blue-400'
                      : 'bg-surface-tertiary text-content-muted'
                const showIcon = pluginType === 'builtin' || pluginType === 'installed'
                return (
                  <div key={skill.name}>
                      <div
                        className="rounded-3xl border border-edge bg-surface-primary p-4 transition-colors hover:bg-surface-secondary sm:p-6"
                      >
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h2 className="min-w-0 break-words text-xl font-semibold text-content-primary">
                              {skill.name}
                            </h2>
                            <span className="rounded-full bg-surface-tertiary px-2.5 py-0.5 text-xs text-content-muted">
                              {CATEGORY_LABELS[skill.category] || skill.category}
                            </span>
                            <span
                              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${pluginBadgeStyle}`}
                            >
                              {showIcon && (pluginType === 'builtin' ? <Code2 className="h-3 w-3" /> : <Globe className="h-3 w-3" />)}
                              {pluginDisplayName}
                            </span>
                          </div>
                          <p className="mt-2 line-clamp-2 text-[15px] leading-7 text-content-muted">
                            {skill.description}
                          </p>
                        </div>

                        <div className="flex shrink-0 items-center gap-2 self-end sm:self-start">
                          <button
                            onClick={() => {
                              openFile(skill.install_path + '/SKILL.md', 'edit')
                            }}
                            className="rounded-lg p-1 text-content-muted transition-colors hover:bg-surface-tertiary hover:text-content-secondary"
                            title="在编辑器中查看"
                          >
                            <Code2 className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(skill.name)}
                            disabled={deleting === skill.name}
                            className="rounded-lg p-1 text-content-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                            title="删除技能"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              handleToggle(skill.name, skill.enabled)
                            }}
                            disabled={toggling === skill.name}
                            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
                              skill.enabled
                                ? 'bg-status-success'
                                : 'bg-surface-tertiary'
                            } ${toggling === skill.name ? 'opacity-50' : ''}`}
                          >
                            <span
                              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                skill.enabled
                                  ? 'translate-x-6'
                                  : 'translate-x-1'
                              }`}
                            />
                          </button>
                        </div>
                      </div>

                      {skill.required_skills.length > 0 && (
                        <div className="mt-4">
                          <div className="mb-1.5 flex items-center gap-1.5 text-xs text-content-muted">
                            <BookOpen className="h-3.5 w-3.5" />
                            <span>前置技能</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {skill.required_skills.map((req) => (
                              <span
                                key={req}
                                className="rounded-full bg-surface-tertiary px-2.5 py-0.5 text-xs text-content-secondary"
                              >
                                {req}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* 加载更多按钮 */}
            <LoadMoreButton hasMore={hasMore} onClick={loadMore} />
          </>
        )}
      </div>
    </div>
  )
}

import { useEffect, useState, useMemo } from 'react'
import { Sparkles, Search, BookOpen, ChevronRight, X, RefreshCw, Code2, Globe } from 'lucide-react'
import { skillApi } from '@/features/skills/skillApi'
import { useToastStore } from '@/stores/toastStore'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import type { Skill, SkillDetail, SkillCategories } from '@/types/skill'

const CATEGORY_LABELS: Record<string, string> = {
  discipline: '规范',
  technique: '技法',
  pattern: '模式',
  reference: '参考',
  uncategorized: '未分类',
}

function getSourceLabel(skill: Skill): { label: string; type: 'builtin' | 'installed' | 'local' } {
  if (skill.source) return { label: skill.source, type: 'installed' }
  if (skill.install_path?.includes('.reflexion')) return { label: '全局安装', type: 'installed' }
  if (skill.install_path?.includes('skills/')) return { label: '项目内置', type: 'builtin' }
  return { label: '本地', type: 'local' }
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [categories, setCategories] = useState<SkillCategories>({})
  const [loading, setLoading] = useState(true)
  const [activeCategory, setActiveCategory] = useState<string>('全部')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null)
  const [skillDetail, setSkillDetail] = useState<SkillDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const openFile = useCodeTabStore((s) => s.openFile)

  const loadSkills = async () => {
    setLoading(true)
    try {
      const [skillsRes, categoriesRes] = await Promise.all([
        skillApi.list(),
        skillApi.categories(),
      ])
      setSkills(skillsRes.data)
      setCategories(categoriesRes.data)
    } catch (error) {
      console.error('Failed to load skills:', error)
      useToastStore.getState().addToast('warning', '加载技能列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSkills()
  }, [])

  const filteredSkills = useMemo(() => {
    let result = skills
    if (activeCategory !== '全部') {
      result = result.filter((s) => s.category === activeCategory)
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q)
      )
    }
    return result
  }, [skills, activeCategory, searchQuery])

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

  const handleSelectSkill = async (name: string) => {
    if (selectedSkill === name) {
      setSelectedSkill(null)
      setSkillDetail(null)
      return
    }
    setSelectedSkill(name)
    setDetailLoading(true)
    try {
      const res = await skillApi.detail(name)
      setSkillDetail(res.data)
    } catch (error) {
      console.error('Failed to load skill detail:', error)
      useToastStore.getState().addToast('warning', '加载技能详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleToggle = async (name: string, enabled: boolean) => {
    setToggling(name)
    try {
      if (enabled) {
        await skillApi.disable(name)
      } else {
        await skillApi.enable(name)
      }
      setSkills((prev) =>
        prev.map((s) => (s.name === name ? { ...s, enabled: !enabled } : s))
      )
      if (skillDetail?.name === name) {
        setSkillDetail((prev) =>
          prev ? { ...prev, enabled: !enabled } : prev
        )
      }
    } catch (error) {
      console.error('Failed to toggle skill:', error)
      useToastStore.getState().addToast('warning', '切换技能状态失败')
    } finally {
      setToggling(null)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await skillApi.refresh()
      await loadSkills()
      useToastStore.getState().addToast('info', '技能列表已刷新')
    } catch (error) {
      console.error('Failed to refresh skills:', error)
      useToastStore.getState().addToast('warning', '刷新技能列表失败')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-primary">
      <div className="mx-auto max-w-5xl px-10 py-10">
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-surface-tertiary px-3 py-1 text-sm text-content-muted">
            <Sparkles className="h-4 w-4" />
            <span>技能</span>
          </div>
          <h1 className="text-3xl font-semibold text-content-primary">
            技能配置
          </h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-content-muted">
            技能决定了 Agent 在特定任务下优先采用的工具组合和执行偏好，你可以按类别浏览并管理技能的启用状态。
          </p>
        </div>

        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
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

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-muted" />
              <input
                type="text"
                placeholder="搜索技能..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-2xl border border-edge bg-surface-tertiary py-2 pl-9 pr-4 text-sm text-content-primary placeholder:text-content-muted focus:outline-none focus:ring-1 focus:ring-content-primary sm:w-64"
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
          </div>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            正在加载技能列表...
          </div>
        ) : filteredSkills.length === 0 && skills.length === 0 ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            暂无技能。点击 + 按钮从 Git 仓库安装技能，或将 SKILL.md 文件放入 skills/ 目录。
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="rounded-3xl border border-edge bg-surface-tertiary px-6 py-8 text-content-muted">
            未找到匹配的技能
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {filteredSkills.map((skill) => {
              const src = getSourceLabel(skill)
              return (
                <div key={skill.name}>
                  <div
                    onClick={() => handleSelectSkill(skill.name)}
                    className={`cursor-pointer rounded-3xl border bg-surface-primary p-6 transition-colors hover:bg-surface-secondary ${
                      selectedSkill === skill.name
                        ? 'border-content-primary'
                        : 'border-edge'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h2 className="text-xl font-semibold text-content-primary">
                            {skill.name}
                          </h2>
                          <span className="rounded-full bg-surface-tertiary px-2.5 py-0.5 text-xs text-content-muted">
                            {CATEGORY_LABELS[skill.category] || skill.category}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                              src.type === 'installed'
                                ? 'bg-blue-500/10 text-blue-400'
                                : src.type === 'builtin'
                                  ? 'bg-green-500/10 text-green-400'
                                  : 'bg-surface-tertiary text-content-muted'
                            }`}
                          >
                            {src.type === 'installed' && <Globe className="h-3 w-3" />}
                            {src.label}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-[15px] leading-7 text-content-muted">
                          {skill.description}
                        </p>
                      </div>

                      <div className="flex shrink-0 items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            openFile(skill.install_path + '/SKILL.md', 'edit')
                          }}
                          className="rounded-lg p-1 text-content-muted transition-colors hover:bg-surface-tertiary hover:text-content-secondary"
                          title="在编辑器中查看"
                        >
                          <Code2 className="h-4 w-4" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
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
                        <ChevronRight
                          className={`h-4 w-4 text-content-muted transition-transform ${
                            selectedSkill === skill.name ? 'rotate-90' : ''
                          }`}
                        />
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

                  {selectedSkill === skill.name && (
                    <div className="rounded-b-3xl border border-t-0 border-edge bg-surface-tertiary px-6 py-5">
                      <div className="mb-3 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
                          <BookOpen className="h-4 w-4" />
                          <span>技能详情</span>
                        </div>
                        <button
                          onClick={() => {
                            setSelectedSkill(null)
                            setSkillDetail(null)
                          }}
                          className="rounded-full p-1 text-content-muted hover:bg-surface-primary"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                      {detailLoading ? (
                        <p className="text-sm text-content-muted">
                          加载中...
                        </p>
                      ) : skillDetail ? (
                        <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-content-secondary">
                          {skillDetail.content}
                        </pre>
                      ) : null}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

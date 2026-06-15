# 技能列表页面优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化技能列表页面，增加插件筛选功能和分页加载，改善显示混乱的问题

**Architecture:** 
- 在现有分类筛选基础上增加插件筛选维度（单行布局，常用插件显示+更多下拉）
- 技能卡片显示插件名替代来源类型标签
- 实现"加载更多"分页功能（初始24个，每次加载12个）
- 技能按插件类型排序（内置→全局安装→本地→独立）

**Tech Stack:** React, TypeScript, Lucide Icons, Tailwind CSS

---

## 文件结构

**新增文件：**
- `frontend/src/components/skills/PluginFilter.tsx` - 插件筛选组件（常用插件+更多下拉）
- `frontend/src/components/skills/LoadMoreButton.tsx` - 加载更多按钮组件
- `frontend/src/utils/skillSorting.ts` - 技能排序工具函数

**修改文件：**
- `frontend/src/pages/SkillsPage.tsx` - 主页面，集成插件筛选和分页功能
- `frontend/src/types/skill.ts` - 可能需要补充类型定义

---

## Task 1: 创建技能排序工具函数

**Files:**
- Create: `frontend/src/utils/skillSorting.ts`

- [ ] **Step 1: 创建排序工具函数文件**

```typescript
import type { Skill } from '@/types/skill'

export type PluginInfo = {
  name: string
  displayName: string
  type: 'builtin' | 'installed' | 'local' | 'independent'
  skillCount: number
}

/**
 * 获取技能的插件类型
 */
export function getPluginType(skill: Skill): 'builtin' | 'installed' | 'local' | 'independent' {
  if (!skill.plugin_name) return 'independent'
  if (skill.install_path?.includes('.reflexion')) return 'installed'
  if (skill.install_path?.includes('skills/')) return 'builtin'
  return 'local'
}

/**
 * 获取技能的插件显示名称
 */
export function getPluginDisplayName(skill: Skill): string {
  if (!skill.plugin_name) return '独立技能'
  return skill.plugin_name
}

/**
 * 获取所有插件信息并按优先级排序
 */
export function getPluginList(skills: Skill[]): PluginInfo[] {
  const pluginMap = new Map<string, PluginInfo>()

  // 统计每个插件的技能数量
  skills.forEach((skill) => {
    const type = getPluginType(skill)
    const name = skill.plugin_name || 'independent'
    const displayName = getPluginDisplayName(skill)

    if (!pluginMap.has(name)) {
      pluginMap.set(name, { name, displayName, type, skillCount: 0 })
    }
    pluginMap.get(name)!.skillCount++
  })

  const plugins = Array.from(pluginMap.values())

  // 排序：内置 → 全局安装 → 本地 → 独立，同类型内按技能数量降序
  const typeOrder: Record<string, number> = {
    builtin: 0,
    installed: 1,
    local: 2,
    independent: 3,
  }

  plugins.sort((a, b) => {
    const typeCompare = typeOrder[a.type] - typeOrder[b.type]
    if (typeCompare !== 0) return typeCompare
    return b.skillCount - a.skillCount
  })

  return plugins
}

/**
 * 获取优先显示的插件（前3-4个常用插件）
 */
export function getTopPlugins(plugins: PluginInfo[]): PluginInfo[] {
  // 独立技能如果存在，始终显示
  const independent = plugins.find((p) => p.type === 'independent')
  const others = plugins.filter((p) => p.type !== 'independent')

  // 取前3个非独立插件
  const topOthers = others.slice(0, 3)

  return independent ? [...topOthers, independent] : topOthers
}

/**
 * 对技能列表排序
 * 按插件类型 → 插件名 → 技能名
 */
export function sortSkills(skills: Skill[]): Skill[] {
  const typeOrder: Record<string, number> = {
    builtin: 0,
    installed: 1,
    local: 2,
    independent: 3,
  }

  return [...skills].sort((a, b) => {
    const typeA = getPluginType(a)
    const typeB = getPluginType(b)
    const typeCompare = typeOrder[typeA] - typeOrder[typeB]
    if (typeCompare !== 0) return typeCompare

    const pluginA = a.plugin_name || ''
    const pluginB = b.plugin_name || ''
    const pluginCompare = pluginA.localeCompare(pluginB)
    if (pluginCompare !== 0) return pluginCompare

    return a.name.localeCompare(b.name)
  })
}
```

- [ ] **Step 2: 提交排序工具函数**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/utils/skillSorting.ts
git commit -m "feat: add skill sorting utilities for plugin-based organization"
```

---

## Task 2: 创建插件筛选组件

**Files:**
- Create: `frontend/src/components/skills/PluginFilter.tsx`

- [ ] **Step 1: 创建插件筛选组件**

```typescript
import { ChevronDown } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import type { PluginInfo } from '@/utils/skillSorting'

interface PluginFilterProps {
  plugins: PluginInfo[]
  topPlugins: PluginInfo[]
  activePlugin: string
  onPluginChange: (plugin: string) => void
}

export default function PluginFilter({
  plugins,
  topPlugins,
  activePlugin,
  onPluginChange,
}: PluginFilterProps) {
  const [showMoreDropdown, setShowMoreDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // 点击外部关闭下拉菜单
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowMoreDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 获取"更多"中的插件
  const morePlugins = plugins.filter(
    (p) => !topPlugins.find((tp) => tp.name === p.name)
  )

  return (
    <div className="flex items-center gap-2">
      {/* 所有插件按钮 */}
      <button
        onClick={() => onPluginChange('all')}
        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
          activePlugin === 'all'
            ? 'bg-content-primary text-surface-primary'
            : 'bg-surface-tertiary text-content-secondary hover:bg-surface-secondary'
        }`}
      >
        所有插件
      </button>

      {/* 常用插件按钮 */}
      {topPlugins.map((plugin) => (
        <button
          key={plugin.name}
          onClick={() => onPluginChange(plugin.name)}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
            activePlugin === plugin.name
              ? 'bg-content-primary text-surface-primary'
              : 'bg-surface-tertiary text-content-secondary hover:bg-surface-secondary'
          }`}
        >
          {plugin.displayName}
        </button>
      ))}

      {/* 更多下拉菜单 */}
      {morePlugins.length > 0 && (
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setShowMoreDropdown(!showMoreDropdown)}
            className={`inline-flex items-center gap-1 rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              morePlugins.find((p) => p.name === activePlugin)
                ? 'bg-content-primary text-surface-primary'
                : 'bg-surface-tertiary text-content-secondary hover:bg-surface-secondary'
            }`}
          >
            更多
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showMoreDropdown ? 'rotate-180' : ''}`} />
          </button>

          {showMoreDropdown && (
            <div className="absolute right-0 top-full z-10 mt-2 w-48 rounded-2xl border border-edge bg-surface-primary py-2 shadow-lg">
              {morePlugins.map((plugin) => (
                <button
                  key={plugin.name}
                  onClick={() => {
                    onPluginChange(plugin.name)
                    setShowMoreDropdown(false)
                  }}
                  className={`block w-full px-4 py-2 text-left text-sm transition-colors ${
                    activePlugin === plugin.name
                      ? 'bg-surface-tertiary text-content-primary'
                      : 'text-content-secondary hover:bg-surface-tertiary hover:text-content-primary'
                  }`}
                >
                  {plugin.displayName}
                  <span className="ml-2 text-xs text-content-muted">
                    ({plugin.skillCount})
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 提交插件筛选组件**

```bash
git add frontend/src/components/skills/PluginFilter.tsx
git commit -m "feat: add plugin filter component with top plugins and more dropdown"
```

---

## Task 3: 创建加载更多按钮组件

**Files:**
- Create: `frontend/src/components/skills/LoadMoreButton.tsx`

- [ ] **Step 1: 创建加载更多按钮组件**

```typescript
interface LoadMoreButtonProps {
  hasMore: boolean
  onClick: () => void
}

export default function LoadMoreButton({ hasMore, onClick }: LoadMoreButtonProps) {
  if (!hasMore) return null

  return (
    <div className="mt-8 flex justify-center">
      <button
        onClick={onClick}
        className="rounded-2xl border border-edge bg-surface-tertiary px-6 py-3 text-sm font-medium text-content-primary transition-colors hover:bg-surface-secondary"
      >
        加载更多
      </button>
    </div>
  )
}
```

- [ ] **Step 2: 提交加载更多按钮组件**

```bash
git add frontend/src/components/skills/LoadMoreButton.tsx
git commit -m "feat: add load more button component for pagination"
```

---

## Task 4: 更新技能页面 - 集成插件筛选

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 添加导入和插件筛选状态**

在文件顶部的导入部分添加：

```typescript
import PluginFilter from '@/components/skills/PluginFilter'
import LoadMoreButton from '@/components/skills/LoadMoreButton'
import {
  getPluginList,
  getTopPlugins,
  sortSkills,
  getPluginType,
  getPluginDisplayName,
} from '@/utils/skillSorting'
```

在组件内的状态声明部分（约第28行后）添加：

```typescript
const [activePlugin, setActivePlugin] = useState<string>('all')
const [displayCount, setDisplayCount] = useState(24)
```

- [ ] **Step 2: 更新筛选逻辑**

将现有的 `filteredSkills` 计算逻辑（约第60-74行）替换为：

```typescript
const filteredSkills = useMemo(() => {
  let result = skills
  
  // 分类筛选
  if (activeCategory !== '全部') {
    result = result.filter((s) => s.category === activeCategory)
  }
  
  // 插件筛选
  if (activePlugin !== 'all') {
    if (activePlugin === 'independent') {
      result = result.filter((s) => !s.plugin_name)
    } else {
      result = result.filter((s) => s.plugin_name === activePlugin)
    }
  }
  
  // 搜索筛选
  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase()
    result = result.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
    )
  }
  
  // 排序
  return sortSkills(result)
}, [skills, activeCategory, activePlugin, searchQuery])
```

- [ ] **Step 3: 添加插件列表计算和分页逻辑**

在 `filteredSkills` 后添加：

```typescript
const pluginList = useMemo(() => getPluginList(skills), [skills])
const topPlugins = useMemo(() => getTopPlugins(pluginList), [pluginList])

const displayedSkills = useMemo(
  () => filteredSkills.slice(0, displayCount),
  [filteredSkills, displayCount]
)

const hasMore = displayCount < filteredSkills.length

const handleLoadMore = () => {
  setDisplayCount((prev) => prev + 12)
}
```

- [ ] **Step 4: 添加筛选条件变化时重置分页**

在 `handleToggle` 函数之前添加：

```typescript
// 筛选条件改变时重置分页
useEffect(() => {
  setDisplayCount(24)
}, [activeCategory, activePlugin, searchQuery])
```

- [ ] **Step 5: 提交插件筛选集成**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat: integrate plugin filter logic and pagination state"
```

---

## Task 5: 更新技能页面 - UI 布局调整

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 更新筛选区域布局**

将现有的筛选区域（约第169-213行）替换为：

```typescript
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
```

- [ ] **Step 2: 提交 UI 布局更新**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat: update skills page layout with plugin filter and reorganized controls"
```

---

## Task 6: 更新技能卡片 - 显示插件名

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 更新技能卡片中的插件标签显示**

将技能列表渲染部分（约第270-367行）中的卡片内容更新。找到这部分代码：

```typescript
{filteredSkills.map((skill) => {
  const src = getSourceLabel(skill)
```

替换为：

```typescript
{displayedSkills.map((skill) => {
  const pluginType = getPluginType(skill)
  const pluginDisplayName = getPluginDisplayName(skill)
  const pluginBadgeStyle =
    pluginType === 'builtin'
      ? 'bg-green-500/10 text-green-400'
      : pluginType === 'installed'
        ? 'bg-blue-500/10 text-blue-400'
        : 'bg-surface-tertiary text-content-muted'
  const showIcon = pluginType === 'builtin' || pluginType === 'installed'
```

- [ ] **Step 2: 更新卡片内的标签显示**

找到卡片中显示来源标签的部分（约第283-298行）：

```typescript
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
```

替换为：

```typescript
<span
  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${pluginBadgeStyle}`}
>
  {showIcon && (pluginType === 'builtin' ? <Code2 className="h-3 w-3" /> : <Globe className="h-3 w-3" />)}
  {pluginDisplayName}
</span>
```

- [ ] **Step 3: 删除不再使用的 getSourceLabel 函数**

找到并删除 `getSourceLabel` 函数定义（约第17-22行）：

```typescript
function getSourceLabel(skill: Skill): { label: string; type: 'builtin' | 'installed' | 'local' } {
  if (skill.source) return { label: skill.source, type: 'installed' }
  if (skill.install_path?.includes('.reflexion')) return { label: '全局安装', type: 'installed' }
  if (skill.install_path?.includes('skills/')) return { label: '项目内置', type: 'builtin' }
  return { label: '本地', type: 'local' }
}
```

- [ ] **Step 4: 提交技能卡片更新**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat: update skill card to display plugin name instead of source type"
```

---

## Task 7: 添加加载更多按钮到页面

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 在技能列表后添加加载更多按钮**

找到技能列表网格结束的位置（约第367行的 `</div>` 后），在 `{filteredSkills.length === 0 ? ... : (...)}` 的最后一个分支末尾，网格容器 `</div>` 之后添加：

```typescript
          <div className="grid gap-4 md:grid-cols-2">
            {displayedSkills.map((skill) => {
              // ... 现有的卡片渲染代码
            })}
          </div>
          
          {/* 加载更多按钮 */}
          <LoadMoreButton hasMore={hasMore} onClick={handleLoadMore} />
```

- [ ] **Step 2: 验证完整的条件渲染逻辑**

确保完整的渲染逻辑是：

```typescript
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
          <>
            <div className="grid gap-4 md:grid-cols-2">
              {displayedSkills.map((skill) => {
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
                    {/* 现有的卡片 JSX */}
                  </div>
                )
              })}
            </div>
            
            <LoadMoreButton hasMore={hasMore} onClick={handleLoadMore} />
          </>
        )}
```

- [ ] **Step 3: 提交加载更多功能**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat: add load more button for skill pagination"
```

---

## Task 8: 测试和验证

**Files:**
- Test: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 启动开发服务器**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend
npm run dev
```

Expected: 前端开发服务器启动成功

- [ ] **Step 2: 手动测试插件筛选功能**

测试项：
1. 打开技能列表页面
2. 验证分类筛选和插件筛选在同一行显示，用竖线分隔
3. 点击不同的插件标签，验证技能列表正确筛选
4. 点击"更多"下拉菜单，验证其他插件显示正确
5. 组合使用分类筛选 + 插件筛选，验证结果正确

- [ ] **Step 3: 手动测试分页功能**

测试项：
1. 验证初始显示 24 个技能（如果总数超过 24）
2. 点击"加载更多"按钮，验证追加显示 12 个技能
3. 继续点击直到显示全部技能，验证按钮消失
4. 切换筛选条件，验证分页重置为前 24 个

- [ ] **Step 4: 手动测试技能卡片显示**

测试项：
1. 验证技能卡片显示插件名而不是来源类型
2. 验证内置插件显示绿色背景 + Code2 图标
3. 验证全局安装插件显示蓝色背景 + Globe 图标
4. 验证独立技能显示灰色背景 + "独立技能"文字

- [ ] **Step 5: 手动测试边缘情况**

测试项：
1. 搜索框输入关键词，验证筛选正确且分页重置
2. 技能总数少于 24 个时，验证不显示"加载更多"按钮
3. 没有技能时，验证显示空状态提示
4. 刷新技能列表后，验证插件筛选器更新正确

- [ ] **Step 6: 验证代码质量**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend
npm run lint
```

Expected: 无 ESLint 错误

- [ ] **Step 7: 提交测试通过的标记**

```bash
git add -A
git commit -m "test: verify plugin filter and pagination functionality"
```

---

## Task 9: 文档更新（可选）

**Files:**
- Modify: `docs/` (如果项目有文档目录)

- [ ] **Step 1: 更新功能文档**

如果项目有用户文档或开发文档，添加新功能说明：

- 插件筛选功能的使用方法
- 分页加载的行为说明
- 技能排序规则的说明

- [ ] **Step 2: 提交文档更新**

```bash
git add docs/
git commit -m "docs: update skills page documentation for new features"
```

---

## 完成检查清单

- [ ] 所有文件已创建和修改
- [ ] 所有测试通过
- [ ] UI 在不同屏幕尺寸下正常显示
- [ ] 插件筛选功能正常工作
- [ ] 分页加载功能正常工作
- [ ] 技能卡片显示插件名正确
- [ ] 没有控制台错误或警告
- [ ] 代码已通过 lint 检查
- [ ] 所有变更已提交到 git

---

## 后续优化建议（不在本计划范围内）

1. **性能优化**：如果技能数量非常大（1000+），考虑虚拟滚动
2. **持久化**：将用户的筛选偏好保存到 localStorage
3. **动画效果**：添加加载更多时的过渡动画
4. **键盘导航**：支持键盘快捷键切换筛选
5. **响应式优化**：在小屏幕上优化插件筛选器的显示方式

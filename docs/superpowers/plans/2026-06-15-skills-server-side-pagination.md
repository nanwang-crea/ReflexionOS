# 技能列表服务端分页实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将技能列表从前端分页改为服务端分页，并重构代码到 Feature-based 架构

**Architecture:** 后端处理筛选、排序、分页，前端使用累积模式加载数据，代码按 feature 组织

**Tech Stack:** Python (FastAPI), TypeScript (React), SQLAlchemy (skill registry)

---

## 文件结构概览

### 后端新建/修改
- Create: `backend/app/orchestration/skill_sorting.py` - 排序逻辑
- Modify: `backend/app/api/routes/skills.py` - API 端点

### 前端重构
- Move: `frontend/src/utils/skillSorting.ts` → `frontend/src/features/skills/utils/skillHelpers.ts`
- Move: `frontend/src/components/skills/*` → `frontend/src/features/skills/components/*`
- Create: `frontend/src/features/skills/hooks/useSkillList.ts`
- Modify: `frontend/src/features/skills/api/skill.api.ts`
- Modify: `frontend/src/pages/SkillsPage.tsx`

---

## Task 1: 后端排序工具函数

**Files:**
- Create: `backend/app/orchestration/skill_sorting.py`

- [ ] **Step 1: 创建排序工具文件**

创建 `backend/app/orchestration/skill_sorting.py`：

```python
from app.orchestration.skill_registry import SkillMetadata


def get_plugin_type(skill: SkillMetadata) -> str:
    """获取技能的插件类型"""
    if not skill.plugin_name:
        return 'independent'
    if not skill.install_path:
        return 'local'
    
    # 标准化路径
    normalized_path = skill.install_path.replace('\\', '/')
    if '/.reflexion/' in normalized_path:
        return 'installed'
    if normalized_path.endswith('/skills') or normalized_path.endswith('/skills/'):
        return 'builtin'
    return 'local'


def sort_skills(skills: list[SkillMetadata]) -> list[SkillMetadata]:
    """
    排序技能列表
    排序规则：插件类型 → 插件名 → 技能名
    """
    type_order = {
        'builtin': 0,
        'installed': 1,
        'local': 2,
        'independent': 3,
    }
    
    def sort_key(skill: SkillMetadata) -> tuple:
        plugin_type = get_plugin_type(skill)
        type_priority = type_order.get(plugin_type, 999)
        plugin_name = skill.plugin_name or ''
        skill_name = skill.name
        return (type_priority, plugin_name, skill_name)
    
    return sorted(skills, key=sort_key)
```

- [ ] **Step 2: 提交排序工具**

```bash
git add backend/app/orchestration/skill_sorting.py
git commit -m "feat(backend): add skill sorting utilities

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 后端分页 API

**Files:**
- Modify: `backend/app/api/routes/skills.py`

- [ ] **Step 1: 导入依赖并定义响应模型**

在 `backend/app/api/routes/skills.py` 文件顶部添加导入：

```python
from typing import Optional
from pydantic import BaseModel
from app.orchestration.skill_sorting import sort_skills
```

在路由定义之前添加响应模型：

```python
class SkillListResponse(BaseModel):
    items: list[dict]
    total: int
    offset: int
    limit: int
    has_more: bool
```

- [ ] **Step 2: 修改 list_skills 端点**

将现有的 `list_skills` 函数替换为：

```python
@router.get("/", response_model=SkillListResponse)
async def list_skills(
    offset: int = 0,
    limit: int = 24,
    category: Optional[str] = None,
    plugin_name: Optional[str] = None,
    search: Optional[str] = None,
):
    # 1. 获取所有技能
    all_skills = skill_registry.list_skills()
    
    # 2. 筛选
    filtered = all_skills
    
    # 分类筛选
    if category:
        filtered = [s for s in filtered if s.category == category]
    
    # 插件筛选
    if plugin_name:
        if plugin_name == "independent":
            filtered = [s for s in filtered if not s.plugin_name]
        else:
            filtered = [s for s in filtered if s.plugin_name == plugin_name]
    
    # 搜索筛选
    if search:
        q = search.lower()
        filtered = [
            s for s in filtered
            if q in s.name.lower() or q in s.description.lower()
        ]
    
    # 3. 排序
    sorted_skills = sort_skills(filtered)
    
    # 4. 分页
    total = len(sorted_skills)
    paginated = sorted_skills[offset:offset+limit]
    
    # 5. 序列化并返回
    return {
        "items": [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "required_skills": s.required_skills,
                "enabled": s.enabled,
                "source": s.source,
                "source_type": s.source_type.value if s.source_type else "",
                "install_path": s.install_path,
                "plugin_name": s.plugin_name,
                "version": s.version,
            }
            for s in paginated
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }
```

- [ ] **Step 3: 提交后端 API 改动**

```bash
git add backend/app/api/routes/skills.py
git commit -m "feat(backend): add pagination, filtering, and sorting to skills API

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: 测试后端 API**

启动后端服务并测试：

```bash
# 基本分页
curl "http://localhost:8000/api/skills/?offset=0&limit=5"

# 分类筛选
curl "http://localhost:8000/api/skills/?category=规范"

# 插件筛选
curl "http://localhost:8000/api/skills/?plugin_name=superpowers"

# 搜索
curl "http://localhost:8000/api/skills/?search=tdd"

# 组合筛选
curl "http://localhost:8000/api/skills/?category=规范&offset=0&limit=10"
```

Expected: 返回包含 `items`, `total`, `offset`, `limit`, `has_more` 的 JSON

---

## Task 3: 前端文件重构 - 移动工具函数

**Files:**
- Move: `frontend/src/utils/skillSorting.ts` → `frontend/src/features/skills/utils/skillHelpers.ts`
- Delete: `frontend/src/utils/skillSorting.ts`

- [ ] **Step 1: 创建 utils 目录**

```bash
mkdir -p frontend/src/features/skills/utils
```

- [ ] **Step 2: 创建 skillHelpers.ts**

创建 `frontend/src/features/skills/utils/skillHelpers.ts`，只保留显示相关函数：

```typescript
import type { Skill } from '@/types/skill'

export type PluginTypeKey = 'builtin' | 'installed' | 'local' | 'independent'

export type PluginInfo = {
  name: string
  displayName: string
  type: PluginTypeKey
  skillCount: number
}

/**
 * 获取技能的插件类型
 */
export function getPluginType(skill: Skill): PluginTypeKey {
  if (!skill.plugin_name) return 'independent'
  if (!skill.install_path) return 'local'

  const normalizedPath = skill.install_path.replace(/\\/g, '/')
  if (normalizedPath.includes('/.reflexion/')) return 'installed'
  if (normalizedPath.match(/\/skills\/?$/)) return 'builtin'
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
 * 注意：仅用于 UI 显示，不用于数据排序（后端处理）
 */
export function getPluginList(skills: Skill[]): PluginInfo[] {
  const pluginMap = new Map<string, PluginInfo>()
  const PLUGIN_TYPE_ORDER: Record<PluginTypeKey, number> = {
    builtin: 0,
    installed: 1,
    local: 2,
    independent: 3,
  }

  skills.forEach((skill) => {
    const type = getPluginType(skill)
    const name = skill.plugin_name || 'independent'
    const displayName = getPluginDisplayName(skill)

    if (!pluginMap.has(name)) {
      pluginMap.set(name, { name, displayName, type, skillCount: 0 })
    }
    const plugin = pluginMap.get(name)
    if (plugin) {
      plugin.skillCount++
    }
  })

  const plugins = Array.from(pluginMap.values())

  plugins.sort((a, b) => {
    const typeCompare = PLUGIN_TYPE_ORDER[a.type] - PLUGIN_TYPE_ORDER[b.type]
    if (typeCompare !== 0) return typeCompare
    return b.skillCount - a.skillCount
  })

  return plugins
}

/**
 * 获取优先显示的插件（前3-4个常用插件）
 */
export function getTopPlugins(plugins: PluginInfo[]): PluginInfo[] {
  const independent = plugins.find((p) => p.type === 'independent')
  const others = plugins.filter((p) => p.type !== 'independent')
  const topOthers = others.slice(0, 3)
  return independent ? [...topOthers, independent] : topOthers
}
```

- [ ] **Step 3: 删除旧文件**

```bash
git rm frontend/src/utils/skillSorting.ts
```

- [ ] **Step 4: 提交文件移动**

```bash
git add frontend/src/features/skills/utils/skillHelpers.ts
git commit -m "refactor(frontend): move skill utilities to features/skills

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 前端文件重构 - 移动组件

**Files:**
- Move: `frontend/src/components/skills/*` → `frontend/src/features/skills/components/*`

- [ ] **Step 1: 创建 components 目录**

```bash
mkdir -p frontend/src/features/skills/components
```

- [ ] **Step 2: 移动组件文件**

```bash
git mv frontend/src/components/skills/PluginFilter.tsx frontend/src/features/skills/components/
git mv frontend/src/components/skills/LoadMoreButton.tsx frontend/src/features/skills/components/
```

- [ ] **Step 3: 删除空目录**

```bash
rmdir frontend/src/components/skills
```

- [ ] **Step 4: 提交组件移动**

```bash
git commit -m "refactor(frontend): move skill components to features/skills

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 修改前端 API

**Files:**
- Modify: `frontend/src/features/skills/api/skill.api.ts`

- [ ] **Step 1: 添加类型定义**

在 `frontend/src/features/skills/api/skill.api.ts` 顶部添加：

```typescript
export interface SkillListParams {
  offset?: number
  limit?: number
  category?: string
  plugin_name?: string
  search?: string
}

export interface SkillListResponse {
  items: Skill[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}
```

- [ ] **Step 2: 修改 list 方法**

将 `list` 方法从：

```typescript
list: () => apiClient.get<Skill[]>('/api/skills'),
```

修改为：

```typescript
list: (params?: SkillListParams) => apiClient.get<SkillListResponse>('/api/skills', { params }),
```

- [ ] **Step 3: 提交 API 修改**

```bash
git add frontend/src/features/skills/api/skill.api.ts
git commit -m "feat(frontend): add pagination support to skills API

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 创建 useSkillList Hook

**Files:**
- Create: `frontend/src/features/skills/hooks/useSkillList.ts`

- [ ] **Step 1: 创建 hooks 目录**

```bash
mkdir -p frontend/src/features/skills/hooks
```

- [ ] **Step 2: 创建 useSkillList hook**

创建 `frontend/src/features/skills/hooks/useSkillList.ts`：

```typescript
import { useState, useEffect } from 'react'
import { skillApi } from '@/features/skills/api/skill.api'
import type { Skill } from '@/types/skill'
import { useToastStore } from '@/shared/stores/toastStore'

interface SkillFilters {
  category: string
  pluginName: string
  search: string
}

export function useSkillList() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  
  const [filters, setFilters] = useState<SkillFilters>({
    category: '全部',
    pluginName: 'all',
    search: ''
  })

  const loadSkills = async (reset = false) => {
    setLoading(true)
    try {
      const params = {
        offset: reset ? 0 : offset,
        limit: 24,
        category: filters.category !== '全部' ? filters.category : undefined,
        plugin_name: filters.pluginName !== 'all' ? filters.pluginName : undefined,
        search: filters.search || undefined
      }
      
      const res = await skillApi.list(params)
      
      if (reset) {
        setSkills(res.data.items)
        setOffset(res.data.offset + res.data.items.length)
      } else {
        setSkills([...skills, ...res.data.items])
        setOffset(offset + res.data.items.length)
      }
      
      setTotal(res.data.total)
      setHasMore(res.data.has_more)
    } catch (error) {
      console.error('Failed to load skills:', error)
      useToastStore.getState().addToast('warning', '加载技能列表失败')
    } finally {
      setLoading(false)
    }
  }

  const loadMore = () => {
    if (!loading && hasMore) {
      loadSkills(false)
    }
  }

  const updateFilters = (newFilters: Partial<SkillFilters>) => {
    setFilters({ ...filters, ...newFilters })
  }

  const refresh = () => {
    loadSkills(true)
  }

  // 筛选条件变化时重新加载
  useEffect(() => {
    loadSkills(true)
  }, [filters.category, filters.pluginName, filters.search])

  return {
    skills,
    loading,
    total,
    hasMore,
    filters,
    updateFilters,
    loadMore,
    refresh
  }
}
```

- [ ] **Step 3: 提交 hook**

```bash
git add frontend/src/features/skills/hooks/useSkillList.ts
git commit -m "feat(frontend): add useSkillList hook for paginated skill loading

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 重构 SkillsPage - 更新导入

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 更新导入语句**

在 `frontend/src/pages/SkillsPage.tsx` 中，将导入从：

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

修改为：

```typescript
import PluginFilter from '@/features/skills/components/PluginFilter'
import LoadMoreButton from '@/features/skills/components/LoadMoreButton'
import { useSkillList } from '@/features/skills/hooks/useSkillList'
import {
  getPluginList,
  getTopPlugins,
  getPluginType,
  getPluginDisplayName,
} from '@/features/skills/utils/skillHelpers'
```

- [ ] **Step 2: 提交导入更新**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "refactor(frontend): update imports to use features structure

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 重构 SkillsPage - 使用 useSkillList Hook

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 替换状态管理**

删除以下状态声明：

```typescript
const [skills, setSkills] = useState<Skill[]>([])
const [searchQuery, setSearchQuery] = useState('')
const [activeCategory, setActiveCategory] = useState('全部')
const [activePlugin, setActivePlugin] = useState<string>('all')
const [displayCount, setDisplayCount] = useState(24)
```

替换为：

```typescript
const {
  skills,
  loading: skillsLoading,
  total,
  hasMore,
  filters,
  updateFilters,
  loadMore,
  refresh: refreshSkills
} = useSkillList()

const [searchQuery, setSearchQuery] = useState('')
```

- [ ] **Step 2: 删除本地加载函数**

删除 `loadSkills` 函数和相关的 useEffect：

```typescript
// 删除这些代码
const loadSkills = async () => { ... }
useEffect(() => { loadSkills() }, [])
```

- [ ] **Step 3: 删除本地筛选和分页逻辑**

删除以下 useMemo：

```typescript
// 删除 filteredSkills, pluginList, topPlugins, displayedSkills
const filteredSkills = useMemo(() => { ... })
const pluginList = useMemo(() => getPluginList(skills), [skills])
const topPlugins = useMemo(() => getTopPlugins(pluginList), [pluginList])
const displayedSkills = useMemo(() => filteredSkills.slice(0, displayCount), [...])
const hasMore = displayCount < filteredSkills.length
const handleLoadMore = () => { setDisplayCount((prev) => prev + 12) }
```

删除筛选条件变化重置分页的 useEffect：

```typescript
// 删除这个
useEffect(() => {
  setDisplayCount(24)
}, [activeCategory, activePlugin, searchQuery])
```

- [ ] **Step 4: 添加新的计算逻辑**

在组件中添加：

```typescript
// 用于 PluginFilter 显示（基于当前已加载的技能）
const pluginList = useMemo(() => getPluginList(skills), [skills])
const topPlugins = useMemo(() => getTopPlugins(pluginList), [pluginList])

// 合并 loading 状态
const loading = skillsLoading || refreshing
```

- [ ] **Step 5: 更新事件处理函数**

修改分类切换：

```typescript
// 从
setActiveCategory(cat)
// 改为
updateFilters({ category: cat })
```

修改插件切换：

```typescript
// PluginFilter 的 onPluginChange 从
onPluginChange={setActivePlugin}
// 改为
onPluginChange={(plugin) => updateFilters({ pluginName: plugin })}
```

修改搜索（添加防抖）：

```typescript
useEffect(() => {
  const timer = setTimeout(() => {
    updateFilters({ search: searchQuery })
  }, 300)
  return () => clearTimeout(timer)
}, [searchQuery])
```

修改刷新按钮：

```typescript
// handleRefresh 函数中，从
await loadSkills()
// 改为
refreshSkills()
```

修改加载更多按钮：

```typescript
<LoadMoreButton hasMore={hasMore} onClick={loadMore} />
```

- [ ] **Step 6: 更新条件判断**

将所有 `filteredSkills.length` 改为 `total`（如果需要判断筛选后的结果数）

保持 `skills.length` 用于判断是否有已加载的技能

- [ ] **Step 7: 提交重构**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "refactor(frontend): use useSkillList hook in SkillsPage

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: 运行 Lint 检查

**Files:**
- Check: All modified frontend files

- [ ] **Step 1: 运行 ESLint**

```bash
cd frontend
npm run lint
```

Expected: 无错误

- [ ] **Step 2: 修复 Lint 错误（如果有）**

根据 ESLint 输出修复错误，常见问题：
- 未使用的导入
- 未使用的变量
- 类型错误

- [ ] **Step 3: 提交 Lint 修复**

```bash
git add frontend/
git commit -m "fix(frontend): resolve lint errors

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: 测试和验证

**Files:**
- Test: 所有改动的文件

- [ ] **Step 1: 启动后端服务**

```bash
cd backend
python -m app.main
```

Expected: 服务运行在 http://localhost:8000

- [ ] **Step 2: 启动前端服务**

```bash
cd frontend
npm run dev
```

Expected: 服务运行在 http://localhost:5173

- [ ] **Step 3: 手动功能测试**

测试清单：

**基本功能：**
- [ ] 页面初始加载显示前 24 个技能
- [ ] 技能按插件类型排序（内置 → 全局 → 本地 → 独立）
- [ ] 技能卡片显示正确的插件名和图标

**分页功能：**
- [ ] 点击"加载更多"追加显示 12 个技能
- [ ] 继续加载直到全部显示，按钮消失
- [ ] 技能总数 < 24 时不显示"加载更多"按钮

**筛选功能：**
- [ ] 分类筛选工作正常
- [ ] 插件筛选工作正常
- [ ] 搜索筛选工作正常（有 300ms 防抖）
- [ ] 组合筛选工作正常

**筛选后分页：**
- [ ] 切换分类后，列表重置并显示前 24 个
- [ ] 切换插件后，列表重置并显示前 24 个
- [ ] 输入搜索词后，列表重置并显示前 24 个

**边缘情况：**
- [ ] 搜索无结果时显示空状态
- [ ] 刷新按钮正常工作
- [ ] 网络错误显示 Toast 提示

- [ ] **Step 4: 检查控制台**

打开浏览器开发者工具，确认：
- 无 JavaScript 错误
- API 请求带正确的查询参数
- API 响应格式正确

- [ ] **Step 5: 提交测试通过标记**

```bash
git commit --allow-empty -m "test: verify server-side pagination functionality

All manual tests passed:
- Initial load shows 24 skills
- Load more appends 12 skills
- Filtering resets pagination
- Plugin filter displays correctly
- Search with debounce works
- Edge cases handled

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: 清理和文档

**Files:**
- Delete: `docs/superpowers/specs/2026-06-15-skills-server-side-pagination-design.md`

- [ ] **Step 1: 删除设计文档**

```bash
git rm docs/superpowers/specs/2026-06-15-skills-server-side-pagination-design.md
git commit -m "docs: remove implementation design doc (replaced by plan)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 2: 查看最终状态**

```bash
git log --oneline -10
```

Expected: 看到本次实施的所有提交

---

## 完成标准

- ✅ 后端 API 支持分页、筛选、排序
- ✅ 前端代码重构到 `features/skills/` 目录
- ✅ 使用 `useSkillList` hook 管理状态
- ✅ 所有功能正常工作
- ✅ 通过 ESLint 检查
- ✅ 所有手动测试通过

---

**实施完成！** 🎉


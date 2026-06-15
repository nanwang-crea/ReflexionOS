# 技能列表服务端分页设计文档

**日期：** 2026-06-15  
**作者：** Claude Opus 4.8  
**状态：** 实施中

---

## 目标

将技能列表从前端分页改为服务端分页，提升性能和可扩展性，同时重构代码到 Feature-based 架构。

## 背景

**当前问题：**
- 前端一次性加载所有技能，然后在内存中筛选、排序、分页
- 技能数量增多时性能下降
- 代码分散在多个目录，不符合 Feature-based 架构

**改进目标：**
- 后端处理筛选、排序、分页
- 前端只加载当前需要显示的数据
- 重构代码到 `src/features/skills/` 目录

---

## 架构设计

### 数据存储策略

**保持文件系统 + 内存方式**（不使用数据库）

**理由：**
- 技能是配置性数据，由开发者创建，需要版本控制
- 数量不大（几十到几百个），内存处理足够快
- 保持简单，避免双重真相源

### 处理流程

```
用户请求（带筛选参数）
    ↓
后端 API 接收参数
    ↓
1. 获取所有技能（从内存）
    ↓
2. 筛选（分类、插件、搜索）
    ↓
3. 排序（插件类型 → 插件名 → 技能名）
    ↓
4. 分页切片
    ↓
返回 { items, total, offset, limit, has_more }
    ↓
前端累积显示（"加载更多"追加）
```

---

## API 设计

### 端点

`GET /api/skills/`

### 查询参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `offset` | int | 0 | 偏移量 |
| `limit` | int | 24 | 每页大小 |
| `category` | str? | None | 分类筛选（不传或传"全部"表示不筛选） |
| `plugin_name` | str? | None | 插件筛选（"independent"表示独立技能，不传或"all"表示不筛选） |
| `search` | str? | None | 搜索关键词（在名称和描述中搜索） |

### 响应格式

```json
{
  "items": [
    {
      "name": "skill-name",
      "description": "技能描述",
      "category": "规范",
      "plugin_name": "superpowers",
      "source_type": "global",
      "enabled": true,
      ...
    }
  ],
  "total": 150,
  "offset": 0,
  "limit": 24,
  "has_more": true
}
```

### 排序规则

1. **按插件类型**：内置 (builtin) → 全局安装 (installed) → 本地 (local) → 独立 (independent)
2. **同类型内按插件名**：字母排序
3. **同插件内按技能名**：字母排序

---

## 前端架构重构

### Feature-based 目录结构

```
src/features/skills/
├── api/
│   └── skill.api.ts           # API 调用（修改：支持分页参数）
├── components/                 # 从 src/components/skills 移动
│   ├── PluginFilter.tsx
│   └── LoadMoreButton.tsx
├── hooks/                      # 新建
│   └── useSkillList.ts        # 分页加载逻辑封装
└── utils/                      # 从 src/utils 移动
    └── skillHelpers.ts        # 只保留显示相关函数（getPluginType, getPluginDisplayName）
```

### 状态管理策略

**累积模式（"加载更多"）：**
- 前端维护已加载的技能列表
- 每次"加载更多"追加新数据
- 切换筛选条件时清空列表重新加载

**状态结构：**
```typescript
{
  skills: Skill[]         // 已加载的技能（累积）
  loading: boolean
  total: number           // 筛选后的总数
  offset: number          // 当前偏移量
  hasMore: boolean        // 是否还有更多
  filters: {
    category: string
    plugin_name: string
    search: string
  }
}
```

---

## 实施计划

### 后端改动

1. **新建** `backend/app/orchestration/skill_sorting.py`
   - 实现排序逻辑（从前端移植）
   - 函数：`get_plugin_type()`, `sort_skills()`

2. **修改** `backend/app/api/routes/skills.py`
   - 添加查询参数
   - 实现筛选、排序、分页逻辑
   - 返回新的响应格式

### 前端改动

#### Phase 1: 文件重构
1. 移动 `src/utils/skillSorting.ts` → `src/features/skills/utils/skillHelpers.ts`
   - 删除排序相关函数（后端处理）
   - 保留 `getPluginType`, `getPluginDisplayName`（UI 显示用）

2. 移动 `src/components/skills/*` → `src/features/skills/components/*`

#### Phase 2: API 和 Hook
3. 修改 `src/features/skills/api/skill.api.ts`
   - 添加分页参数类型
   - 更新响应类型

4. 创建 `src/features/skills/hooks/useSkillList.ts`
   - 封装分页加载逻辑
   - 管理筛选状态
   - 提供 `loadMore`, `updateFilters`, `refresh` 方法

#### Phase 3: 页面简化
5. 重构 `src/pages/SkillsPage.tsx`
   - 使用 `useSkillList` hook
   - 删除本地筛选/排序/分页逻辑
   - 保持 UI 布局不变

6. 删除不再需要的代码
   - `src/utils/skillSorting.ts`（已移动）
   - `src/components/skills/`（已移动）
   - SkillsPage 中的 `filteredSkills`, `displayedSkills`, `displayCount` 等

#### Phase 4: 更新导入路径
7. 更新所有导入路径，从旧位置指向新的 feature 结构

---

## 向后兼容性

**API 兼容性：**
- 如果不传分页参数，默认返回前 24 个
- 响应格式改变，前端必须同步更新

**前端兼容性：**
- 重大重构，需要一次性完成
- 建议在独立分支开发，测试通过后合并

---

## 测试计划

### 后端测试
1. 单元测试：排序函数
2. 集成测试：筛选 + 排序 + 分页组合
3. 边缘情况：空结果、单个结果、大量结果

### 前端测试
1. 功能测试：
   - 初始加载显示前 24 个
   - "加载更多"追加 12 个
   - 筛选条件改变时重置列表
   - 插件筛选器显示正确
2. 边缘情况：
   - 技能总数 < 24
   - 搜索无结果
   - 网络错误处理

---

## 风险和缓解

### 风险 1: 前端大规模重构
- **影响：** 可能引入 bug
- **缓解：** 
  - 在独立分支开发
  - 充分测试后再合并
  - 保留旧代码作为回滚备份

### 风险 2: 排序逻辑不一致
- **影响：** 前后端排序不同导致显示混乱
- **缓解：**
  - 从前端直接移植排序逻辑
  - 添加测试用例验证一致性

---

## 后续优化

1. **缓存优化**：如果技能数量非常大，可以缓存排序结果
2. **虚拟滚动**：如果单次加载的技能很多，可以考虑虚拟滚动
3. **搜索优化**：可以添加模糊搜索或高亮显示

---

## 完成标准

- ✅ 后端 API 支持分页参数并返回正确响应
- ✅ 前端代码重构到 `features/skills/` 目录
- ✅ 使用 `useSkillList` hook 管理状态
- ✅ 所有功能正常工作（筛选、排序、分页）
- ✅ 通过 ESLint 检查
- ✅ 手动测试所有用户场景

---

## 参考

- 当前实现：`frontend/src/pages/SkillsPage.tsx`
- 后端 API：`backend/app/api/routes/skills.py`
- 技能注册表：`backend/app/orchestration/skill_registry.py`

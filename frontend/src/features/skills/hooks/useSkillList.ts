/**
 * 文件功能：技能列表数据加载 Hook
 * 文件描述：封装技能列表的分页拉取逻辑，支持按分类/插件名/关键字过滤，并提供“加载更多”与“刷新”方法。
 * 核心逻辑：内部维护 skills/offset/hasMore 等状态；filter 变化时重置到第一页重新加载；
 *           loadMore 在当前 offset 基础上追加下一页数据。
 */
import { useState, useEffect, useCallback } from 'react'
import { skillApi, type SkillListParams } from '../api/skill.api'
import type { Skill } from '@/types/skill'

const ITEMS_PER_PAGE = 20

interface UseSkillListOptions {
  category?: string
  pluginName?: string
  search?: string
}

interface UseSkillListReturn {
  skills: Skill[]
  loading: boolean
  error: Error | null
  total: number
  hasMore: boolean
  loadMore: () => void
  refresh: () => void
}

/**
 * 函数名：useSkillList
 * 入参：
 *   - options (UseSkillListOptions): 过滤条件，包含 category（分类）、pluginName（插件名）、search（搜索关键字），默认为空对象
 * 功能：拉取并维护技能列表状态，支持分页加载与刷新
 * 运行逻辑：
 *   1. 内部定义 loadSkills(currentOffset)：请求指定 offset 的一页数据；offset 为 0 时覆盖列表，否则追加到列表末尾
 *   2. useEffect 监听 category/pluginName/search 变化，变化时重置 offset 为 0 并重新加载（覆盖式）
 *   3. loadMore：仅在非加载中且还有更多数据时，用当前 offset 继续加载下一页
 *   4. refresh：重置 offset 为 0 并重新加载（用于手动刷新列表）
 * 出参：UseSkillListReturn - { skills, loading, error, total, hasMore, loadMore, refresh }
 */
export function useSkillList(options: UseSkillListOptions = {}): UseSkillListReturn {
  const { category, pluginName, search } = options

  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)

  /**
   * 函数名：loadSkills（内部函数）
   * 入参：
   *   - currentOffset (number): 本次请求的分页偏移量
   * 功能：向后端请求一页技能数据，并根据 offset 决定覆盖或追加到现有列表
   * 运行逻辑：拼装请求参数（分页 + 过滤条件）-> 调用 skillApi.list -> 校验响应格式 ->
   *          offset 为 0 时覆盖 skills，否则追加 -> 更新 total/hasMore/offset -> 捕获异常写入 error
   * 出参：Promise<void>（通过 setSkills/setError 等状态更新副作用体现结果）
   */
  const loadSkills = async (currentOffset: number) => {
    setLoading(true)
    setError(null)

    try {
      const params: SkillListParams = {
        offset: currentOffset,
        limit: ITEMS_PER_PAGE,
      }

      if (category) params.category = category
      if (pluginName) params.plugin_name = pluginName
      if (search) params.search = search

      const response = await skillApi.list(params)

      // 检查响应格式
      if (!response.data || !response.data.items) {
        throw new Error('Invalid API response format')
      }

      if (currentOffset === 0) {
        setSkills(response.data.items)
      } else {
        setSkills(prev => [...prev, ...response.data.items])
      }

      setTotal(response.data.total)
      setHasMore(response.data.has_more)
      setOffset(currentOffset + response.data.items.length)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to load skills'))
    } finally {
      setLoading(false)
    }
  }

  // Load initial data when filters change
  useEffect(() => {
    setOffset(0)
    loadSkills(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, pluginName, search])

  /**
   * 函数名：loadMore（暴露给调用方）
   * 入参：无
   * 功能：加载下一页技能数据（追加到现有列表末尾）
   * 运行逻辑：仅在当前不处于加载中且确实还有更多数据时，以当前 offset 调用 loadSkills
   * 出参：void
   */
  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      loadSkills(offset)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, hasMore, offset])

  /**
   * 函数名：refresh（暴露给调用方）
   * 入参：无
   * 功能：重新从第一页开始加载技能列表
   * 运行逻辑：将 offset 重置为 0，并重新调用 loadSkills(0) 覆盖现有列表
   * 出参：void
   */
  const refresh = useCallback(() => {
    setOffset(0)
    loadSkills(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    skills,
    loading,
    error,
    total,
    hasMore,
    loadMore,
    refresh,
  }
}

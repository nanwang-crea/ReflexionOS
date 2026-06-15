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

export function useSkillList(options: UseSkillListOptions = {}): UseSkillListReturn {
  const { category, pluginName, search } = options

  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)

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

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      loadSkills(offset)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, hasMore, offset])

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

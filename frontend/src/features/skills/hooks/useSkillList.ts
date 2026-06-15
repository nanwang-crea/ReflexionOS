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

  const loadSkills = useCallback(async (resetOffset: boolean = false) => {
    setLoading(true)
    setError(null)

    try {
      const currentOffset = resetOffset ? 0 : offset
      const params: SkillListParams = {
        offset: currentOffset,
        limit: ITEMS_PER_PAGE,
      }

      if (category) params.category = category
      if (pluginName) params.plugin_name = pluginName
      if (search) params.search = search

      const response = await skillApi.list(params)

      if (resetOffset) {
        setSkills(response.data.items)
      } else {
        setSkills(prev => [...prev, ...response.data.items])
      }

      setTotal(response.data.total)
      setHasMore(response.data.has_more)
      setOffset(response.data.offset + response.data.items.length)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to load skills'))
    } finally {
      setLoading(false)
    }
  }, [offset, category, pluginName, search])

  // Load initial data when filters change
  useEffect(() => {
    setOffset(0)
    loadSkills(true)
  }, [category, pluginName, search, loadSkills])

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      loadSkills(false)
    }
  }, [loading, hasMore, loadSkills])

  const refresh = useCallback(() => {
    setOffset(0)
    loadSkills(true)
  }, [loadSkills])

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

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

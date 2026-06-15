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

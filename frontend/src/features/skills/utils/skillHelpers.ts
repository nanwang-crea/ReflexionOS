/**
 * 文件功能：技能（Skill）与插件（Plugin）关系的辅助函数集合
 * 文件描述：根据技能的插件归属信息推导插件类型/显示名称，并汇总生成用于 UI 筛选展示的插件列表。
 * 核心逻辑：仅依据 skill.plugin_name / skill.install_path 做纯前端推断，不涉及网络请求；
 *           插件排序优先级固定为 builtin > installed > local > independent。
 */
import type { Skill } from '@/types/skill'

export type PluginTypeKey = 'builtin' | 'installed' | 'local' | 'independent'

export type PluginInfo = {
  name: string
  displayName: string
  type: PluginTypeKey
  skillCount: number
}

/**
 * 函数名：getPluginType
 * 入参：
 *   - skill (Skill): 技能对象，需包含 plugin_name / install_path 字段
 * 功能：获取技能的插件类型
 * 运行逻辑：
 *   1. 无 plugin_name 视为独立技能（independent）
 *   2. 有 plugin_name 但无 install_path 视为本地插件（local）
 *   3. 归一化路径分隔符后，路径含 /.reflexion/ 视为已安装插件（installed）
 *   4. 路径以 /skills 结尾视为内置插件（builtin），其余情况归为本地插件（local）
 * 出参：PluginTypeKey - 插件类型（'builtin' | 'installed' | 'local' | 'independent'）
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
 * 函数名：getPluginDisplayName
 * 入参：
 *   - skill (Skill): 技能对象，需包含 plugin_name 字段
 * 功能：获取技能所属插件的显示名称
 * 运行逻辑：无 plugin_name 时返回固定文案“独立技能”，否则直接返回 plugin_name
 * 出参：string - 插件显示名称
 */
export function getPluginDisplayName(skill: Skill): string {
  if (!skill.plugin_name) return '独立技能'
  return skill.plugin_name
}

/**
 * 函数名：getPluginList
 * 入参：
 *   - skills (Skill[]): 技能列表
 * 功能：从技能列表中汇总出所有插件信息（名称、显示名、类型、技能数量），并按优先级排序
 * 运行逻辑：
 *   1. 技能列表为空时直接返回空数组
 *   2. 遍历技能，按 plugin_name（无则用 'independent'）分组统计每个插件的技能数量
 *   3. 按 PLUGIN_TYPE_ORDER（builtin > installed > local > independent）排序，
 *      同类型下按技能数量从多到少排序
 * 出参：PluginInfo[] - 排序后的插件信息列表
 * 注意：仅用于 UI 显示，不用于数据排序（后端处理）
 */
export function getPluginList(skills: Skill[]): PluginInfo[] {
  if (!skills || skills.length === 0) {
    return []
  }

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
 * 函数名：getTopPlugins
 * 入参：
 *   - plugins (PluginInfo[]): 已排序的完整插件信息列表（通常来自 getPluginList 的返回值）
 * 功能：从完整插件列表中挑选出优先展示的常用插件（前 3 个非独立插件 + 独立技能项）
 * 运行逻辑：
 *   1. 找出 type 为 'independent' 的那一项（如果存在）
 *   2. 从其余插件中取前 3 个
 *   3. 若存在独立技能项，则拼在末尾一并返回；否则只返回前 3 个
 * 出参：PluginInfo[] - 用于优先展示的插件列表（最多 4 项）
 */
export function getTopPlugins(plugins: PluginInfo[]): PluginInfo[] {
  const independent = plugins.find((p) => p.type === 'independent')
  const others = plugins.filter((p) => p.type !== 'independent')
  const topOthers = others.slice(0, 3)
  return independent ? [...topOthers, independent] : topOthers
}

/**
 * 文件功能：技能列表的插件筛选栏组件
 * 文件描述：展示“所有插件”按钮、常用插件快捷按钮，以及其余插件的“更多”下拉菜单，
 *           用于按插件来源筛选技能列表。
 * 核心逻辑：topPlugins 直接以按钮形式展示；不在 topPlugins 中的插件归入 morePlugins，
 *           通过下拉菜单展示；点击外部区域会自动收起下拉菜单。
 */
import { ChevronDown } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import type { PluginInfo } from '@/features/skills/utils/skillHelpers'

interface PluginFilterProps {
  plugins: PluginInfo[]
  topPlugins: PluginInfo[]
  activePlugin: string
  onPluginChange: (plugin: string) => void
}

/**
 * 函数名：PluginFilter
 * 入参：
 *   - plugins (PluginInfo[]): 全部插件信息列表
 *   - topPlugins (PluginInfo[]): 优先展示的常用插件列表（作为独立按钮展示）
 *   - activePlugin (string): 当前选中的插件名（'all' 表示不筛选）
 *   - onPluginChange ((plugin: string) => void): 切换插件筛选时触发的回调
 * 功能：渲染插件筛选栏，包含“所有插件”按钮、常用插件按钮组，以及其余插件的“更多”下拉菜单
 * 运行逻辑：
 *   1. 用 useState 维护下拉菜单展开状态，useRef + useEffect 监听全局 mousedown 实现点击外部自动收起
 *   2. 用 plugins 过滤掉已在 topPlugins 中出现的插件，得到 morePlugins
 *   3. 渲染时根据 activePlugin 是否匹配来高亮对应按钮，点击按钮调用 onPluginChange 通知外部切换筛选
 * 出参：JSX.Element - 插件筛选栏
 */
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

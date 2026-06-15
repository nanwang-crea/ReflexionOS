import { ChevronDown } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import type { PluginInfo } from '@/features/skills/utils/skillHelpers'

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

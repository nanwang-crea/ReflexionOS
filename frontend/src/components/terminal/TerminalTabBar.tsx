/**
 * 文件功能：终端面板的标签栏组件
 * 文件描述：展示所有已打开的终端实例标签，支持切换/关闭单个终端、新建终端，以及关闭整个终端面板
 * 核心逻辑：从 terminal.store 读取实例列表与当前激活项，新建终端时读取当前项目路径作为工作目录
 */
import { Plus, X } from 'lucide-react'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'
import { useProjectStore } from '@/features/projects/stores/project.store'

interface TerminalTabBarProps {
  onClosePanel: () => void
}

/**
 * 组件名：TerminalTabBar
 * 入参（props）：
 *   - onClosePanel (() => void): 关闭整个终端面板时的回调
 * 作用/渲染逻辑：
 *   1. 从 store 中读取终端实例列表、当前激活的终端 ID，以及切换/关闭/新建终端的方法
 *   2. 遍历实例渲染标签：点击切换激活终端，标签自带关闭按钮（悬浮显示），已退出的终端标签置灰
 *   3. 提供“新建终端”按钮（以当前项目路径为工作目录）与“关闭面板”按钮
 * 返回值：JSX.Element - 终端标签栏
 */
export function TerminalTabBar({ onClosePanel }: TerminalTabBarProps) {
  const instances = useTerminalStore((s) => s.instances)
  const activeTerminalId = useTerminalStore((s) => s.activeTerminalId)
  const setActiveTerminal = useTerminalStore((s) => s.setActiveTerminal)
  const closeTerminal = useTerminalStore((s) => s.closeTerminal)
  const createTerminal = useTerminalStore((s) => s.createTerminal)

  // 新建终端：使用当前项目路径作为初始工作目录（无当前项目时为空字符串）
  const handleNew = () => {
    const cwd = useProjectStore.getState().currentProject?.path ?? ''
    createTerminal(cwd)
  }

  return (
    <div className="flex items-center justify-between bg-surface-secondary border-b border-edge-subtle px-2 py-1">
      <div className="flex items-center gap-1 overflow-x-auto">
        {instances.map((inst) => (
          <div
            key={inst.id}
            className={`group flex items-center gap-1 rounded-md px-2.5 py-1 text-xs cursor-pointer whitespace-nowrap transition-colors ${
              inst.id === activeTerminalId
                ? 'bg-surface-tertiary text-content-primary font-medium'
                : 'text-content-muted hover:text-content-secondary hover:bg-surface-tertiary/50'
            } ${inst.exited ? 'opacity-50' : ''}`}
            onClick={() => setActiveTerminal(inst.id)}
          >
            <span>{inst.title}{inst.exited ? ' (已退出)' : ''}</span>
            <button
              type="button"
              className="hidden group-hover:inline-flex text-content-muted hover:text-content-primary"
              onClick={(e) => {
                e.stopPropagation()
                closeTerminal(inst.id)
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        <button
          type="button"
          className="rounded-md p-1 text-content-muted hover:text-content-primary hover:bg-surface-tertiary/50"
          onClick={handleNew}
          title="新建终端"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <button
        type="button"
        className="rounded-md p-1 text-content-muted hover:text-content-primary hover:bg-surface-tertiary/50"
        onClick={onClosePanel}
        title="关闭面板"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

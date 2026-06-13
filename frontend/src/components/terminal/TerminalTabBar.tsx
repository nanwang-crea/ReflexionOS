import { Plus, X } from 'lucide-react'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'
import { useProjectStore } from '@/features/projects/stores/project.store'

interface TerminalTabBarProps {
  onClosePanel: () => void
}

export function TerminalTabBar({ onClosePanel }: TerminalTabBarProps) {
  const instances = useTerminalStore((s) => s.instances)
  const activeTerminalId = useTerminalStore((s) => s.activeTerminalId)
  const setActiveTerminal = useTerminalStore((s) => s.setActiveTerminal)
  const closeTerminal = useTerminalStore((s) => s.closeTerminal)
  const createTerminal = useTerminalStore((s) => s.createTerminal)

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

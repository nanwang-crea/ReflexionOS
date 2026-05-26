import { Plus, X } from 'lucide-react'
import { useTerminalStore } from '@/features/terminal/terminalStore'

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
    const cwd = instances.length > 0 ? instances[0].cwd : ''
    createTerminal(cwd)
  }

  return (
    <div className="flex items-center justify-between bg-[#16213e] px-2 py-1">
      <div className="flex items-center gap-1 overflow-x-auto">
        {instances.map((inst) => (
          <div
            key={inst.id}
            className={`group flex items-center gap-1 rounded px-2 py-0.5 text-xs cursor-pointer whitespace-nowrap ${
              inst.id === activeTerminalId
                ? 'bg-[#0f3460] text-white'
                : 'text-slate-400 hover:text-slate-200'
            } ${inst.exited ? 'opacity-50' : ''}`}
            onClick={() => setActiveTerminal(inst.id)}
          >
            <span>{inst.title}{inst.exited ? ' (已退出)' : ''}</span>
            <button
              type="button"
              className="hidden group-hover:inline-flex text-slate-400 hover:text-white"
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
          className="rounded p-0.5 text-slate-400 hover:text-slate-200"
          onClick={handleNew}
          title="新建终端"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <button
        type="button"
        className="rounded p-0.5 text-slate-400 hover:text-slate-200"
        onClick={onClosePanel}
        title="关闭面板"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

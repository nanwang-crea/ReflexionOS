import { useCallback, useRef } from 'react'
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { TerminalTabBar } from './TerminalTabBar'
import { TerminalInstance } from './TerminalInstance'

export function TerminalPanel() {
  const instances = useTerminalStore((s) => s.instances)
  const activeTerminalId = useTerminalStore((s) => s.activeTerminalId)
  const panelVisible = useTerminalStore((s) => s.panelVisible)
  const panelHeight = useTerminalStore((s) => s.panelHeight)
  const togglePanel = useTerminalStore((s) => s.togglePanel)
  const setPanelHeight = useTerminalStore((s) => s.setPanelHeight)

  const isDragging = useRef(false)
  const dragStartY = useRef(0)
  const dragStartHeight = useRef(0)

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      isDragging.current = true
      dragStartY.current = e.clientY
      dragStartHeight.current = panelHeight

      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (!isDragging.current) return
        const delta = dragStartY.current - moveEvent.clientY
        const newHeight = dragStartHeight.current + delta
        setPanelHeight(newHeight)
      }

      const handleMouseUp = () => {
        isDragging.current = false
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
      }

      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    },
    [panelHeight, setPanelHeight],
  )

  return (
    <div
      style={{ height: panelVisible ? panelHeight : 0 }}
      className="flex flex-col flex-shrink-0 overflow-hidden"
    >
      <div
        className="h-1 bg-accent cursor-row-resize hover:h-1.5 transition-all flex-shrink-0"
        onMouseDown={handleMouseDown}
      />
      <TerminalTabBar onClosePanel={togglePanel} />
      <div className="flex-1 overflow-hidden bg-terminal-bg relative">
        {instances.length === 0 ? (
          <div className="flex h-full items-center justify-center text-slate-500 text-sm">
            没有活动的终端
          </div>
        ) : (
          instances.map((inst) => (
            <div
              key={inst.id}
              className="absolute inset-0"
              style={{ display: inst.id === activeTerminalId ? 'block' : 'none' }}
            >
              <TerminalInstance terminalId={inst.id} />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

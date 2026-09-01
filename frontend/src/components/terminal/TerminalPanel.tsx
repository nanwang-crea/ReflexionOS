/**
 * 文件功能：终端面板容器组件
 * 文件描述：承载终端标签栏与所有终端实例的可拖拽调整高度的面板，负责面板显隐、高度拖拽调整、终端实例的挂载与切换显示
 * 核心逻辑：所有终端实例始终挂载在 DOM 中（避免重新创建 PTY 连接），通过 display 样式仅显示当前激活的终端；
 *          面板高度通过顶部拖拽条监听鼠标移动实现调整
 */
import { useCallback, useRef } from 'react'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'
import { TerminalTabBar } from './TerminalTabBar'
import { TerminalInstance } from './TerminalInstance'

/**
 * 组件名：TerminalPanel
 * 入参：无（props 为空，所有状态从 terminal.store 读取）
 * 作用/渲染逻辑：
 *   1. 从 store 读取终端实例列表、当前激活终端、面板可见性与高度等状态
 *   2. 顶部拖拽条通过 handleMouseDown 触发拖拽调整面板高度（监听 mousemove/mouseup 计算增量高度）
 *   3. 中部渲染 TerminalTabBar 标签栏
 *   4. 底部区域：无终端实例时展示占位提示；否则渲染所有终端实例（全部挂载，仅通过 display 控制哪个可见）
 * 返回值：JSX.Element - 完整的终端面板（拖拽条 + 标签栏 + 终端实例容器）
 */
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

  // 拖拽调整面板高度：记录起始鼠标位置与起始高度，随鼠标移动计算增量并更新高度，鼠标松开时清理监听
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
      className="flex flex-col flex-shrink-0 overflow-hidden border-t border-edge"
    >
      <div
        className="h-1 cursor-row-resize hover:h-1.5 transition-all flex-shrink-0 bg-surface-tertiary hover:bg-accent/40"
        onMouseDown={handleMouseDown}
      />
      <TerminalTabBar onClosePanel={togglePanel} />
      <div className="flex-1 overflow-hidden bg-terminal-bg relative">
        {instances.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-content-muted">
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

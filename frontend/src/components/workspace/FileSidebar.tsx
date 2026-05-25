import { useCallback, useEffect, useRef, useState } from 'react'
import { GripVertical, PanelLeftClose, RefreshCw } from 'lucide-react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { useProjectStore } from '@/stores/projectStore'
import { FileTreeItem } from './FileTreeItem'
import type { FileTreeNode } from '@/types/fileTree'

export function FileSidebar() {
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const sidebarWidth = useCodeTabStore((s) => s.sidebarWidth)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const setSidebarWidth = useCodeTabStore((s) => s.setSidebarWidth)
  const currentProject = useProjectStore((s) => s.currentProject)

  const [tree, setTree] = useState<FileTreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const resizingRef = useRef(false)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)

  useEffect(() => {
    if (!currentProject || !sidebarOpen) return
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        const resp = await fileApi.getTree(currentProject!.id)
        if (cancelled) return
        setTree(resp.data.tree)
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load file tree:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [currentProject, sidebarOpen])

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizingRef.current = true
    startXRef.current = e.clientX
    startWidthRef.current = sidebarWidth

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!resizingRef.current) return
      const delta = startXRef.current - moveEvent.clientX
      setSidebarWidth(startWidthRef.current - delta)
    }

    const onMouseUp = () => {
      resizingRef.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [sidebarWidth, setSidebarWidth])

  if (!sidebarOpen) return null

  return (
    <div className="relative flex h-full flex-col border-r border-gray-200 bg-white" style={{ width: sidebarWidth }}>
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
          文件
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              if (!currentProject) return
              setLoading(true)
              fileApi.getTree(currentProject.id)
                .then((resp) => setTree(resp.data.tree))
                .catch((err) => console.error('Refresh failed:', err))
                .finally(() => setLoading(false))
            }}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            title="刷新"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            title="收起文件栏"
          >
            <PanelLeftClose className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {!currentProject ? (
          <div className="px-3 py-4 text-xs text-slate-400">请先选择项目</div>
        ) : loading ? (
          <div className="px-3 py-4 text-xs text-slate-400">加载中...</div>
        ) : (
          tree.map((node) => (
            <FileTreeItem key={node.path} node={node} depth={0} />
          ))
        )}
      </div>

      <div
        onMouseDown={handleResizeMouseDown}
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize group"
        title="拖拽调整宽度"
      >
        <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-sm bg-transparent p-0.5 opacity-0 group-hover:opacity-100 group-hover:bg-slate-200 transition-opacity">
          <GripVertical className="h-3 w-3 text-slate-400" />
        </div>
      </div>
    </div>
  )
}

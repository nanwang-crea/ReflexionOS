import { useEffect, useState } from 'react'
import { PanelLeftClose, PanelLeftOpen, RefreshCw } from 'lucide-react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { useProjectStore } from '@/stores/projectStore'
import { FileTreeItem } from './FileTreeItem'
import type { FileTreeNode } from '@/types/fileTree'

export function FileSidebar() {
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const currentProject = useProjectStore((s) => s.currentProject)

  const [tree, setTree] = useState<FileTreeNode[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!currentProject) return
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
  }, [currentProject])

  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center border-r border-gray-200 bg-white py-3">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          title="展开文件栏"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
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
    </div>
  )
}

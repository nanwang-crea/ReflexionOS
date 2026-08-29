/**
 * 文件功能：文件侧边栏
 * 文件描述：展示当前项目的文件树 / Git 变更两个标签视图，支持刷新、收起、拖拽调整宽度
 * 核心逻辑：项目或侧边栏打开状态变化时异步加载文件树；宽度调整通过监听全局 mousemove/mouseup
 *          实现拖拽手柄逻辑；'文件'/'变更' 两个 tab 分别渲染 FileTreeItem 列表或 GitChangesTab
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { GripVertical, PanelRightClose, RefreshCw } from 'lucide-react'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'
import { useGitStore } from '@/features/git/stores/git.store'
import { fileApi } from '@/features/code/api/file.api'
import { useProjectStore } from '@/features/projects/stores/project.store'
import { FileTreeItem } from './FileTreeItem'
import { GitChangesTab } from './git/GitChangesTab'
import type { FileTreeNode } from '@/types/fileTree'

/**
 * 组件名：FileSidebar
 * 入参：无（内部通过 useCodeTabStore / useGitStore / useProjectStore 读取状态）
 * 作用/渲染逻辑：
 *   1. 侧边栏关闭时不渲染任何内容
 *   2. 当前项目或侧边栏打开状态、fileTreeVersion 变化时异步加载文件树
 *   3. 顶部提供刷新（重新拉取文件树）与收起侧边栏按钮
 *   4. 中部为 '文件'/'变更' 两个 tab：文件 tab 渲染文件树列表，变更 tab 渲染 GitChangesTab
 *   5. 左边缘提供可拖拽的宽度调整手柄，拖拽时通过全局 mousemove/mouseup 监听更新宽度
 * 返回值：JSX.Element | null - 文件侧边栏，或收起时为 null
 */
export function FileSidebar() {
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const sidebarWidth = useCodeTabStore((s) => s.sidebarWidth)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const setSidebarWidth = useCodeTabStore((s) => s.setSidebarWidth)
  const sidebarTab = useCodeTabStore((s) => s.sidebarTab)
  const setSidebarTab = useCodeTabStore((s) => s.setSidebarTab)
  const currentProject = useProjectStore((s) => s.currentProject)
  const totalChanges = useGitStore((s) => s.totalChanges)
  const fileTreeVersion = useCodeTabStore((s) => s.fileTreeVersion)

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
  }, [currentProject, sidebarOpen, fileTreeVersion])

  // 拖拽侧边栏宽度调整手柄：记录起始鼠标位置与起始宽度，移动时按位移量反向计算新宽度（手柄在左侧）
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

  const changesCount = totalChanges()

  return (
    <div className="relative flex h-full flex-col border-l border-edge bg-surface-primary" style={{ width: sidebarWidth }}>
      <div className="flex items-center justify-between border-b border-edge-subtle px-3 py-2">
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
            className="rounded-md p-1 text-content-muted hover:bg-surface-tertiary hover:text-content-secondary"
            title="刷新"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="rounded-md p-1 text-content-muted hover:bg-surface-tertiary hover:text-content-secondary"
            title="收起文件栏"
          >
            <PanelRightClose className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex border-b border-edge-subtle">
        <button
          type="button"
          onClick={() => setSidebarTab('files')}
          className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
            sidebarTab === 'files'
              ? 'text-content-primary border-b-2 border-accent'
              : 'text-content-muted hover:text-content-secondary'
          }`}
        >
          文件
        </button>
        <button
          type="button"
          onClick={() => setSidebarTab('changes')}
          className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
            sidebarTab === 'changes'
              ? 'text-content-primary border-b-2 border-accent'
              : 'text-content-muted hover:text-content-secondary'
          }`}
        >
          变更{changesCount > 0 ? ` ${changesCount}` : ''}
        </button>
      </div>

      {sidebarTab === 'files' ? (
        <div className="flex-1 overflow-y-auto py-1">
          {!currentProject ? (
            <div className="px-3 py-4 text-xs text-content-muted">请先选择项目</div>
          ) : loading ? (
            <div className="px-3 py-4 text-xs text-content-muted">加载中...</div>
          ) : (
            tree.map((node) => (
              <FileTreeItem key={node.path} node={node} depth={0} />
            ))
          )}
        </div>
      ) : (
        <GitChangesTab />
      )}

      <div
        onMouseDown={handleResizeMouseDown}
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize group"
        title="拖拽调整宽度"
      >
        <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-sm bg-transparent p-0.5 opacity-0 group-hover:opacity-100 group-hover:bg-surface-tertiary transition-opacity">
          <GripVertical className="h-3 w-3 text-content-muted" />
        </div>
      </div>
    </div>
  )
}

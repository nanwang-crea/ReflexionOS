import { ChevronDown, ChevronRight, File, Folder, FolderOpen } from 'lucide-react'
import type { FileTreeNode, GitStatusCode } from '@/types/fileTree'
import { useCodeTabStore } from '@/features/code/codeTabStore'

const GIT_STATUS_STYLES: Record<GitStatusCode, string> = {
  M: 'text-emerald-600',
  A: 'text-emerald-600',
  D: 'text-red-500',
  U: 'text-slate-400',
}

function GitStatusBadge({ status }: { status: GitStatusCode }) {
  return (
    <span className={`ml-auto text-xs font-mono ${GIT_STATUS_STYLES[status]}`}>
      {status}
    </span>
  )
}

export function FileTreeItem({ node, depth }: { node: FileTreeNode; depth: number }) {
  const expandedDirs = useCodeTabStore((s) => s.expandedDirs)
  const toggleDir = useCodeTabStore((s) => s.toggleDir)
  const setActiveFile = useCodeTabStore((s) => s.setActiveFile)
  const activeFile = useCodeTabStore((s) => s.activeFile)

  const isExpanded = expandedDirs[node.path] ?? false
  const isActive = activeFile?.path === node.path

  if (node.type === 'directory') {
    return (
      <div>
        <button
          type="button"
          onClick={() => toggleDir(node.path)}
          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm text-slate-700 hover:bg-slate-100"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          )}
          {isExpanded ? (
            <FolderOpen className="h-4 w-4 shrink-0 text-amber-500" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-amber-500" />
          )}
          <span className="truncate">{node.name}</span>
        </button>
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeItem key={child.path} node={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => setActiveFile(node.path, '')}
      className={`flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100 ${
        isActive ? 'bg-slate-100 text-slate-900 font-medium' : 'text-slate-600'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8 + 20}px` }}
    >
      <File className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <span className="truncate">{node.name}</span>
      {node.git_status && <GitStatusBadge status={node.git_status} />}
    </button>
  )
}

/**
 * 文件功能：文件树节点展示组件
 * 文件描述：递归渲染文件树的单个节点，目录节点支持展开/收起，文件节点支持点击打开并展示 Git 状态角标
 * 核心逻辑：目录节点根据 expandedDirs 展开状态决定是否递归渲染子节点；文件节点点击后以 edit 模式打开文件；
 *          缩进通过 depth * 12px 计算实现层级视觉效果
 */
import { ChevronDown, ChevronRight, File, Folder, FolderOpen } from 'lucide-react'
import type { FileTreeNode, GitStatusCode } from '@/types/fileTree'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'

const GIT_STATUS_STYLES: Record<GitStatusCode, string> = {
  M: 'text-status-success',
  A: 'text-status-success',
  D: 'text-status-error',
  U: 'text-content-muted',
  R: 'text-accent',
}

/**
 * 组件名：GitStatusBadge
 * 入参（props）：
 *   - status (GitStatusCode): Git 状态码（M/A/D/U/R）
 * 作用/渲染逻辑：按状态码对应颜色展示单字符角标
 * 返回值：JSX.Element - Git 状态角标
 */
function GitStatusBadge({ status }: { status: GitStatusCode }) {
  return (
    <span className={`ml-auto text-xs font-mono ${GIT_STATUS_STYLES[status]}`}>
      {status}
    </span>
  )
}

/**
 * 组件名：FileTreeItem
 * 入参（props）：
 *   - node (FileTreeNode): 当前文件树节点（目录或文件）
 *   - depth (number): 节点层级深度，用于计算缩进
 * 作用/渲染逻辑：
 *   1. 目录节点：点击切换展开状态，展开时递归渲染 children 为子级 FileTreeItem
 *   2. 文件节点：点击以 'edit' 模式打开文件，激活文件高亮显示，若有 git_status 则展示状态角标
 * 返回值：JSX.Element - 目录或文件节点
 */
export function FileTreeItem({ node, depth }: { node: FileTreeNode; depth: number }) {
  const expandedDirs = useCodeTabStore((s) => s.expandedDirs)
  const toggleDir = useCodeTabStore((s) => s.toggleDir)
  const openFile = useCodeTabStore((s) => s.openFile)
  const activeFile = useCodeTabStore((s) => s.activeFile)

  const isExpanded = expandedDirs[node.path] ?? false
  const isActive = activeFile?.path === node.path

  if (node.type === 'directory') {
    return (
      <div>
        <button
          type="button"
          onClick={() => toggleDir(node.path)}
          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm text-content-secondary hover:bg-surface-tertiary"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-content-muted" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-content-muted" />
          )}
          {isExpanded ? (
            <FolderOpen className="h-4 w-4 shrink-0 text-content-secondary" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-content-secondary" />
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
      onClick={() => openFile(node.path, 'edit')}
      className={`flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm hover:bg-surface-tertiary ${
        isActive ? 'bg-surface-tertiary text-content-primary font-medium' : 'text-content-secondary'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8 + 20}px` }}
    >
      <File className="h-3.5 w-3.5 shrink-0 text-content-muted" />
      <span className="truncate">{node.name}</span>
      {node.git_status && <GitStatusBadge status={node.git_status} />}
    </button>
  )
}

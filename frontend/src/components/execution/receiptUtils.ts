type ReceiptDetailStatus = 'pending' | 'running' | 'waiting_for_approval' | 'success' | 'failed' | 'cancelled'
export type ActionReceiptStatus = 'running' | 'waiting_for_approval' | 'completed' | 'failed' | 'cancelled'
type ReceiptCategory = 'explore' | 'search' | 'create' | 'edit' | 'delete' | 'command' | 'other'

export interface ShellApprovalPayload {
  command?: string
  execution_mode?: string
  reasons?: string[]
  risks?: string[]
}

export interface ActionReceiptDetail {
  id: string
  toolName: string
  status: ReceiptDetailStatus
  summary: string
  category: ReceiptCategory
  approval?: {
    runId: string
    approvalId: string
    shell?: ShellApprovalPayload
  }
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, unknown>
  target?: string
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

function shortPath(path?: string) {
  if (!path) return ''

  const normalized = path.replace(/\\/g, '/').replace(/^(a|b)\//, '')
  const segments = normalized.split('/').filter(Boolean)

  if (segments.length <= 2) {
    return normalized
  }

  return segments.slice(-2).join('/')
}

function getPatchTarget(patchText: string) {
  const plusMatch = patchText.match(/^\+\+\+\s+(?:b\/)?([^\n]+)$/m)
  if (plusMatch && plusMatch[1] !== '/dev/null') {
    return plusMatch[1]
  }

  const minusMatch = patchText.match(/^---\s+(?:a\/)?([^\n]+)$/m)
  if (minusMatch && minusMatch[1] !== '/dev/null') {
    return minusMatch[1]
  }

  return ''
}

function getPatchCategory(patchText: string): 'create' | 'edit' | 'delete' {
  if (
    patchText.includes('new file mode') ||
    patchText.includes('*** Add File:') ||
    patchText.includes('--- /dev/null')
  ) {
    return 'create'
  }

  if (
    patchText.includes('deleted file mode') ||
    patchText.includes('*** Delete File:') ||
    patchText.includes('+++ /dev/null')
  ) {
    return 'delete'
  }

  return 'edit'
}

function buildFileDetail(id: string, args: Record<string, unknown>): ActionReceiptDetail {
  const action = typeof args.action === 'string' ? args.action : ''
  const path = typeof args.path === 'string' ? args.path : ''
  const query = typeof args.query === 'string' ? args.query : ''
  const target = shortPath(path)

  switch (action) {
    case 'read':
      return {
        id,
        toolName: 'file',
        status: 'pending',
        summary: target ? `探索 ${target}` : '探索文件',
        category: 'explore',
        arguments: args,
        target
      }
    case 'list':
      return {
        id,
        toolName: 'file',
        status: 'pending',
        summary: target ? `查看 ${target}` : '查看目录',
        category: 'explore',
        arguments: args,
        target
      }
    case 'search':
      return {
        id,
        toolName: 'file',
        status: 'pending',
        summary: query ? `搜索 "${truncate(query, 28)}"` : (target ? `搜索 ${target}` : '搜索项目'),
        category: 'search',
        arguments: args,
        target
      }
    case 'write':
      return {
        id,
        toolName: 'file',
        status: 'pending',
        summary: target ? `写入 ${target}` : '写入文件',
        category: 'edit',
        arguments: args,
        target
      }
    case 'delete':
      return {
        id,
        toolName: 'file',
        status: 'pending',
        summary: target ? `删除 ${target}` : '删除文件',
        category: 'delete',
        arguments: args,
        target
      }
    default:
      return {
        id,
        toolName: 'file',
        status: 'pending',
        summary: target ? `处理 ${target}` : '处理文件',
        category: 'other',
        arguments: args,
        target
      }
  }
}

function buildPatchDetail(id: string, args: Record<string, unknown>): ActionReceiptDetail {
  const patchText = typeof args.patch === 'string' ? args.patch : ''
  const target = shortPath(getPatchTarget(patchText))
  const category = getPatchCategory(patchText)

  const verb = {
    create: '创建',
    edit: '编辑',
    delete: '删除',
    other: '修改'
  }[category]

  return {
    id,
    toolName: 'patch',
    status: 'pending',
    summary: target ? `${verb} ${target}` : `${verb} 文件`,
    category,
    arguments: args,
    target
  }
}

function buildShellDetail(id: string, args: Record<string, unknown>): ActionReceiptDetail {
  const command = typeof args.command === 'string' ? args.command.trim() : ''
  const summary = command ? `运行 ${truncate(command.replace(/\s+/g, ' '), 42)}` : '运行命令'

  return {
    id,
    toolName: 'shell',
    status: 'pending',
    summary,
    category: 'command',
    arguments: args
  }
}

export function buildReceiptDetail(
  id: string,
  toolName: string,
  args?: Record<string, unknown>
): ActionReceiptDetail {
  const safeArgs = args || {}

  if (toolName === 'file') {
    return buildFileDetail(id, safeArgs)
  }

  if (toolName === 'patch') {
    return buildPatchDetail(id, safeArgs)
  }

  if (toolName === 'shell') {
    return buildShellDetail(id, safeArgs)
  }

  return {
    id,
    toolName,
    status: 'pending',
    summary: `执行 ${toolName}`,
    category: 'other',
    arguments: safeArgs
  }
}

function formatSegment(prefix: string, verb: string, count: number, unit: string) {
  if (count === 0) return null
  return `${prefix}${verb} ${count} ${unit}`
}

export function summarizeReceipt(details: ActionReceiptDetail[], status: ActionReceiptStatus) {
  const exploreTargets = new Set<string>()
  const createTargets = new Set<string>()
  const editTargets = new Set<string>()
  const deleteTargets = new Set<string>()
  let searchCount = 0
  let commandCount = 0
  let otherCount = 0

  details.forEach((detail) => {
    switch (detail.category) {
      case 'explore':
        if (detail.target) {
          exploreTargets.add(detail.target)
        } else {
          otherCount += 1
        }
        break
      case 'search':
        searchCount += 1
        break
      case 'create':
        if (detail.target) {
          createTargets.add(detail.target)
        } else {
          otherCount += 1
        }
        break
      case 'edit':
        if (detail.target) {
          editTargets.add(detail.target)
        } else {
          otherCount += 1
        }
        break
      case 'delete':
        if (detail.target) {
          deleteTargets.add(detail.target)
        } else {
          otherCount += 1
        }
        break
      case 'command':
        commandCount += 1
        break
      default:
        otherCount += 1
    }
  })

  const prefix = status === 'running' || status === 'waiting_for_approval'
    ? '正在'
    : status === 'cancelled'
      ? '已取消'
      : '已'
  const segments = [
    formatSegment(prefix, '探索', exploreTargets.size, '个文件'),
    formatSegment(prefix, '探索', searchCount, '次搜索'),
    formatSegment(prefix, '创建', createTargets.size, '个文件'),
    formatSegment(prefix, '编辑', editTargets.size, '个文件'),
    formatSegment(prefix, '删除', deleteTargets.size, '个文件'),
    formatSegment(prefix, '运行', commandCount, '条命令'),
  ].filter(Boolean)

  if (segments.length === 0 && otherCount > 0) {
    segments.push(`${prefix}处理 ${details.length} 个操作`)
  }

  const summary = segments.join('，') || `${prefix}处理 1 个操作`
  if (status === 'failed') {
    return `执行失败 · ${summary}`
  }

  if (status === 'cancelled') {
    return `执行已取消 · ${summary}`
  }

  return summary
}

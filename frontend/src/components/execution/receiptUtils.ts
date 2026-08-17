/**
 * 文件功能：动作回执（ActionReceipt）数据模型与摘要生成工具
 * 文件描述：定义工具调用回执的详情结构（文件/补丁/编辑/命令等类别），提供从原始工具参数构建回执详情、
 *          从审批 payload 解析出审批上下文，以及汇总多条详情生成一句话摘要的工具函数
 * 核心逻辑：按 toolName 分发到对应的 build*Detail 函数生成统一的 ActionReceiptDetail 结构；
 *          summarizeReceipt 按状态（运行中/失败/部分失败/取消/完成）与类别统计生成人类可读的摘要文案
 */
type ReceiptDetailStatus = 'pending' | 'running' | 'waiting_for_approval' | 'success' | 'failed' | 'cancelled'
export type ActionReceiptStatus = 'running' | 'waiting_for_approval' | 'completed' | 'partial_failed' | 'failed' | 'cancelled'
type ReceiptCategory = 'explore' | 'search' | 'create' | 'edit' | 'delete' | 'command' | 'other'

export interface ShellApprovalPayload {
  command?: string
  execution_mode?: string
  reasons?: string[]
  risks?: string[]
}

export interface SandboxNetworkPayload {
  approval_kind: "sandbox_network_elevation"
  command: string
  execution_mode: string
  reasons: string[]
  risks: string[]
}

export interface SandboxPathPayload {
  approval_kind: "sandbox_path_elevation"
  command: string
  execution_mode: string
  denied_paths: string[]
  reasons: string[]
  risks: string[]
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
    parentSessionId?: string  // SubAgent 的父 session ID，用于路由审批响应
    suggestedTrust?: { prefix?: string[]; permission?: string; pattern?: string }
    shell?: ShellApprovalPayload
    sandboxNetwork?: SandboxNetworkPayload
    sandboxPath?: SandboxPathPayload
  }
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, unknown>
  target?: string
  data?: Record<string, unknown>
}

/**
 * 函数名：isRecord
 * 入参：
 *   - value (unknown): 待判断的任意值
 * 功能：判断值是否为普通对象（非 null、非数组）
 * 运行逻辑：typeof 校验为 object 且不为 null 且不是数组即视为普通对象
 * 出参：boolean（类型谓词）- 是否为 Record<string, unknown>
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 函数名：stringArray
 * 入参：
 *   - value (unknown): 待转换的任意值
 * 功能：安全地将任意值转换为字符串数组
 * 运行逻辑：若为数组则过滤出其中的字符串项，否则返回空数组
 * 出参：string[] - 提取出的字符串数组
 */
function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/**
 * 函数名：buildSuggestedTrust
 * 入参：
 *   - value (unknown): 原始的 suggested_trust 字段值
 * 功能：从原始审批 payload 中解析出建议信任规则（前缀数组/权限/模式）
 * 运行逻辑：
 *   1. 非普通对象直接返回 undefined
 *   2. 分别提取 prefix（字符串数组）、permission（字符串）、pattern（字符串）
 *   3. 若均未提取到任何字段则返回 undefined，否则返回组装结果
 * 出参：建议信任对象或 undefined
 */
function buildSuggestedTrust(value: unknown): ActionReceiptDetail['approval'] extends infer Approval
  ? Approval extends { suggestedTrust?: infer Suggested }
    ? Suggested | undefined
    : never
  : never {
  if (!isRecord(value)) return undefined
  const suggested: { prefix?: string[]; permission?: string; pattern?: string } = {}
  if (Array.isArray(value.prefix)) {
    suggested.prefix = value.prefix.filter((item): item is string => typeof item === 'string')
  }
  if (typeof value.permission === 'string') {
    suggested.permission = value.permission
  }
  if (typeof value.pattern === 'string') {
    suggested.pattern = value.pattern
  }
  return Object.keys(suggested).length > 0 ? suggested : undefined
}

/**
 * 函数名：buildApprovalDetailFromPayload
 * 入参：
 *   - payload (Record<string, unknown>): 后端推送的原始审批事件数据
 * 功能：从原始审批事件 payload 中解析出结构化的 approval 与 data 字段，供回执详情展示与审批操作使用
 * 运行逻辑：
 *   1. 提取 approval_id、run_id，若缺失任一必要字段则返回 undefined
 *   2. 提取 parent_session_id、command、execution_mode、approval_kind、reasons、risks
 *   3. 组装基础 approval 对象（含 suggestedTrust）
 *   4. 若存在 command，附加 shell 审批信息
 *   5. 根据 approval_kind 分别附加 sandboxNetwork（网络越权）或 sandboxPath（路径越权）信息
 * 出参：{ approval, data } 或 undefined（当必要字段缺失时）
 */
export function buildApprovalDetailFromPayload(
  payload: Record<string, unknown>,
): Pick<ActionReceiptDetail, 'approval' | 'data'> | undefined {
  const approvalObj = isRecord(payload.approval) ? payload.approval : undefined
  const approvalPayload = isRecord(approvalObj?.payload) ? approvalObj.payload : undefined
  const approvalId = typeof payload.approval_id === 'string' ? payload.approval_id : undefined
  const runId = typeof payload.run_id === 'string' ? payload.run_id : undefined
  if (!approvalId || !runId) return undefined

  const parentSessionId = typeof payload.parent_session_id === 'string' ? payload.parent_session_id : undefined
  const command = typeof approvalPayload?.command === 'string' ? approvalPayload.command : undefined
  const executionMode = typeof approvalPayload?.execution_mode === 'string' ? approvalPayload.execution_mode : undefined
  const approvalKind = typeof approvalPayload?.approval_kind === 'string' ? approvalPayload.approval_kind : undefined
  const reasons = stringArray(approvalObj?.reasons)
  const risks = stringArray(approvalObj?.risks)

  const approval: NonNullable<ActionReceiptDetail['approval']> = {
    runId,
    approvalId,
    parentSessionId,
    suggestedTrust: buildSuggestedTrust(approvalObj?.suggested_trust),
  }

  if (command) {
    approval.shell = {
      command,
      ...(executionMode ? { execution_mode: executionMode } : {}),
      ...(reasons.length > 0 ? { reasons } : {}),
      ...(risks.length > 0 ? { risks } : {}),
    }
  }

  if (approvalKind === 'sandbox_network_elevation' && command) {
    approval.sandboxNetwork = {
      approval_kind: 'sandbox_network_elevation',
      command,
      execution_mode: executionMode ?? '',
      reasons,
      risks,
    }
  }

  if (approvalKind === 'sandbox_path_elevation' && command) {
    const elevationRequest = isRecord(approvalPayload?.elevation_request)
      ? approvalPayload.elevation_request
      : undefined
    approval.sandboxPath = {
      approval_kind: 'sandbox_path_elevation',
      command,
      execution_mode: executionMode ?? '',
      denied_paths: stringArray(elevationRequest?.denied_paths),
      reasons,
      risks,
    }
  }

  return {
    approval,
    data: approvalPayload,
  }
}

/**
 * 函数名：truncate
 * 入参：
 *   - value (string): 待截断的字符串
 *   - length (number): 最大保留长度
 * 功能：超出长度时截断字符串并追加省略号
 * 运行逻辑：比较字符串长度与阈值，超出则切片并拼接 '...'
 * 出参：string - 截断后的字符串
 */
function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

/**
 * 函数名：shortPath
 * 入参：
 *   - path (string | undefined): 原始文件路径，可能带有 diff 的 a/ b/ 前缀
 * 功能：将完整路径缩短为便于展示的短路径（最多保留末两级目录）
 * 运行逻辑：
 *   1. 空路径直接返回空字符串
 *   2. 统一反斜杠为正斜杠，并去除 diff 风格的 a/ 或 b/ 前缀
 *   3. 按 / 分段后，若段数不超过 2 则原样返回，否则只保留最后两段
 * 出参：string - 缩短后的路径
 */
function shortPath(path?: string) {
  if (!path) return ''

  const normalized = path.replace(/\\/g, '/').replace(/^(a|b)\//, '')
  const segments = normalized.split('/').filter(Boolean)

  if (segments.length <= 2) {
    return normalized
  }

  return segments.slice(-2).join('/')
}

/**
 * 函数名：getPatchTarget
 * 入参：
 *   - patchText (string): unified diff 格式的补丁文本
 * 功能：从补丁文本中解析出目标文件路径
 * 运行逻辑：
 *   1. 优先匹配 "+++ " 行（新文件路径），非 /dev/null 时采用
 *   2. 否则匹配 "--- " 行（原文件路径），非 /dev/null 时采用
 *   3. 都未匹配到则返回空字符串
 * 出参：string - 解析出的目标路径，未解析到则为空字符串
 */
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

/**
 * 函数名：getPatchCategory
 * 入参：
 *   - patchText (string): unified diff 格式的补丁文本
 * 功能：判断补丁对应的操作类别（新建/编辑/删除）
 * 运行逻辑：
 *   1. 命中 "new file mode" / "*** Add File:" / "--- /dev/null" 等标记则判定为创建
 *   2. 命中 "deleted file mode" / "*** Delete File:" / "+++ /dev/null" 等标记则判定为删除
 *   3. 其余情况默认判定为编辑
 * 出参：'create' | 'edit' | 'delete' - 补丁操作类别
 */
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

/**
 * 函数名：buildFileDetail
 * 入参：
 *   - id (string): 回执详情的唯一标识
 *   - args (Record<string, unknown>): file 工具调用的原始参数（action、path、query 等）
 * 功能：将 file 工具（读/查看/搜索/写入/删除）的调用参数转换为可展示的回执详情
 * 运行逻辑：根据 args.action 的取值（read/list/search/write/delete/其它）分别生成对应的中文摘要文案与类别
 * 出参：ActionReceiptDetail - 构建好的回执详情对象
 */
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

/**
 * 函数名：buildPatchDetail
 * 入参：
 *   - id (string): 回执详情的唯一标识
 *   - args (Record<string, unknown>): patch 工具调用的原始参数（包含 patch 补丁文本）
 * 功能：将 patch 工具调用转换为可展示的回执详情
 * 运行逻辑：解析补丁文本得到目标路径与操作类别，再拼接对应中文动词（创建/编辑/删除/修改）生成摘要
 * 出参：ActionReceiptDetail - 构建好的回执详情对象
 */
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

/**
 * 函数名：buildEditDetail
 * 入参：
 *   - id (string): 回执详情的唯一标识
 *   - args (Record<string, unknown>): edit 工具调用的原始参数（action、path、old_string 等）
 * 功能：将 edit 工具（字符串替换/补丁/整体写入等多种编辑动作）的调用参数转换为可展示的回执详情
 * 运行逻辑：
 *   1. action 为 str_replace 时：old_string 为空视为创建文件，否则按 replace_all 区分“替换”与“批量替换”
 *   2. action 为 patch 时：解析补丁文本得到类别与目标路径，拼接对应中文动词
 *   3. action 为 write 时：视为创建/写入文件
 *   4. 其余情况归入 other 类别
 * 出参：ActionReceiptDetail - 构建好的回执详情对象
 */
function buildEditDetail(id: string, args: Record<string, unknown>): ActionReceiptDetail {
  const action = typeof args.action === 'string' ? args.action : ''
  const path = typeof args.path === 'string' ? args.path : ''
  const target = shortPath(path)

  if (action === 'str_replace') {
    const oldString = typeof args.old_string === 'string' ? args.old_string : ''
    const replaceAll = args.replace_all === true
    if (!oldString) {
      return {
        id,
        toolName: 'edit',
        status: 'pending',
        summary: target ? `创建 ${target}` : '创建文件',
        category: 'create',
        arguments: args,
        target
      }
    }
    const verb = replaceAll ? '批量替换' : '替换'
    return {
      id,
      toolName: 'edit',
      status: 'pending',
      summary: target ? `${verb} ${target}` : `${verb}内容`,
      category: 'edit',
      arguments: args,
      target
    }
  }

  if (action === 'patch') {
    const patchText = typeof args.patch === 'string' ? args.patch : ''
    const category = getPatchCategory(patchText)
    const patchTarget = shortPath(getPatchTarget(patchText))
    const verb = { create: '创建', edit: '编辑', delete: '删除' }[category]
    return {
      id,
      toolName: 'edit',
      status: 'pending',
      summary: patchTarget ? `${verb} ${patchTarget}` : `${verb}文件`,
      category,
      arguments: args,
      target: patchTarget
    }
  }

  if (action === 'write') {
    return {
      id,
      toolName: 'edit',
      status: 'pending',
      summary: target ? `写入 ${target}` : '写入文件',
      category: 'create',
      arguments: args,
      target
    }
  }

  return {
    id,
    toolName: 'edit',
    status: 'pending',
    summary: target ? `处理 ${target}` : '编辑操作',
    category: 'other',
    arguments: args,
    target
  }
}

/**
 * 函数名：buildShellDetail
 * 入参：
 *   - id (string): 回执详情的唯一标识
 *   - args (Record<string, unknown>): shell 工具调用的原始参数（包含 command 命令字符串）
 * 功能：将 shell 命令调用转换为可展示的回执详情
 * 运行逻辑：取出命令字符串，压缩空白并截断到 42 字符用于摘要展示，无命令时展示通用文案
 * 出参：ActionReceiptDetail - 构建好的回执详情对象
 */
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

/**
 * 函数名：buildReceiptDetail
 * 入参：
 *   - id (string): 回执详情的唯一标识
 *   - toolName (string): 工具名称（file/patch/edit/shell 或其它）
 *   - args (Record<string, unknown> | undefined): 工具调用的原始参数，可为空
 * 功能：统一入口，根据工具名称分发到对应的 build*Detail 函数生成回执详情
 * 运行逻辑：
 *   1. 参数为空时使用空对象兜底
 *   2. 按 toolName 依次匹配 file/patch/edit/shell，命中则调用对应构建函数
 *   3. 未匹配到已知工具时返回通用的“执行 {toolName}”回执详情
 * 出参：ActionReceiptDetail - 构建好的回执详情对象
 */
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

  if (toolName === 'edit') {
    return buildEditDetail(id, safeArgs)
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

/**
 * 函数名：formatSegment
 * 入参：
 *   - prefix (string): 前缀文案（如“已”“正在”）
 *   - verb (string): 动作动词（如“探索”“创建”）
 *   - count (number): 数量
 *   - unit (string): 单位（如“个文件”“次搜索”）
 * 功能：生成摘要中的单个片段文案，数量为 0 时不生成
 * 运行逻辑：数量为 0 返回 null，否则拼接 "前缀动词 数量单位"
 * 出参：string | null - 生成的文案片段，或 null 表示跳过
 */
function formatSegment(prefix: string, verb: string, count: number, unit: string) {
  if (count === 0) return null
  return `${prefix}${verb} ${count} ${unit}`
}

/**
 * 函数名：countByStatus
 * 入参：
 *   - details (ActionReceiptDetail[]): 回执详情数组
 * 功能：统计详情数组中失败与成功的数量
 * 运行逻辑：遍历数组，按 status 字段分别累加 failedCount 与 successCount
 * 出参：{ failedCount, successCount } - 失败与成功的统计结果
 */
function countByStatus(details: ActionReceiptDetail[]) {
  let failedCount = 0
  let successCount = 0
  details.forEach((d) => {
    if (d.status === 'failed') failedCount += 1
    else if (d.status === 'success') successCount += 1
  })
  return { failedCount, successCount }
}

/**
 * 函数名：buildSummarySegments
 * 入参：
 *   - details (ActionReceiptDetail[]): 回执详情数组
 *   - prefix (string): 摘要前缀文案（如“已”“正在”）
 * 功能：按类别统计详情数组，生成用于拼接摘要的文案片段数组
 * 运行逻辑：
 *   1. 遍历详情，按 category 分类：explore/create/edit/delete 按 target 去重计入对应 Set，
 *      search/command 直接计数，无 target 或未知类别计入 otherCount
 *   2. 依次为探索文件数、探索搜索次数、创建、编辑、删除、运行命令生成片段，过滤掉数量为 0 的片段
 *   3. 若所有片段都为空但存在 otherCount，则生成兜底的“处理 N 个操作”片段
 * 出参：string[] - 摘要片段数组
 */
function buildSummarySegments(details: ActionReceiptDetail[], prefix: string): string[] {
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

  const segments = [
    formatSegment(prefix, '探索', exploreTargets.size, '个文件'),
    formatSegment(prefix, '探索', searchCount, '次搜索'),
    formatSegment(prefix, '创建', createTargets.size, '个文件'),
    formatSegment(prefix, '编辑', editTargets.size, '个文件'),
    formatSegment(prefix, '删除', deleteTargets.size, '个文件'),
    formatSegment(prefix, '运行', commandCount, '条命令'),
  ].filter((s): s is string => s !== null)

  if (segments.length === 0 && otherCount > 0) {
    segments.push(`${prefix}处理 ${details.length} 个操作`)
  }

  return segments
}

/**
 * 函数名：summarizeReceipt
 * 入参：
 *   - details (ActionReceiptDetail[]): 回执详情数组
 *   - status (ActionReceiptStatus): 回执整体状态（running/waiting_for_approval/completed/partial_failed/failed/cancelled）
 * 功能：根据整体状态与详情列表生成一句话摘要文案，用于回执标题展示
 * 运行逻辑：
 *   1. partial_failed：统计失败数量前置展示，成功项按类别汇总
 *   2. failed：全部按“已”前缀汇总后加“执行失败”前缀
 *   3. cancelled：全部按“已”前缀汇总后加“执行已取消”前缀
 *   4. 其余状态（running/waiting_for_approval/completed）：running 与 waiting_for_approval 用“正在”前缀，其余用“已”前缀
 * 出参：string - 生成的摘要文案
 */
export function summarizeReceipt(details: ActionReceiptDetail[], status: ActionReceiptStatus) {
  const { failedCount } = countByStatus(details)

  // partial_failed: 只统计成功项的 summary，失败数量前置
  if (status === 'partial_failed') {
    const successDetails = details.filter((d) => d.status !== 'failed')
    const failedLabel = failedCount === 1 ? '1 项失败' : `${failedCount} 项失败`
    const successSegments = buildSummarySegments(successDetails, '已')
    const successSummary = successSegments.join('，') || '其余成功'
    return `${failedLabel} · ${successSummary}`
  }

  // failed (全部失败)
  if (status === 'failed') {
    const prefix = '已'
    const segments = buildSummarySegments(details, prefix)
    const summary = segments.join('，') || `${prefix}处理 ${details.length} 个操作`
    return `执行失败 · ${summary}`
  }

  // cancelled
  if (status === 'cancelled') {
    const prefix = '已'
    const segments = buildSummarySegments(details, prefix)
    const summary = segments.join('，') || `${prefix}处理 ${details.length} 个操作`
    return `执行已取消 · ${summary}`
  }

  // running / waiting_for_approval / completed
  const prefix = status === 'running' || status === 'waiting_for_approval'
    ? '正在'
    : '已'
  const segments = buildSummarySegments(details, prefix)
  return segments.join('，') || `${prefix}处理 1 个操作`
}

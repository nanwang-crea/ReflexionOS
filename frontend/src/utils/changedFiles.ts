// 文件功能：变更聚合（Changed Files）的解析与折叠工具
// 文件描述：从工具轨迹消息的 payload 中解析后端携带的 changed_files 条目，
//          并按"同路径最后一次出现胜出"折叠为每轮的最终变更清单
// 核心逻辑：路径先归一化（反斜杠转斜杠、剥 ./ 前缀）再作为折叠键；moved 条目
//          折叠时先移除 oldPath 的既有键再登记新路径，保证"重命名后"只显示新路径
import type { ChangedFileAction, ChangedFileEntry, ConversationMessage } from '@/types/conversation'

const CHANGED_FILE_ACTIONS: ChangedFileAction[] = ['created', 'modified', 'deleted', 'moved']

/**
 * 函数名：normalizeChangedFilePath
 * 入参：path (string) - 工具返回的文件路径（可能是绝对路径，也可能带反斜杠或 ./ 前缀）
 * 功能：把路径归一化为可比较的展示形式
 * 运行逻辑：反斜杠统一为正斜杠，剥掉开头的 ./，去掉尾部空白
 * 出参：string - 归一化后的路径
 */
export function normalizeChangedFilePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/^\.\//, '').trim()
}

/**
 * 函数名：parseChangedFileEntry
 * 入参：raw (unknown) - payload.changed_files 数组中的一个原始条目
 * 功能：把后端蛇形命名的条目校验/转换为前端 ChangedFileEntry
 * 运行逻辑：path 必须是非空字符串、action 必须在四类之内，否则丢弃该条目；
 *          old_path 仅在合法非空字符串时映射为 oldPath
 * 出参：ChangedFileEntry | null - 合法条目，非法返回 null
 */
export function parseChangedFileEntry(raw: unknown): ChangedFileEntry | null {
  if (typeof raw !== 'object' || raw === null) return null
  const record = raw as Record<string, unknown>
  if (typeof record.path !== 'string' || !record.path.trim()) return null
  if (!CHANGED_FILE_ACTIONS.includes(record.action as ChangedFileAction)) return null
  const entry: ChangedFileEntry = {
    path: normalizeChangedFilePath(record.path),
    action: record.action as ChangedFileAction,
  }
  if (typeof record.old_path === 'string' && record.old_path.trim()) {
    entry.oldPath = normalizeChangedFilePath(record.old_path)
  }
  return entry
}

/**
 * 函数名：parseChangedFilesFromPayload
 * 入参：payloadJson (ConversationMessage['payloadJson']) - 工具轨迹消息负载
 * 功能：从负载中取出 changed_files 数组并逐条解析
 * 运行逻辑：changed_files 非数组时返回空数组；逐条 parseChangedFileEntry 后过滤 null
 * 出参：ChangedFileEntry[] - 该条工具消息声明的全部变更条目
 */
export function parseChangedFilesFromPayload(payloadJson: ConversationMessage['payloadJson']): ChangedFileEntry[] {
  const raw = payloadJson.changed_files
  if (!Array.isArray(raw)) return []
  return raw.map(parseChangedFileEntry).filter((entry): entry is ChangedFileEntry => entry !== null)
}

/**
 * 函数名：aggregateChangedFiles
 * 入参：entries (ChangedFileEntry[]) - 按时间顺序排列的原始变更条目（可能重复、互相覆盖）
 * 功能：折叠为每个路径的最终状态（对齐 Studio 的"保留最后一次出现"语义）
 * 运行逻辑：
 *   1. 按 path 顺序折叠：同路径后面的条目覆盖前面的
 *   2. moved 条目先从结果里移除 oldPath 的键（旧路径不复存在），再登记新路径
 *   3. 输出保持首次出现的相对顺序（按各路径最后一次登记的先后）
 * 出参：ChangedFileEntry[] - 去重后的最终变更清单
 */
export function aggregateChangedFiles(entries: ChangedFileEntry[]): ChangedFileEntry[] {
  const byPath = new Map<string, ChangedFileEntry>()
  for (const entry of entries) {
    const normalized: ChangedFileEntry = { ...entry, path: normalizeChangedFilePath(entry.path) }
    if (normalized.oldPath) {
      normalized.oldPath = normalizeChangedFilePath(normalized.oldPath)
    }
    if (entry.action === 'moved' && normalized.oldPath && byPath.has(normalized.oldPath)) {
      byPath.delete(normalized.oldPath)
    }
    byPath.set(normalized.path, normalized)
  }
  return Array.from(byPath.values())
}

/**
 * 函数名：collectChangedFilesFromMessages
 * 入参：messages (ConversationMessage[]) - 某个 run（过程分组）内的工具轨迹消息
 * 功能：一步到位：收集 + 解析 + 聚合
 * 运行逻辑：flatMap 出各消息的 changed_files 后交给 aggregateChangedFiles
 * 出参：ChangedFileEntry[] - 该 run 的最终变更清单（空数组表示没有文件变更）
 */
export function collectChangedFilesFromMessages(messages: ConversationMessage[]): ChangedFileEntry[] {
  const entries = messages.flatMap((message) => parseChangedFilesFromPayload(message.payloadJson))
  return aggregateChangedFiles(entries)
}

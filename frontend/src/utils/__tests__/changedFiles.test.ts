// 变更聚合（changedFiles）工具的单测：解析负载条目、路径归一化、
// "同路径最后一次出现胜出"折叠与 moved 的 oldPath 移除语义。
import { describe, expect, it } from 'vitest'
import {
  aggregateChangedFiles,
  collectChangedFilesFromMessages,
  normalizeChangedFilePath,
  parseChangedFileEntry,
  parseChangedFilesFromPayload,
} from '../changedFiles'
import type { ConversationMessage } from '@/types/conversation'

function buildToolMessage(payloadJson: Record<string, unknown>): ConversationMessage {
  return {
    id: 'msg-1',
    sessionId: 'session-1',
    turnId: 'turn-1',
    runId: 'run-1',
    turnMessageIndex: 1,
    role: 'assistant',
    messageType: 'tool_trace',
    displayMode: 'default',
    contentText: '',
    streamState: 'completed',
    payloadJson,
    completedAt: '2026-11-01T10:00:01Z',
    createdAt: '2026-11-01T10:00:00Z',
    updatedAt: '2026-11-01T10:00:00Z',
  }
}

describe('normalizeChangedFilePath', () => {
  it('converts backslashes, strips ./ prefix and trims', () => {
    expect(normalizeChangedFilePath('src\\shared\\a.ts')).toBe('src/shared/a.ts')
    expect(normalizeChangedFilePath('./src/a.ts')).toBe('src/a.ts')
    expect(normalizeChangedFilePath('  src/a.ts ')).toBe('src/a.ts')
  })
})

describe('parseChangedFileEntry', () => {
  it('accepts snake_case entries and maps old_path to oldPath', () => {
    expect(parseChangedFileEntry({ path: '/a/b.ts', action: 'modified' })).toEqual({
      path: '/a/b.ts',
      action: 'modified',
    })
    expect(parseChangedFileEntry({ path: '/a/new.ts', action: 'moved', old_path: '/a/old.ts' })).toEqual({
      path: '/a/new.ts',
      action: 'moved',
      oldPath: '/a/old.ts',
    })
  })

  it('rejects malformed entries', () => {
    expect(parseChangedFileEntry(null)).toBeNull()
    expect(parseChangedFileEntry({ path: '', action: 'modified' })).toBeNull()
    expect(parseChangedFileEntry({ path: '/a.ts', action: 'renamed' })).toBeNull()
  })

  it('returns empty array for non-array payload field', () => {
    expect(parseChangedFilesFromPayload({ changed_files: 'nope' })).toEqual([])
    expect(parseChangedFilesFromPayload({})).toEqual([])
  })
})

describe('aggregateChangedFiles', () => {
  it('keeps the last occurrence per path', () => {
    const aggregated = aggregateChangedFiles([
      { path: 'a.ts', action: 'created' },
      { path: 'b.ts', action: 'modified' },
      { path: 'a.ts', action: 'modified' },
    ])
    expect(aggregated).toEqual([
      { path: 'a.ts', action: 'modified' },
      { path: 'b.ts', action: 'modified' },
    ])
  })

  it('removes the old path key when a later entry moves a file', () => {
    const aggregated = aggregateChangedFiles([
      { path: 'old.ts', action: 'modified' },
      { path: 'new.ts', action: 'moved', oldPath: 'old.ts' },
    ])
    expect(aggregated).toEqual([{ path: 'new.ts', action: 'moved', oldPath: 'old.ts' }])
  })

  it('normalizes equivalent paths before folding', () => {
    const aggregated = aggregateChangedFiles([
      { path: 'src\\a.ts', action: 'created' },
      { path: './src/a.ts', action: 'modified' },
    ])
    expect(aggregated).toEqual([{ path: 'src/a.ts', action: 'modified' }])
  })
})

describe('collectChangedFilesFromMessages', () => {
  it('collects and aggregates entries across tool messages', () => {
    const messages = [
      buildToolMessage({ tool_name: 'edit', changed_files: [{ path: '/p/a.ts', action: 'created' }] }),
      buildToolMessage({ tool_name: 'edit', changed_files: [{ path: '/p/a.ts', action: 'modified' }] }),
      buildToolMessage({ tool_name: 'shell' }),
    ]
    expect(collectChangedFilesFromMessages(messages)).toEqual([
      { path: '/p/a.ts', action: 'modified' },
    ])
  })

  it('returns empty array when no tool message declares changes', () => {
    expect(collectChangedFilesFromMessages([buildToolMessage({ tool_name: 'shell' })])).toEqual([])
  })
})

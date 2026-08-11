import { describe, expect, it } from 'vitest'
import { buildApprovalDetailFromPayload } from '../receiptUtils'

describe('buildApprovalDetailFromPayload', () => {
  it('builds shell approval data from ToolApprovalRequest payload', () => {
    const detail = buildApprovalDetailFromPayload({
      approval_id: 'approval-1',
      run_id: 'sub-run-1',
      parent_session_id: 'session-1',
      approval: {
        reasons: ['needs permission'],
        risks: ['can change files'],
        payload: {
          command: 'git status',
          execution_mode: 'argv',
          approval_kind: 'shell_command',
        },
        suggested_trust: {
          prefix: ['git'],
        },
      },
    })

    expect(detail?.approval?.runId).toBe('sub-run-1')
    expect(detail?.approval?.parentSessionId).toBe('session-1')
    expect(detail?.approval?.shell?.command).toBe('git status')
    expect(detail?.approval?.shell?.reasons).toEqual(['needs permission'])
    expect(detail?.approval?.suggestedTrust?.prefix).toEqual(['git'])
    expect(detail?.data?.approval_kind).toBe('shell_command')
  })

  it('builds sandbox path elevation data from nested elevation request', () => {
    const detail = buildApprovalDetailFromPayload({
      approval_id: 'approval-2',
      run_id: 'sub-run-2',
      approval: {
        reasons: ['outside workspace'],
        risks: ['reads private files'],
        payload: {
          command: 'cat /tmp/secret',
          execution_mode: 'argv',
          approval_kind: 'sandbox_path_elevation',
          elevation_request: {
            denied_paths: ['/tmp/secret'],
          },
        },
        suggested_trust: {
          permission: 'sandbox_path',
          pattern: '/tmp/secret/*',
        },
      },
    })

    expect(detail?.approval?.sandboxPath).toEqual({
      approval_kind: 'sandbox_path_elevation',
      command: 'cat /tmp/secret',
      execution_mode: 'argv',
      denied_paths: ['/tmp/secret'],
      reasons: ['outside workspace'],
      risks: ['reads private files'],
    })
    expect(detail?.approval?.suggestedTrust?.permission).toBe('sandbox_path')
    expect(detail?.data?.approval_kind).toBe('sandbox_path_elevation')
  })
})

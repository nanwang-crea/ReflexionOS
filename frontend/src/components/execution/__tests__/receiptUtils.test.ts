// receiptUtils.buildApprovalDetailFromPayload 的单测：验证从后端推送的审批载荷（ToolApprovalRequest）
// 能正确解析出 shell 命令审批和 sandbox 路径提权两种审批详情结构。
import { describe, expect, it } from 'vitest'
import { buildApprovalDetailFromPayload } from '../receiptUtils'

describe('buildApprovalDetailFromPayload', () => {
  // 参数：无。
  // 验证：payload.approval.payload.approval_kind 为 'shell_command' 时，能正确映射出
  // runId/parentSessionId、shell 命令/理由、建议信任前缀等字段。
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

  // 参数：无。
  // 验证：payload.approval.payload.approval_kind 为 'sandbox_path_elevation' 且携带
  // elevation_request.denied_paths 时，能正确映射出 sandboxPath 详情（含拒绝路径列表）及建议信任权限。
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

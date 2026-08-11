import { describe, expect, it } from 'vitest'
import type { SubAgentStep } from '@/hooks/useSubAgentEvents'
import { buildSubAgentRenderItems } from '../SubAgentDetailPanel'

function step(eventType: string, payload: Record<string, unknown>): SubAgentStep {
  return {
    eventType,
    payload,
    receivedAt: Date.now(),
  }
}

describe('buildSubAgentRenderItems', () => {
  it('keeps parallel tool calls in one batch until their results arrive', () => {
    const items = buildSubAgentRenderItems([
      step('tool:start', {
        tool_call_id: 'call-file',
        tool_name: 'file',
        arguments: { action: 'read', path: '/tmp/a.txt' },
      }),
      step('tool:start', {
        tool_call_id: 'call-shell',
        tool_name: 'shell',
        arguments: { command: 'pnpm test' },
      }),
      step('tool:result', {
        tool_call_id: 'call-file',
        success: true,
        output: 'ok',
      }),
      step('tool:result', {
        tool_call_id: 'call-shell',
        success: true,
        output: 'passed',
      }),
    ])

    expect(items).toHaveLength(1)
    const item = items[0]
    expect(item.kind).toBe('tool_group')
    if (item.kind !== 'tool_group') return

    expect(item.status).toBe('completed')
    expect(item.details.map((detail) => detail.id)).toEqual(['call-file', 'call-shell'])
    expect(item.details.map((detail) => detail.status)).toEqual(['success', 'success'])
    expect(item.details[0].output).toBe('ok')
    expect(item.details[1].output).toBe('passed')
  })

  it('keeps approval state attached to the matching tool until the result resolves it', () => {
    const items = buildSubAgentRenderItems([
      step('tool:start', {
        tool_call_id: 'call-shell',
        tool_name: 'shell',
        arguments: { command: 'git push' },
      }),
      step('approval:required', {
        tool_call_id: 'call-shell',
        approval_id: 'approval-1',
        run_id: 'sub-run-1',
        approval: {
          payload: {
            command: 'git push',
            execution_mode: 'argv',
            approval_kind: 'shell_command',
          },
        },
      }),
      step('tool:result', {
        tool_call_id: 'call-shell',
        success: true,
        output: 'pushed',
      }),
    ])

    const item = items[0]
    expect(item.kind).toBe('tool_group')
    if (item.kind !== 'tool_group') return

    expect(item.status).toBe('completed')
    expect(item.details[0]).toMatchObject({
      id: 'call-shell',
      status: 'success',
      output: 'pushed',
    })
  })

  it('does not let run approval state events detach the final tool result', () => {
    const items = buildSubAgentRenderItems([
      step('tool:start', {
        tool_call_id: 'call-shell',
        tool_name: 'shell',
        arguments: { command: 'git push' },
      }),
      step('approval:required', {
        tool_call_id: 'call-shell',
        approval_id: 'approval-1',
        run_id: 'sub-run-1',
        approval: {
          payload: {
            command: 'git push',
            execution_mode: 'argv',
            approval_kind: 'shell_command',
          },
        },
      }),
      step('run:waiting_for_approval', {
        tool_call_id: 'call-shell',
        approval_id: 'approval-1',
        run_id: 'sub-run-1',
      }),
      step('tool:result', {
        tool_call_id: 'call-shell',
        success: true,
        output: 'pushed',
      }),
    ])

    expect(items).toHaveLength(1)
    const item = items[0]
    expect(item.kind).toBe('tool_group')
    if (item.kind !== 'tool_group') return

    expect(item.status).toBe('completed')
    expect(item.details[0]).toMatchObject({
      id: 'call-shell',
      status: 'success',
      output: 'pushed',
    })
  })
})

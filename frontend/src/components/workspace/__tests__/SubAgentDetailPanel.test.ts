/**
 * 文件功能：SubAgentDetailPanel 中 buildSubAgentRenderItems 函数的测试
 * 文件描述：验证子代理（SubAgent）事件流（tool:start / tool:result / approval:required / run:waiting_for_approval 等）被正确归并为可渲染的分组条目
 * 核心逻辑：构造一系列子代理事件（SubAgentStep），调用 buildSubAgentRenderItems 转换为渲染条目，断言并行工具调用被合并进同一个 tool_group、批准状态正确挂载在对应工具上、且不会被中间的运行级事件打断最终结果的关联
 */
import { describe, expect, it } from 'vitest'
import type { SubAgentStep } from '@/hooks/useSubAgentEvents'
import { buildSubAgentRenderItems } from '../SubAgentDetailPanel'

/**
 * 函数名：step
 * 入参：
 *   - eventType (string): 事件类型，如 'tool:start'、'tool:result'、'approval:required'、'run:waiting_for_approval'
 *   - payload (Record<string, unknown>): 事件负载内容
 * 功能：构造一条测试用的子代理事件对象（SubAgentStep），减少各测试用例重复编写事件结构
 * 运行逻辑：直接组装 eventType、payload 和当前时间戳（receivedAt）为一个 SubAgentStep 对象
 * 出参：SubAgentStep - 构造好的子代理事件对象
 */
function step(eventType: string, payload: Record<string, unknown>): SubAgentStep {
  return {
    eventType,
    payload,
    receivedAt: Date.now(),
  }
}

// 测试目标：buildSubAgentRenderItems —— 将子代理原始事件流归并为分组渲染条目的核心转换逻辑
describe('buildSubAgentRenderItems', () => {
  // 场景：多个并行发起的工具调用（tool:start）应先合并进同一个批次，等它们各自的结果（tool:result）都到达后再标记为完成
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

  // 场景：某个工具调用触发了批准请求（approval:required）后，批准状态应一直挂在该工具上，直到最终结果（tool:result）到达并解决它
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

  // 场景：即使在批准请求之后又收到了运行级的"等待批准"事件（run:waiting_for_approval），也不应该让这个中间事件
  // 打断/脱钩最终的工具调用结果（tool:result 仍应正常关联到对应工具并标记为完成）
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

// MessageQueueBar 组件的渲染测试：用 renderToStaticMarkup 做服务端静态渲染断言，
// 覆盖"排队项渲染""暂停横幅""空队列不渲染"三个场景。
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MessageQueueBar } from '../MessageQueueBar'
import type { MessageQueueState } from '@/types/conversation'

function buildQueue(overrides: Partial<MessageQueueState> = {}): MessageQueueState {
  return {
    sessionId: 'session-1',
    paused: false,
    items: [
      {
        id: 'qmsg-1',
        content: '第一条排队消息',
        attachmentIds: [],
        providerId: null,
        modelId: null,
        createdAt: '2026-10-29T10:00:00Z',
      },
      {
        id: 'qmsg-2',
        content: '第二条排队消息',
        attachmentIds: [],
        providerId: null,
        modelId: null,
        createdAt: '2026-10-29T10:00:01Z',
      },
    ],
    ...overrides,
  }
}

describe('MessageQueueBar', () => {
  // 参数：无。
  // 验证：queue 为 null、或 items 为空且未暂停时，组件不渲染任何内容。
  it('renders nothing when queue is empty and not paused', () => {
    const noop = () => undefined
    expect(
      renderToStaticMarkup(
        React.createElement(MessageQueueBar, {
          queue: null,
          onUpdate: noop,
          onRemove: noop,
          onSendNow: noop,
          onResume: noop,
        })
      )
    ).toBe('')

    expect(
      renderToStaticMarkup(
        React.createElement(MessageQueueBar, {
          queue: buildQueue({ items: [] }),
          onUpdate: noop,
          onRemove: noop,
          onSendNow: noop,
          onResume: noop,
        })
      )
    ).toBe('')
  })

  // 参数：无。
  // 验证：排队项按序渲染内容与序号，容器携带 data-message-queue-bar 标识，
  // 并展示"回复结束后自动按序执行"的说明文案。
  it('renders queued items in order with position badges', () => {
    const html = renderToStaticMarkup(
      React.createElement(MessageQueueBar, {
        queue: buildQueue(),
        onUpdate: () => undefined,
        onRemove: () => undefined,
        onSendNow: () => undefined,
        onResume: () => undefined,
      })
    )

    expect(html).toContain('data-message-queue-bar="true"')
    expect(html).toContain('data-queue-item="qmsg-1"')
    expect(html).toContain('data-queue-item="qmsg-2"')
    expect(html).toContain('第一条排队消息')
    expect(html).toContain('第二条排队消息')
    expect(html).toContain('待发送队列')
    expect(html).toContain('自动按序执行')
  })

  // 参数：无。
  // 验证：paused 为 true 时渲染暂停横幅与"恢复队列"按钮；未暂停时不渲染。
  it('renders paused banner with resume button when queue is paused', () => {
    const html = renderToStaticMarkup(
      React.createElement(MessageQueueBar, {
        queue: buildQueue({ paused: true }),
        onUpdate: () => undefined,
        onRemove: () => undefined,
        onSendNow: () => undefined,
        onResume: () => undefined,
      })
    )

    expect(html).toContain('队列已暂停')
    expect(html).toContain('恢复队列')

    const idleHtml = renderToStaticMarkup(
      React.createElement(MessageQueueBar, {
        queue: buildQueue(),
        onUpdate: () => undefined,
        onRemove: () => undefined,
        onSendNow: () => undefined,
        onResume: () => undefined,
      })
    )
    expect(idleHtml).not.toContain('队列已暂停')
  })
})

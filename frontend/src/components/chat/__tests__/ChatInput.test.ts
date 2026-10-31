// ChatInput 组件的渲染测试：用 renderToStaticMarkup 做服务端静态渲染断言，
// 覆盖“未选择供应商/模型时的占位态”和“运行状态提示条的渲染”两个场景。
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ChatInput } from '../ChatInput'

describe('ChatInput', () => {
  // 参数：无。
  // 验证：当 selectedProviderId/selectedModelId 均为 null 时，供应商/模型下拉框渲染为空值选项，
  // 且分别显示“请选择供应商”“请选择模型”的占位文案。
  it('renders empty placeholder options when no provider or model is selected yet', () => {
    const html = renderToStaticMarkup(
      React.createElement(ChatInput, {
        onSend: () => undefined,
        providerOptions: [{ id: 'provider-a', label: 'Provider A' }],
        modelOptions: [{ id: 'model-a', label: 'Model A' }],
        selectedProviderId: null,
        selectedModelId: null,
      })
    )

    expect(html).toContain('value=""')
    expect(html).toContain('请选择供应商')
    expect(html).toContain('请选择模型')
  })

  // 参数：无。
  // 验证：传入 runtimeStatusLabel + isLoading + canCancel 时，会渲染带三条动画条的运行状态提示头
  // （data-chat-running 相关属性），并显示传入的状态文案。
  it('renders a prominent running header with animated bars when runtime status is present', () => {
    const html = renderToStaticMarkup(
      React.createElement(ChatInput, {
        onSend: () => undefined,
        runtimeStatusLabel: '正在执行工具',
        isLoading: true,
        canCancel: true,
      })
    )

    expect(html).toContain('data-chat-running="true"')
    expect(html).toContain('data-chat-running-bar="1"')
    expect(html).toContain('data-chat-running-bar="2"')
    expect(html).toContain('data-chat-running-bar="3"')
    expect(html).toContain('正在执行工具')
  })
})

describe('ChatInput 消息队列（运行中排队发送）', () => {
  // 参数：isLoading + canCancel（模拟会话运行中）。
  // 验证：运行中输入框不再禁用（textarea 无 disabled 属性），并出现"排队"按钮与取消按钮。
  it('keeps textarea enabled and shows queue button while a run is active', () => {
    const html = renderToStaticMarkup(
      React.createElement(ChatInput, {
        onSend: () => undefined,
        isLoading: true,
        canCancel: true,
      })
    )

    expect(html).not.toMatch(/<textarea[^>]*\sdisabled=/)
    expect(html).toContain('排队')
    expect(html).toContain('取消')
  })

  // 参数：isCancelling（取消中，不可提交）。
  // 验证：取消中不渲染"排队"按钮，仅保留取消按钮。
  it('hides queue button while cancelling', () => {
    const html = renderToStaticMarkup(
      React.createElement(ChatInput, {
        onSend: () => undefined,
        isLoading: true,
        canCancel: false,
        isCancelling: true,
      })
    )

    expect(html).not.toContain('排队')
    expect(html).toContain('取消中')
  })
})

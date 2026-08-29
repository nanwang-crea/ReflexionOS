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

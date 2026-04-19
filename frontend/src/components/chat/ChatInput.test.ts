import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ChatInput } from './ChatInput'

describe('ChatInput', () => {
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
})

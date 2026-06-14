import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationMessage, Plan } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'

const { settingsState, sessionDataState, selectionState, confirmActionMock } = vi.hoisted(() => ({
  settingsState: {
    configured: true,
    loaded: true,
  },
  sessionDataState: {
    currentProject: {
      id: 'project-1',
      name: 'Project One',
      path: '/tmp/project-one',
    },
    currentSessionSummary: {
      id: 'session-1',
      projectId: 'project-1',
      title: 'Session One',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
  },
  selectionState: {
    selection: {
      providerId: 'provider-a',
      modelId: 'model-a',
    },
    availableProviders: [{ id: 'provider-a', name: 'Provider A' }],
    selectedModels: [{ id: 'model-a', display_name: 'Model A' }],
    handleProviderChange: vi.fn(),
    handleModelChange: vi.fn(),
  },
  confirmActionMock: vi.fn(() => true),
}))

vi.mock('@/features/settings/stores/settings.store', () => ({
  useSettingsStore: () => settingsState,
}))

vi.mock('../useSessionData', () => ({
  useSessionData: () => sessionDataState,
}))

vi.mock('../useSessionSelection', () => ({
  useSessionSelection: () => selectionState,
}))

vi.mock('@/services/dialogService', () => ({
  nativeDialogService: {
    notifyError: vi.fn(),
    confirmAction: confirmActionMock,
    promptText: vi.fn(),
  },
}))

function createOptions(overrides: Record<string, unknown> = {}) {
  return {
    messages: [] as ConversationMessage[],
    isRunning: false,
    isCancelling: false,
    connectionStatus: 'connected' as const,
    retryInfo: null as LlmRetryDto | null,
    plan: null as Plan | null,
    hasMore: false,
    onLoadMore: vi.fn(),
    onReset: vi.fn(),
    onApprovalAction: undefined,
    editAndRerun: vi.fn(),
    ...overrides,
  }
}

async function renderUseCurrentSessionViewModel(options: ReturnType<typeof createOptions>) {
  const React = await import('react')
  const ReactDOMServer = await import('react-dom/server')
  const { useCurrentSessionViewModel } = await import('../useCurrentSessionViewModel')
  let result: ReturnType<typeof useCurrentSessionViewModel> | undefined

  function TestComponent() {
    result = useCurrentSessionViewModel(options)
    return null
  }

  ReactDOMServer.renderToString(React.createElement(TestComponent))

  return {
    getResult() {
      if (!result) {
        throw new Error('Hook result was not captured')
      }
      return result
    },
  }
}

describe('useCurrentSessionViewModel', () => {
  beforeEach(() => {
    confirmActionMock.mockReset()
    confirmActionMock.mockReturnValue(true)
    selectionState.handleProviderChange.mockClear()
    selectionState.handleModelChange.mockClear()
    sessionDataState.currentProject = {
      id: 'project-1',
      name: 'Project One',
      path: '/tmp/project-one',
    }
    sessionDataState.currentSessionSummary = {
      id: 'session-1',
      projectId: 'project-1',
      title: 'Session One',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    }
    selectionState.selection = {
      providerId: 'provider-a',
      modelId: 'model-a',
    }
  })

  it('uses dialogService confirmation before regenerating a message', async () => {
    const editAndRerun = vi.fn()
    const harness = await renderUseCurrentSessionViewModel(createOptions({ editAndRerun }))

    harness.getResult().transcriptProps.onRegenerateMessage('message-1')

    expect(confirmActionMock).toHaveBeenCalledWith(
      '重新生成回复？此消息之后的对话内容将被清除，AI 将基于当前上下文重新生成回复。',
    )
    expect(editAndRerun).toHaveBeenCalledWith({
      messageId: 'message-1',
      newContent: null,
      providerId: 'provider-a',
      modelId: 'model-a',
    })
  })

  it('does not rerun when confirmation is declined', async () => {
    confirmActionMock.mockReturnValue(false)
    const editAndRerun = vi.fn()
    const harness = await renderUseCurrentSessionViewModel(createOptions({ editAndRerun }))

    harness.getResult().transcriptProps.onRegenerateMessage('message-1')
    expect(editAndRerun).not.toHaveBeenCalled()
  })

  it('uses the current selection when editing a message', async () => {
    const editAndRerun = vi.fn()
    selectionState.selection = {
      providerId: 'provider-b',
      modelId: 'model-b',
    }
    const harness = await renderUseCurrentSessionViewModel(createOptions({ editAndRerun }))

    harness.getResult().transcriptProps.onEditMessage('message-1', 'updated content')

    expect(editAndRerun).toHaveBeenCalledWith({
      messageId: 'message-1',
      newContent: 'updated content',
      providerId: 'provider-b',
      modelId: 'model-b',
    })
  })
})

import { describe, expect, it } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'
import { createConversationStore } from './conversationStore'

function buildSnapshot(): ConversationSnapshot {
  return {
    session: {
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      preferredProviderId: undefined,
      preferredModelId: undefined,
      lastEventSeq: 2,
      activeTurnId: 'turn-1',
      createdAt: '2026-04-24T10:00:00Z',
      updatedAt: '2026-04-24T10:00:02Z',
    },
    turns: [
      {
        id: 'turn-1',
        sessionId: 'session-1',
        turnIndex: 1,
        rootMessageId: 'msg-1',
        status: 'running',
        activeRunId: 'run-1',
        createdAt: '2026-04-24T10:00:00Z',
        updatedAt: '2026-04-24T10:00:01Z',
        completedAt: null,
      },
    ],
    runs: [
      {
        id: 'run-1',
        sessionId: 'session-1',
        turnId: 'turn-1',
        attemptIndex: 1,
        status: 'running',
        providerId: 'provider-a',
        modelId: 'model-a',
        workspaceRef: '/tmp/reflexion',
        startedAt: null,
        finishedAt: null,
        errorCode: null,
        errorMessage: null,
      },
    ],
    messages: [
      {
        id: 'msg-1',
        sessionId: 'session-1',
        turnId: 'turn-1',
        runId: null,
        messageIndex: 1,
        role: 'assistant',
        messageType: 'assistant_message',
        streamState: 'streaming',
        displayMode: 'default',
        contentText: '正在',
        payloadJson: {},
        createdAt: '2026-04-24T10:00:00Z',
        updatedAt: '2026-04-24T10:00:00Z',
        completedAt: null,
      },
    ],
  }
}

describe('createConversationStore', () => {
  it('sets snapshot, applies live updates, and keeps durable seq unchanged for live streaming', () => {
    const store = createConversationStore()
    store.getState().setSnapshot('session-1', buildSnapshot())

    store.getState().applyLiveEvent('session-1', {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-1',
      messageType: 'assistant_message',
      delta: '分析项目结构',
      contentText: '正在分析项目结构',
      streamState: 'streaming',
    })

    expect(store.getState().conversationsBySessionId['session-1'].lastEventSeq).toBe(2)
    expect(store.getState().conversationsBySessionId['session-1'].messagesById['msg-1'].contentText).toBe(
      '正在分析项目结构'
    )
  })

  it('stores live state for a not-yet-durable assistant message', () => {
    const store = createConversationStore()
    store.getState().setSnapshot('session-1', buildSnapshot())

    store.getState().setLiveState('session-1', {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-live',
      messageType: 'assistant_message',
      contentText: '继续输出中',
      streamState: 'streaming',
    })

    expect(store.getState().conversationsBySessionId['session-1'].messagesById['msg-live'].contentText).toBe(
      '继续输出中'
    )
  })

  it('clears a conversation by session id', () => {
    const store = createConversationStore()
    store.getState().setSnapshot('session-1', buildSnapshot())

    store.getState().clearConversation('session-1')

    expect(store.getState().conversationsBySessionId).toEqual({})
  })
})

import { describe, expect, it } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'
import { createConversationStore } from '../stores/conversation.store'

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
        turnMessageIndex: 1,
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
    hasMore: false,
    nextBeforeTurnId: null,
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

  it('keeps the terminal older-page cursor after a later snapshot refresh', () => {
    const store = createConversationStore()

    store.getState().setSnapshot('session-1', {
      ...buildSnapshot(),
      turns: [
        {
          id: 'turn-0',
          sessionId: 'session-1',
          turnIndex: 0,
          rootMessageId: 'msg-0',
          status: 'completed',
          activeRunId: null,
          createdAt: '2026-04-24T09:59:00Z',
          updatedAt: '2026-04-24T09:59:10Z',
          completedAt: '2026-04-24T09:59:10Z',
        },
        ...buildSnapshot().turns,
      ],
      messages: [
        {
          id: 'msg-0',
          sessionId: 'session-1',
          turnId: 'turn-0',
          runId: null,
          turnMessageIndex: 1,
          role: 'user',
          messageType: 'user_message',
          streamState: 'completed',
          displayMode: 'default',
          contentText: 'older',
          payloadJson: {},
          createdAt: '2026-04-24T09:59:00Z',
          updatedAt: '2026-04-24T09:59:00Z',
          completedAt: '2026-04-24T09:59:00Z',
        },
        ...buildSnapshot().messages,
      ],
      hasMore: false,
      nextBeforeTurnId: null,
    })

    store.getState().setSnapshot('session-1', {
      ...buildSnapshot(),
      hasMore: true,
      nextBeforeTurnId: 'turn-1',
    })

    expect(store.getState().conversationsBySessionId['session-1'].turnOrder).toEqual(['turn-0', 'turn-1'])
    expect(store.getState().conversationsBySessionId['session-1'].hasMore).toBe(false)
    expect(store.getState().conversationsBySessionId['session-1'].nextBeforeTurnId).toBeNull()
  })

  it('keeps the older-history cursor after a later snapshot refresh', () => {
    const store = createConversationStore()

    store.getState().setSnapshot('session-1', {
      ...buildSnapshot(),
      turns: [
        {
          id: 'turn-0',
          sessionId: 'session-1',
          turnIndex: 0,
          rootMessageId: 'msg-0',
          status: 'completed',
          activeRunId: null,
          createdAt: '2026-04-24T09:59:00Z',
          updatedAt: '2026-04-24T09:59:10Z',
          completedAt: '2026-04-24T09:59:10Z',
        },
        ...buildSnapshot().turns,
      ],
      messages: [
        {
          id: 'msg-0',
          sessionId: 'session-1',
          turnId: 'turn-0',
          runId: null,
          turnMessageIndex: 1,
          role: 'user',
          messageType: 'user_message',
          streamState: 'completed',
          displayMode: 'default',
          contentText: 'older',
          payloadJson: {},
          createdAt: '2026-04-24T09:59:00Z',
          updatedAt: '2026-04-24T09:59:00Z',
          completedAt: '2026-04-24T09:59:00Z',
        },
        ...buildSnapshot().messages,
      ],
      hasMore: true,
      nextBeforeTurnId: 'turn-0',
    })

    store.getState().setSnapshot('session-1', {
      ...buildSnapshot(),
      hasMore: true,
      nextBeforeTurnId: 'turn-1',
    })

    expect(store.getState().conversationsBySessionId['session-1'].turnOrder).toEqual(['turn-0', 'turn-1'])
    expect(store.getState().conversationsBySessionId['session-1'].hasMore).toBe(true)
    expect(store.getState().conversationsBySessionId['session-1'].nextBeforeTurnId).toBe('turn-0')
  })

  it('treats a null cursor as terminal pagination state when updating pagination directly', () => {
    const store = createConversationStore()
    store.getState().setSnapshot('session-1', {
      ...buildSnapshot(),
      hasMore: true,
      nextBeforeTurnId: 'turn-1',
    })

    store.getState().setPagination('session-1', {
      hasMore: true,
      nextBeforeTurnId: null,
    })

    expect(store.getState().conversationsBySessionId['session-1'].hasMore).toBe(false)
    expect(store.getState().conversationsBySessionId['session-1'].nextBeforeTurnId).toBeNull()
  })

  it('clears a conversation by session id', () => {
    const store = createConversationStore()
    store.getState().setSnapshot('session-1', buildSnapshot())

    store.getState().clearConversation('session-1')

    expect(store.getState().conversationsBySessionId).toEqual({})
  })
})

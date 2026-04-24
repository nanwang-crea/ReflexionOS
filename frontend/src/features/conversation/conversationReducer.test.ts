import { describe, expect, it } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'
import {
  applyConversationEvent,
  applyConversationSnapshot,
} from './conversationReducer'

function buildSnapshot(): ConversationSnapshot {
  return {
    session: {
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
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
        id: 'msg-2',
        sessionId: 'session-1',
        turnId: 'turn-1',
        runId: 'run-1',
        messageIndex: 2,
        role: 'assistant',
        messageType: 'assistant_message',
        streamState: 'streaming',
        displayMode: 'default',
        contentText: '正在',
        payloadJson: {},
        createdAt: '2026-04-24T10:00:01Z',
        updatedAt: '2026-04-24T10:00:01Z',
        completedAt: null,
      },
      {
        id: 'msg-1',
        sessionId: 'session-1',
        turnId: 'turn-1',
        runId: null,
        messageIndex: 1,
        role: 'user',
        messageType: 'user_message',
        streamState: 'completed',
        displayMode: 'default',
        contentText: 'hello',
        payloadJson: {},
        createdAt: '2026-04-24T10:00:00Z',
        updatedAt: '2026-04-24T10:00:00Z',
        completedAt: '2026-04-24T10:00:00Z',
      },
    ],
  }
}

describe('conversationReducer', () => {
  it('imports snapshot entities and keeps message order stable', () => {
    const state = applyConversationSnapshot(undefined, buildSnapshot())

    expect(state.messageOrder).toEqual(['msg-1', 'msg-2'])
    expect(state.lastEventSeq).toBe(2)
  })

  it('appends delta events to existing assistant messages', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())

    const next = applyConversationEvent(base, {
      id: 'evt-3',
      sessionId: 'session-1',
      seq: 3,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.delta_appended',
      payloadJson: { message_id: 'msg-2', delta: '分析项目结构' },
      createdAt: '2026-04-24T10:00:02Z',
    })

    expect(next.messagesById['msg-2'].contentText).toBe('正在分析项目结构')
    expect(next.lastEventSeq).toBe(3)
  })

  it('ignores duplicate incremental events with the same seq', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())
    const first = applyConversationEvent(base, {
      id: 'evt-3',
      sessionId: 'session-1',
      seq: 3,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.delta_appended',
      payloadJson: { message_id: 'msg-2', delta: '分析项目结构' },
      createdAt: '2026-04-24T10:00:02Z',
    })

    const duplicate = applyConversationEvent(first, {
      id: 'evt-3-replay',
      sessionId: 'session-1',
      seq: 3,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.delta_appended',
      payloadJson: { message_id: 'msg-2', delta: '分析项目结构' },
      createdAt: '2026-04-24T10:00:03Z',
    })

    expect(duplicate.messagesById['msg-2'].contentText).toBe('正在分析项目结构')
    expect(duplicate.lastEventSeq).toBe(3)
  })

  it('applies payload updates to existing messages', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())

    const next = applyConversationEvent(base, {
      id: 'evt-4',
      sessionId: 'session-1',
      seq: 4,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.payload_updated',
      payloadJson: {
        payload_json: {
          tool_name: 'shell',
          status: 'ok',
        },
      },
      createdAt: '2026-04-24T10:00:03Z',
    })

    expect(next.messagesById['msg-2'].payloadJson).toEqual({
      tool_name: 'shell',
      status: 'ok',
    })
    expect(next.lastEventSeq).toBe(4)
  })
})

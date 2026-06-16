import { describe, expect, it } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'
import {
  applyConversationEvent,
  applyConversationLiveEvent,
  applyConversationLiveState,
  applyConversationSnapshot,
  createEmptyConversationState,
} from '../conversation.reducer'

function buildSnapshot(): ConversationSnapshot {
  return {
    session: {
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      agentMode: 'build',
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
        turnMessageIndex: 2,
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
        turnMessageIndex: 1,
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
    hasMore: false,
    nextBeforeTurnId: null,
  }
}

describe('conversationReducer', () => {
  it('starts empty conversations in terminal pagination state until a cursor is loaded', () => {
    const state = createEmptyConversationState('session-1')

    expect(state.hasMore).toBe(false)
    expect(state.nextBeforeTurnId).toBeNull()
  })

  it('imports snapshot entities and keeps message order stable', () => {
    const state = applyConversationSnapshot(undefined, buildSnapshot())

    expect(state.messageOrder).toEqual(['msg-1', 'msg-2'])
    expect(state.lastEventSeq).toBe(2)
  })

  it('preserves a terminal older-page cursor after a later latest snapshot refresh', () => {
    const fullHistoryState = applyConversationSnapshot(undefined, {
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

    const refreshedLatestState = applyConversationSnapshot(fullHistoryState, {
      ...buildSnapshot(),
      hasMore: true,
      nextBeforeTurnId: 'turn-1',
    })

    expect(refreshedLatestState.turnOrder).toEqual(['turn-0', 'turn-1'])
    expect(refreshedLatestState.hasMore).toBe(false)
    expect(refreshedLatestState.nextBeforeTurnId).toBeNull()
  })

  it('preserves the older-history cursor after a later latest snapshot refresh', () => {
    const partiallyLoadedHistoryState = applyConversationSnapshot(undefined, {
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

    const refreshedLatestState = applyConversationSnapshot(partiallyLoadedHistoryState, {
      ...buildSnapshot(),
      hasMore: true,
      nextBeforeTurnId: 'turn-1',
    })

    expect(refreshedLatestState.turnOrder).toEqual(['turn-0', 'turn-1'])
    expect(refreshedLatestState.hasMore).toBe(true)
    expect(refreshedLatestState.nextBeforeTurnId).toBe('turn-0')
  })

  it('uses a null cursor as the single source of truth for terminal pagination state', () => {
    const refreshedLatestState = applyConversationSnapshot(undefined, {
      ...buildSnapshot(),
      hasMore: true,
      nextBeforeTurnId: null,
    })

    expect(refreshedLatestState.hasMore).toBe(false)
    expect(refreshedLatestState.nextBeforeTurnId).toBeNull()
  })

  it('applies live assistant chunks without advancing durable seq', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())

    const next = applyConversationLiveEvent(base, {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      messageType: 'assistant_message',
      delta: '分析项目结构',
      contentText: '正在分析项目结构',
      streamState: 'streaming',
    })

    expect(next.messagesById['msg-2'].contentText).toBe('正在分析项目结构')
    expect(next.lastEventSeq).toBe(2)
  })

  it('merges live payload updates such as reasoning text into assistant messages', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())

    const next = applyConversationLiveEvent(base, {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      messageType: 'assistant_message',
      contentText: '正在分析项目结构',
      streamState: 'streaming',
      payloadJson: {
        reasoning_text: '先查看项目结构',
      },
    })

    expect(next.messagesById['msg-2'].payloadJson.reasoning_text).toBe('先查看项目结构')
  })

  it('creates an ephemeral assistant message from live state when durable snapshot has none yet', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())
    const withoutAssistant = {
      ...base,
      messageOrder: ['msg-1'],
      messagesById: {
        'msg-1': base.messagesById['msg-1'],
      },
    }

    const next = applyConversationLiveState(withoutAssistant, {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-live',
      messageType: 'assistant_message',
      contentText: '继续输出中',
      streamState: 'streaming',
    })

    expect(next.messageOrder).toEqual(['msg-1', 'msg-live'])
    expect(next.messagesById['msg-live'].contentText).toBe('继续输出中')
    expect(next.messagesById['msg-live'].streamState).toBe('streaming')
    expect(next.lastEventSeq).toBe(2)
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

  it('updates durable assistant content when a terminal content commit arrives', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())

    const next = applyConversationEvent(base, {
      id: 'evt-5',
      sessionId: 'session-1',
      seq: 5,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.content_committed',
      payloadJson: { content_text: '最终回答' },
      createdAt: '2026-04-24T10:00:04Z',
    })

    expect(next.messagesById['msg-2'].contentText).toBe('最终回答')
    expect(next.lastEventSeq).toBe(5)
  })

  it('normalizes snake_case attachments from realtime message.created events', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())

    const next = applyConversationEvent(base, {
      id: 'evt-attachment-1',
      sessionId: 'session-1',
      seq: 6,
      turnId: 'turn-1',
      runId: null,
      messageId: 'msg-attachment-1',
      eventType: 'message.created',
      payloadJson: {
        message_id: 'msg-attachment-1',
        role: 'user',
        message_type: 'user_message',
        turn_message_index: 3,
        display_mode: 'default',
        content_text: '',
        payload_json: {},
        attachments: [
          {
            id: 'att-1',
            type: 'image',
            mime_type: 'image/png',
            file_path: '/tmp/reflexion/image.png',
            file_size: 123,
            created_at: '2026-04-24T10:00:00Z',
            url: '/api/sessions/session-1/attachments/att-1',
          },
        ],
      },
      createdAt: '2026-04-24T10:00:06Z',
    })

    expect(next.messagesById['msg-attachment-1'].attachments).toEqual([
      {
        id: 'att-1',
        type: 'image',
        mimeType: 'image/png',
        filePath: '/tmp/reflexion/image.png',
        fileSize: 123,
        createdAt: '2026-04-24T10:00:00Z',
        url: '/api/sessions/session-1/attachments/att-1',
      },
    ])
  })

  it('completes any non-terminal messages for a run when run.completed arrives', () => {
    const base = applyConversationSnapshot(undefined, {
      ...buildSnapshot(),
      messages: [
        ...buildSnapshot().messages,
        {
          id: 'msg-tool-1',
          sessionId: 'session-1',
          turnId: 'turn-1',
          runId: 'run-1',
          turnMessageIndex: 3,
          role: 'tool',
          messageType: 'tool_trace',
          streamState: 'idle',
          displayMode: 'default',
          contentText: '',
          payloadJson: {
            tool_name: 'file',
            arguments: { action: 'read', path: '/tmp/reflexion/src/app.ts' },
          },
          createdAt: '2026-04-24T10:00:02Z',
          updatedAt: '2026-04-24T10:00:02Z',
          completedAt: null,
        },
      ],
    })

    const next = applyConversationEvent(base, {
      id: 'evt-6',
      sessionId: 'session-1',
      seq: 6,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: null,
      eventType: 'run.completed',
      payloadJson: { finished_at: '2026-04-24T10:00:05Z' },
      createdAt: '2026-04-24T10:00:05Z',
    })

    expect(next.runsById['run-1'].status).toBe('completed')
    expect(next.messagesById['msg-tool-1'].streamState).toBe('completed')
    expect(next.messagesById['msg-tool-1'].completedAt).toBe('2026-04-24T10:00:05Z')
  })

  it('preserves a live streaming assistant message across snapshot refresh while the run is still active', () => {
    const base = applyConversationSnapshot(undefined, buildSnapshot())
    const liveState = applyConversationLiveState(base, {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-live',
      messageType: 'assistant_message',
      contentText: '正在流式输出',
      streamState: 'streaming',
    })

    const refreshed = applyConversationSnapshot(liveState, buildSnapshot())

    expect(refreshed.messageOrder).toEqual(['msg-1', 'msg-2', 'msg-live'])
    expect(refreshed.messagesById['msg-live'].contentText).toBe('正在流式输出')
    expect(refreshed.messagesById['msg-live'].streamState).toBe('streaming')
  })

  describe('run intermediate status events', () => {
    it('updates run status to running when run.started arrives', () => {
      const base = applyConversationSnapshot(undefined, buildSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-10',
        sessionId: 'session-1',
        seq: 10,
        turnId: 'turn-1',
        runId: 'run-1',
        messageId: null,
        eventType: 'run.started',
        payloadJson: { started_at: '2026-04-24T10:00:03Z' },
        createdAt: '2026-04-24T10:00:03Z',
      })

      expect(next.runsById['run-1'].status).toBe('running')
    })

    it('updates run status to waiting_for_approval when run.waiting_for_approval arrives', () => {
      const base = applyConversationSnapshot(undefined, buildSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-11',
        sessionId: 'session-1',
        seq: 11,
        turnId: 'turn-1',
        runId: 'run-1',
        messageId: null,
        eventType: 'run.waiting_for_approval',
        payloadJson: {},
        createdAt: '2026-04-24T10:00:04Z',
      })

      expect(next.runsById['run-1'].status).toBe('waiting_for_approval')
    })

    it('updates run status to resuming when run.resuming arrives', () => {
      const base = applyConversationSnapshot(undefined, buildSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-12',
        sessionId: 'session-1',
        seq: 12,
        turnId: 'turn-1',
        runId: 'run-1',
        messageId: null,
        eventType: 'run.resuming',
        payloadJson: {},
        createdAt: '2026-04-24T10:00:05Z',
      })

      expect(next.runsById['run-1'].status).toBe('resuming')
    })

    it('creates a new run entry when run.created arrives', () => {
      const base = applyConversationSnapshot(undefined, buildSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-13',
        sessionId: 'session-1',
        seq: 13,
        turnId: 'turn-1',
        runId: 'run-new',
        messageId: null,
        eventType: 'run.created',
        payloadJson: {
          run_id: 'run-new',
          turn_id: 'turn-1',
          attempt_index: 2,
          provider_id: 'provider-b',
          model_id: 'model-b',
          workspace_ref: '/tmp/reflexion',
        },
        createdAt: '2026-04-24T10:00:06Z',
      })

      expect(next.runsById['run-new']).toBeDefined()
      expect(next.runsById['run-new'].status).toBe('created')
      expect(next.runsById['run-new'].providerId).toBe('provider-b')
    })

    it('creates a new turn entry when turn.created arrives', () => {
      const base = applyConversationSnapshot(undefined, buildSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-14',
        sessionId: 'session-1',
        seq: 14,
        turnId: 'turn-new',
        runId: null,
        messageId: null,
        eventType: 'turn.created',
        payloadJson: {
          turn_id: 'turn-new',
          turn_index: 2,
          root_message_id: 'msg-new-root',
        },
        createdAt: '2026-04-24T10:00:07Z',
      })

      expect(next.turnsById['turn-new']).toBeDefined()
      expect(next.turnsById['turn-new'].turnIndex).toBe(2)
      expect(next.turnOrder).toContain('turn-new')
    })
  })

  describe('messages.truncated', () => {
    function buildTwoTurnSnapshot(): ConversationSnapshot {
      return {
        session: {
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          preferredProviderId: 'provider-a',
          preferredModelId: 'model-a',
          lastEventSeq: 8,
          activeTurnId: 'turn-2',
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:10Z',
        },
        turns: [
          {
            id: 'turn-1',
            sessionId: 'session-1',
            turnIndex: 1,
            rootMessageId: 'msg-1',
            status: 'completed',
            activeRunId: null,
            createdAt: '2026-04-24T10:00:00Z',
            updatedAt: '2026-04-24T10:00:05Z',
            completedAt: '2026-04-24T10:00:05Z',
          },
          {
            id: 'turn-2',
            sessionId: 'session-1',
            turnIndex: 2,
            rootMessageId: 'msg-3',
            status: 'running',
            activeRunId: 'run-2',
            createdAt: '2026-04-24T10:00:06Z',
            updatedAt: '2026-04-24T10:00:10Z',
            completedAt: null,
          },
        ],
        runs: [
          {
            id: 'run-1',
            sessionId: 'session-1',
            turnId: 'turn-1',
            attemptIndex: 1,
            status: 'completed',
            providerId: 'provider-a',
            modelId: 'model-a',
            workspaceRef: '/tmp/reflexion',
            startedAt: '2026-04-24T10:00:01Z',
            finishedAt: '2026-04-24T10:00:05Z',
            errorCode: null,
            errorMessage: null,
          },
          {
            id: 'run-2',
            sessionId: 'session-1',
            turnId: 'turn-2',
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
          {
            id: 'msg-2',
            sessionId: 'session-1',
            turnId: 'turn-1',
            runId: 'run-1',
            turnMessageIndex: 2,
            role: 'assistant',
            messageType: 'assistant_message',
            streamState: 'completed',
            displayMode: 'default',
            contentText: 'hi there',
            payloadJson: {},
            createdAt: '2026-04-24T10:00:01Z',
            updatedAt: '2026-04-24T10:00:05Z',
            completedAt: '2026-04-24T10:00:05Z',
          },
          {
            id: 'msg-3',
            sessionId: 'session-1',
            turnId: 'turn-2',
            runId: null,
            turnMessageIndex: 1,
            role: 'user',
            messageType: 'user_message',
            streamState: 'completed',
            displayMode: 'default',
            contentText: 'follow-up',
            payloadJson: {},
            createdAt: '2026-04-24T10:00:06Z',
            updatedAt: '2026-04-24T10:00:06Z',
            completedAt: '2026-04-24T10:00:06Z',
          },
          {
            id: 'msg-4',
            sessionId: 'session-1',
            turnId: 'turn-2',
            runId: 'run-2',
            turnMessageIndex: 2,
            role: 'assistant',
            messageType: 'assistant_message',
            streamState: 'streaming',
            displayMode: 'default',
            contentText: 'answering',
            payloadJson: {},
            createdAt: '2026-04-24T10:00:07Z',
            updatedAt: '2026-04-24T10:00:07Z',
            completedAt: null,
          },
        ],
        hasMore: false,
        nextBeforeTurnId: null,
      }
    }

    it('removes specified turns and their messages/runs from state', () => {
      const base = applyConversationSnapshot(undefined, buildTwoTurnSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-trunc-1',
        sessionId: 'session-1',
        seq: 9,
        turnId: null,
        runId: null,
        messageId: null,
        eventType: 'messages.truncated',
        payloadJson: {
          message_id: 'msg-1',
          deleted_turn_ids: ['turn-1', 'turn-2'],
          is_edit: true,
          is_regenerate: false,
        },
        createdAt: '2026-04-24T10:00:11Z',
      })

      expect(next.turnOrder).toEqual([])
      expect(next.messageOrder).toEqual([])
      expect(Object.keys(next.runsById)).toEqual([])
      expect(Object.keys(next.turnsById)).toEqual([])
      expect(Object.keys(next.messagesById)).toEqual([])
    })

    it('clears activeTurnId when the active turn was truncated', () => {
      const base = applyConversationSnapshot(undefined, buildTwoTurnSnapshot())
      expect(base.session?.activeTurnId).toBe('turn-2')

      const next = applyConversationEvent(base, {
        id: 'evt-trunc-2',
        sessionId: 'session-1',
        seq: 9,
        turnId: null,
        runId: null,
        messageId: null,
        eventType: 'messages.truncated',
        payloadJson: {
          message_id: 'msg-3',
          deleted_turn_ids: ['turn-2'],
          is_edit: true,
          is_regenerate: false,
        },
        createdAt: '2026-04-24T10:00:11Z',
      })

      expect(next.session?.activeTurnId).toBeNull()
    })

    it('updates lastEventSeq', () => {
      const base = applyConversationSnapshot(undefined, buildTwoTurnSnapshot())
      expect(base.lastEventSeq).toBe(8)

      const next = applyConversationEvent(base, {
        id: 'evt-trunc-3',
        sessionId: 'session-1',
        seq: 9,
        turnId: null,
        runId: null,
        messageId: null,
        eventType: 'messages.truncated',
        payloadJson: {
          message_id: 'msg-3',
          deleted_turn_ids: ['turn-2'],
          is_edit: true,
          is_regenerate: false,
        },
        createdAt: '2026-04-24T10:00:11Z',
      })

      expect(next.lastEventSeq).toBe(9)
    })

    it('preserves turns and messages not in the deleted list', () => {
      const base = applyConversationSnapshot(undefined, buildTwoTurnSnapshot())

      const next = applyConversationEvent(base, {
        id: 'evt-trunc-4',
        sessionId: 'session-1',
        seq: 9,
        turnId: null,
        runId: null,
        messageId: null,
        eventType: 'messages.truncated',
        payloadJson: {
          message_id: 'msg-3',
          deleted_turn_ids: ['turn-2'],
          is_edit: true,
          is_regenerate: false,
        },
        createdAt: '2026-04-24T10:00:11Z',
      })

      expect(next.turnOrder).toEqual(['turn-1'])
      expect(next.turnsById['turn-1']).toBeDefined()
      expect(next.runsById['run-1']).toBeDefined()
      expect(next.messageOrder).toEqual(['msg-1', 'msg-2'])
      expect(next.messagesById['msg-1']).toBeDefined()
      expect(next.messagesById['msg-2']).toBeDefined()
      expect(next.messagesById['msg-3']).toBeUndefined()
      expect(next.messagesById['msg-4']).toBeUndefined()
    })

    it('does not preserve deleted messages when editing (bug regression test)', () => {
      // Start with a conversation containing turn-1
      const base = applyConversationSnapshot(undefined, buildTwoTurnSnapshot())
      expect(base.turnOrder).toEqual(['turn-1', 'turn-2'])
      expect(base.messageOrder).toEqual(['msg-1', 'msg-2', 'msg-3', 'msg-4'])

      // User edits msg-1, backend truncates turn-1 and turn-2
      const afterTruncate = applyConversationEvent(base, {
        id: 'evt-trunc-edit',
        sessionId: 'session-1',
        seq: 9,
        turnId: null,
        runId: null,
        messageId: null,
        eventType: 'messages.truncated',
        payloadJson: {
          message_id: 'msg-1',
          deleted_turn_ids: ['turn-1', 'turn-2'],
          is_edit: true,
          is_regenerate: false,
        },
        createdAt: '2026-04-24T10:00:11Z',
      })

      expect(afterTruncate.messageOrder).toEqual([])
      expect(afterTruncate.turnOrder).toEqual([])

      // Backend sends new snapshot with edited message in new turn-1
      const afterEdit = applyConversationSnapshot(afterTruncate, {
        session: {
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          preferredProviderId: 'provider-a',
          preferredModelId: 'model-a',
          agentMode: 'build',
          lastEventSeq: 12,
          activeTurnId: 'turn-1-new',
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:12Z',
        },
        turns: [
          {
            id: 'turn-1-new',
            sessionId: 'session-1',
            turnIndex: 1,
            rootMessageId: 'msg-1-edited',
            status: 'running',
            activeRunId: 'run-1-new',
            createdAt: '2026-04-24T10:00:12Z',
            updatedAt: '2026-04-24T10:00:12Z',
            completedAt: null,
          },
        ],
        runs: [
          {
            id: 'run-1-new',
            sessionId: 'session-1',
            turnId: 'turn-1-new',
            attemptIndex: 1,
            status: 'running',
            providerId: 'provider-a',
            modelId: 'model-a',
            workspaceRef: null,
            startedAt: '2026-04-24T10:00:12Z',
            finishedAt: null,
            errorCode: null,
            errorMessage: null,
          },
        ],
        messages: [
          {
            id: 'msg-1-edited',
            sessionId: 'session-1',
            turnId: 'turn-1-new',
            runId: null,
            turnMessageIndex: 1,
            role: 'user',
            messageType: 'user_message',
            streamState: 'completed',
            displayMode: 'default',
            contentText: 'hello edited',
            payloadJson: {},
            createdAt: '2026-04-24T10:00:12Z',
            updatedAt: '2026-04-24T10:00:12Z',
            completedAt: '2026-04-24T10:00:12Z',
          },
        ],
        hasMore: false,
        nextBeforeTurnId: null,
      })

      // Bug regression check: old messages (msg-1, msg-2, msg-3, msg-4) should NOT be preserved
      // Only the new edited message should be present
      expect(afterEdit.messageOrder).toEqual(['msg-1-edited'])
      expect(afterEdit.turnOrder).toEqual(['turn-1-new'])
      expect(afterEdit.messagesById['msg-1']).toBeUndefined()
      expect(afterEdit.messagesById['msg-2']).toBeUndefined()
      expect(afterEdit.messagesById['msg-3']).toBeUndefined()
      expect(afterEdit.messagesById['msg-4']).toBeUndefined()
      expect(afterEdit.messagesById['msg-1-edited']).toBeDefined()
    })
  })
})

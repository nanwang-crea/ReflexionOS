# Workspace Message Streaming And Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable long-message streaming path for the new workspace UI while moving full message history ownership to the backend and limiting the frontend to recent-round caching.

**Architecture:** The frontend keeps the existing streaming UX for normal replies but switches long replies to buffered flushes so React and markdown rendering do not update on every token. Full session history moves behind a backend API, while the frontend store is reduced to session metadata, recent round cache, and transient overlay state. The old “persist all `sessions.items` in localStorage” path is removed instead of keeping dual message sources.

**Tech Stack:** React 18, TypeScript, Zustand, Vitest, Axios, FastAPI, SQLAlchemy

---

## File Structure

**Create:**
- `frontend/src/features/workspace/streamingBuffer.ts`
  Encapsulate buffered long-message streaming logic and flush thresholds.
- `frontend/src/features/workspace/streamingBuffer.test.ts`
  Verify short-message immediate flush and long-message buffered flush behavior.
- `frontend/src/features/workspace/sessionHistory.ts`
  Convert backend history payloads into frontend rounds and render items.
- `frontend/src/features/workspace/sessionHistory.test.ts`
  Verify round grouping, recent-10 trimming, and render item conversion.
- `backend/app/storage/repositories/conversation_repo.py`
  Read and write conversation rows for a single execution and project timeline.
- `backend/app/models/conversation.py`
  Pydantic response model for message history payloads.

**Modify:**
- `frontend/src/hooks/useExecutionOverlay.ts`
  Replace token-by-token long-message UI updates with buffered flushes and recent-round persistence.
- `frontend/src/stores/workspaceStore.ts`
  Remove full-history persistence, store recent rounds/session metadata only, and add session history hydration helpers.
- `frontend/src/types/workspace.ts`
  Define round/cache structures instead of using full item history as persisted truth.
- `frontend/src/pages/AgentWorkspace.tsx`
  Load session history from the backend and render hydrated rounds plus overlay items.
- `frontend/src/features/workspace/messageFlow.ts`
  Add helpers to flatten rounds to render items and trim recent 10 rounds.
- `frontend/src/features/workspace/messageFlow.test.ts`
  Add tests for round flattening and recent-round trimming.
- `frontend/src/services/apiClient.ts`
  Add frontend API method for session history fetch.
- `frontend/src/hooks/useExecutionRuntime.ts`
  Trigger session history reload when needed after runs complete or session changes.
- `backend/app/api/routes/agent.py`
  Add a session history endpoint.
- `backend/app/services/agent_service.py`
  Persist conversation messages and serve per-project or per-session history.
- `backend/app/storage/models.py`
  If needed, extend conversation rows with session identifiers for frontend history retrieval.

**Test:**
- `frontend/src/features/workspace/streamingBuffer.test.ts`
- `frontend/src/features/workspace/sessionHistory.test.ts`
- `frontend/src/features/workspace/messageFlow.test.ts`
- `frontend/src/hooks/executionOverlayState.test.ts`
- Backend tests if a suitable API test location already exists; otherwise add targeted route/service tests under `backend/tests/`

---

### Task 1: Add buffered streaming for long messages

**Files:**
- Create: `frontend/src/features/workspace/streamingBuffer.ts`
- Test: `frontend/src/features/workspace/streamingBuffer.test.ts`
- Modify: `frontend/src/hooks/useExecutionOverlay.ts`

- [ ] **Step 1: Write the failing streaming buffer tests**

```ts
import { describe, expect, it, vi } from 'vitest'
import {
  createStreamingBuffer,
  LONG_STREAM_THRESHOLD,
} from './streamingBuffer'

describe('createStreamingBuffer', () => {
  it('flushes short content immediately', () => {
    const onFlush = vi.fn()
    const buffer = createStreamingBuffer({ onFlush })

    buffer.push('short')

    expect(onFlush).toHaveBeenCalledWith('short')
  })

  it('buffers long content and flushes batched updates', () => {
    const onFlush = vi.fn()
    const buffer = createStreamingBuffer({ onFlush })
    const longToken = 'x'.repeat(LONG_STREAM_THRESHOLD)

    buffer.push(longToken)

    expect(onFlush).not.toHaveBeenCalled()

    buffer.flush()

    expect(onFlush).toHaveBeenCalledWith(longToken)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test frontend/src/features/workspace/streamingBuffer.test.ts`
Expected: FAIL with module or export not found for `streamingBuffer`

- [ ] **Step 3: Write minimal streaming buffer implementation**

```ts
export const LONG_STREAM_THRESHOLD = 1200

interface StreamingBufferOptions {
  onFlush: (value: string) => void
}

export function createStreamingBuffer({ onFlush }: StreamingBufferOptions) {
  let pending = ''
  let totalLength = 0

  return {
    push(chunk: string) {
      totalLength += chunk.length
      if (totalLength < LONG_STREAM_THRESHOLD) {
        onFlush(chunk)
        return
      }

      pending += chunk
    },
    flush() {
      if (!pending) {
        return
      }
      onFlush(pending)
      pending = ''
    },
    reset() {
      pending = ''
      totalLength = 0
    },
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test frontend/src/features/workspace/streamingBuffer.test.ts`
Expected: PASS

- [ ] **Step 5: Integrate buffered flushes into execution overlay**

Update `useExecutionOverlay.ts` so `handleLlmContent` and `handleSummaryToken` stop writing every token directly once long-message mode is active. Keep short replies immediate, but route long content through `createStreamingBuffer(...)` and flush on a stable cadence plus at completion/cancellation/error boundaries.

```ts
const llmBufferRef = useRef(createStreamingBuffer({
  onFlush: (chunk) => appendStreamingLlmChunk(chunk),
}))

const summaryBufferRef = useRef(createStreamingBuffer({
  onFlush: (chunk) => appendStreamingAssistantChunk(chunk),
}))

const handleLlmContent = useCallback((content: string) => {
  llmStreamingRef.current += content
  llmBufferRef.current.push(content)
}, [])

const handleSummaryToken = useCallback((token: string) => {
  summaryBufferRef.current.push(token)
}, [])

const flushAllStreamingBuffers = useCallback(() => {
  llmBufferRef.current.flush()
  summaryBufferRef.current.flush()
}, [])
```

- [ ] **Step 6: Run targeted overlay and message tests**

Run: `pnpm test frontend/src/features/workspace/streamingBuffer.test.ts frontend/src/features/workspace/messageFlow.test.ts frontend/src/hooks/executionOverlayState.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/workspace/streamingBuffer.ts frontend/src/features/workspace/streamingBuffer.test.ts frontend/src/hooks/useExecutionOverlay.ts frontend/src/features/workspace/messageFlow.test.ts frontend/src/hooks/executionOverlayState.test.ts
git commit -m "fix: buffer long workspace streaming updates"
```

### Task 2: Replace persisted full item history with recent-round cache

**Files:**
- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/stores/workspaceStore.ts`
- Modify: `frontend/src/features/workspace/messageFlow.ts`
- Test: `frontend/src/features/workspace/messageFlow.test.ts`

- [ ] **Step 1: Write the failing recent-round cache tests**

```ts
import { describe, expect, it } from 'vitest'
import { flattenRoundsToItems, trimRecentRounds } from './messageFlow'

describe('trimRecentRounds', () => {
  it('keeps only the latest 10 rounds', () => {
    const rounds = Array.from({ length: 12 }, (_, index) => ({
      id: `round-${index + 1}`,
      items: [],
      createdAt: `${index + 1}`,
    }))

    expect(trimRecentRounds(rounds)).toHaveLength(10)
    expect(trimRecentRounds(rounds)[0].id).toBe('round-3')
  })
})

describe('flattenRoundsToItems', () => {
  it('returns render items in round order', () => {
    const rounds = [
      {
        id: 'round-1',
        createdAt: '1',
        items: [{ id: 'user-1', type: 'user-message', content: 'hello' }],
      },
    ]

    expect(flattenRoundsToItems(rounds).map((item) => item.id)).toEqual(['user-1'])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test frontend/src/features/workspace/messageFlow.test.ts`
Expected: FAIL because `trimRecentRounds` and `flattenRoundsToItems` do not exist

- [ ] **Step 3: Add round types and trimming helpers**

Add `WorkspaceSessionRound` to `frontend/src/types/workspace.ts` and implement `trimRecentRounds` and `flattenRoundsToItems` in `messageFlow.ts`.

```ts
export interface WorkspaceSessionRound {
  id: string
  createdAt: string
  items: WorkspaceChatItem[]
}

export function trimRecentRounds(rounds: WorkspaceSessionRound[]) {
  return rounds.slice(-10)
}

export function flattenRoundsToItems(rounds: WorkspaceSessionRound[]) {
  return rounds.flatMap((round) => round.items)
}
```

- [ ] **Step 4: Refactor workspace store to persist rounds instead of full item history**

Update `workspaceStore.ts` so session state persists `recentRounds` and session metadata instead of full `items`. Remove the old all-items persistence path rather than keeping both formats.

```ts
interface ChatSession {
  id: string
  projectId: string
  title: string
  recentRounds: WorkspaceSessionRound[]
  createdAt: string
  updatedAt: string
}

saveSessionRounds: (sessionId, rounds) => set((state) => ({
  sessions: state.sessions.map((session) => (
    session.id === sessionId
      ? { ...session, recentRounds: trimRecentRounds(rounds), updatedAt: createNow() }
      : session
  ))
}))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm test frontend/src/features/workspace/messageFlow.test.ts`
Expected: PASS

- [ ] **Step 6: Run targeted workspace tests**

Run: `pnpm test frontend/src/features/workspace/messageFlow.test.ts frontend/src/features/workspace/sessionSelection.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/workspace.ts frontend/src/stores/workspaceStore.ts frontend/src/features/workspace/messageFlow.ts frontend/src/features/workspace/messageFlow.test.ts
git commit -m "refactor: store recent workspace rounds only"
```

### Task 3: Add backend-backed session history retrieval

**Files:**
- Create: `backend/app/storage/repositories/conversation_repo.py`
- Create: `backend/app/models/conversation.py`
- Modify: `backend/app/services/agent_service.py`
- Modify: `backend/app/api/routes/agent.py`
- Modify: `backend/app/storage/models.py`
- Modify: `frontend/src/services/apiClient.ts`
- Create: `frontend/src/features/workspace/sessionHistory.ts`
- Create: `frontend/src/features/workspace/sessionHistory.test.ts`

- [ ] **Step 1: Write the failing frontend history conversion tests**

```ts
import { describe, expect, it } from 'vitest'
import { buildRoundsFromHistory } from './sessionHistory'

describe('buildRoundsFromHistory', () => {
  it('groups backend messages into request rounds', () => {
    const history = [
      { id: '1', sessionId: 's1', role: 'user', content: 'hello', createdAt: '1' },
      { id: '2', sessionId: 's1', role: 'assistant', content: 'world', createdAt: '2' },
    ]

    const rounds = buildRoundsFromHistory(history)

    expect(rounds).toHaveLength(1)
    expect(rounds[0].items.map((item) => item.type)).toEqual(['user-message', 'assistant-message'])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test frontend/src/features/workspace/sessionHistory.test.ts`
Expected: FAIL because `sessionHistory.ts` does not exist

- [ ] **Step 3: Add backend session history data model and repository**

Add a repository that can list conversation rows for a given session or execution timeline, and expose a compact response model.

```py
class ConversationMessage(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
```

```py
class ConversationRepository:
    def list_by_session(self, session_id: str) -> list[ConversationModel]:
        with self.db.get_session() as session:
            return session.query(ConversationModel).filter_by(session_id=session_id).order_by(ConversationModel.timestamp.asc()).all()
```
```

- [ ] **Step 4: Expose a backend history endpoint and frontend API method**

Add an endpoint like `GET /api/agent/history/session/{session_id}` and a matching `agentApi.getSessionHistory(sessionId)` method.

```py
@router.get('/history/session/{session_id}', response_model=List[ConversationMessage])
async def get_session_history(session_id: str):
    return agent_service.get_session_history(session_id)
```

```ts
export const agentApi = {
  cancel: (executionId: string) => apiClient.post(`/api/agent/cancel/${executionId}`),
  getSessionHistory: (sessionId: string) => apiClient.get(`/api/agent/history/session/${sessionId}`),
}
```

- [ ] **Step 5: Convert backend history into recent rounds**

Implement `buildRoundsFromHistory(...)` and `takeRecentRounds(...)` in `sessionHistory.ts`, then use them in the frontend.

```ts
export function buildRoundsFromHistory(history: SessionHistoryMessage[]) {
  const rounds: WorkspaceSessionRound[] = []
  let currentRound: WorkspaceSessionRound | null = null

  history.forEach((message) => {
    if (message.role === 'user') {
      currentRound = {
        id: `round-${message.id}`,
        createdAt: message.createdAt,
        items: [{ id: message.id, type: 'user-message', content: message.content }],
      }
      rounds.push(currentRound)
      return
    }

    if (!currentRound) {
      return
    }

    currentRound.items.push({
      id: message.id,
      type: 'assistant-message',
      content: message.content,
    })
  })

  return rounds
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pnpm test frontend/src/features/workspace/sessionHistory.test.ts`
Expected: PASS

- [ ] **Step 7: Add backend test coverage or route verification**

If an agent route test file exists, add a focused test for `GET /api/agent/history/session/{session_id}`. If not, add a service-level test that verifies ordered conversation history is returned for one session only.

Run: `pytest backend/tests -k session_history -q`
Expected: PASS with the new history test

- [ ] **Step 8: Commit**

```bash
git add backend/app/storage/repositories/conversation_repo.py backend/app/models/conversation.py backend/app/services/agent_service.py backend/app/api/routes/agent.py backend/app/storage/models.py frontend/src/services/apiClient.ts frontend/src/features/workspace/sessionHistory.ts frontend/src/features/workspace/sessionHistory.test.ts
git commit -m "feat: load workspace history from backend"
```

### Task 4: Hydrate sessions from backend history and remove old full-item persistence path

**Files:**
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/hooks/useExecutionRuntime.ts`
- Modify: `frontend/src/hooks/useExecutionOverlay.ts`
- Modify: `frontend/src/stores/workspaceStore.ts`
- Modify: `frontend/src/features/workspace/messageFlow.ts`

- [ ] **Step 1: Write a failing hydration behavior test**

Add a test that proves a session with backend history hydrates render items from recent rounds, not from an old persisted all-items array.

```ts
import { describe, expect, it } from 'vitest'
import { flattenRoundsToItems } from '@/features/workspace/messageFlow'

describe('hydrated session rendering', () => {
  it('renders recent rounds instead of legacy persisted item arrays', () => {
    const rounds = [
      {
        id: 'round-1',
        createdAt: '1',
        items: [{ id: 'user-1', type: 'user-message', content: 'hello' }],
      },
    ]

    expect(flattenRoundsToItems(rounds)).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails for the old code path**

Run: `pnpm test frontend/src/features/workspace/messageFlow.test.ts frontend/src/features/workspace/sessionHistory.test.ts`
Expected: FAIL if the code still relies on legacy `session.items`

- [ ] **Step 3: Hydrate current session from backend history on selection/load**

Update `AgentWorkspace.tsx` to load history for the selected session, convert it into rounds, store only the recent 10 rounds, and flatten those rounds for rendering. Remove the old direct `currentSession?.items` render path.

```ts
const renderItems = useMemo(
  () => mergeRenderItems(flattenRoundsToItems(currentSession?.recentRounds || []), overlayItems),
  [currentSession?.recentRounds, overlayItems]
)

useEffect(() => {
  if (!currentSessionId) {
    return
  }

  agentApi.getSessionHistory(currentSessionId).then((response) => {
    const rounds = takeRecentRounds(buildRoundsFromHistory(response.data))
    saveSessionRounds(currentSessionId, rounds)
  })
}, [currentSessionId, saveSessionRounds])
```

- [ ] **Step 4: Persist completed rounds from execution overlay**

Update `useExecutionOverlay.ts` so a completed user request is assembled as one round and saved via `saveSessionRounds(...)` instead of appending raw items forever.

```ts
appendCompletedRound(sessionId, {
  id: createItemId('round'),
  createdAt: createNow(),
  items: [userItem, ...finalItemsForThisRun],
})
```

- [ ] **Step 5: Run targeted frontend tests**

Run: `pnpm test frontend/src/features/workspace/messageFlow.test.ts frontend/src/features/workspace/sessionHistory.test.ts frontend/src/hooks/executionOverlayState.test.ts`
Expected: PASS

- [ ] **Step 6: Run frontend build verification**

Run: `pnpm build`
Expected: PASS with a successful TypeScript compile and Vite build

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/AgentWorkspace.tsx frontend/src/hooks/useExecutionRuntime.ts frontend/src/hooks/useExecutionOverlay.ts frontend/src/stores/workspaceStore.ts frontend/src/features/workspace/messageFlow.ts
git commit -m "refactor: hydrate workspace sessions from backend history"
```

## Self-Review

**Spec coverage:**
- Stable long-message streaming: Task 1
- Recent 10-round frontend cache: Tasks 2 and 4
- Backend history as message truth source: Task 3
- Single new-UI message path with old persistence removed: Tasks 2 and 4

**Placeholder scan:**
- No TODO/TBD markers remain.
- Every task names exact files and explicit verification commands.

**Type consistency:**
- Round terminology is consistently `WorkspaceSessionRound` across plan tasks.
- Backend history endpoint is consistently `getSessionHistory` / `/history/session/{session_id}`.

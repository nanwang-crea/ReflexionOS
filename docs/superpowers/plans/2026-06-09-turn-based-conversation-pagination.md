# Turn-Based Conversation Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change conversation history loading so upward pagination loads complete turns instead of arbitrary message slices, making the transcript top align with whole user requests and their associated assistant/tool history.

**Architecture:** Replace message-level `before=<message_id>` pagination with turn-level `before_turn=<turn_id>` pagination in the backend snapshot pipeline. The backend will fetch older turns, then return all messages/runs for those turns in stable chronological order; the frontend will send the oldest loaded turn id as the cursor and continue prepending normalized entities into the existing store.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy repositories, React, Zustand, Vitest, Pytest

---

## File Structure

**Backend**
- Modify: `backend/app/api/routes/sessions.py`
  Responsibility: expose the new turn-based pagination query parameter while keeping the route shape stable.
- Modify: `backend/app/models/conversation_snapshot.py`
  Responsibility: extend snapshot metadata with the next turn cursor while preserving existing entities.
- Modify: `backend/app/services/conversation_service.py`
  Responsibility: resolve turn-based pagination, fetch the correct turn window, and assemble all messages/runs for those turns.
- Modify: `backend/app/storage/repositories/turn_repo.py`
  Responsibility: add turn-level pagination queries (`latest`, `before`) ordered by `turn_index`.
- Modify: `backend/app/storage/repositories/message_repo.py`
  Responsibility: add a query that returns all messages for a set of turn ids in stable chronological order; keep existing message-level helpers until no longer needed.
- Modify: `backend/app/storage/repositories/run_repo.py`
  Responsibility: verify existing `list_by_turn_ids` behavior or extend it if ordering/coverage is insufficient for turn-based pagination.
- Modify: `backend/tests/test_services/test_conversation_service.py`
  Responsibility: TDD for full-turn pagination semantics.
- Modify: `backend/tests/test_api/test_conversation_api.py`
  Responsibility: API-level verification of new cursor metadata and complete-turn snapshots.

**Frontend**
- Modify: `frontend/src/types/conversation.ts`
  Responsibility: carry the new `nextBeforeTurnId` snapshot field through frontend types.
- Modify: `frontend/src/features/conversation/conversationApi.ts`
  Responsibility: send `before_turn` instead of `before`, and map the new cursor field.
- Modify: `frontend/src/hooks/useConversationData.ts`
  Responsibility: expose the oldest loaded turn id alongside messages/hasMore for upward pagination.
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
  Responsibility: pass the oldest loaded turn id into the runtime load-more path.
- Modify: `frontend/src/hooks/useConversationRuntime.ts`
  Responsibility: call the paginated API with a turn cursor and prepend the returned entities.
- Modify: `frontend/src/hooks/useCurrentSessionViewModel.ts`
  Responsibility: thread the updated load-more callback contract into transcript props.
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`
  Responsibility: trigger load-more using the oldest loaded turn id instead of the oldest visible filtered message id.
- Modify: `frontend/src/features/conversation/conversationStore.ts`
  Responsibility: no behavior change expected beyond consuming the updated snapshot field; keep prepend path stable and remove diagnostics after implementation.
- Modify: `frontend/src/hooks/useConversationRuntime.test.ts`
  Responsibility: verify turn-cursor load-more requests and store updates.
- Modify: `frontend/src/features/conversation/conversationApi.test.ts`
  Responsibility: verify query serialization and snapshot mapping for `before_turn` / `nextBeforeTurnId`.

---

### Task 1: Define the Turn-Based Snapshot Contract

**Files:**
- Modify: `backend/app/models/conversation_snapshot.py`
- Modify: `frontend/src/types/conversation.ts`
- Test: `backend/tests/test_api/test_conversation_api.py`
- Test: `frontend/src/features/conversation/conversationApi.test.ts`

- [ ] **Step 1: Write the failing backend API test for the new cursor metadata**

```python
def test_get_conversation_snapshot_returns_turn_cursor_metadata(client):
    response = client.get("/api/sessions/session-1/conversation")

    assert response.status_code == 200
    payload = response.json()
    assert "next_before_turn_id" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_api/test_conversation_api.py::test_get_conversation_snapshot_returns_turn_cursor_metadata -v`
Expected: FAIL because `next_before_turn_id` is missing from the response payload.

- [ ] **Step 3: Write the failing frontend API mapping test**

```ts
it('maps next_before_turn_id to nextBeforeTurnId', async () => {
  getMock.mockResolvedValue({
    data: {
      session: { /* existing dto fields */ },
      turns: [],
      runs: [],
      messages: [],
      has_more: true,
      next_before_turn_id: 'turn-3',
    },
  })

  const { conversationApi } = await import('./conversationApi')
  const response = await conversationApi.getConversation('session-1')

  expect(response.data.nextBeforeTurnId).toBe('turn-3')
})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `npm test -- --run src/features/conversation/conversationApi.test.ts`
Expected: FAIL because `nextBeforeTurnId` is not part of the mapped snapshot type.

- [ ] **Step 5: Write the minimal contract changes**

```python
class ConversationSnapshot(BaseModel):
    session: Session
    turns: list[Turn]
    runs: list[Run]
    messages: list[Message]
    has_more: bool = False
    next_before_turn_id: str | None = None
```

```ts
export interface ConversationSnapshot {
  session: ConversationSession
  turns: ConversationTurn[]
  runs: ConversationRun[]
  messages: ConversationMessage[]
  hasMore: boolean
  nextBeforeTurnId: string | null
}
```

- [ ] **Step 6: Update DTO mapping minimally**

```ts
interface ConversationSnapshotDto {
  session: ConversationSessionDto
  turns: ConversationTurnDto[]
  runs: ConversationRunDto[]
  messages: ConversationMessageDto[]
  has_more: boolean
  next_before_turn_id: string | null
}

function toConversationSnapshot(dto: ConversationSnapshotDto): ConversationSnapshot {
  return {
    session: toConversationSession(dto.session),
    turns: dto.turns.map(toConversationTurn),
    runs: dto.runs.map(toConversationRun),
    messages: dto.messages.map(toConversationMessage),
    hasMore: dto.has_more,
    nextBeforeTurnId: dto.next_before_turn_id ?? null,
  }
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_api/test_conversation_api.py::test_get_conversation_snapshot_returns_turn_cursor_metadata -v && npm test -- --run src/features/conversation/conversationApi.test.ts`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/conversation_snapshot.py backend/tests/test_api/test_conversation_api.py frontend/src/types/conversation.ts frontend/src/features/conversation/conversationApi.ts frontend/src/features/conversation/conversationApi.test.ts
git commit -m "feat: add turn pagination snapshot cursor"
```

### Task 2: Add Turn-Level Repository Pagination

**Files:**
- Modify: `backend/app/storage/repositories/turn_repo.py`
- Modify: `backend/app/storage/repositories/message_repo.py`
- Test: `backend/tests/test_services/test_conversation_service.py`

- [ ] **Step 1: Write the failing repository/service pagination test for complete turns**

```python
def test_get_snapshot_paginated_returns_complete_turns(tmp_path):
    db = Database(str(tmp_path / "conversation-service-turn-pagination.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    for turn_index in range(1, 5):
        turn_id = f"turn-{turn_index}"
        service.turn_repo.create(Turn(
            id=turn_id,
            session_id="session-1",
            turn_index=turn_index,
            root_message_id=f"msg-user-{turn_index}",
            status=TurnStatus.COMPLETED,
        ))
        service.message_repo.create(Message(
            id=f"msg-user-{turn_index}",
            session_id="session-1",
            turn_id=turn_id,
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text=f"user {turn_index}",
        ))
        service.message_repo.create(Message(
            id=f"msg-assistant-{turn_index}",
            session_id="session-1",
            turn_id=turn_id,
            run_id=None,
            turn_message_index=2,
            role="assistant",
            message_type=MessageType.ASSISTANT_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text=f"assistant {turn_index}",
        ))

    latest = service.get_snapshot("session-1", limit=2)

    assert [turn.id for turn in latest.turns] == ["turn-3", "turn-4"]
    assert [message.id for message in latest.messages] == [
        "msg-user-3",
        "msg-assistant-3",
        "msg-user-4",
        "msg-assistant-4",
    ]
    assert latest.next_before_turn_id == "turn-3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_services/test_conversation_service.py::test_get_snapshot_paginated_returns_complete_turns -v`
Expected: FAIL because `limit` currently applies to messages rather than turns.

- [ ] **Step 3: Add minimal turn pagination helpers**

```python
def list_by_session_latest(self, session_id: str, limit: int) -> list[Turn]:
    with self.db.get_session() as db_session:
        models = (
            db_session.query(TurnModel)
            .filter(TurnModel.session_id == session_id)
            .order_by(TurnModel.turn_index.desc())
            .limit(limit)
            .all()
        )
        return self._to_domain_list(list(reversed(models)))

def list_by_session_before(self, session_id: str, before_turn_id: str, limit: int) -> list[Turn]:
    with self.db.get_session() as db_session:
        cursor = db_session.query(TurnModel).filter_by(id=before_turn_id, session_id=session_id).first()
        if cursor is None:
            return []
        models = (
            db_session.query(TurnModel)
            .filter(TurnModel.session_id == session_id, TurnModel.turn_index < cursor.turn_index)
            .order_by(TurnModel.turn_index.desc())
            .limit(limit)
            .all()
        )
        return self._to_domain_list(list(reversed(models)))
```

- [ ] **Step 4: Add a minimal message fetch-by-turn-ids helper**

```python
def list_by_turn_ids(self, turn_ids: list[str]) -> list[Message]:
    if not turn_ids:
        return []
    with self.db.get_session() as db_session:
        models = (
            db_session.query(MessageModel)
            .outerjoin(
                TurnModel,
                (TurnModel.id == MessageModel.turn_id)
                & (TurnModel.session_id == MessageModel.session_id),
            )
            .filter(MessageModel.turn_id.in_(turn_ids))
            .order_by(
                TurnModel.turn_index.asc(),
                MessageModel.turn_message_index.asc(),
                MessageModel.created_at.asc(),
            )
            .all()
        )
        return self._to_domain_list(models)
```

- [ ] **Step 5: Run the test again to keep it red for service logic**

Run: `pytest backend/tests/test_services/test_conversation_service.py::test_get_snapshot_paginated_returns_complete_turns -v`
Expected: FAIL because the service still pages by messages.

- [ ] **Step 6: Commit**

```bash
git add backend/app/storage/repositories/turn_repo.py backend/app/storage/repositories/message_repo.py backend/tests/test_services/test_conversation_service.py
git commit -m "feat: add turn pagination repositories"
```

### Task 3: Switch ConversationService to Turn-Based Pagination

**Files:**
- Modify: `backend/app/services/conversation_service.py`
- Modify: `backend/app/api/routes/sessions.py`
- Modify: `backend/tests/test_services/test_conversation_service.py`
- Modify: `backend/tests/test_api/test_conversation_api.py`

- [ ] **Step 1: Extend failing service tests for older-page behavior and invalid cursors**

```python
def test_get_snapshot_paginated_before_turn_returns_complete_older_turns(tmp_path):
    # seed 5 turns with 2 messages each
    middle = service.get_snapshot("session-1", limit=2, before_turn="turn-4")

    assert [turn.id for turn in middle.turns] == ["turn-2", "turn-3"]
    assert [message.id for message in middle.messages] == [
        "msg-user-2",
        "msg-assistant-2",
        "msg-user-3",
        "msg-assistant-3",
    ]
    assert middle.has_more is True
    assert middle.next_before_turn_id == "turn-2"


def test_get_snapshot_paginated_before_missing_turn_returns_empty_page(tmp_path):
    empty = service.get_snapshot("session-1", limit=2, before_turn="turn-missing")

    assert empty.turns == []
    assert empty.runs == []
    assert empty.messages == []
    assert empty.has_more is False
    assert empty.next_before_turn_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_services/test_conversation_service.py -k "complete_turns or before_turn" -v`
Expected: FAIL because `get_snapshot` does not accept `before_turn` and still slices by messages.

- [ ] **Step 3: Change the API/service signatures minimally**

```python
@router.get("/sessions/{session_id}/conversation", response_model=ConversationSnapshot)
async def get_session_conversation(
    session_id: str,
    limit: int = 20,
    before_turn: str | None = None,
):
    try:
        return conversation_service.get_snapshot(session_id, limit=limit, before_turn=before_turn)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc
```

```python
def get_snapshot(self, session_id: str, *, limit: int = 0, before_turn: str | None = None) -> ConversationSnapshot:
    session = self.session_repo.get(session_id)
    if session is None:
        raise NotFoundValueError("会话不存在")

    if limit <= 0:
        turns = self.turn_repo.list_by_session(session_id)
        turn_ids = [turn.id for turn in turns]
        return ConversationSnapshot(
            session=session,
            turns=turns,
            runs=self.run_repo.list_by_turn_ids(turn_ids),
            messages=self.message_repo.list_by_turn_ids(turn_ids),
            has_more=False,
            next_before_turn_id=turns[0].id if turns else None,
        )

    probe_limit = limit + 1
    page_turns = (
        self.turn_repo.list_by_session_before(session_id, before_turn, probe_limit)
        if before_turn is not None
        else self.turn_repo.list_by_session_latest(session_id, probe_limit)
    )
    has_more = len(page_turns) > limit
    if has_more:
        page_turns = page_turns[-limit:]

    turn_ids = [turn.id for turn in page_turns]
    return ConversationSnapshot(
        session=session,
        turns=page_turns,
        runs=self.run_repo.list_by_turn_ids(turn_ids),
        messages=self.message_repo.list_by_turn_ids(turn_ids),
        has_more=has_more,
        next_before_turn_id=page_turns[0].id if page_turns else None,
    )
```

- [ ] **Step 4: Add an API-level test for the new query parameter**

```python
def test_get_conversation_snapshot_accepts_before_turn_query(client):
    response = client.get("/api/sessions/session-1/conversation", params={"limit": 20, "before_turn": "turn-3"})

    assert response.status_code == 200
```

- [ ] **Step 5: Run backend tests to verify they pass**

Run: `pytest backend/tests/test_services/test_conversation_service.py backend/tests/test_api/test_conversation_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/sessions.py backend/app/services/conversation_service.py backend/tests/test_services/test_conversation_service.py backend/tests/test_api/test_conversation_api.py
git commit -m "feat: paginate conversation history by turn"
```

### Task 4: Update Frontend Load-More to Use Turn Cursors

**Files:**
- Modify: `frontend/src/features/conversation/conversationApi.ts`
- Modify: `frontend/src/hooks/useConversationData.ts`
- Modify: `frontend/src/hooks/useConversationRuntime.ts`
- Modify: `frontend/src/hooks/useCurrentSessionViewModel.ts`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`
- Modify: `frontend/src/hooks/useConversationRuntime.test.ts`
- Modify: `frontend/src/features/conversation/conversationApi.test.ts`

- [ ] **Step 1: Write the failing frontend API query test**

```ts
it('serializes before_turn when requesting older conversation pages', async () => {
  getMock.mockResolvedValue({ data: minimalSnapshotDto })

  const { conversationApi } = await import('./conversationApi')
  await conversationApi.getConversationPaginated('session-1', { limit: 20, beforeTurn: 'turn-3' })

  expect(getMock).toHaveBeenCalledWith('/api/sessions/session-1/conversation', {
    params: { limit: '20', before_turn: 'turn-3' },
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/features/conversation/conversationApi.test.ts`
Expected: FAIL because `beforeTurn` is not supported.

- [ ] **Step 3: Write the failing runtime test for turn-based load-more**

```ts
it('loads older history using the oldest loaded turn id', async () => {
  const snapshot = buildSnapshot()
  const olderPage = {
    ...snapshot,
    turns: [
      { ...snapshot.turns[0], id: 'turn-0', turnIndex: 0, rootMessageId: 'msg-0' },
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
    ],
    hasMore: false,
    nextBeforeTurnId: 'turn-0',
  }
  getConversationMock.mockResolvedValueOnce({ data: snapshot }).mockResolvedValueOnce({ data: olderPage })
  conversationStoreState.prependMessages = vi.fn()
  conversationStoreState.setHasMore = vi.fn()

  const { useConversationRuntime } = await import('./useConversationRuntime')
  const runtime = useConversationRuntime('session-1')
  await flushAsyncEffects()

  await runtime.loadMore('session-1', 'turn-1')

  expect(getConversationMock).toHaveBeenLastCalledWith('session-1', { limit: 20, beforeTurn: 'turn-1' })
})
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `npm test -- --run src/hooks/useConversationRuntime.test.ts src/features/conversation/conversationApi.test.ts`
Expected: FAIL because the runtime still calls `before` with a message id.

- [ ] **Step 5: Apply the minimal frontend contract changes**

```ts
getConversationPaginated: (sessionId: string, params: { limit?: number; beforeTurn?: string }) => {
  const queryParams: Record<string, string> = {}
  if (params.limit !== undefined) queryParams.limit = String(params.limit)
  if (params.beforeTurn !== undefined) queryParams.before_turn = params.beforeTurn
  return mapConversationResponse(apiClient.get<ConversationSnapshotDto>(buildSessionConversationPath(sessionId), { params: queryParams }))
}
```

```ts
export function useConversationData(currentSessionId: string | null) {
  // existing message lookup
  const oldestLoadedTurnId = useMemo(() => {
    if (!conversation || conversation.turnOrder.length === 0) return null
    return conversation.turnOrder[0]
  }, [conversation])

  return { messages, isRunning, plan, hasMore, oldestLoadedTurnId }
}
```

```ts
const loadMore = useCallback(async (sessionId: string, beforeTurnId: string) => {
  const response = await conversationApi.getConversationPaginated(sessionId, { limit: 20, beforeTurn: beforeTurnId })
  const snapshot = response.data
  useConversationStore.getState().prependMessages(sessionId, snapshot.messages, snapshot.turns, snapshot.runs)
  useConversationStore.getState().setHasMore(sessionId, snapshot.hasMore)
}, [])
```

```tsx
const handleStartReached = useCallback(() => {
  if (hasMore && oldestLoadedTurnId && !isLoadingMore) {
    onLoadMore?.(oldestLoadedTurnId)
  }
}, [hasMore, oldestLoadedTurnId, isLoadingMore, onLoadMore])
```

- [ ] **Step 6: Remove temporary pagination diagnostics while touching these files**

```ts
// Remove the temporary console.info pagination tracing added during debugging
```

- [ ] **Step 7: Run frontend tests to verify they pass**

Run: `npm test -- --run src/hooks/useConversationRuntime.test.ts src/features/conversation/conversationApi.test.ts src/features/conversation/conversationStore.test.ts`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/conversation/conversationApi.ts frontend/src/features/conversation/conversationApi.test.ts frontend/src/hooks/useConversationData.ts frontend/src/hooks/useConversationRuntime.ts frontend/src/hooks/useConversationRuntime.test.ts frontend/src/hooks/useCurrentSessionViewModel.ts frontend/src/pages/AgentWorkspace.tsx frontend/src/components/workspace/WorkspaceTranscript.tsx
git commit -m "feat: load conversation history by turn"
```

### Task 5: Verify End-to-End Turn-Aligned History Loading

**Files:**
- Modify: `frontend/src/components/workspace/ToolTraceCard.test.tsx`
- Modify: `frontend/src/components/workspace/transcriptItems.test.ts`
- Test: `backend/tests/test_services/test_conversation_service.py`
- Test: `frontend/src/components/workspace/ToolTraceCard.test.tsx`

- [ ] **Step 1: Write the failing transcript expectation test for turn-aligned loading**

```ts
it('requests older history using the oldest loaded turn instead of the oldest visible message', () => {
  const loadMore = vi.fn()

  renderToStaticMarkup(
    <WorkspaceTranscript
      loaded
      configured
      currentProject={project}
      currentSession={session}
      messages={[
        buildMessage({ id: 'msg-hidden-cont', turnId: 'turn-1', messageType: 'system_notice', payloadJson: { kind: 'continuation_artifact' } }),
        buildMessage({ id: 'msg-user-visible', turnId: 'turn-2', role: 'user', messageType: 'user_message', contentText: 'visible oldest' }),
      ]}
      hasMore
      onLoadMore={loadMore}
      oldestLoadedTurnId="turn-1"
    />
  )

  expect(loadMore).toHaveBeenCalledWith('turn-1')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/components/workspace/ToolTraceCard.test.tsx`
Expected: FAIL because the transcript still calls load-more with a message id.

- [ ] **Step 3: Update transcript props and any supporting tests minimally**

```tsx
type WorkspaceTranscriptProps = {
  // existing props
  oldestLoadedTurnId?: string | null
  onLoadMore?: (beforeTurnId: string) => void
}
```

```tsx
const handleStartReached = useCallback(() => {
  if (hasMore && oldestLoadedTurnId && !isLoadingMore) {
    onLoadMore?.(oldestLoadedTurnId)
  }
}, [hasMore, oldestLoadedTurnId, isLoadingMore, onLoadMore])
```

- [ ] **Step 4: Run targeted verification for transcript + backend pagination**

Run: `pytest backend/tests/test_services/test_conversation_service.py -k "paginated" -v && npm test -- --run src/components/workspace/ToolTraceCard.test.tsx src/hooks/useConversationRuntime.test.ts`
Expected: PASS

- [ ] **Step 5: Perform one manual verification run**

Run the app, open a long conversation, scroll upward several pages, and verify:
- the top of each newly loaded page aligns with a complete turn
- user messages appear with their associated process/answer history
- `hasMore` eventually becomes false when the oldest turn is reached

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/workspace/ToolTraceCard.test.tsx frontend/src/components/workspace/WorkspaceTranscript.tsx frontend/src/components/workspace/transcriptItems.test.ts backend/tests/test_services/test_conversation_service.py
git commit -m "test: verify turn-aligned transcript history loading"
```

## Self-Review

- Spec coverage: backend pagination contract, repository queries, service assembly, API wiring, frontend cursor changes, transcript trigger changes, and regression tests are all covered.
- Placeholder scan: removed broad placeholders; every task includes explicit files, tests, commands, and concrete code snippets.
- Type consistency: the plan uses `before_turn` on the wire, `beforeTurn` in frontend params, and `nextBeforeTurnId` in frontend state consistently.

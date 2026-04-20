# Full Session History Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade session history from simplified chat replay to full transcript replay, including agent updates and action receipts, while removing the remaining weak role-only archive path in the new UI flow.

**Architecture:** The backend stops treating session history as only `role/content` chat messages and instead stores ordered transcript items with explicit `item_type`, receipt state, and serialized receipt details. The frontend replaces the current role-only history mapper with transcript hydration that groups ordered archive items into rounds, so restored sessions can replay `user-message`, `agent-update`, `action-receipt`, and `assistant-message` together. Cleanup is limited to the obsolete weak archive path and any remaining new-UI assumptions that history is only user/assistant text.

**Tech Stack:** React 18, TypeScript, Zustand, Vitest, FastAPI, SQLAlchemy, Pytest

---

## File Structure

**Create:**
- `frontend/src/features/workspace/transcriptArchive.ts`
  Convert backend transcript archive items into `WorkspaceSessionRound[]`.
- `frontend/src/features/workspace/transcriptArchive.test.ts`
  Verify receipt replay, agent update replay, and round grouping.

**Modify:**
- `backend/app/models/conversation.py`
  Expand conversation archive model from `role/content` to transcript item schema.
- `backend/app/storage/models.py`
  Add transcript-specific database columns such as `item_type`, `receipt_status`, `details_json`, and `sequence`.
- `backend/app/storage/database.py`
  Reset legacy schema when transcript archive columns are missing.
- `backend/app/storage/repositories/conversation_repo.py`
  Persist and return ordered transcript items rather than weak chat rows.
- `backend/app/execution/rapid_loop.py`
  Emit full transcript archive items into execution metadata.
- `backend/app/services/agent_service.py`
  Persist full transcript history and return typed transcript items per session.
- `backend/app/api/routes/agent.py`
  Keep the same route shape but return the richer transcript history payload.
- `backend/tests/test_storage/test_repositories.py`
  Add storage coverage for ordered transcript item replay including receipts.
- `backend/tests/test_execution/test_rapid_loop.py`
  Verify execution metadata now includes transcript items.
- `frontend/src/services/apiClient.ts`
  Type the session history API as transcript archive items.
- `frontend/src/pages/AgentWorkspace.tsx`
  Hydrate rounds from transcript archive items instead of role-only history.
- `frontend/src/features/workspace/sessionHistory.ts`
  Replace or remove the weak role-only mapper in favor of transcript hydration.
- `frontend/src/features/workspace/sessionHistory.test.ts`
  Replace tests that assume history only contains user/assistant messages.

---

### Task 1: Upgrade backend archive model to ordered transcript items

**Files:**
- Modify: `backend/app/models/conversation.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/storage/database.py`
- Modify: `backend/app/storage/repositories/conversation_repo.py`
- Test: `backend/tests/test_storage/test_repositories.py`

- [ ] **Step 1: Write the failing storage test for receipt replay fields**

```py
def test_save_and_list_transcript_items_with_receipts(repo):
    repo.save_messages([
        ConversationMessage(
            id="receipt-1",
            execution_id="exec-1",
            session_id="session-a",
            project_id="proj-1",
            item_type="action-receipt",
            content="",
            receipt_status="completed",
            details_json=[{"title": "Read file", "status": "success"}],
            sequence=2,
        )
    ])

    result = repo.list_by_session("session-a")

    assert result[0].item_type == "action-receipt"
    assert result[0].receipt_status == "completed"
    assert result[0].details_json == [{"title": "Read file", "status": "success"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_storage/test_repositories.py -q`
Expected: FAIL because `ConversationMessage` and repository do not yet support transcript fields

- [ ] **Step 3: Add transcript archive fields to the backend model and database**

```py
class ConversationMessage(BaseModel):
    id: str
    execution_id: str
    session_id: str
    project_id: str
    item_type: str
    content: str = ""
    receipt_status: str | None = None
    details_json: list[dict] = Field(default_factory=list)
    sequence: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
```

```py
class ConversationModel(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    execution_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    project_id = Column(String, nullable=False, index=True)
    item_type = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    receipt_status = Column(String, nullable=True)
    details_json = Column(JSON, nullable=False, default=list)
    sequence = Column(Integer, nullable=False, default=0)
    timestamp = Column(DateTime, default=datetime.now)
```

- [ ] **Step 4: Persist and read ordered transcript items**

```py
def list_by_session(self, session_id: str) -> list[ConversationMessage]:
    with self.db.get_session() as session:
        models = session.query(ConversationModel).filter_by(
            session_id=session_id
        ).order_by(
            ConversationModel.sequence.asc(),
            ConversationModel.timestamp.asc(),
        ).all()

        return [
            ConversationMessage(
                id=model.id,
                execution_id=model.execution_id,
                session_id=model.session_id,
                project_id=model.project_id,
                item_type=model.item_type,
                content=model.content,
                receipt_status=model.receipt_status,
                details_json=model.details_json or [],
                sequence=model.sequence,
                created_at=model.timestamp,
            )
            for model in models
        ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_storage/test_repositories.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/conversation.py backend/app/storage/models.py backend/app/storage/database.py backend/app/storage/repositories/conversation_repo.py backend/tests/test_storage/test_repositories.py
git commit -m "feat: store transcript archive items for session history"
```

### Task 2: Persist full transcript items from execution runtime

**Files:**
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/app/services/agent_service.py`
- Test: `backend/tests/test_execution/test_rapid_loop.py`

- [ ] **Step 1: Write the failing execution metadata test**

```py
@pytest.mark.asyncio
async def test_execution_metadata_contains_receipt_and_agent_update_items(execution_loop, mock_llm):
    async def mock_stream(messages, tools=None):
        async for chunk in self._stream_response(content="先检查文件", tool_calls=[LLMToolCall(name="mock", arguments={})], finish_reason="tool_calls"):
            yield chunk

    mock_llm.stream_complete = mock_stream

    result = await execution_loop.run("检查项目")

    transcript = result.metadata["conversation_messages"]
    assert any(item["item_type"] == "agent-update" for item in transcript)
    assert any(item["item_type"] == "action-receipt" for item in transcript)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_execution/test_rapid_loop.py -q`
Expected: FAIL because metadata currently only contains role/content items

- [ ] **Step 3: Emit full transcript archive items from the runtime**

In `rapid_loop.py`, build `conversation_messages` with explicit transcript item types and ordered sequence values, including:

- `user-message`
- `agent-update`
- `action-receipt`
- `assistant-message`

For receipts, serialize full receipt details into `details_json`.

```py
execution.metadata = {
    "conversation_messages": [
        {
            "id": f"conv-{execution.id}-{index}",
            "execution_id": execution.id,
            "session_id": session_id,
            "project_id": project_id,
            "item_type": item_type,
            "content": content,
            "receipt_status": receipt_status,
            "details_json": details_json,
            "sequence": index,
            "created_at": created_at,
        }
        for index, (...) in enumerate(transcript_items)
    ]
}
```

- [ ] **Step 4: Keep `AgentService` transcript persistence aligned with the richer schema**

```py
def _persist_conversation_history(self, execution: Execution) -> None:
    messages = execution.metadata.get("conversation_messages", [])
    if not messages:
        return

    self.conversation_repo.save_messages([
        ConversationMessage(**message)
        for message in messages
    ])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_execution/test_rapid_loop.py backend/tests/test_services/test_agent_service.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/execution/rapid_loop.py backend/app/services/agent_service.py backend/tests/test_execution/test_rapid_loop.py
git commit -m "feat: persist full transcript replay items"
```

### Task 3: Replace frontend role-only history hydration with transcript replay

**Files:**
- Create: `frontend/src/features/workspace/transcriptArchive.ts`
- Test: `frontend/src/features/workspace/transcriptArchive.test.ts`
- Modify: `frontend/src/features/workspace/sessionHistory.ts`
- Modify: `frontend/src/features/workspace/sessionHistory.test.ts`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/services/apiClient.ts`

- [ ] **Step 1: Write the failing transcript hydration tests**

```ts
import { describe, expect, it } from 'vitest'
import { buildRoundsFromTranscriptArchive } from './transcriptArchive'

describe('buildRoundsFromTranscriptArchive', () => {
  it('replays agent updates and receipts inside the same round', () => {
    const archive = [
      { id: '1', itemType: 'user-message', content: 'hello', sequence: 0, createdAt: '1' },
      { id: '2', itemType: 'agent-update', content: 'checking files', sequence: 1, createdAt: '2' },
      {
        id: '3',
        itemType: 'action-receipt',
        content: '',
        receiptStatus: 'completed',
        detailsJson: [{ title: 'Read file', status: 'success' }],
        sequence: 2,
        createdAt: '3',
      },
      { id: '4', itemType: 'assistant-message', content: 'done', sequence: 3, createdAt: '4' },
    ]

    const rounds = buildRoundsFromTranscriptArchive(archive)

    expect(rounds).toHaveLength(1)
    expect(rounds[0].items.map((item) => item.type)).toEqual([
      'user-message',
      'agent-update',
      'action-receipt',
      'assistant-message',
    ])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test frontend/src/features/workspace/transcriptArchive.test.ts`
Expected: FAIL because transcript archive hydration does not exist

- [ ] **Step 3: Implement transcript archive hydration**

```ts
export function buildRoundsFromTranscriptArchive(archive: TranscriptArchiveItem[]) {
  const rounds: WorkspaceSessionRound[] = []
  let currentRound: WorkspaceSessionRound | null = null

  archive.forEach((item) => {
    if (item.itemType === 'user-message') {
      currentRound = {
        id: `round-${item.id}`,
        createdAt: item.createdAt,
        items: [toWorkspaceItem(item)],
      }
      rounds.push(currentRound)
      return
    }

    if (!currentRound) {
      return
    }

    currentRound.items.push(toWorkspaceItem(item))
  })

  return trimRecentRounds(rounds)
}
```

- [ ] **Step 4: Switch `AgentWorkspace` to the transcript hydrator and delete the weak role-only mapper**

Use the new archive hydrator in `AgentWorkspace.tsx`. If `sessionHistory.ts` becomes redundant after the switch, remove it rather than keeping two history mappers.

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm test frontend/src/features/workspace/transcriptArchive.test.ts frontend/src/features/workspace/sessionHistory.test.ts frontend/src/services/websocketClient.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/workspace/transcriptArchive.ts frontend/src/features/workspace/transcriptArchive.test.ts frontend/src/features/workspace/sessionHistory.ts frontend/src/features/workspace/sessionHistory.test.ts frontend/src/pages/AgentWorkspace.tsx frontend/src/services/apiClient.ts
git commit -m "refactor: hydrate workspace history from transcript archive"
```

### Task 4: Remove obsolete weak archive assumptions and verify replay end-to-end

**Files:**
- Modify: any remaining files still assuming history is only user/assistant text
- Test: frontend and backend verification commands

- [ ] **Step 1: Search for obsolete role-only history assumptions**

Run: `rg "role: 'assistant'|message.role === 'user'|buildRoundsFromHistory|ConversationMessage\(" frontend backend`
Expected: Identify only valid remaining uses unrelated to session replay, or no obsolete matches

- [ ] **Step 2: Remove confirmed obsolete weak replay code**

Examples:
- delete the role-only `sessionHistory.ts` if superseded
- remove now-unused weak history interfaces
- remove route/client assumptions that session history is only `role/content`

- [ ] **Step 3: Run frontend verification**

Run: `pnpm test && pnpm build`
Expected: PASS

- [ ] **Step 4: Run backend verification**

Run: `pytest backend/tests/test_storage/test_repositories.py backend/tests/test_execution/test_rapid_loop.py backend/tests/test_services/test_agent_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app frontend/src/backend src docs
git commit -m "refactor: remove weak session replay assumptions"
```

## Self-Review

**Spec coverage:**
- Full receipt replay in history: Tasks 1, 2, 3
- Agent update replay: Tasks 2 and 3
- Backend archive as real transcript source: Tasks 1 and 2
- Cleanup of obsolete role-only/new-UI replay assumptions: Task 4

**Placeholder scan:**
- No TODO/TBD placeholders remain.
- All tasks include exact files and explicit verification commands.

**Type consistency:**
- Backend archive item naming is consistently `item_type`, `receipt_status`, `details_json`, `sequence`.
- Frontend archive item naming is consistently `itemType`, `receiptStatus`, `detailsJson`, `sequence` after API mapping.

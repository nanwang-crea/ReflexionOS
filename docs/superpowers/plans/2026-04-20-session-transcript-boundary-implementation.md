# Session Transcript Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the frontend-owned session/history model with backend-owned sessions and round-based history, while enforcing completed commit, cancelled discard, failed retain, and removing obsolete local session code.

**Architecture:** The backend becomes the source of truth for sessions and persisted transcript rounds. The frontend is reduced to a UI-state store plus a session feature layer that loads backend sessions/history and maintains only transient execution draft state in memory. Existing local session persistence and archive-to-round reconstruction code are deleted once the new path is live.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, Zustand, Vitest, Axios, WebSocket

---

## File Map

### Backend files to create

- `backend/app/models/session.py`
- `backend/app/services/session_service.py`
- `backend/app/services/transcript_service.py`
- `backend/app/storage/repositories/session_repo.py`
- `backend/app/api/routes/sessions.py`
- `backend/tests/test_services/test_session_service.py`
- `backend/tests/test_api/test_sessions_api.py`

### Backend files to modify

- `backend/app/storage/models.py`
- `backend/app/models/__init__.py`
- `backend/app/models/conversation.py`
- `backend/app/models/execution.py`
- `backend/app/services/agent_service.py`
- `backend/app/execution/rapid_loop.py`
- `backend/app/storage/repositories/conversation_repo.py`
- `backend/app/storage/repositories/__init__.py`
- `backend/app/main.py`
- `backend/tests/test_services/test_agent_service.py`
- `backend/tests/test_execution/test_rapid_loop.py`
- `backend/tests/test_storage/test_repositories.py`

### Frontend files to create

- `frontend/src/features/sessions/sessionApi.ts`
- `frontend/src/features/sessions/sessionStore.ts`
- `frontend/src/features/sessions/sessionLoader.ts`
- `frontend/src/features/sessions/sessionActions.ts`
- `frontend/src/hooks/useCurrentSessionViewModel.ts`
- `frontend/src/hooks/useSessionActions.ts`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/hooks/useExecutionDraftRound.ts`
- `frontend/src/hooks/useExecutionOverlayUi.ts`
- `frontend/src/features/llm/providerDraft.ts`
- `frontend/src/features/llm/providerActions.ts`
- `frontend/src/features/sessions/sessionStore.test.ts`
- `frontend/src/features/sessions/sessionLoader.test.ts`
- `frontend/src/hooks/useExecutionDraftRound.test.ts`

### Frontend files to modify

- `frontend/src/services/apiClient.ts`
- `frontend/src/stores/workspaceStore.ts`
- `frontend/src/types/workspace.ts`
- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/hooks/useExecutionOverlay.ts`
- `frontend/src/hooks/useExecutionRuntime.ts`
- `frontend/src/hooks/useExecutionWebSocket.ts`
- `frontend/src/components/layout/WorkspaceSidebar.tsx`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/features/workspace/transcriptArchive.ts`
- `frontend/src/features/workspace/transcriptArchive.test.ts`
- `frontend/src/demo/demoData.ts`
- `frontend/src/App.cleanup.test.ts`

---

### Task 1: Add Backend Session Model And Repository

**Files:**
- Create: `backend/app/models/session.py`
- Create: `backend/app/storage/repositories/session_repo.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/storage/repositories/__init__.py`
- Test: `backend/tests/test_storage/test_repositories.py`
- Test: `backend/tests/test_services/test_session_service.py`

- [ ] **Step 1: Write failing repository tests for session CRUD**

```python
def test_session_repository_crud(temp_db):
    repo = SessionRepository(temp_db)
    created = repo.create(Session(
        id="session-1",
        project_id="project-1",
        title="新建聊天",
        preferred_provider_id="provider-a",
        preferred_model_id="model-a",
    ))

    fetched = repo.get("session-1")
    project_sessions = repo.list_by_project("project-1")

    assert created.id == "session-1"
    assert fetched is not None
    assert fetched.project_id == "project-1"
    assert [session.id for session in project_sessions] == ["session-1"]
```

- [ ] **Step 2: Run backend repository test and verify failure**

Run: `pytest backend/tests/test_storage/test_repositories.py -v`
Expected: FAIL with import or attribute errors for missing session model/repository.

- [ ] **Step 3: Add SQLAlchemy session table and domain model**

```python
class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, default="新建聊天")
    preferred_provider_id = Column(String)
    preferred_model_id = Column(String)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
```

```python
class Session(BaseModel):
    id: str
    project_id: str
    title: str = "新建聊天"
    preferred_provider_id: Optional[str] = None
    preferred_model_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

- [ ] **Step 4: Implement session repository minimally**

```python
class SessionRepository:
    def create(self, session: Session) -> Session:
        model = SessionModel(**session.model_dump())
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return Session.model_validate(model)

    def get(self, session_id: str) -> Optional[Session]:
        model = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        return Session.model_validate(model) if model else None

    def list_by_project(self, project_id: str) -> list[Session]:
        models = (
            self.db.query(SessionModel)
            .filter(SessionModel.project_id == project_id)
            .order_by(SessionModel.updated_at.desc())
            .all()
        )
        return [Session.model_validate(model) for model in models]
```

- [ ] **Step 5: Run repository tests and verify pass**

Run: `pytest backend/tests/test_storage/test_repositories.py -v`
Expected: PASS for new session repository coverage.

- [ ] **Step 6: Commit backend session model and repository**

```bash
git add backend/app/models/session.py backend/app/storage/repositories/session_repo.py backend/app/storage/models.py backend/app/models/__init__.py backend/app/storage/repositories/__init__.py backend/tests/test_storage/test_repositories.py backend/tests/test_services/test_session_service.py
git commit -m "feat: add persisted session model"
```

---

### Task 2: Add Session Service And Session API

**Files:**
- Create: `backend/app/services/session_service.py`
- Create: `backend/app/api/routes/sessions.py`
- Test: `backend/tests/test_services/test_session_service.py`
- Test: `backend/tests/test_api/test_sessions_api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/__init__.py`

- [ ] **Step 1: Write failing service and API tests**

```python
def test_create_session_rejects_missing_project(monkeypatch):
    service = SessionService(session_repo=FakeSessionRepo(), project_repo=FakeProjectRepo(project=None))
    with pytest.raises(ValueError, match="项目不存在"):
        service.create_session("missing-project", SessionCreate(title="新建聊天"))
```

```python
def test_get_project_sessions_returns_sessions(client):
    response = client.get("/api/projects/project-1/sessions")
    assert response.status_code == 200
    assert response.json()[0]["project_id"] == "project-1"
```

- [ ] **Step 2: Run targeted backend tests and verify failure**

Run: `pytest backend/tests/test_services/test_session_service.py backend/tests/test_api/test_sessions_api.py -v`
Expected: FAIL because `SessionService` and route module do not exist.

- [ ] **Step 3: Add session service with explicit project validation**

```python
class SessionService:
    def create_session(self, project_id: str, payload: SessionCreate) -> Session:
        project = self.project_repo.get(project_id)
        if not project:
            raise ValueError("项目不存在")

        session = Session(
            id=f"session-{uuid4().hex[:8]}",
            project_id=project_id,
            title=payload.title or "新建聊天",
            preferred_provider_id=payload.preferred_provider_id,
            preferred_model_id=payload.preferred_model_id,
        )
        return self.session_repo.create(session)
```

- [ ] **Step 4: Add session routes and register router**

```python
@router.post("/projects/{project_id}/sessions", response_model=Session)
def create_session(project_id: str, payload: SessionCreate):
    try:
        return session_service.create_session(project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/projects/{project_id}/sessions", response_model=list[Session])
def list_project_sessions(project_id: str):
    return session_service.list_project_sessions(project_id)
```

- [ ] **Step 5: Run service and API tests and verify pass**

Run: `pytest backend/tests/test_services/test_session_service.py backend/tests/test_api/test_sessions_api.py -v`
Expected: PASS for create/list/get/update/delete session behavior.

- [ ] **Step 6: Commit session service and API**

```bash
git add backend/app/services/session_service.py backend/app/api/routes/sessions.py backend/app/main.py backend/app/services/__init__.py backend/tests/test_services/test_session_service.py backend/tests/test_api/test_sessions_api.py
git commit -m "feat: add session service and api"
```

---

### Task 3: Return Round-Based Session History From Backend

**Files:**
- Create: `backend/app/services/transcript_service.py`
- Modify: `backend/app/models/conversation.py`
- Modify: `backend/app/storage/repositories/conversation_repo.py`
- Modify: `backend/app/api/routes/sessions.py`
- Test: `backend/tests/test_services/test_agent_service.py`
- Test: `backend/tests/test_api/test_sessions_api.py`

- [ ] **Step 1: Write failing tests for grouped round history**

```python
def test_session_history_groups_items_into_rounds(client, seeded_conversation_items):
    response = client.get("/api/sessions/session-1/history")
    payload = response.json()

    assert payload["session_id"] == "session-1"
    assert len(payload["rounds"]) == 1
    assert payload["rounds"][0]["items"][0]["type"] == "user-message"
```

- [ ] **Step 2: Run session history tests and verify failure**

Run: `pytest backend/tests/test_api/test_sessions_api.py -v`
Expected: FAIL because current history route shape is flat archive data.

- [ ] **Step 3: Add transcript service that groups ordered items into rounds**

```python
class TranscriptService:
    def build_session_history(self, session_id: str) -> SessionHistoryResponse:
        items = self.conversation_repo.list_by_session(session_id)
        rounds: list[TranscriptRoundResponse] = []
        current_round: TranscriptRoundResponse | None = None

        for item in items:
            if item.item_type == "user-message":
                current_round = TranscriptRoundResponse(
                    id=f"round-{item.id}",
                    created_at=item.created_at,
                    items=[self._to_item_response(item)],
                )
                rounds.append(current_round)
                continue

            if current_round is not None:
                current_round.items.append(self._to_item_response(item))

        return SessionHistoryResponse(session_id=session_id, project_id=items[0].project_id if items else None, rounds=rounds)
```

- [ ] **Step 4: Expose grouped history route and stop using flat archive response**

```python
@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(session_id: str):
    return transcript_service.build_session_history(session_id)
```

- [ ] **Step 5: Run backend history tests and verify pass**

Run: `pytest backend/tests/test_api/test_sessions_api.py backend/tests/test_services/test_agent_service.py -v`
Expected: PASS with `rounds` response shape.

- [ ] **Step 6: Commit round-based history API**

```bash
git add backend/app/services/transcript_service.py backend/app/models/conversation.py backend/app/storage/repositories/conversation_repo.py backend/app/api/routes/sessions.py backend/tests/test_api/test_sessions_api.py backend/tests/test_services/test_agent_service.py
git commit -m "feat: return round based session history"
```

---

### Task 4: Enforce Session Validation On Execution Creation

**Files:**
- Modify: `backend/app/services/agent_service.py`
- Modify: `backend/tests/test_services/test_agent_service.py`
- Modify: `backend/app/models/execution.py`

- [ ] **Step 1: Write failing tests for nonexistent and cross-project session rejection**

```python
def test_create_execution_rejects_missing_session(monkeypatch):
    service = build_service_with_repos(monkeypatch, session=None)
    with pytest.raises(ValueError, match="会话不存在"):
        service.create_execution(ExecutionCreate(project_id="project-1", session_id="missing", task="hi"))
```

```python
def test_create_execution_rejects_cross_project_session(monkeypatch):
    session = Session(id="session-1", project_id="project-2", title="test")
    service = build_service_with_repos(monkeypatch, session=session)
    with pytest.raises(ValueError, match="会话不属于当前项目"):
        service.create_execution(ExecutionCreate(project_id="project-1", session_id="session-1", task="hi"))
```

- [ ] **Step 2: Run service tests and verify failure**

Run: `pytest backend/tests/test_services/test_agent_service.py -v`
Expected: FAIL because execution creation does not validate session ownership yet.

- [ ] **Step 3: Validate session existence and project ownership in agent service**

```python
session = self.session_repo.get(request.session_id)
if not session:
    raise ValueError("会话不存在")
if session.project_id != request.project_id:
    raise ValueError("会话不属于当前项目")
```

- [ ] **Step 4: Run service tests and verify pass**

Run: `pytest backend/tests/test_services/test_agent_service.py -v`
Expected: PASS for execution/session validation.

- [ ] **Step 5: Commit execution validation changes**

```bash
git add backend/app/services/agent_service.py backend/app/models/execution.py backend/tests/test_services/test_agent_service.py
git commit -m "fix: validate session ownership for executions"
```

---

### Task 5: Change Execution Persistence To Completed Commit / Cancelled Discard / Failed Retain

**Files:**
- Modify: `backend/app/services/agent_service.py`
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/tests/test_execution/test_rapid_loop.py`
- Modify: `backend/tests/test_services/test_agent_service.py`

- [ ] **Step 1: Write failing tests for cancelled discard and failed retain**

```python
@pytest.mark.asyncio
async def test_cancelled_execution_has_no_transcript_items(execution_loop, mock_llm):
    async def mock_stream(messages, tools=None):
        raise asyncio.CancelledError()

    mock_llm.stream_complete = mock_stream
    result = await execution_loop.run("取消任务", session_id="session-1", project_id="project-1")
    assert result.status.value == "cancelled"
    assert result.transcript_items == []
```

```python
@pytest.mark.asyncio
async def test_failed_execution_retains_failure_round(execution_loop, mock_llm):
    async def mock_stream(messages, tools=None):
        raise RuntimeError("boom")

    mock_llm.stream_complete = mock_stream
    result = await execution_loop.run("失败任务", session_id="session-1", project_id="project-1")
    assert result.status.value == "failed"
    assert result.transcript_items[0]["item_type"] == "user-message"
    assert result.transcript_items[-1]["item_type"] == "assistant-message"
```

- [ ] **Step 2: Run execution tests and verify failure**

Run: `pytest backend/tests/test_execution/test_rapid_loop.py backend/tests/test_services/test_agent_service.py -v`
Expected: FAIL because cancelled still flows through generic transcript generation.

- [ ] **Step 3: Move transcript building behind explicit status checks**

```python
if execution.status == ExecutionStatus.CANCELLED:
    execution.transcript_items = []
elif execution.status == ExecutionStatus.FAILED:
    execution.transcript_items = self._build_failed_round(context, execution, session_id, project_id)
else:
    execution.transcript_items = self._build_completed_round(context, execution, session_id, project_id)
```

- [ ] **Step 4: Persist conversation history only for completed and failed executions**

```python
if result.status in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED} and result.transcript_items:
    self._persist_conversation_history(result)
```

- [ ] **Step 5: Run execution and service tests and verify pass**

Run: `pytest backend/tests/test_execution/test_rapid_loop.py backend/tests/test_services/test_agent_service.py -v`
Expected: PASS for completed, cancelled, failed transcript semantics.

- [ ] **Step 6: Commit execution persistence semantics**

```bash
git add backend/app/services/agent_service.py backend/app/execution/rapid_loop.py backend/tests/test_execution/test_rapid_loop.py backend/tests/test_services/test_agent_service.py
git commit -m "fix: discard cancelled transcript rounds"
```

---

### Task 6: Add Frontend Session API And Session Store

**Files:**
- Create: `frontend/src/features/sessions/sessionApi.ts`
- Create: `frontend/src/features/sessions/sessionStore.ts`
- Create: `frontend/src/features/sessions/sessionStore.test.ts`
- Modify: `frontend/src/services/apiClient.ts`
- Modify: `frontend/src/types/workspace.ts`

- [ ] **Step 1: Write failing frontend store tests for storing backend session data**

```ts
it('stores sessions by project and history by session', () => {
  const store = createSessionStore()
  store.getState().setProjectSessions('project-1', [{ id: 'session-1', projectId: 'project-1', title: '新建聊天', preferredProviderId: undefined, preferredModelId: undefined, createdAt: '2026-04-20T00:00:00Z', updatedAt: '2026-04-20T00:00:00Z' }])
  store.getState().setSessionHistory('session-1', [{ id: 'round-1', createdAt: '2026-04-20T00:00:00Z', items: [{ id: 'item-1', type: 'user-message', content: 'hi' }] }])

  expect(store.getState().sessionsByProjectId['project-1']).toHaveLength(1)
  expect(store.getState().historyBySessionId['session-1']).toHaveLength(1)
})
```

- [ ] **Step 2: Run frontend session store test and verify failure**

Run: `npm test -- sessionStore.test.ts`
Expected: FAIL because session feature files do not exist.

- [ ] **Step 3: Add typed session API and store**

```ts
export const sessionApi = {
  listProjectSessions: (projectId: string) => apiClient.get<SessionSummary[]>(`/api/projects/${projectId}/sessions`),
  createSession: (projectId: string, data: SessionCreatePayload) => apiClient.post<SessionSummary>(`/api/projects/${projectId}/sessions`, data),
  getSessionHistory: (sessionId: string) => apiClient.get<SessionHistoryResponse>(`/api/sessions/${sessionId}/history`),
  updateSession: (sessionId: string, data: SessionUpdatePayload) => apiClient.patch<SessionSummary>(`/api/sessions/${sessionId}`, data),
  deleteSession: (sessionId: string) => apiClient.delete(`/api/sessions/${sessionId}`),
}
```

```ts
interface SessionState {
  sessionsByProjectId: Record<string, SessionSummary[]>
  historyBySessionId: Record<string, WorkspaceSessionRound[]>
  setProjectSessions: (projectId: string, sessions: SessionSummary[]) => void
  setSessionHistory: (sessionId: string, rounds: WorkspaceSessionRound[]) => void
  upsertSession: (projectId: string, session: SessionSummary) => void
  removeSession: (projectId: string, sessionId: string) => void
}
```

- [ ] **Step 4: Run frontend session store test and verify pass**

Run: `npm test -- sessionStore.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit frontend session data layer**

```bash
git add frontend/src/features/sessions/sessionApi.ts frontend/src/features/sessions/sessionStore.ts frontend/src/features/sessions/sessionStore.test.ts frontend/src/services/apiClient.ts frontend/src/types/workspace.ts
git commit -m "feat: add frontend session store"
```

---

### Task 7: Shrink workspaceStore To Pure UI State

**Files:**
- Modify: `frontend/src/stores/workspaceStore.ts`
- Modify: `frontend/src/demo/demoData.ts`
- Modify: `frontend/src/App.cleanup.test.ts`

- [ ] **Step 1: Write failing test asserting workspaceStore no longer owns sessions**

```ts
it('persists only ui state fields', () => {
  const state = useWorkspaceStore.getState()
  expect('currentSessionId' in state).toBe(true)
  expect('searchQuery' in state).toBe(true)
  expect('createSession' in state).toBe(false)
  expect('sessions' in state).toBe(false)
})
```

- [ ] **Step 2: Run cleanup and store tests and verify failure**

Run: `npm test -- App.cleanup.test.ts`
Expected: FAIL because `workspaceStore` still exposes local session data and actions.

- [ ] **Step 3: Remove local session state and local session ID generation from workspaceStore**

```ts
interface WorkspaceState {
  currentSessionId: string | null
  expandedProjectIds: string[]
  expandedSessionProjectIds: string[]
  searchQuery: string
  searchOpen: boolean
  setCurrentSessionId: (sessionId: string | null) => void
  toggleProjectExpanded: (projectId: string) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  toggleProjectShowAll: (projectId: string) => void
  setSearchQuery: (query: string) => void
  setSearchOpen: (open: boolean) => void
}
```

- [ ] **Step 4: Run frontend cleanup tests and verify pass**

Run: `npm test -- App.cleanup.test.ts`
Expected: PASS with workspaceStore persisting only UI state.

- [ ] **Step 5: Commit workspaceStore contraction**

```bash
git add frontend/src/stores/workspaceStore.ts frontend/src/demo/demoData.ts frontend/src/App.cleanup.test.ts
git commit -m "refactor: shrink workspace ui store"
```

---

### Task 8: Replace Flat Archive Reconstruction With Session Loader

**Files:**
- Create: `frontend/src/features/sessions/sessionLoader.ts`
- Create: `frontend/src/features/sessions/sessionLoader.test.ts`
- Modify: `frontend/src/features/workspace/transcriptArchive.ts`
- Modify: `frontend/src/features/workspace/transcriptArchive.test.ts`

- [ ] **Step 1: Write failing tests proving loader stores backend rounds directly**

```ts
it('writes backend round history into sessionStore without archive regrouping', async () => {
  vi.spyOn(sessionApi, 'getSessionHistory').mockResolvedValue({ data: { session_id: 'session-1', project_id: 'project-1', rounds: [{ id: 'round-1', created_at: '2026-04-20T00:00:00Z', items: [{ id: 'item-1', type: 'user-message', content: 'hi' }] }] } } as never)

  await ensureSessionHistoryLoaded('session-1')

  expect(useSessionStore.getState().historyBySessionId['session-1'][0].items[0].type).toBe('user-message')
})
```

- [ ] **Step 2: Run session loader tests and verify failure**

Run: `npm test -- sessionLoader.test.ts transcriptArchive.test.ts`
Expected: FAIL because loader does not exist and archive regrouping still owns history shape.

- [ ] **Step 3: Add loader and reduce transcriptArchive to shared shape helpers only**

```ts
export async function ensureSessionHistoryLoaded(sessionId: string) {
  const response = await sessionApi.getSessionHistory(sessionId)
  const rounds = response.data.rounds.map(normalizeRoundFromApi)
  useSessionStore.getState().setSessionHistory(sessionId, rounds)
}
```

- [ ] **Step 4: Delete round rebuilding logic from transcriptArchive**

```ts
export function normalizeRoundFromApi(round: SessionHistoryRound): WorkspaceSessionRound {
  return {
    id: round.id,
    createdAt: round.created_at,
    items: round.items.map(normalizeItemFromApi),
  }
}
```

- [ ] **Step 5: Run loader and archive tests and verify pass**

Run: `npm test -- sessionLoader.test.ts transcriptArchive.test.ts`
Expected: PASS with no `buildRoundsFromTranscriptArchive()` dependency.

- [ ] **Step 6: Commit backend-history frontend loader path**

```bash
git add frontend/src/features/sessions/sessionLoader.ts frontend/src/features/sessions/sessionLoader.test.ts frontend/src/features/workspace/transcriptArchive.ts frontend/src/features/workspace/transcriptArchive.test.ts
git commit -m "refactor: load session history as rounds"
```

---

### Task 9: Split Execution Draft Round From Overlay UI

**Files:**
- Create: `frontend/src/hooks/useExecutionDraftRound.ts`
- Create: `frontend/src/hooks/useExecutionDraftRound.test.ts`
- Create: `frontend/src/hooks/useExecutionOverlayUi.ts`
- Modify: `frontend/src/hooks/useExecutionOverlay.ts`
- Modify: `frontend/src/hooks/useExecutionRuntime.ts`
- Modify: `frontend/src/hooks/useExecutionWebSocket.ts`

- [ ] **Step 1: Write failing tests for completed clear-draft, cancelled discard, failed refresh hooks**

```ts
it('clears draft on complete before history refresh', () => {
  const { result } = renderHook(() => useExecutionDraftRound())
  act(() => result.current.startDraftRound('session-1', 'hello'))
  act(() => result.current.completeDraftRound())
  expect(result.current.items).toEqual([])
})
```

- [ ] **Step 2: Run execution draft tests and verify failure**

Run: `npm test -- useExecutionDraftRound.test.ts`
Expected: FAIL because draft round logic is still buried inside `useExecutionOverlay`.

- [ ] **Step 3: Extract draft-round ownership into dedicated hook**

```ts
export function useExecutionDraftRound() {
  const [draftRoundItems, setDraftRoundItems] = useState<WorkspaceChatItem[]>([])
  const clearDraftRound = useCallback(() => setDraftRoundItems([]), [])
  const appendDraftItems = useCallback((items: WorkspaceChatItem[]) => {
    setDraftRoundItems((current) => [...current, ...items])
  }, [])
  return { draftRoundItems, appendDraftItems, clearDraftRound }
}
```

- [ ] **Step 4: Remove formal history persistence from overlay hook**

```ts
// delete calls to:
// useWorkspaceStore.getState()
// saveSessionRounds(...)
// updateSessionTitle(...)
```

- [ ] **Step 5: Update runtime flow to honor fixed sequence**

```ts
handleExecutionComplete: async () => {
  clearDraftRound()
  await refreshSessionHistory(activeSessionId)
}
```

- [ ] **Step 6: Run hook tests and verify pass**

Run: `npm test -- useExecutionDraftRound.test.ts executionOverlayState.test.ts`
Expected: PASS with draft state separated from overlay UI state.

- [ ] **Step 7: Commit execution draft split**

```bash
git add frontend/src/hooks/useExecutionDraftRound.ts frontend/src/hooks/useExecutionDraftRound.test.ts frontend/src/hooks/useExecutionOverlayUi.ts frontend/src/hooks/useExecutionOverlay.ts frontend/src/hooks/useExecutionRuntime.ts frontend/src/hooks/useExecutionWebSocket.ts
git commit -m "refactor: split execution draft round from overlay ui"
```

---

### Task 10: Refactor AgentWorkspace To Session Feature Layer

**Files:**
- Create: `frontend/src/hooks/useCurrentSessionViewModel.ts`
- Create: `frontend/src/hooks/useSessionActions.ts`
- Create: `frontend/src/hooks/useSendMessage.ts`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Write failing tests or assertions for session creation and send flow**

```ts
it('creates backend session before first send when no current session exists', async () => {
  vi.spyOn(sessionActions, 'createSession').mockResolvedValue({ id: 'session-1', projectId: 'project-1', title: '新建聊天', createdAt: '', updatedAt: '' } as never)
  const { result } = renderHook(() => useSendMessage())
  await result.current.sendMessage('hello')
  expect(sessionActions.createSession).toHaveBeenCalled()
})
```

- [ ] **Step 2: Run targeted frontend tests and verify failure**

Run: `npm test -- ChatInput.test.ts App.cleanup.test.ts`
Expected: FAIL or require new tests because `AgentWorkspace` still owns direct API and store writes.

- [ ] **Step 3: Move session loading, selection, and send orchestration into dedicated hooks**

```ts
export function useSendMessage() {
  const createSession = useSessionActions((state) => state.createSession)
  const startExecutionRun = useExecutionRuntime(...).startExecutionRun

  return {
    sendMessage: async (message: string) => {
      const session = currentSession ?? await createSession(currentProject.id, selection)
      await startExecutionRun({ sessionId: session.id, message, projectId: currentProject.id, providerId: selection.providerId, modelId: selection.modelId })
    },
  }
}
```

- [ ] **Step 4: Simplify AgentWorkspace to composition-only page**

```tsx
export default function AgentWorkspace() {
  const vm = useCurrentSessionViewModel()
  const actions = useSendMessage()
  return (
    <>
      <WorkspaceHeader {...vm.headerProps} />
      <WorkspaceTranscript items={vm.renderItems} />
      <ChatInput onSend={actions.sendMessage} />
    </>
  )
}
```

- [ ] **Step 5: Run page-related tests and verify pass**

Run: `npm test -- ChatInput.test.ts App.cleanup.test.ts`
Expected: PASS with `AgentWorkspace` no longer directly loading history or writing session state.

- [ ] **Step 6: Commit AgentWorkspace refactor**

```bash
git add frontend/src/hooks/useCurrentSessionViewModel.ts frontend/src/hooks/useSessionActions.ts frontend/src/hooks/useSendMessage.ts frontend/src/pages/AgentWorkspace.tsx
git commit -m "refactor: move workspace session logic into hooks"
```

---

### Task 11: Refactor WorkspaceSidebar To Use Backend Sessions

**Files:**
- Modify: `frontend/src/components/layout/WorkspaceSidebar.tsx`
- Modify: `frontend/src/features/projects/projectLoader.ts`
- Modify: `frontend/src/features/sessions/sessionActions.ts`

- [ ] **Step 1: Write failing behavior test or direct assertions for sidebar session source**

```ts
it('reads session lists from sessionStore instead of workspaceStore', () => {
  useSessionStore.getState().setProjectSessions('project-1', [{ id: 'session-1', projectId: 'project-1', title: 'chat', createdAt: '', updatedAt: '' }])
  expect(selectProjectSessions('project-1')[0].id).toBe('session-1')
})
```

- [ ] **Step 2: Run relevant frontend tests and verify failure**

Run: `npm test -- projectLoader.test.ts App.cleanup.test.ts`
Expected: FAIL or require new assertions because sidebar still depends on `workspaceStore.sessions` and local `createSession`.

- [ ] **Step 3: Replace local session CRUD with session feature actions**

```ts
const projectSessions = useSessionStore((state) => state.sessionsByProjectId[project.id] || [])
const { createSession, deleteSession, renameSession } = useSessionActions()
```

- [ ] **Step 4: Remove obsolete local session operations from sidebar**

```ts
// delete usage of:
// createSession(...)
// updateSessionTitle(...)
// removeSession(...)
// removeProjectSessions(...)
```

- [ ] **Step 5: Run sidebar-adjacent tests and verify pass**

Run: `npm test -- projectLoader.test.ts App.cleanup.test.ts`
Expected: PASS with sidebar backed by sessionStore and sessionActions.

- [ ] **Step 6: Commit sidebar migration**

```bash
git add frontend/src/components/layout/WorkspaceSidebar.tsx frontend/src/features/projects/projectLoader.ts frontend/src/features/sessions/sessionActions.ts
git commit -m "refactor: move sidebar to backend sessions"
```

---

### Task 12: Split SettingsPage Domain Logic Out Of The Page

**Files:**
- Create: `frontend/src/features/llm/providerDraft.ts`
- Create: `frontend/src/features/llm/providerActions.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/features/llm/llmSettingsLoader.test.ts`

- [ ] **Step 1: Write failing unit tests for provider draft normalization and validation**

```ts
it('normalizes provider draft with fallback default model id', () => {
  const provider = normalizeProviderDraft({ id: '', name: 'OpenAI', models: [{ id: 'model-1', display_name: 'GPT', model_name: 'gpt', enabled: true }], default_model_id: '' })
  expect(provider.default_model_id).toBe('model-1')
})
```

- [ ] **Step 2: Run llm feature tests and verify failure**

Run: `npm test -- llmSettingsLoader.test.ts`
Expected: FAIL because draft logic still lives inside `SettingsPage.tsx`.

- [ ] **Step 3: Extract provider draft helpers and provider action orchestration**

```ts
export function normalizeProviderDraft(draft: ProviderDraft): ProviderInstance {
  const enabledModels = draft.models.filter((model) => model.enabled)
  return {
    ...draft,
    default_model_id: draft.default_model_id || enabledModels[0]?.id || draft.models[0]?.id || '',
  }
}
```

- [ ] **Step 4: Reduce SettingsPage to form state and rendering only**

```tsx
const { saveProvider, deleteProvider, testProviderConnection, setDefaultSelection } = useProviderActions()
```

- [ ] **Step 5: Run llm tests and verify pass**

Run: `npm test -- llmSettingsLoader.test.ts`
Expected: PASS and reduced SettingsPage logic size.

- [ ] **Step 6: Commit SettingsPage split**

```bash
git add frontend/src/features/llm/providerDraft.ts frontend/src/features/llm/providerActions.ts frontend/src/pages/SettingsPage.tsx frontend/src/features/llm/llmSettingsLoader.test.ts
git commit -m "refactor: extract llm provider page logic"
```

---

### Task 13: Delete Obsolete Local Session And Archive Code Paths

**Files:**
- Modify: `frontend/src/stores/workspaceStore.ts`
- Modify: `frontend/src/features/workspace/transcriptArchive.ts`
- Modify: `frontend/src/hooks/useExecutionOverlay.ts`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/components/layout/WorkspaceSidebar.tsx`
- Modify: `frontend/src/demo/demoData.ts`

- [ ] **Step 1: Search for obsolete local-session symbols and add cleanup assertions**

```text
createSessionId
buildRoundsFromTranscriptArchive
saveSessionRounds
updateSessionTitle
updateSessionPreferences
removeProjectSessions
```

- [ ] **Step 2: Run targeted tests before cleanup**

Run: `npm test -- App.cleanup.test.ts transcriptArchive.test.ts`
Expected: Existing tests show remaining references or require updated assertions.

- [ ] **Step 3: Delete obsolete symbols and dead code paths**

```ts
// remove from codebase:
// createSessionId()
// buildRoundsFromTranscriptArchive()
// any useWorkspaceStore session persistence helpers
// overlay-driven persisted history writes
```

- [ ] **Step 4: Add final cleanup assertions**

```ts
it('does not expose local session persistence helpers', () => {
  const state = useWorkspaceStore.getState() as Record<string, unknown>
  expect(state.saveSessionRounds).toBeUndefined()
  expect(state.updateSessionTitle).toBeUndefined()
  expect(state.updateSessionPreferences).toBeUndefined()
})
```

- [ ] **Step 5: Run full frontend test suite for affected files**

Run: `npm test -- App.cleanup.test.ts transcriptArchive.test.ts sessionStore.test.ts sessionLoader.test.ts useExecutionDraftRound.test.ts`
Expected: PASS and no runtime path depends on local session truth.

- [ ] **Step 6: Commit legacy path removal**

```bash
git add frontend/src/stores/workspaceStore.ts frontend/src/features/workspace/transcriptArchive.ts frontend/src/hooks/useExecutionOverlay.ts frontend/src/pages/AgentWorkspace.tsx frontend/src/components/layout/WorkspaceSidebar.tsx frontend/src/demo/demoData.ts frontend/src/App.cleanup.test.ts
git commit -m "refactor: remove legacy local session paths"
```

---

### Task 14: Verify End-To-End Behavior

**Files:**
- Modify: `docs/superpowers/status/implementation-status-2026-04-16-写了下一阶段的开发目标.md` only if project keeps status notes
- Test: `backend/tests/test_services/test_agent_service.py`
- Test: `backend/tests/test_execution/test_rapid_loop.py`
- Test: `backend/tests/test_api/test_sessions_api.py`
- Test: `frontend/src/App.cleanup.test.ts`
- Test: `frontend/src/features/sessions/sessionStore.test.ts`
- Test: `frontend/src/features/sessions/sessionLoader.test.ts`
- Test: `frontend/src/hooks/useExecutionDraftRound.test.ts`

- [ ] **Step 1: Run targeted backend verification suite**

Run: `pytest backend/tests/test_storage/test_repositories.py backend/tests/test_services/test_session_service.py backend/tests/test_services/test_agent_service.py backend/tests/test_execution/test_rapid_loop.py backend/tests/test_api/test_sessions_api.py -v`
Expected: PASS.

- [ ] **Step 2: Run targeted frontend verification suite**

Run: `npm test -- App.cleanup.test.ts sessionStore.test.ts sessionLoader.test.ts useExecutionDraftRound.test.ts transcriptArchive.test.ts projectLoader.test.ts llmSettingsLoader.test.ts`
Expected: PASS.

- [ ] **Step 3: Run frontend production build**

Run: `npm run build`
Expected: PASS with no TypeScript errors.

- [ ] **Step 4: Spot-check required semantics manually**

```text
1. Create a project session from the UI.
2. Refresh page and confirm session still exists.
3. Send a message and confirm completed round appears after refresh.
4. Send another message and cancel midway; confirm no new round appears after refresh.
5. Trigger a failed execution path; confirm failed round is visible in history.
```

- [ ] **Step 5: Commit final verification updates if any**

```bash
git add .
git commit -m "test: verify session transcript boundary migration"
```

---

## Self-Review Checklist

- Session backend ownership: covered by Tasks 1, 2, 4.
- Round-based history API: covered by Task 3.
- Completed / failed / cancelled semantics: covered by Task 5.
- Frontend session feature layer: covered by Tasks 6, 8, 10, 11.
- workspaceStore shrink: covered by Task 7.
- Overlay split and fixed complete ordering: covered by Task 9.
- Settings page responsibility split: covered by Task 12.
- Full removal of obsolete local session/archive paths: covered by Task 13.
- Verification and regression safety: covered by Task 14.

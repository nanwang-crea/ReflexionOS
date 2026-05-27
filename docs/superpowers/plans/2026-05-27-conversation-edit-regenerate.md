# Conversation Edit & Regenerate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add message editing and assistant response regeneration to conversations, with an atomic `edit_and_rerun` API that truncates subsequent messages and starts a new turn.

**Architecture:** Single WebSocket message `conversation:edit_and_rerun` performs truncation + new turn creation atomically. Backend physically deletes truncated turns/runs/messages from DB. Frontend handles `messages.truncated` event to update state, plus adds hover action buttons (Copy, Edit, Regenerate) to messages.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Zustand (frontend), SQLAlchemy (DB), lucide-react (icons)

---

### Task 1: Add MESSAGES_TRUNCATED EventType

**Files:**
- Modify: `backend/app/models/conversation.py:42-60`

- [ ] **Step 1: Add the new EventType enum value**

In `backend/app/models/conversation.py`, add `MESSAGES_TRUNCATED` to the `EventType` enum after `SYSTEM_NOTICE_EMITTED`:

```python
class EventType(str, Enum):
    TURN_CREATED = "turn.created"
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_WAITING_FOR_APPROVAL = "run.waiting_for_approval"
    RUN_RESUMING = "run.resuming"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_DENIED = "approval.denied"
    APPROVAL_STALE = "approval.stale"
    MESSAGE_CREATED = "message.created"
    MESSAGE_CONTENT_COMMITTED = "message.content_committed"
    MESSAGE_PAYLOAD_UPDATED = "message.payload_updated"
    MESSAGE_COMPLETED = "message.completed"
    MESSAGE_FAILED = "message.failed"
    SYSTEM_NOTICE_EMITTED = "system.notice_emitted"
    MESSAGES_TRUNCATED = "messages.truncated"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/conversation.py
git commit -m "feat: add MESSAGES_TRUNCATED event type"
```

---

### Task 2: Add repository delete methods for truncation

**Files:**
- Modify: `backend/app/storage/repositories/turn_repo.py`
- Modify: `backend/app/storage/repositories/message_repo.py`
- Modify: `backend/app/storage/repositories/run_repo.py`
- Modify: `backend/app/storage/repositories/message_search_document_repo.py`

- [ ] **Step 1: Add `delete_by_session_after_index` to TurnRepository**

In `backend/app/storage/repositories/turn_repo.py`, add after `list_terminal_before`:

```python
def delete_by_session_after_index(self, session_id: str, min_turn_index: int, *, db_session=None) -> list[str]:
    if db_session is None:
        with self.db.get_session() as managed_session:
            return self.delete_by_session_after_index(session_id, min_turn_index, db_session=managed_session)

    turn_ids = (
        db_session.query(TurnModel.id)
        .filter(TurnModel.session_id == session_id, TurnModel.turn_index >= min_turn_index)
        .all()
    )
    turn_id_list = [tid[0] for tid in turn_ids]
    db_session.query(TurnModel).filter(
        TurnModel.session_id == session_id, TurnModel.turn_index >= min_turn_index
    ).delete(synchronize_session=False)
    db_session.flush()
    return turn_id_list
```

- [ ] **Step 2: Add `delete_by_turn_ids` to MessageRepository**

In `backend/app/storage/repositories/message_repo.py`, add after `from_payload`:

```python
def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
    if not turn_ids:
        return 0

    if db_session is None:
        with self.db.get_session() as managed_session:
            return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

    deleted = (
        db_session.query(MessageModel)
        .filter(MessageModel.turn_id.in_(turn_ids))
        .delete(synchronize_session=False)
    )
    db_session.flush()
    return int(deleted or 0)

def get_user_message_by_turn(self, turn_id: str, *, db_session=None) -> Message | None:
    if db_session is None:
        with self.db.get_session() as managed_session:
            return self.get_user_message_by_turn(turn_id, db_session=managed_session)

    model = (
        db_session.query(MessageModel)
        .filter_by(turn_id=turn_id, message_type=MessageType.USER_MESSAGE.value)
        .order_by(MessageModel.turn_message_index.asc())
        .first()
    )
    return self._to_domain(model)
```

- [ ] **Step 3: Add `delete_by_turn_ids` to RunRepository**

In `backend/app/storage/repositories/run_repo.py`, add after `update`:

```python
def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
    if not turn_ids:
        return 0

    if db_session is None:
        with self.db.get_session() as managed_session:
            return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

    deleted = (
        db_session.query(RunModel)
        .filter(RunModel.turn_id.in_(turn_ids))
        .delete(synchronize_session=False)
    )
    db_session.flush()
    return int(deleted or 0)
```

- [ ] **Step 4: Add `delete_by_turn_ids` to MessageSearchDocumentRepository**

In `backend/app/storage/repositories/message_search_document_repo.py`, add after `upsert`:

```python
def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
    if not turn_ids:
        return 0

    if db_session is None:
        with self.db.get_session() as managed_session:
            return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

    deleted = (
        db_session.query(MessageSearchDocumentModel)
        .filter(MessageSearchDocumentModel.turn_id.in_(turn_ids))
        .delete(synchronize_session=False)
    )
    db_session.flush()
    return int(deleted or 0)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/repositories/turn_repo.py backend/app/storage/repositories/message_repo.py backend/app/storage/repositories/run_repo.py backend/app/storage/repositories/message_search_document_repo.py
git commit -m "feat: add repository delete methods for conversation truncation"
```

---

### Task 3: Add `truncate_after_message` and `edit_and_rerun` to ConversationService

**Files:**
- Modify: `backend/app/services/conversation_service.py`

- [ ] **Step 1: Add `truncate_after_message` method**

In `backend/app/services/conversation_service.py`, add after `cancel_run`:

```python
def truncate_after_message(
    self,
    *,
    session_id: str,
    message_id: str,
    keep_turn: bool = False,
) -> tuple[list[str], str | None]:
    """Delete all turns after the target message's turn.

    If keep_turn is True, delete only messages/runs after the user_message
    within the target turn, but keep the turn and its user message.

    Returns (deleted_turn_ids, surviving_user_content).
    """
    message = self.message_repo.get(message_id)
    if message is None:
        raise NotFoundValueError("消息不存在")
    if message.session_id != session_id:
        raise ValueError("消息不属于当前会话")

    turn = self.turn_repo.get(message.turn_id)
    if turn is None:
        raise NotFoundValueError("轮次不存在")

    surviving_user_content: str | None = None
    deleted_turn_ids: list[str] = []

    if keep_turn:
        user_msg = self.message_repo.get_user_message_by_turn(turn.id)
        surviving_user_content = user_msg.content_text if user_msg else None

        later_turn_ids = [
            t.id for t in self.turn_repo.list_by_session(session_id)
            if t.turn_index > turn.turn_index
        ]

        if later_turn_ids:
            self.message_search_repo.delete_by_turn_ids(later_turn_ids)
            self.message_repo.delete_by_turn_ids(later_turn_ids)
            self.run_repo.delete_by_turn_ids(later_turn_ids)
            self.event_repo.delete_by_turn_ids(later_turn_ids)
            self.turn_repo.delete_by_session_after_index(session_id, turn.turn_index + 1)
            deleted_turn_ids.extend(later_turn_ids)

        non_user_msg_ids = [
            m.id for m in self.message_repo.list_by_turn(turn.id)
            if m.id != (user_msg.id if user_msg else "")
        ]
        if non_user_msg_ids:
            self.message_search_repo.delete_by_turn_ids([turn.id])
            db_msg = self.message_repo.delete_by_turn_ids([turn.id])
            self.run_repo.delete_by_turn_ids([turn.id])
            self.event_repo.delete_by_turn_ids([turn.id])

            if user_msg:
                from app.storage.models import MessageModel
                with self.db.get_session() as db_session:
                    db_session.query(MessageModel).filter_by(id=user_msg.id).delete(synchronize_session=False)
                    db_session.flush()

        deleted_turn_ids.append(turn.id)
    else:
        later_or_equal_turn_ids = [
            t.id for t in self.turn_repo.list_by_session(session_id)
            if t.turn_index >= turn.turn_index
        ]

        if later_or_equal_turn_ids:
            self.message_search_repo.delete_by_turn_ids(later_or_equal_turn_ids)
            self.message_repo.delete_by_turn_ids(later_or_equal_turn_ids)
            self.run_repo.delete_by_turn_ids(later_or_equal_turn_ids)
            self.event_repo.delete_by_turn_ids(later_or_equal_turn_ids)
            self.turn_repo.delete_by_session_after_index(session_id, turn.turn_index)
            deleted_turn_ids.extend(later_or_equal_turn_ids)

    session = self.session_repo.get(session_id)
    if session and session.active_turn_id in deleted_turn_ids:
        self.session_repo.update(
            session.model_copy(update={"active_turn_id": None})
        )

    return deleted_turn_ids, surviving_user_content
```

- [ ] **Step 2: Add `edit_and_rerun` method**

After `truncate_after_message`, add:

```python
def edit_and_rerun(
    self,
    *,
    session_id: str,
    message_id: str,
    new_content: str | None,
    provider_id: str,
    model_id: str,
    workspace_ref: str | None,
) -> StartTurnResult:
    """Atomically truncate after a message and start a new turn.

    If new_content is None or empty, this is a regenerate operation:
    the original user message content is reused.
    If new_content is provided, this is an edit operation:
    the new content replaces the original user message.
    """
    with self.acquire_session_write_lock(session_id):
        session = self.session_repo.get(session_id)
        if session is None:
            raise NotFoundValueError("会话不存在")

        message = self.message_repo.get(message_id)
        if message is None:
            raise NotFoundValueError("消息不存在")
        if message.session_id != session_id:
            raise ValueError("消息不属于当前会话")

        is_user_message = message.message_type == MessageType.USER_MESSAGE

        if is_user_message:
            keep_turn = False
            content = new_content if new_content else message.contentText
        else:
            keep_turn = True
            content = new_content

        deleted_turn_ids, surviving_user_content = self.truncate_after_message(
            session_id=session_id,
            message_id=message_id,
            keep_turn=keep_turn,
        )

        if not content and surviving_user_content:
            content = surviving_user_content

        if not content:
            raise ValueError("无法确定重新运行的内容")

        truncated_event = ConversationEvent(
            id=new_event_id(),
            session_id=session_id,
            event_type=EventType.MESSAGES_TRUNCATED,
            payload_json={
                "message_id": message_id,
                "deleted_turn_ids": deleted_turn_ids,
                "is_edit": is_user_message,
                "is_regenerate": not is_user_message,
            },
        )
        self.event_repo.append_many([truncated_event], session_id=session_id, start_seq=session.last_event_seq + 1)
        latest_session = self.session_repo.get(session_id)
        if latest_session:
            self.session_repo.update(
                latest_session.model_copy(update={"last_event_seq": truncated_event.seq})
            )

        return self.start_turn(
            session_id=session_id,
            content=content,
            provider_id=provider_id,
            model_id=model_id,
            workspace_ref=workspace_ref,
        )
```

Also add the missing import at the top of the file (add `MessageType` to the existing import from `app.models.conversation`):

```python
from app.models.conversation import ConversationEvent, EventType, Message, MessageType, Run, RunStatus, Turn, TurnStatus
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/conversation_service.py
git commit -m "feat: add truncate_after_message and edit_and_rerun to ConversationService"
```

---

### Task 4: Add `edit_and_rerun` to AgentService

**Files:**
- Modify: `backend/app/services/agent_service.py`

- [ ] **Step 1: Add `edit_and_rerun` method**

In `backend/app/services/agent_service.py`, add after `cancel_run` method (around line 602):

```python
async def edit_and_rerun(
    self,
    *,
    project_id: str,
    session_id: str,
    message_id: str,
    new_content: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> StartTurnResult:
    project = self.project_repo.get(project_id)
    if not project:
        raise NotFoundValueError("项目不存在")

    session = self.session_repo.get(session_id)
    if not session:
        raise NotFoundValueError("会话不存在")

    conversation = self.conversation_service.get_snapshot(session_id)
    active_run_id = resolve_active_run_id_from_conversation(conversation)
    if active_run_id:
        try:
            await self.cancel_run(active_run_id)
        except Exception:
            logger.warning("取消活跃运行失败: run_id=%s", active_run_id)

    resolved_llm = self.llm_provider_service.resolve_llm_config(provider_id, model_id)

    before_seq = self.session_repo.get(session_id).last_event_seq

    started = self.conversation_service.edit_and_rerun(
        session_id=session_id,
        message_id=message_id,
        new_content=new_content,
        provider_id=resolved_llm.provider_id,
        model_id=resolved_llm.model_id,
        workspace_ref=project.path,
    )

    events = self.conversation_service.list_events_after(session_id, before_seq)
    await self._broadcast_conversation_events(session_id=session_id, events=events)

    self.schedule_turn(
        run_id=started.run.id,
        session_id=session_id,
        turn_id=started.turn.id,
        task=started.user_message.contentText,
        project_id=project.id,
        project_path=project.path,
        provider_id=resolved_llm.provider_id,
        model_id=resolved_llm.model_id,
    )
    return started
```

Add helper function at module level (before the class):

```python
def resolve_active_run_id_from_conversation(snapshot: ConversationSnapshot) -> str | None:
    if not snapshot.session.active_turn_id:
        return None
    active_turn = next((t for t in snapshot.turns if t.id == snapshot.session.active_turn_id), None)
    if not active_turn or not active_turn.active_run_id:
        return None
    active_run = next((r for r in snapshot.runs if r.id == active_turn.active_run_id), None)
    if not active_run or active_run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
        return None
    return active_run.id
```

Add `ConversationSnapshot` to the import from `app.models.conversation_snapshot`:

```python
from app.models.conversation_snapshot import ConversationSnapshot, StartTurnResult
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/agent_service.py
git commit -m "feat: add edit_and_rerun to AgentService"
```

---

### Task 5: Add WebSocket handler for `conversation:edit_and_rerun`

**Files:**
- Modify: `backend/app/api/routes/websocket.py`

- [ ] **Step 1: Add handler for `conversation:edit_and_rerun` message**

In `backend/app/api/routes/websocket.py`, add after the `conversation:cancel_run` handler block (after line 163) and before the `conversation:approve_tool`/`conversation:deny_tool` block:

```python
if msg_type == "conversation:edit_and_rerun":
    message_id = msg_data.get("message_id")
    if not isinstance(message_id, str) or not message_id:
        await _send_error(
            websocket,
            code="invalid_request",
            message="message_id 不能为空",
        )
        continue

    new_content = msg_data.get("new_content")
    if new_content is not None and not isinstance(new_content, str):
        await _send_error(
            websocket,
            code="invalid_request",
            message="new_content 必须是字符串",
        )
        continue

    provider_id = msg_data.get("provider_id")
    model_id = msg_data.get("model_id")

    try:
        snapshot = conversation_service.get_snapshot(session_id)
        await agent_service.edit_and_rerun(
            project_id=snapshot.session.project_id,
            session_id=session_id,
            message_id=message_id,
            new_content=new_content if new_content else None,
            provider_id=provider_id,
            model_id=model_id,
        )
    except ValueError as exc:
        await _send_error(websocket, code="invalid_request", message=str(exc))
    continue
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/websocket.py
git commit -m "feat: add WebSocket handler for conversation:edit_and_rerun"
```

---

### Task 6: Frontend — Add `editAndRerun` to WebSocket client and types

**Files:**
- Modify: `frontend/src/services/sessionConversationWebSocket.ts`
- Modify: `frontend/src/types/conversation.ts`

- [ ] **Step 1: Add `buildEditAndRerunMessage` function**

In `frontend/src/services/sessionConversationWebSocket.ts`, add after `buildToolApprovalMessage` (around line 134):

```typescript
function buildEditAndRerunMessage(payload: {
  messageId: string
  newContent?: string | null
  providerId?: string | null
  modelId?: string | null
}) {
  return {
    type: 'conversation:edit_and_rerun',
    data: {
      message_id: payload.messageId,
      new_content: payload.newContent ?? null,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
    },
  }
}
```

- [ ] **Step 2: Add `editAndRerun` method to `SessionConversationWebSocket` class**

Add after `denyTool` method (around line 283):

```typescript
editAndRerun(payload: { messageId: string; newContent?: string | null; providerId?: string | null; modelId?: string | null }): void {
  if (this.ws && this.ws.readyState === WebSocket.OPEN) {
    this.ws.send(JSON.stringify(buildEditAndRerunMessage(payload)))
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/sessionConversationWebSocket.ts
git commit -m "feat: add editAndRerun to WebSocket client"
```

---

### Task 7: Frontend — Handle `messages.truncated` event in conversationReducer

**Files:**
- Modify: `frontend/src/features/conversation/conversationReducer.ts`

- [ ] **Step 1: Add `applyMessagesTruncated` function and integrate into `applyConversationEvent`**

In `frontend/src/features/conversation/conversationReducer.ts`, add before `applyConversationEvent`:

```typescript
function applyMessagesTruncated(
  state: ConversationState,
  event: ConversationEvent
): ConversationState {
  const p = event.payloadJson
  const deletedTurnIds = (p.deleted_turn_ids as string[]) ?? []
  const deletedTurnIdSet = new Set(deletedTurnIds)

  const survivingTurnOrder = state.turnOrder.filter((id) => !deletedTurnIdSet.has(id))
  const survivingTurnsById: Record<string, ConversationState['turnsById'][string]> = {}
  for (const id of survivingTurnOrder) {
    const turn = state.turnsById[id]
    if (turn) survivingTurnsById[id] = turn
  }

  const survivingMessageOrder = state.messageOrder.filter((id) => {
    const msg = state.messagesById[id]
    return msg && !deletedTurnIdSet.has(msg.turnId)
  })
  const survivingMessagesById: Record<string, ConversationMessage> = {}
  for (const id of survivingMessageOrder) {
    const msg = state.messagesById[id]
    if (msg) survivingMessagesById[id] = msg
  }

  const survivingRunsById: Record<string, ConversationRun> = {}
  for (const [id, run] of Object.entries(state.runsById)) {
    if (!deletedTurnIdSet.has(run.turnId)) {
      survivingRunsById[id] = run
    }
  }

  const session = state.session
    ? { ...state.session, activeTurnId: null }
    : null

  return {
    ...state,
    lastEventSeq: event.seq,
    session,
    turnOrder: survivingTurnOrder,
    turnsById: survivingTurnsById,
    runsById: survivingRunsById,
    messageOrder: survivingMessageOrder,
    messagesById: survivingMessagesById,
  }
}
```

Then in `applyConversationEvent`, add at the beginning of the function body (after the seq check), before the `if (!event.messageId)` check:

```typescript
if (event.eventType === 'messages.truncated') {
  return applyMessagesTruncated(currentState, event)
}
```

Also add `ConversationRun` to the type imports at the top:

```typescript
import type {
  ConversationEvent,
  ConversationLiveMessage,
  ConversationMessage,
  ConversationRun,
  ConversationSnapshot,
  ConversationState,
} from '@/types/conversation'
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/conversation/conversationReducer.ts
git commit -m "feat: handle messages.truncated event in conversation reducer"
```

---

### Task 8: Frontend — Add `editAndRerun` to useConversationRuntime hook

**Files:**
- Modify: `frontend/src/hooks/useConversationRuntime.ts`

- [ ] **Step 1: Add `editAndRerun` callback**

In `frontend/src/hooks/useConversationRuntime.ts`, add after `denyTool` callback (around line 281):

```typescript
const editAndRerun = useCallback((payload: {
  messageId: string
  newContent?: string | null
  providerId?: string | null
  modelId?: string | null
}) => {
  if (!wsRef.current?.isConnected()) {
    return
  }

  wsRef.current.editAndRerun(payload)
}, [])
```

Add it to the return object:

```typescript
return {
  connectionStatus,
  isCancelling,
  retryInfo,
  startTurn,
  cancelRun,
  approveTool,
  denyTool,
  editAndRerun,
  resetConversationRuntime,
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useConversationRuntime.ts
git commit -m "feat: add editAndRerun to useConversationRuntime hook"
```

---

### Task 9: Frontend — Create MessageActions component

**Files:**
- Create: `frontend/src/components/workspace/MessageActions.tsx`

- [ ] **Step 1: Create MessageActions component**

Create `frontend/src/components/workspace/MessageActions.tsx`:

```tsx
import { useState } from 'react'
import { Copy, Pencil, RefreshCw } from 'lucide-react'

interface MessageActionsProps {
  messageId: string
  contentText: string
  messageType: 'user_message' | 'assistant_message'
  onEdit: (messageId: string, contentText: string) => void
  onRegenerate: (messageId: string) => void
}

export function MessageActions({
  messageId,
  contentText,
  messageType,
  onEdit,
  onRegenerate,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(contentText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      console.error('复制失败')
    }
  }

  const buttonBaseClass =
    'inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors text-content-muted hover:bg-surface-tertiary hover:text-content-secondary'

  return (
    <div className="mt-1 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        type="button"
        className={buttonBaseClass}
        title={copied ? '已复制' : '复制'}
        onClick={handleCopy}
      >
        <Copy className="h-4 w-4" />
      </button>
      {messageType === 'user_message' && (
        <button
          type="button"
          className={buttonBaseClass}
          title="编辑"
          onClick={() => onEdit(messageId, contentText)}
        >
          <Pencil className="h-4 w-4" />
        </button>
      )}
      {messageType === 'assistant_message' && (
        <button
          type="button"
          className={buttonBaseClass}
          title="重新生成"
          onClick={() => onRegenerate(messageId)}
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/MessageActions.tsx
git commit -m "feat: create MessageActions component with Copy, Edit, Regenerate"
```

---

### Task 10: Frontend — Integrate MessageActions into WorkspaceTranscript

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`
- Modify: `frontend/src/hooks/useCurrentSessionViewModel.ts`

- [ ] **Step 1: Add MessageActions import and props to WorkspaceTranscript**

In `frontend/src/components/workspace/WorkspaceTranscript.tsx`:

Add import:

```typescript
import { MessageActions } from './MessageActions'
```

Add to `WorkspaceTranscriptProps`:

```typescript
onEditMessage?: (messageId: string, contentText: string) => void
onRegenerateMessage?: (messageId: string) => void
```

Destructure in component params:

```typescript
onEditMessage,
onRegenerateMessage,
```

- [ ] **Step 2: Wrap user_message with group hover + MessageActions**

Replace the user_message rendering block (lines 160-175) with:

```tsx
if (message.messageType === 'user_message') {
  const isEditing = editingMessageId === message.id
  return (
    <SlideIn key={message.id} direction="up">
      <div className="mb-8 flex flex-col items-end group">
        {isEditing ? (
          <div className="max-w-[720px] w-full">
            <textarea
              className="w-full rounded-2xl bg-surface-tertiary border border-edge px-5 py-4 text-[15px] leading-7 text-content-secondary resize-y min-h-[60px] focus:outline-none focus:border-edge-active"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              autoFocus
            />
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-edge px-3 py-1.5 text-xs text-content-muted hover:text-content-secondary hover:border-edge-active transition-colors"
                onClick={() => setEditingMessageId(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-lg bg-surface-tertiary px-3 py-1.5 text-xs text-content-secondary hover:bg-surface-active transition-colors"
                onClick={() => {
                  if (editContent.trim()) {
                    onEditMessage?.(message.id, editContent.trim())
                    setEditingMessageId(null)
                  }
                }}
              >
                发送
              </button>
            </div>
          </div>
        ) : (
          <motion.div
            className="max-w-[720px] rounded-2xl bg-surface-tertiary px-5 py-4 text-[15px] leading-7 text-content-secondary"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            {message.contentText}
          </motion.div>
        )}
        {!isEditing && onEditMessage && (
          <MessageActions
            messageId={message.id}
            contentText={message.contentText}
            messageType="user_message"
            onEdit={(msgId, content) => {
              setEditingMessageId(msgId)
              setEditContent(content)
            }}
            onRegenerate={onRegenerateMessage ?? (() => {})}
          />
        )}
      </div>
    </SlideIn>
  )
}
```

- [ ] **Step 3: Add edit state variables at component top**

After the destructured props, add:

```typescript
const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
const [editContent, setEditContent] = useState('')
```

- [ ] **Step 4: Wrap assistant_message with group hover + MessageActions**

Replace the assistant_message rendering block (lines 191-226) with:

```tsx
if (message.messageType === 'assistant_message') {
  const isFailed = message.streamState === 'failed'
  const isCancelled = message.streamState === 'cancelled'
  const run = message.runId != null ? runsById?.[message.runId] : undefined
  const errorCode = (message.payloadJson?.error_code as string | undefined) ?? run?.errorCode ?? undefined
  const errorMessage = (message.payloadJson?.error_message as string | undefined) ?? run?.errorMessage ?? undefined

  return (
    <SlideIn key={message.id} direction="up">
      <div className="mb-10 group">
        {message.contentText && (
          <MarkdownRenderer
            content={message.contentText}
            variant="plain"
            isStreaming={message.streamState === 'streaming'}
            className={transcriptClassName}
          />
        )}
        {(isFailed || isCancelled) && (errorMessage || errorCode) && (
          <div className={`mt-3 rounded-lg border px-4 py-3 text-sm ${
            isFailed
              ? 'border-status-error-border bg-status-error-soft text-status-error'
              : 'border-status-warning-border bg-status-warning-soft text-status-warning'
          }`}>
            <div className="flex items-center gap-2 font-medium">
              {isFailed ? '执行失败' : '执行已取消'}
            </div>
            {errorMessage && (
              <div className="mt-1 text-xs opacity-80">{errorMessage}</div>
            )}
          </div>
        )}
        {message.streamState === 'completed' && onRegenerateMessage && (
          <MessageActions
            messageId={message.id}
            contentText={message.contentText}
            messageType="assistant_message"
            onEdit={onEditMessage ?? (() => {})}
            onRegenerate={onRegenerateMessage}
          />
        )}
      </div>
    </SlideIn>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workspace/WorkspaceTranscript.tsx
git commit -m "feat: integrate MessageActions into WorkspaceTranscript"
```

---

### Task 11: Frontend — Wire edit/regenerate through view model to runtime

**Files:**
- Modify: `frontend/src/hooks/useCurrentSessionViewModel.ts`

- [ ] **Step 1: Read current file**

Read `frontend/src/hooks/useCurrentSessionViewModel.ts` to understand current structure.

- [ ] **Step 2: Add edit/regenerate callbacks**

In `useCurrentSessionViewModel.ts`, the hook already has access to `useConversationRuntime`. Add `editAndRerun` from the runtime's return value and create `handleEditMessage` and `handleRegenerateMessage` callbacks.

Add to the hook's logic:

```typescript
const handleEditMessage = useCallback((messageId: string, newContent: string) => {
  if (!currentSession) return
  editAndRerun({
    messageId,
    newContent,
    providerId: selection.providerId,
    modelId: selection.modelId,
  })
}, [currentSession, editAndRerun, selection.providerId, selection.modelId])

const handleRegenerateMessage = useCallback((messageId: string) => {
  if (!currentSession) return
  if (!window.confirm('重新生成回复？此消息之后的对话内容将被清除，AI 将基于当前上下文重新生成回复。')) return
  editAndRerun({
    messageId,
    newContent: null,
    providerId: selection.providerId,
    modelId: selection.modelId,
  })
}, [currentSession, editAndRerun, selection.providerId, selection.modelId])
```

Pass these through the returned view model:

```typescript
onEditMessage: handleEditMessage,
onRegenerateMessage: handleRegenerateMessage,
```

- [ ] **Step 3: Thread props through AgentWorkspace → WorkspaceTranscript**

Read `frontend/src/pages/AgentWorkspace.tsx` to understand prop threading, then add `onEditMessage` and `onRegenerateMessage` to `WorkspaceTranscript`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useCurrentSessionViewModel.ts frontend/src/pages/AgentWorkspace.tsx frontend/src/components/workspace/WorkspaceTranscript.tsx
git commit -m "feat: wire edit/regenerate callbacks through view model to runtime"
```

---

### Task 12: Backend test — ConversationService truncate and edit_and_rerun

**Files:**
- Create: `backend/tests/test_conversation/test_edit_and_rerun.py`

- [ ] **Step 1: Write tests for `edit_and_rerun`**

Create `backend/tests/test_conversation/test_edit_and_rerun.py` with tests covering:
- Edit a user message truncates subsequent turns and starts new turn with new content
- Regenerate an assistant message keeps preceding user message content
- Cannot edit when there is an active running turn
- Truncating the first message works correctly

- [ ] **Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_conversation/test_edit_and_rerun.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_conversation/test_edit_and_rerun.py
git commit -m "test: add tests for edit_and_rerun conversation service"
```

---

### Task 13: Frontend test — conversationReducer messages.truncated handling

**Files:**
- Modify: `frontend/src/features/conversation/conversationReducer.test.ts`

- [ ] **Step 1: Read existing test file**

Read `frontend/src/features/conversation/conversationReducer.test.ts` to understand test patterns.

- [ ] **Step 2: Add test for `messages.truncated` event handling**

Add test that verifies:
- A `messages.truncated` event removes the specified turns and their messages/runs from state
- The `activeTurnId` is cleared if the active turn was truncated
- `lastEventSeq` is updated

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx vitest run src/features/conversation/conversationReducer.test.ts
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/conversation/conversationReducer.test.ts
git commit -m "test: add reducer test for messages.truncated event"
```

---

### Task 14: Integration verification

- [ ] **Step 1: Run backend tests**

```bash
cd backend && python -m pytest -v
```

Expected: All PASS

- [ ] **Step 2: Run frontend tests**

```bash
cd frontend && npx vitest run
```

Expected: All PASS

- [ ] **Step 3: Run frontend type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 4: Manual smoke test**

Start dev server, open a conversation, hover on messages to verify action buttons appear, test copy/edit/regenerate flows.

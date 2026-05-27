# Conversation Message Edit & Regenerate Design

**Date:** 2026-05-27
**Status:** Approved

## Summary

Add the ability to edit a previously sent user message or regenerate an assistant response within a conversation. When editing, all messages after the edited message are truncated and the conversation continues from the edit point with a new LLM run. This is an overwrite (non-branching) model similar to ChatGPT.

## Requirements

1. **Edit user message**: Click edit on a user message → inline textarea with current content → modify and send → truncate all subsequent turns/messages → start a new turn with the edited content
2. **Copy text**: Copy the raw text of any message to clipboard
3. **Copy to edit box**: Copy a user message's content into the input textarea for modification and re-send
4. **Regenerate assistant response**: Click regenerate on an assistant message → confirmation dialog → truncate all messages after the assistant's turn → re-run with the same user message that preceded it
5. **UI**: GPT-style action buttons appear below messages on hover, using lucide-react icons (Copy, Pencil, RefreshCw)

## Architecture: Atomic `edit_and_rerun` API

A single WebSocket message type `conversation:edit_and_rerun` performs truncation + new turn creation atomically.

### Backend

#### New EventType

Add `messages.truncated` to `EventType` enum. This event signals that all turns/messages after a given point have been deleted.

#### New method: `ConversationService.truncate_after_message(session_id, message_id)`

1. Find the target message and its turn
2. Find all turns with `turn_index >= target_turn.turn_index` (for user message edits) or `turn_index > target_turn.turn_index` (for assistant regenerates — keep the current turn's user message)
3. Delete all messages, runs, turns, conversation_events, and message_search_documents for those turns
4. Clear `session.active_turn_id` if the active turn was deleted
5. Append `messages.truncated` event with the surviving state
6. Return the surviving state (remaining turns, last user message content if applicable)

#### New method: `ConversationService.edit_and_rerun(session_id, message_id, new_content, provider_id, model_id, workspace_ref)`

1. Acquire session write lock
2. Validate no active run is currently executing (cancel if needed)
3. Find the target message
4. If target is a user_message:
   - Truncate all turns with `turn_index >= target_turn.turn_index`
   - Start a new turn with `new_content`
5. If target is an assistant_message:
   - Truncate all turns with `turn_index > target_turn.turn_index`
   - Truncate the current turn's messages after the user_message (keep the user message)
   - Start a new run in the same turn structure (new turn with same user message content)
6. Return `StartTurnResult` for the new run

#### New method: `AgentService.edit_and_rerun(project_id, session_id, message_id, new_content, provider_id, model_id)`

1. If there's an active run, cancel it first
2. Call `conversation_service.edit_and_rerun(...)`
3. Broadcast truncation events
4. Schedule the new turn execution

#### WebSocket handler addition

Add `conversation:edit_and_rerun` message type in `websocket.py`:
- Required fields: `message_id`, `new_content` (for user message edits; empty string for regenerate)
- Optional fields: `provider_id`, `model_id`

### Frontend

#### New component: `MessageActions`

A row of icon buttons that appears below a message on hover:
- **User messages**: Copy (clipboard) + Edit (inline edit mode)
- **Assistant messages**: Copy (clipboard) + Regenerate (with confirmation)

Icons: `Copy`, `Pencil`, `RefreshCw` from lucide-react

#### User message edit flow

1. Hover → show Copy + Edit buttons below message
2. Click Edit → message bubble becomes textarea with current content + Cancel/Send buttons
3. Click Send → call `edit_and_rerun` via WebSocket with `message_id` and `new_content`
4. Frontend reducer handles `messages.truncated` event by removing truncated messages/turns from state
5. New turn events arrive normally via existing event handling

#### Assistant message regenerate flow

1. Hover → show Copy + Regenerate buttons below message
2. Click Regenerate → show confirmation dialog
3. Confirm → call `edit_and_rerun` via WebSocket with `message_id` and empty `new_content` (signals regenerate)
4. Backend truncates after the assistant's turn and re-runs with the preceding user message

#### Copy flow

1. Click Copy → `navigator.clipboard.writeText(message.contentText)` + brief "Copied" toast

#### Copy to edit box flow

1. Click Edit → same as edit flow but the textarea is pre-filled
2. Actually, for user messages, "Edit" and "Copy to edit box" are the same action — clicking Edit opens inline textarea

#### ConversationReducer update

Handle `messages.truncated` event:
- Remove all messages with `turnMessageIndex` beyond the truncation point
- Remove all turns after the truncation point
- Remove associated runs
- Clear `activeTurnId` if needed

## Data Model Changes

### Backend EventType addition

```python
class EventType(str, Enum):
    # ... existing ...
    MESSAGES_TRUNCATED = "messages.truncated"
```

### No database schema changes

Truncation physically deletes rows from `turns`, `runs`, `messages`, `conversation_events`, `message_search_documents` tables. No new columns or tables needed.

## Edge Cases

1. **Active run exists**: Cancel the active run before truncating
2. **Edit the first message in a conversation**: Truncates all turns, starts fresh
3. **Regenerate a response mid-conversation**: Truncates turns after the assistant's turn, keeps the user message
4. **Network failure during truncate**: The session write lock + atomic DB transaction ensures consistency
5. **Concurrent edit attempts**: Session write lock serializes operations

## Files to Modify

### Backend
- `backend/app/models/conversation.py` — add `MESSAGES_TRUNCATED` EventType
- `backend/app/services/conversation_service.py` — add `truncate_after_message()`, `edit_and_rerun()`
- `backend/app/services/agent_service.py` — add `edit_and_rerun()` method
- `backend/app/api/routes/websocket.py` — handle `conversation:edit_and_rerun`
- `backend/app/storage/repositories/turn_repo.py` — add `delete_by_session_after_index()`
- `backend/app/storage/repositories/message_repo.py` — add `delete_by_turn_ids()`
- `backend/app/storage/repositories/run_repo.py` — add `delete_by_turn_ids()`
- `backend/app/storage/repositories/conversation_event_repo.py` — add `delete_by_turn_ids()`
- `backend/app/storage/repositories/message_search_document_repo.py` — add `delete_by_turn_ids()`

### Frontend
- `frontend/src/types/conversation.ts` — add `messages_truncated` event type handling
- `frontend/src/features/conversation/conversationReducer.ts` — handle `messages.truncated` event
- `frontend/src/components/workspace/WorkspaceTranscript.tsx` — add `MessageActions` component integration, edit mode state
- `frontend/src/services/sessionConversationWebSocket.ts` — add `sendEditAndRerun()` method
- `frontend/src/hooks/useConversationRuntime.ts` — expose `editAndRerun` callback
- `frontend/src/hooks/useSendMessage.ts` — integrate with edit flow (optional, may stay in runtime hook)

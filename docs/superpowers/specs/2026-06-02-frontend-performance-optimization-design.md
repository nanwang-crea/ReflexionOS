# Frontend Performance Optimization & UI Polish

**Date:** 2026-06-02
**Scope:** WorkspaceTranscript rendering pipeline, conversation data flow, UI animations

## Problem

When a conversation reaches 50-200 messages, the UI becomes noticeably laggy. Root causes:

1. **No virtualization** — all messages rendered in DOM, unbounded growth
2. **Full re-render on streaming delta** — `useConversationData` selects entire `conversation` object; any change triggers re-computation of full `messages` array
3. **framer-motion on every item** — `AnimatePresence` + `SlideIn` on all transcript items creates large motion tree
4. **MarkdownRenderer re-parses every render** — no caching of parse results for completed messages
5. **No message-level memoization** — `WorkspaceTranscript` map callback produces inline JSX, no `React.memo` boundaries

## Design

### 1. Virtual Scrolling (react-virtuoso)

Replace the full-render `<AnimatePresence>` block in `WorkspaceTranscript` with `Virtuoso`:

- Only render visible items + overscan buffer
- `react-virtuoso` handles dynamic item heights (markdown content, collapsible sections)
- `followOutput="smooth"` replaces manual auto-scroll logic (`shouldAutoScrollRef`, `scrollIntoView`)
- `startReached` callback triggers history pagination (section 2)

Item components render without `SlideIn`/framer-motion entry animation. Only the very last newly-added item gets a simple CSS transition (0.15s opacity + translateY).

### 2. Paginated History Loading

#### 2.1 Backend API Change

Modify existing `GET /api/sessions/:id/conversation` to accept pagination parameters:

- `before_seq: int | null` — return messages with `seq < before_seq`; omit for initial load
- `limit: int` — default 20
- Response includes `has_more: bool` and `oldest_seq: int | null`

Initial load: no `before_seq`, returns latest 20 messages + `has_more` + `oldest_seq`.

#### 2.2 Frontend Loading Logic

- `useConversationRuntime` initial snapshot request uses `limit=20` (no `before_seq`)
- Virtuoso `startReached` triggers `loadMore()`: requests `before_seq=oldestSeq`
- New messages prepended to store via `prependMessages` action
- Loading indicator shown at top during fetch

#### 2.3 Store Adaptation

- `conversationReducer` adds `prependMessages` action: inserts messages at head of `messageOrder`, merges into `messagesById`
- WebSocket resync (on reconnect) still fetches full snapshot — existing behavior unchanged

### 3. Message Component Memoization

Extract inline JSX from `WorkspaceTranscript` map into independent `React.memo` components:

| Component | Props | Notes |
|---|---|---|
| `UserMessageItem` | messageId, contentText, isEditing, editContent, onEdit, onRegenerate | User bubble + edit textarea + MessageActions |
| `AssistantMessageItem` | messageId, isStreaming, runsById, onEdit, onRegenerate, onDetailClick | ThinkingBlock + WorkingNoteBlock + MarkdownRenderer + error display + MessageActions |
| `SystemNoticeItem` | messageId, contentText | Warning-style notice box |
| `ToolGroupItem` | status, details, onApprovalAction, onDetailClick | Wraps existing memoized ActionReceipt |

Each component receives stable prop references:
- Primitive props (messageId, contentText) are stable by nature
- Callback props use `useCallback` from parent
- Object props (details, runsById) use `useMemo` where possible

### 4. Streaming Message Independent Subscription

Current problem: `useConversationData` selects entire `conversation` → `messages` array recomputes on every streaming delta → all items re-render.

Optimization:

- Add `useStreamingMessage(sessionId)` selector — selects only the last message where `streamState === 'streaming'`
- `AssistantMessageItem` for completed messages reads from `messagesById[messageId]` directly (stable reference, no re-render on streaming updates)
- Only the last `AssistantMessageItem` (the streaming one) subscribes via `useStreamingMessage` — isolated re-renders
- `messages` array still computed for Virtuoso item count / keys, but its reference changes don't cascade into per-item re-renders (memo boundaries prevent it)

### 5. MarkdownRenderer Caching

- For completed messages (`isStreaming === false`): `useMemo` caches the `ReactMarkdown` output, keyed on `content` string
- For streaming messages: re-render every time (content is changing)
- Remove `motion.div` wrapper (`initial/animate/transition`) — pure rendering, no entry animation needed
- Apply CSS `opacity` transition on the outer div for smooth appearance (0.15s)

### 6. Animation Streamlining

**Remove framer-motion from:**
- `SlideIn` wrapper on all transcript items → delete `SlideIn` usage in transcript
- `MarkdownRenderer` outer `motion.div` → plain `div`
- User message `motion.div` → plain `div`
- Streaming cursor `motion.span` → CSS `@keyframes blink`
- `RunningIndicator` 3x `motion.div` bars → CSS `@keyframes` animation

**Retain framer-motion for:**
- `ActionReceipt` expand/collapse (user interaction feedback)
- `PlanProgress` enter/exit (important visual cue)
- Scroll-to-bottom button enter/exit
- `ChatInput` focus scale animation

**New message entry animation:**
- Only the latest added item gets a CSS transition: `opacity: 0 → 1`, `transform: translateY(8px) → none`, 0.15s
- Implemented via a CSS class added to the newest item, removed after transition ends

### 7. UI Polish

#### 7.1 Message Spacing

Unify spacing across message types:
- All items: `mb-6` (currently user=mb-8, assistant=mb-10, tool=mb-8 — inconsistent)

#### 7.2 MessageActions Hover

- Add `transition-opacity duration-150` for smoother fade-in on hover
- Increase hover detection area slightly with padding

#### 7.3 Code Block Enhancements

- Add copy button (top-right corner) to fenced code blocks
- Display language label extracted from `className` `language-xxx`

#### 7.4 Streaming Cursor

Replace `motion.span` with:
```css
@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
```

### 8. Auto-Scroll Refactor

Replace manual auto-scroll with Virtuoso's built-in `followOutput`:
- `followOutput="smooth"` when user is at bottom
- `followOutput=false` when user has scrolled up
- Virtuoso's `isAtBottom` state replaces `shouldFollowTranscript` + `isAtBottom` state
- Remove `messagesEndRef` scroll-into-view pattern
- Keep scroll-to-bottom floating button (framer-motion animated)

## Implementation Order

1. Install `react-virtuoso`, refactor `WorkspaceTranscript` to use Virtuoso
2. Extract memoized item components (`UserMessageItem`, `AssistantMessageItem`, `SystemNoticeItem`, `ToolGroupItem`)
3. Add `useStreamingMessage` selector, wire into `AssistantMessageItem`
4. Optimize `MarkdownRenderer` caching, remove `motion.div`
5. Replace all `SlideIn` + `AnimatePresence` with CSS transitions in transcript
6. Replace `RunningIndicator` motion bars with CSS keyframes
7. Replace streaming cursor with CSS keyframes
8. Backend: add pagination params to existing conversation API
9. Frontend: `prependMessages` reducer action + `useConversationRuntime` pagination
10. UI polish: spacing, MessageActions hover, code block copy button + language label

## Files Changed

| File | Change |
|---|---|
| `frontend/src/components/workspace/WorkspaceTranscript.tsx` | Major: Virtuoso, memoized items, remove AnimatePresence/SlideIn |
| `frontend/src/components/chat/MarkdownRenderer.tsx` | Caching, remove motion.div, code block copy + lang label |
| `frontend/src/components/workspace/RunningIndicator.tsx` | CSS keyframes replace motion.div |
| `frontend/src/components/workspace/MessageActions.tsx` | Hover transition polish |
| `frontend/src/hooks/useConversationData.ts` | Add useStreamingMessage selector |
| `frontend/src/hooks/useCurrentSessionViewModel.ts` | Simplify auto-scroll (Virtuoso followOutput) |
| `frontend/src/hooks/useConversationRuntime.ts` | Pagination: initial limit=20, loadMore |
| `frontend/src/features/conversation/conversationReducer.ts` | Add prependMessages action |
| `frontend/src/features/conversation/conversationApi.ts` | Add before_seq/limit params |
| `frontend/src/components/animations/SlideIn.tsx` | Keep (used elsewhere) but remove from transcript |
| Backend conversation API handler | Add before_seq/limit params, has_more/oldest_seq in response |
| `frontend/package.json` | Add react-virtuoso dependency |

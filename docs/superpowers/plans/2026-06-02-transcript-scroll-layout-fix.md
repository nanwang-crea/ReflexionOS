# Transcript Scroll & Layout Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two user-facing bugs: (1) sending a message or cancelling causes the transcript to jump to the top, and (2) streaming responses jitter as `atBottom` state oscillates. Also fix the transcript content being partially hidden behind the chat input area.

**Architecture:** Replace the current `followOutput` + `isAtBottom` latch hack with the Virtuoso-recommended pattern: use `followOutput="smooth"` unconditionally when streaming (the component handles bottom-detection internally), and use `alignToBottom` so short conversations anchor to the bottom. Remove the `streamFollowLockedRef` / `prevIsRunningRef` patch entirely. Add bottom padding inside the Virtuoso scroller so the last message is never hidden behind the fixed-position chat input.

**Tech Stack:** react-virtuoso ^4.18.7, React 18, TypeScript

---

## Problem Analysis

### Root Cause 1: Jump-to-top on send/cancel

The current `followOutput` is a function that returns `false` when `atBottom === false`. During send, the Virtuoso component may briefly report `atBottom = false` (layout recalculation, input focus change, etc.), causing `followOutput` to return `false` and the list stops following. When the data changes (new messages arrive), Virtuoso doesn't scroll to the new content.

The previous patch added `streamFollowLockedRef` which latches `followOutput` to `'smooth'` when `isRunning` transitions to true. But this breaks when:
- User clicks **cancel** → `isRunning` becomes `false` → latch resets → `followOutput` returns `false` for `atBottom = false` → list jumps away from bottom
- The `prevIsRunningRef` triggers a `scrollToIndex` on `isRunning` transition, which can race with Virtuoso's own scroll management

### Root Cause 2: Streaming jitter

Same underlying issue: `followOutput` depends on `atBottom` which oscillates during streaming because content height changes cause Virtuoso to recalculate bottom proximity on each frame. The latch was an attempt to fix this, but it's a band-aid.

### Root Cause 3: Input遮挡 (content hidden behind chat input)

The `AgentWorkspace` layout uses a flex column:
```
┌─────────────────┐
│ WorkspaceHeader  │
├─────────────────┤
│ WorkspaceTranscript (flex-1) │  ← Virtuoso fills this
├─────────────────┤
│ ChatInput (not flex)         │  ← fixed height, outside Virtuoso
└─────────────────┘
```

The Virtuoso scroller fills the `flex-1` area correctly, but the Footer component (PlanProgress, RunningIndicator) and the last message's bottom padding (32px) are not enough to account for the space the external ChatInput takes. Virtuoso doesn't know about the external input bar, so its `atBottom` calculation thinks the bottom of the scroller IS the bottom, but visually the ChatInput overlaps the last ~80px of content.

## Correct Architecture (from Virtuoso docs & ChatGPT/Claude patterns)

The Virtuoso Message List examples and API docs recommend:

1. **`followOutput` as a simple value or state-driven function** — NOT depending on the volatile `atBottom` callback parameter for the streaming case. When streaming, return `'smooth'` always. When not streaming, return `'smooth'` only if the user hasn't scrolled up.

2. **`alignToBottom`** — Set this to `true` so that when content is shorter than the viewport, it's anchored to the bottom (like ChatGPT).

3. **Scroll state managed by user intent, not by Virtuoso callbacks** — Track "user chose to scroll away" as a separate boolean, set only by explicit scroll-up gestures, not by Virtuoso's measurement jitter.

4. **Bottom padding inside scroller** — The internal `paddingBottom` in the Scroller component should be large enough so the last item's bottom edge clears the external ChatInput bar.

---

### Task 1: Remove the streamFollowLockedRef patch

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx:114-115,205-241,245-251`

- [ ] **Step 1: Remove `streamFollowLockedRef` and `prevIsRunningRef` declarations**

Remove these two lines:
```tsx
const streamFollowLockedRef = useRef(false)
const prevIsRunningRef = useRef(isRunning)
```

- [ ] **Step 2: Remove the `isRunning` transition effect**

Remove the entire `useEffect` block (lines 227-241):
```tsx
useEffect(() => {
  if (!isRunning) {
    streamFollowLockedRef.current = false
  }
  const wasRunning = prevIsRunningRef.current
  prevIsRunningRef.current = isRunning
  if (isRunning && !wasRunning) {
    streamFollowLockedRef.current = true
    virtuosoRef.current?.scrollToIndex({
      index: lastItemIndex,
      align: 'end',
      behavior: 'smooth',
    })
  }
}, [isRunning, lastItemIndex])
```

- [ ] **Step 3: Remove latch logic from `handleAtBottomStateChange`**

Remove the latch-related lines from `handleAtBottomStateChange`:
```tsx
if (streamFollowLockedRef.current && !atBottom) {
  streamFollowLockedRef.current = false
}
```

- [ ] **Step 4: Run tests to verify removal doesn't break anything unexpected**

Run: `cd frontend && npx vitest run src/components/workspace/ToolTraceCard.test.tsx --reporter=verbose`
Expected: Some tests may fail (the `followOutput` test expectations), but no runtime errors.

---

### Task 2: Implement user-intent-based scroll following

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`

The key insight: track "user deliberately scrolled up" separately from Virtuoso's `atBottom` measurement. Once the user deliberately scrolls up during streaming, stop following. Once they scroll back down (or send a new message), resume following.

- [ ] **Step 1: Add `userScrolledAwayRef` ref**

Replace the removed refs with:
```tsx
const userScrolledAwayRef = useRef(false)
```

- [ ] **Step 2: Rewrite `followOutput`**

Replace the current `followOutput` callback with:
```tsx
const followOutput = useCallback((_atBottom: boolean) => {
  if (userScrolledAwayRef.current) return false
  return isRunning ? 'smooth' : 'smooth'
}, [isRunning])
```

This simplifies to: if user hasn't scrolled away, always follow with smooth scroll. The `isRunning` check is kept in the dependency array for future differentiation (e.g., `'auto'` vs `'smooth'`) but the behavior is the same for now.

Actually, even simpler — since the return value is the same in both branches:
```tsx
const followOutput = useCallback((_atBottom: boolean) => {
  if (userScrolledAwayRef.current) return false
  return 'smooth'
}, [])
```

This is the correct pattern from Virtuoso docs: the function form of `followOutput` receives `atBottom` but we ignore it (it's too volatile). Instead we use our own intent tracking.

- [ ] **Step 3: Rewrite `handleAtBottomStateChange` to track user intent**

```tsx
const handleAtBottomStateChange = useCallback((atBottom: boolean) => {
  isAtBottomRef.current = atBottom
  setIsAtBottom(atBottom)
  if (!atBottom) {
    userScrolledAwayRef.current = true
  } else {
    userScrolledAwayRef.current = false
  }
}, [])
```

Wait — this has the same problem as before. `atBottom` oscillates during streaming, which would set `userScrolledAwayRef` to `true` on a jitter.

The real fix: `atBottom` jitter only happens when `isRunning` is true (streaming content changes height). So:

```tsx
const handleAtBottomStateChange = useCallback((atBottom: boolean) => {
  isAtBottomRef.current = atBottom
  setIsAtBottom(atBottom)
  if (!isRunning && !atBottom) {
    userScrolledAwayRef.current = true
  }
  if (atBottom) {
    userScrolledAwayRef.current = false
  }
}, [isRunning])
```

Logic:
- When **not streaming**: if `atBottom` becomes `false`, the user genuinely scrolled up → set `userScrolledAway = true`
- When **streaming**: ignore `atBottom = false` jitter — don't set `userScrolledAway`
- When `atBottom` becomes `true` (any time): always clear `userScrolledAway` — user is back at bottom

- [ ] **Step 4: Add `alignToBottom` prop to Virtuoso**

Add the `alignToBottom` prop so short conversations anchor to the bottom of the viewport (like ChatGPT/Claude):
```tsx
<Virtuoso
  alignToBottom
  ...
/>
```

---

### Task 3: Fix bottom padding to prevent content being hidden by ChatInput

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx:348-365`

The internal scroller frame has `paddingBottom: 32` which is not enough to clear the external ChatInput bar (~80-100px).

- [ ] **Step 1: Increase `paddingBottom` in the scroller inner frame**

Change `paddingBottom: 32` to `paddingBottom: 96` in the `data-transcript-frame` div inside the Scroller component:

```tsx
<div
  data-transcript-frame
  style={{
    maxWidth: 1280,
    marginLeft: 'auto',
    marginRight: 'auto',
    width: '100%',
    boxSizing: 'border-box',
    paddingLeft: 32,
    paddingRight: 32,
    paddingTop: 32,
    paddingBottom: 96,
  }}
>
```

This ensures the last message has enough bottom clearance that it's fully visible above the ChatInput area.

---

### Task 4: Force scroll-to-bottom on new user message

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`

Even with `followOutput`, when a user sends a message they should always be taken to the bottom. This handles the case where `userScrolledAway` was true (user was reading older messages) and then sends a new message.

- [ ] **Step 1: Add effect to detect new user messages and scroll to bottom**

Detect when a new user message appears (the last message is a user_message and it's different from the previous last). When this happens, clear `userScrolledAway` and scroll to bottom:

```tsx
const prevLastUserMessageIdRef = useRef<string | null>(null)

useEffect(() => {
  const lastMessage = filteredMessages[filteredMessages.length - 1]
  const lastUserMsgId = lastMessage?.messageType === 'user_message' ? lastMessage.id : null
  if (lastUserMsgId && lastUserMsgId !== prevLastUserMessageIdRef.current) {
    userScrolledAwayRef.current = false
    virtuosoRef.current?.scrollToIndex({
      index: lastItemIndex,
      align: 'end',
      behavior: 'smooth',
    })
  }
  prevLastUserMessageIdRef.current = lastUserMsgId
}, [filteredMessages, lastItemIndex])
```

---

### Task 5: Update tests

**Files:**
- Modify: `frontend/src/components/workspace/ToolTraceCard.test.tsx:788-790`

The existing test expects `followOutput` to be a function that:
- Returns `'smooth'` when called with `atBottom = true` and `isRunning = true` → now returns `'smooth'` regardless
- Returns `false` when called with `atBottom = false` → now returns `'smooth'` when `userScrolledAway` is false, or `false` when it's true

- [ ] **Step 1: Update the `followOutput` test expectations**

The test at line ~788 checks:
```tsx
expect(typeof latestVirtuosoProps?.followOutput).toBe('function')
expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(true)).toBe('smooth')
expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(false)).toBe(false)
```

Update to:
```tsx
expect(typeof latestVirtuosoProps?.followOutput).toBe('function')
expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(true)).toBe('smooth')
expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(false)).toBe('smooth')
```

Since `followOutput` no longer uses `atBottom` to decide — it uses `userScrolledAwayRef` instead. In a test environment where no scrolling has happened, `userScrolledAwayRef` is `false`, so both calls return `'smooth'`.

- [ ] **Step 2: Add test for `alignToBottom` prop**

Find the Virtuoso props assertions and add:
```tsx
expect(latestVirtuosoProps?.alignToBottom).toBe(true)
```

- [ ] **Step 3: Run all tests**

Run: `cd frontend && npx vitest run --reporter=verbose`
Expected: All 148 tests pass.

---

### Task 6: Verify the complete fix manually

- [ ] **Step 1: Run dev server**

Run: `cd frontend && pnpm dev`

- [ ] **Step 2: Manual test checklist**

1. Send a message → transcript should scroll to bottom smoothly, not jump to top
2. While streaming (assistant replying) → no jitter, smooth scroll following
3. Click cancel during streaming → transcript stays at current position, does NOT jump to top
4. Scroll up during streaming → streaming content should NOT auto-scroll (user chose to read earlier messages)
5. Scroll back to bottom during streaming → auto-scroll resumes
6. Scroll up, then send new message → should scroll to bottom
7. Short conversation (few messages) → messages anchored at bottom of viewport, not at top
8. Last message should be fully visible, not hidden behind ChatInput

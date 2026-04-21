# Frontend Cleanup And Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining dead frontend session/history compatibility code and further split overburdened frontend view-model/sidebar/overlay modules while preserving the current round assembly behavior.

**Architecture:** Keep the current session/history ownership intact and refine structure in place. Delete obsolete compatibility paths first, then split `useCurrentSessionViewModel`, `WorkspaceSidebar`, and lightweight `useExecutionOverlay` helpers into focused units with stable responsibilities.

**Tech Stack:** React, TypeScript, Zustand, Vitest, Vite

---

## File Map

### Frontend files to create

- `frontend/src/hooks/useSessionData.ts`
- `frontend/src/hooks/useSessionSelection.ts`
- `frontend/src/hooks/useSessionRenderItems.ts`
- `frontend/src/components/layout/useSidebarProjectActions.ts`
- `frontend/src/components/layout/useSidebarSessionActions.ts`
- `frontend/src/components/layout/useSidebarFilteredProjects.ts`
- `frontend/src/hooks/useSessionData.test.ts` if split logic needs direct coverage
- `frontend/src/components/layout/useSidebarFilteredProjects.test.ts` if filtering logic is extracted into pure helpers

### Frontend files to modify

- `frontend/src/services/apiClient.ts`
- `frontend/src/features/workspace/messageFlow.ts`
- `frontend/src/features/workspace/messageFlow.test.ts`
- `frontend/src/hooks/useCurrentSessionViewModel.ts`
- `frontend/src/components/layout/WorkspaceSidebar.tsx`
- `frontend/src/hooks/useExecutionOverlay.ts`
- `frontend/src/hooks/executionOverlayState.test.ts`
- `frontend/src/App.cleanup.test.ts`
- `frontend/src/features/projects/projectLoader.test.ts`
- `frontend/src/features/sessions/sessionActions.test.ts`

---

### Task 1: Remove Obsolete Session History And Local Session Helpers

**Files:**
- Modify: `frontend/src/services/apiClient.ts`
- Modify: `frontend/src/features/workspace/messageFlow.ts`
- Modify: `frontend/src/features/workspace/messageFlow.test.ts`
- Modify: `frontend/src/App.cleanup.test.ts`

- [ ] **Step 1: Write or tighten failing cleanup assertions**

```ts
it('does not expose legacy session history fetch from agentApi', async () => {
  const source = await fs.promises.readFile('src/services/apiClient.ts', 'utf8')
  expect(source.includes('getSessionHistory')).toBe(false)
})

it('removes obsolete local session helpers from messageFlow', async () => {
  const source = await fs.promises.readFile('src/features/workspace/messageFlow.ts', 'utf8')
  expect(source.includes('deriveSessionTitle')).toBe(false)
  expect(source.includes('trimRecentRounds')).toBe(false)
})
```

- [ ] **Step 2: Run cleanup-focused tests and verify failure**

Run: `npm test -- App.cleanup.test.ts messageFlow.test.ts`
Expected: FAIL because the legacy helper exports still exist.

- [ ] **Step 3: Delete obsolete helper and API paths**

```ts
export const agentApi = {
  cancel: (executionId: string) =>
    apiClient.post(`/api/agent/cancel/${executionId}`),
}
```

```ts
export function mergeRenderItems(
  persistedItems: WorkspaceChatItem[],
  overlayItems: WorkspaceChatItem[]
) {
  return [...persistedItems, ...overlayItems]
}

export function flattenRoundsToItems(rounds: WorkspaceSessionRound[]) {
  return rounds.flatMap((round) => round.items)
}
```

- [ ] **Step 4: Run cleanup-focused tests and verify pass**

Run: `npm test -- App.cleanup.test.ts messageFlow.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit cleanup foundation**

```bash
git add frontend/src/services/apiClient.ts frontend/src/features/workspace/messageFlow.ts frontend/src/features/workspace/messageFlow.test.ts frontend/src/App.cleanup.test.ts
git commit -m "refactor: remove legacy session helper paths"
```

---

### Task 2: Split Session View Model Into Data, Selection, And Render Layers

**Files:**
- Create: `frontend/src/hooks/useSessionData.ts`
- Create: `frontend/src/hooks/useSessionSelection.ts`
- Create: `frontend/src/hooks/useSessionRenderItems.ts`
- Modify: `frontend/src/hooks/useCurrentSessionViewModel.ts`
- Test: `frontend/src/hooks/useSendMessage.test.ts`
- Test: `frontend/src/App.cleanup.test.ts`

- [ ] **Step 1: Write or tighten tests around session summary/history selection behavior**

```ts
it('clears stale currentSessionId when it does not exist in sessionStore', async () => {
  // arrange stale selection and expect setCurrentSessionId(null)
})

it('derives render items from persisted rounds plus active round plus overlay items', () => {
  const items = mergeRenderItems([...flattenRoundsToItems(persistedRounds), ...activeRoundItems], overlayItems)
  expect(items).toHaveLength(3)
})
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- App.cleanup.test.ts useSendMessage.test.ts`
Expected: FAIL or require new coverage because the responsibilities are still concentrated in one hook.

- [ ] **Step 3: Extract session data loading and stale-id handling**

```ts
export function useSessionData() {
  // currentProject/currentSessionId/session summaries/history loading
}
```

- [ ] **Step 4: Extract provider/model selection and preference update logic**

```ts
export function useSessionSelection(options: {
  currentSessionId: string | null
  preferredProviderId?: string | null
  preferredModelId?: string | null
  updateSessionPreferences: (...) => Promise<unknown>
}) {
  // resolveSessionSelection + handlers
}
```

- [ ] **Step 5: Extract render-item assembly and scroll behavior**

```ts
export function useSessionRenderItems(options: {
  persistedRounds: WorkspaceSessionRound[]
  activeRoundItems: WorkspaceChatItem[]
  overlayItems: WorkspaceChatItem[]
}) {
  // flattenRoundsToItems + mergeRenderItems + messagesEndRef
}
```

- [ ] **Step 6: Reduce useCurrentSessionViewModel to a composition layer**

```ts
export function useCurrentSessionViewModel(options: ...) {
  const data = useSessionData()
  const selection = useSessionSelection(...)
  const render = useSessionRenderItems(...)
  return { ... }
}
```

- [ ] **Step 7: Run focused tests and verify pass**

Run: `npm test -- App.cleanup.test.ts useSendMessage.test.ts`
Expected: PASS and build remains green.

- [ ] **Step 8: Commit view-model split**

```bash
git add frontend/src/hooks/useSessionData.ts frontend/src/hooks/useSessionSelection.ts frontend/src/hooks/useSessionRenderItems.ts frontend/src/hooks/useCurrentSessionViewModel.ts frontend/src/App.cleanup.test.ts frontend/src/hooks/useSendMessage.test.ts
git commit -m "refactor: split session view model responsibilities"
```

---

### Task 3: Split WorkspaceSidebar Filtering And Actions

**Files:**
- Create: `frontend/src/components/layout/useSidebarProjectActions.ts`
- Create: `frontend/src/components/layout/useSidebarSessionActions.ts`
- Create: `frontend/src/components/layout/useSidebarFilteredProjects.ts`
- Modify: `frontend/src/components/layout/WorkspaceSidebar.tsx`
- Modify: `frontend/src/features/projects/projectLoader.test.ts`
- Modify: `frontend/src/features/sessions/sessionActions.test.ts`

- [ ] **Step 1: Write or tighten failing tests around sidebar project/session actions**

```ts
it('filters and sorts project sessions by updatedAt descending', () => {
  const result = getFilteredProjects(...)
  expect(result[0].sessions[0].updatedAt).toBe('2026-04-20T02:00:00Z')
})

it('delegates session creation through sessionActions', async () => {
  await createSidebarSession(...)
  expect(createSessionMock).toHaveBeenCalled()
})
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- projectLoader.test.ts sessionActions.test.ts`
Expected: FAIL or require updated assertions because the logic still lives inside WorkspaceSidebar.

- [ ] **Step 3: Extract project CRUD logic**

```ts
export function useSidebarProjectActions() {
  return {
    handleCreateProject,
    handleDeleteProject,
    handleSelectDirectory,
  }
}
```

- [ ] **Step 4: Extract session CRUD logic**

```ts
export function useSidebarSessionActions() {
  return {
    handleCreateSession,
    handleRenameSession,
    handleDeleteSession,
  }
}
```

- [ ] **Step 5: Extract filtering and sorting logic**

```ts
export function useSidebarFilteredProjects(...) {
  return filteredProjects
}
```

- [ ] **Step 6: Reduce WorkspaceSidebar to composition and binding**

```tsx
export function WorkspaceSidebar() {
  const filteredProjects = useSidebarFilteredProjects(...)
  const projectActions = useSidebarProjectActions(...)
  const sessionActions = useSidebarSessionActions(...)
  return (...) 
}
```

- [ ] **Step 7: Run focused tests and verify pass**

Run: `npm test -- projectLoader.test.ts sessionActions.test.ts App.cleanup.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit sidebar split**

```bash
git add frontend/src/components/layout/useSidebarProjectActions.ts frontend/src/components/layout/useSidebarSessionActions.ts frontend/src/components/layout/useSidebarFilteredProjects.ts frontend/src/components/layout/WorkspaceSidebar.tsx frontend/src/features/projects/projectLoader.test.ts frontend/src/features/sessions/sessionActions.test.ts
git commit -m "refactor: split workspace sidebar responsibilities"
```

---

### Task 4: Extract Lightweight Execution Overlay Helpers

**Files:**
- Modify: `frontend/src/hooks/useExecutionOverlay.ts`
- Modify: `frontend/src/hooks/executionOverlayState.test.ts`
- Create if needed: `frontend/src/hooks/executionOverlayHelpers.ts`

- [ ] **Step 1: Write or tighten failing tests around extracted helper behavior**

```ts
it('finalizes receipt items with failed detail status when forced failed', () => {
  const next = finalizeReceiptItem(receiptItem, 'failed')
  expect(next.details[0].status).toBe('failed')
})
```

- [ ] **Step 2: Run focused overlay tests and verify failure or missing coverage**

Run: `npm test -- executionOverlayState.test.ts useExecutionWebSocket.test.ts`
Expected: FAIL or require new coverage because helper seams are not explicit yet.

- [ ] **Step 3: Extract isolated overlay helper logic**

```ts
export function createOverlayItemId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function resolveReceiptStatus(...) {
  ...
}
```

- [ ] **Step 4: Reduce useExecutionOverlay by delegating to extracted helpers**

```ts
import { createOverlayItemId, ... } from './executionOverlayHelpers'
```

- [ ] **Step 5: Run focused overlay tests and verify pass**

Run: `npm test -- executionOverlayState.test.ts useExecutionWebSocket.test.ts useExecutionDraftRound.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit overlay helper extraction**

```bash
git add frontend/src/hooks/useExecutionOverlay.ts frontend/src/hooks/executionOverlayState.test.ts frontend/src/hooks/executionOverlayHelpers.ts
git commit -m "refactor: extract execution overlay helpers"
```

---

### Task 5: Final Verification For Cleanup Round

**Files:**
- Test: `frontend/src/App.cleanup.test.ts`
- Test: `frontend/src/features/workspace/messageFlow.test.ts`
- Test: `frontend/src/features/projects/projectLoader.test.ts`
- Test: `frontend/src/features/sessions/sessionActions.test.ts`
- Test: `frontend/src/hooks/useExecutionDraftRound.test.ts`
- Test: `frontend/src/hooks/useExecutionWebSocket.test.ts`
- Test: `frontend/src/hooks/useSendMessage.test.ts`

- [ ] **Step 1: Run final focused frontend verification suite**

Run: `npm test -- App.cleanup.test.ts messageFlow.test.ts projectLoader.test.ts sessionActions.test.ts useExecutionDraftRound.test.ts useExecutionWebSocket.test.ts useSendMessage.test.ts`
Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run: `npm run build`
Expected: PASS with no TypeScript errors.

- [ ] **Step 3: Grep for removed legacy symbols**

Run: `rg "getSessionHistory|deriveSessionTitle|trimRecentRounds" frontend/src`
Expected: No runtime references for removed legacy symbols.

- [ ] **Step 4: Commit final cleanup-round verification if needed**

```bash
git add .
git commit -m "test: verify frontend cleanup and decomposition"
```

---

## Self-Review Checklist

- Dead code removal: covered by Task 1.
- useCurrentSessionViewModel split: covered by Task 2.
- WorkspaceSidebar split: covered by Task 3.
- Lightweight useExecutionOverlay cleanup: covered by Task 4.
- Validation and regression checks: covered by Task 5.

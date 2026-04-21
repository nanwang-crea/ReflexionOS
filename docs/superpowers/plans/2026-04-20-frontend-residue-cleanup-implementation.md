# Frontend Residue Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining duplicate session-preference/session-loading paths, narrow redundant frontend APIs, and clean invalid intermediate docs while preserving the current session/history behavior and round assembly.

**Architecture:** Keep the current stable session/history design intact, but collapse double-write and double-load paths into one clear owner each. Preload project lists plus session summaries at startup, keep session history lazy, make send-time preference persistence the single write path, simplify draft-round APIs, and remove stale intermediate docs that are no longer execution references.

**Tech Stack:** React, TypeScript, Zustand, Vitest, Vite, Markdown docs

---

## File Map

### Frontend files to modify

- `frontend/src/features/projects/projectLoader.ts`
- `frontend/src/features/projects/projectLoader.test.ts`
- `frontend/src/features/sessions/sessionLoader.ts`
- `frontend/src/features/sessions/sessionLoader.test.ts`
- `frontend/src/hooks/useSessionData.ts`
- `frontend/src/hooks/useSessionData.test.ts`
- `frontend/src/hooks/useSessionSelection.ts`
- `frontend/src/hooks/useSessionSelection.test.ts`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/hooks/useSendMessage.test.ts`
- `frontend/src/hooks/useExecutionDraftRound.ts`
- `frontend/src/hooks/useExecutionDraftRound.test.ts`
- `frontend/src/hooks/useExecutionWebSocket.ts`
- `frontend/src/hooks/useExecutionWebSocket.test.ts`
- `frontend/src/hooks/useExecutionRuntime.ts`
- `frontend/src/hooks/useSessionActions.ts`
- `frontend/src/features/sessions/sessionActions.ts`
- `frontend/src/features/sessions/sessionActions.test.ts`

### Docs to evaluate for deletion

- `docs/superpowers/plans/2026-04-20-explicit-transcript-field-and-doc-alignment.md`
- `docs/superpowers/plans/2026-04-20-full-session-history-replay.md`
- `docs/superpowers/plans/2026-04-20-workspace-message-streaming-and-storage.md`

### Docs to keep

- `docs/superpowers/specs/2026-04-20-session-transcript-boundary-design.md`
- `docs/superpowers/specs/2026-04-20-frontend-cleanup-and-decomposition-design.md`
- `docs/superpowers/specs/2026-04-20-frontend-residue-cleanup-design.md`

---

### Task 1: Collapse Session Preference Persistence To Send-Time Only

**Files:**
- Modify: `frontend/src/hooks/useSessionSelection.ts`
- Modify: `frontend/src/hooks/useSessionSelection.test.ts`
- Modify: `frontend/src/hooks/useSendMessage.ts`
- Modify: `frontend/src/hooks/useSendMessage.test.ts`

- [ ] **Step 1: Write failing tests for single-path preference persistence**

```ts
it('does not persist session preferences during selection changes', async () => {
  const updateSessionPreferences = vi.fn()
  const { shouldPersistSelectionPreferences } = await import('./useSessionSelection')
  expect(shouldPersistSelectionPreferences(...)).toBe(false)
  expect(updateSessionPreferences).not.toHaveBeenCalled()
})

it('persists preferences from useSendMessage before sending when session exists', async () => {
  const updateSessionPreferences = vi.fn().mockResolvedValue(undefined)
  await sendMessage(...)
  expect(updateSessionPreferences).toHaveBeenCalledWith('session-1', {
    preferredProviderId: 'provider-a',
    preferredModelId: 'model-a',
  })
})
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- useSessionSelection.test.ts useSendMessage.test.ts`
Expected: FAIL because selection changes still auto-persist today.

- [ ] **Step 3: Remove automatic persistence from useSessionSelection**

```ts
// useSessionSelection should only update local selection state.
// Remove calls to updateSessionPreferences from:
// - initial resolution effect
// - handleProviderChange
// - handleModelChange
```

- [ ] **Step 4: Keep send-time writeback in useSendMessage as the single owner**

```ts
if (targetSession.id) {
  await dependencies.updateSessionPreferences(targetSession.id, {
    preferredProviderId: dependencies.selection.providerId,
    preferredModelId: dependencies.selection.modelId,
  })
}
```

- [ ] **Step 5: Run focused tests and verify pass**

Run: `npm test -- useSessionSelection.test.ts useSendMessage.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit session preference path cleanup**

```bash
git add frontend/src/hooks/useSessionSelection.ts frontend/src/hooks/useSessionSelection.test.ts frontend/src/hooks/useSendMessage.ts frontend/src/hooks/useSendMessage.test.ts
git commit -m "refactor: persist session preferences only on send"
```

---

### Task 2: Keep Project Summary Preload But Remove Current-Project Reload Duplication

**Files:**
- Modify: `frontend/src/features/projects/projectLoader.ts`
- Modify: `frontend/src/features/projects/projectLoader.test.ts`
- Modify: `frontend/src/hooks/useSessionData.ts`
- Modify: `frontend/src/hooks/useSessionData.test.ts`
- Modify: `frontend/src/features/sessions/sessionActions.ts`
- Modify: `frontend/src/features/sessions/sessionActions.test.ts`

- [ ] **Step 1: Write failing tests for load ownership**

```ts
it('preloads project sessions during project loading', async () => {
  await ensureProjectsLoaded()
  expect(ensureProjectSessionsLoaded).toHaveBeenCalledWith('project-1')
})

it('does not reload current project session summaries inside useSessionData', async () => {
  await runSessionDataEffect(...)
  expect(ensureProjectSessionsLoaded).not.toHaveBeenCalled()
})

it('refreshes only the affected project session summaries after rename', async () => {
  await renameSession(...)
  expect(refreshProjectSessions).toHaveBeenCalledWith('project-1')
  expect(refreshProjectSessions).not.toHaveBeenCalledWith('project-2')
})
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- projectLoader.test.ts useSessionData.test.ts sessionActions.test.ts`
Expected: FAIL because the current project is still reloading session summaries in useSessionData or action refresh semantics are incomplete.

- [ ] **Step 3: Keep startup preload in projectLoader**

```ts
const projects = response.data
setProjects(projects)
await Promise.all(projects.map((project) => ensureProjectSessionsLoaded(project.id)))
```

- [ ] **Step 4: Remove current-project session summary reload from useSessionData**

```ts
// delete the effect that calls ensureProjectSessionsLoaded(currentProject.id)
// keep only current session history loading and stale-id handling
```

- [ ] **Step 5: Ensure sessionActions refresh only the current project summaries**

```ts
export async function renameSession(...) {
  await sessionApi.updateSession(...)
  await ensureProjectSessionsLoaded(projectId)
}
```

- [ ] **Step 6: Run focused tests and verify pass**

Run: `npm test -- projectLoader.test.ts useSessionData.test.ts sessionActions.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit summary-load ownership cleanup**

```bash
git add frontend/src/features/projects/projectLoader.ts frontend/src/features/projects/projectLoader.test.ts frontend/src/hooks/useSessionData.ts frontend/src/hooks/useSessionData.test.ts frontend/src/features/sessions/sessionActions.ts frontend/src/features/sessions/sessionActions.test.ts
git commit -m "refactor: separate session summary preload from history loading"
```

---

### Task 3: Split History Ensure Vs Refresh Semantics

**Files:**
- Modify: `frontend/src/features/sessions/sessionLoader.ts`
- Modify: `frontend/src/features/sessions/sessionLoader.test.ts`
- Modify: `frontend/src/hooks/useExecutionWebSocket.ts`
- Modify: `frontend/src/hooks/useExecutionWebSocket.test.ts`
- Modify: `frontend/src/hooks/useExecutionRuntime.ts`

- [ ] **Step 1: Write failing tests for explicit refresh path**

```ts
it('refreshSessionHistory always re-fetches and replaces cached rounds', async () => {
  await refreshSessionHistory('session-1')
  expect(sessionApi.getSessionHistory).toHaveBeenCalledTimes(1)
})

it('execution complete path uses refreshSessionHistory rather than ensureSessionHistoryLoaded', async () => {
  await runExecutionCompleteSequence(...)
  expect(refreshSessionHistory).toHaveBeenCalledWith('session-1')
})
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- sessionLoader.test.ts useExecutionWebSocket.test.ts`
Expected: FAIL because only `ensureSessionHistoryLoaded` exists today.

- [ ] **Step 3: Add explicit refreshSessionHistory helper**

```ts
export async function refreshSessionHistory(sessionId: string) {
  const response = await sessionApi.getSessionHistory(sessionId)
  useSessionStore.getState().setSessionHistory(
    sessionId,
    response.data.rounds.map(normalizeRoundFromApi)
  )
}
```

- [ ] **Step 4: Keep ensureSessionHistoryLoaded as first-load semantic only**

```ts
export async function ensureSessionHistoryLoaded(sessionId: string) {
  if (useSessionStore.getState().historyBySessionId[sessionId]) return
  await refreshSessionHistory(sessionId)
}
```

- [ ] **Step 5: Switch runtime/websocket completion and failure paths to refreshSessionHistory**

```ts
await draftRound.refreshSessionHistory(sessionId)
```

- [ ] **Step 6: Run focused tests and verify pass**

Run: `npm test -- sessionLoader.test.ts useExecutionWebSocket.test.ts useExecutionDraftRound.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit history semantic split**

```bash
git add frontend/src/features/sessions/sessionLoader.ts frontend/src/features/sessions/sessionLoader.test.ts frontend/src/hooks/useExecutionWebSocket.ts frontend/src/hooks/useExecutionWebSocket.test.ts frontend/src/hooks/useExecutionRuntime.ts
git commit -m "refactor: split ensure and refresh session history"
```

---

### Task 4: Remove Redundant Draft-Round APIs And Narrow Session Actions Surface

**Files:**
- Modify: `frontend/src/hooks/useExecutionDraftRound.ts`
- Modify: `frontend/src/hooks/useExecutionDraftRound.test.ts`
- Modify: `frontend/src/hooks/useExecutionWebSocket.ts`
- Modify: `frontend/src/hooks/useExecutionRuntime.ts`
- Modify: `frontend/src/hooks/useSessionActions.ts`

- [ ] **Step 1: Write failing tests for narrowed APIs**

```ts
it('exposes a single clearDraftRound API instead of redundant terminal aliases', async () => {
  const mod = await import('./useExecutionDraftRound')
  expect('clearDraftRound' in mod.createDraftRoundStore()).toBe(true)
  expect('completeDraftRound' in mod.createDraftRoundStore()).toBe(false)
})

it('does not expose a public generic updateSession action', async () => {
  const actions = useSessionActions()
  expect('updateSession' in actions).toBe(false)
})
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- useExecutionDraftRound.test.ts App.cleanup.test.ts`
Expected: FAIL because the redundant APIs still exist.

- [ ] **Step 3: Remove complete/cancel/fail draft aliases and keep clearDraftRound**

```ts
return {
  draftRoundItems,
  appendItems,
  clearDraftRound,
  startDraftRound,
}
```

- [ ] **Step 4: Update callers to express semantics at the call site**

```ts
draftRound.clearDraftRound()
```

- [ ] **Step 5: Narrow useSessionActions public surface**

```ts
return {
  createSession,
  updateSessionPreferences,
  loadSessionHistory,
}
```

- [ ] **Step 6: Run focused tests and verify pass**

Run: `npm test -- useExecutionDraftRound.test.ts useExecutionWebSocket.test.ts App.cleanup.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit API narrowing**

```bash
git add frontend/src/hooks/useExecutionDraftRound.ts frontend/src/hooks/useExecutionDraftRound.test.ts frontend/src/hooks/useExecutionWebSocket.ts frontend/src/hooks/useExecutionRuntime.ts frontend/src/hooks/useSessionActions.ts frontend/src/App.cleanup.test.ts
git commit -m "refactor: narrow draft round and session action apis"
```

---

### Task 5: Clean Invalid Intermediate Docs And Verify The Round

**Files:**
- Delete if confirmed invalid: `docs/superpowers/plans/2026-04-20-explicit-transcript-field-and-doc-alignment.md`
- Delete if confirmed invalid: `docs/superpowers/plans/2026-04-20-full-session-history-replay.md`
- Delete if confirmed invalid: `docs/superpowers/plans/2026-04-20-workspace-message-streaming-and-storage.md`
- Keep: overall session/frontend design specs

- [ ] **Step 1: Verify candidate docs are superseded and not the active execution reference**

```text
1. Read each candidate plan/spec.
2. Confirm its content is superseded by current implementation and newer docs.
3. Confirm it is not the active design reference for any remaining work.
```

- [ ] **Step 2: Delete only the confirmed-invalid intermediate docs**

```text
Delete the validated stale docs.
Keep the high-level design docs listed in the spec.
```

- [ ] **Step 3: Run final focused frontend verification**

Run: `npm test -- App.cleanup.test.ts useSessionData.test.ts useSessionSelection.test.ts useSendMessage.test.ts useExecutionDraftRound.test.ts useExecutionWebSocket.test.ts projectLoader.test.ts sessionActions.test.ts sessionLoader.test.ts`
Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run: `npm run build`
Expected: PASS.

- [ ] **Step 5: Grep for removed residue paths**

Run: `grep` for these runtime residues:
- automatic preference persistence in `useSessionSelection`
- `completeDraftRound|cancelDraftRound|failDraftRound`
- public `updateSession` exposure in `useSessionActions`

Expected: removed or narrowed per spec.

- [ ] **Step 6: Commit final residue cleanup verification if needed**

```bash
git add .
git commit -m "test: verify frontend residue cleanup"
```

---

## Self-Review Checklist

- Single-path session preference persistence: covered by Task 1.
- Startup preload vs current-session history boundary: covered by Task 2.
- Ensure vs refresh history semantics: covered by Task 3.
- Draft-round/session-action API narrowing: covered by Task 4.
- Intermediate doc cleanup and final verification: covered by Task 5.

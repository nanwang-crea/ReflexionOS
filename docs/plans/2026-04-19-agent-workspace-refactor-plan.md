# Agent Workspace Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `AgentWorkspace.tsx` to a thin page component while preserving the current interaction model and fixing the highest-risk state, configuration, and legacy-code issues around chat execution.

**Architecture:** Move persistent chat/session data into the workspace store, move execution-time behavior into focused runtime modules, and have the page render from a single derived view model. Keep the current UI structure and behavior stable while introducing small pure helpers that are easy to test and reason about.

**Tech Stack:** React 18, TypeScript, Zustand, Vite, Axios, WebSocket, Vitest

---

## File Structure

### New files

- `frontend/src/services/runtimeConfig.ts`
  - Resolve HTTP and WebSocket base URLs from the current runtime.
- `frontend/src/services/__tests__/runtimeConfig.test.ts`
  - Verify config resolution behavior.
- `frontend/src/features/workspace/sessionSelection.ts`
  - Resolve provider/model selection for the active session.
- `frontend/src/features/workspace/messageFlow.ts`
  - Pure helpers for session title derivation, render item merging, and receipt/message transitions.
- `frontend/src/features/workspace/types.ts`
  - Shared types for runtime overlays and render items.
- `frontend/src/features/workspace/__tests__/sessionSelection.test.ts`
  - Verify provider/model fallback behavior.
- `frontend/src/features/workspace/__tests__/messageFlow.test.ts`
  - Verify transcript derivation and message flow edge cases.
- `frontend/src/components/workspace/WorkspaceHeader.tsx`
  - Header UI for current session/project and connection state.
- `frontend/src/components/workspace/WorkspaceTranscript.tsx`
  - Message list rendering only.
- `frontend/src/hooks/useExecutionRuntime.ts`
  - Own execution lifecycle, websocket wiring, and runtime overlay state.

### Modified files

- `frontend/package.json`
  - Add test tooling and scripts.
- `frontend/vite.config.ts`
  - Share runtime config expectations and test config.
- `frontend/src/services/apiClient.ts`
  - Use shared runtime config instead of hard-coded host.
- `frontend/src/services/websocketClient.ts`
  - Use shared runtime config and emit connection lifecycle events with typed payloads.
- `frontend/src/pages/AgentWorkspace.tsx`
  - Shrink to container logic and composition.
- `frontend/src/stores/workspaceStore.ts`
  - Add a targeted session removal helper if needed and keep persistent items as the single persisted transcript source.
- `frontend/src/pages/ProjectsPage.tsx`
  - Remove orphan sessions when deleting a project.
- `frontend/src/App.tsx`
  - Remove legacy routes when the new path is confirmed.

### Deleted files

- `frontend/src/pages/AgentWorkspace.tsx.backup`
- `frontend/src/pages/AgentPage.tsx`
- `frontend/src/stores/agentStore.ts`

---

### Task 1: Add Minimal Test Infrastructure

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/services/__tests__/runtimeConfig.test.ts`

- [ ] Add `vitest` and a `test` script to the frontend package.
- [ ] Configure Vitest in `vite.config.ts` with a jsdom environment.
- [ ] Write a failing test for runtime config resolution.
- [ ] Run the test to confirm it fails for the missing module.
- [ ] Add the runtime config module with the minimal implementation.
- [ ] Re-run the test and confirm it passes.

### Task 2: Unify Runtime Configuration

**Files:**
- Create: `frontend/src/services/runtimeConfig.ts`
- Modify: `frontend/src/services/apiClient.ts`
- Modify: `frontend/src/services/websocketClient.ts`

- [ ] Replace hard-coded HTTP and WebSocket hosts with shared runtime config helpers.
- [ ] Add typed connection lifecycle events to the websocket client.
- [ ] Keep the current execution message protocol unchanged.
- [ ] Verify the frontend still builds after the config change.

### Task 3: Extract Pure Workspace Logic

**Files:**
- Create: `frontend/src/features/workspace/types.ts`
- Create: `frontend/src/features/workspace/sessionSelection.ts`
- Create: `frontend/src/features/workspace/messageFlow.ts`
- Create: `frontend/src/features/workspace/__tests__/sessionSelection.test.ts`
- Create: `frontend/src/features/workspace/__tests__/messageFlow.test.ts`

- [ ] Write failing tests for provider/model fallback and transcript derivation.
- [ ] Add pure helpers for selection resolution and message flow updates.
- [ ] Re-run tests until the helpers pass.
- [ ] Keep helper inputs/outputs small and serializable.

### Task 4: Extract Execution Runtime and Thin the Page

**Files:**
- Create: `frontend/src/hooks/useExecutionRuntime.ts`
- Create: `frontend/src/components/workspace/WorkspaceHeader.tsx`
- Create: `frontend/src/components/workspace/WorkspaceTranscript.tsx`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] Move websocket lifecycle, execution handlers, and transient overlay state into the hook.
- [ ] Keep persistent session items in the workspace store as the stored source of truth.
- [ ] Derive render items from persisted session items plus runtime overlay state.
- [ ] Replace inline transcript/header JSX in `AgentWorkspace.tsx` with focused presentational components.
- [ ] Confirm current interaction behavior remains unchanged: send, cancel, reset, provider/model selection, and session switching.

### Task 5: Clean Legacy Paths and Data Consistency Issues

**Files:**
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/pages/AgentWorkspace.tsx.backup`
- Delete: `frontend/src/pages/AgentPage.tsx`
- Delete: `frontend/src/stores/agentStore.ts`

- [ ] Fix project deletion so related sessions are removed too.
- [ ] Remove unused legacy page/store files once references are gone.
- [ ] Keep only the active chat workspace route.

### Task 6: Verify the Refactor

**Files:**
- No additional files expected

- [ ] Run `pnpm -C frontend test`
- [ ] Run `pnpm -C frontend build`
- [ ] Run `git diff --stat` and sanity-check the scope.
- [ ] Document any remaining follow-up risks if the refactor leaves non-blocking debt behind.

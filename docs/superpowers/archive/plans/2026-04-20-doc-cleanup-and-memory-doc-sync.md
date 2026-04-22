# Doc Cleanup And Memory Doc Sync Implementation Plan

> Archived historical execution plan. Kept for reference only; not an active execution source.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove clearly invalid intermediate docs and update the memory-related high-level docs so they accurately reflect the current session/history architecture and implementation status.

**Architecture:** Treat the current session/history implementation as the stable baseline. Delete only superseded execution plans, keep high-level design docs, and rewrite memory docs to clearly separate what is already implemented (session/history/archive foundations) from what remains unimplemented (structured memory layers, candidate promotion, durable memory).

**Tech Stack:** Markdown docs

---

## File Map

### Docs to modify

- `docs/superpowers/specs/2026-04-20-memory-phase-1-grounding-spec.md`
- `docs/superpowers/plans/2026-04-19-memory-architecture-记忆整体架构.md`
- `docs/superpowers/specs/2026-04-20-workspace-message-streaming-and-storage-design.md`

### Docs to delete if confirmed superseded

- `docs/superpowers/plans/2026-04-20-session-transcript-boundary-implementation.md`
- `docs/superpowers/plans/2026-04-20-frontend-cleanup-and-decomposition-implementation.md`
- `docs/superpowers/plans/2026-04-20-frontend-residue-cleanup-implementation.md`

### Docs to keep

- `docs/superpowers/specs/2026-04-20-session-transcript-boundary-design.md`
- `docs/superpowers/specs/2026-04-20-frontend-cleanup-and-decomposition-design.md`
- `docs/superpowers/specs/2026-04-20-frontend-residue-cleanup-design.md`

---

### Task 1: Clean Invalid Intermediate Plan Docs

**Files:**
- Delete if confirmed superseded: `docs/superpowers/plans/2026-04-20-session-transcript-boundary-implementation.md`
- Delete if confirmed superseded: `docs/superpowers/plans/2026-04-20-frontend-cleanup-and-decomposition-implementation.md`
- Delete if confirmed superseded: `docs/superpowers/plans/2026-04-20-frontend-residue-cleanup-implementation.md`

- [ ] **Step 1: Verify each candidate plan is already completed and superseded by code plus retained design docs**
- [ ] **Step 2: Delete only the confirmed-invalid intermediate plans**

### Task 2: Update Memory Phase-1 Grounding Doc To Match Current Reality

**Files:**
- Modify: `docs/superpowers/specs/2026-04-20-memory-phase-1-grounding-spec.md`

- [ ] **Step 1: Rewrite the current-baseline section around the real session/history architecture**
- [ ] **Step 2: Remove outdated statements about workspaceStore/recentRounds/local session truth**
- [ ] **Step 3: Clarify what memory foundations exist today vs what remains unimplemented**

### Task 3: Update Memory Architecture Doc To Distinguish Implemented Base Layer Vs Future Memory Layer

**Files:**
- Modify: `docs/superpowers/plans/2026-04-19-memory-architecture-记忆整体架构.md`

- [ ] **Step 1: Add a clear “already implemented base layer” framing**
- [ ] **Step 2: Clarify that candidate/durable memory/structured active workspace are future layers, not current implementation**
- [ ] **Step 3: Keep the long-term memory direction intact while removing any accidental implication that it is already built**

### Task 4: Sync Workspace Message/Storage Design Doc With Current Session/History Reality

**Files:**
- Modify: `docs/superpowers/specs/2026-04-20-workspace-message-streaming-and-storage-design.md`

- [ ] **Step 1: Remove stale wording around recentRounds/local session truth**
- [ ] **Step 2: Clarify that backend session/history is now the source of truth**
- [ ] **Step 3: Keep the document scoped to workspace streaming/storage, not full memory implementation**

### Task 5: Final Review

**Files:**
- Verify only

- [ ] **Step 1: Read the updated docs for contradiction checks**
- [ ] **Step 2: Confirm retained high-level design docs are still present**
- [ ] **Step 3: Confirm deleted docs are only intermediate execution plans**

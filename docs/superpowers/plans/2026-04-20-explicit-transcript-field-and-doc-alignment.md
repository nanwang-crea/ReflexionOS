# Explicit Transcript Field And Doc Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic `Execution.metadata` transcript handoff with an explicit transcript field and update the memory/workspace docs so they match the current codebase reality.

**Architecture:** The backend execution model now exposes transcript replay data through a dedicated `transcript_items` field instead of a generic metadata bag. Documentation is updated in parallel so the memory baseline doc and workspace message design doc describe the current backend transcript archive, frontend recent-round caching, and remaining memory gaps accurately.

**Tech Stack:** Python, Pydantic, FastAPI, SQLAlchemy, TypeScript, Markdown

---

### Task 1: Replace generic metadata transcript handoff with explicit transcript_items

**Files:**
- Modify: `backend/app/models/execution.py`
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/app/services/agent_service.py`
- Modify: `backend/tests/test_execution/test_rapid_loop.py`

- [ ] Write failing test references against `result.transcript_items`
- [ ] Run backend tests to see `Execution` missing explicit field
- [ ] Add `transcript_items` to `Execution`
- [ ] Update runtime and service code to write/read `transcript_items`
- [ ] Re-run backend tests

### Task 2: Refresh docs so code reality and landing docs match

**Files:**
- Modify: `docs/superpowers/specs/2026-04-20-memory-phase-1-grounding-spec.md`
- Modify: `docs/superpowers/specs/2026-04-20-workspace-message-streaming-and-storage-design.md`

- [ ] Update memory grounding doc to reflect transcript archive and recentRounds reality
- [ ] Update workspace message design doc to distinguish implemented vs remaining work
- [ ] Self-review docs for contradictions and stale future-tense claims

### Task 3: Verify alignment end-to-end

**Files:**
- Verify only

- [ ] Run: `pnpm test`
- [ ] Run: `pnpm build`
- [ ] Run: `PYTHONPATH=. pytest tests/test_storage/test_repositories.py tests/test_execution/test_rapid_loop.py tests/test_services/test_agent_service.py -q`

# Build/Plan Dual Mode + Explore Tool Design

## Summary

Add Build/Plan dual agent mode and an Explore search aggregation tool to ReflexionOS. Plan mode is read-only and produces plan files in `.reflexion/plans/`. Build mode is the existing full-access mode. The two modes are fully decoupled — Plan's output is just a project file, Build reads it naturally if needed.

## AgentMode

```python
class AgentMode(str, Enum):
    BUILD = "build"
    PLAN = "plan"
```

## Mode Differences

| Dimension | Build Mode | Plan Mode |
|-----------|-----------|----------|
| **Tools** | All (file/grep/glob/edit/shell/memory/plan/session_recall) | Read-only (file/grep/glob/session_recall/memory/explore) |
| **System prompt** | Current `system` template | Plan-specific prompt: "only analyze, never modify; produce a plan file" |
| **Output** | Code changes + final answer | `.reflexion/plans/YYYY-MM-DD-<slug>.md` |
| **Plan tool** | plan.create/step_done/block/adjust | Not available (replaced by plan file) |
| **Run end state** | Code modifications + final response | Plan file + summary |

## Plan File Format

Stored at `.reflexion/plans/YYYY-MM-DD-<slug>.md`:

```markdown
# <Goal Title>

## Goal
<One sentence description of what to achieve>

## Steps
1. ✅ <Completed step description>
2. ▶ <In-progress step description>
3. ○ <Pending step description>

## Key Findings
- <Finding 1>
- <Finding 2>
```

- `✅` = completed, `▶` = current/in-progress, `○` = pending, `✗` = blocked
- Plan mode writes this via the `edit` tool (write action) — no special tool needed
- The `.reflexion/` directory should be gitignored by default

## Decoupling Plan and Build

Plan and Build are fully independent:

- **Plan mode** produces a file in the project directory. That's it.
- **Build mode** runs exactly as today. No special plan-loading mechanism.
- When switching Plan → Build, the frontend only sends `session:set_mode { mode: "build" }`. No `plan_file` parameter.
- If the user tells Build "execute the plan", the LLM reads the plan file via the `file` tool on its own.
- If the user doesn't mention the plan, Build runs normally.
- Plan file path appears in conversation history (assistant messages), so Build's LLM naturally sees it.

## Explore Tool

A read-only search aggregation tool for both modes.

### Interface

```python
class ExploreTool(BaseTool):
    name = "explore"
    # Input: { query: str, paths?: list[str] }
    # Internal: runs glob + grep + file.read automatically
    # Output: structured summary (file list + key code snippets + locations)
```

### Behavior

- Takes a natural language query and optional path filters
- Internally executes: glob to find candidate files → grep to find relevant lines → file.read for top matches
- Returns a structured text summary, not individual tool call results
- Does NOT consume a main loop step — it's a single tool call that internally aggregates
- Available in both Build and Plan modes
- Useful for "quickly understand a module" scenarios without multiple sequential grep/glob/file calls

## Frontend

### Mode Indicator

- Display mode badge near the chat input: `BUILD` or `PLAN`
- Tab key or click to toggle between modes
- Visual distinction: Plan mode badge in a different color (e.g., blue), Build in default

### Mode Switching Flow

1. User presses Tab or clicks mode indicator
2. If a run is in progress, cancel it first
3. Frontend sends WebSocket message: `session:set_mode { mode: "plan" | "build" }`
4. Backend stores `session.agent_mode`
5. Next user message starts a new run with the selected mode's configuration

### Plan Mode UI

- Tool call results are read-only display only — no edit diffs
- When Plan mode writes a file (the plan), show it as a file creation with preview
- The plan file path is visible in the conversation transcript

### Build Mode UI

- Unchanged from current behavior

## Backend Changes

### New Files

- `backend/app/tools/explore_tool.py` — Read-only search aggregation tool

### Modified Files

- `backend/app/execution/models.py` — Add `AgentMode` enum
- `backend/app/execution/prompt_manager.py` — Add `plan_mode` system prompt template
- `backend/app/execution/runtime_tool_definitions.py` — Plan mode returns only read-only tools + explore
- `backend/app/services/agent_service.py` — Select tool set and prompt based on mode; pass mode to LoopContext
- `backend/app/execution/context_manager.py` — Add `agent_mode` field to `LoopContext`
- `backend/app/models/conversation.py` — Add `agent_mode` field to session model
- `backend/app/api/routes/websocket.py` — Handle `session:set_mode` message

### Frontend Files

- `frontend/src/pages/AgentWorkspace.tsx` — Mode indicator + Tab key handler
- `frontend/src/hooks/useConversationRuntime.ts` — Send `session:set_mode` WebSocket message
- `frontend/src/features/conversation/conversationStore.ts` — Store `currentMode` per session
- `frontend/src/types/conversation.ts` — Add `AgentMode` type

## Data Flow

```
User presses Tab → Plan mode
  → Frontend: ws.send("session:set_mode", { mode: "plan" })
  → Backend: session.agent_mode = "plan"
  → User sends message
  → AgentService: mode=plan → Plan prompt + read-only tools
  → Loop runs: LLM searches code, analyzes, writes .reflexion/plans/xxx.md
  → Frontend: shows plan file creation

User presses Tab → Build mode
  → Frontend: ws.send("session:set_mode", { mode: "build" })
  → Backend: session.agent_mode = "build"
  → User sends message (e.g., "按计划执行")
  → AgentService: mode=build → Build prompt + all tools
  → Loop runs: LLM reads plan file via file tool if needed, executes changes
```

## .reflexion Directory

- Location: `<project_root>/.reflexion/`
- Contains: `plans/` subdirectory with plan markdown files
- Should be gitignored: Add `.reflexion/` to `.gitignore` if not already present
- Plan files are plain markdown, human-readable and editable

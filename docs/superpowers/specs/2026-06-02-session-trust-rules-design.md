# Session Trust Rules Design

## Problem

The current approval system only offers "允许执行" (allow once) and "拒绝" (deny). When an agent runs multiple similar commands (e.g., `npm run dev`, `npm run build`, `npm run test`), the user must approve each one individually. This is tedious.

## Reference

opencode solves this with a 3-button model: "Allow Once" / "Allow for Session" / "Reject". Choosing "Allow for Session" adds wildcard prefix rules (e.g., `npm run *`) to an in-memory store. Subsequent matching commands are auto-approved.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Trust granularity | Command prefix (arity-based) | `npm run dev` → trust `npm run *` — matches opencode behavior |
| Rule persistence | In-memory only (session-scoped) | Rules vanish when session ends; simpler, no DB migration |
| Cascade auto-approval | Yes | When "Allow for Session" is chosen, other pending approvals matching the new rule are auto-approved |
| Wildcard matching | Glob-style (`*` and `?`) | Standard, simple, matches opencode |

## Architecture

### 1. New Component: `SessionTrustStore`

**File:** `backend/app/security/session_trust_store.py`

In-memory, thread-safe store keyed by `session_id`.

```python
class TrustRule(BaseModel):
    permission: str          # "shell"
    pattern: str             # "npm run *"
    action: Literal["allow"] = "allow"

class SessionTrustStore:
    def __init__(self) -> None:
        self._rules: dict[str, list[TrustRule]] = {}  # session_id -> rules
        self._lock = RLock()

    def add_rule(self, session_id: str, rule: TrustRule) -> None
    def get_rules(self, session_id: str) -> list[TrustRule]
    def clear_session(self, session_id: str) -> None
    def matches(self, session_id: str, permission: str, target: str) -> bool
```

`matches()` uses `fnmatch.fnmatch(target, rule.pattern)` for glob matching.

### 2. New Component: `CommandArity`

**File:** `backend/app/security/command_arity.py`

Maps command prefixes to the number of leading tokens that define the "command scope".

```python
COMMAND_ARITY: dict[str, int] = {
    "git": 2,           # git push, git commit, ...
    "npm": 2,           # npm install, npm run, ...
    "npm run": 3,       # npm run dev, npm run build, ...
    "npx": 2,           # npx create-react-app, ...
    "pip": 2,           # pip install, pip uninstall, ...
    "pip install": 2,   # pip install pkg (don't wildcard pkg names)
    "python": 2,        # python script.py, ...
    "node": 2,          # node script.js, ...
    "docker": 2,        # docker build, docker run, ...
    "docker compose": 3, # docker compose up, ...
    "curl": 1,          # curl (entire command)
    "wget": 1,          # wget (entire command)
    "make": 2,          # make target
    "cargo": 2,         # cargo build, cargo test, ...
    "go": 2,            # go build, go test, ...
    "pytest": 1,        # pytest (entire command)
    "vitest": 1,        # vitest (entire command)
    "rm": 2,            # rm file (don't wildcard targets for destructive)
}
DEFAULT_ARITY = 1

def extract_prefix_rule(command: str) -> str:
    """Extract a prefix rule from a command string.
    
    e.g. "npm run dev --flag" -> "npm run *"
         "git push origin main" -> "git push *"
         "curl https://example.com" -> "curl *"
    """
```

### 3. Changes: `ShellTool` — inject `session_id` and `trust_store` via constructor

**File:** `backend/app/tools/shell_tool.py`

`ShellTool` receives `session_id` and `trust_store` at construction time (not from LLM args):

```python
class ShellTool(BaseTool):
    def __init__(
        self,
        security: ShellSecurity,
        path_security: PathSecurity,
        registry: CommandEffectRegistry | None = None,
        sandbox: SandboxProvider | None = None,
        session_id: str | None = None,       # NEW
        trust_store: SessionTrustStore | None = None,  # NEW
    ):
        ...
        self._session_id = session_id
        self.trust_store = trust_store
```

In `execute()`, before calling `self.policy.evaluate()`, check `self.trust_store`:

```python
async def execute(self, args: dict[str, Any]) -> ToolResult:
    command = args.get("command")
    # ... existing validation ...

    approved_decision_data = args.get("_approved_decision")
    if approved_decision_data:
        return await self._execute_approved_decision(approved_decision_data, timeout)

    # NEW: Check session trust rules first
    if self._session_id and self.trust_store:
        if self.trust_store.matches(self._session_id, "shell", command):
            decision = self.policy.evaluate(command=command, cwd=cwd, timeout=timeout)
            if decision.action == CommandAction.DENY:
                return ToolResult(success=False, error="; ".join(decision.reasons))
            return await self._execute_decision(decision)

    # Existing flow: evaluate -> DENY / REQUIRE_APPROVAL / ALLOW
    decision = self.policy.evaluate(command=command, cwd=cwd, timeout=timeout)
    ...
```

Important: Trusted commands still go through `CommandPolicy.evaluate()` to enforce **hard deny patterns** (e.g., `rm -rf /`). Trust only bypasses the `REQUIRE_APPROVAL` → `ALLOW` escalation.

### 3b. Changes: `AgentService._build_run_tool_registry()`

**File:** `backend/app/services/agent_service.py`

Pass `session_id` and `trust_store` to `ShellTool`:

```python
@staticmethod
def _build_run_tool_registry(
    project_path: str | None,
    session_id: str | None = None,
    trust_store: SessionTrustStore | None = None,
) -> ToolRegistry:
    ...
    registry.register(ShellTool(
        ShellSecurity(), path_security, CommandEffectRegistry(), create_sandbox(),
        session_id=session_id,
        trust_store=trust_store,
    ))
    ...
```

### 4. Changes: `CommandPolicy` — populate `suggested_prefix_rule`

**File:** `backend/app/security/command_policy.py`

In `_evaluate_argv_command()` and `_evaluate_shell_command()`, when `action == CommandAction.REQUIRE_APPROVAL`:

```python
from app.security.command_arity import extract_prefix_rule

suggested_prefix_rule = [extract_prefix_rule(command)] if action == CommandAction.REQUIRE_APPROVAL else None
```

Pass this into the `CommandDecision` constructor.

### 5. Changes: `AgentService.approve_tool_call()`

**File:** `backend/app/services/agent_service.py`

Add `decision` parameter to `approve_tool_call`:

```python
async def approve_tool_call(
    self, *, session_id: str, run_id: str, approval_id: str,
    decision: AllowApprovalDecision = "allow_once",
) -> None:
```

When `decision == "trust_and_allow"`:
1. Extract prefix rules from `pending.approval_payload["suggested_prefix_rule"]` (from `ToolApprovalRequest.payload`)
2. Add each as `TrustRule(permission="shell", pattern=prefix)` to `SessionTrustStore`
3. Scan other pending approvals in the same session; auto-approve any whose command matches a new trust rule

### 6. Changes: WebSocket handler

**File:** `backend/app/api/routes/websocket.py`

The `conversation:approve_tool` message now accepts an optional `decision` field:

```python
decision_str = msg_data.get("decision", "allow_once")
if decision_str not in ("allow_once", "trust_and_allow"):
    await _send_error(websocket, code="invalid_request", message="decision must be allow_once or trust_and_allow")
    continue

await agent_service.approve_tool_call(
    session_id=session_id,
    run_id=run_id,
    approval_id=approval_id,
    decision=decision_str,
)
```

### 7. Changes: Frontend — `ApprovalActionType`

**File:** `frontend/src/components/execution/approvalActions.ts`

```typescript
export type ApprovalActionType = 'approve' | 'trust' | 'deny'
```

- `approve` = allow once (existing)
- `trust` = allow for session (new)
- `deny` = reject (existing)

### 8. Changes: Frontend — `ApprovalCard`

**File:** `frontend/src/components/execution/ActionReceipt.tsx`

Add a third button "此会话允许" between "允许执行" and "拒绝":

```tsx
<button onClick={() => sendApprovalAction(onApprovalAction, 'approve', detail.approval)}>
  <Check /> 允许一次
</button>
<button onClick={() => sendApprovalAction(onApprovalAction, 'trust', detail.approval)}>
  <ShieldCheck /> 此会话允许
</button>
<button onClick={() => sendApprovalAction(onApprovalAction, 'deny', detail.approval)}>
  <X /> 拒绝
</button>
```

When `suggested_trust` is available in the approval payload, show a hint under the "此会话允许" button indicating the rule scope (e.g., "将信任: npm run *").

### 9. Changes: Frontend — WebSocket message

**File:** `frontend/src/services/sessionConversationWebSocket.ts`

`buildToolApprovalMessage` now includes `decision`:

```typescript
function buildToolApprovalMessage(
  type: 'conversation:approve_tool' | 'conversation:deny_tool',
  payload: { runId: string; approvalId: string; decision?: 'allow_once' | 'trust_and_allow' }
) {
  const data: Record<string, string> = {
    approval_id: payload.approvalId,
    run_id: payload.runId,
  }
  if (payload.decision) {
    data.decision = payload.decision
  }
  return { type, data }
}
```

### 10. Changes: Frontend — `useConversationRuntime`

**File:** `frontend/src/hooks/useConversationRuntime.ts`

```typescript
const approveTool = useCallback((runId: string, approvalId: string) => {
  wsRef.current?.approveTool({ runId, approvalId, decision: 'allow_once' })
}, [])

const trustTool = useCallback((runId: string, approvalId: string) => {
  wsRef.current?.approveTool({ runId, approvalId, decision: 'trust_and_allow' })
}, [])
```

### 11. Changes: Frontend — `AgentWorkspace` wiring

**File:** `frontend/src/pages/AgentWorkspace.tsx`

`onApprovalAction` callback maps `'trust'` to `trustTool()`:

```typescript
const handleApprovalAction = useCallback((action: ApprovalActionType, payload: ApprovalActionPayload) => {
  if (action === 'approve') {
    approveTool(payload.runId, payload.approvalId)
  } else if (action === 'trust') {
    trustTool(payload.runId, payload.approvalId)
  } else if (action === 'deny') {
    denyTool(payload.runId, payload.approvalId)
  }
}, [approveTool, trustTool, denyTool])
```

### 12. Changes: Frontend — pass `suggested_trust` through to UI

**File:** `frontend/src/components/workspace/transcriptItems.ts`

When building `detail.approval`, also extract `suggested_trust` from the approval payload:

```typescript
const suggestedTrust = approvalObj?.suggested_trust as Record<string, unknown> | undefined
detail.approval = {
  runId: message.runId,
  approvalId: payload.approval_id,
  suggestedTrust: suggestedTrust ?? undefined,
  ...
}
```

**File:** `frontend/src/components/execution/receiptUtils.ts`

Add `suggestedTrust` to the `approval` field:

```typescript
export interface ActionReceiptDetail {
  ...
  approval?: {
    runId: string
    approvalId: string
    suggestedTrust?: { prefix?: string[] }
    shell?: ShellApprovalPayload
  }
}
```

## Data Flow Summary

```
User clicks "此会话允许"
  → Frontend: sendApprovalAction('trust', {runId, approvalId})
  → WebSocket: conversation:approve_tool {approval_id, run_id, decision: "trust_and_allow"}
  → AgentService.approve_tool_call(decision="trust_and_allow")
    → SessionTrustStore.add_rule(session_id, TrustRule(permission="shell", pattern="npm run *"))
    → Scan other pending approvals in same session, auto-approve matching ones
    → Execute the approved tool (same as allow_once)
    → Emit events

Next time ShellTool.execute() is called with "npm run build":
  → ShellTool checks SessionTrustStore.matches(session_id, "shell", "npm run build")
  → "npm run build" matches rule "npm run *" → trusted
  → Bypass REQUIRE_APPROVAL, execute directly (still enforce hard deny)
```

## Files Changed

| File | Change |
|---|---|
| `backend/app/security/session_trust_store.py` | **New** — in-memory trust rule store |
| `backend/app/security/command_arity.py` | **New** — command prefix arity dictionary |
| `backend/app/security/command_policy.py` | Populate `suggested_prefix_rule` on REQUIRE_APPROVAL decisions |
| `backend/app/tools/shell_tool.py` | Check trust store before policy; receive `session_id` and `trust_store` via constructor |
| `backend/app/services/agent_service.py` | Add `decision` param to `approve_tool_call`; add trust rules + cascade; pass `session_id`/`trust_store` to `_build_run_tool_registry` |
| `backend/app/api/routes/websocket.py` | Accept `decision` field in approve message |
| `frontend/src/components/execution/approvalActions.ts` | Add `'trust'` to `ApprovalActionType` |
| `frontend/src/components/execution/ActionReceipt.tsx` | Add "此会话允许" button with hint |
| `frontend/src/components/execution/receiptUtils.ts` | Add `suggestedTrust` to approval interface |
| `frontend/src/components/workspace/transcriptItems.ts` | Extract `suggested_trust` from payload |
| `frontend/src/services/sessionConversationWebSocket.ts` | Add `decision` to approve message |
| `frontend/src/hooks/useConversationRuntime.ts` | Add `trustTool` callback |
| `frontend/src/pages/AgentWorkspace.tsx` | Wire `'trust'` action to `trustTool()` |

## Out of Scope

- Config-file-based permission rules (like opencode.json) — future work
- Cross-session persistent trust rules — future work
- Non-shell tool approvals (file, edit, patch) — only shell currently uses approval

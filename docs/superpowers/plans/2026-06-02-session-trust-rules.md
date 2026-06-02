# Session Trust Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "此会话允许" (Allow for Session) option to the approval system, so users can trust command prefixes and skip repeated approvals within a session.

**Architecture:** New `SessionTrustStore` (in-memory, per-session) stores wildcard prefix rules. `CommandArity` generates prefix rules from commands. `ShellTool` checks the trust store before policy evaluation. `AgentService.approve_tool_call()` gains a `decision` param; when `trust_and_allow`, it adds rules and auto-approves matching pending approvals. Frontend adds a third "此会话允许" button.

**Tech Stack:** Python (Pydantic, fnmatch, threading), TypeScript/React (existing frontend patterns)

**Spec:** `docs/superpowers/specs/2026-06-02-session-trust-rules-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/security/command_arity.py` | **New** — command prefix arity dictionary + `extract_prefix_rule()` |
| `backend/app/security/session_trust_store.py` | **New** — in-memory per-session trust rule store with glob matching |
| `backend/app/security/command_policy.py` | Populate `suggested_prefix_rule` on REQUIRE_APPROVAL decisions |
| `backend/app/tools/shell_tool.py` | Accept `session_id` + `trust_store` via constructor; check trust before policy |
| `backend/app/services/agent_service.py` | Add `decision` param; inject trust_store; add rules + cascade auto-approve |
| `backend/app/api/routes/websocket.py` | Accept `decision` field in approve message |
| `frontend/src/components/execution/approvalActions.ts` | Add `'trust'` to `ApprovalActionType` |
| `frontend/src/components/execution/receiptUtils.ts` | Add `suggestedTrust` to approval interface |
| `frontend/src/components/execution/ActionReceipt.tsx` | Add "此会话允许" button with hint |
| `frontend/src/components/workspace/transcriptItems.ts` | Extract `suggested_trust` from payload |
| `frontend/src/services/sessionConversationWebSocket.ts` | Add `decision` to approve message payload |
| `frontend/src/hooks/useConversationRuntime.ts` | Add `trustTool` callback |
| `frontend/src/pages/AgentWorkspace.tsx` | Wire `'trust'` action |
| `backend/tests/test_security/test_command_arity.py` | **New** — tests for command_arity |
| `backend/tests/test_security/test_session_trust_store.py` | **New** — tests for session_trust_store |

---

### Task 1: CommandArity — extract prefix rules from commands

**Files:**
- Create: `backend/app/security/command_arity.py`
- Test: `backend/tests/test_security/test_command_arity.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_security/test_command_arity.py
from app.security.command_arity import extract_prefix_rule


def test_extract_prefix_rule_npm_run():
    assert extract_prefix_rule("npm run dev") == "npm run *"


def test_extract_prefix_rule_npm_run_with_flags():
    assert extract_prefix_rule("npm run dev --flag") == "npm run *"


def test_extract_prefix_rule_git_push():
    assert extract_prefix_rule("git push origin main") == "git push *"


def test_extract_prefix_rule_curl():
    assert extract_prefix_rule("curl https://example.com") == "curl *"


def test_extract_prefix_rule_simple_command():
    assert extract_prefix_rule("pytest") == "pytest *"


def test_extract_prefix_rule_python_script():
    assert extract_prefix_rule("python script.py") == "python *"


def test_extract_prefix_rule_unknown_command():
    assert extract_prefix_rule("mycustomtool --flag arg1") == "mycustomtool *"


def test_extract_prefix_rule_docker_compose():
    assert extract_prefix_rule("docker compose up -d") == "docker compose *"


def test_extract_prefix_rule_make_target():
    assert extract_prefix_rule("make build") == "make *"


def test_extract_prefix_rule_empty_string():
    assert extract_prefix_rule("") == "*"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_security/test_command_arity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.security.command_arity'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/security/command_arity.py
import shlex

COMMAND_ARITY: dict[str, int] = {
    "git": 2,
    "npm": 2,
    "npm run": 3,
    "npx": 2,
    "pip": 2,
    "pip install": 2,
    "python": 2,
    "node": 2,
    "docker": 2,
    "docker compose": 3,
    "curl": 1,
    "wget": 1,
    "make": 2,
    "cargo": 2,
    "go": 2,
    "pytest": 1,
    "vitest": 1,
    "rm": 2,
}

DEFAULT_ARITY = 1


def extract_prefix_rule(command: str) -> str:
    if not command or not command.strip():
        return "*"

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if not tokens:
        return "*"

    best_arity = DEFAULT_ARITY
    for prefix, arity in COMMAND_ARITY.items():
        prefix_tokens = prefix.split()
        if len(tokens) >= len(prefix_tokens) and tokens[:len(prefix_tokens)] == prefix_tokens:
            if arity > best_arity:
                best_arity = arity

    prefix_tokens = tokens[:best_arity]
    return " ".join(prefix_tokens) + " *"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_security/test_command_arity.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/command_arity.py backend/tests/test_security/test_command_arity.py
git commit -m "feat: add command_arity module for prefix rule extraction"
```

---

### Task 2: SessionTrustStore — in-memory trust rule store

**Files:**
- Create: `backend/app/security/session_trust_store.py`
- Test: `backend/tests/test_security/test_session_trust_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_security/test_session_trust_store.py
from app.security.session_trust_store import SessionTrustStore, TrustRule


def test_trust_store_add_and_match():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    assert store.matches("session-1", "shell", "npm run dev") is True
    assert store.matches("session-1", "shell", "npm run build") is True
    assert store.matches("session-1", "shell", "npm install") is False


def test_trust_store_no_match_without_rules():
    store = SessionTrustStore()
    assert store.matches("session-1", "shell", "npm run dev") is False


def test_trust_store_different_sessions_isolated():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    assert store.matches("session-1", "shell", "npm run dev") is True
    assert store.matches("session-2", "shell", "npm run dev") is False


def test_trust_store_different_permissions():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    assert store.matches("session-1", "file", "npm run dev") is False


def test_trust_store_clear_session():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))
    store.clear_session("session-1")

    assert store.matches("session-1", "shell", "npm run dev") is False


def test_trust_store_get_rules():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))
    store.add_rule("session-1", TrustRule(permission="shell", pattern="git push *"))

    rules = store.get_rules("session-1")
    assert len(rules) == 2
    assert rules[0].pattern == "npm run *"
    assert rules[1].pattern == "git push *"


def test_trust_store_glob_wildcard():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="git *"))

    assert store.matches("session-1", "shell", "git push") is True
    assert store.matches("session-1", "shell", "git commit") is True
    assert store.matches("session-1", "shell", "git log --oneline") is True


def test_trust_store_glob_question_mark():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="pytest ?"))

    assert store.matches("session-1", "shell", "pytest x") is True
    assert store.matches("session-1", "shell", "pytest tests/") is False


def test_trust_store_multiple_rules_match():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))
    store.add_rule("session-1", TrustRule(permission="shell", pattern="git *"))

    assert store.matches("session-1", "shell", "npm run test") is True
    assert store.matches("session-1", "shell", "git commit") is True
    assert store.matches("session-1", "shell", "curl example.com") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_security/test_session_trust_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.security.session_trust_store'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/security/session_trust_store.py
from fnmatch import fnmatch
from threading import RLock
from typing import Literal

from pydantic import BaseModel


class TrustRule(BaseModel):
    permission: str
    pattern: str
    action: Literal["allow"] = "allow"


class SessionTrustStore:
    def __init__(self) -> None:
        self._rules: dict[str, list[TrustRule]] = {}
        self._lock = RLock()

    def add_rule(self, session_id: str, rule: TrustRule) -> None:
        with self._lock:
            if session_id not in self._rules:
                self._rules[session_id] = []
            self._rules[session_id].append(rule)

    def get_rules(self, session_id: str) -> list[TrustRule]:
        with self._lock:
            return list(self._rules.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._rules.pop(session_id, None)

    def matches(self, session_id: str, permission: str, target: str) -> bool:
        with self._lock:
            rules = self._rules.get(session_id, [])
            for rule in rules:
                if rule.permission == permission and fnmatch(target, rule.pattern):
                    return True
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_security/test_session_trust_store.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/session_trust_store.py backend/tests/test_security/test_session_trust_store.py
git commit -m "feat: add SessionTrustStore for per-session trust rules"
```

---

### Task 3: CommandPolicy — populate `suggested_prefix_rule`

**Files:**
- Modify: `backend/app/security/command_policy.py:267-279` (shell command decision)
- Modify: `backend/app/security/command_policy.py:377-389` (argv command decision)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_security/test_command_policy.py`:

```python
def test_argv_require_approval_has_suggested_prefix_rule(self, policy):
    decision = policy.evaluate(command="npm run dev", cwd="/tmp")
    if decision.action == CommandAction.REQUIRE_APPROVAL:
        assert decision.suggested_prefix_rule is not None
        assert len(decision.suggested_prefix_rule) == 1
        assert decision.suggested_prefix_rule[0] == "npm run *"
    else:
        pytest.skip("npm run dev is not REQUIRE_APPROVAL on this platform")


def test_shell_require_approval_has_suggested_prefix_rule(self, policy):
    decision = policy.evaluate(command="npm run dev && echo done", cwd="/tmp")
    if decision.action == CommandAction.REQUIRE_APPROVAL:
        assert decision.suggested_prefix_rule is not None
        assert len(decision.suggested_prefix_rule) == 1
    else:
        pytest.skip("command is not REQUIRE_APPROVAL on this platform")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_security/test_command_policy.py::TestCommandPolicyEvaluate::test_argv_require_approval_has_suggested_prefix_rule -v`
Expected: FAIL — `assert decision.suggested_prefix_rule is not None` (currently always `None`)

- [ ] **Step 3: Implement — add import and populate field**

In `backend/app/security/command_policy.py`, add import at top:

```python
from app.security.command_arity import extract_prefix_rule
```

In `_evaluate_shell_command()` (around line 267), change the `CommandDecision` construction to include `suggested_prefix_rule`:

```python
suggested_prefix_rule = [extract_prefix_rule(command)] if action == CommandAction.REQUIRE_APPROVAL else None

return CommandDecision(
    action=action,
    execution_mode="shell",
    command=command,
    argv=None,
    cwd=cwd,
    timeout=timeout,
    reasons=reasons or [f"效果分类: {effect.value}"],
    risks=risks,
    approval_kind=approval_kind,
    suggested_prefix_rule=suggested_prefix_rule,
    environment_snapshot=snapshot,
    effect_category=effect,
)
```

In `_evaluate_argv_command()` (around line 377), do the same:

```python
suggested_prefix_rule = [extract_prefix_rule(command)] if action == CommandAction.REQUIRE_APPROVAL else None

return CommandDecision(
    action=action,
    execution_mode="argv",
    command=command,
    argv=argv,
    cwd=cwd,
    timeout=timeout,
    reasons=reasons or [f"效果分类: {effect.value}"],
    risks=risks,
    approval_kind=approval_kind,
    suggested_prefix_rule=suggested_prefix_rule,
    environment_snapshot=snapshot,
    effect_category=effect,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_security/test_command_policy.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/command_policy.py backend/tests/test_security/test_command_policy.py
git commit -m "feat: populate suggested_prefix_rule on REQUIRE_APPROVAL decisions"
```

---

### Task 4: ShellTool — inject session_id and trust_store, check trust before policy

**Files:**
- Modify: `backend/app/tools/shell_tool.py:19-34` (constructor)
- Modify: `backend/app/tools/shell_tool.py:67-88` (execute method)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tools/test_shell_tool.py`:

```python
import pytest
from app.security.session_trust_store import SessionTrustStore, TrustRule
from app.tools.shell_tool import ShellTool


def test_shell_tool_trusted_command_bypasses_approval():
    trust_store = SessionTrustStore()
    trust_store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    tool = ShellTool(
        ShellSecurity(),
        PathSecurity(["/tmp"], base_dir="/tmp"),
        CommandEffectRegistry(),
        NullSandbox(),
        session_id="session-1",
        trust_store=trust_store,
    )

    result = asyncio.get_event_loop().run_until_complete(
        tool.execute({"command": "npm run dev"})
    )
    # Should NOT require approval — trusted
    assert result.approval_required is False


def test_shell_tool_untrusted_command_still_requires_approval():
    trust_store = SessionTrustStore()

    tool = ShellTool(
        ShellSecurity(),
        PathSecurity(["/tmp"], base_dir="/tmp"),
        CommandEffectRegistry(),
        NullSandbox(),
        session_id="session-1",
        trust_store=trust_store,
    )

    result = asyncio.get_event_loop().run_until_complete(
        tool.execute({"command": "curl https://example.com"})
    )
    # curl should still require approval — no trust rule
    assert result.approval_required is True


def test_shell_tool_hard_deny_overrides_trust():
    trust_store = SessionTrustStore()
    trust_store.add_rule("session-1", TrustRule(permission="shell", pattern="rm *"))

    tool = ShellTool(
        ShellSecurity(),
        PathSecurity(["/tmp"], base_dir="/tmp"),
        CommandEffectRegistry(),
        NullSandbox(),
        session_id="session-1",
        trust_store=trust_store,
    )

    result = asyncio.get_event_loop().run_until_complete(
        tool.execute({"command": "rm -rf /"})
    )
    # Hard deny should override trust
    assert result.success is False
    assert result.approval_required is False
```

Note: Check the existing test file for the import patterns and how `asyncio.get_event_loop()` is used, and adjust accordingly. If the test file uses `@pytest.mark.asyncio`, use that instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_tools/test_shell_tool.py -v -k "trusted_command_bypasses_approval or untrusted_command_still_requires or hard_deny_overrides_trust"`
Expected: FAIL — `TypeError: ShellTool.__init__() got unexpected keyword arguments`

- [ ] **Step 3: Implement the changes**

In `backend/app/tools/shell_tool.py`:

Add import at top:
```python
from app.security.session_trust_store import SessionTrustStore
```

Change the constructor to accept optional `session_id` and `trust_store`:
```python
def __init__(
    self,
    security: ShellSecurity,
    path_security: PathSecurity,
    registry: CommandEffectRegistry | None = None,
    sandbox: SandboxProvider | None = None,
    session_id: str | None = None,
    trust_store: SessionTrustStore | None = None,
):
    self.security = security
    self.path_security = path_security
    self.registry = registry or CommandEffectRegistry()
    self.sandbox = sandbox or NullSandbox()
    self.policy = CommandPolicy(security, path_security, self.registry)
    self._session_id = session_id
    self.trust_store = trust_store
```

In `execute()`, add trust check before policy evaluation (after the `_approved_decision` check):

```python
if self._session_id and self.trust_store:
    if self.trust_store.matches(self._session_id, "shell", command):
        decision = self.policy.evaluate(command=command, cwd=cwd, timeout=timeout)
        if decision.action == CommandAction.DENY:
            reason_str = "; ".join(decision.reasons) if decision.reasons else "命令被拒绝"
            return ToolResult(success=False, error=reason_str)
        return await self._execute_decision(decision)
```

This goes between the `_approved_decision` check and the `self.policy.evaluate()` call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_tools/test_shell_tool.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/shell_tool.py backend/tests/test_tools/test_shell_tool.py
git commit -m "feat: ShellTool checks SessionTrustStore before policy evaluation"
```

---

### Task 5: AgentService — add decision param, inject trust_store, cascade auto-approve

**Files:**
- Modify: `backend/app/services/agent_service.py:715-723` (approve_tool_call signature)
- Modify: `backend/app/services/agent_service.py:112-147` (_build_run_tool_registry)
- Modify: `backend/app/services/agent_service.py:740-852` (_decide_tool_call_approval)

- [ ] **Step 1: Add `SessionTrustStore` to `AgentService`**

Add import at top of `agent_service.py`:
```python
from app.security.session_trust_store import SessionTrustStore, TrustRule
from app.security.command_arity import extract_prefix_rule
```

Add `trust_store` to `AgentService.__init__()`:
```python
self.trust_store = SessionTrustStore()
```

- [ ] **Step 2: Update `_build_run_tool_registry` to accept and pass `session_id` + `trust_store`**

Change the method signature:
```python
@staticmethod
def _build_run_tool_registry(
    project_path: str | None,
    session_id: str | None = None,
    trust_store: SessionTrustStore | None = None,
) -> ToolRegistry:
```

In the body, pass them to `ShellTool`:
```python
registry.register(ShellTool(
    ShellSecurity(), path_security, CommandEffectRegistry(), create_sandbox(),
    session_id=session_id,
    trust_store=trust_store,
))
```

- [ ] **Step 3: Update call sites of `_build_run_tool_registry`**

Search for all calls to `self._build_run_tool_registry(` or `AgentService._build_run_tool_registry(` and pass `session_id` and `trust_store`:

Where `session_id` is available (around line 377):
```python
run_tool_registry = self._build_run_tool_registry(project_path, session_id=session_id, trust_store=self.trust_store)
```

Where `session_id` is NOT available (around line 875 in `_execute_approved_tool`):
```python
tool_registry = getattr(loop, "tool_registry", None) or self._build_run_tool_registry(project_path)
```
Leave this one as-is (no session_id available in that context, and the trust store check only matters at initial tool execution time, not at re-execution after approval).

- [ ] **Step 4: Update `approve_tool_call` signature and `_decide_tool_call_approval`**

Change `approve_tool_call`:
```python
async def approve_tool_call(
    self, *, session_id: str, run_id: str, approval_id: str,
    decision: AllowApprovalDecision = "allow_once",
) -> None:
    await self._decide_tool_call_approval(
        session_id=session_id,
        run_id=run_id,
        approval_id=approval_id,
        approval_event_type=EventType.APPROVAL_APPROVED,
        decision=decision,
    )
```

Change `_decide_tool_call_approval` signature to accept `decision`:
```python
async def _decide_tool_call_approval(
    self,
    *,
    session_id: str,
    run_id: str,
    approval_id: str,
    approval_event_type: EventType,
    decision: AllowApprovalDecision = "allow_once",
) -> None:
```

In the `APPROVAL_APPROVED` branch (around line 769), change:
```python
self.pending_approval_store.approve(approval_id, decision=decision)
```

And add trust rule logic after the approval:
```python
if decision == "trust_and_allow":
    self._add_trust_rules_from_approval(pending, session_id)
    await self._cascade_auto_approve(session_id)
```

- [ ] **Step 5: Add helper methods `_add_trust_rules_from_approval` and `_cascade_auto_approve`**

```python
def _add_trust_rules_from_approval(self, pending: PendingToolApproval, session_id: str) -> None:
    approval_payload = pending.approval_payload
    suggested_prefixes = approval_payload.get("suggested_prefix_rule")
    if suggested_prefixes and isinstance(suggested_prefixes, list):
        for prefix in suggested_prefixes:
            if isinstance(prefix, str) and prefix:
                self.trust_store.add_rule(session_id, TrustRule(permission="shell", pattern=prefix))

    suggested_trust = approval_payload.get("suggested_trust")
    if isinstance(suggested_trust, dict):
        trust_prefixes = suggested_trust.get("prefix")
        if isinstance(trust_prefixes, list):
            for prefix in trust_prefixes:
                if isinstance(prefix, str) and prefix:
                    self.trust_store.add_rule(session_id, TrustRule(permission="shell", pattern=prefix))

async def _cascade_auto_approve(self, session_id: str) -> None:
    from app.models.approval import AllowApprovalDecision
    for approval_id in self.pending_approval_store._list_pending_approval_ids_for_session(session_id):
        pending = self.pending_approval_store.get(approval_id)
        if pending is None or pending.status != "pending":
            continue
        command = pending.approval_payload.get("command") or pending.tool_arguments.get("command")
        if command and self.trust_store.matches(session_id, "shell", command):
            await self.approve_tool_call(
                session_id=session_id,
                run_id=pending.run_id,
                approval_id=pending.id,
                decision="allow_once",
            )
```

Also add the helper method to `PendingApprovalStore`:

In `backend/app/execution/approval_store.py`, add:
```python
def list_pending_approval_ids_for_session(self, session_id: str) -> list[str]:
    with self._lock:
        return [
            aid for aid, pending in self._approvals.items()
            if pending.session_id == session_id and pending.status == "pending"
        ]
```

- [ ] **Step 6: Run existing tests to verify nothing is broken**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_services/test_agent_service.py -v -k "approve"`
Expected: All PASS (default `decision="allow_once"` preserves existing behavior)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agent_service.py backend/app/execution/approval_store.py
git commit -m "feat: AgentService supports trust_and_allow decision with cascade auto-approve"
```

---

### Task 6: WebSocket handler — accept `decision` field

**Files:**
- Modify: `backend/app/api/routes/websocket.py:202-236`

- [ ] **Step 1: Modify the approve handler**

In the `conversation:approve_tool` branch, extract and validate the `decision` field:

Replace the existing block (lines 222-227):
```python
if msg_type == "conversation:approve_tool":
    await agent_service.approve_tool_call(
        session_id=session_id,
        run_id=run_id,
        approval_id=approval_id,
    )
```

With:
```python
if msg_type == "conversation:approve_tool":
    decision_str = msg_data.get("decision", "allow_once")
    if decision_str not in ("allow_once", "trust_and_allow"):
        await _send_error(
            websocket,
            code="invalid_request",
            message="decision must be allow_once or trust_and_allow",
        )
        continue

    await agent_service.approve_tool_call(
        session_id=session_id,
        run_id=run_id,
        approval_id=approval_id,
        decision=decision_str,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/websocket.py
git commit -m "feat: WebSocket handler accepts decision field for approval"
```

---

### Task 7: Frontend — approvalActions + receiptUtils + transcriptItems

**Files:**
- Modify: `frontend/src/components/execution/approvalActions.ts`
- Modify: `frontend/src/components/execution/receiptUtils.ts`
- Modify: `frontend/src/components/workspace/transcriptItems.ts`

- [ ] **Step 1: Update `approvalActions.ts`**

```typescript
// frontend/src/components/execution/approvalActions.ts
export type ApprovalActionType = 'approve' | 'trust' | 'deny'

export interface ApprovalActionPayload {
  runId: string
  approvalId: string
}

export type ApprovalActionHandler = (
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) => void

export function sendApprovalAction(
  onApprovalAction: ApprovalActionHandler | undefined,
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) {
  onApprovalAction?.(action, {
    runId: payload.runId,
    approvalId: payload.approvalId,
  })
}
```

- [ ] **Step 2: Update `receiptUtils.ts` — add `suggestedTrust` to approval interface**

In the `ActionReceiptDetail` interface, update the `approval` field:

```typescript
approval?: {
  runId: string
  approvalId: string
  suggestedTrust?: { prefix?: string[] }
  shell?: ShellApprovalPayload
}
```

- [ ] **Step 3: Update `transcriptItems.ts` — extract `suggested_trust` from payload**

In the block where `detail.approval` is built (around line 95), add `suggestedTrust`:

```typescript
const suggestedTrust = approvalObj?.suggested_trust as Record<string, unknown> | undefined

detail.approval = {
  runId: message.runId,
  approvalId: payload.approval_id,
  suggestedTrust: suggestedTrust ?? undefined,
  ...(hasShellPayload
    ? {
        shell: {
          command: approvalPayload.command as string,
          ...(typeof approvalPayload.execution_mode === 'string'
            ? { execution_mode: approvalPayload.execution_mode }
            : {}),
          ...(Array.isArray(approvalObj?.reasons)
            ? { reasons: (approvalObj!.reasons as string[]).filter((r): r is string => typeof r === 'string') }
            : {}),
          ...(Array.isArray(approvalObj?.risks)
            ? { risks: (approvalObj!.risks as string[]).filter((r): r is string => typeof r === 'string') }
            : {}),
        },
      }
    : {}),
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No new errors related to the changed files

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/execution/approvalActions.ts frontend/src/components/execution/receiptUtils.ts frontend/src/components/workspace/transcriptItems.ts
git commit -m "feat: frontend types support trust action and suggestedTrust"
```

---

### Task 8: Frontend — ActionReceipt "此会话允许" button

**Files:**
- Modify: `frontend/src/components/execution/ActionReceipt.tsx:145-207`

- [ ] **Step 1: Update ApprovalCard component**

Add `ShieldCheck` to the lucide-react import (it's already importing from lucide-react).

Then modify the `ApprovalCard` component's button area. Replace the existing two-button block with three buttons:

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, AlertTriangle, Check, ChevronDown, ChevronRight, Clock3, Loader2, ShieldAlert, ShieldCheck, Terminal, X } from 'lucide-react'
```

Replace the buttons section in `ApprovalCard` (the `<div className="border-t ...">` block):

```tsx
<div className="border-t border-edge bg-surface-secondary px-4 py-3">
  {approvalDetails.map((detail) => (
    <div key={detail.id} className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => sendApprovalAction(onApprovalAction, 'approve', detail.approval)}
        className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <Check className="h-3.5 w-3.5" />
        允许一次
      </button>
      <button
        type="button"
        onClick={() => sendApprovalAction(onApprovalAction, 'trust', detail.approval)}
        className="inline-flex items-center justify-center gap-1.5 rounded-md border border-accent bg-surface-primary px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent/10 focus:outline-none focus:ring-2 focus:ring-accent/30"
      >
        <ShieldCheck className="h-3.5 w-3.5" />
        此会话允许
      </button>
      {detail.shell && detail.approval.suggestedTrust?.prefix && (
        <span className="text-xs text-content-muted">
          将信任: {detail.approval.suggestedTrust.prefix.join(', ')}
        </span>
      )}
      <button
        type="button"
        onClick={() => sendApprovalAction(onApprovalAction, 'deny', detail.approval)}
        className="inline-flex items-center justify-center gap-1.5 rounded-md border border-edge bg-surface-primary px-3 py-1.5 text-sm font-medium text-content-secondary transition-colors hover:bg-surface-tertiary focus:outline-none focus:ring-2 focus:ring-accent/30"
      >
        <X className="h-3.5 w-3.5" />
        拒绝
      </button>
    </div>
  ))}
</div>
```

- [ ] **Step 2: Verify TypeScript compiles and UI renders**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/execution/ActionReceipt.tsx
git commit -m "feat: add '此会话允许' button to ApprovalCard"
```

---

### Task 9: Frontend — WebSocket message + useConversationRuntime + AgentWorkspace wiring

**Files:**
- Modify: `frontend/src/services/sessionConversationWebSocket.ts`
- Modify: `frontend/src/hooks/useConversationRuntime.ts`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Update `sessionConversationWebSocket.ts`**

Change `buildToolApprovalMessage` to accept `decision`:

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

Update `approveTool` method to accept and pass `decision`:

```typescript
approveTool(payload: { runId: string; approvalId: string; decision?: 'allow_once' | 'trust_and_allow' }): void {
  if (this.ws && this.ws.readyState === WebSocket.OPEN) {
    this.ws.send(JSON.stringify(buildToolApprovalMessage('conversation:approve_tool', payload)))
  }
}
```

- [ ] **Step 2: Update `useConversationRuntime.ts`**

Change `approveTool` to pass `decision: 'allow_once'`:

```typescript
const approveTool = useCallback((runId: string, approvalId: string) => {
  if (!wsRef.current?.isConnected()) {
    return
  }
  wsRef.current.approveTool({ runId, approvalId, decision: 'allow_once' })
}, [])
```

Add `trustTool` callback after `denyTool`:

```typescript
const trustTool = useCallback((runId: string, approvalId: string) => {
  if (!wsRef.current?.isConnected()) {
    return
  }
  wsRef.current.approveTool({ runId, approvalId, decision: 'trust_and_allow' })
}, [])
```

Make sure `trustTool` is returned from the hook (add it to the return object).

- [ ] **Step 3: Update `AgentWorkspace.tsx`**

Wire `'trust'` action to `trustTool()`:

```typescript
onApprovalAction: (action, payload) => {
  if (action === 'approve') {
    approveTool(payload.runId, payload.approvalId)
    return
  }
  if (action === 'trust') {
    trustTool(payload.runId, payload.approvalId)
    return
  }
  denyTool(payload.runId, payload.approvalId)
},
```

Make sure `trustTool` is destructured from `useConversationRuntime`.

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/sessionConversationWebSocket.ts frontend/src/hooks/useConversationRuntime.ts frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: wire trust action through WebSocket, runtime hook, and workspace"
```

---

### Task 10: Integration verification

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: All tests PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit 2>&1 | tail -10`
Expected: No errors

- [ ] **Step 3: Manual smoke test**

Start dev server and verify:
1. Send a message that triggers a shell command requiring approval
2. Verify 3 buttons appear: "允许一次", "此会话允许", "拒绝"
3. Click "此会话允许" → verify the hint shows the prefix rule (e.g., "将信任: npm run *")
4. Verify the next matching command executes without asking for approval
5. Verify hard-denied commands (e.g., `rm -rf /`) are still blocked even if trusted

- [ ] **Step 4: Final commit if any fixes needed**

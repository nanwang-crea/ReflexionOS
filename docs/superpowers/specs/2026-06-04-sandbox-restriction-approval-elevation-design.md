# Sandbox Restriction Approval Elevation Design

**Date:** 2026-06-04
**Status:** Approved

## Problem

When commands execute inside the OS sandbox (Seatbelt on macOS, bubblewrap on Linux), two categories of restriction can cause runtime failures:

1. **Network denied** — The sandbox blocks network access by default (`(deny network*)` on Seatbelt, `--unshare-net` on bwrap). Commands like `pip install`, `npm install`, `cargo build` need network but are classified as `WRITE_PROJECT` (which gets `ALLOW`), so they execute directly with `allow_network=False`. The sandbox kills them, and the LLM receives an opaque stderr error. It retries the same command infinitely.

2. **Path denied** — The sandbox restricts file access to project directories and system paths. When a command tries to access a path outside the allowed scope (e.g., reading a config from `~/` or writing to a shared cache), the sandbox denies it. Same infinite retry loop.

**Root cause:** Sandbox restrictions manifest as runtime errors, not as structured approval requests. The LLM cannot distinguish "the command is wrong" from "the sandbox blocked this, you need user approval."

## Non-Goals

- Do NOT modify `CommandPolicy` classification logic — `WRITE_PROJECT` stays `ALLOW`, `NETWORK_OUT` stays `REQUIRE_APPROVAL`.
- Do NOT modify `SandboxLevel` / `SandboxPolicy` structure.
- Do NOT modify Seatbelt profile generation logic.
- Do NOT implement project-level persistent trust rules (session-level only).
- Do NOT add a parallel approval system — must unify with existing `ToolApprovalRequest` flow.

## Design: Unified Approval Elevation

### Core Principle

Reuse the existing approval chain: `ToolApprovalRequest` → frontend `ApprovalCard` → backend `_execute_approved_decision` → `_execute_decision`. Differentiate by `approval_kind` field.

```
Trigger 1 (existing): Policy evaluate → REQUIRE_APPROVAL → approval_kind = "shell_command"
Trigger 2 (new):      Execute fail → Sandbox error detected → approval_kind = "sandbox_network_elevation" / "sandbox_path_elevation"
```

Both share: same `ToolApprovalRequest` structure, same `ApprovalCard` component, same `_execute_approved_decision` recovery path.

### SandboxErrorDetector

New module: `backend/app/security/sandbox/error_detector.py`

#### Detection Signals

1. **stderr pattern matching** — primary signal
   - macOS Seatbelt: `deny network`, `deny file-read* (subpath "...")`, `deny file-write*`
   - Linux bwrap: `Network is unreachable` + nonzero exit, `Permission denied` in sandbox context
2. **Nonzero exit code** — necessary condition (exit 0 cannot be sandbox denial)
3. **Registry auxiliary signal** — `CommandEffectEntry.often_needs_network` for commands like `pip install`, `npm install`, `cargo build`, `go mod download`

#### Confidence Levels

- **high**: stderr directly matches Seatbelt deny statement
- **medium**: nonzero exit + network error keywords + registry `often_needs_network=True`

#### Data Model

```python
class SandboxErrorType(str, enum.Enum):
    NETWORK_DENIED = "network_denied"
    PATH_DENIED = "path_denied"

@dataclass
class SandboxErrorInfo:
    error_type: SandboxErrorType
    denied_paths: list[str] = field(default_factory=list)
    original_stderr: str = ""
    confidence: Literal["high", "medium"] = "medium"

class SandboxErrorDetector:
    SEATBELT_NETWORK_PATTERNS = [
        r"deny\s+network",
        r"sandbox-exec.*denied.*network",
    ]
    SEATBELT_PATH_PATTERNS = [
        r"deny\s+file-read\*\s+\(subpath\s+\"([^\"]+)\"\)",
        r"deny\s+file-write\*\s+.*\(subpath\s+\"([^\"]+)\"\)",
    ]
    BWRAP_NETWORK_PATTERNS = [
        r"Network is unreachable",
        r"Could not resolve host",
        r"Temporary failure in name resolution",
    ]

    def detect(
        self,
        returncode: int,
        stderr: str,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
        platform: str = sys.platform,
    ) -> SandboxErrorInfo | None:
        # returncode == 0 → not sandbox denial
        # Match stderr patterns → high confidence
        # Nonzero + network error keywords + often_needs_network → medium confidence
```

### CommandEffectEntry Extension

```python
class CommandEffectEntry(BaseModel):
    category: EffectCategory
    allow_subcommands: bool = False
    subcommand_overrides: dict[str, EffectCategory] = {}
    flag_overrides: dict[str, EffectCategory] = {}
    platform_overrides: dict[str, EffectCategory] = {}
    often_needs_network: bool = False  # NEW
```

Default registrations to add `often_needs_network=True`:

| Command | Category | often_needs_network |
|---------|----------|-------------------|
| pip install | WRITE_PROJECT | True |
| pip download | NETWORK_OUT | True (already NETWORK_OUT, but explicit) |
| npm install | WRITE_PROJECT | True |
| npm publish | NETWORK_OUT | True |
| cargo build | WRITE_PROJECT | True |
| cargo install | WRITE_PROJECT | True |
| go mod download | WRITE_PROJECT | True |
| go get | WRITE_PROJECT | True |
| dotnet restore | WRITE_PROJECT | True |
| docker pull | WRITE_SYSTEM | True |
| git push | NETWORK_OUT | True (already NETWORK_OUT) |
| git fetch | NETWORK_OUT | True (already NETWORK_OUT) |
| git clone | NETWORK_OUT | True (already NETWORK_OUT) |
| pre-commit | WRITE_PROJECT | True (autoupdate fetches hooks) |

### ShellTool Integration

#### Execution Error Path Change

In `_execute_argv` and `_execute_shell`, insert detection before returning generic error:

```python
# Before (existing):
if process.returncode != 0:
    return ToolResult(success=False, output=output, error=error, data={"return_code": process.returncode})

# After:
if process.returncode != 0:
    error_info = self.sandbox_error_detector.detect(
        returncode=process.returncode,
        stderr=error,
        command_argv=argv if execution_mode == "argv" else None,
        registry=self.registry,
    )
    if error_info is not None:
        return self._create_approval_result(decision, elevation=error_info)

    return ToolResult(success=False, output=output, error=error, data={"return_code": process.returncode})
```

Note: `decision` needs to be passed through to `_execute_argv` / `_execute_shell`. Currently `_execute_decision` passes only partial fields. The method signature changes to accept the full `CommandDecision` or at minimum the `approval_kind` + effect category.

#### _create_approval_result Extension

```python
def _create_approval_result(
    self,
    decision: CommandDecision,
    elevation: SandboxErrorInfo | None = None,
) -> ToolResult:
    approval_id = f"approval-{uuid.uuid4().hex[:12]}"

    if elevation is not None:
        # Sandbox elevation approval
        if elevation.error_type == SandboxErrorType.NETWORK_DENIED:
            approval_kind = "sandbox_network_elevation"
            summary = f"沙箱阻止了网络访问: {decision.command}"
            reasons = ["命令需要网络访问，但沙箱默认禁止网络"]
            risks = ["允许网络访问可能导致数据外传"]
            elevation_request = {"type": "network", "denied_paths": []}
        else:
            approval_kind = "sandbox_path_elevation"
            paths_str = ", ".join(elevation.denied_paths)
            summary = f"沙箱阻止了路径访问: {decision.command} — {paths_str}"
            reasons = [f"命令需要访问沙箱外路径: {paths_str}"]
            risks = ["访问项目外路径可能暴露敏感文件"]
            elevation_request = {"type": "path", "denied_paths": elevation.denied_paths}
    else:
        # Existing shell command approval (unchanged)
        approval_kind = decision.approval_kind
        # ... existing summary/reasons/risks logic ...
        elevation_request = None

    approval = ToolApprovalRequest(
        approval_id=approval_id,
        tool_name="shell",
        summary=summary,
        reasons=reasons,
        risks=risks,
        payload={
            "command": decision.command,
            "execution_mode": decision.execution_mode,
            "argv": decision.argv,
            "cwd": decision.cwd,
            "timeout": decision.timeout,
            "approval_kind": approval_kind,
            "effect_category": decision.effect_category.value if decision.effect_category else None,
            "elevation_request": elevation_request,
            "environment_snapshot": decision.environment_snapshot.model_dump() if decision.environment_snapshot else None,
            "approved_decision": decision.model_dump(),
        },
        suggested_action="allow_once",
        suggested_trust=(
            {"permission": "sandbox_network", "pattern": "*"} if elevation and elevation.error_type == SandboxErrorType.NETWORK_DENIED
            else {"permission": "sandbox_path", "pattern": elevation.denied_paths[0] + "/*"} if elevation and elevation.denied_paths
            else {"prefix": decision.suggested_prefix_rule} if decision.suggested_prefix_rule
            else None
        ),
    )

    return ToolResult(success=False, approval_required=True, approval=approval)
```

#### _execute_approved_decision Elevation Handling

```python
async def _execute_approved_decision(self, decision_data: dict, default_timeout: int) -> ToolResult:
    decision = CommandDecision.model_validate(decision_data)
    elevation = decision_data.get("elevation_request")

    if elevation:
        if elevation["type"] == "network":
            decision._sandbox_allow_network = True
        elif elevation["type"] == "path":
            decision._sandbox_extra_paths = elevation["denied_paths"]

    return await self._execute_decision(decision)
```

#### _execute_decision Pass-Through

`_execute_decision` reads the elevation flags from `decision` and passes them to `_execute_argv` / `_execute_shell`:

```python
async def _execute_decision(self, decision: CommandDecision) -> ToolResult:
    # ... existing cwd/timeout logic ...

    try:
        if decision.execution_mode == "shell":
            return await self._execute_shell(
                decision.command, cwd, timeout, decision.effect_category,
                sandbox_allow_network=getattr(decision, '_sandbox_allow_network', False),
                sandbox_extra_paths=getattr(decision, '_sandbox_extra_paths', []),
            )
        else:
            return await self._execute_argv(
                decision.argv, cwd, timeout, decision.effect_category,
                sandbox_allow_network=getattr(decision, '_sandbox_allow_network', False),
                sandbox_extra_paths=getattr(decision, '_sandbox_extra_paths', []),
            )
    except Exception as e:
        # ... existing error handling ...
```

`_execute_argv` / `_execute_shell` use the flags:

```python
async def _execute_argv(self, argv, cwd, timeout, effect_category=None,
                        sandbox_allow_network=False, sandbox_extra_paths=None):
    if self.sandbox.is_available():
        allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
        allowed_paths = list(self.path_security.allowed_base_paths)
        if sandbox_extra_paths:
            allowed_paths.extend(sandbox_extra_paths)
        argv = self.sandbox.wrap_command(
            argv, cwd=cwd, allowed_paths=allowed_paths, allow_network=allow_network,
        )
    # ... rest unchanged ...
```

#### Pre-execution Trust Check

Before executing, check if the session already has elevation trust:

```python
async def _execute_decision(self, decision: CommandDecision) -> ToolResult:
    # Pre-check session trust for sandbox elevation
    sandbox_allow_network = False
    sandbox_extra_paths = []

    if self._session_id and self.trust_store:
        if self.trust_store.matches(self._session_id, "sandbox_network", "*"):
            sandbox_allow_network = True
        # Check path elevation trust
        for rule in self.trust_store.get_rules(self._session_id):
            if rule.permission == "sandbox_path" and ...:
                sandbox_extra_paths.append(...)

    # Merge with decision-level elevation flags
    final_allow_network = sandbox_allow_network or getattr(decision, '_sandbox_allow_network', False)
    final_extra_paths = sandbox_extra_paths + getattr(decision, '_sandbox_extra_paths', [])
    # ... pass to execute methods ...
```

### Session Trust Extension

`SessionTrustStore` does not need code changes — `permission` is already a `str` field.

New permission types used by elevation approvals:

| permission | pattern | Meaning |
|-----------|---------|---------|
| `sandbox_network` | `*` | Network access allowed in this session |
| `sandbox_path` | `/some/path/*` | Path access allowed in this session |

Trust is written when user clicks "此会话允许" on an elevation approval card. The frontend sends a `trust` action with the `suggested_trust` from the approval payload.

### Frontend Changes

#### receiptUtils.ts — New Payload Types

```typescript
export interface SandboxNetworkPayload {
  approval_kind: "sandbox_network_elevation"
  command: string
  execution_mode: string
  reasons: string[]
  risks: string[]
}

export interface SandboxPathPayload {
  approval_kind: "sandbox_path_elevation"
  command: string
  execution_mode: string
  denied_paths: string[]
  reasons: string[]
  risks: string[]
}
```

#### ActionReceipt.tsx — New Detail Components

```tsx
const SandboxNetworkDetail = memo(function ({ payload }: { payload: SandboxNetworkPayload }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
        <Globe className="h-4 w-4 shrink-0 text-content-muted" />
        <code className="font-mono text-sm break-all">{payload.command}</code>
      </div>
      <div className="text-xs text-status-warning pl-6">
        沙箱阻止了网络访问
      </div>
      {payload.reasons && <div className="text-xs text-content-secondary pl-6">原因: {payload.reasons.join('；')}</div>}
    </div>
  )
})

const SandboxPathDetail = memo(function ({ payload }: { payload: SandboxPathPayload }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
        <FolderLock className="h-4 w-4 shrink-0 text-content-muted" />
        <code className="font-mono text-sm break-all">{payload.command}</code>
      </div>
      <div className="text-xs text-status-warning pl-6">
        沙箱阻止了路径访问: {payload.denied_paths.join(', ')}
      </div>
    </div>
  )
})
```

`ApprovalCard` dispatches by `approval_kind`:

```tsx
{detail.shell && <ShellApprovalDetail shell={detail.shell} />}
{detail.sandboxNetwork && <SandboxNetworkDetail payload={detail.sandboxNetwork} />}
{detail.sandboxPath && <SandboxPathDetail payload={detail.sandboxPath} />}
```

Button labels adapt:

| approval_kind | 允许一次 | 此会话允许 | 拒绝 |
|---------------|---------|-----------|------|
| shell_command | 允许一次 | 此会话允许 | 拒绝 |
| sandbox_network_elevation | 允许网络一次 | 此会话允许网络 | 拒绝 |
| sandbox_path_elevation | 允许访问一次 | 此会话允许访问 | 拒绝 |

### Error Prompt Optimization

When sandbox error is NOT detected (low confidence or unknown pattern), the error message includes guidance to prevent infinite loops:

**prompts/error.txt** addition:

```
6. If the error contains "deny", "network", "Permission denied", or "sandbox" keywords,
   this is likely a sandbox restriction — do NOT retry. Ask the user to approve.
```

**prompts/glm/error.txt** addition:

```
6. 如果错误信息包含 "deny"、"network"、"Permission denied" 或 "sandbox" 等关键词，
   这很可能是沙箱安全限制——不要重试，请告知用户审批。
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `backend/app/security/sandbox/error_detector.py` | **NEW** | `SandboxErrorType`, `SandboxErrorInfo`, `SandboxErrorDetector` |
| `backend/app/security/command_effect_registry.py` | **MODIFY** | `CommandEffectEntry` add `often_needs_network: bool = False`; register ~15 commands |
| `backend/app/tools/shell_tool.py` | **MODIFY** | Error path detection; `_create_approval_result` extension; `_execute_decision` trust check; `_execute_argv`/`_execute_shell` accept elevation flags |
| `backend/app/security/session_trust_store.py` | **NO CHANGE** | `permission` is already `str`, supports new values |
| `backend/app/execution/prompts/error.txt` | **MODIFY** | Add sandbox restriction guidance |
| `backend/app/execution/prompts/glm/error.txt` | **MODIFY** | Add sandbox restriction guidance (Chinese) |
| `frontend/src/components/execution/ActionReceipt.tsx` | **MODIFY** | Add `SandboxNetworkDetail`, `SandboxPathDetail`; dispatch by `approval_kind` |
| `frontend/src/components/execution/receiptUtils.ts` | **MODIFY** | Add sandbox elevation payload types |

## Testing

### Backend Tests

- `test_sandbox_error_detector.py`:
  - Seatbelt "deny network" pattern → `SandboxErrorType.NETWORK_DENIED`, confidence=high
  - Seatbelt "deny file-read* (subpath ...)" pattern → `SandboxErrorType.PATH_DENIED`, extracted path, confidence=high
  - bwrap "Network is unreachable" + nonzero exit → `SandboxErrorType.NETWORK_DENIED`, confidence=medium
  - Exit code 0 → None (not sandbox error)
  - Unknown stderr + no registry match → None
  - `often_needs_network=True` + network error keyword → medium confidence

- `test_command_effect_registry.py` (extend):
  - `often_needs_network=True` entries present for pip, npm, cargo, go, docker

- `test_shell_tool.py` (extend):
  - `_create_approval_result` with `elevation=SandboxErrorInfo(...)` produces correct `approval_kind`
  - `_execute_approved_decision` with `elevation_request` sets elevation flags on decision
  - `_execute_argv` with `sandbox_allow_network=True` passes `allow_network=True` to sandbox
  - `_execute_argv` with `sandbox_extra_paths` extends `allowed_paths` for sandbox
  - Pre-execution trust check: `sandbox_network` trust → auto allow_network

### Frontend Tests

- `SandboxNetworkDetail` renders command + network denial message
- `SandboxPathDetail` renders command + denied paths
- `ApprovalCard` dispatches to correct detail component by `approval_kind`
- Button labels adapt by `approval_kind`

### Integration Tests

- `pip install` in sandbox → network denied → elevation approval → approve → retry with network → success
- Path access in sandbox → path denied → elevation approval → approve → retry with extra path → success
- Deny elevation → clear error returned, no retry
- "此会话允许网络" → subsequent network-needing command auto-elevated

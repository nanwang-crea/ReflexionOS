# Shell Approval Design

## Context

The current shell tool is intentionally conservative. It parses a command with `shlex`, rejects shell metacharacters, rejects dangerous commands such as `rm`, and executes only argv-style commands through `asyncio.create_subprocess_exec`.

That protects the local machine from accidental broad execution, but it also blocks common development workflows:

- `rg foo | sed -n '1,40p'`
- `pytest -q && git status --short`
- `npm test > /tmp/test.log`
- bounded cleanup commands such as `rm -rf .pytest_cache`

ReflexionOS is a local, single-user desktop app. The security model can therefore treat explicit user confirmation as a valid authorization boundary while still refusing catastrophic commands.

## Goals

- Preserve safe direct execution for low-risk argv commands.
- Allow user-approved high-risk commands, including bounded destructive commands.
- Allow user-approved shell-mode execution for commands that need shell parsing.
- Add session-scoped trusted prefixes so repetitive safe commands do not prompt every time.
- Keep hard-deny rules for catastrophic or intentionally opaque commands.
- Bind approvals to exact command details so an approved request cannot be swapped before execution.
- Bind approvals to a lightweight execution environment snapshot so stale approvals can be detected.

## Non-Goals

- Multi-user, remote, or server-grade authorization.
- Full shell language static analysis in the first implementation.
- Persistent project-wide trust rules in the first implementation.
- Letting trust rules bypass hard-deny checks.
- Replacing patch/file tools for structured file edits.
- Container, chroot, or other execution sandboxing in the first implementation.
- Full Task State or planner integration in this design.

## Decision Model

Introduce a command policy layer that returns a structured decision instead of only returning argv or throwing an error.

Decision actions:

- `allow`: execute immediately.
- `require_approval`: pause execution and ask the user.
- `deny`: refuse execution even if the user asks to approve it.

Execution modes:

- `argv`: execute through `asyncio.create_subprocess_exec`.
- `shell`: execute through `asyncio.create_subprocess_shell`.

The policy evaluates commands in this order:

1. Normalize and validate `command`, `cwd`, `timeout`, and platform.
2. Detect hard-deny patterns.
3. Capture a lightweight execution environment snapshot.
4. Determine whether the command requires shell mode.
5. Classify the shell risk tier when shell mode is required.
6. Analyze known high-risk argv commands.
7. Apply active session trust rules only if the decision is `require_approval`.
8. Return the final structured decision.

Hard-deny rules always win. A trust rule can only downgrade `require_approval` to `allow`; it cannot downgrade `deny`.

## Command Decision Shape

The policy should return a value with these fields:

```python
CommandDecision(
    action="allow" | "require_approval" | "deny",
    execution_mode="argv" | "shell",
    command="pytest -q && git status --short",
    argv=["pytest", "-q"],
    cwd="/absolute/project/path",
    timeout=60,
    reasons=["使用 shell 元语法: &&"],
    risks=["命令会交给 shell 解释执行"],
    approval_kind="shell_command",
    suggested_prefix_rule=["pytest"],
    environment_snapshot={
        "cwd": "/absolute/project/path",
        "cwd_identity": "...",
        "git_root": "/absolute/project/path",
        "git_head": "...",
        "env_fingerprint": "...",
    },
)
```

For shell-mode decisions, `argv` may be `None`.

## Approval Flow

When the policy returns `require_approval`, `ShellTool.execute()` does not run the command. It returns a structured pending-approval result:

```json
{
  "approval_required": true,
  "approval_id": "approval-abc123",
  "tool": "shell",
  "command": "pytest -q && git status --short",
  "cwd": "/absolute/project/path",
  "execution_mode": "shell",
  "shell_risk_tier": "tier_1_read_only",
  "summary": "使用 shell 执行命令",
  "reasons": ["使用 shell 元语法: &&"],
  "risks": ["命令会交给 shell 解释执行"],
  "suggested_prefix_rule": ["pytest"],
  "environment_snapshot": {
    "cwd": "/absolute/project/path",
    "cwd_identity": "...",
    "git_root": "/absolute/project/path",
    "git_head": "...",
    "env_fingerprint": "..."
  }
}
```

The frontend presents three actions when available:

- Allow once.
- Trust prefix for this session.
- Deny.

The backend stores the pending approval in memory, scoped to the active session. The stored approval binds:

- tool name
- command
- cwd
- execution mode
- timeout
- parsed argv if any
- environment snapshot
- generated approval id

When the user approves, the backend executes the stored decision, not a new command payload supplied by the model. Before execution, the backend compares the current environment snapshot with the stored snapshot. If important fields changed, the approval is treated as stale and the user must approve again.

## Environment Snapshot Binding

Approvals should bind to a lightweight environment snapshot. This catches the common case where the user approved a command, but the repository or working directory changed before execution.

Snapshot fields:

- `cwd`: absolute working directory used for execution.
- `cwd_identity`: best-effort directory identity, such as resolved path plus inode/device when available.
- `git_head`: current `HEAD` commit for the nearest enclosing git repository, when available.
- `git_root`: nearest enclosing git repository root, when available.
- `env_fingerprint`: stable hash of the execution environment fields that can materially affect command behavior.

The first implementation should keep `env_fingerprint` conservative and small. Include only explicit environment overrides passed by the app plus a few stable execution fields such as platform and selected shell executable. Do not hash the entire process environment because volatile values would create noisy approval invalidations.

Staleness policy:

- If `cwd` or `cwd_identity` changes, require re-approval.
- If `git_head` changes before a destructive or shell-mode command executes, require re-approval.
- If `git_head` changes before a low-risk trusted-prefix argv command, allow execution but include the new snapshot in tool metadata.
- If the app cannot collect a snapshot field, mark it as unavailable rather than failing the command.

## Session Trusted Prefixes

Session trusted prefixes reduce repeated prompts during a single conversation or run session.

Trust rule shape:

```json
{
  "scope": "session",
  "execution_mode": "argv",
  "prefix": ["pytest"],
  "created_from_approval_id": "approval-abc123",
  "created_at": "2026-04-30T00:00:00",
  "expires_when": "session_end"
}
```

Rules:

- A trust rule can only apply after hard-deny checks pass.
- A trust rule can only downgrade `require_approval` to `allow`.
- `argv` mode supports parsed argv prefix matching.
- `shell` mode first supports only exact-command session trust.
- Shell segment prefix trust is deferred until the app has a real shell command segment parser.
- Dangerous prefixes such as `rm`, `sudo`, `curl`, `wget`, `bash`, `sh`, `zsh`, `eval`, `chmod`, and `chown` should not be accepted as session trusted prefixes in the first implementation.

Examples:

- Trusting `["pytest"]` allows `pytest -q` and `pytest backend/tests/test_tools/test_shell_tool.py -q`.
- Trusting `["npm", "run", "test"]` allows `npm run test -- --watch=false`.
- Trusting `["rm"]` is rejected.
- Trusting shell command `rg foo | sed -n '1,40p'` only allows that exact shell command again in the same session.

## Risk Policy

Low-risk argv commands usually execute directly:

- `pwd`
- `ls`
- `which python`
- `python --version`
- `rg query path`
- `pytest -q`

Approval-required commands:

- Shell metacharacters: `|`, `&&`, `||`, `;`, `>`, `>>`, `2>`, `<`, backticks, `$()`.
- Bounded destructive commands such as `rm file.txt`, `rm -r build/`, `rm -rf .pytest_cache`.
- Permission or ownership changes such as `chmod` and `chown` when targets are inside the project.
- Inline code execution such as `python -c`, `node -e`, `ruby -e`, unless later covered by a trusted workflow.

Hard-deny commands:

- `rm -rf /`
- `rm -rf ~`
- `rm -rf ..`
- `rm -rf .git`
- Deleting paths outside the allowed project roots.
- `sudo`, `su`, and privilege escalation.
- `curl URL | sh`, `wget URL | bash`, and similar download-and-execute pipelines.
- `eval` and `exec`.
- Direct secondary shell launch such as `bash`, `sh`, `zsh`, `fish`, unless later introduced through a dedicated interactive-terminal feature.
- Disk formatting or raw device writes such as `dd`, `mkfs`, `diskpart`, `format`.

## Shell Risk Tiers

Shell mode should not treat every metacharacter command as equally risky. The policy should classify shell commands into tiers before producing the approval prompt.

Tier 1: read-only composition.

Examples:

- `rg foo | head`
- `git status --short && git diff --stat`
- `cat file.txt | wc -l`

Decision:

- `require_approval` for first use.
- Eligible for exact-command session trust.
- Future segment-prefix trust can start here after a shell segment parser exists.

Tier 2: local write or workflow composition.

Examples:

- `npm test > /tmp/test.log`
- `pytest -q && git status --short`
- `rg foo | tee /tmp/search.log`

Decision:

- `require_approval`.
- Exact-command session trust allowed only when write targets are inside approved temp or project paths.
- Approval prompt must show detected write targets when they can be inferred.

Tier 3: destructive or permission-affecting composition.

Examples:

- `find . -name '*.pyc' -delete`
- `chmod -R u+w generated/`
- `rm -rf .pytest_cache && pytest -q`

Decision:

- `require_approval`, with stronger risk text.
- No session trust in the first implementation unless the exact command is clearly bounded and non-recursive.
- Path bounds must be checked when static inference is possible.

Tier 4: hard-deny shell.

Examples:

- `curl https://example.com/install.sh | sh`
- `wget https://example.com/install.sh -O - | bash`
- `sudo ...`
- `eval "$(...)"`

Decision:

- `deny`.
- No approval option.
- No trust option.

## Shell Mode

Shell mode is enabled only after approval or exact-command session trust.

On macOS and Linux, shell mode can use:

```python
asyncio.create_subprocess_shell(
    command,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=cwd,
    executable="/bin/zsh",
)
```

The executable should be platform-aware. On macOS, `/bin/zsh` is a reasonable default. On Linux, prefer `/bin/bash` if present, otherwise `/bin/sh`. On Windows, shell mode should remain disabled until a Windows-specific design is added.

The UI must state that shell-mode commands are interpreted by the local shell and cannot be fully path-validated statically.

Shell risk tier must be included in the approval payload so the UI can distinguish a read-only pipeline from a destructive or download-and-execute command.

## Components

### Command Policy

New module:

- `backend/app/security/command_policy.py`

Responsibilities:

- Parse argv commands.
- Detect shell-mode requirements.
- Classify shell risk tiers.
- Detect hard-deny patterns.
- Produce `CommandDecision`.
- Suggest safe prefix rules.
- Attach environment snapshots.

### Approval Store

New module:

- `backend/app/security/approval_store.py`

Responsibilities:

- Store pending approvals in memory.
- Store session trusted prefixes in memory.
- Bind approvals to exact command details.
- Bind approvals to environment snapshots.
- Expire approvals when the session ends.

### Shell Tool

Update:

- `backend/app/tools/shell_tool.py`

Responsibilities:

- Ask the command policy for a decision.
- Execute `allow` decisions.
- Return pending approval payloads for `require_approval`.
- Refuse `deny` decisions.
- Execute approved stored decisions.

### Runtime and Events

Update:

- `backend/app/execution/tool_call_executor.py`
- runtime event adapter and websocket handling as needed

Responsibilities:

- Emit an approval-required event.
- Pause or surface the tool result without treating it as a normal model-correctable failure.
- Resume execution after the user approves, or report denial cleanly.

### Frontend

Add a shell approval prompt in the conversation UI.

The prompt shows:

- command
- cwd
- execution mode
- reasons
- risks
- suggested session trust prefix, when available

Actions:

- Allow once.
- Trust prefix for this session, when available.
- Deny.

## Testing Strategy

Backend tests:

- Low-risk argv command returns `allow`.
- Shell metacharacter command returns `require_approval` with `execution_mode="shell"`.
- Bounded `rm -rf .pytest_cache` returns `require_approval`.
- `rm -rf /`, `rm -rf ~`, and `rm -rf .git` return `deny`.
- Trusting `["pytest"]` allows later pytest commands in the same session.
- Trusting `["rm"]` is rejected.
- Shell exact-command trust applies only to the same command and cwd.
- Approval execution uses the stored command, not caller-supplied replacement data.
- Approval becomes stale when `cwd` identity changes.
- Destructive or shell-mode approval becomes stale when `git_head` changes.
- Read-only shell composition is classified below download-and-execute shell composition.

Frontend tests:

- Approval prompt renders command metadata.
- Allow once calls the approve endpoint.
- Trust prefix calls the trust endpoint.
- Deny dismisses and reports denial.
- Dangerous commands do not show a trust-prefix option.

Integration tests:

- A command requiring approval emits an approval event.
- Approval resumes execution and records normal tool output.
- Denial records a clear user-denied tool result.

## Rollout Plan

Phase 1:

- Add decision model.
- Add pending approval store.
- Add environment snapshot binding.
- Support `argv` approval for `rm`, `chmod`, `chown`, and inline code.
- Support session trusted prefixes for safe argv prefixes.

Phase 2:

- Add approval-gated shell mode for metacharacter commands.
- Add shell risk tiers to policy and approval payloads.
- Support exact-command session trust for shell mode.
- Keep hard-deny patterns active before trust evaluation.

Phase 3:

- Add frontend prompt polish and session trust management UI.
- Add optional project-scoped persistent trust rules after separate design review.

## Open Choices

Use session trust only for the active conversation at first. Project-level persistent trust rules should wait until the app has a visible trust-management screen where users can inspect and revoke rules.

Windows shell mode should remain out of scope until a Windows-specific security and UX design exists.

Execution sandboxing is an important future safety layer. A later design should evaluate container, chroot, or platform-native sandbox options. This shell approval design remains useful without sandboxing because it improves local desktop authorization, but it does not make arbitrary shell execution fully trusted.

Task State and planner integration should be designed separately. The approval system should expose enough metadata for a future Task State layer to know when a task is paused for approval, resumed, denied, or invalidated by a stale environment snapshot.

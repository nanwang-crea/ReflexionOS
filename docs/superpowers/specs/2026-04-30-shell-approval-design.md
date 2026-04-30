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

## Non-Goals

- Multi-user, remote, or server-grade authorization.
- Full shell language static analysis in the first implementation.
- Persistent project-wide trust rules in the first implementation.
- Letting trust rules bypass hard-deny checks.
- Replacing patch/file tools for structured file edits.

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
3. Determine whether the command requires shell mode.
4. Analyze known high-risk argv commands.
5. Apply active session trust rules only if the decision is `require_approval`.
6. Return the final structured decision.

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
  "summary": "使用 shell 执行命令",
  "reasons": ["使用 shell 元语法: &&"],
  "risks": ["命令会交给 shell 解释执行"],
  "suggested_prefix_rule": ["pytest"]
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
- generated approval id

When the user approves, the backend executes the stored decision, not a new command payload supplied by the model.

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

## Components

### Command Policy

New module:

- `backend/app/security/command_policy.py`

Responsibilities:

- Parse argv commands.
- Detect shell-mode requirements.
- Detect hard-deny patterns.
- Produce `CommandDecision`.
- Suggest safe prefix rules.

### Approval Store

New module:

- `backend/app/security/approval_store.py`

Responsibilities:

- Store pending approvals in memory.
- Store session trusted prefixes in memory.
- Bind approvals to exact command details.
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
- Support `argv` approval for `rm`, `chmod`, `chown`, and inline code.
- Support session trusted prefixes for safe argv prefixes.

Phase 2:

- Add approval-gated shell mode for metacharacter commands.
- Support exact-command session trust for shell mode.
- Keep hard-deny patterns active before trust evaluation.

Phase 3:

- Add frontend prompt polish and session trust management UI.
- Add optional project-scoped persistent trust rules after separate design review.

## Open Choices

Use session trust only for the active conversation at first. Project-level persistent trust rules should wait until the app has a visible trust-management screen where users can inspect and revoke rules.

Windows shell mode should remain out of scope until a Windows-specific security and UX design exists.

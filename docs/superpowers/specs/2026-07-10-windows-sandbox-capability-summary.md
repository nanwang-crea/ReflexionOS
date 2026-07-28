# Windows Sandbox Capability Summary

## Purpose

This document summarizes the current Windows sandbox capability after Phase 2 completion, and compares it with the existing macOS and Linux sandbox paths.

It is a capability boundary note, not a new design source of truth. The implementation source of truth remains in backend code and the Phase 2 design doc.

## Short Answer

Windows is now much closer to macOS/Linux than before:

- Windows can now execute many local commands inside a real sandboxed path instead of relying on the old `git-only` fallback behavior.
- Windows still does not mean "everything is fully equivalent to macOS/Linux".
- The main remaining differences are around sandbox mechanism shape and how network restriction is enforced.

So the correct statement is:

Windows is now close in day-to-day command capability, but not yet fully identical to macOS/Linux in isolation semantics.

## What Changed On Windows

Before Phase 2:

- Windows shell commands with metacharacters were heavily constrained by the first-stage fallback whitelist.
- Many commands only worked on the non-shell argv path.
- Allowed commands were effectively running without real OS-level isolation.

After Phase 2:

- Windows now has a `WindowsSandbox` provider selected by the sandbox factory on `win32`.
- `ShellTool` prefers `sandbox.run_command()` and `sandbox.run_shell_command()` on Windows when the sandbox is available.
- The old Windows `git-only` shell whitelist is now fallback-only behavior and applies when sandbox is unavailable.
- Session-level `PermissionMode` is wired through runtime and affects local approval semantics on Windows as designed.

## Current Windows Behavior

### 1. Local command execution

When the Windows sandbox is available:

- many local argv commands can run in the Windows sandbox
- many shell commands can also run in the Windows sandbox
- pipeline-style commands are no longer blocked just because they are shell-shaped

Examples of behavior now covered by tests:

- `dir` in `AUTO` mode is not denied
- `dir | findstr foo` in `AUTO` mode is not denied
- `runas ...` remains denied even in `YOLO`
- `YOLO` with no sandbox available is denied rather than fail-open

### 2. Path boundary

Windows now has a real execution path using:

- Restricted Token
- ACL-based write boundary
- `CreateProcessAsUser`

This is materially stronger than the old fallback-only model. Commands are no longer just "policy-allowed then naked".

### 3. Network behavior

Windows is still not "network fully open".

- `PermissionMode` does not bypass network approval.
- `NETWORK_OUT` still stays on approval semantics.
- When sandbox is unavailable, Windows shell network commands are still rejected on the fallback path.

This means:

- `YOLO` means local approval is relaxed
- `YOLO` does not mean network is silently unrestricted

### 4. Fallback behavior

When the Windows sandbox is unavailable:

- the old first-stage Windows shell whitelist becomes active again
- this is still a safety fallback, not the preferred steady-state path

## Compared With macOS And Linux

## Similarities

Windows is now similar to macOS/Linux in these important ways:

- there is a platform sandbox provider selected by the common factory
- command execution prefers the sandbox runtime instead of fallback wrapping
- unsupported or unavailable sandbox paths fall back safely instead of pretending isolation exists
- local command permission decisions are now aligned with the same `PermissionMode` model

In practical product terms, this means Windows is no longer a clearly crippled path relative to macOS/Linux for ordinary local command execution.

## Differences

Windows is still not identical to macOS/Linux:

- macOS uses Seatbelt profile wrapping
- Linux uses Landlock/bwrap-style wrapping
- Windows uses Restricted Token plus ACL plus `CreateProcessAsUser`

So the platform mechanisms are different even though the high-level product goal is now similar.

The most important remaining behavioral difference is:

- macOS/Linux already had mature provider-based sandbox execution earlier
- Windows only now caught up on real local execution isolation, and its network control story is still more conditional than "perfectly identical across all platforms"

## Practical Guidance

For current team communication, the safe wording is:

- Windows sandbox support is now production-shaped for many local commands.
- Windows is broadly aligned with macOS/Linux on local sandboxed execution.
- Windows should not yet be described as "fully identical to macOS/Linux in every isolation detail".

Avoid saying:

- Windows can now run any command without restriction
- Windows is now exactly the same as macOS/Linux
- YOLO on Windows means networking is also fully open

Prefer saying:

- Windows can now run many more commands in a real sandbox
- the old `git-only` behavior is now fallback-only
- path isolation is real; network semantics still keep approval boundaries

## Code Pointers

- `backend/app/security/sandbox/factory.py`
- `backend/app/security/sandbox/windows.py`
- `backend/app/tools/shell_tool.py`
- `backend/app/security/permission_mode.py`
- `backend/app/security/command_policy.py`

## Test Pointers

- `backend/tests/test_security/test_sandbox_windows.py`
- `backend/tests/test_security/test_sandbox_windows_integration.py`
- `backend/tests/test_security/test_permission_mode.py`
- `backend/tests/test_security/test_command_policy_sandbox_conditional.py`

# backend/app/security/command_policy.py
import logging
import os
import shlex
import subprocess

from pydantic import BaseModel, Field

from app.security.command_effect_registry import CommandEffectRegistry
from app.security.effect_category import EffectCategory, EFFECT_DANGER_LEVEL, EFFECT_ACTION_MAP, most_dangerous, CommandAction
from app.security.path_security import PathSecurity, SecurityError
from app.security.shell_security import ShellSecurity, ShellSecurityError

logger = logging.getLogger(__name__)


class EnvironmentSnapshot(BaseModel):
    cwd: str
    cwd_identity: str | None = None
    git_root: str | None = None
    git_head: str | None = None
    env_fingerprint: str | None = None


class CommandDecision(BaseModel):
    action: CommandAction
    execution_mode: str = "argv"
    command: str
    argv: list[str] | None = None
    cwd: str | None = None
    timeout: int = 600
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    approval_kind: str = "shell_command"
    suggested_prefix_rule: list[str] | None = None
    environment_snapshot: EnvironmentSnapshot | None = None
    effect_category: EffectCategory | None = None


# ── Hard deny patterns (preserved) ───────────────────────────────

HARD_DENY_PATTERNS: list[tuple[list[str], str]] = [
    (["rm", "-rf", "/"], "递归删除根目录"),
    (["rm", "-rf", "~"], "递归删除用户主目录"),
    (["rm", "-rf", "--"], "递归删除根目录(--分隔)"),
    (["rm", "-rf", ".."], "递归删除上级目录"),
    (["rm", "-rf", ".git"], "递归删除 .git 目录"),
]

HARD_DENY_SHELL_PATTERNS: set[str] = {"curl", "wget"}

# Shell interpreters whose -c flag means CODE_GEN
SHELL_INTERPRETERS = {"bash", "sh", "zsh", "fish", "ksh", "csh"}

# Inline eval flags that prevent file-argument downgrade
INLINE_EVAL_FLAGS = {"-c", "-e", "--eval"}


def _capture_environment_snapshot(cwd: str) -> EnvironmentSnapshot:
    cwd_identity: str | None = None
    try:
        stat = os.stat(cwd)
        cwd_identity = f"{stat.st_dev}:{stat.st_ino}"
    except OSError:
        pass

    git_root: str | None = None
    git_head: str | None = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, timeout=2,
        )
        if result.returncode == 0:
            git_root = result.stdout.strip()
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=2,
        )
        if result.returncode == 0:
            git_head = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    env_fingerprint: str | None = None
    try:
        import hashlib
        parts = [cwd, os.name]
        h = hashlib.sha256(":".join(parts).encode()).hexdigest()[:12]
        env_fingerprint = h
    except Exception:
        pass

    return EnvironmentSnapshot(
        cwd=cwd,
        cwd_identity=cwd_identity,
        git_root=git_root,
        git_head=git_head,
        env_fingerprint=env_fingerprint,
    )


class CommandPolicy:
    """Evaluates shell commands and returns structured decisions based on effect classification."""

    def __init__(self, shell_security: ShellSecurity, path_security: PathSecurity,
                 registry: CommandEffectRegistry | None = None):
        self.shell_security = shell_security
        self.path_security = path_security
        self.registry = registry or CommandEffectRegistry()

    def evaluate(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> CommandDecision:
        command_normalized = command.strip()
        if not command_normalized:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                reasons=["命令不能为空"],
            )

        resolved_cwd = cwd or "."
        try:
            resolved_cwd = self.path_security.validate_path(resolved_cwd)
        except SecurityError as e:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                cwd=cwd,
                reasons=[f"cwd 不在允许范围内: {e}"],
            )

        timeout = timeout or 600
        snapshot = _capture_environment_snapshot(resolved_cwd)

        # Parse command using ShellSecurity (without path validation — we handle that ourselves)
        try:
            result = self.shell_security.validate_command(command_normalized)
        except ShellSecurityError as e:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=[str(e)],
                environment_snapshot=snapshot,
            )

        if result.has_meta and self.shell_security._is_windows():
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=["Windows shell 模式尚未支持"],
                environment_snapshot=snapshot,
            )

        if result.has_meta:
            return self._evaluate_shell_command(
                command_normalized, resolved_cwd, timeout, snapshot
            )

        return self._evaluate_argv_command(
            command_normalized, result.argv, resolved_cwd, timeout, snapshot
        )

    # ── Shell command evaluation (pipe chains, redirects) ──────────

    def _evaluate_shell_command(
        self,
        command: str,
        cwd: str,
        timeout: int,
        snapshot: EnvironmentSnapshot,
    ) -> CommandDecision:
        # 1. Hard deny: curl/wget | sh/bash
        try:
            tokens = shlex.split(command, posix=not self.shell_security._is_windows())
        except ValueError:
            tokens = []

        first_token = tokens[0] if tokens else ""
        first_cmd = self.shell_security._command_name(first_token) if first_token else ""

        # Check for download-and-execute patterns
        if first_cmd in HARD_DENY_SHELL_PATTERNS and "|" in command:
            pipe_parts = command.split("|")
            for part in pipe_parts[1:]:
                try:
                    part_tokens = shlex.split(part.strip())
                    if part_tokens:
                        target_cmd = self.shell_security._command_name(part_tokens[0])
                        if target_cmd in SHELL_INTERPRETERS:
                            return CommandDecision(
                                action=CommandAction.DENY,
                                command=command,
                                execution_mode="shell",
                                cwd=cwd,
                                timeout=timeout,
                                reasons=[f"下载后执行管道: {first_cmd} | {target_cmd}"],
                                risks=["下载的代码会在本地 shell 中执行，无法静态校验"],
                                environment_snapshot=snapshot,
                                effect_category=EffectCategory.ESCALATE,
                            )
                except ValueError:
                    continue

        # 2. Classify the entire shell command (pipes, &&/||, ;, redirects)
        effect = self._classify_shell_command(command)

        # 3. Determine action based on effect classification
        #    - &&/|| chains are treated like pipes: split, classify each, aggregate
        #    - Command substitution $() and backticks always require approval (cannot statically validate)
        #    - Redirects >/>/> always add WRITE_PROJECT but are still effect-classified
        has_unvalidated_meta = any([
            "$(" in command or "`" in command,  # Command substitution — cannot statically validate
        ])

        if effect == EffectCategory.ESCALATE:
            action = CommandAction.DENY
        elif has_unvalidated_meta:
            # Command substitution content is opaque → always require approval
            action = CommandAction.REQUIRE_APPROVAL
        else:
            # All other shell commands use effect-based action map
            action = EFFECT_ACTION_MAP[effect]

        # 3. Build reasons and risks
        reasons = []
        if "|" in command:
            reasons.append("使用管道: |")
        if "&&" in command or "||" in command:
            reasons.append("使用链式操作: &&或||")
        if ";" in command:
            reasons.append("使用分号: ;")
        if ">" in command or ">>" in command:
            reasons.append("使用重定向: >或>>")
        if "$(" in command or "`" in command:
            reasons.append("使用命令替换")
        if "2>" in command:
            reasons.append("使用错误重定向: 2>")

        risks = []
        if has_unvalidated_meta:
            risks.append("命令会交给本地 shell 解释执行，包含命令替换，无法完全静态校验")
        elif effect in (EffectCategory.WRITE_SYSTEM, EffectCategory.DESTRUCTIVE,
                        EffectCategory.NETWORK_OUT, EffectCategory.CODE_GEN,
                        EffectCategory.UNKNOWN):
            risks.append("命令会交给本地 shell 解释执行，无法完全静态校验路径安全")

        approval_kind = "shell_command"

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
            environment_snapshot=snapshot,
            effect_category=effect,
        )

    # ── Argv command evaluation ────────────────────────────────────

    def _evaluate_argv_command(
        self,
        command: str,
        argv: list[str],
        cwd: str,
        timeout: int,
        snapshot: EnvironmentSnapshot,
    ) -> CommandDecision:
        command_name = self.shell_security._command_name(argv[0])

        # 1. Hard deny patterns
        for pattern, reason in HARD_DENY_PATTERNS:
            if len(argv) >= len(pattern) and argv[:len(pattern)] == pattern:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="argv",
                    argv=argv,
                    cwd=cwd,
                    timeout=timeout,
                    reasons=[reason],
                    environment_snapshot=snapshot,
                )

        # Additional rm -rf checks
        if command_name == "rm" and ("-rf" in argv or "-fr" in argv):
            target_idx = None
            for i, arg in enumerate(argv[1:], 1):
                if not arg.startswith("-"):
                    target_idx = i
                    break
            if target_idx is not None:
                target = argv[target_idx]
                target_resolved = os.path.expanduser(target)
                if target_resolved in {"/", "~", ".."} or target_resolved.endswith("/.git") or target == ".git":
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="argv",
                        argv=argv,
                        cwd=cwd,
                        timeout=timeout,
                        reasons=[f"禁止递归删除: {target}"],
                        environment_snapshot=snapshot,
                    )

        # 2. Classify using registry
        effect = self._classify_argv_command(argv)
        action = EFFECT_ACTION_MAP[effect]

        # 3. Build decision details based on effect
        reasons = []
        risks = []
        approval_kind = "argv_approval"

        if effect == EffectCategory.DESTRUCTIVE:
            reasons.append(f"破坏性命令: {command_name}")
            if command_name == "rm" and "-rf" in argv:
                risks.append("递归强制删除")
            elif command_name == "rm":
                risks.append("删除文件")
            elif command_name in {"chmod", "chown"}:
                risks.append("修改文件权限或所有权")
        elif effect == EffectCategory.NETWORK_OUT:
            reasons.append(f"网络请求命令: {command_name}")
            risks.append("可能向外部发送数据")
        elif effect == EffectCategory.WRITE_SYSTEM:
            reasons.append(f"系统级写入: {command_name}")
            risks.append("修改系统状态")
        elif effect == EffectCategory.CODE_GEN:
            reasons.append(f"内联代码执行: {command_name}")
            risks.append("内联代码无法静态校验")
        elif effect == EffectCategory.ESCALATE:
            reasons.append(f"禁止执行: {command_name}")
        elif effect == EffectCategory.UNKNOWN:
            reasons.append(f"未知命令: {command_name}")
            risks.append("未注册命令，无法判断效果")

        # 4. Validate paths for non-DENY decisions
        if action != CommandAction.DENY:
            if command_name not in self.shell_security.NON_PATH_ARGUMENT_COMMANDS:
                path_error = self._validate_argv_paths(argv[1:], command_name)
                if path_error:
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="argv",
                        argv=argv,
                        cwd=cwd,
                        timeout=timeout,
                        reasons=[path_error],
                        environment_snapshot=snapshot,
                    )

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
            environment_snapshot=snapshot,
            effect_category=effect,
        )

    # ── Effect classification helpers ──────────────────────────────

    def _classify_argv_command(self, argv: list[str]) -> EffectCategory:
        """Classify an argv command using the registry with override resolution."""
        command_name = self.shell_security._command_name(argv[0])
        entry = self.registry.lookup(command_name)

        if entry is None:
            return EffectCategory.UNKNOWN

        # Start with base category
        effect = entry.category

        # Check flag overrides first (e.g., python -c → CODE_GEN, python --version → READ_ONLY)
        # Collect all matching flag overrides and pick the most dangerous one
        flag_effects: list[EffectCategory] = []
        for arg in argv[1:]:
            if arg in entry.flag_overrides:
                flag_effects.append(entry.flag_overrides[arg])
        if flag_effects:
            effect = most_dangerous(flag_effects)

        # Check subcommand overrides (e.g., git push → NETWORK_OUT)
        if entry.allow_subcommands and len(argv) >= 2:
            subcmd = argv[1]
            if not subcmd.startswith("-") and subcmd in entry.subcommand_overrides:
                subcmd_effect = entry.subcommand_overrides[subcmd]
                if EFFECT_DANGER_LEVEL[subcmd_effect] > EFFECT_DANGER_LEVEL[effect]:
                    effect = subcmd_effect

        # Shell interpreter override: bash script.sh → WRITE_PROJECT
        if command_name in SHELL_INTERPRETERS:
            effect = self._shell_interpreter_override(command_name, argv, effect)

        return effect

    def _shell_interpreter_override(
        self, command_name: str, argv: list[str], current_effect: EffectCategory
    ) -> EffectCategory:
        """Override shell interpreter classification based on arguments.

        Rules:
        1. If -c/-e/--eval present → CODE_GEN (no override)
        2. If a non-flag argument looks like a file path → WRITE_PROJECT
        3. Otherwise → keep current effect (ESCALATE → DENY)
        """
        # Check for inline eval flags first
        for arg in argv[1:]:
            if arg in INLINE_EVAL_FLAGS:
                return EffectCategory.CODE_GEN

        # Check for file-like argument
        for arg in argv[1:]:
            if not arg.startswith("-"):
                if self.shell_security._looks_like_path(arg):
                    return EffectCategory.WRITE_PROJECT
                # Also treat script-name-like args with dots or slashes
                if "." in arg or "/" in arg:
                    return EffectCategory.WRITE_PROJECT

        return current_effect

    def _classify_shell_command(self, command: str) -> EffectCategory:
        """Classify a shell command containing pipes, &&/||, ;, and redirects.

        Splits by |, &&, ||, and ; — classifies each segment independently,
        then returns the most dangerous effect category.
        Redirects (>, >>, 2>) add WRITE_PROJECT to the effect list.
        """
        effects: list[EffectCategory] = []

        # Detect redirects → WRITE_PROJECT
        if ">" in command or ">>" in command or "2>" in command:
            effects.append(EffectCategory.WRITE_PROJECT)

        # Split by all shell operators (|, &&, ||, ;) and classify each segment
        segments = self._split_shell_chain(command)
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                seg_argv = shlex.split(segment, posix=True)
                if seg_argv:
                    seg_effect = self._classify_argv_command(seg_argv)
                    effects.append(seg_effect)
            except ValueError:
                effects.append(EffectCategory.UNKNOWN)

        if not effects:
            return EffectCategory.UNKNOWN

        return most_dangerous(effects)

    def _split_shell_chain(self, command: str) -> list[str]:
        """Split a shell command by |, &&, ||, and ; respecting basic quoting.

        This handles the most common shell metacharacters that chain commands.
        Each resulting segment is a single command that can be classified independently.
        """
        segments: list[str] = []
        current: list[str] = []
        in_single = False
        in_double = False

        i = 0
        while i < len(command):
            ch = command[i]

            # Handle quoting
            if ch == "'" and not in_double:
                in_single = not in_single
                current.append(ch)
                i += 1
                continue
            elif ch == '"' and not in_single:
                in_double = not in_double
                current.append(ch)
                i += 1
                continue

            # Only split on metacharacters outside quotes
            if not in_single and not in_double:
                # Check for && (must check before single &)
                if ch == '&' and i + 1 < len(command) and command[i + 1] == '&':
                    segments.append(''.join(current))
                    current = []
                    i += 2  # Skip both &
                    continue
                # Check for || (must check before single |)
                elif ch == '|' and i + 1 < len(command) and command[i + 1] == '|':
                    segments.append(''.join(current))
                    current = []
                    i += 2  # Skip both |
                    continue
                # Check for | (single pipe)
                elif ch == '|':
                    segments.append(''.join(current))
                    current = []
                    i += 1
                    continue
                # Check for ; (semicolon)
                elif ch == ';':
                    segments.append(''.join(current))
                    current = []
                    i += 1
                    continue

            current.append(ch)
            i += 1

        if current:
            segments.append(''.join(current))

        return segments

    def _validate_argv_paths(self, args: list[str], command_name: str) -> str | None:
        try:
            self.shell_security._validate_path_arguments(args, self.path_security)
            return None
        except Exception as e:
            return str(e)

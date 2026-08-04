import logging
import os
import re
import shlex
import subprocess

from pydantic import BaseModel, Field

from app.errors import SecurityError
from app.security.command_arity import extract_prefix_rules
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.effect_category import (
    EFFECT_DANGER_LEVEL,
    CommandAction,
    EffectCategory,
    most_dangerous,
)
from app.security.path_security import PathSecurity
from app.security.permission_mode import PermissionMode, resolve_action
from app.security.session_trust_store import SessionTrustStore
from app.security.shell_security import ShellSecurity

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

# Download-and-execute shells are denied separately because the risky part
# is the composition (curl|bash / wget|sh), not just the first command token.
HARD_DENY_SHELL_PATTERNS: set[str] = {"curl", "wget"}

# Shell interpreters whose -c flag means CODE_GEN
SHELL_INTERPRETERS = {"bash", "sh", "zsh", "fish", "ksh", "csh"}

# Windows 解释器：powershell/pwsh 的 -Command、cmd 的 /c 语义上等价于 bash -c，
# 同样交给 _shell_interpreter_override 判断（是否降级为 CODE_GEN/WRITE_PROJECT）
WINDOWS_SHELL_INTERPRETERS = {"powershell", "pwsh", "cmd"}

# Inline eval flags that prevent file-argument downgrade
INLINE_EVAL_FLAGS = {
    "-c", "-e", "--eval",
    "-Command", "-command", "-EncodedCommand", "-encodedcommand",
    "/c", "/C", "/k", "/K",
}


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
    """Classify a shell command and return the execution decision.

    The policy pipeline is: parse -> classify -> validate paths -> map the
    effect into allow / approval / deny. Splitting those responsibilities keeps
    the command registry reusable while still letting the shell path enforce
    platform-specific safety rules.
    """

    def __init__(self, shell_security: ShellSecurity, path_security: PathSecurity,
                 registry: CommandEffectRegistry | None = None,
                 trust_store: SessionTrustStore | None = None,
                 session_id: str | None = None,
                 permission_mode: PermissionMode = PermissionMode.AUTO,
                 sandbox_available: bool = False):
        self.shell_security = shell_security
        self.path_security = path_security
        self.registry = registry or CommandEffectRegistry()
        self.trust_store = trust_store
        self._session_id = session_id
        self.permission_mode = permission_mode
        self.sandbox_available = sandbox_available

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
        except SecurityError as e:
            if not (e.detail and e.detail.get("source") == "shell"):
                raise
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=[str(e)],
                environment_snapshot=snapshot,
            )

        if result.has_meta and self.shell_security._is_windows() and not self.sandbox_available:
            # ========== Windows 第一阶段：严格白名单策略（沙盒不可用时）==========
            # 原因：Windows 无 sandbox.wrap_shell_command，无法约束命令内自由路径参数
            # 条件：sandbox_available=True 时旁路第一阶段，改由第二阶段沙盒执行流处理
            # 策略：(1) 只放行纯读的 git 子命令；(2) 复用 shell_security._validate_path_arguments 校验路径参数

            # 检查元字符：第一阶段只支持 && 和 ||（命令链）
            supported_on_windows = {'&&', '||'}
            unsupported_on_windows = {'|', '<', '>', '>>', '2>', '&', ';'}

            used_meta = self._extract_meta_chars(command_normalized)
            unsupported_used = used_meta & unsupported_on_windows

            if unsupported_used:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    cwd=resolved_cwd,
                    timeout=timeout,
                    reasons=[f"Windows 第一阶段不支持这些 shell 特性：{', '.join(unsupported_used)}"],
                    environment_snapshot=snapshot,
                )

            # 拆分命令链（按 && 和 || 拆）
            segments = self._split_shell_command(command_normalized)

            for segment in segments:
                segment_normalized = segment.strip()

                # 检查是否是 git 命令
                if not segment_normalized.startswith('git '):
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="shell",
                        cwd=resolved_cwd,
                        timeout=timeout,
                        reasons=[f"Windows 第一阶段只支持 git 命令，不支持: {segment_normalized}"],
                        environment_snapshot=snapshot,
                    )

                # 解析命令为 argv（用于后续路径校验）
                try:
                    segment_argv = shlex.split(segment_normalized, posix=False)  # Windows 用非 POSIX 模式
                except ValueError as e:
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="shell",
                        cwd=resolved_cwd,
                        timeout=timeout,
                        reasons=[f"命令解析失败: {e}"],
                        environment_snapshot=snapshot,
                    )

                if len(segment_argv) < 2:
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="shell",
                        cwd=resolved_cwd,
                        timeout=timeout,
                        reasons=["git 命令缺少子命令"],
                        environment_snapshot=snapshot,
                    )

                git_subcommand = segment_argv[1]

                # 严格白名单：只允许纯读的子命令（无 -D/-m/add/remove 等写操作）
                # 注意：不允许 branch、remote（它们有写子命令）
                allowed_pure_read_subcommands = {'status', 'log', 'diff', 'show'}

                if git_subcommand not in allowed_pure_read_subcommands:
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="shell",
                        cwd=resolved_cwd,
                        timeout=timeout,
                        reasons=[f"Windows 第一阶段只支持纯读 git 命令，不支持: git {git_subcommand}"],
                        environment_snapshot=snapshot,
                    )

                # 路径参数校验：复用 shell_security._validate_path_arguments
                # 这会校验命令中所有看起来像路径的参数（segment_argv[2:] 是 git 子命令的参数）
                try:
                    self.shell_security._validate_path_arguments(segment_argv[2:], self.path_security)
                except SecurityError as e:
                    return CommandDecision(
                        action=CommandAction.DENY,
                        command=command,
                        execution_mode="shell",
                        cwd=resolved_cwd,
                        timeout=timeout,
                        reasons=[f"路径参数不在允许范围: {e}"],
                        environment_snapshot=snapshot,
                    )

            # 通过白名单检查：继续走 shell 执行流程
            # 注意：macOS/Linux 的逻辑不修改

        # Commands with shell metacharacters are evaluated as full shell
        # expressions; plain argv commands can use tighter per-argument checks.
        if result.has_meta:
            return self._evaluate_shell_command(
                command_normalized, resolved_cwd, timeout, snapshot
            )

        return self._evaluate_argv_command(
            command_normalized, result.argv, resolved_cwd, timeout, snapshot
        )

    # ── Shell command evaluation (pipe chains, redirects) ──────────

    def _extract_meta_chars(self, command: str) -> set[str]:
        """
        提取命令中的 shell 元字符（quote-aware，忽略引号内的字符）

        Args:
            command: shell 命令字符串

        Returns:
            使用的元字符集合（如 {'&&', '||', '>'}）
        """
        meta_chars = set()

        # 使用状态机跟踪引号边界
        in_single_quote = False
        in_double_quote = False
        i = 0

        while i < len(command):
            char = command[i]

            # 跟踪引号状态
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                i += 1
                continue
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                i += 1
                continue

            # 在引号内，跳过
            if in_single_quote or in_double_quote:
                i += 1
                continue

            # 检查双字符元字符（&&、||、>>、2>）
            if i + 1 < len(command):
                two_char = command[i:i+2]
                if two_char in {'&&', '||', '>>', '2>'}:
                    meta_chars.add(two_char)
                    i += 2
                    continue

            # 检查单字符元字符
            if char in {'|', '<', '>', ';', '&'}:
                meta_chars.add(char)

            i += 1

        return meta_chars

    def _split_shell_command(self, command: str) -> list[str]:
        """
        按 && 和 || 拆分命令链（quote-aware）

        Args:
            command: shell 命令字符串

        Returns:
            命令片段列表
        """
        segments = []
        current_segment = []
        in_single_quote = False
        in_double_quote = False
        i = 0

        while i < len(command):
            char = command[i]

            # 跟踪引号状态
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                current_segment.append(char)
                i += 1
                continue
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                current_segment.append(char)
                i += 1
                continue

            # 在引号内，直接添加
            if in_single_quote or in_double_quote:
                current_segment.append(char)
                i += 1
                continue

            # 检查 && 或 ||
            if i + 1 < len(command):
                two_char = command[i:i+2]
                if two_char in {'&&', '||'}:
                    # 保存当前片段
                    segment_str = ''.join(current_segment).strip()
                    if segment_str:
                        segments.append(segment_str)
                    current_segment = []
                    i += 2
                    continue

            # 普通字符
            current_segment.append(char)
            i += 1

        # 保存最后一个片段
        segment_str = ''.join(current_segment).strip()
        if segment_str:
            segments.append(segment_str)

        return segments

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
            action = resolve_action(self.permission_mode, effect, sandbox_available=self.sandbox_available)

        # 3. Build reasons and risks (using quote-aware operator detection)
        reasons = []
        operators = self._detect_shell_operators(command)
        if operators.get("pipe"):
            reasons.append("使用管道: |")
        if operators.get("chain"):
            reasons.append("使用链式操作: &&或||")
        if operators.get("semicolon"):
            reasons.append("使用分号: ;")
        if operators.get("redirect") or operators.get("append_redirect"):
            reasons.append("使用重定向: >或>>")
        if has_unvalidated_meta:
            reasons.append("使用命令替换")
        if operators.get("stderr_redirect"):
            reasons.append("使用错误重定向: 2>")

        risks = []
        if has_unvalidated_meta:
            risks.append("命令会交给本地 shell 解释执行，包含命令替换，无法完全静态校验")
        elif effect in (EffectCategory.WRITE_SYSTEM, EffectCategory.DESTRUCTIVE,
                        EffectCategory.NETWORK_OUT, EffectCategory.CODE_GEN,
                        EffectCategory.UNKNOWN):
            risks.append("命令会交给本地 shell 解释执行，无法完全静态校验路径安全")

        approval_kind = "shell_command"
        suggested_prefix_rule = extract_prefix_rules(command) if action == CommandAction.REQUIRE_APPROVAL else None

        # Trust store: if command matches a trusted pattern, downgrade REQUIRE_APPROVAL → ALLOW
        if action == CommandAction.REQUIRE_APPROVAL and self._is_trusted(command):
            action = CommandAction.ALLOW
            suggested_prefix_rule = None

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
        action = resolve_action(self.permission_mode, effect, sandbox_available=self.sandbox_available)

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

        suggested_prefix_rule = extract_prefix_rules(command) if action == CommandAction.REQUIRE_APPROVAL else None

        # Trust store: if command matches a trusted pattern, downgrade REQUIRE_APPROVAL → ALLOW
        if action == CommandAction.REQUIRE_APPROVAL and self._is_trusted(command):
            action = CommandAction.ALLOW
            suggested_prefix_rule = None

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
        if command_name in SHELL_INTERPRETERS or command_name in WINDOWS_SHELL_INTERPRETERS:
            effect = self._shell_interpreter_override(command_name, argv, effect)

        return effect

    def _shell_interpreter_override(
        self, command_name: str, argv: list[str], current_effect: EffectCategory
    ) -> EffectCategory:
        """Override shell interpreter classification based on arguments.

        Applies to both Unix shells (bash/sh/...) and Windows interpreters
        (powershell/pwsh/cmd) — same semantics, different flag spellings.

        Rules:
        1. If an inline-eval flag is present (-c/-e/--eval/-Command/-EncodedCommand/
           /c/etc., see INLINE_EVAL_FLAGS) → CODE_GEN (no override)
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

    _REDIRECT_PATTERN = re.compile(r'(?:2>&1|2>>?|>>?>)\s*(\S+)')
    _APPEND_REDIRECT_PATTERN = re.compile(r'>>\s*(\S+)')

    def _classify_shell_command(self, command: str) -> EffectCategory:
        """Classify a shell command containing pipes, &&/||, ;, and redirects.

        Splits by |, &&, ||, and ; — classifies each segment independently,
        then returns the most dangerous effect category.
        Redirects (>, >>, 2>) add WRITE_PROJECT to the effect list.
        Redirect targets outside allowed paths upgrade to WRITE_SYSTEM.
        """
        effects: list[EffectCategory] = []

        has_redirect = ">" in command or ">>" in command or "2>" in command

        if has_redirect:
            redirect_effect = self._classify_redirect_target(command)
            effects.append(redirect_effect)

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

    def _classify_redirect_target(self, command: str) -> EffectCategory:
        """Classify redirect targets: paths within allowed_paths → WRITE_PROJECT,
        paths outside → WRITE_SYSTEM. 2>&1 (no target file) → WRITE_PROJECT."""
        for m in self._REDIRECT_PATTERN.finditer(command):
            target = m.group(1)
            if target == "&1":
                continue
            try:
                resolved = os.path.expanduser(target)
                self.path_security.validate_path(resolved)
            except SecurityError:
                return EffectCategory.WRITE_SYSTEM
        return EffectCategory.WRITE_PROJECT

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
                elif ch == '|' or ch == ';':
                    segments.append(''.join(current))
                    current = []
                    i += 1
                    continue

            current.append(ch)
            i += 1

        if current:
            segments.append(''.join(current))

        return segments

    def _detect_shell_operators(self, command: str) -> dict[str, bool]:
        """Detect which shell operators are present outside quotes.

        Returns a dict of operator presence flags. This avoids false positives
        from operators inside quoted strings (e.g. ``;`` in ``python3 -c "a; b"``).
        """
        result: dict[str, bool] = {
            "pipe": False,
            "chain": False,
            "semicolon": False,
            "redirect": False,
            "append_redirect": False,
            "stderr_redirect": False,
        }
        in_single = False
        in_double = False

        i = 0
        while i < len(command):
            ch = command[i]

            if ch == "'" and not in_double:
                in_single = not in_single
                i += 1
                continue
            elif ch == '"' and not in_single:
                in_double = not in_double
                i += 1
                continue

            if not in_single and not in_double:
                if ch == '&' and i + 1 < len(command) and command[i + 1] == '&':
                    result["chain"] = True
                    i += 2
                    continue
                if ch == '|' and i + 1 < len(command) and command[i + 1] == '|':
                    result["chain"] = True
                    i += 2
                    continue
                if ch == '|':
                    result["pipe"] = True
                    i += 1
                    continue
                if ch == ';':
                    result["semicolon"] = True
                    i += 1
                    continue
                if ch == '2' and i + 1 < len(command) and command[i + 1] == '>':
                    if i + 2 < len(command) and command[i + 2] == '>':
                        result["stderr_redirect"] = True
                        i += 3
                    else:
                        result["stderr_redirect"] = True
                        i += 2
                    continue
                if ch == '>' and (i == 0 or command[i - 1] != '2'):
                    if i + 1 < len(command) and command[i + 1] == '>':
                        result["append_redirect"] = True
                        i += 2
                    else:
                        result["redirect"] = True
                        i += 1
                    continue

            i += 1

        return result

    def _validate_argv_paths(self, args: list[str], command_name: str) -> str | None:
        try:
            self.shell_security._validate_path_arguments(args, self.path_security)
            return None
        except Exception as e:
            return str(e)

    def _is_trusted(self, command: str) -> bool:
        if not self.trust_store or not self._session_id:
            return False
        return self.trust_store.matches(self._session_id, "shell", command)

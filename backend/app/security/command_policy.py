import enum
import logging
import os
import subprocess

from pydantic import BaseModel, Field

from app.security.path_security import PathSecurity, SecurityError
from app.security.shell_security import ShellSecurity

logger = logging.getLogger(__name__)


class CommandAction(str, enum.Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


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


HARD_DENY_PATTERNS: list[tuple[list[str], str]] = [
    (["rm", "-rf", "/"], "递归删除根目录"),
    (["rm", "-rf", "~"], "递归删除用户主目录"),
    (["rm", "-rf", "--"], "递归删除根目录(--分隔)"),
    (["rm", "-rf", ".."], "递归删除上级目录"),
    (["rm", "-rf", ".git"], "递归删除 .git 目录"),
]

HARD_DENY_PREFIXES_ARGV: set[str] = {
    "sudo", "su", "eval", "exec", "dd", "mkfs",
    "bash", "sh", "zsh", "fish", "ksh", "csh",
}

HARD_DENY_SHELL_PATTERNS: list[str] = [
    "curl",
    "wget",
]

HIGH_RISK_ARGV_COMMANDS: set[str] = {
    "rm", "rmdir", "chmod", "chown",
}

INLINE_CODE_COMMANDS: dict[str, set[str]] = {
    "python": {"-c"},
    "python3": {"-c"},
    "node": {"-e", "--eval"},
    "perl": {"-e"},
    "ruby": {"-e"},
    "php": {"-r"},
}

HARD_DENY_SHELL_COMMANDS: set[str] = {
    "sudo", "su", "eval", "exec",
    "bash", "sh", "zsh", "fish", "ksh", "csh",
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
    """Evaluates shell commands and returns structured decisions."""

    def __init__(self, shell_security: ShellSecurity, path_security: PathSecurity):
        self.shell_security = shell_security
        self.path_security = path_security

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

        needs_shell = bool(self.shell_security.SHELL_META_PATTERN.search(command_normalized))

        if needs_shell and self.shell_security._is_windows():
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=["Windows shell 模式尚未支持"],
                environment_snapshot=snapshot,
            )

        if needs_shell:
            return self._evaluate_shell_command(
                command_normalized, resolved_cwd, timeout, snapshot
            )

        return self._evaluate_argv_command(
            command_normalized, resolved_cwd, timeout, snapshot
        )

    def _evaluate_shell_command(
        self,
        command: str,
        cwd: str,
        timeout: int,
        snapshot: EnvironmentSnapshot,
    ) -> CommandDecision:
        import shlex
        try:
            tokens = shlex.split(command, posix=not self.shell_security._is_windows())
        except ValueError:
            tokens = []

        first_token = tokens[0] if tokens else ""
        command_name = self.shell_security._command_name(first_token) if first_token else ""

        if command_name in HARD_DENY_SHELL_PATTERNS:
            if "|" in command or ">" in command:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    cwd=cwd,
                    timeout=timeout,
                    reasons=[f"下载后执行管道: {command_name}"],
                    risks=["下载的代码会在本地 shell 中执行，无法静态校验"],
                    environment_snapshot=snapshot,
                )

        if command_name in HARD_DENY_SHELL_COMMANDS:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                cwd=cwd,
                timeout=timeout,
                reasons=[f"禁止在 shell 模式下执行: {command_name}"],
                environment_snapshot=snapshot,
            )

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

        has_destructive = any(
            tok in command for tok in ["rm ", "chmod ", "chown ", "delete", "-delete"]
        )
        has_write_redirect = ">" in command or ">>" in command

        risks = ["命令会交给本地 shell 解释执行，无法完全静态校验路径安全"]

        if has_destructive:
            risks.append("包含破坏性操作")
        elif has_write_redirect:
            risks.append("包含写入/重定向操作")

        approval_kind = "shell_command"

        return CommandDecision(
            action=CommandAction.REQUIRE_APPROVAL,
            execution_mode="shell",
            command=command,
            argv=None,
            cwd=cwd,
            timeout=timeout,
            reasons=reasons or ["使用 shell 元语法"],
            risks=risks,
            approval_kind=approval_kind,
            environment_snapshot=snapshot,
        )

    def _evaluate_argv_command(
        self,
        command: str,
        cwd: str,
        timeout: int,
        snapshot: EnvironmentSnapshot,
    ) -> CommandDecision:
        import shlex

        try:
            argv = shlex.split(command, posix=not self.shell_security._is_windows())
        except ValueError as exc:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="argv",
                cwd=cwd,
                timeout=timeout,
                reasons=[f"命令解析失败: {exc}"],
                environment_snapshot=snapshot,
            )

        if not argv:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="argv",
                cwd=cwd,
                timeout=timeout,
                reasons=["命令不能为空"],
                environment_snapshot=snapshot,
            )

        command_name = self.shell_security._command_name(argv[0])

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

        if command_name in HARD_DENY_PREFIXES_ARGV:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="argv",
                argv=argv,
                cwd=cwd,
                timeout=timeout,
                reasons=[f"禁止执行: {command_name}"],
                environment_snapshot=snapshot,
            )

        inline_flags = INLINE_CODE_COMMANDS.get(command_name)
        if inline_flags and any(arg in inline_flags for arg in argv[1:]):
            return CommandDecision(
                action=CommandAction.REQUIRE_APPROVAL,
                command=command,
                execution_mode="argv",
                argv=argv,
                cwd=cwd,
                timeout=timeout,
                reasons=[f"内联代码执行: {command_name}"],
                risks=["内联代码无法静态校验"],
                approval_kind="argv_approval",
                environment_snapshot=snapshot,
            )

        if command_name in HIGH_RISK_ARGV_COMMANDS:
            reasons = [f"高风险命令: {command_name}"]
            risks = []
            if command_name == "rm" and "-rf" in argv:
                risks.append("递归强制删除")
            elif command_name == "rm":
                risks.append("删除文件")
            elif command_name in {"chmod", "chown"}:
                risks.append("修改文件权限或所有权")

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

            suggested_prefix = None

            return CommandDecision(
                action=CommandAction.REQUIRE_APPROVAL,
                command=command,
                execution_mode="argv",
                argv=argv,
                cwd=cwd,
                timeout=timeout,
                reasons=reasons,
                risks=risks,
                approval_kind="argv_approval",
                suggested_prefix_rule=suggested_prefix,
                environment_snapshot=snapshot,
            )

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

        logger.info("低风险 argv 命令允许执行: %s", command)
        return CommandDecision(
            action=CommandAction.ALLOW,
            command=command,
            execution_mode="argv",
            argv=argv,
            cwd=cwd,
            timeout=timeout,
            environment_snapshot=snapshot,
        )

    def _validate_argv_paths(self, args: list[str], command_name: str) -> str | None:
        try:
            self.shell_security._validate_path_arguments(args, self.path_security)
            return None
        except Exception as e:
            return str(e)

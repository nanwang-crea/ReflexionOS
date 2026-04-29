import logging
import os
import re
import shlex
import sys

from app.security.path_security import PathSecurity

logger = logging.getLogger(__name__)


class ShellSecurityError(Exception):
    """Shell 安全错误"""
    pass


class ShellSecurity:
    """Shell 命令执行安全控制 - 拒绝危险命令并校验路径参数"""
    
    SHELL_META_PATTERN = re.compile(r"[;&|<>`]|[$][(]")

    POSIX_DANGEROUS_COMMANDS = {
        "rm",
        "rmdir",
        "dd",
        "mkfs",
        "chmod",
        "chown",
        "sudo",
        "su",
        "eval",
        "exec",
        "bash",
        "sh",
        "zsh",
        "fish",
        "ksh",
        "csh",
    }

    WINDOWS_DANGEROUS_COMMANDS = {
        "del",
        "erase",
        "rd",
        "rmdir",
        "format",
        "diskpart",
        "cmd",
        "powershell",
        "pwsh",
    }

    INLINE_CODE_COMMANDS = {
        "python": {"-c"},
        "python3": {"-c"},
        "node": {"-e", "--eval"},
        "perl": {"-e"},
        "ruby": {"-e"},
        "php": {"-r"},
    }

    NON_PATH_ARGUMENT_COMMANDS = {"echo"}

    def __init__(self, platform_name: str | None = None):
        self.platform_name = platform_name or sys.platform

    @property
    def platform_label(self) -> str:
        if self._is_windows():
            return "Windows"
        if self.platform_name == "darwin":
            return "macOS"
        if self.platform_name.startswith("linux"):
            return "Linux"
        return self.platform_name

    @property
    def command_hint(self) -> str:
        if self._is_windows():
            return (
                "当前平台是 Windows。使用 Windows 可执行命令，例如 `where python`、"
                "`python --version`；不要使用 cmd /c、PowerShell、管道、重定向或 Shell 内置命令。"
            )
        return (
            f"当前平台是 {self.platform_label}。"
            "命令按 argv 直接执行，不经过 shell 解析，因此禁止任何 shell 元语法，"
            "包括但不限于: 管道 `|`、重定向 `>` `>>` `2>` `/dev/null`、"
            "链式操作 `&&` `||` `;`、命令替换 `` ` `` `$()`。"
            "请用单条命令完成操作，例如 `pwd`、`ls`、`which python`、`python --version`。"
        )

    def validate_command(
        self,
        command: str,
        path_security: PathSecurity | None = None,
    ) -> list[str]:
        """
        验证命令安全性
        
        Args:
            command: 待执行的命令
            path_security: 可选路径安全控制，用于校验命令参数中的路径
            
        Raises:
            ShellSecurityError: 命令不安全
        """
        command_normalized = command.strip()
        if not command_normalized:
            raise ShellSecurityError("命令不能为空")

        if self.SHELL_META_PATTERN.search(command_normalized):
            raise ShellSecurityError(f"禁止使用 Shell 元语法: {command}")

        try:
            argv = shlex.split(command_normalized, posix=not self._is_windows())
        except ValueError as exc:
            raise ShellSecurityError(f"命令解析失败: {exc}") from exc

        if not argv:
            raise ShellSecurityError("命令不能为空")

        command_name = self._command_name(argv[0])
        dangerous_commands = (
            self.WINDOWS_DANGEROUS_COMMANDS
            if self._is_windows()
            else self.POSIX_DANGEROUS_COMMANDS
        )

        if command_name in dangerous_commands:
            logger.warning("检测到危险命令: %s", command)
            raise ShellSecurityError(f"禁止执行危险命令: {command}")

        inline_flags = self.INLINE_CODE_COMMANDS.get(command_name)
        if inline_flags and any(arg in inline_flags for arg in argv[1:]):
            logger.warning("检测到危险命令: %s", command)
            raise ShellSecurityError(f"禁止执行危险命令: {command}")

        if path_security and command_name not in self.NON_PATH_ARGUMENT_COMMANDS:
            self._validate_path_arguments(argv[1:], path_security)

        logger.info("命令验证通过: %s", command)
        return argv

    def _is_windows(self) -> bool:
        return self.platform_name.startswith("win")

    def _command_name(self, command: str) -> str:
        normalized = command.replace("\\", "/").split("/")[-1].lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)]
        return normalized

    def _validate_path_arguments(self, args: list[str], path_security: PathSecurity) -> None:
        for arg in args:
            for candidate in self._path_candidates(arg):
                if not self._looks_like_path(candidate):
                    continue
                if self._is_windows_absolute_path(candidate) and not self._is_windows():
                    raise ShellSecurityError(f"路径不在允许范围内: {candidate}")
                path_security.validate_path(os.path.expanduser(candidate))

    def _path_candidates(self, arg: str) -> list[str]:
        if arg.startswith("-") and "=" in arg:
            return [arg.split("=", 1)[1]]
        if arg.startswith("-"):
            return []
        return [arg]

    def _looks_like_path(self, value: str) -> bool:
        if not value:
            return False
        if value in {".", ".."}:
            return True
        if value.startswith(("~", "/", "\\", "./", "../", ".\\", "..\\")):
            return True
        if self._is_windows_absolute_path(value):
            return True
        if "/" in value or "\\" in value:
            return True
        return bool(re.search(r"\.(py|js|ts|tsx|jsx|json|md|txt|toml|yaml|yml|ini|cfg|sh)$", value))

    def _is_windows_absolute_path(self, value: str) -> bool:
        return bool(re.match(r"^[a-zA-Z]:[\\/]", value) or value.startswith("\\\\"))

# backend/app/security/shell_security.py
import logging
import os
import re
import shlex
import sys
from dataclasses import dataclass

from app.security.path_security import PathSecurity

logger = logging.getLogger(__name__)


class ShellSecurityError(Exception):
    """Shell 安全错误"""
    pass


@dataclass
class ValidateResult:
    """Result of command validation."""
    argv: list[str]
    has_meta: bool  # Whether shell metacharacters were detected


class ShellSecurity:
    """Shell 命令执行安全控制 — 解析命令并校验路径参数

    NOTE: Effect classification (dangerous commands, inline code, etc.) has moved
    to CommandEffectRegistry + CommandPolicy. This class now only handles:
    - Shell metacharacter detection (for execution mode decision)
    - Command parsing (shlex.split)
    - Path argument validation
    """

    SHELL_META_PATTERN = re.compile(r"[;&|<>`]|[$][(]")

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
                "`python --version`；不要使用 cmd /c、PowerShell。"
            )
        return (
            f"当前平台是 {self.platform_label}。"
            "低风险命令直接执行；含管道 `|` 或重定向 `>` 的命令可能需要审批，"
            "具体取决于命令的效果分类（只读管道如 `git log | head` 可直接执行）。"
        )

    def validate_command(
        self,
        command: str,
        path_security: PathSecurity | None = None,
    ) -> ValidateResult:
        """
        解析命令并检测 shell 元语法

        Returns:
            ValidateResult with argv and has_meta flag

        Raises:
            ShellSecurityError: only on empty command or parse failure
        """
        command_normalized = command.strip()
        if not command_normalized:
            raise ShellSecurityError("命令不能为空")

        has_meta = bool(self.SHELL_META_PATTERN.search(command_normalized))

        try:
            argv = shlex.split(command_normalized, posix=not self._is_windows())
        except ValueError as exc:
            raise ShellSecurityError(f"命令解析失败: {exc}") from exc

        if not argv:
            raise ShellSecurityError("命令不能为空")

        command_name = self._command_name(argv[0])

        if path_security and command_name not in self.NON_PATH_ARGUMENT_COMMANDS:
            self._validate_path_arguments(argv[1:], path_security)

        logger.info("命令解析完成: %s (has_meta=%s)", command, has_meta)
        return ValidateResult(argv=argv, has_meta=has_meta)

    def _is_windows(self) -> bool:
        return self.platform_name.startswith("win")

    def _command_name(self, command: str) -> str:
        normalized = command.replace("\\", "/").split("/")[-1].lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if normalized.endswith(suffix):
                return normalized[:-len(suffix)]
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

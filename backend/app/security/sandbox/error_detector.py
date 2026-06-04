from __future__ import annotations

import enum
import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.security.command_effect_registry import CommandEffectRegistry


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
        re.compile(r"deny\s+network", re.IGNORECASE),
        re.compile(r"sandbox-exec.*denied.*network", re.IGNORECASE),
    ]
    SEATBELT_PATH_PATTERNS = [
        re.compile(r'deny\s+file-read\*\s*\(subpath\s+"([^"]+)"\)', re.IGNORECASE),
        re.compile(r'deny\s+file-write\*\s*.*\(subpath\s+"([^"]+)"\)', re.IGNORECASE),
    ]
    BWRAP_NETWORK_PATTERNS = [
        re.compile(r"Network is unreachable", re.IGNORECASE),
        re.compile(r"Could not resolve host", re.IGNORECASE),
        re.compile(r"Temporary failure in name resolution", re.IGNORECASE),
    ]
    GENERIC_NETWORK_ERROR_PATTERNS = [
        re.compile(r"Connection refused", re.IGNORECASE),
        re.compile(r"Connection timed? ?out", re.IGNORECASE),
        re.compile(r"Network is (unreachable|down)", re.IGNORECASE),
        re.compile(r"Could not resolve (host|hostname)", re.IGNORECASE),
        re.compile(r"Name or service not known", re.IGNORECASE),
        re.compile(r"Temporary failure in name resolution", re.IGNORECASE),
    ]

    def detect(
        self,
        returncode: int,
        stderr: str,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
        platform: str = sys.platform,
    ) -> SandboxErrorInfo | None:
        if returncode == 0:
            return None

        if not stderr:
            return None

        if platform == "darwin":
            return self._detect_seatbelt(stderr, returncode, command_argv, registry)
        elif platform == "linux":
            return self._detect_bwrap(stderr, returncode, command_argv, registry)
        else:
            return None

    def _detect_seatbelt(
        self,
        stderr: str,
        returncode: int,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
    ) -> SandboxErrorInfo | None:
        for pattern in self.SEATBELT_NETWORK_PATTERNS:
            if pattern.search(stderr):
                return SandboxErrorInfo(
                    error_type=SandboxErrorType.NETWORK_DENIED,
                    original_stderr=stderr,
                    confidence="high",
                )

        denied_paths = []
        for pattern in self.SEATBELT_PATH_PATTERNS:
            for match in pattern.finditer(stderr):
                denied_paths.append(match.group(1))
        if denied_paths:
            return SandboxErrorInfo(
                error_type=SandboxErrorType.PATH_DENIED,
                denied_paths=denied_paths,
                original_stderr=stderr,
                confidence="high",
            )

        return self._detect_generic_network(stderr, returncode, command_argv, registry)

    def _detect_bwrap(
        self,
        stderr: str,
        returncode: int,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
    ) -> SandboxErrorInfo | None:
        for pattern in self.BWRAP_NETWORK_PATTERNS:
            if pattern.search(stderr):
                return SandboxErrorInfo(
                    error_type=SandboxErrorType.NETWORK_DENIED,
                    original_stderr=stderr,
                    confidence="medium",
                )

        return self._detect_generic_network(stderr, returncode, command_argv, registry)

    def _detect_generic_network(
        self,
        stderr: str,
        returncode: int,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
    ) -> SandboxErrorInfo | None:
        has_network_keyword = any(p.search(stderr) for p in self.GENERIC_NETWORK_ERROR_PATTERNS)
        if not has_network_keyword:
            return None

        often_needs = False
        if registry and command_argv and len(command_argv) > 0:
            entry = registry.lookup(command_argv[0])
            if entry and entry.often_needs_network:
                often_needs = True

        if often_needs:
            return SandboxErrorInfo(
                error_type=SandboxErrorType.NETWORK_DENIED,
                original_stderr=stderr,
                confidence="medium",
            )

        return None

# backend/app/security/command_effect_registry.py
import logging

from pydantic import BaseModel

from app.security.effect_category import EffectCategory

logger = logging.getLogger(__name__)


class CommandEffectEntry(BaseModel):
    """Registry entry describing a command's effect category and overrides."""

    category: EffectCategory                          # Base effect category
    allow_subcommands: bool = False                   # Whether subcommands are allowed
    subcommand_overrides: dict[str, EffectCategory] = {}  # Subcommand effect overrides
    flag_overrides: dict[str, EffectCategory] = {}        # Specific flag overrides
    platform_overrides: dict[str, str | EffectCategory] = {}  # Platform-specific overrides
    often_needs_network: bool = False


def _normalize_command_name(command: str) -> str:
    """Normalize a command name: strip path prefix, remove .exe/.cmd/.bat/.com suffix."""
    normalized = command.replace("\\", "/").split("/")[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if normalized.endswith(suffix):
            return normalized[:-len(suffix)]
    return normalized


class CommandEffectRegistry:
    """Registry mapping command names to their effect categories."""

    def __init__(self):
        self._entries: dict[str, CommandEffectEntry] = {}
        self._register_defaults()

    def register(self, command_name: str, entry: CommandEffectEntry) -> None:
        """Register or override a command entry."""
        normalized = _normalize_command_name(command_name)
        self._entries[normalized] = entry

    def lookup(self, command_name: str) -> CommandEffectEntry | None:
        """Look up a command by name. Returns None if not registered."""
        normalized = _normalize_command_name(command_name)
        return self._entries.get(normalized)

    def _register_defaults(self) -> None:
        """Register the default command set (~80+ commands)."""

        # ── READ_ONLY ──────────────────────────────────────────────
        read_only_commands = [
            "ls", "cat", "head", "tail", "wc", "file", "find", "diff",
            "grep", "rg", "sort", "uniq", "which", "where", "pwd", "echo",
            "env", "printenv", "uname", "hostname", "whoami", "id", "date",
            "uptime", "df", "du", "ps", "top", "free", "lsof", "netstat",
            "ss", "true", "false", "yes", "tee",
        ]
        for cmd in read_only_commands:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.READ_ONLY))

        # git — base READ_ONLY, subcommands override
        self.register("git", CommandEffectEntry(
            category=EffectCategory.READ_ONLY,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "add": EffectCategory.WRITE_PROJECT,
                "commit": EffectCategory.WRITE_PROJECT,
                "checkout": EffectCategory.WRITE_PROJECT,
                "switch": EffectCategory.WRITE_PROJECT,
                "merge": EffectCategory.WRITE_PROJECT,
                "rebase": EffectCategory.WRITE_PROJECT,
                "cherry-pick": EffectCategory.WRITE_PROJECT,
                "stash": EffectCategory.WRITE_PROJECT,
                "push": EffectCategory.NETWORK_OUT,
                "fetch": EffectCategory.NETWORK_OUT,
                "pull": EffectCategory.NETWORK_OUT,
                "clone": EffectCategory.NETWORK_OUT,
                "reset": EffectCategory.DESTRUCTIVE,
                "clean": EffectCategory.DESTRUCTIVE,
                "rm": EffectCategory.DESTRUCTIVE,
            },
        ))

        # ── WRITE_PROJECT ──────────────────────────────────────────
        write_project_commands = [
            "mkdir", "touch", "cp", "mv", "ln", "tar", "unzip",
            "make", "cmake", "pytest",
        ]
        for cmd in write_project_commands:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.WRITE_PROJECT))

        self.register("pre-commit", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            often_needs_network=True,
        ))

        # python / python3 — WRITE_PROJECT base, -c → CODE_GEN
        for cmd in ["python", "python3"]:
            self.register(cmd, CommandEffectEntry(
                category=EffectCategory.WRITE_PROJECT,
                flag_overrides={
                    "--version": EffectCategory.READ_ONLY,
                    "-V": EffectCategory.READ_ONLY,
                    "-c": EffectCategory.CODE_GEN,
                },
            ))

        # node — WRITE_PROJECT base, -e/--eval → CODE_GEN
        self.register("node", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            flag_overrides={
                "--version": EffectCategory.READ_ONLY,
                "-e": EffectCategory.CODE_GEN,
                "--eval": EffectCategory.CODE_GEN,
            },
        ))

        # npm
        self.register("npm", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "install": EffectCategory.WRITE_PROJECT,
                "run": EffectCategory.WRITE_PROJECT,
                "test": EffectCategory.WRITE_PROJECT,
                "build": EffectCategory.WRITE_PROJECT,
                "start": EffectCategory.WRITE_PROJECT,
                "list": EffectCategory.READ_ONLY,
                "ls": EffectCategory.READ_ONLY,
                "publish": EffectCategory.NETWORK_OUT,
                "view": EffectCategory.READ_ONLY,
                "info": EffectCategory.READ_ONLY,
            },
        ))

        # pip
        self.register("pip", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "install": EffectCategory.WRITE_PROJECT,
                "list": EffectCategory.READ_ONLY,
                "show": EffectCategory.READ_ONLY,
                "check": EffectCategory.READ_ONLY,
                "download": EffectCategory.NETWORK_OUT,
                "search": EffectCategory.NETWORK_OUT,
                "uninstall": EffectCategory.DESTRUCTIVE,
            },
        ))

        # pip3 — alias for pip
        self.register("pip3", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "install": EffectCategory.WRITE_PROJECT,
                "list": EffectCategory.READ_ONLY,
                "show": EffectCategory.READ_ONLY,
                "check": EffectCategory.READ_ONLY,
                "download": EffectCategory.NETWORK_OUT,
                "uninstall": EffectCategory.DESTRUCTIVE,
            },
        ))

        # cargo
        self.register("cargo", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "build": EffectCategory.WRITE_PROJECT,
                "test": EffectCategory.WRITE_PROJECT,
                "run": EffectCategory.WRITE_PROJECT,
                "check": EffectCategory.READ_ONLY,
                "version": EffectCategory.READ_ONLY,
                "publish": EffectCategory.NETWORK_OUT,
                "clean": EffectCategory.DESTRUCTIVE,
            },
        ))

        # go
        self.register("go", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "build": EffectCategory.WRITE_PROJECT,
                "test": EffectCategory.WRITE_PROJECT,
                "run": EffectCategory.WRITE_PROJECT,
                "version": EffectCategory.READ_ONLY,
                "mod": EffectCategory.WRITE_PROJECT,
                "get": EffectCategory.NETWORK_OUT,
            },
        ))

        # dotnet
        self.register("dotnet", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "build": EffectCategory.WRITE_PROJECT,
                "test": EffectCategory.WRITE_PROJECT,
                "run": EffectCategory.WRITE_PROJECT,
            },
        ))

        # docker
        self.register("docker", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            allow_subcommands=True,
            often_needs_network=True,
            subcommand_overrides={
                "build": EffectCategory.WRITE_PROJECT,
                "compose": EffectCategory.WRITE_PROJECT,
                "pull": EffectCategory.WRITE_SYSTEM,
                "run": EffectCategory.WRITE_SYSTEM,
                "push": EffectCategory.NETWORK_OUT,
                "images": EffectCategory.READ_ONLY,
                "ps": EffectCategory.READ_ONLY,
                "logs": EffectCategory.READ_ONLY,
                "exec": EffectCategory.ESCALATE,
            },
        ))

        # Interpreters with CODE_GEN flag overrides
        self.register("perl", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            flag_overrides={"-e": EffectCategory.CODE_GEN},
        ))
        self.register("ruby", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            flag_overrides={"-e": EffectCategory.CODE_GEN},
        ))
        self.register("php", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
            flag_overrides={"-r": EffectCategory.CODE_GEN},
        ))

        # ── WRITE_SYSTEM ────────────────────────────────────────────
        write_system_commands = [
            "apt-get", "apt", "yum", "dnf", "brew", "pacman", "snap",
            "systemctl", "service", "launchctl",
        ]
        for cmd in write_system_commands:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.WRITE_SYSTEM))

        # ── DESTRUCTIVE ────────────────────────────────────────────
        destructive_commands = ["rm", "rmdir", "chmod", "chown", "truncate", "shred"]
        for cmd in destructive_commands:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.DESTRUCTIVE))

        # ── ESCALATE ────────────────────────────────────────────────
        escalate_commands = ["sudo", "su", "eval", "exec", "newgrp", "pkexec", "gksudo", "runas"]
        for cmd in escalate_commands:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.ESCALATE))

        # Shell interpreters — ESCALATE base, with -c → CODE_GEN override
        for interp in ["bash", "sh", "zsh", "fish", "ksh", "csh"]:
            self.register(interp, CommandEffectEntry(
                category=EffectCategory.ESCALATE,
                flag_overrides={
                    "-c": EffectCategory.CODE_GEN,
                },
            ))

        # ── NETWORK_OUT ─────────────────────────────────────────────
        network_out_commands = [
            "curl", "wget", "ssh", "scp", "rsync", "nc", "ncat",
            "telnet", "ftp",
        ]
        for cmd in network_out_commands:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.NETWORK_OUT))

        # ── Windows-specific ────────────────────────────────────────
        # 注意：直接注册（不通过 platform_overrides；该字段虽存在但 lookup 从不消费）
        # 跨平台安全：这些命令在 Unix 不存在或行为不同，但 register 本身无害
        #  cd/chdir/dir/type/set/findstr/tree/ver/cls → 不存在也是 READ_ONLY 语义
        #  copy/xcopy/move/ren/rename/md → 不存在也是 WRITE_PROJECT 语义
        windows_builtin_read_only = [
            "cd", "chdir", "dir", "type", "set", "findstr", "tree", "ver", "cls",
        ]
        for cmd in windows_builtin_read_only:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.READ_ONLY))

        windows_builtin_write = [
            "copy", "xcopy", "robocopy", "move", "ren", "rename", "md",
        ]
        for cmd in windows_builtin_write:
            self.register(cmd, CommandEffectEntry(category=EffectCategory.WRITE_PROJECT))

        # 保留原有 Windows 命令（直接注册，不用 platform_overrides）
        windows_commands = [
            ("del", EffectCategory.DESTRUCTIVE),
            ("erase", EffectCategory.DESTRUCTIVE),
            ("rd", EffectCategory.DESTRUCTIVE),
            ("rmdir", EffectCategory.DESTRUCTIVE),
            ("format", EffectCategory.DESTRUCTIVE),
            ("diskpart", EffectCategory.DESTRUCTIVE),
        ]
        for cmd, base_cat in windows_commands:
            self.register(cmd, CommandEffectEntry(category=base_cat))

        # PowerShell/cmd —— ESCALATE 基类，与 bash -c 同等语义：
        # -Command/-c/-EncodedCommand（PowerShell）、/c、/k（cmd）都是"交给解释器执行任意命令"，
        # 通过 flag_overrides 降级为 CODE_GEN，交由 command_policy._shell_interpreter_override 判断
        # （命中类路径参数进一步降级为 WRITE_PROJECT；裸调用无参数维持 ESCALATE 拒绝）。
        for interp in ["powershell", "pwsh"]:
            self.register(interp, CommandEffectEntry(
                category=EffectCategory.ESCALATE,
                flag_overrides={
                    "-Command": EffectCategory.CODE_GEN,
                    "-command": EffectCategory.CODE_GEN,
                    "-c": EffectCategory.CODE_GEN,
                    "-EncodedCommand": EffectCategory.CODE_GEN,
                    "-encodedcommand": EffectCategory.CODE_GEN,
                },
            ))
        self.register("cmd", CommandEffectEntry(
            category=EffectCategory.ESCALATE,
            flag_overrides={
                "/c": EffectCategory.CODE_GEN,
                "/C": EffectCategory.CODE_GEN,
                "/k": EffectCategory.CODE_GEN,
                "/K": EffectCategory.CODE_GEN,
            },
        ))

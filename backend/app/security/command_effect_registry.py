# backend/app/security/command_effect_registry.py
# 命令效果注册表：维护"命令名 -> 效果分类（EffectCategory）"的静态映射表，
# 是 command_policy.py 判断一条命令"允许/需审批/拒绝"的知识库来源。
# 收录约 80+ 常见命令（git/npm/pip/docker/shell 解释器等），并支持按子命令、
# 具体 flag、平台差异对基础分类做精细化覆盖（override），避免"一个命令名只能对应一种危险级别"的粗粒度问题。
import logging

from pydantic import BaseModel

from app.security.effect_category import EffectCategory

logger = logging.getLogger(__name__)


class CommandEffectEntry(BaseModel):
    """注册表条目：描述一个命令的基础效果分类及各类覆盖规则。

    字段说明：
        category: 该命令的基础效果分类（如 READ_ONLY/WRITE_PROJECT/ESCALATE 等）。
        allow_subcommands: 是否按第二个 token（子命令，如 git 的 commit/push）
            查 subcommand_overrides 做精细化覆盖；False 时忽略子命令，只用 category。
        subcommand_overrides: 子命令名 -> 效果分类，仅当 allow_subcommands=True 时生效
            （如 git push 覆盖为 NETWORK_OUT，比基础的 READ_ONLY 更危险）。
        flag_overrides: 具体 flag（如 -c、--eval）-> 效果分类，命中优先级高于子命令覆盖
            （如 python -c 覆盖为 CODE_GEN，因为内联代码无法静态审查）。
        platform_overrides: 平台特定覆盖（当前字段存在但 lookup 从不消费，仅作预留/文档用途）。
        often_needs_network: 标记该命令通常需要联网（用于展示提示，不参与危险等级判断）。
    """

    category: EffectCategory                          # 基础效果分类
    allow_subcommands: bool = False                   # 是否启用子命令覆盖
    subcommand_overrides: dict[str, EffectCategory] = {}  # 子命令效果覆盖
    flag_overrides: dict[str, EffectCategory] = {}        # 具体 flag 效果覆盖
    platform_overrides: dict[str, str | EffectCategory] = {}  # 平台特定覆盖（预留，未被 lookup 使用）
    often_needs_network: bool = False


def _normalize_command_name(command: str) -> str:
    """归一化命令名：去掉路径前缀、去掉 Windows 可执行后缀、转小写。

    参数：
        command: 原始命令名，可能带路径（如 "/usr/bin/git" 或 "C:\\...\\python.exe"）。

    逻辑：
        统一反斜杠为正斜杠后按 "/" 取最后一段（去路径前缀），转小写后
        再剥离 .exe/.cmd/.bat/.com 后缀，使得 "git"、"/usr/bin/git"、
        "C:\\Git\\git.exe" 都能归一到同一个注册表 key "git"。

    返回：
        归一化后的命令名（全小写、无路径、无可执行后缀）。
    """
    normalized = command.replace("\\", "/").split("/")[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if normalized.endswith(suffix):
            return normalized[:-len(suffix)]
    return normalized


class CommandEffectRegistry:
    """命令名 -> 效果分类条目 的注册表，供 CommandPolicy 查询命令危险等级。"""

    def __init__(self):
        """初始化空注册表，并立即调用 _register_defaults 灌入内置命令集。"""
        self._entries: dict[str, CommandEffectEntry] = {}
        self._register_defaults()

    def register(self, command_name: str, entry: CommandEffectEntry) -> None:
        """注册或覆盖一条命令条目。

        参数：
            command_name: 命令名（会先归一化，因此传入带路径/后缀的形式也可以）。
            entry: 对应的 CommandEffectEntry（基础分类 + 各类覆盖规则）。

        逻辑：
            归一化命令名后直接写入 _entries，若该 key 已存在则整体覆盖旧条目
            （不做合并，后注册的完全替换先注册的）。

        返回：
            无返回值。
        """
        normalized = _normalize_command_name(command_name)
        self._entries[normalized] = entry

    def lookup(self, command_name: str) -> CommandEffectEntry | None:
        """按命令名查条目。

        参数：
            command_name: 命令名（原始形式，内部会归一化）。

        返回：
            命中的 CommandEffectEntry；未注册过的命令返回 None
            （调用方——command_policy._classify_argv_command——会将 None 视为 UNKNOWN 效果分类，
            未知命令默认走"需审批"而不是"直接放行"，避免遗漏危险命令）。
        """
        normalized = _normalize_command_name(command_name)
        return self._entries.get(normalized)

    def _register_defaults(self) -> None:
        """注册内置默认命令集（约 80+ 个），按效果分类分组批量 register。

        分组依据（从低危到高危）：
            READ_ONLY（只读，如 ls/cat/grep）→ WRITE_PROJECT（改动项目内文件，如 mkdir/npm/pip）
            → WRITE_SYSTEM（改动系统状态，如 apt-get/systemctl）→ DESTRUCTIVE（删除/覆盖，如 rm/chmod）
            → ESCALATE（提权/任意代码执行，如 sudo/bash -c）→ NETWORK_OUT（对外网络请求，如 curl/ssh）。
            另外为 git/npm/pip/cargo/go/docker 等常用工具单独配置了子命令覆盖
            （如 git push 比 git status 更危险），以及为解释器类命令（python/node/bash/powershell 等）
            配置了 flag 覆盖（-c/-e/-Command 等内联执行参数 → CODE_GEN，因为内联代码内容无法静态审查）。
            无返回值，方法执行完毕后 self._entries 即包含全部默认注册。
        """

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

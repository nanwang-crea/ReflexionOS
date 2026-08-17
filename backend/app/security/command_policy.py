# backend/app/security/command_policy.py
# 命令执行策略核心：整条命令从"字符串"到"是否可执行"的判定管线。
# 管线大致为：解析(shell/argv) -> 效果分类(CommandEffectRegistry) -> 路径校验(PathSecurity)
#            -> 映射为 ALLOW/REQUIRE_APPROVAL/DENY(PermissionMode)。
# 拆分这几个职责的好处：命令效果知识库（哪个命令危险）可以独立复用，
# 而 shell 层的平台差异（尤其 Windows 无法用 sandbox 约束自由路径参数）
# 只需在本文件的判定入口做特殊处理，不污染注册表本身。
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
    """命令执行前捕获的环境快照，用于审批记录/审计留痕（不参与安全判定本身）。

    字段：
        cwd: 执行目录（已校验后的绝对路径）。
        cwd_identity: 目录的设备号:inode 号，用于识别"看似同一路径但实际是不同挂载"的情况。
        git_root: 若 cwd 在某个 git 仓库内，记录该仓库根目录；否则为 None。
        git_head: 记录时的 HEAD commit hash；获取失败（非仓库/git 不可用）则为 None。
        env_fingerprint: cwd+平台 的哈希摘要，用于粗略比对环境是否发生变化。
    """
    cwd: str
    cwd_identity: str | None = None
    git_root: str | None = None
    git_head: str | None = None
    env_fingerprint: str | None = None


class CommandDecision(BaseModel):
    """CommandPolicy.evaluate 的最终判定结果，供上层执行器/审批 UI 使用。

    字段：
        action: 最终动作（ALLOW/REQUIRE_APPROVAL/DENY）。
        execution_mode: "argv"（无 shell 元字符，按参数数组直接执行）或
            "shell"（含管道/重定向等，需交给 shell 解释执行）。
        command: 原始命令字符串（未做任何清洗）。
        argv: execution_mode="argv" 时的解析结果；shell 模式下为 None。
        cwd: 已校验通过的执行目录；校验失败时可能为原始未校验的 cwd（仅用于展示）。
        timeout: 命令执行超时秒数。
        reasons: 判定理由列表（给用户/日志看的说明，如"破坏性命令: rm"）。
        risks: 风险提示列表（比 reasons 更强调后果，如"递归强制删除"）。
        approval_kind: 审批类型标识（"shell_command"/"argv_approval"），供审批 UI 区分展示方式。
        suggested_prefix_rule: 当 action=REQUIRE_APPROVAL 时，建议的信任前缀规则
            （用户批准后可选择"以后信任此前缀"）；其他情况为 None。
        environment_snapshot: 对应的 EnvironmentSnapshot。
        effect_category: 命令被分类到的效果类别；DENY 早退（如空命令、hard-deny 命中）时可能为 None。
    """
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
# 硬拒绝模式：无论权限模式/沙盒状态如何，命中即直接 DENY，不进入效果分类流程。
# 这是最后一道防线，专门堵最容易造成不可逆损失的"参数级"危险组合
# （效果分类只能识别到命令名是 rm，识别不到 "-rf /" 这种参数级别的毁灭性组合）。
HARD_DENY_PATTERNS: list[tuple[list[str], str]] = [
    (["rm", "-rf", "/"], "递归删除根目录"),
    (["rm", "-rf", "~"], "递归删除用户主目录"),
    (["rm", "-rf", "--"], "递归删除根目录(--分隔)"),
    (["rm", "-rf", ".."], "递归删除上级目录"),
    (["rm", "-rf", ".git"], "递归删除 .git 目录"),
]

# 下载后执行类命令单独硬拒绝，因为真正的风险点在于组合方式
# （curl|bash / wget|sh），而不是单看第一个命令 token。
HARD_DENY_SHELL_PATTERNS: set[str] = {"curl", "wget"}

# shell 解释器：其 -c flag 意味着 CODE_GEN（内联执行，无法静态审查）
SHELL_INTERPRETERS = {"bash", "sh", "zsh", "fish", "ksh", "csh"}

# Windows 解释器：powershell/pwsh 的 -Command、cmd 的 /c 语义上等价于 bash -c，
# 同样交给 _shell_interpreter_override 判断（是否降级为 CODE_GEN/WRITE_PROJECT）
WINDOWS_SHELL_INTERPRETERS = {"powershell", "pwsh", "cmd"}

# 内联执行 flag：命中即阻止后续按"类文件路径参数"做降级判断
INLINE_EVAL_FLAGS = {
    "-c", "-e", "--eval",
    "-Command", "-command", "-EncodedCommand", "-encodedcommand",
    "/c", "/C", "/k", "/K",
}


def _capture_environment_snapshot(cwd: str) -> EnvironmentSnapshot:
    """采集执行前的环境快照（仅用于审计留痕，采集失败均静默降级为 None，不影响命令判定）。

    参数：
        cwd: 已校验通过的执行目录绝对路径。

    逻辑：
        1. os.stat 拿 (st_dev, st_ino) 拼成 cwd_identity；拿不到（目录不存在等）则为 None。
        2. 用 `git rev-parse --show-toplevel` / `HEAD` 探测是否在 git 仓库内
           （2 秒超时，避免非仓库或 git 不可用时卡住整个判定流程）；探测失败静默忽略。
        3. 用 cwd+平台名 算一个 sha256 短摘要作为 env_fingerprint；计算异常也静默忽略。
        这些采集均为"尽力而为"，任何一步失败都不应该阻断命令判定主流程，因此每步都单独 try/except。

    返回：
        EnvironmentSnapshot（字段可能部分为 None）。
    """
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
    """对一条 shell 命令做分类，并返回最终执行判定。

    判定管线：解析(parse) -> 效果分类(classify) -> 路径校验(validate paths)
    -> 效果映射为 allow/需审批/deny。拆分这几步职责的好处是：命令效果注册表
    可以独立复用（不关心平台），而 shell 层的平台专属安全规则
    （尤其是 Windows 无沙盒时的白名单策略）只在本类内单独处理。
    """

    def __init__(self, shell_security: ShellSecurity, path_security: PathSecurity,
                 registry: CommandEffectRegistry | None = None,
                 trust_store: SessionTrustStore | None = None,
                 session_id: str | None = None,
                 permission_mode: PermissionMode = PermissionMode.AUTO,
                 sandbox_available: bool = False):
        """初始化命令策略。

        参数：
            shell_security: 负责解析命令、检测 shell 元字符、校验路径类参数。
            path_security: 负责判断某个绝对路径是否在允许的项目目录范围内。
            registry: 命令效果注册表；未传则新建一个内置默认注册表实例。
            trust_store: 会话级信任规则存储；用于把已批准过的命令前缀自动放行。
            session_id: 当前会话 ID，配合 trust_store 做会话级信任查询。
            permission_mode: 权限模式（ASK/AUTO/YOLO），决定同一效果分类下的最终动作。
            sandbox_available: 是否有沙盒可用；影响 Windows 第一阶段白名单策略是否启用，
                以及 YOLO 模式下是否允许放行（无沙盒时 YOLO 直接拒绝，避免沦为无约束的主机执行）。
        """
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
        """命令判定主入口：给出一条命令字符串，返回最终执行决策。

        参数：
            command: 原始命令字符串（未清洗）。
            cwd: 期望的执行目录；None 时用当前目录 "."。会先经 path_security 校验，
                不在允许范围内直接 DENY（防止在允许目录外的地方执行任何命令）。
            timeout: 执行超时秒数；None 时默认 600 秒。

        逻辑（按顺序）：
            1. 空命令 -> DENY。
            2. 校验 cwd 是否在允许路径范围内，不通过则 DENY 并带上具体原因。
            3. 采集环境快照（用于审计留痕，不影响判定）。
            4. 调用 shell_security.validate_command 解析命令、判断是否含 shell 元字符
               （has_meta）。解析出的 SecurityError 若来源标记为 "shell"，转成 DENY 返回；
               其余异常直接向上抛出（说明是编程错误而非命令本身问题）。
            5. Windows 专属分支：当命令含元字符、当前是 Windows、且沙盒不可用时，
               进入"第一阶段严格白名单"——因为 Windows 没有 sandbox.wrap_shell_command，
               无法约束命令内的自由路径参数，所以只放行 && / || 连接的纯只读 git 子命令
               （status/log/diff/show），并复用 shell_security._validate_path_arguments
               校验路径参数；命中任何不支持的元字符、非 git 命令、或非纯读子命令都直接 DENY。
               sandbox_available=True 时跳过这一分支，改由后续沙盒执行流处理；
               macOS/Linux 不受此分支影响。
            6. 通过以上检查后，按 has_meta 分流：含元字符走 _evaluate_shell_command
               （管道/链式/重定向的整体效果分类），否则走 _evaluate_argv_command
               （更严格的按参数校验）。

        返回：
            CommandDecision，包含最终 action 及判定依据。
        """
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

        # 用 ShellSecurity 解析命令（不做路径校验——路径校验由本类自行处理）
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

            # 检查元字符：第一阶段只支持 && 和 ||（命令链），其余元字符一律拒绝。
            # 采用黑名单判定：命中 unsupported_on_windows 即拒绝，
            # 支持集 {'&&', '||'} 仅作说明，不参与判断，故不再定义为局部变量。
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

        # 含 shell 元字符的命令按完整 shell 表达式判定；纯 argv 命令走更严格的逐参数校验
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
        """判定含 shell 元字符（管道/链式/重定向/命令替换）的命令。

        参数：
            command: 已 strip 过的原始命令字符串。
            cwd: 已校验通过的执行目录。
            timeout: 超时秒数。
            snapshot: 已采集的环境快照，原样带入返回结果。

        逻辑：
            1. 硬拒绝"下载后执行"管道：若命令以 curl/wget 开头且含 "|"，
               检查管道后续任一段的命令名是否落在 SHELL_INTERPRETERS 中
               （bash/sh/zsh 等），命中则直接 DENY——因为下载回来的内容是运行时才能
               确定的字节流，静态阶段完全无法审查其安全性。
            2. 用 _classify_shell_command 对整条命令（拆分各管道/链式段后取最危险者）
               做效果分类。
            3. 决定最终 action：
               - 效果为 ESCALATE 直接 DENY；
               - 命令含 $() 或反引号（命令替换）时，因替换内容不可静态求值，
                 始终判定为 REQUIRE_APPROVAL（即使效果分类本身较低危）；
               - 否则按 permission_mode + sandbox_available 走 resolve_action 常规映射。
            4. 组装 reasons/risks 说明文本（基于检测到的操作符：管道/链式/分号/重定向/命令替换/错误重定向）。
            5. 若最终动作是 REQUIRE_APPROVAL，生成建议的信任前缀规则（extract_prefix_rules）；
               若该命令命中会话信任规则（_is_trusted），则降级为 ALLOW 并清空建议规则
               （因为已经不需要再建议信任了）。

        返回：
            CommandDecision，execution_mode 固定为 "shell"。
        """
        # 1. 硬拒绝：curl/wget | sh/bash 这类"下载后执行"组合
        try:
            tokens = shlex.split(command, posix=not self.shell_security._is_windows())
        except ValueError:
            tokens = []

        first_token = tokens[0] if tokens else ""
        first_cmd = self.shell_security._command_name(first_token) if first_token else ""

        # 检测"下载后执行"模式
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

        # 2. 对整条 shell 命令（管道/&&/||/;/重定向）做效果分类
        effect = self._classify_shell_command(command)

        # 3. 根据效果分类决定最终 action
        #    - &&/|| 链式命令按管道处理：拆分、逐段分类、取最危险者聚合
        #    - 命令替换 $() 和反引号内容不可静态求值，始终需要审批
        #    - 重定向 >/>> 会叠加 WRITE_PROJECT 效果，但仍参与效果分类
        has_unvalidated_meta = any([
            "$(" in command or "`" in command,  # 命令替换 —— 无法静态校验
        ])

        if effect == EffectCategory.ESCALATE:
            action = CommandAction.DENY
        elif has_unvalidated_meta:
            # 命令替换的内容不透明 → 始终需要审批
            action = CommandAction.REQUIRE_APPROVAL
        else:
            action = resolve_action(self.permission_mode, effect, sandbox_available=self.sandbox_available)

        # 4. 组装 reasons/risks 说明文本（用引号感知的操作符检测，避免引号内的符号误判）
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

        # 信任存储：若命令匹配已信任的模式，将 REQUIRE_APPROVAL 降级为 ALLOW
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
        """判定无 shell 元字符的纯 argv 命令（更严格，可逐参数校验路径）。

        参数：
            command: 原始命令字符串。
            argv: shell_security 解析出的参数数组（argv[0] 为命令本身）。
            cwd: 已校验通过的执行目录。
            timeout: 超时秒数。
            snapshot: 已采集的环境快照。

        逻辑：
            1. 硬拒绝模式匹配（HARD_DENY_PATTERNS，如 rm -rf /）：argv 前缀完全匹配即 DENY。
            2. 针对 rm -rf/-fr 的补充检查：定位第一个非 flag 参数作为删除目标，
               展开 ~ 后若目标是 "/"、"~"、".."、或落在 .git 目录上，直接 DENY
               ——这类目标即使不匹配 HARD_DENY_PATTERNS 的精确 token 序列也同样危险
               （例如 "rm -rf .git" 与 "rm -rf --force .git" 参数顺序不同但后果相同）。
            3. 用 CommandEffectRegistry 对命令做效果分类，再按 permission_mode 映射出 action。
            4. 按效果分类补充 reasons/risks 的人类可读说明（如破坏性命令具体是删除还是改权限）。
            5. action 不是 DENY 时，除白名单命令（NON_PATH_ARGUMENT_COMMANDS，如 echo）外，
               对 argv[1:] 做路径参数校验（_validate_argv_paths），任何参数解析为
               不在允许目录范围内的路径都会使最终结果整体降级为 DENY。
            6. 若最终 action 为 REQUIRE_APPROVAL，生成建议信任前缀规则；命中会话信任规则
               （_is_trusted）则降级为 ALLOW 并清空建议规则。

        返回：
            CommandDecision，execution_mode 固定为 "argv"。
        """
        command_name = self.shell_security._command_name(argv[0])

        # 1. 硬拒绝模式匹配
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

        # 针对 rm -rf 的补充检查（目标是危险路径时，即使不匹配硬拒绝的精确 token 序列也要拒绝）
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

        # 2. 用注册表分类效果
        effect = self._classify_argv_command(argv)
        action = resolve_action(self.permission_mode, effect, sandbox_available=self.sandbox_available)

        # 3. 按效果分类补充判定详情
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

        # 4. 对非 DENY 结果做路径参数校验
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

        # 信任存储：若命令匹配已信任的模式，将 REQUIRE_APPROVAL 降级为 ALLOW
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
        """按注册表对 argv 命令做效果分类，并逐层解析 flag/子命令/解释器覆盖。

        参数：
            argv: 参数数组，argv[0] 为命令本身。

        逻辑：
            1. 归一化命令名后查注册表，未注册命令直接判 UNKNOWN
               （UNKNOWN 在 EFFECT_ACTION_MAP 中默认走 REQUIRE_APPROVAL，
               保证"没见过的命令"不会被静默放行）。
            2. 以注册条目的 category 为基础效果。
            3. 遍历 argv[1:]，收集所有命中 flag_overrides 的效果，
               取其中最危险者覆盖基础效果（如 python --version 和 -c 同时出现，
               以 -c 对应的 CODE_GEN 为准，因为要按最坏情况判定）。
            4. 若条目允许子命令覆盖（allow_subcommands）且 argv[1] 是非 flag 的子命令名，
               查 subcommand_overrides；仅当子命令对应效果比当前效果更危险
               （EFFECT_DANGER_LEVEL 更高）才会覆盖，避免子命令覆盖意外把已升级的
               flag 覆盖结果又降回去。
            5. 若命令名是 shell 解释器（bash/sh/... 或 powershell/pwsh/cmd），
               再交给 _shell_interpreter_override 做进一步降级判断。

        返回：
            最终的 EffectCategory。
        """
        command_name = self.shell_security._command_name(argv[0])
        entry = self.registry.lookup(command_name)

        if entry is None:
            return EffectCategory.UNKNOWN

        # 从基础分类开始
        effect = entry.category

        # 先检查 flag 覆盖（如 python -c → CODE_GEN, python --version → READ_ONLY）
        # 收集所有命中的 flag 覆盖，取最危险的一个
        flag_effects: list[EffectCategory] = []
        for arg in argv[1:]:
            if arg in entry.flag_overrides:
                flag_effects.append(entry.flag_overrides[arg])
        if flag_effects:
            effect = most_dangerous(flag_effects)

        # 再检查子命令覆盖（如 git push → NETWORK_OUT）
        if entry.allow_subcommands and len(argv) >= 2:
            subcmd = argv[1]
            if not subcmd.startswith("-") and subcmd in entry.subcommand_overrides:
                subcmd_effect = entry.subcommand_overrides[subcmd]
                if EFFECT_DANGER_LEVEL[subcmd_effect] > EFFECT_DANGER_LEVEL[effect]:
                    effect = subcmd_effect

        # shell 解释器覆盖：bash script.sh → WRITE_PROJECT
        if command_name in SHELL_INTERPRETERS or command_name in WINDOWS_SHELL_INTERPRETERS:
            effect = self._shell_interpreter_override(command_name, argv, effect)

        return effect

    def _shell_interpreter_override(
        self, command_name: str, argv: list[str], current_effect: EffectCategory
    ) -> EffectCategory:
        """基于参数对 shell 解释器命令做进一步分类覆盖。

        参数：
            command_name: 已归一化的命令名（bash/sh/... 或 powershell/pwsh/cmd）。
            argv: 参数数组。
            current_effect: 覆盖前的当前效果分类（一般是 ESCALATE，因为裸解释器调用危险）。

        适用范围：
            同时覆盖 Unix shell（bash/sh/zsh/fish/ksh/csh）和 Windows 解释器
            （powershell/pwsh/cmd）——语义相同，只是 flag 拼写不同。

        规则（按顺序判断）：
            1. 若存在内联执行 flag（-c/-e/--eval/-Command/-EncodedCommand/
               /c 等，见 INLINE_EVAL_FLAGS）→ CODE_GEN（内联代码内容无法静态审查）。
            2. 否则若存在看起来像文件路径的非 flag 参数 → WRITE_PROJECT
               （说明是在执行一个脚本文件，效果收窄为项目内写操作）。
            3. 否则保持 current_effect 不变（裸调用解释器且无脚本/内联参数，
               维持 ESCALATE，最终会被判 DENY——防止"看似无害的裸命令"被放行）。

        返回：
            覆盖后的 EffectCategory。
        """
        # 先检查内联执行 flag
        for arg in argv[1:]:
            if arg in INLINE_EVAL_FLAGS:
                return EffectCategory.CODE_GEN

        # 再检查类文件路径的参数
        for arg in argv[1:]:
            if not arg.startswith("-"):
                if self.shell_security._looks_like_path(arg):
                    return EffectCategory.WRITE_PROJECT
                # 同时把带点号/斜杠、形似脚本名的参数也当作路径处理
                if "." in arg or "/" in arg:
                    return EffectCategory.WRITE_PROJECT

        return current_effect

    _REDIRECT_PATTERN = re.compile(r'(?:2>&1|2>>?|>>?>)\s*(\S+)')
    _APPEND_REDIRECT_PATTERN = re.compile(r'>>\s*(\S+)')

    def _classify_shell_command(self, command: str) -> EffectCategory:
        """对含管道/&&/||/;/重定向的整条 shell 命令做效果分类。

        参数：
            command: 原始命令字符串。

        逻辑：
            按 |、&&、||、; 拆分成若干段，逐段独立分类（复用 _classify_argv_command），
            再取所有段中最危险的效果分类。重定向（>、>>、2>）会额外叠加一个效果：
            重定向目标若在允许路径范围内记为 WRITE_PROJECT，超出范围则升级为 WRITE_SYSTEM
            （因为等价于"把内容写到项目目录之外"，比单纯的项目内写操作更危险）。

        返回：
            所有分段效果及重定向效果中最危险的 EffectCategory；
            没有任何有效分段时返回 UNKNOWN。
        """
        effects: list[EffectCategory] = []

        has_redirect = ">" in command or ">>" in command or "2>" in command

        if has_redirect:
            redirect_effect = self._classify_redirect_target(command)
            effects.append(redirect_effect)

        # 按所有 shell 操作符（|、&&、||、;）拆分，逐段分类
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
        """判定重定向目标的效果分类。

        参数：
            command: 含重定向操作符的原始命令字符串。

        逻辑：
            用 _REDIRECT_PATTERN 匹配所有 >、>>、2>、2>&1 形式的重定向，
            提取每个目标路径；目标是 "&1"（如 2>&1，没有实际目标文件）时跳过。
            其余目标展开 ~ 后交给 path_security.validate_path 校验：
            校验失败（说明目标在允许目录范围之外）→ 整体判定为 WRITE_SYSTEM
            （写到项目外部，风险更高）；只要没有目标越界，就判定为 WRITE_PROJECT。

        返回：
            WRITE_SYSTEM 或 WRITE_PROJECT。
        """
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
        """按 |、&&、||、; 拆分 shell 命令（引号感知状态机，与 command_arity._split_chain 逻辑一致）。

        参数：
            command: 原始命令字符串。

        逻辑：
            处理最常见的几种链式/管道 shell 元字符；逐字符扫描并用 in_single/in_double
            两个状态位跟踪是否处于引号内，只在引号外遇到这些元字符时才切分，
            确保每个切分出的分段都是可以独立分类的单个命令。

        返回：
            按顺序排列的命令分段列表。
        """
        segments: list[str] = []
        current: list[str] = []
        in_single = False
        in_double = False

        i = 0
        while i < len(command):
            ch = command[i]

            # 处理引号状态
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

            # 只在引号外的元字符处切分
            if not in_single and not in_double:
                # 检查 &&（须先于单个 & 判断）
                if ch == '&' and i + 1 < len(command) and command[i + 1] == '&':
                    segments.append(''.join(current))
                    current = []
                    i += 2  # 跳过两个 &
                    continue
                # 检查 ||（须先于单个 | 判断）
                elif ch == '|' and i + 1 < len(command) and command[i + 1] == '|':
                    segments.append(''.join(current))
                    current = []
                    i += 2  # 跳过两个 |
                    continue
                # 检查 |（单个管道）
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
        """检测命令中（引号外）出现了哪些 shell 操作符，用于生成 reasons 说明文本。

        参数：
            command: 原始命令字符串。

        逻辑：
            逐字符扫描并跟踪引号状态，只在引号外识别 &&/||/|/;/>/>>/2>，
            避免把引号内的同名字符误判为操作符（如 ``python3 -c "a; b"`` 中的 ";"
            是内联代码的一部分，不是真正的 shell 分隔符）。

        返回：
            各操作符是否出现的布尔字典，key 包括：
            pipe（|）、chain（&&或||）、semicolon（;）、redirect（>）、
            append_redirect（>>）、stderr_redirect（2>或2>>）。
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
        """校验 argv 参数中所有看起来像路径的项是否都在允许目录范围内。

        参数：
            args: 待校验的参数列表（一般是 argv[1:]，即命令本身之后的所有参数）。
            command_name: 命令名，当前实现未使用，保留用于未来按命令定制校验逻辑
                （签名保持不变，未改动调用方式）。

        逻辑：
            委托给 shell_security._validate_path_arguments 做逐参数路径提取与校验；
            该方法内部会用 path_security 判断每个候选路径是否越界，越界则抛 SecurityError。

        返回：
            校验通过返回 None；校验失败（含任意异常，不局限于 SecurityError）返回错误信息字符串，
            调用方据此判 DENY 并把该字符串作为拒绝原因。
        """
        try:
            self.shell_security._validate_path_arguments(args, self.path_security)
            return None
        except Exception as e:
            return str(e)

    def _is_trusted(self, command: str) -> bool:
        """判断命令是否命中当前会话已建立的信任规则。

        参数：
            command: 原始命令字符串。

        逻辑：
            未配置 trust_store 或没有 session_id 时（如无会话上下文的一次性调用），
            直接判为不信任，返回 False；否则委托 trust_store.matches 按
            permission="shell" 查该会话下是否有匹配的信任规则（fnmatch 风格）。

        返回：
            是否命中信任规则。
        """
        if not self.trust_store or not self._session_id:
            return False
        return self.trust_store.matches(self._session_id, "shell", command)

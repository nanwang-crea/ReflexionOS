# backend/app/security/shell_security.py
# shell 命令解析与路径参数校验：负责把原始命令字符串解析成 argv、
# 检测是否含 shell 元字符（决定后续走 argv 严格校验还是整体 shell 效果分类），
# 并对命令参数中"看起来像路径"的部分做词法级别的路径校验。
# 效果分类（判断命令危险程度）已迁移到 CommandEffectRegistry + CommandPolicy，
# 本类只保留解析和路径这两项相对独立、可复用的职责，策略层再基于此做平台专属的安全规则叠加。
import logging
import os
import re
import shlex
import sys
from dataclasses import dataclass

from app.errors import SecurityError
from app.security.path_security import PathSecurity

logger = logging.getLogger(__name__)


@dataclass
class ValidateResult:
    """validate_command 的解析结果。

    字段：
        argv: 解析出的参数数组。
        has_meta: 命令中是否检测到 shell 元字符（; & | < > ` 或 $(），
            决定 CommandPolicy 后续走 argv 严格路径 还是 完整 shell 表达式路径。
    """
    argv: list[str]
    has_meta: bool


class ShellSecurity:
    """解析 shell 命令并校验其中形似路径的参数。

    效果分类（命令有多危险）已经迁移到 CommandEffectRegistry + CommandPolicy；
    本类刻意保持职责单一：检测 shell 元字符、把命令拆成 argv 形式，
    并在策略层决定是否允许执行之前，先对明显的路径参数做一次校验。
    """

    # 检测会强制走 shell 表达式路径（而非更严格的纯 argv 路径）的操作符。
    # 引号内的字符由后续 shlex 解析阶段处理，这里只做粗粒度探测。
    SHELL_META_PATTERN = re.compile(r"[;&|<>`]|[$][(]")

    # 参数不会被当作路径处理的命令白名单（如 echo 的参数是任意文本，不是路径）
    NON_PATH_ARGUMENT_COMMANDS = {"echo"}

    def __init__(self, platform_name: str | None = None):
        """初始化。

        参数：
            platform_name: 平台标识字符串；未传时用 sys.platform（便于测试时注入固定平台名）。
        """
        self.platform_name = platform_name or sys.platform

    @property
    def platform_label(self) -> str:
        """返回人类可读的平台名称（Windows/macOS/Linux/其他原始值），用于日志和提示文案。"""
        if self._is_windows():
            return "Windows"
        if self.platform_name == "darwin":
            return "macOS"
        if self.platform_name.startswith("linux"):
            return "Linux"
        return self.platform_name

    @property
    def command_hint(self) -> str:
        """返回面向调用方（如 LLM 代理）的平台相关命令提示文案。

        逻辑：
            Windows 下提示优先用原生命令、说明 cmd/powershell 需要审批、
            以及 % 在 cmd/PowerShell 中的特殊转义问题；非 Windows 下提示
            低风险命令可直接执行，含管道/重定向的命令是否需要审批取决于效果分类。
            纯文案性质，不参与任何安全判定。

        返回：
            提示文本字符串。
        """
        if self._is_windows():
            return (
                "Current platform is Windows. Use Windows executable commands, e.g. `where python`, "
                "`python --version`. `cmd /c` and `powershell -Command` are allowed but require user "
                "approval (they may take a while to be approved) — prefer direct commands when possible. "
                "`%` is special in both cmd (batch variable, e.g. `%D`) and PowerShell (ForEach-Object alias) — "
                "commands like `git log --pretty=format:\"%h|%an\"` will fail or be misparsed unless escaped "
                "(`%%h` in cmd, `` `%h `` in PowerShell). Prefer `git shortlog` or `--no-pager` with a "
                "simple format when possible to avoid escaping issues."
            )
        return (
            f"Current platform is {self.platform_label}. "
            "Low-risk commands execute directly; commands with pipes `|` or redirects `>` may require approval, "
            "depending on the command's effect classification (read-only pipes like `git log | head` execute directly)."
        )

    def validate_command(
        self,
        command: str,
        path_security: PathSecurity | None = None,
    ) -> ValidateResult:
        """解析命令并检测 shell 元语法。

        参数：
            command: 原始命令字符串。
            path_security: 可选的路径安全校验器；传入时会对解析出的参数做路径校验，
                不传则只解析不校验路径（校验职责留给上层策略统一处理）。

        逻辑：
            1. 空命令直接拒绝。
            2. 用 SHELL_META_PATTERN 粗粒度探测是否含 shell 元字符（has_meta），
               供上层决定走 argv 严格路径还是 shell 表达式路径。
            3. 用 shlex.split 解析出 argv；Windows 下用 posix=False 保留反斜杠路径
               （如 C:\\Users\\foo），代价是不会像 posix 模式那样剥离引号，
               所以额外对每个 token 调用 _strip_wrapping_quotes，剥离"整体被一对双引号
               包裹"的 token（否则如 powershell -Command "Write-Output 'x'" 这种整体加引号的
               参数会带着字面引号传给 subprocess，PowerShell 收到后只会回显而不执行）。
            4. 解析结果为空同样拒绝。
            5. 若传入 path_security 且命令名不在 NON_PATH_ARGUMENT_COMMANDS 白名单中
               （如 echo，其参数是任意文本不是路径），对 argv[1:] 做词法级路径校验——
               这里的校验是"尽力而为"的词法判断，策略层（CommandPolicy）执行前仍会
               再做一次自己的边界检查，不依赖这里作为唯一防线。

        返回：
            ValidateResult(argv=解析出的参数数组, has_meta=是否含 shell 元字符)。

        异常：
            SecurityError(detail.source="shell"): 命令为空或 shlex 解析失败时抛出
            （调用方 command_policy.py 会识别这个 source 标记，转成 DENY 而不是向上传播）。
        """
        command_normalized = command.strip()
        if not command_normalized:
            raise SecurityError(message="命令不能为空", detail={"source": "shell"})

        has_meta = bool(self.SHELL_META_PATTERN.search(command_normalized))

        try:
            argv = shlex.split(command_normalized, posix=not self._is_windows())
        except ValueError as exc:
            raise SecurityError(message=f"命令解析失败: {exc}", detail={"source": "shell"}) from exc

        if self._is_windows():
            # shlex.split(posix=False) 为保留 Windows 路径反斜杠（如 C:\Users\foo），
            # 不会像 posix 模式那样剥离引号，导致整段被双引号包裹的参数
            # （如 powershell -Command "Write-Output 'x'"）原样带着外层引号传给 subprocess，
            # PowerShell/cmd 收到字面量引号后不会当命令执行，而是原样回显。
            # 这里只剥离"整体被一对双引号包裹"的 token，不触碰未加引号的路径参数。
            argv = [self._strip_wrapping_quotes(token) for token in argv]

        if not argv:
            raise SecurityError(message="命令不能为空", detail={"source": "shell"})

        command_name = self._command_name(argv[0])

        if path_security and command_name not in self.NON_PATH_ARGUMENT_COMMANDS:
            # 这里的路径校验刻意是词法/尽力而为的。策略层在真正执行前仍会做自己的边界检查。
            self._validate_path_arguments(argv[1:], path_security)

        logger.info("命令解析完成: %s (has_meta=%s)", command, has_meta)
        return ValidateResult(argv=argv, has_meta=has_meta)

    def _is_windows(self) -> bool:
        """判断当前平台名是否为 Windows（platform_name 以 "win" 开头）。"""
        return self.platform_name.startswith("win")

    @staticmethod
    def _strip_wrapping_quotes(token: str) -> str:
        """剥离整体被一对双引号包裹的 token 的外层引号（仅 Windows posix=False 场景使用）"""
        if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
            return token[1:-1]
        return token

    def _command_name(self, command: str) -> str:
        """归一化命令名：统一路径分隔符后取最后一段、转小写、去 Windows 可执行后缀。

        参数：
            command: 命令字符串（可能带路径，如 "/usr/bin/git" 或 argv[0]）。

        逻辑：
            与 command_effect_registry._normalize_command_name 逻辑一致：
            统一反斜杠为正斜杠后取最后一段（去路径前缀），转小写后剥离
            .exe/.cmd/.bat/.com 后缀，确保同一命令的不同调用形式能归一到同一个名字，
            供 NON_PATH_ARGUMENT_COMMANDS 白名单判断和后续效果分类使用。

        返回：
            归一化后的命令名。
        """
        normalized = command.replace("\\", "/").split("/")[-1].lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if normalized.endswith(suffix):
                return normalized[:-len(suffix)]
        return normalized

    def _validate_path_arguments(self, args: list[str], path_security: PathSecurity) -> None:
        """逐个校验参数列表中形似路径的候选项是否在允许范围内。

        参数：
            args: 待校验的参数列表（一般是命令本身之后的所有参数）。
            path_security: 路径安全校验器。

        逻辑：
            对每个参数先用 _path_candidates 提取出"可能是路径"的候选字符串
            （如 --path=xxx 这种带等号的 flag 会取等号后的值），
            再用 _looks_like_path 过滤出真正形似路径的候选。
            对形似路径的候选：
              - 若是 Windows 风格绝对路径（如 C:\\foo）但当前运行平台不是 Windows，
                直接拒绝——这类路径在非 Windows 上无法被 os.path 正确处理，
                与其让它被错误解析为相对路径从而意外通过校验，不如直接拒绝；
              - 否则展开 ~ 后交给 path_security.validate_path 做正式的目录范围校验，
                越界会抛 SecurityError 并中断遍历。

        返回：
            无返回值；校验通过静默返回，校验失败抛出异常（不捕获，交给调用方处理）。
        """
        for arg in args:
            for candidate in self._path_candidates(arg):
                if not self._looks_like_path(candidate):
                    continue
                if self._is_windows_absolute_path(candidate) and not self._is_windows():
                    raise SecurityError(
                        message=f"路径不在允许范围内: {candidate}",
                        detail={"source": "shell"},
                    )
                path_security.validate_path(os.path.expanduser(candidate))

    # Windows 风格标志：/c、/k、/Command 这类"斜杠+纯字母"参数（cmd、powershell 的标志语法），
    # 与真实的类 Unix 绝对路径（如 /mnt/c/foo，含多段路径分隔符）区分开，避免被误判为路径参数
    _WINDOWS_STYLE_FLAG_PATTERN = re.compile(r"^/[A-Za-z]+$")

    def _path_candidates(self, arg: str) -> list[str]:
        """从单个参数中提取"可能是路径"的候选字符串。

        参数：
            arg: 单个 argv 参数。

        逻辑：
            - 形如 "--path=value" 的带等号 flag：取等号后的值作为候选
              （flag 名本身不是路径，值才可能是）。
            - 纯 flag（以 "-" 开头但无等号，如 "-rf"）：不产生候选，直接返回空列表
              （flag 本身不是路径参数）。
            - Windows 风格纯字母标志（如 "/c"，命中 _WINDOWS_STYLE_FLAG_PATTERN）：
              同样返回空列表，避免和真正的类 Unix 绝对路径混淆。
            - 其余情况：整个参数本身作为候选。

        返回：
            候选字符串列表（0 个或 1 个元素）。
        """
        if arg.startswith("-") and "=" in arg:
            return [arg.split("=", 1)[1]]
        if arg.startswith("-"):
            return []
        if self._WINDOWS_STYLE_FLAG_PATTERN.match(arg):
            return []
        return [arg]

    def _looks_like_path(self, value: str) -> bool:
        """词法判断一个字符串是否"形似路径"（用于决定是否需要走路径校验）。

        参数：
            value: 候选字符串。

        逻辑（命中任一条件即判定为形似路径）：
            - 空字符串直接判否。
            - 恰好是 "." 或 ".."。
            - 以 ~、/、\\、./、../、.\\、..\\ 开头（常见的相对/绝对路径前缀）。
            - 是 Windows 风格绝对路径（如 C:\\foo 或 \\\\server\\share）。
            - 含 "/" 或 "\\"（多段路径分隔符，暗示是路径而非单纯的参数值）。
            - 以常见源码/配置文件后缀结尾（.py/.js/.json/.md/... 等），
              即便没有路径分隔符（如裸文件名 "config.yaml"）也当作路径处理。
            这是一个宁可"宽泛识别、多校验几个非路径参数"，也不要漏判真实路径参数的策略——
            漏判会让越界路径绕过校验，而误判最多只是多做一次无害的路径校验。

        返回：
            是否形似路径。
        """
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
        """判断字符串是否为 Windows 风格绝对路径（盘符路径或 UNC 路径）。

        参数：
            value: 候选字符串。

        逻辑：
            匹配 "字母:\\" 或 "字母:/"（如 C:\\foo、C:/foo）这类盘符路径，
            或以 "\\\\" 开头的 UNC 网络路径（如 \\\\server\\share）。

        返回：
            是否为 Windows 风格绝对路径。
        """
        return bool(re.match(r"^[a-zA-Z]:[\\/]", value) or value.startswith("\\\\"))

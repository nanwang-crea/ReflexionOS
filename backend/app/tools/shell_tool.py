# Shell 命令执行工具：Agent 可调用的最高权限工具，负责在受控沙箱内执行任意 shell 命令。
# 核心流程：CommandPolicy 先评估命令风险（ALLOW/REQUIRE_APPROVAL/DENY），
# 低风险命令直接执行，高风险/含网络访问的命令需人工审批；
# 执行时优先走 OS 级沙箱（SandboxProvider，默认禁网+限制路径访问），
# Windows/macOS/Linux 各自有独立的子进程执行分支（因异步子进程支持程度不同）。
import asyncio
import logging
import os
import sys
from typing import Any

from app.config.settings import config_manager
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.command_policy import CommandAction, CommandDecision, CommandPolicy
from app.security.effect_category import EffectCategory
from app.security.path_security import ExternalPathError, PathSecurity
from app.security.permission_mode import PermissionMode
from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.error_detector import SandboxErrorDetector, SandboxErrorInfo, SandboxErrorType
from app.security.sandbox.factory import NullSandbox
from app.security.sandbox.windows_cmd import is_cmd_internal_command
from app.security.session_trust_store import SessionTrustStore
from app.security.shell_security import ShellSecurity
from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult

logger = logging.getLogger(__name__)

# 模块级缓存：conda base 环境变量只探测一次，避免每次执行命令都重复调用 conda hook
_CONDA_BASE_ENV: dict[str, str] | None = None


def _get_conda_base_env() -> dict[str, str] | None:
    """探测并缓存 conda/mamba 的 base 环境变量（用于让 shell 命令继承 conda 环境）。

    入参：无。
    功能：
      1. 若已缓存过结果（非 None）直接返回；
      2. 查找 conda/mamba 可执行文件路径（优先环境变量 CONDA_EXE/MAMBA_EXE，其次 PATH 查找）；
      3. 未找到可执行文件则缓存空字典并返回 None（表示不使用 conda 环境）；
      4. 执行 `conda shell.bash hook` 拿到其导出的环境变量文本，解析 export 语句合并进当前环境；
      5. 任何异常都静默失败，缓存空字典，不影响主流程。
    出参：dict[str, str] | None - 合并了 conda base 环境的变量字典；探测失败或无 conda 时返回 None。
    """
    global _CONDA_BASE_ENV
    if _CONDA_BASE_ENV is not None:
        return _CONDA_BASE_ENV
    try:
        import subprocess
        conda_exe = os.environ.get("CONDA_EXE") or os.environ.get("MAMBA_EXE")
        if not conda_exe:
            for candidate in ("conda", "mamba"):
                import shutil
                found = shutil.which(candidate)
                if found:
                    conda_exe = found
                    break
        if not conda_exe:
            _CONDA_BASE_ENV = {}
            return None
        result = subprocess.run(
            [conda_exe, "shell.bash", "hook"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            _CONDA_BASE_ENV = {}
            return None
        env_lines = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("export ") and "=" in stripped:
                env_lines.append(stripped[len("export "):])
        env = dict(os.environ)
        for assignment in env_lines:
            key, _, value = assignment.partition("=")
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            env[key] = value
        _CONDA_BASE_ENV = env
        return _CONDA_BASE_ENV
    except Exception:
        _CONDA_BASE_ENV = {}
        return None


class ShellTool(BaseTool):
    """Shell 命令执行工具

    能力边界：可执行任意 shell/argv 命令，但受 CommandPolicy 风险评估约束——
    低风险命令直接跑；高风险命令、涉及网络访问的命令需要走审批流程；
    执行环境默认套一层 OS 沙箱（禁网、限制可访问路径），沙箱不可用时退化为直接执行。
    """

    def __init__(
        self,
        security: ShellSecurity,
        path_security: PathSecurity,
        registry: CommandEffectRegistry | None = None,
        sandbox: SandboxProvider | None = None,
        session_id: str | None = None,
        trust_store: SessionTrustStore | None = None,
        permission_mode: PermissionMode = PermissionMode.AUTO,
    ):
        """初始化 ShellTool。

        入参：
          - security (ShellSecurity): shell 命令安全策略（危险命令识别等）
          - path_security (PathSecurity): 路径安全校验器，限制命令可访问的目录范围
          - registry (CommandEffectRegistry | None): 命令效果注册表（识别命令是否常需要网络等），缺省新建默认实例
          - sandbox (SandboxProvider | None): 沙箱执行器，缺省使用 NullSandbox（即不启用沙箱）
          - session_id (str | None): 当前会话 ID，用于查询/记录会话级信任规则
          - trust_store (SessionTrustStore | None): 会话信任存储（记录用户"总是允许"的规则）
          - permission_mode (PermissionMode): 权限模式，默认 AUTO（按策略自动判断是否需要审批）
        功能：组装 CommandPolicy（命令风险评估器）与沙箱可用性标记，供 execute 使用。
        """
        self.security = security
        self.path_security = path_security
        self.registry = registry or CommandEffectRegistry()
        self.sandbox = sandbox or NullSandbox()
        self._session_id = session_id
        self.trust_store = trust_store
        self.permission_mode = permission_mode
        self.sandbox_available = self.sandbox.is_available()
        self.policy = CommandPolicy(
            security, path_security, self.registry,
            trust_store=trust_store, session_id=session_id,
            permission_mode=permission_mode,
            sandbox_available=self.sandbox_available,
        )
        self.sandbox_error_detector = SandboxErrorDetector()

    def _build_env(self) -> dict[str, str]:
        """构造子进程执行环境变量。

        入参：无。
        功能：优先使用带 conda base 环境的变量表（若探测到 conda），否则退化为当前进程环境副本。
        出参：dict[str, str] - 传给 subprocess 的 env 参数。
        """
        conda_env = _get_conda_base_env()
        if conda_env:
            return conda_env
        return dict(os.environ)

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        # 面向 LLM 的工具功能说明，保留英文原文；动态拼入当前平台标签和命令提示
        return (
            f"Execute safe commands (current platform: {self.security.platform_label}). "
            "Low-risk commands execute directly; high-risk commands and commands containing shell metacharacters require user approval. "
            "Commands run inside an OS-level sandbox that blocks network access by default. "
            "Set requires_network=true when the command needs internet access — this will prompt the user for network approval "
            "before execution, avoiding a guaranteed failure. "
            f"{self.security.command_hint}"
        )

    def get_schema(self) -> dict[str, Any]:
        """返回本工具的 JSON Schema 定义（供 LLM 函数调用使用）。

        入参：无
        功能：声明 shell 工具的参数结构——command（必填，待执行命令）、
        requires_network（可选，是否需要联网，用于提前触发网络审批而非执行失败）、
        cwd（可选，工作目录）、timeout（可选，超时秒数）。
        出参：dict - OpenAI/Anthropic 兼容的 tool schema 字典。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            f"Command to execute. {self.security.command_hint} "
                            "The sandbox blocks network by default. If the command needs internet, set requires_network=true."
                        ),
                    },
                    "requires_network": {
                        "type": "boolean",
                        "description": (
                            "Set to true if this command needs internet access (e.g. pip install, npm install, "
                            "cargo build, go mod download, curl, wget, API calls, git clone/push/fetch). "
                            "This triggers a network approval before execution instead of running and failing."
                        ),
                    },
                    "cwd": {"type": "string", "description": "Working directory for command execution, optional"},
                    "timeout": {"type": "integer", "description": "Command timeout in seconds, optional"},
                },
                "required": ["command"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行 shell 命令的入口方法，先做策略评估再决定直接执行/走审批。

        入参：args (dict) - 包含 command（必填）、cwd（可选工作目录）、
        timeout（可选超时秒数，默认取全局配置）、requires_network（可选，是否需要联网）、
        _approved_decision（内部字段，审批通过后回填的决策数据，跳过重新评估直接执行）。
        功能：
          1. 若带有 _approved_decision（说明是审批通过后的重放调用），直接执行该决策；
          2. 否则用 CommandPolicy.evaluate 评估命令风险，得到 decision；
          3. DENY 直接拒绝并返回原因；
          4. 若命令可能需要网络访问且尚未获得网络权限，创建网络审批请求（proactive）；
          5. 若策略要求审批（REQUIRE_APPROVAL），创建审批请求；
          6. 否则直接执行该决策。
        出参：ToolResult - 执行结果，或 approval_required=True 的审批请求。
        """
        command = args.get("command")
        cwd = args.get("cwd")
        timeout = args.get("timeout", config_manager.settings.execution.max_execution_time)
        requires_network = args.get("requires_network", False)

        if not command:
            return ToolResult(success=False, error="缺少 command 参数")

        approved_decision_data = args.get("_approved_decision")
        if approved_decision_data:
            return await self._execute_approved_decision(approved_decision_data, timeout)

        decision = self.policy.evaluate(command=command, cwd=cwd, timeout=timeout)

        if decision.action == CommandAction.DENY:
            reason_str = "; ".join(decision.reasons) if decision.reasons else "命令被拒绝"
            return ToolResult(success=False, error=reason_str)

        needs_network_approval = self._needs_network_approval(decision, requires_network)
        if needs_network_approval:
            return self._create_network_approval_result(decision, proactive=True)

        if decision.action == CommandAction.REQUIRE_APPROVAL:
            return self._create_approval_result(decision)

        return await self._execute_decision(decision, requires_network=requires_network)

    def _needs_network_approval(self, decision: CommandDecision, requires_network: bool) -> bool:
        """判断本次命令是否需要先弹出"网络访问审批"再执行。

        入参：
          - decision (CommandDecision): 策略评估结果
          - requires_network (bool): 调用方（LLM）显式声明的是否需要联网
        功能：
          1. 沙箱不可用时，网络审批无意义（无法真正拦截），直接返回 False；
          2. 若命令本身效果分类就是允许的网络出站类型，不需要额外审批；
          3. 若当前会话已获得 "sandbox_network:*" 的信任授权，不需要再问；
          4. 调用方显式声明 requires_network=True 时需要审批；
          5. 或者命令的可执行文件在 registry 中被标记为"常需要网络"（如 pip/npm）时也需要审批。
        出参：bool - True 表示需要先走网络审批流程。
        """
        if not self.sandbox.is_available():
            return False
        if decision.effect_category == EffectCategory.NETWORK_OUT:
            return False
        if self._session_id and self.trust_store:
            if self.trust_store.matches(self._session_id, "sandbox_network", "*"):
                return False

        if requires_network:
            return True

        if decision.argv and len(decision.argv) > 0:
            entry = self.registry.lookup(decision.argv[0])
            if entry and entry.often_needs_network:
                return True

        return False

    def _create_network_approval_result(
        self, decision: CommandDecision, proactive: bool = False,
    ) -> ToolResult:
        """构造"需要网络访问权限"的审批请求结果。

        入参：
          - decision (CommandDecision): 命令策略评估结果
          - proactive (bool): True 表示执行前主动检测到需要联网而提前拦截；
            False 表示命令已实际执行、沙箱在运行时才拦截了网络访问（补救性审批）
        功能：生成带唯一 approval_id 的 ToolApprovalRequest，payload 中携带完整的命令决策信息
        （便于审批通过后原样回放执行），suggested_trust 建议用户可选择"总是允许网络访问"。
        出参：ToolResult - success=False 且 approval_required=True，携带 approval 请求对象。
        """
        import uuid

        approval_id = f"approval-{uuid.uuid4().hex[:12]}"

        if proactive:
            summary = f"命令需要网络访问: {decision.command}"
            reasons = ["此命令需要网络访问（如下载依赖、API 调用等），沙箱默认禁止网络"]
            risks = ["允许网络访问可能导致数据外传"]
        else:
            summary = f"沙箱阻止了网络访问: {decision.command}"
            reasons = ["命令需要网络访问，但沙箱默认禁止网络"]
            risks = ["允许网络访问可能导致数据外传"]

        approval = ToolApprovalRequest(
            approval_id=approval_id,
            tool_name="shell",
            summary=summary,
            reasons=reasons,
            risks=risks,
            payload={
                "command": decision.command,
                "execution_mode": decision.execution_mode,
                "argv": decision.argv,
                "cwd": decision.cwd,
                "timeout": decision.timeout,
                "approval_kind": "sandbox_network_elevation",
                "suggested_prefix_rule": decision.suggested_prefix_rule,
                "effect_category": decision.effect_category.value if decision.effect_category else None,
                "elevation_request": {"type": "network", "denied_paths": []},
                "environment_snapshot": decision.environment_snapshot.model_dump() if decision.environment_snapshot else None,
                "approved_decision": decision.model_dump(),
            },
            suggested_action="allow_once",
            suggested_trust={"permission": "sandbox_network", "pattern": "*"},
        )

        return ToolResult(
            success=False,
            approval_required=True,
            approval=approval,
        )

    async def _execute_approved_decision(
        self, decision_data: dict, default_timeout: int
    ) -> ToolResult:
        """重放一个已经通过用户审批的命令决策，直接执行不再重新评估风险。

        入参：
          - decision_data (dict): execute 参数中 _approved_decision 字段的原始数据，
            即之前 _create_approval_result/_create_network_approval_result 生成的 payload
          - default_timeout (int): 备用超时时间（当前实现未直接使用，decision 自带 timeout）
        功能：反序列化为 CommandDecision，若审批时申请的是"提权"（elevation_request，网络或路径），
        将对应的沙箱豁免标记写回 decision 私有属性，再交给 _execute_decision 实际执行。
        出参：ToolResult - 命令执行结果。
        """
        decision = CommandDecision.model_validate(decision_data)
        elevation = decision_data.get("elevation_request")

        if elevation:
            if elevation["type"] == "network":
                decision._sandbox_allow_network = True
            elif elevation["type"] == "path":
                decision._sandbox_extra_paths = elevation["denied_paths"]

        return await self._execute_decision(decision)

    async def _execute_decision(self, decision: CommandDecision, requires_network: bool = False) -> ToolResult:
        """按策略决策的执行模式（shell / argv）分发实际执行，并统一处理异常。

        入参：
          - decision (CommandDecision): 已通过风险评估（或审批）的命令决策，
            包含 execution_mode（"shell"或argv模式）、command、argv、cwd、timeout、effect_category 等
          - requires_network (bool): 是否额外授予网络访问权限（叠加到 decision 自带的沙箱豁免标记上）
        功能：
          1. 汇总网络放行标记与额外允许路径（来自 decision 私有属性 + 会话信任规则）；
          2. execution_mode == "shell" 时走 _execute_shell（cmd.exe/bash 解释执行，支持管道等）；
          3. 否则走 argv 模式（直接 CreateProcess/exec，更安全但不支持 shell 语法）；
             其中 Windows 下若 argv[0] 是 cmd 内部命令（无独立 exe，如 dir/copy），
             会降级为 shell 模式执行，因为 CreateProcess 找不到这类命令的可执行文件；
          4. 统一捕获 FileNotFoundError/OSError/Exception，转换为带 exit code 的友好错误信息。
        出参：ToolResult - 命令执行结果或错误信息。
        """
        cwd = decision.cwd or self.path_security.base_dir
        timeout = decision.timeout

        sandbox_allow_network = getattr(decision, '_sandbox_allow_network', False) or requires_network
        sandbox_extra_paths = getattr(decision, '_sandbox_extra_paths', [])

        if self._session_id and self.trust_store:
            if self.trust_store.matches(self._session_id, "sandbox_network", "*"):
                sandbox_allow_network = True
            for rule in self.trust_store.get_rules(self._session_id):
                if rule.permission == "sandbox_path":
                    sandbox_extra_paths.append(rule.pattern.rstrip("/*"))

        try:
            if decision.execution_mode == "shell":
                logger.info("开始执行 shell 模式: command=%s, cwd=%s", decision.command, cwd)
                return await self._execute_shell(
                    decision.command, cwd, timeout, decision.effect_category,
                    sandbox_allow_network=sandbox_allow_network,
                    sandbox_extra_paths=sandbox_extra_paths,
                )
            else:
                argv = decision.argv
                if argv is None:
                    return ToolResult(success=False, error="argv 模式决策缺少 argv")
                # Windows: cmd 内部命令（if/mkdir/copy/dir 等）无独立 .exe，
                # CreateProcess 找不到可执行文件必败，降级走 shell 模式（cmd.exe /c）。
                # 复用 decision.command 原始字符串，不用 list2cmdline 重建（实测会破坏带引号的路径）。
                if sys.platform == "win32" and is_cmd_internal_command(argv[0] if argv else None):
                    logger.info("argv 首命令为 cmd 内部命令，降级 shell 执行: %s", argv[0])
                    return await self._execute_shell(
                        decision.command, cwd, timeout, decision.effect_category,
                        sandbox_allow_network=sandbox_allow_network,
                        sandbox_extra_paths=sandbox_extra_paths,
                    )
                logger.info("开始执行 argv 模式: argv=%s, cwd=%s", argv, cwd)
                result = await self._execute_argv(
                    argv, cwd, timeout, decision.effect_category,
                    sandbox_allow_network=sandbox_allow_network,
                    sandbox_extra_paths=sandbox_extra_paths,
                )
                logger.info("argv 模式执行完成: success=%s, output_len=%d", result.success, len(result.output or ''))
                return result
        except FileNotFoundError:
            cmd_name = decision.command.split()[0] if decision.command else "command"
            logger.error("命令不存在: %s", decision.command)
            return ToolResult(success=False, error=f"命令未找到: {cmd_name} (exit code 127)", data={"return_code": 127})
        except OSError as e:
            cmd_name = decision.command.split()[0] if decision.command else "command"
            if e.errno == 2 or "not found" in str(e).lower():
                logger.error("命令不存在: %s", decision.command)
                return ToolResult(success=False, error=f"命令未找到: {cmd_name} (exit code 127)", data={"return_code": 127})
            logger.error("Shell 执行系统错误: %s", e)
            return ToolResult(success=False, error=f"执行错误: {e} (errno={e.errno})", data={"return_code": -1})
        except Exception as e:
            logger.error("Shell 执行异常: %s (type=%s)", e, type(e).__name__, exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _execute_argv(
        self, argv: list[str], cwd: str, timeout: int,
        effect_category: EffectCategory | None = None,
        sandbox_allow_network: bool = False,
        sandbox_extra_paths: list[str] | None = None,
    ) -> ToolResult:
        """以 argv 数组形式执行命令（不经过 shell 解释，更安全，不支持管道/通配符等 shell 语法）。

        入参：
          - argv (list[str]): 命令及其参数列表
          - cwd (str): 工作目录
          - timeout (int): 超时秒数
          - effect_category (EffectCategory | None): 命令效果分类（用于判断是否天然需要联网）
          - sandbox_allow_network (bool): 是否放行网络访问
          - sandbox_extra_paths (list[str] | None): 额外允许访问的路径
        功能：
          1. 沙箱可用时，Windows 优先尝试 sandbox.run_command（CreateProcessAsUser+Restricted Token）
             直接返回结果；否则用 sandbox.wrap_command 包装 argv 后再走普通子进程执行；
          2. Windows 下用线程池跑同步 subprocess（事件循环不支持子进程 API）；
             其他平台用 asyncio.create_subprocess_exec 原生异步执行；
          3. 等待执行完成，超时则杀掉进程并返回超时错误；
          4. Windows 下对 stdout/stderr 做 UTF-8→GBK 兜底解码；
          5. 非零退出码时，先用 SandboxErrorDetector 判断是否是"沙箱拦截导致的失败"
             （是则转为审批请求，让用户决定是否提权重试），否则返回友好错误信息。
        出参：ToolResult - 命令执行结果，或需要提权审批时返回 approval_required 请求。
        """
        if self.sandbox.is_available():
            allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
            allowed_paths = list(self.path_security.allowed_base_paths)
            if sandbox_extra_paths:
                allowed_paths.extend(sandbox_extra_paths)

            # Windows: 优先走 sandbox.run_command（CreateProcessAsUser + Restricted Token）
            if sys.platform == "win32":
                result = self.sandbox.run_command(
                    argv, cwd=cwd, timeout=timeout,
                    allowed_paths=allowed_paths,
                    allow_network=allow_network,
                )
                if result is not None:
                    return ToolResult(
                        success=result.success, output=result.output,
                        error=result.error, data={"return_code": result.return_code},
                    )

            argv = self.sandbox.wrap_command(
                argv, cwd=cwd, allowed_paths=allowed_paths, allow_network=allow_network,
            )

        # Windows: 用线程池执行同步 subprocess，不依赖事件循环的子进程支持
        if sys.platform == "win32":
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,  # 使用默认线程池
                self._sync_subprocess_run,
                argv,
                cwd,
                timeout,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
                env=self._build_env(),
            )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            logger.error("命令执行超时: %s", " ".join(argv))
            return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")

        # Windows 上需要处理 GBK 编码
        if sys.platform == "win32":
            try:
                output = stdout.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    output = stdout.decode("gbk")
                except UnicodeDecodeError:
                    output = stdout.decode("utf-8", errors="replace")

            try:
                error = stderr.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    error = stderr.decode("gbk")
                except UnicodeDecodeError:
                    error = stderr.decode("utf-8", errors="replace")
        else:
            output = stdout.decode("utf-8", errors="ignore")
            error = stderr.decode("utf-8", errors="ignore")

        if process.returncode == 0:
            logger.info("argv 命令执行成功: %s", " ".join(argv))
            return ToolResult(success=True, output=output, data={"return_code": process.returncode})
        else:
            logger.warning("argv 命令执行失败: %s, 返回码: %s", " ".join(argv), process.returncode)
            error_info = self.sandbox_error_detector.detect(
                returncode=process.returncode,
                stderr=error,
                command_argv=argv,
                registry=self.registry,
            )
            if error_info is not None:
                decision = CommandDecision(
                    action=CommandAction.ALLOW,
                    execution_mode="argv",
                    command=" ".join(argv),
                    argv=argv,
                    cwd=cwd,
                    timeout=timeout,
                    effect_category=effect_category,
                )
                return self._create_approval_result(decision, elevation=error_info)
            friendly_error = self._friendly_error(process.returncode, error, output, argv[0] if argv else "")
            return ToolResult(success=False, output=output, error=friendly_error, data={"return_code": process.returncode})

    def _sync_subprocess_run(
        self,
        argv: list[str],
        cwd: str,
        timeout: int,
    ) -> ToolResult:
        """
        同步执行 subprocess（argv 模式），在线程池中调用。
        仅用于 Windows 平台，绕过事件循环的子进程支持限制。

        Args:
            argv: 命令参数列表
            cwd: 工作目录
            timeout: 超时秒数

        Returns:
            ToolResult: 执行结果
        """
        import subprocess

        try:
            result = subprocess.run(
                argv,
                cwd=cwd,
                env=self._build_env(),
                capture_output=True,
                timeout=timeout,
                check=False,  # 不抛异常，通过返回码判断
            )

            # GBK/UTF-8 编码降级（复用现有逻辑）
            output = self._decode_windows_output(result.stdout)
            error = self._decode_windows_output(result.stderr)

            return ToolResult(
                success=(result.returncode == 0),
                output=output.strip(),
                error=error.strip() if error else None,
                data={"return_code": result.returncode},
            )
        except subprocess.TimeoutExpired:
            logger.error("同步 subprocess 执行超时: %s", " ".join(argv))
            return ToolResult(
                success=False,
                output=None,
                error=f"命令执行超时（{timeout}秒）",
            )
        except Exception as e:
            logger.error("同步 subprocess 执行异常: %s", e, exc_info=True)
            return ToolResult(success=False, output=None, error=str(e))

    def _decode_windows_output(self, data: bytes) -> str:
        """
        解码 Windows 子进程输出，GBK/UTF-8 降级处理。

        Args:
            data: 子进程输出的原始字节

        Returns:
            str: 解码后的字符串
        """
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

    def _sync_subprocess_run_shell(
        self,
        command: str,
        cwd: str,
        timeout: int,
    ) -> ToolResult:
        """
        同步执行 subprocess（shell 模式），在线程池中调用。
        仅用于 Windows 平台，绕过事件循环的子进程支持限制。

        注意：接收原始命令，内部包装 cmd.exe /c

        Args:
            command: 原始 shell 命令（不含 cmd.exe /c）
            cwd: 工作目录
            timeout: 超时秒数

        Returns:
            ToolResult: 执行结果
        """
        import subprocess

        shell_command = f'cmd.exe /c "{command}"'

        try:
            result = subprocess.run(
                shell_command,
                cwd=cwd,
                env=self._build_env(),
                capture_output=True,
                timeout=timeout,
                shell=True,  # shell 模式
                check=False,
            )

            output = self._decode_windows_output(result.stdout)
            error = self._decode_windows_output(result.stderr)

            return ToolResult(
                success=(result.returncode == 0),
                output=output.strip(),
                error=error.strip() if error else None,
                data={"return_code": result.returncode},
            )
        except subprocess.TimeoutExpired:
            logger.error("同步 shell subprocess 执行超时: %s", command)
            return ToolResult(
                success=False,
                output=None,
                error=f"Shell 命令执行超时（{timeout}秒）",
            )
        except Exception as e:
            logger.error("同步 shell subprocess 执行异常: %s", e, exc_info=True)
            return ToolResult(success=False, output=None, error=str(e))

    async def _execute_shell(
        self, command: str, cwd: str, timeout: int,
        effect_category: EffectCategory | None = None,
        sandbox_allow_network: bool = False,
        sandbox_extra_paths: list[str] | None = None,
    ) -> ToolResult:
        """以 shell 解释执行命令（支持管道、重定向、通配符等 shell 语法）。

        入参：
          - command (str): 原始 shell 命令字符串
          - cwd (str): 工作目录
          - timeout (int): 超时秒数
          - effect_category (EffectCategory | None): 命令效果分类
          - sandbox_allow_network (bool): 是否放行网络访问
          - sandbox_extra_paths (list[str] | None): 额外允许访问的路径
        功能：Windows 与 Unix 分两条执行路径（因为 Windows 下 asyncio 不支持子进程 API，
        且沙箱实现基于 CreateProcessAsUser，机制完全不同）：
          - Windows 分支：先校验 cwd/额外路径是否在允许范围内；沙箱可用时优先走
            sandbox.run_shell_command；沙箱不可用时网络型命令直接拒绝（无法强制隔离），
            本地命令记录警告日志后降级为线程池同步执行（cmd.exe /c）；
          - 非 Windows 分支：沙箱可用时用 sandbox.wrap_shell_command 包装命令字符串，
            再用 asyncio.create_subprocess_shell 在 bash/zsh/sh 下异步执行；
            超时杀进程；非零退出码时同样先判断是否为沙箱拦截，是则转为审批请求。
        出参：ToolResult - 命令执行结果，或需要提权审批时返回 approval_required 请求。
        """
        if sys.platform == "win32":
            # ========== Windows 执行分支（第一阶段 / 第二阶段沙盒）==========

            # 1. 路径限制（与 Unix 对齐）
            try:
                validated_cwd = self.path_security.validate_path(cwd)
            except ExternalPathError as e:
                return ToolResult(success=False, error=f"工作目录不在允许范围: {e}")

            if sandbox_extra_paths:
                for extra_path in sandbox_extra_paths:
                    try:
                        self.path_security.validate_path(extra_path)
                    except ExternalPathError as e:
                        return ToolResult(success=False, error=f"额外路径 {extra_path} 不在允许范围: {e}")

            # 2. 网络权限检查 + 允许路径（与 Unix _execute_argv 对齐）
            allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
            allowed_paths = list(self.path_security.allowed_base_paths)
            if sandbox_extra_paths:
                allowed_paths.extend(sandbox_extra_paths)

            # 3. 沙盒可用时优先走 run_shell_command（CreateProcessAsUser + Restricted Token）
            if self.sandbox.is_available():
                result = self.sandbox.run_shell_command(
                    command, cwd=validated_cwd, timeout=timeout,
                    allowed_paths=allowed_paths,
                    allow_network=allow_network,
                )
                if result is not None:
                    return ToolResult(
                        success=result.success, output=result.output,
                        error=result.error, data={"return_code": result.return_code},
                    )

            # 4. 沙盒不可用时，继续拒绝网络型命令（无沙箱强制）
            if effect_category == EffectCategory.NETWORK_OUT:
                return ToolResult(
                    success=False,
                    error="Windows 第一阶段不支持网络型 shell 命令（无沙箱强制），请在 macOS/Linux 上执行"
                )

            # 5. 本地命令：记录网络权限标志（供审计，但无技术强制）
            if not allow_network:
                logger.warning(
                    "Windows shell 命令未授权网络访问（无沙箱强制）: %s, cwd=%s",
                    command, validated_cwd
                )

            # 6. 审计日志（与 Unix 一致）
            logger.info(
                "执行 Windows shell 命令: %s, cwd=%s, network=%s, effect=%s",
                command, validated_cwd, allow_network, effect_category
            )

            # 7. 回退到同步线程池执行（第一阶段 / 无沙盒）
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._sync_subprocess_run_shell,
                command,
                validated_cwd,
                timeout,
            )

        if self.sandbox.is_available():
            allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
            allowed_paths = list(self.path_security.allowed_base_paths)
            if sandbox_extra_paths:
                allowed_paths.extend(sandbox_extra_paths)
            command = self.sandbox.wrap_shell_command(
                command, cwd=cwd, allowed_paths=allowed_paths, allow_network=allow_network,
            )

        executable = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
        if not os.path.exists(executable):
            executable = "/bin/sh"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            executable=executable,
            env=self._build_env(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            logger.error("Shell 命令执行超时: %s", command)
            return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")

        output = stdout.decode("utf-8", errors="ignore")
        error = stderr.decode("utf-8", errors="ignore")

        if process.returncode == 0:
            logger.info("Shell 命令执行成功: %s", command)
            return ToolResult(success=True, output=output, data={"return_code": process.returncode})
        else:
            logger.warning("Shell 命令执行失败: %s, 返回码: %s", command, process.returncode)
            error_info = self.sandbox_error_detector.detect(
                returncode=process.returncode,
                stderr=error,
                registry=self.registry,
            )
            if error_info is not None:
                decision = CommandDecision(
                    action=CommandAction.ALLOW,
                    execution_mode="shell",
                    command=command,
                    cwd=cwd,
                    timeout=timeout,
                    effect_category=effect_category,
                )
                return self._create_approval_result(decision, elevation=error_info)
            cmd_name = command.split()[0] if command.split() else ""
            friendly_error = self._friendly_error(process.returncode, error, output, cmd_name)
            return ToolResult(success=False, output=output, error=friendly_error, data={"return_code": process.returncode})

    @staticmethod
    def _friendly_error(returncode: int, stderr: str, stdout: str, cmd_name: str) -> str:
        """将进程退出码/stderr 转换为对用户/LLM 更友好的错误提示文本。

        入参：
          - returncode (int): 进程退出码
          - stderr (str): 标准错误输出
          - stdout (str): 标准输出（用于兜底判断"not found"类错误）
          - cmd_name (str): 命令名（用于拼接提示文本）
        功能：按常见退出码含义做特判——127命令未找到、126不可执行、1且无stderr但stdout含
        "not found"也视为命令未找到；否则优先返回 stderr 原文，都没有则给出通用失败提示。
        出参：str - 展示给调用方的错误描述文本。
        """
        if returncode == 127:
            return f"命令未找到: {cmd_name}" if cmd_name else "命令未找到 (exit code 127)"
        if returncode == 126:
            return f"命令不可执行: {cmd_name}" if cmd_name else "命令不可执行 (exit code 126)"
        if returncode == 1 and not stderr.strip() and "not found" in stdout.lower():
            return f"命令未找到: {cmd_name}" if cmd_name else "命令未找到"
        if stderr.strip():
            return stderr.strip()
        if returncode != 0:
            return f"命令失败 (exit code {returncode})"
        return "Unknown error"

    def _create_approval_result(
        self,
        decision: CommandDecision,
        elevation: SandboxErrorInfo | None = None,
    ) -> ToolResult:
        """构造通用的命令审批请求结果（区别于专门的网络审批 _create_network_approval_result）。

        入参：
          - decision (CommandDecision): 命令策略评估结果
          - elevation (SandboxErrorInfo | None): 若命令已实际执行、被沙箱拦截触发的补救性提权信息
            （区分是网络拦截还是路径拦截），为 None 时表示是策略评估阶段就判定需要审批
        功能：
          1. 有 elevation 时，说明命令刚才执行失败是因为沙箱拦截，根据拦截类型
             （NETWORK_DENIED 或路径拒绝）生成对应的审批摘要、理由、风险提示和建议信任规则；
          2. 无 elevation 时，说明是执行前策略就判定为高风险命令，直接用 decision 中的
             reasons/risks/建议前缀规则拼装审批摘要；
          3. 两种情况都生成带完整命令上下文（含 approved_decision 全量数据）的 payload，
             便于用户批准后原样回放执行（见 _execute_approved_decision）。
        出参：ToolResult - success=False 且 approval_required=True，携带 approval 请求对象。
        """
        import uuid

        approval_id = f"approval-{uuid.uuid4().hex[:12]}"

        if elevation is not None:
            if elevation.error_type == SandboxErrorType.NETWORK_DENIED:
                approval_kind = "sandbox_network_elevation"
                summary = f"沙箱阻止了网络访问: {decision.command}"
                reasons = ["命令尝试了网络访问，被沙箱拦截"]
                risks = ["允许网络访问可能导致数据外传"]
                elevation_request = {"type": "network", "denied_paths": []}
            else:
                approval_kind = "sandbox_path_elevation"
                paths_str = ", ".join(elevation.denied_paths)
                summary = f"沙箱阻止了路径访问: {decision.command} — {paths_str}"
                reasons = [f"命令需要访问沙箱外路径: {paths_str}"]
                risks = ["访问项目外路径可能暴露敏感文件"]
                elevation_request = {"type": "path", "denied_paths": elevation.denied_paths}

            suggested_trust = None
            if elevation.error_type == SandboxErrorType.NETWORK_DENIED:
                suggested_trust = {"permission": "sandbox_network", "pattern": "*"}
            elif elevation.denied_paths:
                suggested_trust = {"permission": "sandbox_path", "pattern": elevation.denied_paths[0] + "/*"}
        else:
            approval_kind = decision.approval_kind
            summary_parts = []
            if decision.execution_mode == "shell":
                summary_parts.append("使用 shell 执行命令")
            else:
                summary_parts.append("需要审批的命令")
            if decision.reasons:
                summary_parts.append("; ".join(decision.reasons))
            if decision.effect_category:
                summary_parts.append(f"效果分类: {decision.effect_category.value}")
            summary = " — ".join(summary_parts)
            reasons = decision.reasons
            risks = decision.risks
            elevation_request = None
            suggested_trust = {"prefix": decision.suggested_prefix_rule} if decision.suggested_prefix_rule else None

        approval = ToolApprovalRequest(
            approval_id=approval_id,
            tool_name="shell",
            summary=summary,
            reasons=reasons,
            risks=risks,
            payload={
                "command": decision.command,
                "execution_mode": decision.execution_mode,
                "argv": decision.argv,
                "cwd": decision.cwd,
                "timeout": decision.timeout,
                "approval_kind": approval_kind,
                "suggested_prefix_rule": decision.suggested_prefix_rule,
                "effect_category": decision.effect_category.value if decision.effect_category else None,
                "elevation_request": elevation_request,
                "environment_snapshot": decision.environment_snapshot.model_dump() if decision.environment_snapshot else None,
                "approved_decision": decision.model_dump(),
            },
            suggested_action="allow_once",
            suggested_trust=suggested_trust,
        )

        return ToolResult(
            success=False,
            approval_required=True,
            approval=approval,
        )

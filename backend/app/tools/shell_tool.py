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
from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.error_detector import SandboxErrorDetector, SandboxErrorInfo, SandboxErrorType
from app.security.sandbox.factory import NullSandbox
from app.security.session_trust_store import SessionTrustStore
from app.security.shell_security import ShellSecurity
from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult

logger = logging.getLogger(__name__)

_CONDA_BASE_ENV: dict[str, str] | None = None


def _get_conda_base_env() -> dict[str, str] | None:
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
    """Shell 命令执行工具"""

    def __init__(
        self,
        security: ShellSecurity,
        path_security: PathSecurity,
        registry: CommandEffectRegistry | None = None,
        sandbox: SandboxProvider | None = None,
        session_id: str | None = None,
        trust_store: SessionTrustStore | None = None,
    ):
        self.security = security
        self.path_security = path_security
        self.registry = registry or CommandEffectRegistry()
        self.sandbox = sandbox or NullSandbox()
        self._session_id = session_id
        self.trust_store = trust_store
        self.policy = CommandPolicy(security, path_security, self.registry, trust_store=trust_store, session_id=session_id)
        self.sandbox_error_detector = SandboxErrorDetector()

    def _build_env(self) -> dict[str, str]:
        conda_env = _get_conda_base_env()
        if conda_env:
            return conda_env
        return dict(os.environ)

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            f"Execute safe commands (current platform: {self.security.platform_label}). "
            "Low-risk commands execute directly; high-risk commands and commands containing shell metacharacters require user approval. "
            "Commands run inside an OS-level sandbox that blocks network access by default. "
            "Set requires_network=true when the command needs internet access — this will prompt the user for network approval "
            "before execution, avoiding a guaranteed failure. "
            f"{self.security.command_hint}"
        )

    def get_schema(self) -> dict[str, Any]:
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
        decision = CommandDecision.model_validate(decision_data)
        elevation = decision_data.get("elevation_request")

        if elevation:
            if elevation["type"] == "network":
                decision._sandbox_allow_network = True
            elif elevation["type"] == "path":
                decision._sandbox_extra_paths = elevation["denied_paths"]

        return await self._execute_decision(decision)

    async def _execute_decision(self, decision: CommandDecision, requires_network: bool = False) -> ToolResult:
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
        if self.sandbox.is_available():
            allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
            allowed_paths = list(self.path_security.allowed_base_paths)
            if sandbox_extra_paths:
                allowed_paths.extend(sandbox_extra_paths)
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
        if sys.platform == "win32":
            # ========== Windows 第一阶段执行分支 ==========
            # 注意：命令内路径参数校验已在策略层完成（command_policy.py）
            #       这里只处理执行层的 cwd 和 sandbox_extra_paths 校验

            # 1. 路径限制（部分对齐 Unix sandbox）
            # 验证 cwd 在白名单内
            try:
                validated_cwd = self.path_security.validate_path(cwd)
            except ExternalPathError as e:
                return ToolResult(success=False, error=f"工作目录不在允许范围: {e}")

            # 验证 sandbox_extra_paths（若有）也在白名单内
            if sandbox_extra_paths:
                for extra_path in sandbox_extra_paths:
                    try:
                        self.path_security.validate_path(extra_path)
                    except ExternalPathError as e:
                        return ToolResult(success=False, error=f"额外路径 {extra_path} 不在允许范围: {e}")

            # 2. 网络权限检查（不对齐，策略层已拒绝）
            allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)

            # Windows 第一阶段：继续拒绝网络型命令（因无沙箱强制）
            if effect_category == EffectCategory.NETWORK_OUT:
                return ToolResult(
                    success=False,
                    error="Windows 第一阶段不支持网络型 shell 命令（无沙箱强制），请在 macOS/Linux 上执行"
                )

            # 本地命令：记录网络权限标志（供审计，但无技术强制）
            if not allow_network:
                logger.warning(
                    "Windows shell 命令未授权网络访问（无沙箱强制）: %s, cwd=%s",
                    command, validated_cwd
                )

            # 3. 审计日志（与 Unix 一致）
            logger.info(
                "执行 Windows shell 命令: %s, cwd=%s, network=%s, effect=%s",
                command, validated_cwd, allow_network, effect_category
            )

            # 构建 Windows 命令并执行（线程池 + 同步 subprocess）
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._sync_subprocess_run_shell,
                command,  # 原始命令（辅助函数内部包装 cmd.exe /c）
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

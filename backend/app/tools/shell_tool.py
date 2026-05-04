import asyncio
import logging
import sys
from typing import Any

from app.config.settings import config_manager
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.command_policy import CommandAction, CommandDecision, CommandPolicy
from app.security.effect_category import EffectCategory
from app.security.path_security import PathSecurity
from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.factory import NullSandbox
from app.security.shell_security import ShellSecurity
from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult

logger = logging.getLogger(__name__)


class ShellTool(BaseTool):
    """Shell 命令执行工具"""

    def __init__(
        self,
        security: ShellSecurity,
        path_security: PathSecurity,
        registry: CommandEffectRegistry | None = None,
        sandbox: SandboxProvider | None = None,
    ):
        self.security = security
        self.path_security = path_security
        self.registry = registry or CommandEffectRegistry()
        self.sandbox = sandbox or NullSandbox()
        # Policy does NOT receive sandbox — approval decisions are sandbox-independent
        self.policy = CommandPolicy(security, path_security, self.registry)

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            f"执行安全的命令（当前平台: {self.security.platform_label}）。"
            "低风险命令直接执行；高风险命令和含 shell 元语法的命令需要用户审批。"
            f"{self.security.command_hint}"
        )

    def get_schema(self) -> dict[str, Any]:
        """返回工具的 JSON Schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": f"要执行的命令。{self.security.command_hint}",
                    },
                    "cwd": {"type": "string", "description": "命令执行目录，可选"},
                    "timeout": {"type": "integer", "description": "命令超时时间，单位秒，可选"},
                },
                "required": ["command"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        command = args.get("command")
        cwd = args.get("cwd")
        timeout = args.get("timeout", config_manager.settings.execution.max_execution_time)

        if not command:
            return ToolResult(success=False, error="缺少 command 参数")

        approved_decision_data = args.get("_approved_decision")
        if approved_decision_data:
            return await self._execute_approved_decision(approved_decision_data, timeout)

        decision = self.policy.evaluate(command=command, cwd=cwd, timeout=timeout)

        if decision.action == CommandAction.DENY:
            reason_str = "; ".join(decision.reasons) if decision.reasons else "命令被拒绝"
            return ToolResult(success=False, error=reason_str)

        if decision.action == CommandAction.REQUIRE_APPROVAL:
            return self._create_approval_result(decision)

        return await self._execute_decision(decision)

    async def _execute_approved_decision(
        self, decision_data: dict, default_timeout: int
    ) -> ToolResult:
        decision = CommandDecision.model_validate(decision_data)
        return await self._execute_decision(decision)

    async def _execute_decision(self, decision: CommandDecision) -> ToolResult:
        cwd = decision.cwd or self.path_security.base_dir
        timeout = decision.timeout

        try:
            if decision.execution_mode == "shell":
                return await self._execute_shell(
                    decision.command, cwd, timeout, decision.effect_category
                )
            else:
                argv = decision.argv
                if argv is None:
                    return ToolResult(success=False, error="argv 模式决策缺少 argv")
                return await self._execute_argv(argv, cwd, timeout, decision.effect_category)
        except Exception as e:
            logger.error("Shell 执行异常: %s", e)
            return ToolResult(success=False, error=str(e))

    async def _execute_argv(
        self, argv: list[str], cwd: str, timeout: int,
        effect_category: EffectCategory | None = None,
    ) -> ToolResult:
        # Wrap in sandbox if available (confinement, not authorization)
        if self.sandbox.is_available():
            allow_network = (effect_category == EffectCategory.NETWORK_OUT)
            argv = self.sandbox.wrap_command(
                argv,
                cwd=cwd,
                allowed_paths=self.path_security.allowed_base_paths,
                allow_network=allow_network,
            )

        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            logger.error("命令执行超时: %s", " ".join(argv))
            return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")

        output = stdout.decode("utf-8", errors="ignore")
        error = stderr.decode("utf-8", errors="ignore")

        if process.returncode == 0:
            logger.info("argv 命令执行成功: %s", " ".join(argv))
            return ToolResult(success=True, output=output, data={"return_code": process.returncode})
        else:
            logger.warning("argv 命令执行失败: %s, 返回码: %s", " ".join(argv), process.returncode)
            return ToolResult(success=False, output=output, error=error)

    async def _execute_shell(
        self, command: str, cwd: str, timeout: int,
        effect_category: EffectCategory | None = None,
    ) -> ToolResult:
        if sys.platform == "win32":
            return ToolResult(success=False, error="Windows shell 模式尚未支持")

        # Wrap in sandbox if available (confinement, not authorization)
        if self.sandbox.is_available():
            allow_network = (effect_category == EffectCategory.NETWORK_OUT)
            command = self.sandbox.wrap_shell_command(
                command,
                cwd=cwd,
                allowed_paths=self.path_security.allowed_base_paths,
                allow_network=allow_network,
            )

        executable = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
        import os
        if not os.path.exists(executable):
            executable = "/bin/sh"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            executable=executable,
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
            return ToolResult(success=False, output=output, error=error)

    def _create_approval_result(self, decision: CommandDecision) -> ToolResult:
        import uuid

        approval_id = f"approval-{uuid.uuid4().hex[:12]}"

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

        approval = ToolApprovalRequest(
            approval_id=approval_id,
            tool_name="shell",
            summary=summary,
            reasons=decision.reasons,
            risks=decision.risks,
            payload={
                "command": decision.command,
                "execution_mode": decision.execution_mode,
                "argv": decision.argv,
                "cwd": decision.cwd,
                "timeout": decision.timeout,
                "approval_kind": decision.approval_kind,
                "suggested_prefix_rule": decision.suggested_prefix_rule,
                "effect_category": decision.effect_category.value if decision.effect_category else None,
                "environment_snapshot": decision.environment_snapshot.model_dump() if decision.environment_snapshot else None,
                "approved_decision": decision.model_dump(),
            },
            suggested_action="allow_once",
            suggested_trust={"prefix": decision.suggested_prefix_rule} if decision.suggested_prefix_rule else None,
        )

        return ToolResult(
            success=False,
            approval_required=True,
            approval=approval,
        )

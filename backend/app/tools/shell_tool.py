import asyncio
import logging
from typing import Any

from app.config.settings import config_manager
from app.security.path_security import PathSecurity, SecurityError
from app.security.shell_security import ShellSecurity, ShellSecurityError
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ShellTool(BaseTool):
    """Shell 命令执行工具"""

    def __init__(self, security: ShellSecurity, path_security: PathSecurity):
        self.security = security
        self.path_security = path_security

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            f"执行安全的命令（当前平台: {self.security.platform_label}）。"
            "命令按 argv 执行，不经过 shell；禁止 Shell 元语法、二级 shell、危险命令和越界路径。"
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
        """
        执行 Shell 命令

        Args:
            args: 包含 command 和可选 cwd 的字典

        Returns:
            ToolResult: 执行结果
        """
        command = args.get("command")
        cwd = args.get("cwd")
        timeout = args.get("timeout", config_manager.settings.execution.max_execution_time)

        if not command:
            return ToolResult(success=False, error="缺少 command 参数")

        try:
            argv = self.security.validate_command(command, path_security=self.path_security)
            cwd = self.path_security.validate_path(cwd or ".")

            process = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except TimeoutError:
                process.kill()
                logger.error("命令执行超时: %s", command)
                return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")

            output = stdout.decode("utf-8", errors="ignore")
            error = stderr.decode("utf-8", errors="ignore")

            if process.returncode == 0:
                logger.info("命令执行成功: %s", command)
                return ToolResult(
                    success=True, output=output, data={"return_code": process.returncode}
                )
            else:
                logger.warning("命令执行失败: %s, 返回码: %s", command, process.returncode)
                return ToolResult(success=False, output=output, error=error)

        except ShellSecurityError as e:
            logger.error("Shell 安全错误: %s", e)
            return ToolResult(success=False, error=str(e))
        except SecurityError as e:
            logger.error("Shell 路径安全错误: %s", e)
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.error("Shell 执行异常: %s", e)
            return ToolResult(success=False, error=str(e))

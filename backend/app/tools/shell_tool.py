import asyncio
from typing import Dict, Any
from app.tools.base import BaseTool, ToolResult
from app.security.shell_security import ShellSecurity, ShellSecurityError
from app.config.settings import config_manager
import logging

logger = logging.getLogger(__name__)


class ShellTool(BaseTool):
    """Shell 命令执行工具"""
    
    def __init__(self, security: ShellSecurity):
        self.security = security
    
    @property
    def name(self) -> str:
        return "shell"
    
    @property
    def description(self) -> str:
        return "执行安全的 Shell 命令"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
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
            self.security.validate_command(command)
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                logger.error(f"命令执行超时: {command}")
                return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")
            
            output = stdout.decode('utf-8', errors='ignore')
            error = stderr.decode('utf-8', errors='ignore')
            
            if process.returncode == 0:
                logger.info(f"命令执行成功: {command}")
                return ToolResult(
                    success=True,
                    output=output,
                    data={"return_code": process.returncode}
                )
            else:
                logger.warning(f"命令执行失败: {command}, 返回码: {process.returncode}")
                return ToolResult(
                    success=False,
                    output=output,
                    error=error
                )
                
        except ShellSecurityError as e:
            logger.error(f"Shell 安全错误: {str(e)}")
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Shell 执行异常: {str(e)}")
            return ToolResult(success=False, error=str(e))

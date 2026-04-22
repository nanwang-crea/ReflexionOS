import logging
import re

logger = logging.getLogger(__name__)


class ShellSecurityError(Exception):
    """Shell 安全错误"""
    pass


class ShellSecurity:
    """Shell 命令执行安全控制 - 黑名单模式"""
    
    DANGEROUS_PATTERNS = [
        r'(^|[;&|])\s*rm\s+-rf\s+/($|\s)',
        r'(^|[;&|])\s*rm\s+-rf\s+~($|\s)',
        r'(^|[;&|])\s*dd\s+if=',
        r'(^|[;&|])\s*mkfs\b',
        r':\(\)\s*\{\s*:\|:&\s*\}',
        r'(^|[;&|])\s*chmod\s+777\s+/($|\s)',
        r'(^|[;&|])\s*chown\s+root\b',
        r'(^|[;&|])\s*sudo\s+rm\b',
        r'(^|[;&|])\s*su\s+-($|\s)',
        r'(^|[;&|])\s*eval\b',
        r'(^|[;&|])\s*exec\b',
    ]

    def validate_command(self, command: str) -> None:
        """
        验证命令安全性
        
        Args:
            command: 待执行的命令
            
        Raises:
            ShellSecurityError: 命令不安全
        """
        command_normalized = command.strip()
        if not command_normalized:
            raise ShellSecurityError("命令不能为空")

        command_lower = command_normalized.lower()

        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command_lower):
                logger.warning("检测到危险命令: %s", command)
                raise ShellSecurityError(f"禁止执行危险命令: {command}")

        logger.info("命令验证通过: %s", command)

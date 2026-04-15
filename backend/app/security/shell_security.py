import re
from typing import List
import logging

logger = logging.getLogger(__name__)


class ShellSecurityError(Exception):
    """Shell 安全错误"""
    pass


class ShellSecurity:
    """Shell 命令执行安全控制"""
    
    FORBIDDEN_COMMANDS = [
        'rm -rf /',
        'dd if=',
        'mkfs',
        ':(){ :|:& };:',
        'chmod 777',
        'chown root',
        'sudo',
        'su ',
    ]
    
    ALLOWED_COMMANDS_PATTERNS = [
        r'^(pytest|python|python3)\s+',
        r'^(node|npm|yarn|pnpm)\s+',
        r'^git\s+(status|diff|log|add|commit|push|pull|branch|checkout)',
        r'^(ls|cat|grep|find|mkdir|touch|echo)\s+',
        r'^npm\s+(run|test|build|install)',
        r'^yarn\s+(run|test|build|add)',
    ]
    
    def validate_command(self, command: str) -> None:
        """
        验证命令安全性
        
        Args:
            command: 待执行的命令
            
        Raises:
            ShellSecurityError: 命令不安全
        """
        command_lower = command.lower().strip()
        
        for forbidden in self.FORBIDDEN_COMMANDS:
            if forbidden.lower() in command_lower:
                logger.warning(f"检测到禁止命令: {command}")
                raise ShellSecurityError(f"禁止执行危险命令: {command}")
        
        is_allowed = any(
            re.match(pattern, command_lower)
            for pattern in self.ALLOWED_COMMANDS_PATTERNS
        )
        
        if not is_allowed:
            logger.warning(f"命令不在允许列表中: {command}")
            raise ShellSecurityError(f"命令不在允许列表中: {command}")
        
        logger.info(f"命令验证通过: {command}")

import os
from typing import List
import logging

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """安全错误"""
    pass


class PathSecurity:
    """文件系统访问安全控制"""
    
    def __init__(self, allowed_base_paths: List[str]):
        self.allowed_base_paths = [os.path.realpath(os.path.abspath(p)) for p in allowed_base_paths]
        logger.info(f"路径安全控制初始化,允许的路径: {self.allowed_base_paths}")
    
    def validate_path(self, path: str) -> str:
        """
        验证路径是否在允许范围内
        
        Args:
            path: 待验证路径
            
        Returns:
            str: 规范化后的绝对路径
            
        Raises:
            SecurityError: 路径不在允许范围内
        """
        abs_path = os.path.abspath(path)
        
        if not any(abs_path.startswith(base) for base in self.allowed_base_paths):
            raise SecurityError(f"路径 {path} 不在允许的访问范围内")
        
        real_path = os.path.realpath(abs_path)
        if not any(real_path.startswith(base) for base in self.allowed_base_paths):
            raise SecurityError("检测到路径遍历攻击")
        
        return abs_path
    
    def validate_write_path(self, path: str) -> str:
        """
        验证写入路径
        
        Args:
            path: 待验证路径
            
        Returns:
            str: 规范化后的绝对路径
            
        Raises:
            SecurityError: 禁止写入敏感文件
        """
        abs_path = self.validate_path(path)
        
        sensitive_patterns = ['.env', 'credentials', 'secrets', '.git/config']
        if any(pattern in abs_path for pattern in sensitive_patterns):
            raise SecurityError("禁止修改敏感文件")
        
        return abs_path

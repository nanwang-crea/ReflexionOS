import logging
import os

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """安全错误"""
    pass


class PathSecurity:
    """文件系统访问安全控制"""
    
    def __init__(self, allowed_base_paths: list[str], base_dir: str | None = None):
        self.allowed_base_paths = [os.path.realpath(os.path.abspath(p)) for p in allowed_base_paths]
        # 基准目录用于解析相对路径
        self.base_dir = os.path.realpath(os.path.abspath(base_dir)) if base_dir else (
            allowed_base_paths[0] if allowed_base_paths else os.getcwd()
        )
        logger.info(
            "路径安全控制初始化,允许的路径: %s, 基准目录: %s",
            self.allowed_base_paths,
            self.base_dir,
        )
    
    def validate_path(self, path: str) -> str:
        """
        验证路径是否在允许范围内
        
        Args:
            path: 待验证路径（可以是相对路径或绝对路径）
            
        Returns:
            str: 规范化后的绝对路径
            
        Raises:
            SecurityError: 路径不在允许范围内
        """
        # 如果是相对路径，基于 base_dir 解析
        if not os.path.isabs(path):
            abs_path = os.path.realpath(os.path.join(self.base_dir, path))
        else:
            abs_path = os.path.realpath(os.path.abspath(path))
        
        # 检查是否在允许范围内
        if not any(
            abs_path == base or abs_path.startswith(f"{base}{os.sep}")
            for base in self.allowed_base_paths
        ):
            allowed_str = ", ".join(self.allowed_base_paths)
            raise SecurityError(
                f"路径不在允许范围内。\n"
                f"请求路径: {abs_path}\n"
                f"允许的目录: {allowed_str}\n"
                f"提示: 请使用相对于项目目录的路径，或使用绝对路径。"
            )
        
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

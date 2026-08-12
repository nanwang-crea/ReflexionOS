import logging
import os
from typing import TYPE_CHECKING

from app.errors import SecurityError

if TYPE_CHECKING:
    # 仅用于类型注解，运行时不导入；补上后类型检查器/IDE 能正确
    # 解析 PathSecurity.__init__ 中 "SessionTrustStore | None" 前向引用注解
    from app.security.session_trust_store import SessionTrustStore

logger = logging.getLogger(__name__)


class ExternalPathError(SecurityError):
    def __init__(self, message: str, requested_path: str, allowed_paths: list[str]):
        super().__init__(message)
        self.requested_path = requested_path
        self.allowed_paths = allowed_paths


class PathSecurity:

    def __init__(
        self,
        allowed_base_paths: list[str],
        base_dir: str | None = None,
        session_id: str | None = None,
        trust_store: "SessionTrustStore | None" = None,
    ):
        self.allowed_base_paths = [os.path.realpath(os.path.abspath(p)) for p in allowed_base_paths]
        self.base_dir = (
            os.path.realpath(os.path.abspath(base_dir))
            if base_dir
            else (allowed_base_paths[0] if allowed_base_paths else os.getcwd())
        )
        self._session_id = session_id
        self._trust_store = trust_store
        logger.info(
            "路径安全控制初始化,允许的路径: %s, 基准目录: %s",
            self.allowed_base_paths,
            self.base_dir,
        )

    def _resolve(self, path: str) -> str:
        if not os.path.isabs(path):
            return os.path.realpath(os.path.join(self.base_dir, path))
        return os.path.realpath(os.path.abspath(path))

    def _is_allowed(self, abs_path: str) -> bool:
        return any(
            abs_path == base or abs_path.startswith(f"{base}{os.sep}")
            for base in self.allowed_base_paths
        )

    def _is_trusted_external(self, abs_path: str) -> bool:
        if not self._session_id or not self._trust_store:
            return False
        return self._trust_store.matches(self._session_id, "external_path", abs_path)

    def validate_path(self, path: str) -> str:
        abs_path = self._resolve(path)
        if self._is_allowed(abs_path):
            return abs_path
        if self._is_trusted_external(abs_path):
            return abs_path
        allowed_str = ", ".join(self.allowed_base_paths)
        raise ExternalPathError(
            f"路径不在允许范围内。\n"
            f"请求路径: {abs_path}\n"
            f"允许的目录: {allowed_str}\n"
            f"提示: 请使用相对于项目目录的路径，或使用绝对路径。",
            requested_path=abs_path,
            allowed_paths=list(self.allowed_base_paths),
        )

    def validate_write_path(self, path: str) -> str:
        abs_path = self.validate_path(path)
        sensitive_patterns = [".env", "credentials", "secrets", ".git/config"]
        if any(pattern in abs_path for pattern in sensitive_patterns):
            raise SecurityError("禁止修改敏感文件")
        return abs_path


def create_project_security(project_path: str) -> PathSecurity:
    return PathSecurity(allowed_base_paths=[project_path], base_dir=project_path)

# backend/app/security/path_security.py
# 路径安全边界：判断一个路径是否落在允许的项目目录范围内，是整套命令安全体系里
# "路径越界"这一类风险的唯一裁判。command_policy.py 和 shell_security.py
# 校验命令中的路径参数、cwd 时都最终调用这里的 validate_path。
# 核心安全考量：所有路径判断都基于 os.path.realpath 后的绝对路径做前缀比较，
# 避免用户通过 ../ 相对路径、符号链接等方式绕过目录范围限制。
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
    """路径越界异常：请求路径不在允许的目录范围内时抛出。

    参数：
        message: 错误说明文本。
        requested_path: 被拒绝的绝对路径（已解析）。
        allowed_paths: 当前允许的基准路径列表，供上层展示/日志记录。
    """
    def __init__(self, message: str, requested_path: str, allowed_paths: list[str]):
        super().__init__(message)
        self.requested_path = requested_path
        self.allowed_paths = allowed_paths


class PathSecurity:
    """路径安全校验器：判断路径是否落在允许的基准目录范围内。

    典型用法：项目级实例只允许项目目录本身；如需临时放宽到某个外部路径，
    需配合 SessionTrustStore 建立会话级信任规则（_is_trusted_external），
    而不是直接扩大 allowed_base_paths（后者是永久性放宽，前者是会话级、可审计的临时放宽）。
    """

    def __init__(
        self,
        allowed_base_paths: list[str],
        base_dir: str | None = None,
        session_id: str | None = None,
        trust_store: "SessionTrustStore | None" = None,
    ):
        """初始化路径安全校验器。

        参数：
            allowed_base_paths: 允许访问的基准目录列表；会统一转成 realpath 绝对路径，
                避免因相对路径/符号链接导致后续前缀比较失真。
            base_dir: 相对路径的解析基准目录；未传时优先用 allowed_base_paths 的第一个，
                都没有则退化为当前工作目录。
            session_id: 当前会话 ID，配合 trust_store 支持会话级的临时路径信任。
            trust_store: 会话信任规则存储；用于 _is_trusted_external 查询临时放宽的外部路径。

        返回：
            无返回值（初始化完成后写日志记录允许路径与基准目录，便于排查越界拒绝的原因）。
        """
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
        """把输入路径解析成绝对真实路径（realpath）。

        参数：
            path: 相对或绝对路径字符串。

        逻辑：
            相对路径先拼接到 base_dir 再 realpath；绝对路径直接 abspath 后 realpath。
            统一走 realpath 是为了消除符号链接、多余的 ./.. 等造成的路径表示差异，
            确保后续 _is_allowed 的前缀比较是基于"真实"路径而非字面字符串。

        返回：
            解析后的绝对真实路径。
        """
        if not os.path.isabs(path):
            return os.path.realpath(os.path.join(self.base_dir, path))
        return os.path.realpath(os.path.abspath(path))

    def _is_allowed(self, abs_path: str) -> bool:
        """判断绝对路径是否落在任一允许的基准目录范围内。

        参数：
            abs_path: 已解析的绝对真实路径。

        逻辑：
            路径等于某个基准目录本身，或以"基准目录 + 分隔符"为前缀，都算允许；
            用分隔符收尾比较可以避免 "/allowed" 误匹配到 "/allowed-other" 这类
            前缀相同但实际是不同目录的路径。

        返回：
            是否在允许范围内。
        """
        return any(
            abs_path == base or abs_path.startswith(f"{base}{os.sep}")
            for base in self.allowed_base_paths
        )

    def _is_trusted_external(self, abs_path: str) -> bool:
        """判断路径是否命中会话级的"外部路径信任"规则（用于临时放宽越界限制）。

        参数：
            abs_path: 已解析的绝对真实路径。

        逻辑：
            没有 session_id 或 trust_store 时（如无会话上下文），直接判不信任；
            否则委托 trust_store.matches 按 permission="external_path" 查该会话
            是否有匹配的信任规则。这类信任只在当前会话内生效，不会永久扩大
            allowed_base_paths，是可撤销、可审计的临时放宽手段。

        返回：
            是否命中会话级外部路径信任规则。
        """
        if not self._session_id or not self._trust_store:
            return False
        return self._trust_store.matches(self._session_id, "external_path", abs_path)

    def validate_path(self, path: str) -> str:
        """校验路径是否可访问，是本类对外的核心安全接口。

        参数：
            path: 待校验的相对或绝对路径。

        逻辑：
            先解析为绝对真实路径，命中 _is_allowed（在基准目录内）或
            _is_trusted_external（会话临时信任）任一条件即视为合法；
            两者都不满足则拒绝，抛出 ExternalPathError 并在错误信息中
            列出请求路径和允许的目录范围，方便调用方/用户定位问题。

        返回：
            校验通过时返回解析后的绝对真实路径。

        异常：
            ExternalPathError: 路径既不在允许范围内、也未被会话信任时抛出。
        """
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
        """在 validate_path 基础上，额外禁止写入敏感文件。

        参数：
            path: 待校验的写入目标路径。

        逻辑：
            先走 validate_path 完成常规的目录范围校验；通过后再检查路径中是否
            包含敏感文件特征（.env、credentials、secrets、.git/config 等），
            命中任一特征即拒绝——这类文件即使在允许目录内，写入也可能造成
            凭证泄露或破坏版本控制元数据，因此需要比普通文件更严格的限制。

        返回：
            校验通过时返回解析后的绝对真实路径。

        异常：
            ExternalPathError: 继承自 validate_path 的目录越界拒绝。
            SecurityError: 命中敏感文件特征时抛出（"禁止修改敏感文件"）。
        """
        abs_path = self.validate_path(path)
        sensitive_patterns = [".env", "credentials", "secrets", ".git/config"]
        if any(pattern in abs_path for pattern in sensitive_patterns):
            raise SecurityError("禁止修改敏感文件")
        return abs_path


def create_project_security(project_path: str) -> PathSecurity:
    """便捷构造函数：创建一个只允许访问指定项目目录的 PathSecurity 实例。

    参数：
        project_path: 项目根目录路径。

    逻辑：
        allowed_base_paths 和 base_dir 都设为同一个项目路径，即最常见的
        "只能在项目目录内操作"场景，不需要单独传各种可选参数。

    返回：
        新建的 PathSecurity 实例。
    """
    return PathSecurity(allowed_base_paths=[project_path], base_dir=project_path)

# Windows Restricted Token 构造。
#
# 使用 Win32 API CreateRestrictedToken 创建受限令牌：
# - 移除 Administrators SID（降权到 Standard User）
# - 禁用 SeTakeOwnershipPrivilege / SeDebugPrivilege 等高危权限
# - 保留基本读取权限（保证 dir/cd 等正常工作）
#
# 依赖 pywin32（仅 Windows 可用）。非 Windows 平台顶层 import 会失败，
# 这里用 try/except 兜底为 None，方便单测通过 patch 替换模块引用。

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

try:
    import win32security  # type: ignore[import-untyped]
    import win32con  # type: ignore[import-untyped]
    import win32api  # type: ignore[import-untyped]
    import pywintypes  # type: ignore[import-untyped]
except ImportError:
    win32security = None  # type: ignore[assignment]
    win32con = None  # type: ignore[assignment]
    win32api = None  # type: ignore[assignment]
    pywintypes = None  # type: ignore[assignment]


def create_restricted_token() -> int | None:
    """创建 Windows Restricted Token 并返回句柄。

    返回的令牌：
    - 已移除 Administrators SID
    - 已禁用 SeTakeOwnershipPrivilege / SeDebugPrivilege
    - 可配合 CreateProcessAsUserW 使用

    Returns:
        int | None: 令牌句柄（HANDLE），失败返回 None
    """
    try:
        # 获取当前进程令牌
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_QUERY | win32con.TOKEN_DUPLICATE |
            win32con.TOKEN_ASSIGN_PRIMARY | win32con.TOKEN_ADJUST_DEFAULT,
        )

        # 禁用高风险权限
        se_privileges = [
            "SeTakeOwnershipPrivilege",
            "SeDebugPrivilege",
            "SeBackupPrivilege",
            "SeRestorePrivilege",
            "SeLoadDriverPrivilege",
            "SeTcbPrivilege",
            "SeShutdownPrivilege",
            "SeSecurityPrivilege",
        ]
        # DeletePrivilegeArray 需要 (luid, attributes) 元组，attributes 传 0 即可
        luid_list = []
        for priv_name in se_privileges:
            try:
                luid = win32security.LookupPrivilegeValue(None, priv_name)
                luid_list.append((luid, 0))
            except pywintypes.error:
                pass  # 当前令牌没有该权限，跳过

        # SidsToDisable 需要 (sid, attributes) 元组；移除 Administrators SID
        admin_sid = win32security.CreateWellKnownSid(
            win32security.WinBuiltinAdministratorsSid, None
        )
        restricted_token = win32security.CreateRestrictedToken(
            token,
            0,  # Flags：不使用 DISABLE_MAX_PRIVILEGE（改由 DeletePrivilegeArray 精确指定）
            [(admin_sid, 0)],  # SidsToDisable：移除 Administrators SID
            luid_list,  # DeletePrivilegeArray：要删除的权限
            None,  # RestrictedSids：不做限制性 SID
        )

        logger.info("创建 Restricted Token 成功")
        return restricted_token

    except Exception as e:
        logger.error("创建 Restricted Token 失败: %s", e, exc_info=True)
        return None

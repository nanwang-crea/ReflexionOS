# Elevated 档沙盒用户管理（ReflexionSandboxOffline / ReflexionSandboxOnline）。
#
# Unelevated 档使用 Restricted Token（当前用户降权），不创建新用户。
# Elevated 档创建专用本地用户，通过 CreateProcessAsUser + 对应 token 执行命令。
# Online 用户：有防火墙出站规则（允许指定端口）
# Offline 用户：防火墙禁止出站
#
# 创建用户需要管理员权限；无管理员权限时静默失败（不阻止主流程）。

from __future__ import annotations
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

OFFLINE_USER = "ReflexionSandboxOffline"
ONLINE_USER = "ReflexionSandboxOnline"


def ensure_sandbox_users() -> bool:
    """创建 Elevated 档沙盒用户（需管理员权限）。

    使用 net user /add 创建两个本地用户，账号已禁用（仅用于令牌创建）：
    - ReflexionSandboxOffline: 离线条目，防火墙禁止出站
    - ReflexionSandboxOnline: 网络条目，防火墙允许指定端口

    Returns:
        bool: 全部创建成功返回 True，任一失败返回 False
    """
    if sys.platform != "win32":
        return False

    all_ok = True
    for username in (OFFLINE_USER, ONLINE_USER):
        try:
            result = subprocess.run(
                ["net", "user", username, "/add", "/active:no"],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "创建沙盒用户 %s 返回非零退出码 %d: %s",
                    username, result.returncode, result.stderr.decode("gbk", errors="replace").strip(),
                )
                all_ok = False
            else:
                logger.info("沙盒用户 %s 已创建/已存在", username)
        except subprocess.TimeoutExpired:
            logger.warning("创建沙盒用户 %s 超时", username)
            all_ok = False
        except Exception as e:
            logger.warning("创建沙盒用户 %s 失败: %s", username, e)
            all_ok = False

    return all_ok


def get_user_token(username: str) -> int | None:
    """获取指定用户的 primary token，用于 CreateProcessAsUser。

    使用 LOGON32_LOGON_BATCH 登录类型，返回的已是 primary token，
    可直接传给 CreateProcessAsUser（无需 DuplicateTokenEx）。

    需要管理员权限或已启用"作为批处理作业登录"策略。

    Args:
        username: 用户名（OFFLINE_USER 或 ONLINE_USER）

    Returns:
        int | None: 用户令牌句柄(HANDLE)，失败返回 None
    """
    if sys.platform != "win32":
        return None

    try:
        import win32security  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]

        # LOGON32_LOGON_BATCH 返回 primary token，可直接用于 CreateProcessAsUser
        token = win32security.LogonUser(
            username,
            ".",  # 本地计算机
            "",  # 空密码
            win32con.LOGON32_LOGON_BATCH,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
        logger.info("获取用户 %s 令牌成功", username)
        return token
    except Exception as e:
        logger.error("获取用户 %s 令牌失败: %s", username, e)
        return None


def remove_sandbox_users() -> bool:
    """删除 Elevated 档沙盒用户。

    仅在测试环境或卸载时调用。

    Returns:
        bool: 全部删除成功返回 True，任一失败返回 False
    """
    if sys.platform != "win32":
        return False

    all_ok = True
    for username in (OFFLINE_USER, ONLINE_USER):
        try:
            result = subprocess.run(
                ["net", "user", username, "/delete"],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning("删除沙盒用户 %s 返回非零退出码 %d", username, result.returncode)
                all_ok = False
            else:
                logger.info("沙盒用户 %s 已删除", username)
        except Exception as e:
            logger.warning("删除沙盒用户 %s 失败: %s", username, e)
            all_ok = False

    return all_ok

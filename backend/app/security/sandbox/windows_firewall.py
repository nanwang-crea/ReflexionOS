# Elevated 档防火墙策略（Outbound 规则）。
#
# Online 用户：有选择性的出站规则（允许指定远程端口）
# Offline 用户：禁止所有出站
#
# 使用 netsh advfirewall 命令管理 Windows 防火墙规则，需要管理员权限。
# 无管理员权限时静默失败。

from __future__ import annotations
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def block_outbound_for_user(username: str) -> bool:
    """为指定沙盒用户禁止出站连接（需管理员权限）。

    添加一条 Windows 防火墙出站阻止规则，规则名为 BlockOutbound_{username}。
    适用于 ReflexionSandboxOffline 用户。

    注意：会检查 subprocess.run 的 returncode。非零退出码意味着 netsh
    规则创建失败，此时返回 False 而非静默吞掉错误。

    Args:
        username: 用户名（如 ReflexionSandboxOffline）

    运行逻辑：
        1. 非 Windows 平台直接返回 False；
        2. 构造规则名 BlockOutbound_{username}，调用 netsh advfirewall firewall
           add rule 添加一条 dir=out action=block remoteip=any 的规则，即对该
           用户账号的所有出站连接（任意远程 IP）一律阻断，实现"完全离线"隔离；
        3. 检查子进程 returncode，非零表示 netsh 规则创建失败（如权限不足），
           记录 error 日志并返回 False，不会静默吞掉错误；
        4. 命令超时或抛异常同样按失败处理并记录日志。

    Returns:
        bool: 规则添加成功返回 True，失败返回 False
    """
    if sys.platform != "win32":
        return False

    rule_name = f"BlockOutbound_{username}"
    try:
        result = subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={rule_name}", "dir=out", "action=block",
                "remoteip=any", "description=ReflexionOS sandbox block outbound",
            ],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            logger.error(
                "添加防火墙规则 %s 返回非零退出码 %d: %s",
                rule_name, result.returncode,
                result.stderr.decode("gbk", errors="replace").strip(),
            )
            return False
        logger.info("防火墙规则 %s 已添加", rule_name)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("添加防火墙规则 %s 超时", rule_name)
        return False
    except Exception as e:
        logger.error("添加防火墙规则失败: %s", e)
        return False


def allow_outbound_for_user(username: str, ports: list[int] | None = None) -> bool:
    """为指定沙盒用户允许出站连接到指定远端端口（需管理员权限）。

    适用于 ReflexionSandboxOnline 用户，仅允许指定 TCP 远程端口。
    使用 remoteport（而非 localport）匹配目标端口语义。

    Args:
        username: 用户名（如 ReflexionSandboxOnline）
        ports: 允许的远端端口列表（默认仅 443）

    运行逻辑：
        1. 非 Windows 平台直接返回 False；
        2. 确定允许的端口列表（默认仅 443，即仅放行 HTTPS）；
        3. 构造规则名 AllowOutbound_{username}，调用 netsh advfirewall firewall
           add rule 添加一条 dir=out action=allow protocol=tcp 的规则，
           remoteport 限定为传入的端口集合（用 remoteport 而非 localport，
           匹配"连接到该远程端口"的出站语义），即该用户账号只能对外发起到
           这些端口的 TCP 连接，其余出站流量仍受系统默认策略约束；
        4. 检查子进程 returncode，非零表示规则创建失败，记录 error 并返回 False；
        5. 命令超时或抛异常同样按失败处理并记录日志。

    Returns:
        bool: 规则添加成功返回 True，失败返回 False
    """
    if sys.platform != "win32":
        return False

    allowed_ports = ports or [443]
    rule_name = f"AllowOutbound_{username}"
    try:
        result = subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={rule_name}", "dir=out", "action=allow",
                "protocol=tcp",
                f"remoteport={','.join(str(p) for p in allowed_ports)}",
                "description=ReflexionOS sandbox allow outbound",
            ],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            logger.error(
                "添加防火墙规则 %s 返回非零退出码 %d: %s",
                rule_name, result.returncode,
                result.stderr.decode("gbk", errors="replace").strip(),
            )
            return False
        logger.info("防火墙规则 %s 已添加（端口: %s）", rule_name, allowed_ports)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("添加防火墙规则 %s 超时", rule_name)
        return False
    except Exception as e:
        logger.error("添加防火墙规则失败: %s", e)
        return False


def remove_rules_for_user(username: str) -> bool:
    """删除指定用户的所有沙盒防火墙规则。

    Args:
        username: 用户名（如 ReflexionSandboxOffline / ReflexionSandboxOnline）。

    运行逻辑：
        1. 非 Windows 平台直接返回 False；
        2. 依次删除该用户可能存在的两条规则：BlockOutbound_{username}（离线阻断规则）
           和 AllowOutbound_{username}（在线放行规则），无论用户实际属于哪一档，
           两个规则名都尝试删除一次，不存在的规则删除失败也不影响流程继续；
        3. 调用 netsh advfirewall firewall delete rule 逐条删除，任一条返回非零
           退出码或抛异常都记为失败（记录 warning），但会继续处理下一条规则名，
           确保尽量清理干净。

    Returns:
        bool: 两条规则均删除成功返回 True，任一失败返回 False
    """
    if sys.platform != "win32":
        return False

    all_ok = True
    for rule_name in [f"BlockOutbound_{username}", f"AllowOutbound_{username}"]:
        try:
            result = subprocess.run(
                [
                    "netsh", "advfirewall", "firewall", "delete", "rule",
                    f"name={rule_name}",
                ],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning("删除防火墙规则 %s 返回非零退出码", rule_name)
                all_ok = False
        except Exception:
            all_ok = False
    return all_ok

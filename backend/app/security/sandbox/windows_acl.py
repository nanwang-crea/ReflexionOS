# Windows 文件 ACL 写入边界控制。
#
# stub 阶段仅设置当前用户在沙箱目录上的 ALLOW ACE，不修改系统目录持久 ACL。
# 真实的写入限制（DENY ACE + 受限令牌）在 Task 6 实现。这样避免在开发/测试时
# 意外污染宿主机系统目录 DACL。
#
# 依赖 pywin32（仅 Windows 可用）。非 Windows 平台顶层 import 会失败，
# 这里用 try/except 兜底 None，方便单测通过 patch 替换模块引用。

from __future__ import annotations
import logging
import os
import shutil

logger = logging.getLogger(__name__)

try:
    import win32security  # type: ignore[import-untyped]
    import win32con  # type: ignore[import-untyped]
    import win32api  # type: ignore[import-untyped]
    import ntsecuritycon  # type: ignore[import-untyped]
except ImportError:
    win32security = None  # type: ignore[assignment]
    win32con = None  # type: ignore[assignment]
    win32api = None  # type: ignore[assignment]
    ntsecuritycon = None  # type: ignore[assignment]


def apply_write_boundary(
    work_dir: str,
    allowed_write_dirs: list[str] | None = None,
) -> bool:
    """设置沙箱目录 ACL，允许当前用户写入。

    stub 阶段仅在沙箱相关目录设置 ALLOW ACE，不修改系统目录（如 C:\\Windows）
    的持久 ACL。真实 DENY 隔离交由 Task 6 的 Restricted Token 实现。

    必须在 WindowsSandbox.run_command/run_shell_command 中检查返回值，
    失败时不应继续执行命令（否则等于静默绕过了 ACL 保护）。

    Args:
        work_dir: 沙箱根目录
        allowed_write_dirs: 额外允许写入的目录，默认仅 work_dir

    运行逻辑：
        1. 确定待处理目录列表（allowed_write_dirs 或仅 work_dir）；
        2. 逐个目录检查是否存在，不存在则跳过并记录 warning（不中断循环）；
        3. 存在的目录调用 _apply_dir_acl(allow_write=True) 添加 ALLOW ACE；
        4. 单个目录 ACL 设置异常时记录 error 但继续处理其余目录；
        5. 统计成功数，全部失败（success_count == 0）时返回 False，否则返回 True。

    Returns:
        bool: 至少有一个目录 ACL 设置成功返回 True，全部失败返回 False

    注意：部分允许目录可能尚未创建（例如未安装的 skills/packages 目录），
    此时跳过该目录而非整体失败，避免一个不存在的额外目录导致整条命令无法执行。
    """
    allowed = allowed_write_dirs or [work_dir]
    success_count = 0
    skipped: list[str] = []

    for allowed_dir in allowed:
        # 目录不存在时无法设置 DACL，跳过并记录，不中断其余目录的 ACL 设置
        if not os.path.isdir(allowed_dir):
            skipped.append(allowed_dir)
            logger.warning("ACL 跳过不存在的目录: %s", allowed_dir)
            continue
        try:
            _apply_dir_acl(allowed_dir, allow_write=True)
            success_count += 1
        except Exception as e:
            logger.error("ACL 写入边界设置失败（目录 %s）: %s", allowed_dir, e, exc_info=True)

    if success_count == 0:
        logger.error(
            "ACL 写入边界设置全部失败: allowed=%d, skipped=%d", len(allowed), len(skipped)
        )
        return False

    logger.info(
        "ACL 写入边界设置完成: allowed=%d, success=%d, skipped=%d",
        len(allowed), success_count, len(skipped),
    )
    return True


def _apply_dir_acl(directory: str, *, allow_write: bool) -> bool:
    """对单个目录设置允许/拒绝写入的 DACL。

    allow_write=True  时添加 ALLOW ACE，授予 FILE_ALL_ACCESS
    allow_write=False 时添加 DENY ACE，阻止 FILE_GENERIC_WRITE + DELETE

    Args:
        directory: 目标目录路径。
        allow_write: True 表示放行写入（ALLOW ACE），False 表示禁止写入（DENY ACE）。
            当前 apply_write_boundary 只会以 True 调用本函数（stub 阶段不做 DENY 隔离，
            真实 DENY 隔离交由 Task 6 实现），DENY 分支代码已具备但暂未被上层触发。

    运行逻辑：
        1. 获取当前进程访问令牌对应的用户 SID；
        2. 读取目标目录现有的安全描述符与 DACL（不存在则新建一个空 ACL）；
        3. 按 allow_write 追加对应的 ACE（ALLOW 授予 FILE_ALL_ACCESS，
           DENY 禁止 FILE_GENERIC_WRITE | DELETE）；
        4. 将修改后的 DACL 写回安全描述符并调用 SetFileSecurity 持久化到目录。

    Returns:
        bool: 始终返回 True（成功路径），异常由调用方 apply_write_boundary 捕获处理。
    """
    user_sid = win32security.GetTokenInformation(
        win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_QUERY,
        ),
        win32security.TokenUser,
    )[0]

    security_descriptor = win32security.GetFileSecurity(
        directory, win32security.DACL_SECURITY_INFORMATION
    )
    dacl = security_descriptor.GetSecurityDescriptorDacl()
    if dacl is None:
        dacl = win32security.ACL()

    if allow_write:
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, user_sid
        )
    else:
        dacl.AddAccessDeniedAce(
            win32security.ACL_REVISION,
            ntsecuritycon.FILE_GENERIC_WRITE | ntsecuritycon.DELETE,
            user_sid,
        )

    security_descriptor.SetSecurityDescriptorDacl(1, dacl, 0)
    win32security.SetFileSecurity(
        directory, win32security.DACL_SECURITY_INFORMATION, security_descriptor
    )
    logger.debug("ACL 更新: %s write=%s", directory, allow_write)
    return True


def create_sandbox_work_dir(base_dir: str) -> str:
    """在 base_dir 下创建沙箱工作目录并设置 ACL。

    Args:
        base_dir: 沙箱工作目录所在的父目录。

    运行逻辑：
        1. 在 base_dir 下拼出固定名称的子目录 .reflexion-sandbox；
        2. os.makedirs(exist_ok=True) 创建该目录（已存在则忽略）；
        3. 调用 apply_write_boundary 为该子目录及 base_dir 设置写入 ACL，
           允许当前用户写入这两个目录。

    Returns:
        str: 新建（或已存在）的沙箱工作目录绝对/相对路径（与 base_dir 拼接结果一致）。
    """
    sandbox_dir = os.path.join(base_dir, ".reflexion-sandbox")
    os.makedirs(sandbox_dir, exist_ok=True)
    apply_write_boundary(sandbox_dir, allowed_write_dirs=[sandbox_dir, base_dir])
    return sandbox_dir


def cleanup_sandbox_work_dir(sandbox_dir: str) -> None:
    """删除沙箱工作目录。

    Args:
        sandbox_dir: 待清理的沙箱工作目录路径（通常是 create_sandbox_work_dir 的返回值）。

    运行逻辑：目录存在时用 shutil.rmtree 递归删除，ignore_errors=True 表示
    删除过程中的错误（如文件被占用）不会抛异常，只是尽力清理；目录不存在则直接跳过。

    Returns:
        None
    """
    if os.path.isdir(sandbox_dir):
        shutil.rmtree(sandbox_dir, ignore_errors=True)

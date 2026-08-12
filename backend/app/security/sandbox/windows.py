# Windows 沙盒提供者。
#
# 使用 CreateProcessAsUser + Restricted Token 执行命令，实现 OS 级隔离：
# - Unelevated 档：Restricted Token（移除 Administrator SID + 禁用高危权限）
# - Elevated 档（未来）：专用用户 + 防火墙规则
#
# macOS/Linux 平台 is_available() 返回 False。

from __future__ import annotations
import contextlib
import logging
import sys

from app.security.sandbox.base import SandboxProvider, SandboxRunResult
from app.security.sandbox.sandbox_policy import SandboxLevel
from app.security.sandbox.windows_token import create_restricted_token
from app.security.sandbox.windows_acl import apply_write_boundary

logger = logging.getLogger(__name__)


class WindowsSandbox(SandboxProvider):
    """Windows 沙盒提供者：使用 Restricted Token + ACL 执行命令。

    Unelevated 档：Restricted Token（移除 Administrator SID + 禁用高危权限）
    Elevated 档（Task 6）：Online/Offline 用户 + 防火墙规则
    """

    def __init__(self, level: SandboxLevel = SandboxLevel.DEV) -> None:
        self.level = level
        self._elevated = False

    def is_available(self) -> bool:
        """仅 Windows 平台可用。"""
        return sys.platform == "win32"

    def wrap_command(self, argv, *, cwd, **kw):
        """回退到直接执行（WindowsSandbox 主要使用 run_command）。"""
        return list(argv)

    def wrap_shell_command(self, command, *, cwd, **kw):
        """回退到直接执行（WindowsSandbox 主要使用 run_shell_command）。"""
        return command

    def run_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int = 300,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """使用 Restricted Token + ACL 执行 argv 命令。

        Args:
            argv: 命令参数列表（如 ["npm", "install"]）
            cwd: 工作目录
            timeout: 超时秒数（传给 proc.communicate）
            allowed_paths: 允许写入的路径
            read_only_paths: 只读路径
            allow_network: 是否允许网络（Unelevated 暂不支持）
            allow_ipc: 是否允许 IPC

        Returns:
            SandboxRunResult | None: 执行结果
        """
        if sys.platform != "win32":
            return None

        try:
            restricted_token = create_restricted_token()
            if restricted_token is None:
                return SandboxRunResult(
                    success=False, output="", error="创建 Restricted Token 失败", return_code=-1
                )

            if allowed_paths:
                if not apply_write_boundary(cwd, allowed_write_dirs=allowed_paths):
                    return SandboxRunResult(
                        success=False, output="", error="ACL 写入边界设置失败", return_code=-1
                    )

            return self._exec_in_sandbox(argv, cwd, restricted_token, timeout=timeout)
        except Exception as e:
            logger.error("WindowsSandbox.run_command 失败: %s", e, exc_info=True)
            return SandboxRunResult(success=False, output="", error=str(e), return_code=-1)

    def run_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        timeout: int = 300,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """使用 Restricted Token + ACL 执行 shell 命令（cmd.exe /c）。

        与 run_command 的区别：命令包装为 cmd.exe /c "{command}" 后执行。
        """
        if sys.platform != "win32":
            return None

        try:
            restricted_token = create_restricted_token()
            if restricted_token is None:
                return SandboxRunResult(
                    success=False, output="", error="创建 Restricted Token 失败", return_code=-1
                )

            if allowed_paths:
                if not apply_write_boundary(cwd, allowed_write_dirs=allowed_paths):
                    return SandboxRunResult(
                        success=False, output="", error="ACL 写入边界设置失败", return_code=-1
                    )

            # 包装为 cmd.exe /c
            shell_argv = ["cmd.exe", "/c", command]
            return self._exec_in_sandbox(shell_argv, cwd, restricted_token, timeout=timeout)
        except Exception as e:
            logger.error("WindowsSandbox.run_shell_command 失败: %s", e, exc_info=True)
            return SandboxRunResult(success=False, output="", error=str(e), return_code=-1)

    def _exec_in_sandbox(
        self,
        argv: list[str],
        cwd: str,
        token: int,
        timeout: int = 300,
    ) -> SandboxRunResult:
        """使用 CreateProcessAsUser + Restricted Token 执行命令。

        通过线程并发读取 stdout/stderr pipe（避免 pipe buffer 写满触发 deadlock），
        循环读取直到 EOF（不受 64KB 截断限制）。

        注意：CreateRestrictedToken 返回的已经是 Primary Token，无需 DuplicateTokenEx。
        pipe 句柄必须设置 bInheritHandle=True 才能被子进程继承。
        超时后 TerminateProcess + CloseHandle 清理全部句柄。
        """
        try:
            import win32process  # type: ignore[import-untyped]
            import win32con  # type: ignore[import-untyped]
            import win32pipe  # type: ignore[import-untyped]
            import win32event  # type: ignore[import-untyped]
            import win32api  # type: ignore[import-untyped]
            import win32security  # type: ignore[import-untyped]
            import msvcrt
            import os as os_mod
            import subprocess as _sp
            import threading
        except ImportError:
            logger.error("pywin32 未安装，无法使用 CreateProcessAsUser")
            return SandboxRunResult(
                success=False, output="", error="pywin32 not installed", return_code=-1
            )

        sa = win32security.SECURITY_ATTRIBUTES()
        sa.bInheritHandle = True

        try:
            out_read, out_write = win32pipe.CreatePipe(sa, 0)
            err_read, err_write = win32pipe.CreatePipe(sa, 0)

            si = win32process.STARTUPINFO()
            si.hStdOutput = out_write
            si.hStdError = err_write
            si.dwFlags = win32con.STARTF_USESTDHANDLES | win32con.STARTF_USESHOWWINDOW
            si.wShowWindow = win32con.SW_HIDE

            cmd_line = _sp.list2cmdline(argv)

            proc_handle, thread_handle, pid, tid = win32process.CreateProcessAsUser(
                token,
                None,  # lpApplicationName
                cmd_line,
                None,  # lpProcessAttributes
                None,  # lpThreadAttributes
                True,  # bInheritHandles
                0,     # dwCreationFlags
                None,  # lpEnvironment
                cwd,
                si,
            )

            # 关闭写端，否则读端永远读不完
            win32api.CloseHandle(out_write)
            win32api.CloseHandle(err_write)

            # 将 pipe PyHANDLE 转换为 Python fd
            out_fd = msvcrt.open_osfhandle(
                out_read.Detach(), os_mod.O_RDONLY | os_mod.O_BINARY
            )
            err_fd = msvcrt.open_osfhandle(
                err_read.Detach(), os_mod.O_RDONLY | os_mod.O_BINARY
            )

            # 用线程并发读取 stdout/stderr，避免 pipe buffer 满时死锁
            collected_stdout: list[bytes] = []
            collected_stderr: list[bytes] = []
            read_error: list[str] = []

            def _read_pipe(fd: int, dest: list[bytes]) -> None:
                """循环读取 fd 直到 EOF，不受单次 read 大小限制。"""
                try:
                    while True:
                        chunk = os_mod.read(fd, 65536)
                        if not chunk:
                            break
                        dest.append(chunk)
                except Exception as exc:
                    read_error.append(str(exc))

            t_out = threading.Thread(target=_read_pipe, args=(out_fd, collected_stdout), daemon=True)
            t_err = threading.Thread(target=_read_pipe, args=(err_fd, collected_stderr), daemon=True)
            t_out.start()
            t_err.start()

            # 等待进程完成
            wait_result = win32event.WaitForSingleObject(
                proc_handle, timeout * 1000
            )

            # 不管是否超时，先关读端让读线程退出（避免线程 join 卡死）
            os_mod.close(out_fd)
            os_mod.close(err_fd)
            t_out.join(timeout=5)
            t_err.join(timeout=5)

            if wait_result == win32event.WAIT_TIMEOUT:
                win32process.TerminateProcess(proc_handle, -1)
                win32api.CloseHandle(proc_handle)
                win32api.CloseHandle(thread_handle)
                return SandboxRunResult(
                    success=False, output="", error="命令执行超时", return_code=-1,
                )

            exit_code = win32process.GetExitCodeProcess(proc_handle)
            win32api.CloseHandle(proc_handle)
            win32api.CloseHandle(thread_handle)

            stdout_text = b"".join(collected_stdout)
            stderr_text = b"".join(collected_stderr) if collected_stderr else b""

            output = self._decode_output(stdout_text)
            error = self._decode_output(stderr_text) if stderr_text else None
            if read_error:
                logger.warning("pipe 读取异常: %s", read_error)

            return SandboxRunResult(
                success=(exit_code == 0),
                output=output.strip(),
                error=error.strip() if error else None,
                return_code=exit_code,
            )
        except Exception as e:
            logger.error("CreateProcessAsUser 失败: %s", e, exc_info=True)
            for h in ['out_read', 'out_write', 'err_read', 'err_write', 'proc_handle', 'thread_handle']:
                # 逐个关闭句柄，单个关闭失败不应阻断后续句柄清理
                with contextlib.suppress(Exception):
                    win32api.CloseHandle(locals().get(h))
            return SandboxRunResult(
                success=False, output="", error=str(e), return_code=-1,
            )

    @staticmethod
    def _decode_output(data: bytes) -> str:
        """解码 Windows 输出（GBK 降级到 UTF-8）。"""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

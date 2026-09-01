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
        """初始化 Windows 沙盒提供者。

        Args:
            level: 沙盒隔离档位（DEV/Unelevated/Elevated 等），默认 DEV。

        当前仅记录档位与是否已提权（_elevated），实际隔离逻辑在 run_command/run_shell_command 中执行。
        """
        self.level = level
        self._elevated = False

    def is_available(self) -> bool:
        """判断当前平台是否支持本沙盒实现。

        运行逻辑：仅当运行平台为 win32 时才可用；macOS/Linux 一律不可用。

        Returns:
            bool: True 表示可在当前进程使用 Windows 沙盒。
        """
        return sys.platform == "win32"

    def wrap_command(self, argv, *, cwd, **kw):
        """按 SandboxProvider 接口要求包装 argv 命令。

        Args:
            argv: 原始命令参数列表。
            cwd: 工作目录（本实现未使用，仅为接口兼容保留）。
            **kw: 其余隔离参数（本实现未使用）。

        运行逻辑：WindowsSandbox 的实际隔离在 run_command 中通过 Restricted Token 完成，
        本方法只是接口占位，直接原样返回参数列表，不做任何包装。

        Returns:
            list: 与 argv 内容相同的命令参数列表。
        """
        return list(argv)

    def wrap_shell_command(self, command, *, cwd, **kw):
        """按 SandboxProvider 接口要求包装 shell 命令字符串。

        Args:
            command: 原始 shell 命令字符串。
            cwd: 工作目录（本实现未使用，仅为接口兼容保留）。
            **kw: 其余隔离参数（本实现未使用）。

        运行逻辑：实际隔离在 run_shell_command 中通过 Restricted Token 完成，
        本方法只是接口占位，原样返回命令字符串，不做任何包装。

        Returns:
            str: 与 command 内容相同的命令字符串。
        """
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

        与 run_command 的区别：命令不是直接以 argv 执行，而是包装为
        ["cmd.exe", "/c", command] 交给 cmd.exe 解析后再执行，用于支持管道、
        重定向等 shell 语法。安全隔离手段（Restricted Token + ACL 写边界）与
        run_command 完全一致。

        Args:
            command: 待执行的 shell 命令字符串（如 "dir & echo done"）。
            cwd: 工作目录。
            timeout: 超时秒数（传给 proc.communicate）。
            allowed_paths: 允许写入的路径，会通过 ACL 设置写入边界。
            read_only_paths: 只读路径（当前实现未使用，仅为接口兼容保留）。
            allow_network: 是否允许网络（Unelevated 暂不支持）。
            allow_ipc: 是否允许 IPC（当前实现未使用，仅为接口兼容保留）。

        Returns:
            SandboxRunResult | None: 非 Windows 平台返回 None；
            Restricted Token 创建失败或 ACL 设置失败时返回 success=False 的结果；
            正常执行后返回命令的输出/错误/返回码。
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

        Args:
            argv: 命令参数列表，会通过 subprocess.list2cmdline 拼接为命令行。
            cwd: 子进程的工作目录。
            token: 已创建好的 Restricted Token（Primary Token）句柄，子进程将以此
                令牌的降权身份运行，实现权限隔离。
            timeout: 等待子进程结束的超时秒数，超时后强制终止进程。

        运行逻辑：
            1. 创建 stdout/stderr 匿名管道（可继承），构造 STARTUPINFO 重定向标准输出/错误；
            2. 调用 CreateProcessAsUser 以 token 身份创建子进程；
            3. 关闭管道写端，避免读端永久阻塞；
            4. 用两个后台线程分别循环读取 stdout/stderr，防止单管道写满导致双方死锁；
            5. WaitForSingleObject 等待进程结束或超时；无论是否超时都先关闭读端 fd
               让读线程能够退出，再 join 等待线程收尾；
            6. 超时则 TerminateProcess 并清理句柄，返回失败结果；
            7. 正常结束则读取退出码，解码输出后打包返回。

        Returns:
            SandboxRunResult: 包含 success（退出码是否为 0）、output（解码后的
            stdout）、error（解码后的 stderr，若有）、return_code（子进程退出码）。
            发生异常时返回 success=False 的结果，并尽力清理已分配的句柄。
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
        """解码 Windows 子进程输出字节流。

        Args:
            data: 从 stdout/stderr 管道读取到的原始字节。

        运行逻辑：优先按 UTF-8 解码；失败则降级尝试 GBK（Windows 中文环境下
        cmd.exe 等程序常用该编码输出）；两者都失败则用 UTF-8 + errors="replace"
        兜底，避免因编码问题抛异常导致整体执行失败。

        Returns:
            str: 解码后的文本，可能包含替换字符（当兜底分支被触发时）。
        """
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

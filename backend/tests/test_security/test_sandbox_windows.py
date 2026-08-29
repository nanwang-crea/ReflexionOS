# WindowsSandbox 主类（Task 6: CreateProcessAsUser + Restricted Token）单测
import sys
from unittest.mock import MagicMock, patch
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows sandbox tests require Windows APIs",
)


@pytest.fixture(autouse=True)
def mock_windows_only():
    """Mock pywin32 模块，避免非 Windows 上 import 失败"""
    if sys.platform != "win32":
        with patch.dict("sys.modules", {
            "win32security": MagicMock(),
            "win32con": MagicMock(),
            "win32process": MagicMock(),
            "win32pipe": MagicMock(),
            "win32event": MagicMock(),
            "win32api": MagicMock(),
            "win32file": MagicMock(),
            "pywintypes": MagicMock(),
        }):
            yield
    else:
        yield


@pytest.fixture
def windows_sandbox():
    from app.security.sandbox.windows import WindowsSandbox
    return WindowsSandbox()


def test_is_available_on_windows(windows_sandbox):
    """Windows 平台应可用（检测 sys.platform == win32）"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        assert windows_sandbox.is_available() is True


def test_is_available_not_on_windows(windows_sandbox):
    """非 Windows 平台不可用"""
    with patch("app.security.sandbox.windows.sys.platform", "linux"):
        assert windows_sandbox.is_available() is False


def test_run_command_argv_mode(windows_sandbox):
    """run_command 应调用 _exec_in_sandbox 执行 argv"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
            from app.security.sandbox.base import SandboxRunResult
            mock_exec.return_value = SandboxRunResult(success=True, output="hello", error=None, return_code=0)
            result = windows_sandbox.run_command(["echo", "hello"], cwd=r"C:\work")
            assert result is not None
            assert result.success is True
            assert result.output == "hello"


def test_run_shell_command_shell_mode(windows_sandbox):
    """run_shell_command 应调用 _exec_in_sandbox 执行 cmd.exe /c"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
            from app.security.sandbox.base import SandboxRunResult
            mock_exec.return_value = SandboxRunResult(success=True, output="dir output", error=None, return_code=0)
            result = windows_sandbox.run_shell_command("dir", cwd=r"C:\work")
            assert result is not None
            assert result.success is True
            assert result.output == "dir output"


def test_run_command_passes_restricted_token(windows_sandbox):
    """run_command 应创建并使用 Restricted Token 执行"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token") as mock_token:
            mock_token.return_value = 12345
            with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
                from app.security.sandbox.base import SandboxRunResult
                mock_exec.return_value = SandboxRunResult(success=True, output="", error=None, return_code=0)
                windows_sandbox.run_command(["echo", "hi"], cwd=r"C:\work")
                mock_token.assert_called_once()


def test_run_command_inherits_wrap_behaviors(windows_sandbox):
    """wrap_command / wrap_shell_command 仍可用（回退到无沙盒版本）"""
    argv = windows_sandbox.wrap_command(["echo", "hi"], cwd="/tmp")
    assert argv == ["echo", "hi"]
    cmd = windows_sandbox.wrap_shell_command("echo hi", cwd="/tmp")
    assert cmd == "echo hi"


def test_run_command_applies_acls(windows_sandbox):
    """run_command 应通过 apply_write_boundary 限制写入范围"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.apply_write_boundary") as mock_acl:
            with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
                from app.security.sandbox.base import SandboxRunResult
                mock_exec.return_value = SandboxRunResult(success=True, output="", error=None, return_code=0)
                windows_sandbox.run_command(["npm", "install"], cwd=r"C:\work", allowed_paths=[r"C:\work"])
                mock_acl.assert_called_once()


def test_run_command_fail_close_on_acl_failure(windows_sandbox):
    """ACL 设置失败时 run_command 应提前返回不执行命令"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.apply_write_boundary") as mock_acl:
            mock_acl.return_value = False
            with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
                result = windows_sandbox.run_command(["npm", "install"], cwd=r"C:\work", allowed_paths=[r"C:\work"])
                mock_exec.assert_not_called()
                assert result is not None
                assert result.success is False
                assert "ACL" in (result.error or "")


def test_run_shell_command_fail_close_on_acl_failure(windows_sandbox):
    """ACL 设置失败时 run_shell_command 应提前返回不执行命令"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.apply_write_boundary") as mock_acl:
            mock_acl.return_value = False
            with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
                result = windows_sandbox.run_shell_command("npm install", cwd=r"C:\work", allowed_paths=[r"C:\work"])
                mock_exec.assert_not_called()
                assert result is not None
                assert result.success is False
                assert "ACL" in (result.error or "")


# ── Task 6: CreateProcessAsUser 真实沙盒隔离 ──────────────────────

@pytest.fixture
def mock_cpas():
    """Mock CreateProcessAsUser 管线上所有 Win32 API 调用，含线程安全的 pipe 读取。"""
    with patch("win32process.CreateProcessAsUser") as mock_create:
        mock_create.return_value = (MagicMock(), MagicMock(), 100, 200)

        with patch("win32pipe.CreatePipe") as mock_pipe:
            mock_pipe.return_value = (MagicMock(), MagicMock())

            with patch("win32security.SECURITY_ATTRIBUTES") as mock_sa:
                mock_sa.return_value = MagicMock()

                with patch("win32event.WaitForSingleObject", return_value=0):
                    with patch("win32process.GetExitCodeProcess", return_value=0):
                        with patch("msvcrt.open_osfhandle", side_effect=[3, 4]):
                            # os.read: 第一次返回内容，第二次返回空（EOF，让读线程退出）
                            read_side_effects = [
                                b"output_text",  # stdout chunk
                                b"",              # stdout EOF
                                b"error_text",    # stderr chunk
                                b"",              # stderr EOF
                            ]
                            with patch("os.read", side_effect=read_side_effects):
                                with patch("os.close"):
                                    with patch("win32api.CloseHandle"):
                                        yield mock_create


def test_exec_in_sandbox_calls_create_process_as_user(windows_sandbox, mock_cpas):
    """_exec_in_sandbox 应调用 CreateProcessAsUser，而非 subprocess.Popen"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token", return_value=12345):
            result = windows_sandbox.run_command(["echo", "hello"], cwd=r"C:\work")
            assert result is not None
            assert result.success is True
            assert result.output == "output_text"
            mock_cpas.assert_called_once()


def test_exec_in_sandbox_passes_token_and_command(windows_sandbox, mock_cpas):
    """CreateProcessAsUser 应收到正确的 token 和命令行"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token", return_value=99999):
            with patch("app.security.sandbox.windows.apply_write_boundary", return_value=True):
                with patch.object(windows_sandbox, "_decode_output", return_value="ok"):
                    windows_sandbox.run_command(
                        ["npm", "install", "--production"], cwd=r"C:\project",
                        allowed_paths=[r"C:\project"],
                    )
                    token_arg, cmd_line_arg = mock_cpas.call_args[0][0], mock_cpas.call_args[0][2]
                    assert str(token_arg) == "99999"
                    assert "npm" in cmd_line_arg
                    assert "install" in cmd_line_arg


def test_exec_in_sandbox_timeout_terminates_process(windows_sandbox):
    """超时时应调用 TerminateProcess"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token", return_value=12345):
            with patch("win32process.CreateProcessAsUser") as mock_create:
                mock_proc = MagicMock()
                mock_thread = MagicMock()
                mock_create.return_value = (mock_proc, mock_thread, 100, 200)

                with patch("win32pipe.CreatePipe") as mock_pipe:
                    mock_pipe.return_value = (MagicMock(), MagicMock())
                    with patch("win32security.SECURITY_ATTRIBUTES") as mock_sa:
                        mock_sa.return_value = MagicMock()
                        # open_osfhandle + os.read + os.close for pipe read threads
                        with patch("msvcrt.open_osfhandle", side_effect=[3, 4]):
                            with patch("os.read", return_value=b""):
                                with patch("os.close"):
                                    with patch("win32event.WaitForSingleObject", return_value=258):
                                        with patch("win32process.TerminateProcess") as mock_term:
                                            with patch("win32api.CloseHandle"):
                                                result = windows_sandbox.run_command(
                                                    ["sleep", "999"], cwd=r"C:\work"
                                                )
                                                assert result is not None
                                                assert result.success is False
                                                assert "超时" in (result.error or "")
                                                mock_term.assert_called_once_with(mock_proc, -1)


def test_exec_in_sandbox_pipe_handles_closed_on_exception(windows_sandbox):
    """异常路径应清理已创建的 pipe 句柄（不泄漏）"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token", return_value=12345):
            with patch("win32process.CreateProcessAsUser",
                       side_effect=RuntimeError("CPAS failed")):
                with patch("win32pipe.CreatePipe") as mock_pipe:
                    mock_pipe.return_value = (MagicMock(), MagicMock())
                    with patch("win32security.SECURITY_ATTRIBUTES") as mock_sa:
                        mock_sa.return_value = MagicMock()
                        with patch("win32api.CloseHandle") as mock_close:
                            result = windows_sandbox.run_command(["echo", "hi"], cwd=r"C:\work")
                            assert result is not None
                            assert result.success is False
                            assert mock_close.call_count >= 1


def test_exec_in_sandbox_separates_stdout_stderr(windows_sandbox):
    """CreateProcessAsUser 应为 stdout/stderr 创建独立 pipe"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token", return_value=12345):
            with patch("win32process.CreateProcessAsUser") as mock_create:
                mock_create.return_value = (MagicMock(), MagicMock(), 100, 200)
                pipe_calls = []

                def pipe_side_effect(sa, flags):
                    h = MagicMock()
                    pipe_calls.append((sa, flags))
                    return (h, h)

                with patch("win32pipe.CreatePipe", side_effect=pipe_side_effect):
                    with patch("win32security.SECURITY_ATTRIBUTES") as mock_sa:
                        mock_sa.return_value = MagicMock()
                        with patch("msvcrt.open_osfhandle", side_effect=[3, 4]):
                            with patch("os.read", return_value=b""):
                                with patch("os.close"):
                                    with patch("win32event.WaitForSingleObject", return_value=0):
                                        with patch("win32process.GetExitCodeProcess", return_value=0):
                                            with patch("win32api.CloseHandle"):
                                                windows_sandbox.run_command(["echo", "hi"], cwd=r"C:\work")
                                                assert len(pipe_calls) == 2, "应为 stdout/stderr 各创建一个 pipe"


def test_exec_in_sandbox_without_pywin32_fails_gracefully(windows_sandbox):
    """没有 pywin32 时应返回错误而非崩溃"""
    with patch("app.security.sandbox.windows.sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token", return_value=12345):
            original_import = __builtins__['__import__']

            def mock_import(name, *args, **kwargs):
                if name.startswith('win32'):
                    raise ImportError(f"No module named {name}")
                return original_import(name, *args, **kwargs)

            with patch('builtins.__import__', side_effect=mock_import):
                result = windows_sandbox.run_command(["echo", "hi"], cwd=r"C:\work")
                assert result is not None
                assert result.success is False
                assert "pywin32" in (result.error or "")

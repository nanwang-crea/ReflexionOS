# backend/tests/test_security/test_shell_security_quoting.py
"""验证 ShellSecurity.validate_command 在 Windows 平台上的引号剥离行为。

背景 bug：shlex.split(command, posix=False) 为保留 Windows 路径反斜杠不转义，
不会像 posix 模式那样剥离引号，导致 `powershell -Command "Write-Output 'x'"`
这类命令解析出的 argv 中，-Command 参数值原样带着外层双引号
（如 '"Write-Output \'x\'"'）。这个带引号的字符串被原样传给 subprocess，
PowerShell/cmd 收到字面量引号后把整段参数当普通字符串回显，并未真正执行内层命令。
"""
from app.security.shell_security import ShellSecurity


class TestWindowsQuoteStripping:
    def test_powershell_command_arg_strips_wrapping_quotes(self):
        security = ShellSecurity(platform_name="win32")
        result = security.validate_command(
            "powershell -NoProfile -Command \"Write-Output 'hint test ok'\""
        )
        assert result.argv == [
            "powershell", "-NoProfile", "-Command", "Write-Output 'hint test ok'",
        ]

    def test_cmd_c_arg_strips_wrapping_quotes(self):
        security = ShellSecurity(platform_name="win32")
        result = security.validate_command('cmd /c "echo hi"')
        assert result.argv == ["cmd", "/c", "echo hi"]

    def test_windows_path_backslash_not_mangled(self):
        # 路径参数未加引号，不应被引号剥离逻辑影响，反斜杠也不能被 shlex 转义破坏
        security = ShellSecurity(platform_name="win32")
        result = security.validate_command(r"python C:\Users\foo\bar.py")
        assert result.argv == ["python", r"C:\Users\foo\bar.py"]

    def test_unix_platform_unaffected(self):
        # posix 模式下 shlex 本身就会剥离引号，此改动只在 Windows 分支生效，
        # 这里确认 Unix 平台行为不受影响（回归防护）
        security = ShellSecurity(platform_name="darwin")
        result = security.validate_command("bash -c \"echo hi\"")
        assert result.argv == ["bash", "-c", "echo hi"]
